"""Validate, stage, and activate a source-backed private DuckDB candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase5_uncoordinated_guard import require_uncoordinated_ack

from phase3_duckdb_service import GenerationManager, _utc_now


def promote(database: Path, source_report: Path, generation_id: str) -> dict:
    root = Path(__file__).resolve().parent
    generations = root / "phase2_private_data" / "generations"
    pointer = root / "phase3_private_serving" / "current.json"
    manager = GenerationManager(generations, pointer)
    current = manager.current()
    if current is None:
        raise RuntimeError("no active generation available for rollback")
    report = json.loads(source_report.read_text(encoding="utf-8"))
    if report.get("status") != "ok":
        raise RuntimeError("source-backed builder report is not successful")
    manifest = dict(current.manifest)
    manifest.update(
        {
            "generation": generation_id,
            "data_version": f"phase5-source-{report.get('generation')}",
            "source_generation": report.get("generation"),
            "parent_generation": current.generation_id,
            "database": str(generations / f"{generation_id}.duckdb"),
            "staged_at": _utc_now(),
            "status": "ok",
            "source_materialization": report,
        }
    )
    manifest_path = database.with_suffix(".candidate.manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        candidate = manager.stage_and_activate(generation_id, database, manifest_path)
    finally:
        manifest_path.unlink(missing_ok=True)
    return {
        "status": "ok",
        "generation": candidate.generation_id,
        "data_version": candidate.data_version,
        "previous_generation": current.generation_id,
        "rollback_ready": manager.readiness().get("rollback_ready"),
    }


def main() -> int:
    require_uncoordinated_ack(Path(__file__).name)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("source_report", type=Path)
    parser.add_argument("generation")
    args = parser.parse_args()
    print(json.dumps(promote(args.database, args.source_report, args.generation), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
