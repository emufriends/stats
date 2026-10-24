"""Promote a validated same-filesystem DuckDB candidate as a new generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase5_uncoordinated_guard import require_uncoordinated_ack

from phase3_duckdb_service import GenerationManager, _utc_now


def main() -> int:
    require_uncoordinated_ack(Path(__file__).name)
    parser = argparse.ArgumentParser()
    parser.add_argument("generation")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root.resolve()
    manager = GenerationManager(
        root / "phase2_private_data" / "generations",
        root / "phase3_private_serving" / "current.json",
    )
    current = manager.current()
    if current is None:
        raise RuntimeError("no active generation")
    manifest = dict(current.manifest)
    manifest.update({
        "generation": args.generation,
        "database": str(args.candidate.resolve()),
        "parent_generation": current.generation_id,
        "staged_at": _utc_now(),
        "status": "ok",
        "serving_optimization": {
            "completed_tables_narrow": True,
            "players_metrics_narrow": True,
            "players_cohort_aggregation": "split",
        },
    })
    manifest_path = args.candidate.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    candidate = manager.adopt_existing(args.generation, args.candidate, manifest_path)
    activated = manager.activate(candidate.generation_id)
    print(json.dumps({
        "status": "ok",
        "generation": activated.generation_id,
        "data_version": activated.data_version,
        "previous_generation": current.generation_id,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
