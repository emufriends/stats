"""Build one private DuckDB candidate with all moving-source relations.

Arena rosters, Arena season windows, tournament membership, and Records
spreadsheets are external inputs.  They are validated and materialized in the
same candidate copy as the analytical generation so activation remains atomic
and no route reads a live spreadsheet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb, _utc_now
from phase4_metadata import fetch_tournament_metadata, load_arena_settings, materialize_metadata_tables
from phase4_materialize_route_derivatives import _create_relations as create_arena_relations
from phase4_records_source import read_biggest, read_elo, read_fastest, _sha


def _materialize_records(connection, source_dir: Path) -> dict[str, int]:
    fastest = read_fastest(source_dir / "records-fastest.csv")
    biggest = read_biggest(source_dir / "records-biggest.csv")
    elo = read_elo(source_dir / "records-elo.csv")

    connection.execute("DROP TABLE IF EXISTS records_manual_narrow")
    connection.execute("""CREATE TABLE records_manual_narrow(
      record_view VARCHAR NOT NULL, source_row BIGINT NOT NULL,
      table_id BIGINT NOT NULL, player VARCHAR NOT NULL, mode VARCHAR,
      turns DOUBLE, score DOUBLE, ept BIGINT, flat BIGINT, "end" BIGINT,
      total BIGINT, move BIGINT, actions BIGINT, map_code VARCHAR,
      result_code VARCHAR, game_date VARCHAR
    )""")
    connection.executemany(
        "INSERT INTO records_manual_narrow VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fastest + biggest,
    )
    connection.execute("DROP TABLE IF EXISTS records_elo_leaderboard_narrow")
    connection.execute("""CREATE TABLE records_elo_leaderboard_narrow(
      source_row BIGINT NOT NULL, country VARCHAR NOT NULL, player VARCHAR NOT NULL,
      peak_elo DOUBLE NOT NULL, peak_arena DOUBLE, rank BIGINT NOT NULL
    )""")
    connection.executemany(
        "INSERT INTO records_elo_leaderboard_narrow VALUES (?, ?, ?, ?, ?, ?)", elo
    )
    return {
        "records_manual_narrow": len(fastest) + len(biggest),
        "records_elo_leaderboard_narrow": len(elo),
    }


def build(
    generation_id: str,
    *,
    root: Path,
    arena_settings: Path,
    source_dir: Path,
) -> dict:
    generations = root / "phase2_private_data" / "generations"
    staging = root / "phase2_private_data" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    pointer = root / "phase3_private_serving" / "current.json"
    manager = GenerationManager(generations, pointer)
    source = manager.current()
    if source is None:
        raise RuntimeError("no active generation")
    if generation_id == source.generation_id:
        raise ValueError("candidate generation must differ from active generation")

    target_db = staging / f"{generation_id}.duckdb"
    target_manifest = staging / f"{generation_id}.manifest.json"
    if target_db.exists() or target_manifest.exists():
        raise FileExistsError(f"staging candidate already exists: {generation_id}")

    tournament_rows, tournament_info = fetch_tournament_metadata()
    arena_rows, arena_info = load_arena_settings(root / arena_settings)
    shutil.copyfile(source.database_path, target_db)
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(target_db))
    try:
        materialize_metadata_tables(connection, tournament_rows, arena_rows)
        arena_counts = create_arena_relations(connection, root)
        record_counts = _materialize_records(connection, source_dir)
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    manifest = dict(source.manifest)
    manifest.update({
        "generation": generation_id,
        "database": str(generations / f"{generation_id}.duckdb"),
        "parent_generation": source.generation_id,
        "staged_at": _utc_now(),
        "status": "ok",
        "metadata_sources": {
            "tournament_sheet": tournament_info,
            "arena_settings": arena_info,
        },
        "route_derivatives": {**arena_counts, **record_counts},
        "moving_sources": {
            "records_fastest_sha256": _sha(source_dir / "records-fastest.csv"),
            "records_biggest_sha256": _sha(source_dir / "records-biggest.csv"),
            "records_elo_sha256": _sha(source_dir / "records-elo.csv"),
        },
    })
    target_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        candidate = manager.adopt_existing(generation_id, target_db, target_manifest)
        manager.activate(generation_id)
    except Exception:
        target_db.unlink(missing_ok=True)
        target_manifest.unlink(missing_ok=True)
        raise
    return {
        "generation": candidate.generation_id,
        "data_version": candidate.data_version,
        "parent_generation": source.generation_id,
        "counts": manifest["route_derivatives"],
        "active": manager.current().generation_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--arena-settings", type=Path, default=Path("arena/arena_settings.csv"))
    parser.add_argument(
        "--source-dir", type=Path,
        default=Path("phase2_private_data/moving_sources"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    settings = args.arena_settings if args.arena_settings.is_absolute() else root / args.arena_settings
    source_dir = args.source_dir if args.source_dir.is_absolute() else root / args.source_dir
    print(json.dumps(build(args.generation, root=root, arena_settings=settings, source_dir=source_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
