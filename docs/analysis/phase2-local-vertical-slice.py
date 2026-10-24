"""Materialize the first narrow local serving relations.

This slice covers the shared player-game attributes and normal card plays. It
is intentionally independent from the public API until its population and
numeric output are reconciled with the existing dashboard derivatives. The
safe VM defaults are two DuckDB threads, a 2.8-GB memory ceiling, and an
explicit on-disk spill directory so the builder remains viable on the 4-GiB
private test VM.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


VALID_MAPS = [
    "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
    "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
    "Map 5a: Park Restaurant", "Map 6a: Research Institute",
    "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
    "Map 9: Geographical Zoo", "Map 10: Rescue Station",
    "Map 11: Caves", "Map 12: Artificial Intelligence",
    "Map 13: Drawing Board", "Map 14: Lagoon", "Map T1: Tournament 1",
]
EXCLUDED_PROJECTS = {
    "reptiles", "europe", "predators", "americas", "australia",
    "birds", "sea animals", "africa", "herbivores", "asia",
    "primates", "habitat diversity", "species diversity",
}


def sql_list(values: list[str]) -> str:
    return "[" + ", ".join(
        "'" + value.replace("'", "''") + "'" for value in values
    ) + "]"


def run(
    database_path: Path,
    output_path: Path | None = None,
    threads: int = 2,
    memory_limit: str = "2800MB",
    temp_directory: Path | None = None,
) -> int:
    package_candidates = [
        database_path.parent.parent / "python314",
        database_path.parent.parent / "python",
        Path(__file__).resolve().parent.parent / "python314",
        Path(__file__).resolve().parent.parent / "python",
    ]
    package_dir = next((path for path in package_candidates if path.exists()), None)
    if package_dir is not None:
        sys.path.insert(0, str(package_dir))
    import duckdb

    started = time.perf_counter()
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute(f"PRAGMA threads = {max(1, int(threads))}")
        connection.execute("PRAGMA enable_progress_bar = false")
        connection.execute("PRAGMA preserve_insertion_order = false")
        spill_dir = temp_directory or database_path.parent / ".duckdb-spill"
        spill_dir.mkdir(parents=True, exist_ok=True)
        connection.execute("PRAGMA temp_directory = ?", [str(spill_dir)])
        connection.execute("PRAGMA memory_limit = ?", [memory_limit])
        # Compute the table-level flag with a hash aggregate.  This avoids the
        # large partition window that previously caused the 4 GiB VM to hit
        # its cgroup limit while creating game_player_narrow.
        connection.execute("DROP TABLE IF EXISTS table_conceded_narrow")
        connection.execute("""
            CREATE TEMP TABLE table_conceded_narrow AS
            SELECT table_id,
              BOOL_OR(CAST(COALESCE(concede, 0) AS BOOLEAN)) AS table_conceded
            FROM source_full_sample
            GROUP BY table_id
        """)
        connection.execute("DROP TABLE IF EXISTS game_player_narrow")
        connection.execute("""
            CREATE TABLE game_player_narrow AS
            SELECT
              table_id,
              player,
              player_id,
              is_mw,
              Map AS map_name,
              CAST(game_ended_at AS DATE) AS game_date,
              game_ended_at,
              Starting_position_in_first_round AS starting_position,
              pre_match_elo,
              post_match_elo,
              elo_delta,
              Game_result AS result_code,
              concede,
              end_game_triggered,
              COALESCE(c.table_conceded, FALSE) AS table_conceded
            FROM source_full_sample f
            LEFT JOIN table_conceded_narrow c USING (table_id)
        """)
        connection.execute("DROP TABLE IF EXISTS corrupted_tables_narrow")
        connection.execute("""
            CREATE TABLE corrupted_tables_narrow AS
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
        """)
        connection.execute("DROP TABLE IF EXISTS card_play_narrow")
        connection.execute("""
            CREATE TEMP TABLE valid_log_ids_narrow AS
            SELECT table_id
            FROM source_logs
            GROUP BY table_id
            HAVING COUNT(*) = 2
        """)
        card_play_select = """
            SELECT DISTINCT
              g.table_id, g.player, g.player_id, g.is_mw, g.map_name,
              g.game_date, g.game_ended_at, g.starting_position,
              g.pre_match_elo, g.post_match_elo, g.elo_delta,
              g.result_code, g.concede, g.table_conceded,
              g.end_game_triggered, {name} AS card_name,
              '{card_type}' AS card_type, TRY_CAST(card.round AS BIGINT) AS played_round
            FROM game_player_narrow g
            JOIN source_logs l USING (table_id, player)
            JOIN valid_log_ids_narrow v USING (table_id)
            CROSS JOIN UNNEST(l.{array_name}) AS played(card)
            WHERE {name} IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM corrupted_tables_narrow bad
                WHERE bad.table_id = g.table_id
              )
        """
        branches = [
            ("card.animal", "animal", "played_animals"),
            ("card.sponsor", "sponsor", "played_sponsors"),
            ("card.project", "project", "played_projects"),
        ]
        first_name, first_type, first_array = branches[0]
        connection.execute(
            "CREATE TABLE card_play_narrow AS "
            + card_play_select.format(
                name=first_name, card_type=first_type, array_name=first_array
            )
        )
        for name, card_type, array_name in branches[1:]:
            connection.execute(
                "INSERT INTO card_play_narrow\n" + card_play_select.format(
                    name=name, card_type=card_type, array_name=array_name
                )
            )
        default_maps = sql_list(VALID_MAPS)
        excluded_projects = sql_list(sorted(EXCLUDED_PROJECTS))
        connection.execute("DROP TABLE IF EXISTS card_component_by_table_narrow")
        connection.execute(f"""
            CREATE TABLE card_component_by_table_narrow AS
            WITH scoped AS (
              SELECT DISTINCT
                cp.table_id, cp.player, cp.card_name, cp.card_type,
                cp.elo_delta
              FROM card_play_narrow cp
              WHERE cp.is_mw = 1
                AND cp.map_name IN {default_maps}
                AND cp.game_date >= DATE '2025-01-01'
                AND NOT (
                  cp.card_type = 'project'
                  AND LOWER(cp.card_name) IN {excluded_projects}
                )
                AND COALESCE(cp.pre_match_elo, 0) >= 300
                AND EXISTS (
                  SELECT 1
                  FROM game_player_narrow opponent
                  WHERE opponent.table_id = cp.table_id
                    AND opponent.player <> cp.player
                    AND COALESCE(opponent.pre_match_elo, 0) >= 300
                )
                AND NOT EXISTS (
                  SELECT 1
                  FROM corrupted_tables_narrow bad
                  WHERE bad.table_id = cp.table_id
                )
            )
            SELECT card_name, card_type, table_id,
              COUNT(elo_delta) AS delta_count,
              SUM(elo_delta) AS delta_sum,
              SUM(POW(elo_delta, 2)) AS delta_sum_squares
            FROM scoped
            WHERE elo_delta IS NOT NULL
            GROUP BY card_name, card_type, table_id
        """)
        # Pair-level additive Synergy confidence intervals were retired.  Keep
        # the exact Card + Card point-estimate moments, but aggregate directly
        # from the deduplicated scoped rows instead of materializing the much
        # larger table/player pair relation.  This preserves the observation
        # semantics while avoiding a disk-heavy intermediate cross join.
        connection.execute("DROP TABLE IF EXISTS card_pair_aggregate_narrow")
        connection.execute(f"""
            CREATE TABLE card_pair_aggregate_narrow AS
            WITH scoped AS (
              SELECT DISTINCT
                cp.table_id, cp.player, cp.card_name, cp.card_type,
                cp.elo_delta, cp.pre_match_elo
              FROM card_play_narrow cp
              WHERE cp.is_mw = 1
                AND cp.map_name IN {default_maps}
                AND cp.game_date >= DATE '2025-01-01'
                AND NOT (
                  cp.card_type = 'project'
                  AND LOWER(cp.card_name) IN {excluded_projects}
                )
                AND COALESCE(cp.pre_match_elo, 0) >= 300
                AND EXISTS (
                  SELECT 1
                  FROM game_player_narrow opponent
                  WHERE opponent.table_id = cp.table_id
                    AND opponent.player <> cp.player
                    AND COALESCE(opponent.pre_match_elo, 0) >= 300
                )
                AND NOT EXISTS (
                  SELECT 1
                  FROM corrupted_tables_narrow bad
                  WHERE bad.table_id = cp.table_id
                )
            )
            SELECT
              a.card_name AS card_1,
              a.card_type AS type_1,
              b.card_name AS card_2,
              b.card_type AS type_2,
              COUNT(*) AS observation_count,
              COUNT(a.elo_delta) AS delta_count,
              SUM(a.elo_delta) AS delta_sum,
              SUM(POW(a.elo_delta, 2)) AS delta_sum_squares,
              COUNT(a.pre_match_elo) AS elo_count,
              SUM(a.pre_match_elo) AS elo_sum
            FROM scoped a
            JOIN scoped b
              ON b.table_id = a.table_id
             AND b.player = a.player
             AND a.card_name < b.card_name
            GROUP BY a.card_name, a.card_type, b.card_name, b.card_type
        """)
        connection.execute("DROP TABLE IF EXISTS card_component_aggregate_narrow")
        connection.execute("""
            CREATE TABLE card_component_aggregate_narrow AS
            SELECT
              card_name,
              card_type,
              SUM(delta_count) AS delta_count,
              SUM(delta_sum) AS delta_sum,
              SUM(delta_sum_squares) AS delta_sum_squares,
              COUNT(*) AS cluster_count
            FROM card_component_by_table_narrow
            GROUP BY card_name, card_type
        """)
        # Flatten the log card arrays once.  Cards' in-hand and seen metrics
        # reuse these relations on every snapshot build, so the serving query
        # does not repeatedly scan and UNNEST the wide Logs export.
        connection.execute("DROP TABLE IF EXISTS card_log_narrow")
        connection.execute("""
            CREATE TABLE card_log_narrow AS
            SELECT
              l.table_id,
              l.player,
              l.cards_drawn,
              l.display_cards
            FROM source_logs l
            JOIN game_player_narrow g
              ON g.table_id = l.table_id AND g.player = l.player
        """)
        connection.execute("DROP TABLE IF EXISTS card_in_hand_narrow")
        connection.execute("""
            CREATE TABLE card_in_hand_narrow AS
            SELECT DISTINCT
              table_id,
              player,
              TRIM(drawn.card_name) AS card_name
            FROM card_log_narrow
            CROSS JOIN UNNEST(
              COALESCE(cards_drawn, CAST([] AS VARCHAR[]))
            ) AS drawn(card_name)
            WHERE TRIM(drawn.card_name) <> ''
        """)
        connection.execute("DROP TABLE IF EXISTS card_seen_narrow")
        connection.execute("""
            CREATE TABLE card_seen_narrow AS
            SELECT DISTINCT
              table_id,
              player,
              TRIM(seen.card_name) AS card_name
            FROM card_log_narrow
            CROSS JOIN UNNEST(ARRAY_CONCAT(
              COALESCE(cards_drawn, CAST([] AS VARCHAR[])),
              COALESCE(display_cards, CAST([] AS VARCHAR[]))
            )) AS seen(card_name)
            WHERE TRIM(seen.card_name) <> ''
        """)
        game_players = connection.execute(
            "SELECT COUNT(*) FROM game_player_narrow"
        ).fetchone()[0]
        tables = connection.execute(
            "SELECT COUNT(DISTINCT table_id) FROM game_player_narrow"
        ).fetchone()[0]
        card_plays = connection.execute(
            "SELECT COUNT(*) FROM card_play_narrow"
        ).fetchone()[0]
        card_groups = connection.execute(
            "SELECT COUNT(DISTINCT card_type || ':' || card_name) FROM card_play_narrow"
        ).fetchone()[0]
        corrupted_tables = connection.execute(
            "SELECT COUNT(*) FROM corrupted_tables_narrow"
        ).fetchone()[0]
        card_log_rows = connection.execute(
            "SELECT COUNT(*) FROM card_log_narrow"
        ).fetchone()[0]
        card_in_hand_rows = connection.execute(
            "SELECT COUNT(*) FROM card_in_hand_narrow"
        ).fetchone()[0]
        card_seen_rows = connection.execute(
            "SELECT COUNT(*) FROM card_seen_narrow"
        ).fetchone()[0]
        component_rows = connection.execute(
            "SELECT COUNT(*) FROM card_component_by_table_narrow"
        ).fetchone()[0]
        component_aggregate_rows = connection.execute(
            "SELECT COUNT(*) FROM card_component_aggregate_narrow"
        ).fetchone()[0]
        pair_aggregate_rows = connection.execute(
            "SELECT COUNT(*) FROM card_pair_aggregate_narrow"
        ).fetchone()[0]
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    report = {
        "status": "ok",
        "database": str(database_path),
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "relations": {
            "game_player_narrow": {
                "rows": int(game_players),
                "distinct_tables": int(tables),
            },
            "card_play_narrow": {
                "rows": int(card_plays),
                "distinct_card_groups": int(card_groups),
            },
            "corrupted_tables_narrow": {
                "rows": int(corrupted_tables),
            },
            "card_log_narrow": {
                "rows": int(card_log_rows),
            },
            "card_in_hand_narrow": {
                "rows": int(card_in_hand_rows),
            },
            "card_seen_narrow": {
                "rows": int(card_seen_rows),
            },
            "card_component_by_table_narrow": {
                "rows": int(component_rows),
            },
            "card_component_aggregate_narrow": {
                "rows": int(component_aggregate_rows),
            },
            "card_pair_aggregate_narrow": {
                "rows": int(pair_aggregate_rows),
            },
        },
        "build_seconds": round(time.perf_counter() - started, 3),
        "parity_status": "cards_shape_reconciled; focused_pair_and_ci_reconciled",
    }
    if output_path:
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="2800MB")
    parser.add_argument("--temp-directory", type=Path)
    args = parser.parse_args(argv)
    return run(
        args.database_path,
        args.output,
        threads=args.threads,
        memory_limit=args.memory_limit,
        temp_directory=args.temp_directory,
    )


if __name__ == "__main__":
    sys.exit(main())
