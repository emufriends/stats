"""Production gate for uncached filtered reads and mixed refresh concurrency.

This gate deliberately disables default-snapshot and persistent-response-cache
shortcuts. Pass the real refresh command after ``--refresh-command`` to make
the mixed read/refresh result mandatory for a production pass.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if os.name != "nt":
    import resource

from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3RequestAdapter,
    Phase3ResponseCache,
)


FILTERED_REQUESTS = [
    {
        "stats_page": "cards", "is_mw": 1, "player_elo_min": 700,
        "opponent_elo_min": 300, "date_from": "2026-01-01", "limit": 100,
    },
    {
        "stats_page": "actions", "actions_view": "starting_position", "is_mw": 1,
        "starting_positions": ["First player"], "date_from": "2026-01-01", "limit": 100,
    },
    {
        "stats_page": "combinations", "combinations_view": "card_card", "is_mw": 1,
        "maps": ["Map 1a: Observation Tower"], "combination_min_plays": 25, "limit": 100,
    },
    {
        "stats_page": "combinations", "combinations_view": "card_action_card", "is_mw": 1,
        "player_elo_min": 301, "opponent_elo_min": 300, "limit": 100,
    },
    {
        "stats_page": "players", "players_view": "general", "is_mw": 1,
        "players_player": "Propaganda Panda", "opponent_elo_min": 1, "limit": 100,
    },
]


def refresh_progress(path: Path | None) -> dict[str, Any]:
    """Read an atomic progress record; absence is not proof of refresh work."""
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def mixed_refresh_pass(results: list[dict[str, Any]], refresh_result: dict[str, Any]) -> bool:
    # A no-op/reused refresh or queries that finished before rebuilding began
    # cannot substitute for reads while real derivative work was in flight.
    required = {
        (request['stats_page'], request.get('combinations_view') or request.get('players_view'))
        for request in FILTERED_REQUESTS
    }
    measured = {
        (item.get('page'), item.get('view')) for item in results
        if item.get('status') == 'ok' and item.get('refresh_running')
        and 48 <= item.get('refresh_progress', 0) < 96
    }
    # One fast route cannot stand in for the other, potentially expensive,
    # routes. Each probe needs its own successful read during real rebuilding.
    return refresh_result.get('status') == 'ok' and required.issubset(measured)


def stop_refresh_process(process: subprocess.Popen | None) -> None:
    """Do not leave a builder running after an interrupted/failed gate."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def rss_bytes() -> int | None:
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = ctypes.c_void_p
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
        get_info.restype = ctypes.c_int
        if get_info(get_process(), ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value * (1024 if sys.platform != "darwin" else 1))


def system_memory_bytes() -> tuple[int | None, int | None]:
    """Return total and available system memory without another dependency."""
    if os.name == "nt":
        return None, None
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            name, raw = line.split(":", 1)
            if name in {"MemTotal", "MemAvailable"}:
                values[name] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return None, None
    return values.get("MemTotal"), values.get("MemAvailable")


def run(
    root: Path,
    refresh_command: list[str] | None,
    latency_limit: float,
    generation_id: str | None = None,
    progress_file: Path | None = None,
    query_interval_seconds: float = 300,
) -> dict[str, Any]:
    if latency_limit <= 0 or query_interval_seconds <= 0:
        raise ValueError('latency limit and query interval must be positive')
    manager = GenerationManager(
        root / "phase2_private_data" / "generations",
        root / "phase3_private_serving" / "current.json",
    )
    generation = (
        manager.inspect(generation_id)
        if generation_id is not None else manager.current()
    )
    if generation is None:
        raise RuntimeError(
            f"generation {generation_id!r} does not exist"
            if generation_id is not None else "no active generation"
        )
    refresh_process = subprocess.Popen(refresh_command, cwd=root) if refresh_command else None
    memory_stop = threading.Event()
    memory_samples: list[tuple[int, int]] = []

    def sample_memory() -> None:
        while not memory_stop.wait(0.5):
            total, available = system_memory_bytes()
            if total is not None and available is not None:
                memory_samples.append((total, available))

    memory_thread = threading.Thread(target=sample_memory, daemon=True)
    memory_thread.start()

    def query(request: dict[str, Any]) -> dict[str, Any]:
        # Each measurement gets a new memory-only cache and cannot use a
        # default snapshot, so every result is a genuine filtered DuckDB read.
        adapter = Phase3RequestAdapter(
            DuckDBServingStore(manager, generation_id=generation.generation_id),
            Phase3ResponseCache(),
            allow_default_snapshots=False,
        )
        started = time.perf_counter()
        progress = refresh_progress(progress_file)
        overlap = {
            "refresh_running": refresh_process is not None and refresh_process.poll() is None,
            "refresh_progress": int(progress.get("progress_percent") or 0),
            "refresh_phase": progress.get("phase"),
        }
        try:
            response = adapter.execute(request)
            return {
                **overlap,
                "page": request["stats_page"],
                "view": request.get("combinations_view") or request.get("players_view"),
                "duration_seconds": round(time.perf_counter() - started, 3),
                "cache_status": response.get("cache_status"),
                "row_count": response.get("row_count"),
                "status": response.get("status"),
            }
        except Exception as exc:
            return {
                **overlap,
                "page": request["stats_page"],
                "duration_seconds": round(time.perf_counter() - started, 3),
                "cache_status": None,
                "row_count": None,
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            }

    before = shutil.disk_usage(root)
    results = []
    def batch() -> None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(query, request) for request in FILTERED_REQUESTS]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print(json.dumps({"measurement": result}), flush=True)
    refresh_result: dict[str, Any]
    try:
        batch()
        if refresh_process:
            deadline = time.monotonic() + 3 * 60 * 60
            last_sample = time.monotonic()
            last_phase = refresh_progress(progress_file).get("progress_percent")
            while refresh_process.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("concurrent refresh exceeded its three-hour window")
                phase = refresh_progress(progress_file).get("progress_percent")
                if (phase != last_phase and isinstance(phase, (int, float)) and 48 <= phase < 96
                        or time.monotonic() - last_sample >= query_interval_seconds):
                    batch()
                    last_sample = time.monotonic()
                    last_phase = phase
                time.sleep(5)
            code = refresh_process.returncode
            refresh_result = {"status": "ok" if code == 0 else "failed", "returncode": code}
        else:
            refresh_result = {"status": "not_run", "reason": "no --refresh-command supplied"}
    finally:
        stop_refresh_process(refresh_process)
        memory_stop.set()
        memory_thread.join(timeout=2)
    after = shutil.disk_usage(root)
    memory = rss_bytes()
    total_memory = max((sample[0] for sample in memory_samples), default=None)
    minimum_available = min((sample[1] for sample in memory_samples), default=None)
    query_pass = all(
        item["status"] == "ok"
        and item["cache_status"] == "private_miss"
        and item["duration_seconds"] <= latency_limit
        for item in results
    )
    overlap_pass = mixed_refresh_pass(results, refresh_result)
    result = {
        "status": "ok" if query_pass and overlap_pass else "incomplete",
        "generation": generation.generation_id,
        "data_version": generation.data_version,
        "requirements": {
            "uncached_non_default_reads": query_pass,
            "mixed_read_refresh_concurrency": overlap_pass,
        },
        "queries": sorted(results, key=lambda item: item["page"]),
        "refresh": refresh_result,
        "serving_limits": {
            "threads": os.environ.get("DUCKDB_SERVING_THREADS", "2"),
            "memory_limit": os.environ.get("DUCKDB_SERVING_MEMORY_LIMIT", "1300MB"),
        },
        "memory": {
            "gate_peak_process_rss_bytes": memory,
            "system_total_bytes": total_memory,
            "system_minimum_available_bytes": minimum_available,
            "system_maximum_used_bytes": (
                total_memory - minimum_available
                if total_memory is not None and minimum_available is not None else None
            ),
            "sample_count": len(memory_samples),
        },
        "disk": {
            "before_free_bytes": before.free,
            "after_free_bytes": after.free,
            "consumed_bytes": before.free - after.free,
        },
        "source_bytes": (generation.manifest.get("source_materialization") or {}).get("bytes"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--latency-limit", type=float, default=5.0)
    parser.add_argument("--progress-file", type=Path,
                        help="Atomic progress file written by the real refresh command")
    parser.add_argument("--query-interval-seconds", type=float, default=300)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--generation-id",
        help="Pin every gate query to this immutable candidate generation.",
    )
    parser.add_argument("--refresh-command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    result = run(
        args.root.resolve(), args.refresh_command, args.latency_limit,
        args.generation_id, args.progress_file, args.query_interval_seconds,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True)
    print(encoded)
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
