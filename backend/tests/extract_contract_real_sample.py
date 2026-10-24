"""Print a deterministic real-data sample from an imported DuckDB generation.

This is a review/reconciliation helper. It is read-only and deliberately does
not import any migrated route builder. The committed real-data fixture records
the output plus its source generation so it can be inspected without a database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _rows(connection, sql: str, parameters=()):
    result = connection.execute(sql, parameters)
    columns = [item[0] for item in result.description]
    return [
        {key: _json_value(value) for key, value in zip(columns, row)}
        for row in result.fetchall()
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--generation", required=True)
    args = parser.parse_args()
    configured = os.environ.get("DUCKDB_PYTHON_PATH")
    candidates = [Path(configured)] if configured else []
    candidates.extend((args.database.parents[1] / "python314", args.database.parents[1] / "python"))
    for candidate in candidates:
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    import duckdb

    connection = duckdb.connect(str(args.database), read_only=True)
    try:
        ids = [row[0] for row in connection.execute("""
          SELECT l.table_id
          FROM source_logs l
          JOIN source_full_sample f USING(table_id, player)
          WHERE f.is_mw = 1
            AND f.Map = 'Map 1a: Observation Tower'
            AND f.table_id IN (
              SELECT table_id FROM source_full_sample
              GROUP BY table_id
              HAVING COUNT(*) = 2
                 AND SUM(CASE WHEN COALESCE(concede, 0) <> 0 THEN 1 ELSE 0 END) = 0
                 AND SUM(CASE WHEN end_game_triggered IS TRUE THEN 1 ELSE 0 END) = 2
            )
            AND f.table_id NOT IN (SELECT table_id FROM corrupted_tables_narrow)
            AND array_length(l.opening_cards) > 0
            AND (
              array_length(l.played_animals) > 0
              OR array_length(l.played_sponsors) > 0
              OR array_length(l.played_projects) > 0
            )
          GROUP BY l.table_id
          HAVING COUNT(*) = 2
          ORDER BY l.table_id
          LIMIT 2
        """).fetchall()]
        parameters = [*ids]
        placeholders = ", ".join("?" for _ in ids)
        games = _rows(connection, f"""
          SELECT table_id, player, is_mw, Map AS map, pre_match_elo,
            opponent_elo AS raw_opponent_elo, elo_delta,
            Starting_position_in_first_round AS starting_position,
            Game_result AS game_result, end_game_triggered, concede, game_ended_at
          FROM source_full_sample
          WHERE table_id IN ({placeholders})
          ORDER BY table_id, player
        """, parameters)
        logs = _rows(connection, f"""
          SELECT table_id, player, to_json(opening_cards) AS opening_cards,
            to_json(opening_keep) AS opening_keep,
            to_json(played_animals) AS played_animals,
            to_json(played_sponsors) AS played_sponsors,
            to_json(played_projects) AS played_projects,
            to_json(endgame_scores) AS endgame_scores
          FROM source_logs
          WHERE table_id IN ({placeholders})
          ORDER BY table_id, player
        """, parameters)
    finally:
        connection.close()
    print(json.dumps({
        "fixture_version": "2026-09-22.1",
        "source_generation": args.generation,
        "selection": "first two eligible completed MW Map 1a tables with two log rows",
        "table_ids": ids,
        "games": games,
        "logs": logs,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
