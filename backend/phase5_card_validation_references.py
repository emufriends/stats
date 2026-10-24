"""Independent validation-only references in a disposable scratch database.

Preserves the fixed historical default reference population. Never called by
nightly builds or serving; no paired accelerator is used to compute references.
"""
from phase2_local_vertical_slice import VALID_MAPS, EXCLUDED_PROJECTS, sql_list

VALIDATION_RELATIONS = (
    "card_component_by_table_narrow", "card_component_aggregate_narrow",
    "card_pair_aggregate_narrow",
)


def validation_scoped_sql():
    """Canonical distinct player-game/card scope for stable independent SD."""
    default_maps = sql_list(VALID_MAPS)
    excluded_projects = sql_list(sorted(EXCLUDED_PROJECTS))
    return f"""
          SELECT DISTINCT
            cp.table_id, cp.player, cp.is_mw, cp.card_name, cp.card_type,
            cp.elo_delta, cp.pre_match_elo
          FROM card_play_narrow cp
          WHERE cp.map_name IN {default_maps}
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
    """


def create_validation_references(connection):
    default_maps = sql_list(VALID_MAPS)
    excluded_projects = sql_list(sorted(EXCLUDED_PROJECTS))
    connection.execute("DROP TABLE IF EXISTS card_component_by_table_narrow")
    connection.execute(f"""
        CREATE TABLE card_component_by_table_narrow AS
        WITH scoped AS (
          SELECT DISTINCT
            cp.table_id, cp.player, cp.is_mw, cp.card_name, cp.card_type,
            cp.elo_delta
          FROM card_play_narrow cp
          WHERE cp.map_name IN {default_maps}
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
        SELECT is_mw, card_name, card_type, table_id,
          COUNT(elo_delta) AS delta_count,
          SUM(elo_delta) AS delta_sum,
          SUM(POW(elo_delta, 2)) AS delta_sum_squares
        FROM scoped
        WHERE elo_delta IS NOT NULL
        GROUP BY is_mw, card_name, card_type, table_id
    """)
    # Synergy is a point estimate and has no pair-level confidence interval.
    # Preserve independent Card + Card diagnostic moments and aggregate directly
    # from the deduplicated scoped rows instead of materializing the much
    # larger wide table/player pair relation. The separate compact filter
    # accelerator retains only numeric keys and independent round masks.
    # This preserves the observation
    # semantics while avoiding a disk-heavy intermediate cross join.
    connection.execute("DROP TABLE IF EXISTS card_pair_aggregate_narrow")
    connection.execute(f"""
        CREATE TABLE card_pair_aggregate_narrow AS
        WITH scoped AS (
          SELECT DISTINCT
            cp.table_id, cp.player, cp.is_mw, cp.card_name, cp.card_type,
            cp.elo_delta, cp.pre_match_elo
          FROM card_play_narrow cp
          WHERE cp.map_name IN {default_maps}
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
          a.is_mw,
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
         AND b.is_mw = a.is_mw
         AND a.card_name < b.card_name
        GROUP BY a.is_mw, a.card_name, a.card_type, b.card_name, b.card_type
    """)
    connection.execute("DROP TABLE IF EXISTS card_component_aggregate_narrow")
    connection.execute("""
        CREATE TABLE card_component_aggregate_narrow AS
        SELECT
          is_mw,
          card_name,
          card_type,
          SUM(delta_count) AS delta_count,
          SUM(delta_sum) AS delta_sum,
          SUM(delta_sum_squares) AS delta_sum_squares,
          COUNT(*) AS cluster_count
        FROM card_component_by_table_narrow
        GROUP BY is_mw, card_name, card_type
    """)
    return {name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in VALIDATION_RELATIONS}
