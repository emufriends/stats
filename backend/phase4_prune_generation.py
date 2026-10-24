"""Build and atomically activate a pruned private DuckDB generation.

The active generation is immutable.  This utility copies its local relations
into a staging database and removes corrupted tables from the compact
non-Home card-play relation before activation.  It never calls BigQuery and
never mutates the source generation.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb, _utc_now


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def rebuild(generation_id: str) -> dict:
    root = Path(__file__).resolve().parent
    generation_dir = root / "phase2_private_data" / "generations"
    staging_dir = root / "phase2_private_data" / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    manager = GenerationManager(
        generation_dir,
        root / "phase3_private_serving" / "current.json",
    )
    source = manager.current()
    if generation_id == source.generation_id:
        raise ValueError("candidate generation must differ from the active generation")
    target_db = staging_dir / f"{generation_id}.duckdb"
    target_manifest = staging_dir / f"{generation_id}.manifest.json"
    if target_db.exists() or target_manifest.exists():
        raise FileExistsError(f"staging candidate already exists: {generation_id}")

    duckdb = _load_duckdb()
    started = time.perf_counter()
    source_count = None
    pruned_count = None
    try:
        # Preserve every relation and its physical layout by copying the
        # immutable database file.  Rebuilding all twelve relations with CTAS
        # needlessly materializes the 5.5M-row source table and exceeded the
        # small VM's memory envelope before reaching the target relation.
        shutil.copyfile(source.database_path, target_db)
        writer = duckdb.connect(str(target_db))
        try:
            writer.execute("PRAGMA threads=2")
            source_count = writer.execute("SELECT COUNT(*) FROM card_play_narrow").fetchone()[0]
            writer.execute(
                "CREATE TABLE card_play_narrow_pruned AS "
                "SELECT * FROM card_play_narrow "
                "WHERE table_id NOT IN (SELECT table_id FROM corrupted_tables_narrow)"
            )
            pruned_count = writer.execute("SELECT COUNT(*) FROM card_play_narrow_pruned").fetchone()[0]
            writer.execute("DROP TABLE card_play_narrow")
            writer.execute("ALTER TABLE card_play_narrow_pruned RENAME TO card_play_narrow")
            writer.execute("CHECKPOINT")
        finally:
            writer.close()
        manifest = dict(source.manifest)
        manifest.update({
            "generation": generation_id,
            "data_version": source.data_version,
            "database": str(generation_dir / f"{generation_id}.duckdb"),
            "parent_generation": source.generation_id,
            "staged_at": _utc_now(),
            "status": "ok",
            "physical_pruning": {
                "relation": "card_play_narrow",
                "excluded_corrupted_rows": source_count - pruned_count,
            },
        })
        target_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        pass

    candidate = manager.stage(generation_id, target_db, target_manifest)
    manager.activate(generation_id)
    target_db.unlink(missing_ok=True)
    target_manifest.unlink(missing_ok=True)
    return {
        "generation": candidate.generation_id,
        "data_version": candidate.data_version,
        "parent_generation": source.generation_id,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "row_counts": {"card_play_narrow": pruned_count},
        "card_play_narrow_before": source_count,
        "card_play_narrow_after": pruned_count,
        "active": manager.current().generation_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generation", help="new path-safe generation ID")
    args = parser.parse_args()
    print(json.dumps(rebuild(args.generation), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
