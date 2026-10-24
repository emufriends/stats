"""Build the completed-game derivative and time Players/General on a DB copy."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb

from phase2_local_vertical_slice import create_players_metrics_relation
from phase4_local_routes import _players_metric_sql


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--build-completed", action="store_true")
    parser.add_argument("--parity", action="store_true")
    args = parser.parse_args()
    connection = duckdb.connect(str(args.database))
    connection.execute("SET threads=2")
    connection.execute("SET preserve_insertion_order=false")
    if args.build_completed:
        started = time.perf_counter()
        connection.execute("DROP TABLE IF EXISTS completed_tables_narrow")
        connection.execute("""
            CREATE TABLE completed_tables_narrow AS
            SELECT table_id
            FROM source_full_sample
            GROUP BY table_id
            HAVING COUNT(*) = 2
              AND SUM(CASE WHEN COALESCE(concede, 0) <> 0 THEN 1 ELSE 0 END) = 0
              AND SUM(CASE WHEN COALESCE(end_game_triggered, FALSE) IS NOT TRUE THEN 1 ELSE 0 END) = 0
        """)
        connection.execute("CHECKPOINT")
        count = connection.execute("SELECT COUNT(*) FROM completed_tables_narrow").fetchone()[0]
        players_rows = create_players_metrics_relation(connection)
        connection.execute("CHECKPOINT")
        print({
            "completed_tables": count,
            "players_metric_rows": players_rows,
            "build_seconds": round(time.perf_counter() - started, 3),
        })
    request = {
        "is_mw": 1,
        "maps": [
            "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
            "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
            "Map 5a: Park Restaurant", "Map 6a: Research Institute",
            "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
            "Map 9: Geographical Zoo", "Map 10: Rescue Station",
            "Map 11: Caves", "Map 12: Artificial Intelligence",
            "Map 13: Drawing Board", "Map 14: Lagoon", "Map T1: Tournament 1",
        ],
        "opponent_elo_min": 0,
    }
    sql, parameters = _players_metric_sql(request, "general")
    started = time.perf_counter()
    rows = connection.execute(sql, [*parameters, 1000, 0]).fetchall()
    print({"rows": len(rows), "query_seconds": round(time.perf_counter() - started, 3)})
    if args.parity:
        standard_maps = request["maps"]
        placeholders = ", ".join("?" for _ in standard_maps)
        cohort = """
          COUNT(*) AS n,
          AVG(Number_of_turns) AS turns,
          AVG(Score) AS score,
          AVG(Reputation_association_tasks) AS reputation_actions,
          AVG(Science_icons) AS science_icons
        """
        prepared = connection.execute(
            f"SELECT {cohort} FROM players_metrics_narrow "
            f"WHERE is_mw = 1 AND Map IN ({placeholders}) AND opponent_elo >= 0",
            standard_maps,
        ).fetchone()
        source = connection.execute(
            f"SELECT {cohort} FROM source_full_sample f "
            "JOIN completed_tables_narrow completed USING(table_id) "
            "LEFT JOIN corrupted_tables_narrow corrupted USING(table_id) "
            f"WHERE corrupted.table_id IS NULL AND f.is_mw = 1 "
            f"AND f.Map IN ({placeholders}) AND f.opponent_elo >= 0",
            standard_maps,
        ).fetchone()
        print({"parity": prepared == source, "prepared": prepared, "source": source})
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
