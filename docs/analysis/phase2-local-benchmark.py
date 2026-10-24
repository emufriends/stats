"""Run a small read-only local benchmark against a Phase 2 DuckDB file."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def run(database_path: Path, output_path: Path | None = None) -> int:
    private_root = database_path.parent.parent
    package_dir = private_root / "python314"
    if not package_dir.exists():
        package_dir = private_root / "python"
    sys.path.insert(0, str(package_dir))
    import duckdb

    connection = duckdb.connect(str(database_path), read_only=True)
    card_scope = """
        WITH corrupted AS (
          SELECT table_id
          FROM source_full_sample
          GROUP BY table_id
          HAVING BOOL_OR(
            TRY_CAST(Game_result AS BIGINT) = 2
            AND TRY_CAST(Number_of_turns AS DOUBLE) IS NOT NULL
            AND TRY_CAST(Animals_actions AS DOUBLE) IS NOT NULL
            AND TRY_CAST(Association_actions AS DOUBLE) IS NOT NULL
            AND TRY_CAST(Build_actions AS DOUBLE) IS NOT NULL
            AND TRY_CAST(Cards_actions AS DOUBLE) IS NOT NULL
            AND TRY_CAST(Sponsors_actions AS DOUBLE) IS NOT NULL
            AND TRY_CAST(X_Tokens_gained_instead_of_action AS DOUBLE) IS NOT NULL
            AND TRY_CAST(Number_of_turns AS DOUBLE) - (
              TRY_CAST(Animals_actions AS DOUBLE)
              + TRY_CAST(Association_actions AS DOUBLE)
              + TRY_CAST(Build_actions AS DOUBLE)
              + TRY_CAST(Cards_actions AS DOUBLE)
              + TRY_CAST(Sponsors_actions AS DOUBLE)
              + TRY_CAST(X_Tokens_gained_instead_of_action AS DOUBLE)
            ) >= 2
          )
        ), scoped AS (
          SELECT cp.table_id, cp.player, cp.card_name, cp.elo_delta,
            cp.map_name, cp.game_date
          FROM card_play_narrow cp
          JOIN game_player_narrow player_row
            ON player_row.table_id = cp.table_id AND player_row.player = cp.player
          JOIN game_player_narrow opponent_row
            ON opponent_row.table_id = cp.table_id AND opponent_row.player <> cp.player
          LEFT JOIN corrupted bad ON bad.table_id = cp.table_id
          WHERE bad.table_id IS NULL
            AND cp.is_mw = 1
            AND cp.map_name NOT IN ('Map 0', 'Map A',
              'Map 1: Observation Tower', 'Map 2: Outdoor Areas',
              'Map 3: Silver Lake', 'Map 4: Commercial Harbor',
              'Map 5: Park Restaurant', 'Map 6: Research Institute',
              'Map 7: Ice Cream Parlors', 'Map 8: Hollywood Hills')
            AND cp.game_date >= DATE '2025-01-01'
            AND COALESCE(player_row.pre_match_elo, 0) >= 300
            AND COALESCE(opponent_row.pre_match_elo, 0) >= 300
        )
    """
    cases = {
        "full_sample_count": "SELECT COUNT(*) FROM source_full_sample",
        "distinct_tables": "SELECT COUNT(DISTINCT table_id) FROM source_full_sample",
        "logs_count": "SELECT COUNT(*) FROM source_logs",
        "mw_card_play_shape": """
            SELECT COUNT(*)
            FROM source_full_sample f
            JOIN source_logs l USING (table_id, player)
            CROSS JOIN UNNEST(l.played_animals) AS played(card)
            WHERE f.is_mw = 1 AND card.animal IS NOT NULL
        """,
        "mw_card_delta_groups": """
            SELECT card.animal, COUNT(*) AS plays, AVG(f.elo_delta) AS avg_delta
            FROM source_full_sample f
            JOIN source_logs l USING (table_id, player)
            CROSS JOIN UNNEST(l.played_animals) AS played(card)
            WHERE f.is_mw = 1 AND card.animal IS NOT NULL
            GROUP BY card.animal
            ORDER BY plays DESC
        """,
        "players_history_filtered": """
            WITH selected AS (
              SELECT player
              FROM game_player_narrow
              GROUP BY player
              ORDER BY COUNT(*) DESC, player
              LIMIT 1
            )
            SELECT g.player, COUNT(*) AS games, AVG(g.elo_delta) AS avg_delta
            FROM game_player_narrow g
            JOIN selected USING (player)
            WHERE g.is_mw = 1 AND g.game_date >= DATE '2025-01-01'
            GROUP BY g.player
        """,
        "card_pair_actual": f"""
            {card_scope}, pair AS (
              SELECT DISTINCT a.table_id, a.player, a.elo_delta
              FROM scoped a
              JOIN scoped b
                ON b.table_id = a.table_id AND b.player = a.player
              WHERE a.card_name = 'Bamboo Forest'
                AND b.card_name = 'Jungle'
            )
            SELECT COUNT(*) AS observations, COUNT(DISTINCT table_id) AS tables,
              AVG(elo_delta) AS actual_delta
            FROM pair
        """,
        "ordinary_card_ci": f"""
            {card_scope}, rows AS (
              SELECT table_id, elo_delta
              FROM scoped
              WHERE card_name = 'Bamboo Forest' AND elo_delta IS NOT NULL
            ), by_table AS (
              SELECT table_id, COUNT(*) AS n, SUM(elo_delta) AS s
              FROM rows GROUP BY table_id
            ), totals AS (
              SELECT SUM(n) AS n_total, SUM(s) / SUM(n) AS mean, COUNT(*) AS clusters
              FROM by_table
            )
            SELECT mean, clusters,
              SQRT(clusters / (clusters - 1) *
                SUM(POW(s - n * mean, 2)) / POW(n_total, 2)) AS se
            FROM by_table CROSS JOIN totals GROUP BY mean, clusters, n_total
        """,
        "mw_action_card_scope": """
            WITH corrupted AS (
              SELECT table_id
              FROM source_full_sample
              GROUP BY table_id
              HAVING BOOL_OR(
                TRY_CAST(Game_result AS BIGINT) = 2
                AND TRY_CAST(Number_of_turns AS DOUBLE) IS NOT NULL
                AND TRY_CAST(Animals_actions AS DOUBLE) IS NOT NULL
                AND TRY_CAST(Association_actions AS DOUBLE) IS NOT NULL
                AND TRY_CAST(Build_actions AS DOUBLE) IS NOT NULL
                AND TRY_CAST(Cards_actions AS DOUBLE) IS NOT NULL
                AND TRY_CAST(Sponsors_actions AS DOUBLE) IS NOT NULL
                AND TRY_CAST(X_Tokens_gained_instead_of_action AS DOUBLE) IS NOT NULL
                AND TRY_CAST(X_Tokens_gained_instead_of_action AS DOUBLE) IS NOT NULL
                AND TRY_CAST(Number_of_turns AS DOUBLE) - (
                  TRY_CAST(Animals_actions AS DOUBLE) + TRY_CAST(Association_actions AS DOUBLE)
                  + TRY_CAST(Build_actions AS DOUBLE) + TRY_CAST(Cards_actions AS DOUBLE)
                  + TRY_CAST(Sponsors_actions AS DOUBLE) + TRY_CAST(X_Tokens_gained_instead_of_action AS DOUBLE)
                ) >= 2
              )
            ), eligible AS (
              SELECT f.table_id
              FROM source_full_sample f
              LEFT JOIN corrupted bad USING (table_id)
              WHERE f.is_mw = 1 AND bad.table_id IS NULL
              GROUP BY f.table_id
              HAVING COUNT(*) = 2 AND COUNT(DISTINCT f.player) = 2
                AND BOOL_AND(COALESCE(TRY_CAST(f.Animals_Action_Card_Number AS BIGINT) BETWEEN 0 AND 4, FALSE))
                AND BOOL_AND(COALESCE(TRY_CAST(f.Association_Action_Card_Number AS BIGINT) BETWEEN 0 AND 4, FALSE))
                AND BOOL_AND(COALESCE(TRY_CAST(f.Build_Action_Card_Number AS BIGINT) BETWEEN 0 AND 4, FALSE))
                AND BOOL_AND(COALESCE(TRY_CAST(f.Cards_Action_Card_Number AS BIGINT) BETWEEN 0 AND 4, FALSE))
                AND BOOL_AND(COALESCE(TRY_CAST(f.Sponsors_Action_Card_Number AS BIGINT) BETWEEN 0 AND 4, FALSE))
                AND BOOL_AND(regexp_matches(COALESCE(CAST(f.First_drafted_action_card AS VARCHAR), ''), '^(Animals|Association|Build|Cards|Sponsors) [1-4]$'))
                AND BOOL_AND(regexp_matches(COALESCE(CAST(f.Second_drafted_action_card AS VARCHAR), ''), '^(Animals|Association|Build|Cards|Sponsors) [1-4]$'))
                AND BOOL_AND(regexp_matches(COALESCE(CAST(f.Third_drafted_action_card AS VARCHAR), ''), '^(Animals|Association|Build|Cards|Sponsors) [1-4]$'))
            )
            SELECT COUNT(*) AS eligible_tables
            FROM eligible
        """,
    }
    results = {}
    try:
        for name, query in cases.items():
            started = time.perf_counter()
            try:
                rows = connection.execute(query).fetchall()
            except Exception as exc:
                raise RuntimeError(f"benchmark case {name} failed: {exc}") from exc
            results[name] = {
                "seconds": round(time.perf_counter() - started, 3),
                "rows": len(rows),
                "sample": [list(row) for row in rows[:5]],
            }
    finally:
        connection.close()
    concurrent_started = time.perf_counter()

    def concurrent_reader(_):
        reader = duckdb.connect(str(database_path), read_only=True)
        try:
            return reader.execute(
                "SELECT COUNT(*) FROM game_player_narrow WHERE is_mw = 1"
            ).fetchone()[0]
        finally:
            reader.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        concurrent_samples = list(executor.map(concurrent_reader, range(4)))
    results["four_concurrent_readers"] = {
        "seconds": round(time.perf_counter() - concurrent_started, 3),
        "readers": 4,
        "consistent_results": len(set(concurrent_samples)) == 1,
        "sample": concurrent_samples[:1],
    }
    report = {
        "status": "ok",
        "database": str(database_path),
        "results": results,
    }
    if output_path:
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    return run(args.database_path, args.output)


if __name__ == "__main__":
    sys.exit(main())
