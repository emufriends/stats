"""Run one bounded default-scope request against every private native route."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from phase3_duckdb_service import (
    GenerationManager,
    PHASE4_NATIVE_ROUTES,
    DuckDBServingStore, Phase3RequestAdapter, Phase3ResponseCache,
)


VIEW_FIELDS = {
    "endgames": "endgames_view",
    "maps": "maps_view",
    "sponsor_endgames": "sponsor_endgames_view",
    "combinations": "combinations_view",
    "build": "build_view",
    "predictors": "predictors_view",
    "actions": "actions_view",
    "conservation": "conservation_view",
    "scoring": "scoring_view",
    "workers": "workers_view",
    "players": "players_view",
    "arena": "arena_view",
    "records": "records_view",
    "mw_action_cards": "mw_action_cards_view",
}


def request_for(page: str, view: str) -> dict:
    request = {"stats_page": page, "limit": 2, "offset": 0}
    if page not in {"home", "arena"}:
        request["is_mw"] = 1
    field = VIEW_FIELDS.get(page)
    if field:
        request[field] = view
    if page == "combinations":
        request["combination_min_plays"] = 1000
    return request


def run_one(page: str, view: str, root: Path, generation: str | None) -> int:
    manager_dir = root / "phase2_private_data" / "generations"
    pointer = root / "phase3_private_serving" / "current.json"
    adapter = Phase3RequestAdapter(
        DuckDBServingStore(GenerationManager(manager_dir, pointer), generation_id=generation),
        Phase3ResponseCache(), allow_default_snapshots=False,
    )
    started = time.perf_counter()
    response = adapter.execute(request_for(page, view))
    print(json.dumps({
        "page": page,
        "view": view,
        "status": response.get("status"),
        "row_count": response.get("row_count"),
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--one", nargs=2, metavar=("PAGE", "VIEW"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--generation-id", help="Pin uncached checks to an inactive candidate")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.one:
        return run_one(*args.one, args.root.resolve(), args.generation_id)

    root = args.root.resolve()
    pointer = root / "phase3_private_serving" / "current.json"
    generation = args.generation_id or json.loads(pointer.read_text(encoding="utf-8")).get("generation")
    def run_child(page: str, view: str) -> dict:
        started = time.perf_counter()
        command = [sys.executable, str(Path(__file__).resolve()), "--one", page, view,
                   "--root", str(root), "--generation-id", generation]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=args.timeout,
            )
            line = next(
                (candidate for candidate in reversed(completed.stdout.splitlines())
                 if candidate.strip().startswith("{")),
                None,
            )
            result = json.loads(line) if line else {
                "status": "error",
                "error_type": "missing_child_result",
                "error": completed.stderr[-1000:],
            }
            result.update({
                "page": page,
                "view": view,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            })
            if completed.returncode != 0 and result.get("status") == "ok":
                result["status"] = "error"
        except subprocess.TimeoutExpired:
            result = {
                "page": page,
                "view": view,
                "status": "timeout",
                "error_type": "route_timeout",
                "error": f"exceeded {args.timeout:.1f}s",
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        return result
    routes = sorted(PHASE4_NATIVE_ROUTES)
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(run_child, page, view) for page, view in routes]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: (item.get("page", ""), item.get("view", "")))
    output = {
        "status": "ok" if all(item["status"] == "ok" for item in results) else "failed",
        "generation": generation,
        "route_count": len(results),
        "timeout_seconds": args.timeout,
        "results": results,
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    if args.report:
        args.report.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if output["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
