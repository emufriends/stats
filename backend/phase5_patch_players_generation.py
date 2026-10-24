"""Create an immutable generation with the complete Players serving fact.

This narrowly repairs generations created before the prepared Players fact
retained elo_delta. The source generation remains untouched and is the
automatic rollback target.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from phase2_local_vertical_slice import create_players_metrics_relation
from phase3_duckdb_service import GenerationManager, _load_duckdb, _utc_now


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generation")
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

    staging = root / "phase2_private_data" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    candidate = staging / f"{args.generation}.duckdb"
    manifest_path = candidate.with_suffix(".manifest.json")
    if candidate.exists() or manifest_path.exists():
        raise RuntimeError(f"staging candidate already exists: {candidate}")
    shutil.copy2(current.database_path, candidate)

    duckdb = _load_duckdb()
    connection = duckdb.connect(str(candidate))
    try:
        row_count = create_players_metrics_relation(connection)
        columns = {
            row[0] for row in connection.execute(
                "DESCRIBE players_metrics_narrow"
            ).fetchall()
        }
        if "elo_delta" not in columns:
            raise RuntimeError("players_metrics_narrow still lacks elo_delta")
        source_count = int(connection.execute(
            """
            SELECT COUNT(*)
            FROM source_full_sample f
            JOIN completed_tables_narrow completed USING (table_id)
            LEFT JOIN corrupted_tables_narrow corrupted USING (table_id)
            WHERE corrupted.table_id IS NULL
            """
        ).fetchone()[0])
        if row_count != source_count:
            raise RuntimeError(
                f"Players fact count mismatch: {row_count} != {source_count}"
            )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    manifest = dict(current.manifest)
    manifest.update({
        "generation": args.generation,
        "database": str(candidate),
        "parent_generation": current.generation_id,
        "staged_at": _utc_now(),
        "status": "ok",
        "serving_optimization": {
            **dict(manifest.get("serving_optimization") or {}),
            "completed_tables_narrow": True,
            "players_metrics_narrow": True,
            "players_metrics_elo_delta": True,
            "players_cohort_aggregation": "split",
        },
    })
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    adopted = manager.adopt_existing(args.generation, candidate, manifest_path)
    activated = manager.activate(adopted.generation_id)
    print(json.dumps({
        "status": "ok",
        "generation": activated.generation_id,
        "data_version": activated.data_version,
        "previous_generation": current.generation_id,
        "players_row_count": row_count,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
