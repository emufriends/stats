"""Materialize immutable dashboard facts and page-specific serving relations.

The refresh workflow invokes this builder against committed local source files,
then independently reconciles its output before coordinated publication. The
production worker supplies two threads and an 800-MB engine memory limit; the
CLI's standalone defaults are not the production resource contract. On-disk
spill and bounded batches keep the build separate from the read-only API.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from phase3_cards_pair_contracts import create_cards_pair_relations, create_combo_card_pair_relations
from phase5_refresh_metrics import TimedConnection
from phase5_refresh_dependencies import log_dependency_signature, reuse_log_relations, LOG_RELATIONS


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

# Inactive candidates can be rebuilt over an older derivative inventory. Remove
# obsolete event/validation copies here only; active/rollback generations are immutable.
# Serving uses the filter-ready sponsor/reward facts and canonical action data.
RETIRED_EVENT_RELATIONS = (
    'sponsor_endgame_event_narrow', 'project_reward_event_narrow',
    'action_history_event_narrow',
)
VALIDATION_ONLY_RELATIONS = (
    'card_component_by_table_narrow', 'card_component_aggregate_narrow',
    'card_pair_aggregate_narrow',
)

# The public Marine Worlds action-card catalogue is a fixed 5 x 4 grid. Keep
# it beside the prepared-data builder so every route joins the same identifiers.
MW_ACTION_CARDS = (
    (1, "Animals", 1, "Ignore"), (2, "Animals", 2, "Hunter"),
    (3, "Animals", 3, "Appeal"), (4, "Animals", 4, "Mark"),
    (5, "Association", 1, "Duplicate"), (6, "Association", 2, "Hire"),
    (7, "Association", 3, "X-token"), (8, "Association", 4, "Determination"),
    (9, "Build", 1, "Pavilion"), (10, "Build", 2, "Kiosk"),
    (11, "Build", 3, "+1"), (12, "Build", 4, "Terrain"),
    (13, "Cards", 1, "Keep"), (14, "Cards", 2, "Digging"),
    (15, "Cards", 3, "Snap"), (16, "Cards", 4, "Clever"),
    (17, "Sponsors", 1, "Trade"), (18, "Sponsors", 2, "Money"),
    (19, "Sponsors", 3, "Sunbathing"), (20, "Sponsors", 4, "Marketing"),
)

PLAYER_METRIC_COLUMNS = (
    "table_id", "player", "is_mw", "Map", "game_ended_at",
    "Starting_position_in_first_round", "opponent_elo", "opponent_pre_match_elo",
    "starting_position", "player_identity", "arena_season", "is_tournament",
    "arena_rating_delta",
    "elo_delta", "Game_result", "pre_match_elo", "post_match_elo",
    "Number_of_turns", "Number_of_breaks_triggered", "total_breaks",
    "points_per_turn", "points_per_money", "Money_gained", "Score", "Appeal",
    "Conservation", "Reputation", "Conservation_project_association_tasks",
    "Upgraded_action_cards", "Association_workers", "Empty_hexes",
    "Upgraded_Animals_action_card", "Upgraded_Association_action_card",
    "Upgraded_Build_action_card", "Upgraded_Cards_action_card",
    "Upgraded_Sponsors_action_card", "determinations", "Animals_actions",
    "Association_actions", "Build_actions", "Cards_actions", "Sponsors_actions",
    "University_association_tasks", "Partner_zoo_association_tasks",
    "Reputation_association_tasks", "X_Tokens_gained", "X_Tokens_used",
    "X_Tokens_gained_instead_of_action", "Money_gained_through_income",
    "Money_spent_on_animals", "Money_spent_on_enclosures",
    "Money_spent_on_donations", "Money_spent_for_playing_cards_from_reputation_range",
    "Cards_drawn_from_deck", "Cards_taken_from_reputation_range", "Snapped_cards",
    "Discarded_cards", "Built_enclosures", "Built_kiosks", "Built_pavilions",
    "Built_unique_buildings", "Played_animals", "Released_animals",
    "Played_sponsors", "Bird_icons", "Herbivore_icons", "Predator_icons",
    "Primate_icons", "Reptile_icons", "Sea_Animal_icons", "Bear_icons",
    "Petting_Zoo_icons", "Africa_icons", "Americas_icons", "Asia_icons",
    "Australia_icons", "Europe_icons", "Rock_icons", "Water_icons", "Science_icons",
)

PREDICTOR_GENERAL_FIELDS = (
    "Conservation", "Appeal", "Reputation",
    "Conservation_project_association_tasks", "Released_animals", "Money_gained",
    "Money_gained_through_income", "Money_spent_on_animals",
    "Money_spent_on_enclosures", "Money_spent_on_donations",
    "Money_spent_for_playing_cards_from_reputation_range",
    "Number_of_breaks_triggered", "Played_sponsors", "Played_animals",
    "Cards_drawn_from_deck", "Snapped_cards", "Discarded_cards",
    "Animals_actions", "Association_actions", "Build_actions", "Cards_actions",
    "Sponsors_actions", "determinations", "X_Tokens_gained_instead_of_action",
    "X_Tokens_gained", "X_Tokens_used", "Empty_hexes", "Built_pavilions",
    "Built_kiosks", "Built_unique_buildings",
)

ICON_FIELDS = (
    "Bird_icons", "Herbivore_icons", "Predator_icons", "Primate_icons",
    "Reptile_icons", "Sea_Animal_icons", "Bear_icons", "Petting_Zoo_icons",
    "Africa_icons", "Americas_icons", "Asia_icons", "Australia_icons",
    "Europe_icons", "Rock_icons", "Water_icons", "Science_icons",
)


def sql_list(values: list[str]) -> str:
    return "[" + ", ".join(
        "'" + value.replace("'", "''") + "'" for value in values
    ) + "]"


def _relation_exists(connection, name: str) -> bool:
    return bool(connection.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [name],
    ).fetchone()[0])


def _drop_relation(connection, name: str) -> None:
    """Drop only our main object, never an attached immutable reference."""
    row = connection.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = ? "
        "AND table_catalog = current_database() AND table_schema = 'main'",
        [name],
    ).fetchone()
    if row is None:
        return
    object_type = "VIEW" if str(row[0]).upper() == "VIEW" else "TABLE"
    connection.execute(f"DROP {object_type} main.{name}")


def _merge_player_rows(path: Path | None) -> list[tuple[str, str, str]]:
    """Return validated case-insensitive alias-to-identity rows.

    The identity algorithm implements the dashboard's merged-player contract.
    An absent mapping is safe: every player still receives its exact fallback
    identity.  A malformed present file fails the refresh instead of silently
    changing merged-player populations.
    """

    if path is None or not path.exists():
        return []
    groups: list[tuple[str, str, str]] = []
    aliases_seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row_number, raw_row in enumerate(csv.reader(source), 1):
            members = [str(value or "").strip() for value in raw_row]
            members = [value for value in members if value]
            if not members:
                continue
            if len(members) < 2:
                raise ValueError(
                    f"merge_players.csv row {row_number} must contain at least two names"
                )
            normalized = [value.casefold() for value in members]
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"merge_players.csv row {row_number} has duplicate aliases")
            overlap = aliases_seen.intersection(normalized)
            if overlap:
                raise ValueError(
                    f"merge_players.csv alias {sorted(overlap)[0]!r} occurs more than once"
                )
            aliases_seen.update(normalized)
            group_key = tuple(sorted(normalized))
            identity = "merge:" + hashlib.sha256(
                "\0".join(group_key).encode("utf-8")
            ).hexdigest()[:20]
            groups.extend((member, folded, identity) for member, folded in zip(members, normalized))
    return groups


def create_canonical_player_relations(
    connection,
    merge_players_path: Path | None = None,
) -> dict:
    """Build the canonical player-game boundary without mutating raw imports."""

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
    connection.execute("DROP TABLE IF EXISTS completed_tables_narrow")
    connection.execute("""
        CREATE TABLE completed_tables_narrow AS
        SELECT table_id
        FROM source_full_sample
        GROUP BY table_id
        HAVING COUNT(*) = 2
          AND COUNT(DISTINCT player) = 2
          AND SUM(CASE WHEN COALESCE(TRY_CAST(concede AS INTEGER), 0) <> 0 THEN 1 ELSE 0 END) = 0
          AND SUM(CASE WHEN COALESCE(TRY_CAST(end_game_triggered AS BOOLEAN), FALSE) IS NOT TRUE
                       THEN 1 ELSE 0 END) = 0
    """)
    connection.execute("DROP TABLE IF EXISTS player_identity_metadata")
    connection.execute("""
        CREATE TABLE player_identity_metadata(
          player VARCHAR NOT NULL,
          player_casefold VARCHAR PRIMARY KEY,
          player_identity VARCHAR NOT NULL
        )
    """)
    merge_rows = _merge_player_rows(merge_players_path)
    if merge_rows:
        connection.executemany(
            "INSERT INTO player_identity_metadata VALUES (?, ?, ?)", merge_rows
        )

    connection.execute("DROP TABLE IF EXISTS table_conceded_narrow")
    connection.execute("""
        CREATE TEMP TABLE table_conceded_narrow AS
        SELECT table_id,
          BOOL_OR(COALESCE(TRY_CAST(concede AS INTEGER), 0) <> 0) AS table_conceded
        FROM source_full_sample
        GROUP BY table_id
    """)
    connection.execute("DROP TABLE IF EXISTS player_ratings_narrow")
    connection.execute("""
        CREATE TEMP TABLE player_ratings_narrow AS
        SELECT table_id, CAST(player AS VARCHAR) AS player,
          CASE WHEN COUNT(DISTINCT TRY_CAST(pre_match_elo AS DOUBLE)) = 1
            THEN ANY_VALUE(TRY_CAST(pre_match_elo AS DOUBLE)) ELSE NULL END AS pre_match_elo
        FROM source_full_sample
        GROUP BY table_id, CAST(player AS VARCHAR)
    """)
    connection.execute("DROP TABLE IF EXISTS opponent_ratings_narrow")
    connection.execute("""
        CREATE TEMP TABLE opponent_ratings_narrow AS
        SELECT me.table_id, me.player,
          CASE WHEN COUNT(DISTINCT opponent.player) = 1
            THEN ANY_VALUE(opponent.pre_match_elo) ELSE NULL END AS opponent_pre_match_elo
        FROM player_ratings_narrow me
        LEFT JOIN player_ratings_narrow opponent
          ON opponent.table_id = me.table_id AND opponent.player <> me.player
        GROUP BY me.table_id, me.player
    """)

    has_arena = _relation_exists(connection, "arena_seasons_metadata")
    has_tournament = _relation_exists(connection, "tournament_tables_metadata")
    arena_season_sql = """(
        SELECT a.season FROM arena_seasons_metadata a
        WHERE TRY_CAST(f.game_ended_at AS TIMESTAMPTZ) >= a.start_utc
          AND TRY_CAST(f.game_ended_at AS TIMESTAMPTZ) < a.end_utc
          AND a.mode = CASE WHEN TRY_CAST(f.is_mw AS INTEGER) = 1 THEN 'mw' ELSE 'base' END
          AND f.arena_rating_delta IS NOT NULL
        ORDER BY a.start_utc DESC LIMIT 1
      )""" if has_arena else "CAST(NULL AS VARCHAR)"
    tournament_sql = (
        "EXISTS (SELECT 1 FROM tournament_tables_metadata t WHERE t.table_id = f.table_id)"
        if has_tournament else "FALSE"
    )
    _drop_relation(connection, "prepared_full_sample_narrow")
    connection.execute("DROP TABLE IF EXISTS game_player_narrow")
    connection.execute(f"""
        CREATE TABLE game_player_narrow AS
        SELECT
          f.table_id,
          CAST(f.player AS VARCHAR) AS player,
          f.player_id,
          TRY_CAST(f.is_mw AS INTEGER) AS is_mw,
          f.Map AS map_name,
          CAST(f.game_ended_at AS DATE) AS game_date,
          f.game_ended_at,
          CASE LOWER(TRIM(CAST(f.Starting_position_in_first_round AS VARCHAR)))
            WHEN 'first player' THEN 'First player'
            WHEN 'second player' THEN 'Second player'
            ELSE NULL
          END AS starting_position,
          TRY_CAST(f.pre_match_elo AS DOUBLE) AS pre_match_elo,
          TRY_CAST(f.post_match_elo AS DOUBLE) AS post_match_elo,
          opponent.opponent_pre_match_elo,
          TRY_CAST(f.elo_delta AS DOUBLE) AS elo_delta,
          TRY_CAST(f.Game_result AS BIGINT) AS result_code,
          TRY_CAST(f.concede AS BIGINT) AS concede,
          COALESCE(TRY_CAST(f.end_game_triggered AS BOOLEAN), FALSE) AS end_game_triggered,
          COALESCE(conceded.table_conceded, FALSE) AS table_conceded,
          corrupted.table_id IS NOT NULL AS is_corrupted_game,
          completed.table_id IS NOT NULL AS is_completed_game,
          {arena_season_sql} AS arena_season,
          f.arena_rating_delta IS NOT NULL AND ({arena_season_sql}) IS NOT NULL AS is_arena_game,
          {tournament_sql} AS is_tournament,
          COALESCE(identity.player_identity, 'player:' || CAST(f.player AS VARCHAR)) AS player_identity
        FROM source_full_sample f
        LEFT JOIN opponent_ratings_narrow opponent
          ON opponent.table_id = f.table_id AND opponent.player = CAST(f.player AS VARCHAR)
        LEFT JOIN table_conceded_narrow conceded ON conceded.table_id = f.table_id
        LEFT JOIN corrupted_tables_narrow corrupted ON corrupted.table_id = f.table_id
        LEFT JOIN completed_tables_narrow completed ON completed.table_id = f.table_id
        LEFT JOIN player_identity_metadata identity
          ON identity.player_casefold = LOWER(TRIM(CAST(f.player AS VARCHAR)))
    """)
    # These TEMP lookups have no consumer after the canonical player-game
    # relation is built. Release them before wide enrichment and page facts.
    for name in (
        "opponent_ratings_narrow", "player_ratings_narrow", "table_conceded_narrow"
    ):
        connection.execute(f"DROP TABLE {name}")
    return create_prepared_full_sample_relation(connection)


def create_prepared_full_sample_relation(connection):
    """Physical copy/update boundary, preserving source rows and typed fields.

    Disjoint updates retain the matching semantics for duplicate and missing
    player-game keys without multiplying or dropping source observations.
    """
    canonical_columns = (
        ('pre_match_elo', 'DOUBLE'), ('post_match_elo', 'DOUBLE'),
        ('opponent_elo', 'DOUBLE'), ('opponent_pre_match_elo', 'DOUBLE'),
        ('Starting_position_in_first_round', 'VARCHAR'), ('starting_position', 'VARCHAR'),
        ('end_game_triggered', 'BOOLEAN'), ('table_conceded', 'BOOLEAN'),
        ('is_corrupted_game', 'BOOLEAN'), ('is_completed_game', 'BOOLEAN'),
        ('arena_season', 'VARCHAR'), ('is_arena_game', 'BOOLEAN'),
        ('is_tournament', 'BOOLEAN'), ('player_identity', 'VARCHAR'),
    )
    _drop_relation(connection, 'prepared_full_sample_narrow')

    # Keep the canonical wide player-game relation physical. Most analytical
    # routes read several source metrics plus canonical opponent/completion
    # fields; leaving this as a view forces a 6M-row source-to-canonical join on
    # every cache miss and makes ordinary filters tens of seconds slower.
    #
    # Copy source columns first, then update only the narrow canonical payload.
    # A single CREATE TABLE ... SELECT over f.* plus g.* makes DuckDB carry the
    # complete wide source through the hash join and can spill several GiB.
    # The two-step build has identical rows and types while
    # keeping the join's working set bounded to the canonical columns. Updates
    # are additionally partitioned by table ID and checkpointed: DuckDB update
    # state cannot all spill, so one transaction across millions of rows defeats
    # a smaller engine budget even when the hash join itself is narrow.
    connection.execute("""
        CREATE TABLE prepared_full_sample_narrow AS
        SELECT
          f.* EXCLUDE (
            pre_match_elo, post_match_elo, opponent_elo,
            Starting_position_in_first_round, end_game_triggered
          )
        FROM source_full_sample f
    """)
    for column, data_type in canonical_columns:
        connection.execute(
            f"ALTER TABLE prepared_full_sample_narrow ADD COLUMN {column} {data_type}"
        )
    update_sql = """
        UPDATE prepared_full_sample_narrow AS f SET
          pre_match_elo = g.pre_match_elo,
          post_match_elo = g.post_match_elo,
          opponent_elo = g.opponent_pre_match_elo,
          opponent_pre_match_elo = g.opponent_pre_match_elo,
          Starting_position_in_first_round = g.starting_position,
          starting_position = g.starting_position,
          end_game_triggered = g.end_game_triggered,
          table_conceded = g.table_conceded,
          is_corrupted_game = g.is_corrupted_game,
          is_completed_game = g.is_completed_game,
          arena_season = g.arena_season,
          is_arena_game = g.is_arena_game,
          is_tournament = g.is_tournament,
          player_identity = g.player_identity
        FROM (SELECT * FROM game_player_narrow WHERE {scope}) AS g
        WHERE f.table_id = g.table_id AND f.player = g.player
          AND {target_scope}
    """
    for scope, target_scope, parameters in canonical_update_scopes(connection):
        connection.execute(update_sql.format(scope=scope, target_scope=target_scope), parameters)
        # Only the inactive candidate is writable. Completing this checkpoint
        # releases each batch's update state; publication still requires the
        # complete builder and snapshot gates, never a partially updated file.
        connection.execute('CHECKPOINT')
    return {'method':'copy_update'}


def canonical_update_scopes(connection, batches: int | None = None):
    """Disjoint table-ID ranges; approximate boundaries do not approximate data."""
    batches = int(os.environ.get('DUCKDB_CANONICAL_UPDATE_BATCHES', '32')) if batches is None else int(batches)
    if not 1 <= batches <= 256:
        raise ValueError('canonical update batches must be between 1 and 256')
    if batches == 1:
        return [('TRUE', 'TRUE', [])]
    # Quantiles only balance transaction sizes. Every exact table ID (including
    # tied IDs) belongs to exactly one half-open range, with unbounded end ranges.
    cuts = connection.execute('SELECT APPROX_QUANTILE(table_id, ?::FLOAT[]) FROM game_player_narrow',
                              [[index/batches for index in range(1, batches)]]).fetchone()[0]
    boundaries = [None, *sorted(set(cuts or [])), None]
    ranges = []
    for lower, upper in zip(boundaries, boundaries[1:]):
        predicates, values = [], []
        if lower is not None:
            predicates.append('table_id >= ?')
            values.append(lower)
        if upper is not None:
            predicates.append('table_id < ?')
            values.append(upper)
        scope = ' AND '.join(predicates) or 'TRUE'
        ranges.append((scope, scope.replace('table_id', 'f.table_id'), values+values))
    return ranges


def create_players_metrics_relation(connection, *, rebuild_base: bool = True) -> int:
    """Materialize the completed, non-corrupted Players analytical fact."""

    if rebuild_base:
        selected = ",\n              ".join(f"f.{column}" for column in PLAYER_METRIC_COLUMNS)
        connection.execute("DROP TABLE IF EXISTS players_metrics_narrow")
        connection.execute(f"""
            CREATE TABLE players_metrics_narrow AS
            SELECT
              {selected}
            FROM prepared_full_sample_narrow f
            WHERE f.is_completed_game AND NOT f.is_corrupted_game
            ORDER BY f.is_mw, f.Map, CAST(f.game_ended_at AS DATE)
        """)
    # General's default comparison cohorts never change when a player is
    # selected. Persist them once per generation for both the no-player default
    # snapshot and default-scope player lookups. The snapshot has no individual
    # player results; its empty selected population must not scan these facts.
    from phase4_local_routes import PLAYERS_METRICS, PLAYERS_MONEY_FIELDS

    aggregate_fields = ["COUNT(*) AS observation_count"]
    aggregate_fields.extend(
        f"{expression} AS {key}" for key, *_rest, expression in PLAYERS_METRICS
    )
    aggregate_fields.extend(
        f"AVG(TRY_CAST({column} AS DOUBLE)) AS raw_{key}"
        for key, column in PLAYERS_MONEY_FIELDS.items()
    )
    aggregates = ",\n              ".join(aggregate_fields)
    default_maps = sql_list(VALID_MAPS)
    connection.execute("DROP TABLE IF EXISTS players_default_cohorts_narrow")
    cohort_predicates = (
        ("all", "TRUE"),
        ("winners", "TRY_CAST(Game_result AS INTEGER) = 1"),
        ("experts", "TRY_CAST(pre_match_elo AS DOUBLE) >= 500"),
        ("masters", "TRY_CAST(pre_match_elo AS DOUBLE) >= 700"),
    )
    for index, (cohort, predicate) in enumerate(cohort_predicates):
        statement = (
            "CREATE TABLE players_default_cohorts_narrow AS"
            if index == 0 else "INSERT INTO players_default_cohorts_narrow"
        )
        connection.execute(f"""
            {statement}
            SELECT is_mw, '{cohort}' AS cohort,
              {aggregates}
            FROM players_metrics_narrow
            WHERE Map IN {default_maps}
              AND pre_match_elo >= 0
              AND opponent_pre_match_elo >= 0
              AND {predicate}
            GROUP BY is_mw
        """)

    # DuckDB row-group pruning is effective only when the selected identity is
    # physically clustered. Keep the cohort-oriented fact above and a second
    # identity-oriented copy for the interactive selected-player path.
    connection.execute("DROP TABLE IF EXISTS players_by_identity_narrow")
    connection.execute("""
        CREATE TABLE players_by_identity_narrow AS
        SELECT * FROM players_metrics_narrow
        ORDER BY player_identity, is_mw, game_ended_at, table_id
    """)
    return int(connection.execute("SELECT COUNT(*) FROM players_metrics_narrow").fetchone()[0])


def create_home_log_feature_relation(connection) -> None:
    """Reduce nested arrays per log row, without correlated UNNEST joins.

    Scalar list operations preserve duplicate counts, null handling and exact
    names. They avoid materializing parent/element joins for the whole Logs
    population, which otherwise spills several GiB at a reduced buffer budget.
    Home deliberately retains corrupted and incomplete observations.
    """
    connection.execute('DROP TABLE IF EXISTS home_log_feature_narrow')
    connection.execute('''CREATE TEMP TABLE home_log_feature_narrow AS
        SELECT l.table_id, l.player,
          LIST_COUNT(LIST_FILTER(COALESCE(l.played_animals, []),
            e -> e.animal = 'Emu'))::BIGINT AS emus_played,
          COALESCE(l."2cp_worker", FALSE)::BIGINT AS two_cp_workers_taken,
          (CASE WHEN l.chosen_5cp_bonus IN ('1 University', '1 Partner-Zoo') THEN 1 ELSE 0 END
            + CASE WHEN l.chosen_8cp_bonus IN ('1 University', '1 Partner-Zoo') THEN 1 ELSE 0 END
          )::BIGINT AS free_unis_and_partner_zoos,
          (LIST_CONTAINS(COALESCE(l.cards_drawn, CAST([] AS VARCHAR[])), 'Primates')
            AND NOT LIST_CONTAINS(LIST_TRANSFORM(COALESCE(l.played_projects, []),
              e -> e.project), 'Primates')) AS primates_candidate,
          LIST_CONTAINS(LIST_TRANSFORM(COALESCE(l.played_animals, []),
            e -> e.animal), 'Proboscis Monkey') AS has_proboscis,
          COALESCE(TRY_CAST(l.petting_zoo_built AS INTEGER), 0) = 1
            AND NOT LIST_CONTAINS(LIST_TRANSFORM(COALESCE(l.played_sponsors, []),
              e -> e.sponsor), 'Horse Whisperer') AS empty_petting_candidate
        FROM source_logs l
    ''')
    # Count distinct matching players rather than joining a correlated EXISTS
    # against every Full Sample row. Duplicate Logs rows must not turn an own
    # Proboscis into an opponent; null names cannot satisfy player inequality.
    connection.execute('DROP TABLE IF EXISTS home_proboscis_table_narrow')
    connection.execute('''CREATE TEMP TABLE home_proboscis_table_narrow AS
        SELECT table_id, COUNT(DISTINCT player) AS proboscis_players,
          ANY_VALUE(player) AS only_proboscis_player
        FROM home_log_feature_narrow
        WHERE has_proboscis AND player IS NOT NULL
        GROUP BY table_id
    ''')


def create_fast_filter_relations(connection) -> dict[str, int]:
    """Materialize compact serving facts for the remaining scan-heavy routes.

    These tables contain only the shared filter dimensions and route payload.
    Expensive opponent comparisons and nested-log classifications are computed
    once per immutable generation rather than on every cache miss.
    """

    scope_columns = """
      me.table_id, me.player, me.is_mw, me.Map, me.game_ended_at,
      me.starting_position, me.pre_match_elo, me.opponent_pre_match_elo,
      me.elo_delta, TRUE AS is_completed_game, me.arena_season,
      me.arena_season IS NOT NULL AS is_arena_game, me.is_tournament,
      FALSE AS is_corrupted_game
    """
    general_mask = " + ".join(
        f"CASE WHEN TRY_CAST(me.{field} AS DOUBLE) > TRY_CAST(opp.{field} AS DOUBLE) "
        f"THEN {1 << index}::UBIGINT ELSE 0::UBIGINT END"
        for index, field in enumerate(PREDICTOR_GENERAL_FIELDS)
    )
    icon_mask = " + ".join(
        f"CASE WHEN TRY_CAST(me.{field} AS DOUBLE) > TRY_CAST(opp.{field} AS DOUBLE) "
        f"THEN {1 << index}::UBIGINT ELSE 0::UBIGINT END"
        for index, field in enumerate(ICON_FIELDS)
    )
    connection.execute("DROP TABLE IF EXISTS predictor_pair_fact_narrow")
    connection.execute(f"""
        CREATE TABLE predictor_pair_fact_narrow AS
        SELECT {scope_columns},
          ({general_mask}) AS general_mask,
          ({icon_mask}) AS icon_mask
        FROM players_metrics_narrow me
        JOIN players_metrics_narrow opp
          ON me.table_id = opp.table_id AND me.player <> opp.player
        ORDER BY me.is_mw, me.game_ended_at, me.Map
    """)

    icon_columns = ",\n          ".join(
        f"TRY_CAST(me.{field} AS SMALLINT) AS {field}" for field in ICON_FIELDS
    )
    connection.execute("DROP TABLE IF EXISTS icon_filter_fact_narrow")
    connection.execute(f"""
        CREATE TABLE icon_filter_fact_narrow AS
        SELECT {scope_columns},
          {icon_columns}
        FROM players_metrics_narrow me
        ORDER BY me.is_mw, me.game_ended_at, me.Map
    """)

    connection.execute("DROP TABLE IF EXISTS action_starting_fact_narrow")
    connection.execute(f"""
        CREATE TABLE action_starting_fact_narrow AS
        SELECT {scope_columns},
          TRY_CAST(ml.association_starting_strength AS SMALLINT) AS association_strength,
          TRY_CAST(ml.build_starting_strength AS SMALLINT) AS build_strength,
          TRY_CAST(ml.cards_starting_strength AS SMALLINT) AS cards_strength,
          TRY_CAST(ml.sponsors_starting_strength AS SMALLINT) AS sponsors_strength,
          TRY_CAST(ml.association_starting_strength AS SMALLINT)
            > TRY_CAST(ol.association_starting_strength AS SMALLINT) AS higher_association,
          TRY_CAST(ml.build_starting_strength AS SMALLINT)
            > TRY_CAST(ol.build_starting_strength AS SMALLINT) AS higher_build,
          TRY_CAST(ml.cards_starting_strength AS SMALLINT)
            > TRY_CAST(ol.cards_starting_strength AS SMALLINT) AS higher_cards,
          TRY_CAST(ml.sponsors_starting_strength AS SMALLINT)
            > TRY_CAST(ol.sponsors_starting_strength AS SMALLINT) AS higher_sponsors
        FROM players_metrics_narrow me
        JOIN source_logs ml USING(table_id, player)
        JOIN players_metrics_narrow opp
          ON me.table_id = opp.table_id AND me.player <> opp.player
        JOIN source_logs ol ON ol.table_id = opp.table_id AND ol.player = opp.player
        ORDER BY me.is_mw, me.game_ended_at, me.Map
    """)

    from phase4_local_routes import predictor_specific_feature_sql
    connection.execute("DROP TABLE IF EXISTS predictor_specific_player_fact_narrow")
    connection.execute(
        "CREATE TABLE predictor_specific_player_fact_narrow AS "
        + predictor_specific_feature_sql()
        + " ORDER BY is_mw, game_ended_at, Map"
    )

    create_home_log_feature_relation(connection)
    connection.execute("DROP TABLE IF EXISTS home_filter_fact_narrow")
    connection.execute("""
        CREATE TABLE home_filter_fact_narrow AS
        SELECT f.table_id, f.player, f.is_mw, f.Map, f.game_ended_at,
          f.starting_position, f.pre_match_elo, f.opponent_pre_match_elo,
          f.is_completed_game, f.arena_season, f.is_arena_game, f.is_tournament,
          f.is_corrupted_game,
          TRY_CAST(f.Played_animals AS BIGINT) AS played_animals,
          TRY_CAST(f.Played_sponsors AS BIGINT) AS played_sponsors,
          TRY_CAST(f.Conservation_project_association_tasks AS BIGINT) AS projects_supported,
          TRY_CAST(f.Number_of_breaks_triggered AS BIGINT) AS breaks_triggered,
          TRY_CAST(f.X_Tokens_gained AS BIGINT) AS x_tokens_gained,
          l.player IS NOT NULL AS has_log,
          COALESCE(l.emus_played, 0) AS emus_played,
          COALESCE(l.two_cp_workers_taken, 0) AS two_cp_workers_taken,
          CASE WHEN COALESCE(l.empty_petting_candidate, FALSE)
                 AND COALESCE(TRY_CAST(f.Petting_Zoo_icons AS INTEGER), 0) = 0
               THEN 1 ELSE 0 END AS empty_petting_zoos_played,
          COALESCE(l.free_unis_and_partner_zoos, 0) AS free_unis_and_partner_zoos,
          CASE WHEN COALESCE(l.primates_candidate, FALSE)
                 AND f.player IS NOT NULL
                 AND (p.proboscis_players > 1 OR
                      (p.proboscis_players = 1 AND f.player <> p.only_proboscis_player))
               THEN 1 ELSE 0 END AS bignose_project_blocks
        FROM prepared_full_sample_narrow f
        LEFT JOIN home_log_feature_narrow l USING(table_id, player)
        LEFT JOIN home_proboscis_table_narrow p ON p.table_id = f.table_id
        ORDER BY f.is_mw, f.game_ended_at, f.Map
    """)
    return {
        name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        for name in (
            "predictor_pair_fact_narrow", "icon_filter_fact_narrow",
            "action_starting_fact_narrow", "home_filter_fact_narrow",
            "predictor_specific_player_fact_narrow",
        )
    }


def create_card_action_pair_filter_relation(connection) -> int:
    """Refresh-only pair expansion, without duplicating names or raw logs.

    Strict selection telemetry guarantees two distinct selected action cards
    per player-game. Pair means can recover the normal-card component because
    each eligible played card appears exactly twice; action-card components
    still use all eligible selections, including games with no played card.
    Standalone clustered CIs continue to use table-keyed component facts.
    """
    connection.execute('DROP TABLE IF EXISTS card_action_pair_filter_fact_narrow')
    connection.execute('''CREATE TABLE card_action_pair_filter_fact_narrow AS
      SELECT c.card_id, a.card_order AS action_card_order,
        c.is_mw, c.Map, c.game_ended_at, c.starting_position,
        c.pre_match_elo, c.opponent_pre_match_elo, c.elo_delta,
        c.is_completed_game, c.arena_season, c.is_arena_game, c.is_tournament,
        c.played_r1, c.played_r2, c.played_r3, c.played_r4, c.played_r5, c.played_r6plus
      FROM card_play_filter_fact_mw_narrow c
      JOIN mw_action_card_selection_narrow a USING(table_id, player)
    ''')
    return int(connection.execute('SELECT COUNT(*) FROM card_action_pair_filter_fact_narrow').fetchone()[0])


def create_log_filter_relations(connection) -> dict[str, int]:
    """Flatten page events without imposing Cards' two-log-row eligibility.

    Endgames, Sponsor Endgames and Project Rewards use the joined Log Sample,
    including matching player logs from tables with incomplete log telemetry.
    Their completion/corruption rules are enforced independently. Do not reuse
    Cards' stricter event facts, or duplicate logs by joining event facts back
    to a log-row population at request time.
    """
    dimensions = """g.table_id, g.player, g.is_mw, g.map_name AS Map,
      g.game_ended_at, g.starting_position, g.pre_match_elo,
      g.opponent_pre_match_elo, g.elo_delta, g.is_completed_game,
      g.arena_season, g.is_arena_game, g.is_tournament, g.is_corrupted_game"""
    definitions = {
        'log_player_filter_fact_narrow': f"""SELECT {dimensions}
          FROM source_logs l JOIN game_player_narrow g USING(table_id, player)
          WHERE NOT g.is_corrupted_game""",
        'endgame_dealt_event_narrow': """SELECT g.table_id, g.player,
          TRIM(e.card_name) AS endgame_name
          FROM source_logs l JOIN game_player_narrow g USING(table_id, player),
            UNNEST(COALESCE(l.endgame, CAST([] AS VARCHAR[]))) e(card_name)
          WHERE TRIM(e.card_name) <> '' AND NOT g.is_corrupted_game""",
        'endgame_score_filter_event_narrow': """SELECT g.table_id, g.player,
          TRIM(e.score.endgame) AS endgame_name, TRY_CAST(e.score.cp AS BIGINT) AS cp
          FROM source_logs l JOIN game_player_narrow g USING(table_id, player),
            UNNEST(COALESCE(l.endgame_scores, [])) e(score)
          WHERE e.score.endgame IS NOT NULL AND NOT g.is_corrupted_game""",
        'sponsor_play_filter_event_narrow': """SELECT DISTINCT g.table_id, g.player,
          TRIM(e.card.sponsor) AS sponsor_name
          FROM source_logs l JOIN game_player_narrow g USING(table_id, player),
            UNNEST(COALESCE(l.played_sponsors, [])) e(card)
          WHERE e.card.sponsor IS NOT NULL AND NOT g.is_corrupted_game""",
        'sponsor_endgame_filter_event_narrow': """SELECT g.table_id, g.player,
          TRIM(e.score.sponsor) AS sponsor_name,
          TRY_CAST(e.score.cp AS BIGINT) AS cp,
          TRY_CAST(e.score.appeal AS BIGINT) AS appeal
          FROM source_logs l JOIN game_player_narrow g USING(table_id, player),
            UNNEST(COALESCE(l.endgame_from_sponsors, [])) e(score)
          WHERE e.score.sponsor IS NOT NULL AND NOT g.is_corrupted_game""",
        'project_reward_choice_narrow': f"""SELECT {dimensions},
          LOWER(TRIM(e.reward.reward)) AS reward,
          TRY_CAST(e.reward."order" AS BIGINT) AS reward_order
          FROM source_logs l JOIN game_player_narrow g USING(table_id, player),
            UNNEST(COALESCE(l.project_rewards, [])) e(reward)
          WHERE e.reward.reward IS NOT NULL AND NOT g.is_corrupted_game""",
    }
    counts = {}
    for name, query in definitions.items():
        connection.execute(f'DROP TABLE IF EXISTS {name}')
        connection.execute(f'CREATE TABLE {name} AS {query}')
        counts[name] = int(connection.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0])
    return counts


def create_card_table_filter_relations(connection, batches: int | None = None) -> None:
    """Bound symmetric Cards moments without splitting any table/card group.

    Both the game scope and card moments use the same disjoint table-ID bucket.
    This avoids a population-wide aggregate/join spill at a low memory budget.
    All player observations of each table stay together, preserving clustered
    counts, eligibility and ordinary confidence-interval sufficient statistics.
    """
    batches = int(os.environ.get('DUCKDB_CARD_TABLE_BATCHES', '32')) if batches is None else int(batches)
    if not 1 <= batches <= 256:
        raise ValueError('card table batches must be between 1 and 256')

    for relation, dataset in (
        ("card_filter_fact_mw_narrow", 1),
        ("card_filter_fact_base_narrow", 0),
    ):
        table_relation = relation.replace("_fact_", "_table_fact_")
        connection.execute(f"DROP TABLE IF EXISTS {table_relation}")
        query = f"""
            WITH table_scope AS (
              SELECT table_id, COUNT(*) AS table_player_count,
                COUNT(pre_match_elo) AS table_elo_count,
                MIN(pre_match_elo) AS min_pre_match_elo,
                MAX(pre_match_elo) AS max_pre_match_elo,
                ANY_VALUE(map_name) AS Map,
                ANY_VALUE(game_ended_at) AS game_ended_at,
                BOOL_OR(is_completed_game) AS is_completed_game,
                ANY_VALUE(arena_season) AS arena_season,
                BOOL_OR(is_arena_game) AS is_arena_game,
                BOOL_OR(is_tournament) AS is_tournament
              FROM game_player_narrow
              WHERE is_mw = {dataset} AND NOT is_corrupted_game AND {{scope}}
              GROUP BY table_id
            ), card_moments AS (
              SELECT table_id, card_name, MAX(card_type) AS card_type,
                MAX(CASE WHEN played_count > 0 AND elo_delta IS NOT NULL
                         THEN 1 ELSE 0 END)::BIGINT AS n_played,
                SUM(played_count) FILTER (
                  WHERE played_count > 0 AND elo_delta IS NOT NULL
                )::BIGINT AS played_n,
                FSUM(played_count * elo_delta) FILTER (
                  WHERE played_count > 0 AND elo_delta IS NOT NULL
                ) AS played_sum,
                FSUM(played_count * elo_delta * elo_delta) FILTER (
                  WHERE played_count > 0 AND elo_delta IS NOT NULL
                ) AS played_sumsq,
                SUM(played_count) FILTER (
                  WHERE played_count > 0 AND elo_delta IS NOT NULL
                    AND pre_match_elo IS NOT NULL
                )::BIGINT AS pre_match_n,
                FSUM(played_count * pre_match_elo) FILTER (
                  WHERE played_count > 0 AND elo_delta IS NOT NULL
                    AND pre_match_elo IS NOT NULL
                ) AS pre_match_sum,
                COUNT(*) FILTER (
                  WHERE in_hand > 0 AND elo_delta IS NOT NULL
                )::BIGINT AS hand_n,
                FSUM(elo_delta) FILTER (
                  WHERE in_hand > 0 AND elo_delta IS NOT NULL
                ) AS hand_sum,
                FSUM(elo_delta * elo_delta) FILTER (
                  WHERE in_hand > 0 AND elo_delta IS NOT NULL
                ) AS hand_sumsq,
                MAX(seen)::BIGINT AS n_seen
              FROM {relation}
              WHERE {{scope}}
              GROUP BY table_id, card_name
            )
            SELECT m.*, s.* EXCLUDE(table_id), {dataset}::BIGINT AS is_mw
            FROM card_moments m JOIN table_scope s USING(table_id)
        """
        connection.execute(f'CREATE TABLE {table_relation} AS '+query.format(scope='FALSE'))
        for bucket in range(batches):
            connection.execute(f'INSERT INTO {table_relation} '+query.format(
                scope=f'hash(table_id) % {batches} = {bucket}'))
            connection.execute('CHECKPOINT')


def create_card_play_filter_summary(connection, batches: int | None = None) -> int:
    """Bound LIST/DISTINCT aggregate state without splitting player-card groups."""
    batches = int(os.environ.get('DUCKDB_CARD_PLAY_SUMMARY_BATCHES', '32')) if batches is None else int(batches)
    if not 1 <= batches <= 256:
        raise ValueError('card play summary batches must be between 1 and 256')
    connection.execute("DROP TABLE IF EXISTS card_play_filter_summary")
    aggregate = """
        SELECT table_id, player, card_name, MAX(card_type) AS card_type,
          COUNT(*)::BIGINT AS played_count,
          COUNT(*) FILTER (WHERE played_round = 1)::BIGINT AS played_r1,
          COUNT(*) FILTER (WHERE played_round = 2)::BIGINT AS played_r2,
          COUNT(*) FILTER (WHERE played_round = 3)::BIGINT AS played_r3,
          COUNT(*) FILTER (WHERE played_round = 4)::BIGINT AS played_r4,
          COUNT(*) FILTER (WHERE played_round = 5)::BIGINT AS played_r5,
          COUNT(*) FILTER (WHERE played_round >= 6)::BIGINT AS played_r6plus,
          LIST(DISTINCT played_round ORDER BY played_round) AS played_rounds
        FROM card_play_narrow
        WHERE {scope}
        GROUP BY table_id, player, card_name
    """
    connection.execute('CREATE TEMP TABLE card_play_filter_summary AS '+aggregate.format(scope='FALSE'))
    for bucket in range(batches):
        # Keep every round/repeated event of each player-game/card together.
        connection.execute('INSERT INTO card_play_filter_summary '+aggregate.format(
            scope=f'hash(table_id) % {batches} = {bucket}'))
        connection.execute('CHECKPOINT')
    return int(connection.execute('SELECT COUNT(*) FROM card_play_filter_summary').fetchone()[0])


def create_card_filter_core_relation(connection, batches: int | None = None, *,
                                    hand_is_subset_of_seen: bool = False) -> int:
    """Bound exact contexts; skip hand-only work only for a trusted producer.

    The canonical log producer filters null/blank card names and includes every
    hand key in seen. Generic callers keep the hand-only/null-key branch unless
    they explicitly guarantee that invariant. Observation grain, batching and
    downstream complete facts remain unchanged.
    """
    batches = int(os.environ.get('DUCKDB_CARD_FILTER_CORE_BATCHES', '32')) if batches is None else int(batches)
    if not 1 <= batches <= 256:
        raise ValueError('card filter core batches must be between 1 and 256')
    connection.execute("DROP TABLE IF EXISTS card_filter_fact_narrow")
    hand_only = "" if hand_is_subset_of_seen else """
        UNION ALL
        SELECT h.table_id, h.player, h.card_name, p.card_type,
          COALESCE(p.played_count, 0), COALESCE(p.played_r1, 0),
          COALESCE(p.played_r2, 0), COALESCE(p.played_r3, 0),
          COALESCE(p.played_r4, 0), COALESCE(p.played_r5, 0),
          COALESCE(p.played_r6plus, 0), 1, 0
        FROM hand h
        LEFT JOIN played p USING(table_id, player, card_name)
        WHERE NOT EXISTS (
          SELECT 1 FROM seen s
          WHERE s.table_id = h.table_id AND s.player = h.player
            AND s.card_name = h.card_name
        )
    """
    query = """
        WITH seen AS MATERIALIZED (SELECT * FROM card_seen_narrow WHERE {scope}),
        hand AS MATERIALIZED (SELECT * FROM card_in_hand_narrow WHERE {scope}),
        played AS MATERIALIZED (SELECT * FROM card_play_filter_summary WHERE {scope}),
        games AS MATERIALIZED (SELECT table_id,player,is_mw FROM game_player_narrow WHERE {scope}),
        core AS (
        SELECT s.table_id, s.player, s.card_name, p.card_type,
          COALESCE(p.played_count, 0)::BIGINT AS played_count,
          COALESCE(p.played_r1, 0)::BIGINT AS played_r1,
          COALESCE(p.played_r2, 0)::BIGINT AS played_r2,
          COALESCE(p.played_r3, 0)::BIGINT AS played_r3,
          COALESCE(p.played_r4, 0)::BIGINT AS played_r4,
          COALESCE(p.played_r5, 0)::BIGINT AS played_r5,
          COALESCE(p.played_r6plus, 0)::BIGINT AS played_r6plus,
          CASE WHEN h.card_name IS NULL THEN 0 ELSE 1 END::BIGINT AS in_hand,
          1::BIGINT AS seen
        FROM seen s
        LEFT JOIN hand h USING(table_id, player, card_name)
        LEFT JOIN played p USING(table_id, player, card_name)
        {hand_only}
        UNION ALL
        SELECT p.table_id, p.player, p.card_name, p.card_type,
          p.played_count, p.played_r1, p.played_r2, p.played_r3,
          p.played_r4, p.played_r5, p.played_r6plus, 0, 0
        FROM played p
        WHERE NOT EXISTS (
          SELECT 1 FROM seen s
          WHERE s.table_id = p.table_id AND s.player = p.player
            AND s.card_name = p.card_name
        ) AND NOT EXISTS (
          SELECT 1 FROM hand h
          WHERE h.table_id = p.table_id AND h.player = p.player
            AND h.card_name = p.card_name
        )
        )
        SELECT core.*, g.is_mw
        FROM core JOIN games g USING(table_id, player)
    """
    connection.execute('CREATE TABLE card_filter_fact_narrow AS '+query.format(scope='FALSE',hand_only=hand_only))
    for bucket in range(batches):
        # Bound the complete seen/hand/played groups without splitting tables.
        connection.execute('INSERT INTO card_filter_fact_narrow '+query.format(
            scope=f'hash(table_id) % {batches} = {bucket}',hand_only=hand_only))
        connection.execute('CHECKPOINT')
    return int(connection.execute('SELECT COUNT(*) FROM card_filter_fact_narrow').fetchone()[0])


def create_card_filter_fact_relation(connection, *, hand_is_subset_of_seen: bool = False) -> int:
    """Build the one-scan Cards serving fact from canonical event grains."""
    create_card_play_filter_summary(connection)
    create_card_filter_core_relation(connection,hand_is_subset_of_seen=hand_is_subset_of_seen)
    connection.execute("DROP TABLE IF EXISTS card_filter_fact_mw_narrow")
    connection.execute("""
        CREATE TABLE card_filter_fact_mw_narrow AS
        SELECT * EXCLUDE(is_mw) FROM card_filter_fact_narrow WHERE is_mw = 1
    """)
    connection.execute("DROP TABLE IF EXISTS card_filter_fact_base_narrow")
    connection.execute("""
        CREATE TABLE card_filter_fact_base_narrow AS
        SELECT * EXCLUDE(is_mw) FROM card_filter_fact_narrow WHERE is_mw = 0
    """)
    connection.execute("DROP TABLE IF EXISTS card_catalog_narrow")
    connection.execute("""
        CREATE TABLE card_catalog_narrow AS
        SELECT ROW_NUMBER() OVER (ORDER BY card_name)::SMALLINT AS card_id,
          card_name, card_type
        FROM (SELECT card_name, ANY_VALUE(card_type) AS card_type
              FROM card_play_narrow GROUP BY card_name)
    """)
    for relation, dataset in (
        ("card_filter_fact_mw_narrow", 1),
        ("card_filter_fact_base_narrow", 0),
    ):
        scoped_relation = relation + "_scoped"
        connection.execute(f"DROP TABLE IF EXISTS {scoped_relation}")
        connection.execute(f"""
            CREATE TABLE {scoped_relation} AS
            SELECT c.*, {dataset}::BIGINT AS is_mw,
              g.map_name AS Map, g.game_ended_at, g.starting_position,
              g.pre_match_elo, g.opponent_pre_match_elo, g.elo_delta,
              g.is_completed_game, g.arena_season, g.is_arena_game,
              g.is_tournament
            FROM {relation} c
            JOIN game_player_narrow g USING(table_id, player)
            WHERE NOT g.is_corrupted_game
        """)
        connection.execute(f"DROP TABLE {relation}")
        connection.execute(f"ALTER TABLE {scoped_relation} RENAME TO {relation}")
        played_relation = relation.replace("card_filter_fact_", "card_play_filter_fact_")
        connection.execute(f"DROP TABLE IF EXISTS {played_relation}")
        connection.execute(f"""
            CREATE TABLE {played_relation} AS
            SELECT c.*, k.card_id, s.played_rounds
            FROM {relation} c JOIN card_catalog_narrow k USING(card_name)
            JOIN card_play_filter_summary s USING(table_id, player, card_name)
            WHERE c.played_count > 0
            ORDER BY c.game_ended_at, c.Map, c.table_id, c.player
        """)
    create_card_table_filter_relations(connection)
    counts = connection.execute("""
        SELECT
          (SELECT COUNT(*) FROM card_filter_fact_mw_narrow),
          (SELECT COUNT(*) FROM card_filter_fact_base_narrow)
    """).fetchone()
    connection.execute("DROP TABLE card_filter_fact_narrow")
    return int(counts[0]) + int(counts[1])




def create_seen_card_relation(connection, batches: int | None = None) -> int:
    """Exact seen-card set without concatenating all nested arrays in memory."""
    batches = int(os.environ.get('DUCKDB_SEEN_CARD_BATCHES', '32')) if batches is None else int(batches)
    if not 1 <= batches <= 256:
        raise ValueError('seen-card batches must be between 1 and 256')
    connection.execute('DROP TABLE IF EXISTS card_seen_narrow')
    connection.execute('CREATE TABLE card_seen_narrow AS SELECT table_id, player, card_name FROM card_in_hand_narrow WHERE FALSE')
    for bucket in range(batches):
        # Each table ID belongs to one bucket, so per-bucket DISTINCT is globally
        # exact, including repeated logs and duplicate/trimmed card names.
        connection.execute(f'''
            INSERT INTO card_seen_narrow
            SELECT DISTINCT table_id, player, card_name FROM (
              SELECT table_id, player, card_name FROM card_in_hand_narrow
              WHERE hash(table_id) % {batches} = {bucket}
              UNION ALL
              SELECT l.table_id, l.player, TRIM(seen.card_name) AS card_name
              FROM (SELECT table_id, player, display_cards FROM card_log_narrow
                    WHERE hash(table_id) % {batches} = {bucket}) l
              CROSS JOIN UNNEST(COALESCE(l.display_cards, CAST([] AS VARCHAR[]))) AS seen(card_name)
              WHERE TRIM(seen.card_name) <> ''
            ) observations
        ''')
        connection.execute('CHECKPOINT')
    return int(connection.execute('SELECT COUNT(*) FROM card_seen_narrow').fetchone()[0])


def create_log_card_relations(connection):
    """Build the log-population facts; callers may reuse only identical inputs."""
    connection.execute("DROP TABLE IF EXISTS card_play_event_narrow")
    connection.execute("DROP TABLE IF EXISTS card_play_narrow")
    connection.execute("""
        CREATE TEMP TABLE valid_log_ids_narrow AS
        SELECT table_id
        FROM source_logs
        GROUP BY table_id
        HAVING COUNT(*) = 2
    """)
    card_play_select = """
        SELECT
          g.table_id, g.player, g.player_id, g.is_mw, g.map_name,
          g.game_date, g.game_ended_at, g.starting_position,
          g.pre_match_elo, g.post_match_elo, g.opponent_pre_match_elo,
          g.elo_delta, g.player_identity, g.arena_season,
          g.is_arena_game, g.is_tournament, g.is_completed_game,
          g.result_code, g.concede, g.table_conceded,
          g.end_game_triggered, {name} AS card_name,
          '{card_type}' AS card_type,
          TRY_CAST(card.round AS BIGINT) AS played_round,
          TRY_CAST(card."move" AS BIGINT) AS played_move,
          TRY_CAST(card."order" AS BIGINT) AS played_order
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
        "CREATE TABLE card_play_event_narrow AS "
        + card_play_select.format(
            name=first_name, card_type=first_type, array_name=first_array
        )
    )
    for name, card_type, array_name in branches[1:]:
        connection.execute(
            "INSERT INTO card_play_event_narrow\n" + card_play_select.format(
                name=name, card_type=card_type, array_name=array_name
            )
        )
    # Keep the source event grain available. The compatibility relation
    # removes only exact duplicate log events; it does not collapse plays
    # from different rounds or moves.
    connection.execute("""
        CREATE TABLE card_play_narrow AS
        SELECT * EXCLUDE(event_duplicate)
        FROM (
          SELECT *, ROW_NUMBER() OVER (
            PARTITION BY table_id, player, card_type, card_name,
              played_round, played_move, played_order
            ORDER BY table_id
          ) AS event_duplicate
          FROM card_play_event_narrow
        )
        WHERE event_duplicate = 1
    """)
    # Independent references are constructed on demand in a scratch database,
    # never in nightly serving facts (phase5_cardcard_reconcile).
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
    create_seen_card_relation(connection)
    # Cards' played, in-hand and seen contexts share one exact
    # player-game/card fact. Played event counts are
    # retained by round so repeated plays and round filters preserve the
    # existing weighted EV and sample-variance semantics.
    # Canonical seen includes all normalized hand keys, allowing an opt-in
    # subset fast path. Default enablement stays held until the complete native
    # public-output gate is qualified; generic/direct callers retain the union.
    create_card_filter_fact_relation(connection)
    cards_pair_rows = create_cards_pair_relations(connection)
    combo_pair_rows = create_combo_card_pair_relations(connection, EXCLUDED_PROJECTS)
    connection.execute("DROP TABLE IF EXISTS opening_hand_narrow")
    connection.execute("""
        CREATE TABLE opening_hand_narrow AS
        SELECT DISTINCT
          g.table_id, g.player, g.player_identity,
          TRIM(dealt.card_name) AS card_name,
          LIST_CONTAINS(COALESCE(l.opening_keep, CAST([] AS VARCHAR[])), dealt.card_name)
            AS kept
        FROM source_logs l
        JOIN game_player_narrow g USING(table_id, player)
        JOIN valid_log_ids_narrow v USING(table_id)
        CROSS JOIN UNNEST(
          COALESCE(l.opening_cards, CAST([] AS VARCHAR[]))
        ) AS dealt(card_name)
        WHERE TRIM(dealt.card_name) <> '' AND NOT g.is_corrupted_game
    """)
    connection.execute("DROP TABLE IF EXISTS endgame_score_event_narrow")
    connection.execute("""
        CREATE TABLE endgame_score_event_narrow AS
        SELECT g.table_id, g.player, g.player_identity,
          TRIM(event.score.endgame) AS endgame_name,
          TRY_CAST(event.score.cp AS BIGINT) AS cp
        FROM source_logs l
        JOIN game_player_narrow g USING(table_id, player)
        JOIN valid_log_ids_narrow v USING(table_id)
        CROSS JOIN UNNEST(COALESCE(l.endgame_scores, [])) AS event(score)
        WHERE event.score.endgame IS NOT NULL AND NOT g.is_corrupted_game
    """)
    connection.execute("DROP TABLE IF EXISTS conservation_cp_player_narrow")
    connection.execute("""
        CREATE TABLE conservation_cp_player_narrow AS
        SELECT g.table_id, g.player, g.player_identity,
          LOWER(TRIM(l.chosen_5cp_bonus)) AS chosen_5cp_bonus,
          LOWER(TRIM(l.chosen_8cp_bonus)) AS chosen_8cp_bonus,
          (SELECT MIN(TRY_CAST(h.cp_event."move" AS INTEGER))
             FROM UNNEST(COALESCE(l.cp_history, [])) AS h(cp_event)
            WHERE TRY_CAST(cp_event.cp AS INTEGER) >= 5) AS my_5_move,
          (SELECT MIN(TRY_CAST(h.cp_event."move" AS INTEGER))
             FROM UNNEST(COALESCE(l.cp_history, [])) AS h(cp_event)
            WHERE TRY_CAST(cp_event.cp AS INTEGER) >= 8) AS my_8_move
        FROM source_logs l
        JOIN game_player_narrow g USING(table_id, player)
        JOIN valid_log_ids_narrow v USING(table_id)
        WHERE NOT g.is_corrupted_game
    """)
    connection.execute("DROP TABLE IF EXISTS conservation_cp_opportunity_narrow")
    connection.execute("""
        CREATE TABLE conservation_cp_opportunity_narrow AS
        SELECT DISTINCT table_id, player, threshold, raw_value
        FROM (
          SELECT l.table_id, l.player, 5 AS threshold,
            LOWER(TRIM(r.reward)) AS raw_value
          FROM source_logs l
          JOIN valid_log_ids_narrow v USING(table_id)
          CROSS JOIN UNNEST(COALESCE(l."5cp_bonus", [])) AS r(reward)
          UNION ALL
          SELECT l.table_id, l.player, 8,
            LOWER(TRIM(r.reward))
          FROM source_logs l
          JOIN valid_log_ids_narrow v USING(table_id)
          CROSS JOIN UNNEST(COALESCE(l."8cp_bonus", [])) AS r(reward)
          UNION ALL
          SELECT table_id, player, 5, '5 money'
          FROM conservation_cp_player_narrow
          UNION ALL
          SELECT table_id, player, 8, '5 money'
          FROM conservation_cp_player_narrow
        ) rewards
        WHERE raw_value IS NOT NULL AND raw_value <> ''
    """)
    return cards_pair_rows, combo_pair_rows
def create_mw_action_card_draft_relation(connection, batches: int | None = None) -> int:
    """Exact draft facts in disjoint table buckets, avoiding a global window/join.

    Only fields consumed by the draft result cross the ranking boundary.
    Eligibility, first-player orientation, selected cards and draft flags retain
    the original table-level population; batching never samples observations.
    """
    batches = int(os.environ.get("DUCKDB_MW_DRAFT_BATCHES", "32")) if batches is None else int(batches)
    if not 1 <= batches <= 256:
        raise ValueError("MW draft batches must be between 1 and 256")
    connection.execute("DROP TABLE IF EXISTS mw_action_card_draft_narrow")
    for bucket in range(batches):
        query = f"""WITH ranked AS (
              SELECT f.table_id, f.pre_match_elo, f.Map, f.game_ended_at,
                f.is_completed_game, f.is_arena_game, f.arena_season, f.is_tournament,
                f.First_drafted_action_card, f.Second_drafted_action_card,
                f.Third_drafted_action_card,
                ROW_NUMBER() OVER (
                  PARTITION BY f.table_id
                  ORDER BY CASE f.starting_position WHEN 'First player' THEN 1 ELSE 2 END,
                    f.player
                ) AS player_position
              FROM prepared_full_sample_narrow f
              JOIN mw_action_card_eligible_tables_narrow eligible USING(table_id)
              WHERE COALESCE(HASH(f.table_id), 0) % {batches} = {bucket}
            )
            , paired AS (
              SELECT table_id,
                MAX(CASE WHEN player_position = 1 THEN pre_match_elo END) AS first_pre_match_elo,
                MAX(CASE WHEN player_position = 2 THEN pre_match_elo END) AS second_pre_match_elo,
                MAX(CASE WHEN player_position = 1 THEN Map END) AS first_map,
                MAX(CASE WHEN player_position = 2 THEN Map END) AS second_map,
                MAX(game_ended_at) AS game_ended_at,
                BOOL_AND(is_completed_game) AS is_completed_game,
                BOOL_OR(is_arena_game) AS is_arena_game,
                MAX(arena_season) AS arena_season,
                BOOL_OR(is_tournament) AS is_tournament,
                MAX(CASE WHEN player_position = 1 THEN First_drafted_action_card END) AS p1_first,
                MAX(CASE WHEN player_position = 2 THEN First_drafted_action_card END) AS p2_first,
                MAX(CASE WHEN player_position = 1 THEN Second_drafted_action_card END) AS p1_second,
                MAX(CASE WHEN player_position = 2 THEN Second_drafted_action_card END) AS p2_second,
                MAX(CASE WHEN player_position = 1 THEN Third_drafted_action_card END) AS p1_third,
                MAX(CASE WHEN player_position = 2 THEN Third_drafted_action_card END) AS p2_third
              FROM ranked GROUP BY table_id
            ), selected AS (
              SELECT table_id, LIST(card_key) AS selected_cards
              FROM mw_action_card_selection_narrow
              WHERE COALESCE(HASH(table_id), 0) % {batches} = {bucket}
              GROUP BY table_id
            )
            SELECT p.table_id, p.first_pre_match_elo, p.second_pre_match_elo,
              p.first_map, p.second_map, p.game_ended_at, p.is_completed_game,
              p.is_arena_game, p.arena_season, p.is_tournament,
              c.card_order, c.card_type, c.card_number, c.card_name, c.card_key,
              LIST_CONTAINS(s.selected_cards, c.card_key) AS picked,
              c.card_key IN (p.p1_first, p.p2_first) AS drafted_first,
              c.card_key IN (p.p1_second, p.p2_second) AS drafted_second,
              c.card_key IN (p.p1_third, p.p2_third) AS undrafted
            FROM paired p JOIN selected s USING(table_id)
            CROSS JOIN mw_action_card_catalog_narrow c
            WHERE c.card_key IN (
              p.p1_first, p.p2_first, p.p1_second, p.p2_second, p.p1_third, p.p2_third
            )"""
        if bucket == 0:
            connection.execute("CREATE TABLE mw_action_card_draft_narrow AS " + query)
        else:
            connection.execute("INSERT INTO mw_action_card_draft_narrow " + query)
        connection.execute('CHECKPOINT')
    return int(connection.execute("SELECT COUNT(*) FROM mw_action_card_draft_narrow").fetchone()[0])


def run(
    database_path: Path,
    output_path: Path | None = None,
    threads: int = 2,
    memory_limit: str = "2800MB",
    temp_directory: Path | None = None,
    merge_players_path: Path | None = None,
    source_manifest: Path | None = None,
    reuse_database: Path | None = None,
    reuse_report: dict | None = None,
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
    connection = TimedConnection(duckdb.connect(str(database_path)), temp_directory)
    try:
        connection.execute(f"PRAGMA threads = {max(1, int(threads))}")
        connection.execute("PRAGMA enable_progress_bar = false")
        connection.execute("PRAGMA preserve_insertion_order = false")
        spill_dir = temp_directory or database_path.parent / ".duckdb-spill"
        spill_dir.mkdir(parents=True, exist_ok=True)
        connection.spill_directory = spill_dir
        connection.execute("PRAGMA temp_directory = ?", [str(spill_dir)])
        connection.execute("PRAGMA memory_limit = ?", [memory_limit])
        for name in (*RETIRED_EVENT_RELATIONS, *VALIDATION_ONLY_RELATIONS):
            _drop_relation(connection, name)
        if merge_players_path is None:
            merge_players_path = Path(__file__).resolve().with_name("merge_players.csv")
        canonical_strategy = create_canonical_player_relations(connection, merge_players_path)
        players_metric_rows = create_players_metrics_relation(connection)
        log_dependency = log_dependency_signature(connection, source_manifest)
        reuse_decision = {}
        reused = reuse_log_relations(connection, reuse_database, reuse_report or {}, log_dependency,
                                    decision=reuse_decision)
        if reused is None:
            cards_pair_rows, combo_pair_rows = create_log_card_relations(connection)
        else:
            cards_pair_rows, combo_pair_rows = reused
        telemetry_condition = " AND ".join([
            f"COALESCE(TRY_CAST(f.{field} AS INTEGER) BETWEEN 0 AND 4, FALSE)"
            for field in (
                "Animals_Action_Card_Number", "Association_Action_Card_Number",
                "Build_Action_Card_Number", "Cards_Action_Card_Number",
                "Sponsors_Action_Card_Number",
            )
        ] + [
            f"COALESCE(REGEXP_MATCHES(TRIM(CAST(f.{field} AS VARCHAR)), "
            "'^(Animals|Association|Build|Cards|Sponsors) [1-4]$'), FALSE)"
            for field in (
                "First_drafted_action_card", "Second_drafted_action_card",
                "Third_drafted_action_card",
            )
        ])
        selection_count = " + ".join(
            f"CASE WHEN TRY_CAST(f.{field} AS INTEGER) BETWEEN 1 AND 4 THEN 1 ELSE 0 END"
            for field in (
                "Animals_Action_Card_Number", "Association_Action_Card_Number",
                "Build_Action_Card_Number", "Cards_Action_Card_Number",
                "Sponsors_Action_Card_Number",
            )
        )
        connection.execute("DROP TABLE IF EXISTS mw_action_card_eligible_tables_narrow")
        connection.execute(f"""
            CREATE TABLE mw_action_card_eligible_tables_narrow AS
            SELECT table_id
            FROM prepared_full_sample_narrow f
            WHERE f.is_mw = 1 AND NOT f.is_corrupted_game
            GROUP BY table_id
            HAVING COUNT(*) = 2 AND COUNT(DISTINCT player) = 2
              AND BOOL_AND({telemetry_condition})
              AND BOOL_AND(({selection_count}) = 2)
        """)
        connection.execute("DROP TABLE IF EXISTS mw_action_card_selection_narrow")
        connection.execute("DROP TABLE IF EXISTS mw_action_card_catalog_narrow")
        connection.execute("""
            CREATE TABLE mw_action_card_catalog_narrow(
              card_order INTEGER, card_type VARCHAR, card_number INTEGER,
              card_name VARCHAR, card_key VARCHAR
            )
        """)
        connection.executemany(
            "INSERT INTO mw_action_card_catalog_narrow VALUES (?, ?, ?, ?, ?)",
            [(order, card_type, number, name, f"{card_type} {number}")
             for order, card_type, number, name in MW_ACTION_CARDS],
        )
        selection_branches = []
        for order, (card_type, field) in enumerate((
            ("Animals", "Animals_Action_Card_Number"),
            ("Association", "Association_Action_Card_Number"),
            ("Build", "Build_Action_Card_Number"),
            ("Cards", "Cards_Action_Card_Number"),
            ("Sponsors", "Sponsors_Action_Card_Number"),
        ), 1):
            selection_branches.append(f"""
              SELECT f.table_id, f.player, f.player_identity, {order} AS type_order,
                '{card_type}' AS card_type, TRY_CAST(f.{field} AS INTEGER) AS card_number,
                f.elo_delta, f.pre_match_elo, f.opponent_pre_match_elo,
                f.Map AS map_name, f.game_ended_at, f.starting_position,
                f.is_completed_game, f.is_arena_game, f.arena_season,
                f.is_tournament,
                COALESCE(TRY_CAST(f.Upgraded_{card_type}_action_card AS BOOLEAN), FALSE) AS upgraded
              FROM prepared_full_sample_narrow f
              JOIN mw_action_card_eligible_tables_narrow eligible USING(table_id)
              WHERE TRY_CAST(f.{field} AS INTEGER) BETWEEN 1 AND 4
            """)
        connection.execute(
            "CREATE TABLE mw_action_card_selection_narrow AS SELECT "
            "s.* EXCLUDE(type_order), c.card_order, c.card_name, c.card_key "
            "FROM (" + " UNION ALL ".join(selection_branches) + ") s "
            "JOIN mw_action_card_catalog_narrow c "
            "ON c.card_type = s.card_type AND c.card_number = s.card_number"
        )
        create_mw_action_card_draft_relation(connection)
        connection.execute("DROP TABLE IF EXISTS mw_action_card_pair_narrow")
        connection.execute("""
            CREATE TABLE mw_action_card_pair_narrow AS
            SELECT a.table_id, a.player, a.player_identity,
              a.elo_delta, a.pre_match_elo, a.opponent_pre_match_elo,
              a.map_name, a.game_ended_at, a.starting_position,
              a.is_completed_game, a.is_arena_game, a.arena_season, a.is_tournament,
              a.card_order AS card_1_order, a.card_type AS card_1_type,
              a.card_number AS card_1_number, a.card_name AS card_1_name,
              a.card_key AS card_1_key,
              b.card_order AS card_2_order, b.card_type AS card_2_type,
              b.card_number AS card_2_number, b.card_name AS card_2_name,
              b.card_key AS card_2_key
            FROM mw_action_card_selection_narrow a
            JOIN mw_action_card_selection_narrow b
              ON b.table_id = a.table_id AND b.player = a.player
             AND a.card_order < b.card_order
        """)
        connection.execute("DROP TABLE IF EXISTS mw_action_card_same_map_tables_narrow")
        connection.execute("""
            CREATE TABLE mw_action_card_same_map_tables_narrow AS
            SELECT g.table_id
            FROM game_player_narrow g
            JOIN mw_action_card_eligible_tables_narrow e USING(table_id)
            GROUP BY g.table_id HAVING COUNT(DISTINCT g.map_name) = 1
              AND COUNT(g.map_name) = 2
        """)
        card_action_pair_rows = create_card_action_pair_filter_relation(connection)
        log_filter_rows = create_log_filter_relations(connection)
        fast_filter_rows = create_fast_filter_relations(connection)
        game_players = connection.execute(
            "SELECT COUNT(*) FROM game_player_narrow"
        ).fetchone()[0]
        tables = connection.execute(
            "SELECT COUNT(DISTINCT table_id) FROM game_player_narrow"
        ).fetchone()[0]
        prepared_rows = connection.execute(
            "SELECT COUNT(*) FROM prepared_full_sample_narrow"
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
        completed_tables = connection.execute(
            "SELECT COUNT(*) FROM completed_tables_narrow"
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
        card_filter_mw_rows = connection.execute(
            "SELECT COUNT(*) FROM card_filter_fact_mw_narrow"
        ).fetchone()[0]
        card_filter_base_rows = connection.execute(
            "SELECT COUNT(*) FROM card_filter_fact_base_narrow"
        ).fetchone()[0]
        card_filter_table_mw_rows = connection.execute(
            "SELECT COUNT(*) FROM card_filter_table_fact_mw_narrow"
        ).fetchone()[0]
        card_filter_table_base_rows = connection.execute(
            "SELECT COUNT(*) FROM card_filter_table_fact_base_narrow"
        ).fetchone()[0]
        players_by_identity_rows = connection.execute(
            "SELECT COUNT(*) FROM players_by_identity_narrow"
        ).fetchone()[0]
        players_default_cohort_rows = connection.execute(
            "SELECT COUNT(*) FROM players_default_cohorts_narrow"
        ).fetchone()[0]
        event_relation_rows = {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in (
                "card_play_event_narrow", "opening_hand_narrow",
                "endgame_score_event_narrow", "endgame_dealt_event_narrow",
                "project_reward_choice_narrow",
                "conservation_cp_player_narrow",
                "conservation_cp_opportunity_narrow",
                "mw_action_card_eligible_tables_narrow",
                "mw_action_card_catalog_narrow",
                "mw_action_card_selection_narrow",
                "mw_action_card_draft_narrow",
                "mw_action_card_pair_narrow",
                "mw_action_card_same_map_tables_narrow",
                "card_play_filter_fact_mw_narrow", "card_play_filter_fact_base_narrow",
                "card_catalog_narrow",
                "card_action_pair_filter_fact_narrow",
                "log_player_filter_fact_narrow", "endgame_score_filter_event_narrow",
                "sponsor_play_filter_event_narrow", "sponsor_endgame_filter_event_narrow",
            )
        }
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    report = {
        "status": "ok",
        "canonical_build_strategy": canonical_strategy,
        "database": str(database_path),
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "relations": {
            "game_player_narrow": {
                "rows": int(game_players),
                "distinct_tables": int(tables),
            },
            "prepared_full_sample_narrow": {
                "rows": int(prepared_rows),
                "materialized": True,
            },
            "card_play_narrow": {
                "rows": int(card_plays),
                "distinct_card_groups": int(card_groups),
            },
            "corrupted_tables_narrow": {
                "rows": int(corrupted_tables),
            },
            "completed_tables_narrow": {
                "rows": int(completed_tables),
            },
            "players_metrics_narrow": {
                "rows": int(players_metric_rows),
            },
            "players_by_identity_narrow": {
                "rows": int(players_by_identity_rows),
            },
            "players_default_cohorts_narrow": {
                "rows": int(players_default_cohort_rows),
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
            "card_filter_fact_mw_narrow": {
                "rows": int(card_filter_mw_rows),
            },
            "card_filter_fact_base_narrow": {
                "rows": int(card_filter_base_rows),
            },
            "card_filter_table_fact_mw_narrow": {
                "rows": int(card_filter_table_mw_rows),
            },
            "card_filter_table_fact_base_narrow": {
                "rows": int(card_filter_table_base_rows),
            },
            **{name: {"rows": rows} for name, rows in fast_filter_rows.items()},
            **{name: {"rows": rows, "schema_version": 2} for name, rows in cards_pair_rows.items()},
            **{name: {"rows": rows, "schema_version": 2} for name, rows in combo_pair_rows.items()},
            **{name: {"rows": rows} for name, rows in log_filter_rows.items()},
            **{name: {"rows": rows} for name, rows in event_relation_rows.items()},
        },
        "build_seconds": round(time.perf_counter() - started, 3),
        "statement_timings": connection.statements,
        "log_dependency": log_dependency,
        "reused_relations": list(LOG_RELATIONS) if reused is not None else [],
        "log_reuse_decision": reuse_decision,
        "parity_status": "canonical_population_and_event_grains_materialized",
    }
    if output_path:
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Detailed statement telemetry belongs in the private report, not thousands
    # of stdout lines that hide the useful worker diagnostics.
    print(json.dumps({key:value for key,value in report.items() if key != 'statement_timings'}, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="2800MB")
    parser.add_argument("--temp-directory", type=Path)
    parser.add_argument("--merge-players", type=Path)
    args = parser.parse_args(argv)
    return run(
        args.database_path,
        args.output,
        threads=args.threads,
        memory_limit=args.memory_limit,
        temp_directory=args.temp_directory,
        merge_players_path=args.merge_players,
    )


if __name__ == "__main__":
    sys.exit(main())
