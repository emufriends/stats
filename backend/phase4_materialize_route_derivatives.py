"""Materialize small external-source relations for the private Phase 4 port.

Arena rosters and record spreadsheets are moving inputs, not BigQuery facts.
They are imported once while a generation is built so route requests remain
read-only and deterministic.  This utility never calls BigQuery and never
mutates the active database in place.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb, _utc_now


def _read_arena(root: Path) -> list[tuple[str, int, str, int, float, str]]:
    by_key: dict[tuple[str, int], tuple[str, int, str, int, float, str]] = {}
    # Refresh-owned moving sources store arena_settings.csv and s*.csv in one
    # committed directory. Repository tools may still pass the project root.
    arena_dir = root / "arena" if (root / "arena").is_dir() else root
    for path in sorted(arena_dir.glob("s*.csv")):
        season = path.stem.upper()
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                player = (raw.get("BGA Name") or "").strip()
                if not player:
                    continue
                try:
                    rank = int((raw.get("#") or "").strip())
                    player_id = int((raw.get("ID") or "").strip())
                    ending = float((raw.get("Rating") or "").strip())
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid Arena row in {path.name}: {raw}") from exc
                key = (season, player_id)
                current = (rank, player, player_id, ending, path.name)
                # A manually maintained season sheet can briefly contain the
                # same ID twice (for example after a username correction).
                # IDs are the authoritative identity, so the later row is the
                # deterministic winner and the roster remains one row/player.
                by_key[key] = (season, *current)
    return list(by_key.values())


def _create_relations(connection, root: Path) -> dict[str, int]:
    arena_rows = _read_arena(root)
    connection.execute("DROP TABLE IF EXISTS arena_roster_narrow")
    connection.execute(
        "CREATE TABLE arena_roster_narrow("
        "season VARCHAR NOT NULL, rank BIGINT NOT NULL, player VARCHAR NOT NULL, "
        "player_id BIGINT NOT NULL, ending_rating DOUBLE NOT NULL, source_file VARCHAR NOT NULL, "
        "PRIMARY KEY(season, player_id))"
    )
    if arena_rows:
        # One parameterized bulk INSERT avoids one autocommit/fsync per roster
        # row. Elite League rosters contain far more than 100 players. JSON
        # arrays preserve all six typed fields without a pandas/Arrow dependency;
        # the table's constraints still validate the imported population.
        connection.execute("""
            INSERT INTO arena_roster_narrow
            SELECT CAST(value ->> '$[0]' AS VARCHAR),
              CAST(value ->> '$[1]' AS BIGINT), CAST(value ->> '$[2]' AS VARCHAR),
              CAST(value ->> '$[3]' AS BIGINT), CAST(value ->> '$[4]' AS DOUBLE),
              CAST(value ->> '$[5]' AS VARCHAR)
            FROM json_each(CAST(? AS JSON))
        """, [json.dumps(arena_rows, ensure_ascii=False, allow_nan=False)])

    return {"arena_roster_narrow": len(arena_rows)}


def rebuild(generation_id: str) -> dict:
    root = Path(__file__).resolve().parent
    generations = root / "phase2_private_data" / "generations"
    staging = root / "phase2_private_data" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    manager = GenerationManager(generations, root / "phase3_private_serving" / "current.json")
    source = manager.current()
    if source is None:
        raise RuntimeError("no active generation")
    if generation_id == source.generation_id:
        raise ValueError("candidate generation must differ from the active generation")
    target_db = staging / f"{generation_id}.duckdb"
    target_manifest = staging / f"{generation_id}.manifest.json"
    if target_db.exists() or target_manifest.exists():
        raise FileExistsError(f"staging candidate already exists: {generation_id}")

    shutil.copyfile(source.database_path, target_db)
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(target_db))
    try:
        counts = _create_relations(connection, root)
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
        "route_derivatives": counts,
    })
    target_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        candidate = manager.stage(generation_id, target_db, target_manifest)
        manager.activate(generation_id)
    except Exception:
        target_db.unlink(missing_ok=True)
        target_manifest.unlink(missing_ok=True)
        raise
    return {"generation": candidate.generation_id, "data_version": candidate.data_version,
            "parent_generation": source.generation_id, "counts": counts,
            "active": manager.current().generation_id}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generation")
    args = parser.parse_args()
    print(json.dumps(rebuild(args.generation), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
