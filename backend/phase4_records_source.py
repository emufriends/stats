"""Import the moving Records spreadsheets into a private DuckDB generation.

The spreadsheets are deliberately treated as external inputs.  This module
validates their small, explicit contracts, stores a generation-local copy, and
never changes the active database in place.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb, _utc_now


def _int(value: str, field: str, row: int) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError as exc:
        raise ValueError(f"row {row}: invalid {field}: {value!r}") from exc


def _float(value: str, field: str, row: int, *, nullable: bool = False) -> float | None:
    token = str(value or "").strip()
    if nullable and token.casefold() in {"", "n/a", "na"}:
        return None
    try:
        return float(token)
    except ValueError as exc:
        raise ValueError(f"row {row}: invalid {field}: {value!r}") from exc


def read_fastest(path: Path) -> list[tuple]:
    rows: list[tuple] = []
    seen: set[tuple[int, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Turns", "Player", "Score", "ID", "EPT"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"{path.name} is missing {sorted(required - set(reader.fieldnames or []))}")
        for row_number, raw in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in raw.values()):
                continue
            table_id = _int(raw.get("ID", ""), "ID", row_number)
            player = str(raw.get("Player") or "").strip()
            if not player:
                raise ValueError(f"row {row_number}: blank Player")
            key = (table_id, player.casefold())
            if key in seen:
                raise ValueError(f"{path.name}: duplicate ID/Player at row {row_number}")
            seen.add(key)
            turns = _int(raw.get("Turns", ""), "Turns", row_number)
            if not 1 <= turns <= 23:
                raise ValueError(f"row {row_number}: Turns must be between 1 and 23")
            rows.append(("fastest_games", row_number, table_id, player, None,
                         float(turns), float(_int(raw.get("Score", ""), "Score", row_number)),
                         _int(raw.get("EPT", ""), "EPT", row_number),
                         None, None, None, None, None, None, None, None))
    if not rows:
        raise ValueError(f"{path.name} contains no data rows")
    return rows


def read_biggest(path: Path) -> list[tuple]:
    rows: list[tuple] = []
    seen: set[tuple[str, int, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Flat", "End", "Total", "Player", "Score", "Turns", "Map", "Move",
                     "# Actions", "ID", "Result", "Date", "Mode"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"{path.name} is missing {sorted(required - set(reader.fieldnames or []))}")
        for row_number, raw in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in raw.values()):
                continue
            mode = str(raw.get("Mode") or "").strip()
            if mode not in {"MW", "Base"}:
                raise ValueError(f"row {row_number}: invalid Mode {mode!r}")
            table_id = _int(raw.get("ID", ""), "ID", row_number)
            player = str(raw.get("Player") or "").strip()
            result = str(raw.get("Result") or "").strip().upper()
            if result not in {"W", "D", "L"} or not player:
                raise ValueError(f"row {row_number}: invalid Result or Player")
            key = (mode, table_id, player.casefold())
            if key in seen:
                raise ValueError(f"{path.name}: duplicate Mode/ID/Player at row {row_number}")
            seen.add(key)
            flat = _int(raw.get("Flat", ""), "Flat", row_number)
            end = _int(raw.get("End", ""), "End", row_number)
            total = _int(raw.get("Total", ""), "Total", row_number)
            if flat + end != total:
                raise ValueError(f"row {row_number}: Flat + End does not equal Total")
            rows.append(("biggest_turns", row_number, table_id, player, mode,
                         float(_int(raw.get("Turns", ""), "Turns", row_number)),
                         float(_int(raw.get("Score", ""), "Score", row_number)), 0,
                         flat, end, total, _int(raw.get("Move", ""), "Move", row_number),
                         _int(raw.get("# Actions", ""), "# Actions", row_number),
                         str(raw.get("Map") or "").strip(), result,
                         str(raw.get("Date") or "").strip()))
    if not rows:
        raise ValueError(f"{path.name} contains no data rows")
    return rows


def read_elo(path: Path) -> list[tuple]:
    rows: list[tuple] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header or len(header) < 8:
            raise ValueError(f"{path.name} has no valid header")
        normalized = [str(value or "").strip().casefold() for value in header]
        if normalized[1] not in {"nationality", "country"} or normalized[2] not in {"bga name", "player"}:
            raise ValueError(f"{path.name} has an unexpected leaderboard header")
        for row_number, raw in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in raw):
                continue
            if len(raw) < 8:
                raise ValueError(f"row {row_number}: fewer than eight columns")
            country = str(raw[1] or "").strip().lower()
            player = str(raw[2] or "").strip()
            if len(country) != 2 or not country.isalpha() or not player:
                raise ValueError(f"row {row_number}: invalid country or player")
            rows.append((row_number, country, player,
                         _float(raw[5], "Peak Elo", row_number),
                         _float(raw[7], "Peak Arena", row_number, nullable=True)))
    if len(rows) < 100:
        raise ValueError(f"{path.name} contains only {len(rows)} valid players")
    rows.sort(key=lambda item: (-item[3], item[0], item[2].casefold()))
    return [(row[0], row[1], row[2], row[3], row[4], rank)
            for rank, row in enumerate(rows[:100], start=1)]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rebuild(generation_id: str, source_dir: Path) -> dict:
    root = Path(__file__).resolve().parent
    generations = root / "phase2_private_data" / "generations"
    staging = root / "phase2_private_data" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    manager = GenerationManager(generations, root / "phase3_private_serving" / "current.json")
    source = manager.current()
    if source is None or generation_id == source.generation_id:
        raise ValueError("candidate generation must differ from the active generation")
    fastest_path = source_dir / "records-fastest.csv"
    biggest_path = source_dir / "records-biggest.csv"
    elo_path = source_dir / "records-elo.csv"
    fastest = read_fastest(fastest_path)
    biggest = read_biggest(biggest_path)
    elo = read_elo(elo_path)
    target_db = staging / f"{generation_id}.duckdb"
    target_manifest = staging / f"{generation_id}.manifest.json"
    if target_db.exists() or target_manifest.exists():
        raise FileExistsError(f"staging candidate already exists: {generation_id}")
    shutil.copyfile(source.database_path, target_db)
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(target_db))
    try:
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
        "route_derivatives": {
            "records_manual_narrow": len(fastest) + len(biggest),
            "records_elo_leaderboard_narrow": len(elo),
        },
        "moving_sources": {
            "records_fastest_sha256": _sha(fastest_path),
            "records_biggest_sha256": _sha(biggest_path),
            "records_elo_sha256": _sha(elo_path),
        },
    })
    target_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    candidate = manager.stage(generation_id, target_db, target_manifest)
    manager.activate(generation_id)
    return {"generation": candidate.generation_id, "data_version": candidate.data_version,
            "parent_generation": source.generation_id,
            "counts": manifest["route_derivatives"], "active": manager.current().generation_id}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generation")
    parser.add_argument("--source-dir", type=Path,
                        default=Path(__file__).resolve().parent / "phase2_private_data" / "moving_sources")
    args = parser.parse_args()
    print(json.dumps(rebuild(args.generation, args.source_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
