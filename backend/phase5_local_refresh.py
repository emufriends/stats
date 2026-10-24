"""Build and atomically activate one private DuckDB serving generation.

This is the Phase 5 private refresh boundary.  It never mutates the active
database: the active file is copied to a same-filesystem staging path, the
bounded builder works on that copy, and the completed file is renamed into the
generation store before the existing GenerationManager activates it.  A
builder or validation failure leaves the active pointer unchanged.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase3_duckdb_service import GenerationManager, ServingStateError


EXPECTED_RELATIONS = {
    "game_player_narrow",
    "card_play_narrow",
    "corrupted_tables_narrow",
    "card_log_narrow",
    "card_in_hand_narrow",
    "card_seen_narrow",
    "mw_action_card_catalog_narrow",
    "mw_action_card_draft_narrow",
    "mw_action_card_pair_narrow",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_builder(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("phase5_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load builder module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _acquire_lock(path: Path, stale_after: float = 6 * 3600) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            if time.time() - path.stat().st_mtime > stale_after:
                path.unlink()
                return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileNotFoundError:
            return _acquire_lock(path, stale_after)
        raise RuntimeError(f"a local refresh is already running: {path}")


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def refresh(
    *,
    root: Path,
    builder_path: Path,
    generation_id: str,
    threads: int = 2,
    memory_limit: str = "2800MB",
    temp_directory: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    private = root / "phase2_private_data"
    generations = private / "generations"
    pointer = root / "phase3_private_serving" / "current.json"
    manager = GenerationManager(generations, pointer)
    active = manager.current()
    if active is None:
        raise ServingStateError("cannot refresh without an active generation")
    builder = _load_builder(builder_path)
    if not hasattr(builder, "run"):
        raise RuntimeError("builder module must expose run(database_path, ...)")

    target_db = generations / f"{generation_id}.duckdb"
    target_manifest = generations / f"{generation_id}.manifest.json"
    if target_db.exists() or target_manifest.exists():
        raise RuntimeError(f"generation already exists: {generation_id}")
    staging = private / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    staging_db = staging / f"{generation_id}.duckdb.staging"
    staging_report = staging / f"{generation_id}.builder.json"
    lock_path = private / "refresh.lock"
    lock_fd = _acquire_lock(lock_path)
    try:
        source_db = active.database_path
        shutil.copyfile(source_db, staging_db)
        with staging_db.open("rb") as handle:
            os.fsync(handle.fileno())
        report: dict[str, Any] = {}
        result = builder.run(
            staging_db,
            staging_report,
            threads=threads,
            memory_limit=memory_limit,
            temp_directory=temp_directory or staging / f"{generation_id}.spill",
        )
        if result != 0:
            raise RuntimeError(f"builder returned status {result}")
        report = json.loads(staging_report.read_text(encoding="utf-8"))
        if report.get("status") != "ok":
            raise RuntimeError("builder report is not successful")
        relation_names = set(report.get("relations", {}))
        missing = sorted(EXPECTED_RELATIONS - relation_names)
        if missing:
            raise RuntimeError(f"builder report is missing relations: {missing}")

        manifest = dict(active.manifest)
        manifest.update({
            "generation": generation_id,
            "parent_generation": active.generation_id,
            "staged_at": _utc_now(),
            "status": "ok",
            "builder": {
                "path": builder_path.name,
                "threads": threads,
                "memory_limit": memory_limit,
                "report": report,
            },
        })
        staging_manifest = staging / f"{generation_id}.manifest.json.staging"
        staging_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(staging_db, target_db)
        os.replace(staging_manifest, target_manifest)
        activated = manager.activate(generation_id)
        output = {
            "status": "ok",
            "generation": activated.generation_id,
            "data_version": activated.data_version,
            "previous_generation": active.generation_id,
            "builder_report": report,
        }
        if report_path:
            _write_report(report_path, output)
        return output
    except Exception as exc:
        staging_db.unlink(missing_ok=True)
        (staging / f"{generation_id}.manifest.json.staging").unlink(missing_ok=True)
        failure = {"status": "error", "generation": generation_id, "error": type(exc).__name__}
        if report_path:
            _write_report(report_path, failure)
        raise
    finally:
        try:
            os.close(lock_fd)
        finally:
            lock_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation")
    parser.add_argument("--builder", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="2800MB")
    parser.add_argument("--temp-directory", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    result = refresh(
        root=args.root,
        builder_path=args.builder,
        generation_id=args.generation,
        threads=args.threads,
        memory_limit=args.memory_limit,
        temp_directory=args.temp_directory,
        report_path=args.report,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
