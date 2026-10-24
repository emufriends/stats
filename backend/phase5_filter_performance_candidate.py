"""Patch one immutable generation with interactive Cards/Players facts.

This is a data-local release operation: it copies the active DuckDB file,
derives optimized relations without contacting BigQuery, writes a new manifest,
and leaves activation/publication to the normal release gate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from phase2_local_vertical_slice import (
    create_card_filter_fact_relation,
    create_players_metrics_relation,
)
from phase3_duckdb_service import _load_duckdb


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/ascri"))
    parser.add_argument("--generation", required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    generations = root / "phase2_private_data" / "generations"
    pointer = json.loads(
        (root / "phase3_private_serving" / "current.json").read_text(encoding="utf-8")
    )
    parent = str(pointer["generation"])
    source_db = generations / f"{parent}.duckdb"
    source_manifest = generations / f"{parent}.manifest.json"
    target_db = generations / f"{args.generation}.duckdb"
    target_manifest = generations / f"{args.generation}.manifest.json"
    if target_db.exists() or target_manifest.exists():
        raise FileExistsError(args.generation)

    started = time.perf_counter()
    shutil.copyfile(source_db, target_db)
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(target_db))
    try:
        connection.execute("SET threads=2")
        connection.execute("SET memory_limit='2800MB'")
        connection.execute("SET preserve_insertion_order=false")
        spill = root / "phase2_private_data" / "staging" / f"{args.generation}.spill"
        spill.mkdir(parents=True, exist_ok=True)
        connection.execute("SET temp_directory=?", [str(spill)])
        players_rows = create_players_metrics_relation(connection, rebuild_base=False)
        card_rows = create_card_filter_fact_relation(connection)
        connection.execute("CHECKPOINT")
        cohort_rows = connection.execute(
            "SELECT COUNT(*) FROM players_default_cohorts_narrow"
        ).fetchone()[0]
    except Exception:
        connection.close()
        target_db.unlink(missing_ok=True)
        raise
    else:
        connection.close()

    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    relations = dict((manifest.get("builder") or {}).get("relations") or {})
    # Counts are read from the builder result in aggregate below; the manifest
    # stores both physical partitions so serving can capability-check safely.
    connection = duckdb.connect(str(target_db), read_only=True)
    try:
        card_mw_rows = int(connection.execute(
            "SELECT COUNT(*) FROM card_filter_fact_mw_narrow"
        ).fetchone()[0])
        card_base_rows = int(connection.execute(
            "SELECT COUNT(*) FROM card_filter_fact_base_narrow"
        ).fetchone()[0])
        card_table_mw_rows = int(connection.execute(
            "SELECT COUNT(*) FROM card_filter_table_fact_mw_narrow"
        ).fetchone()[0])
        card_table_base_rows = int(connection.execute(
            "SELECT COUNT(*) FROM card_filter_table_fact_base_narrow"
        ).fetchone()[0])
    finally:
        connection.close()
    relations.update({
        "players_by_identity_narrow": {"rows": int(players_rows)},
        "players_default_cohorts_narrow": {"rows": int(cohort_rows)},
        "card_filter_fact_mw_narrow": {"rows": card_mw_rows},
        "card_filter_fact_base_narrow": {"rows": card_base_rows},
        "card_filter_table_fact_mw_narrow": {"rows": card_table_mw_rows},
        "card_filter_table_fact_base_narrow": {"rows": card_table_base_rows},
    })
    builder = dict(manifest.get("builder") or {})
    builder["relations"] = relations
    manifest.update({
        "generation": args.generation,
        "database": str(target_db),
        "parent_generation": parent,
        "staged_at": utc_now(),
        "status": "ok",
        "builder": builder,
        "filter_performance_optimization": {
            "schema": 1,
            "built_at": utc_now(),
            "cards_rows": int(card_rows),
            "players_rows": int(players_rows),
            "default_cohort_rows": int(cohort_rows),
        },
    })
    target_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "candidate_ready",
        "generation": args.generation,
        "parent_generation": parent,
        "database_bytes": target_db.stat().st_size,
        "card_filter_rows": int(card_rows),
        "players_rows": int(players_rows),
        "default_cohort_rows": int(cohort_rows),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
