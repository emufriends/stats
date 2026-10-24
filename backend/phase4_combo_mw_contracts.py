"""Exact local contracts for Combos and Marine Worlds action cards.

These routes deliberately derive every filtered population from immutable
player-game facts.  Compact default snapshots are an acceleration layer only;
they never define the statistical population. Synergy has no confidence
interval, while displayed standalone component means retain the
table-clustered ordinary-mean interval used by the dashboard.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from phase4_local_scope import MAP_CODE_TO_NAME, normalize_scope, scope_predicates
from phase3_cards_pair_contracts import paired_side_scope_sql


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
STANDARD_MAPS = tuple(list(MAP_CODE_TO_NAME.values())[:15])
EXCLUDED_PROJECTS = (
    "africa", "americas", "asia", "australia", "birds", "europe",
    "habitat diversity", "herbivores", "predators", "primates", "reptiles",
    "sea animals", "species diversity",
)

CARD_PAIR_TYPE_SQL = """
CASE
  WHEN p.type_1 = p.type_2 THEN
    UPPER(SUBSTR(p.type_1, 1, 1)) || SUBSTR(p.type_1, 2) || ' + ' ||
    UPPER(SUBSTR(p.type_2, 1, 1)) || SUBSTR(p.type_2, 2)
  WHEN (p.type_1 = 'animal' AND p.type_2 = 'project')
    OR (p.type_1 = 'project' AND p.type_2 = 'animal') THEN 'Animal + Project'
  WHEN (p.type_1 = 'animal' AND p.type_2 = 'sponsor')
    OR (p.type_1 = 'sponsor' AND p.type_2 = 'animal') THEN 'Animal + Sponsor'
  ELSE 'Project + Sponsor'
END
"""


def _quoted(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _round_clause(alias: str, rounds: Sequence[str]) -> str:
    if not rounds:
        return ""
    parts = []
    exact = [int(value) for value in rounds if str(value).isdigit()]
    if exact:
        parts.append(f"{alias}.played_round IN ({', '.join(map(str, exact))})")
    if "6+" in rounds:
        parts.append(f"{alias}.played_round >= 6")
    return " AND (" + " OR ".join(parts) + ")" if parts else ""


def _played_summary_round_clause(alias: str, rounds: Sequence[str]) -> str:
    """Filter the deduplicated per-card fact when any selected round matched."""

    if not rounds:
        return ""
    columns = {
        "1": "played_r1", "2": "played_r2", "3": "played_r3",
        "4": "played_r4", "5": "played_r5", "6+": "played_r6plus",
    }
    selected = [f"{alias}.{columns[str(value)]} > 0" for value in rounds if str(value) in columns]
    return " AND (" + " OR ".join(selected) + ")" if selected else ""


def _played_filter_cte(scope: Mapping[str, Any], *, compact: bool = False,
                       retain_round: bool = False) -> tuple[str, list[Any]]:
    """Use the refresh-built one-row-per-player-game/card serving fact.

    Pair routes must not reconstruct the deduplicated card population from raw
    log events on every request.  The selected dataset relation already carries
    all sidebar dimensions and excludes corrupted tables.
    """

    relation = "card_filter_fact_mw_narrow" if scope.get("is_mw") == 1 else "card_filter_fact_base_narrow"
    if compact:
        relation = relation.replace("card_filter_fact_", "card_play_filter_fact_")
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False, include_corrupted=True)
    round_clause = _played_summary_round_clause("g", scope.get("rounds") or [])
    excluded = ", ".join(_quoted(value) for value in EXCLUDED_PROJECTS)
    grain = ", g.played_rounds" if retain_round else ""
    encoded = ", g.card_id" if compact else ""
    if retain_round:
        round_clause = ""
    cte_name = "played_base" if retain_round else "played"
    expansion = f""", played AS (
      SELECT * FROM (
        SELECT b.* EXCLUDE(played_rounds), UNNEST(b.played_rounds) AS played_round
        FROM played_base b
      ) r WHERE TRUE {_round_clause('r', scope.get('rounds') or [])}
    )""" if retain_round else ""
    return f"""
    {cte_name} AS (
      SELECT g.table_id, g.player, g.card_name, g.card_type,
        g.Map AS map_name, g.elo_delta, g.pre_match_elo{encoded}{grain}
      FROM {relation} g
      WHERE {predicates}
        AND g.played_count > 0
        AND NOT (g.card_type = 'project' AND LOWER(g.card_name) IN ({excluded}))
        {round_clause}
    ){expansion}
    """, parameters


def _player_scope_cte(scope: Mapping[str, Any]) -> tuple[str, list[Any]]:
    """Thin canonical scope; metrics and log arrays are not needed for pairs."""
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False)
    predicates = predicates.replace("g.Map", "g.map_name")
    return f"""scoped_players AS (
      SELECT g.table_id, g.player, g.elo_delta, g.pre_match_elo, g.map_name
      FROM game_player_narrow g WHERE {predicates}
    )""", parameters


def _played_ctes(scope: Mapping[str, Any], *, retain_round: bool = False) -> tuple[str, list[Any]]:
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False)
    round_clause = _round_clause("cp", scope.get("rounds") or [])
    excluded = ", ".join(_quoted(value) for value in EXCLUDED_PROJECTS)
    grain = ", cp.played_round" if retain_round else ""
    return f"""
    scoped_players AS (
      SELECT g.table_id, g.player, g.elo_delta, g.pre_match_elo, g.Map AS map_name
      FROM prepared_full_sample_narrow g WHERE {predicates}
    ), played AS (
      SELECT DISTINCT p.table_id, p.player, cp.card_name, cp.card_type{grain},
        p.map_name, p.elo_delta, p.pre_match_elo
      FROM scoped_players p
      JOIN card_play_narrow cp USING(table_id, player)
      WHERE NOT (cp.card_type = 'project' AND LOWER(cp.card_name) IN ({excluded}))
        {round_clause}
    )
    """, parameters


def combination_sql(request: Mapping[str, Any], view: str) -> tuple[str, list[Any]]:
    """Return every candidate row; response projection applies local controls."""

    scope = normalize_scope(request)
    if view == "card_action_card":
        if scope.get("is_mw") != 1:
            raise ValueError("Card + Action Card is only available for Marine Worlds")
        if request.get('_card_action_pair_fact'):
            return _card_action_pair_fact_sql(scope)
        player_predicates, player_parameters = scope_predicates(scope, "g", hard_completed=False)
        if request.get("_combos_filter_fact"):
            # Current generations use the compact one-row-per-player-game/card
            # serving fact. The raw branch below keeps a validated rollback
            # generation executable without changing the public contract.
            played_cte, played_parameters = _played_filter_cte(
                scope, compact=bool(request.get("_combos_played_fact"))
            )
            cards_ctes = f"""{played_cte}, cards AS (
              SELECT p.* FROM played p
              JOIN mw_action_card_eligible_tables_narrow e USING(table_id)
            )"""
            parameters = player_parameters + played_parameters
        else:
            round_clause = _round_clause("cp", scope.get("rounds") or [])
            excluded = ", ".join(_quoted(value) for value in EXCLUDED_PROJECTS)
            cards_ctes = f"""cards AS (
              SELECT DISTINCT s.table_id, s.player, cp.card_name, cp.card_type,
                s.elo_delta, s.pre_match_elo
              FROM scoped_players s JOIN card_play_narrow cp USING(table_id, player)
              WHERE NOT (cp.card_type = 'project' AND LOWER(cp.card_name) IN ({excluded}))
                {round_clause}
            )"""
            parameters = player_parameters
        actions_cte = """actions AS (
          SELECT a.table_id, a.player, a.card_order AS action_card_order,
            a.card_key AS action_card_key, a.card_name AS action_card_name,
            a.card_type AS action_card_type, a.card_number AS action_card_number,
            s.elo_delta, s.pre_match_elo
          FROM mw_action_card_selection_narrow a
          JOIN scoped_players s USING(table_id, player)
        )"""
        scope_cte = f"""scoped_players AS (
          SELECT g.table_id, g.player, g.elo_delta, g.pre_match_elo
          FROM prepared_full_sample_narrow g
          JOIN mw_action_card_eligible_tables_narrow e USING(table_id)
          WHERE {player_predicates}
        )"""
        if request.get("_combos_played_fact"):
            action_where, action_parameters = _mw_selection_scope(scope, "a")
            scope_cte = "unused_scope AS (SELECT 1)"
            actions_cte = f"""actions AS (
              SELECT a.table_id, a.player, a.card_order AS action_card_order,
                a.card_key AS action_card_key, a.card_name AS action_card_name,
                a.card_type AS action_card_type, a.card_number AS action_card_number,
                a.elo_delta, a.pre_match_elo
              FROM mw_action_card_selection_narrow a WHERE {action_where}
            )"""
            parameters = played_parameters + action_parameters
        return f"""
        WITH {scope_cte}, {cards_ctes}, {actions_cte}, card_components AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type,
            AVG(elo_delta) AS delta_card
          FROM cards GROUP BY card_name
        ), action_components AS (
          SELECT action_card_key, AVG(elo_delta) AS delta_action
          FROM actions GROUP BY action_card_key
        ), pairs AS (
          SELECT c.card_name, ANY_VALUE(c.card_type) AS card_type,
            a.action_card_order, a.action_card_key,
            ANY_VALUE(a.action_card_name) AS action_card_name,
            ANY_VALUE(a.action_card_type) AS action_card_type,
            ANY_VALUE(a.action_card_number) AS action_card_number,
            AVG(c.elo_delta) AS delta_actual,
            STDDEV_SAMP(c.elo_delta) AS delta_actual_ci_sd,
            COUNT(c.elo_delta) AS delta_actual_ci_n,
            AVG(c.pre_match_elo) AS avg_elo, COUNT(*) AS n_played
          FROM cards c JOIN actions a USING(table_id, player)
          GROUP BY c.card_name, a.action_card_order, a.action_card_key
        )
        SELECT p.card_name, p.card_type, ROUND(c.delta_card, 3) AS delta_card,
          p.action_card_order, p.action_card_key, p.action_card_name,
          p.action_card_type, p.action_card_number,
          ROUND(a.delta_action, 3) AS delta_action,
          ROUND(c.delta_card + a.delta_action, 3) AS delta_combined,
          ROUND(p.delta_actual, 3) AS delta_actual,
          p.delta_actual AS delta_actual_ci_mean,
          p.delta_actual_ci_sd, p.delta_actual_ci_n,
          ROUND(p.delta_actual - c.delta_card - a.delta_action, 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo, p.n_played,
          UPPER(SUBSTR(p.card_type, 1, 1)) || SUBSTR(p.card_type, 2)
            || ' + ' || p.action_card_type AS pair_type
        FROM pairs p JOIN card_components c USING(card_name)
        JOIN action_components a USING(action_card_key)
        ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, action_card_order
        LIMIT ? OFFSET ?
        """, parameters

    if view == "card_card":
        if request.get('_combo_card_pair_fact'):
            return _card_card_pair_fact_sql(scope,
                paired_components=bool(request.get('_combo_card_component_pair_fact')))
        if request.get("_combos_filter_fact"):
            ctes, parameters = _played_filter_cte(
                scope, compact=bool(request.get("_combos_played_fact"))
            )
        else:
            # Compatibility path for generations that predate the compact
            # Combo serving facts.
            ctes, parameters = _played_ctes(scope)
        encoded = bool(request.get("_combos_played_fact"))
        pair_key_1 = "a.card_id" if encoded else "a.card_name"
        pair_key_2 = "b.card_id" if encoded else "b.card_name"
        pair_names = ("k1.card_name AS card_1, k1.card_type AS type_1, "
                      "k2.card_name AS card_2, k2.card_type AS type_2") if encoded else "p.*"
        catalog_join = ("JOIN card_catalog_narrow k1 ON k1.card_id = p.card_1 "
                        "JOIN card_catalog_narrow k2 ON k2.card_id = p.card_2") if encoded else ""
        return f"""
        WITH {ctes}, components AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type, AVG(elo_delta) AS delta
          FROM played GROUP BY card_name
        ), pair_moments AS (
          SELECT {pair_key_1} AS card_1,
            {pair_key_2} AS card_2,
            {"" if encoded else "ANY_VALUE(a.card_type) AS type_1, ANY_VALUE(b.card_type) AS type_2,"}
            AVG(a.elo_delta) AS delta_actual,
            STDDEV_SAMP(a.elo_delta) AS delta_actual_ci_sd,
            COUNT(a.elo_delta) AS delta_actual_ci_n,
            AVG(a.pre_match_elo) AS avg_elo, COUNT(*) AS n_played
          FROM played a JOIN played b
            ON b.table_id = a.table_id AND b.player = a.player
           AND {pair_key_1} < {pair_key_2}
          GROUP BY {pair_key_1}, {pair_key_2}
        ), pairs AS (
          SELECT {pair_names}{", p.* EXCLUDE(card_1, card_2)" if encoded else ""}
          FROM pair_moments p {catalog_join}
        )
        SELECT p.card_1, p.type_1, p.card_2, p.type_2,
          ROUND(c1.delta, 3) AS delta_1, ROUND(c2.delta, 3) AS delta_2,
          ROUND(c1.delta + c2.delta, 3) AS delta_combined,
          ROUND(p.delta_actual, 3) AS delta_actual,
          p.delta_actual AS delta_actual_ci_mean,
          p.delta_actual_ci_sd, p.delta_actual_ci_n,
          ROUND(p.delta_actual - c1.delta - c2.delta, 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo, p.n_played,
          {CARD_PAIR_TYPE_SQL} AS pair_type
        FROM pairs p JOIN components c1 ON c1.card_name = p.card_1
        JOIN components c2 ON c2.card_name = p.card_2
        ORDER BY interaction DESC NULLS LAST, n_played DESC, card_1, card_2
        LIMIT ? OFFSET ?
        """, parameters
    if request.get("_combos_played_fact"):
        ctes, parameters = _played_filter_cte(scope, compact=True, retain_round=view == "card_round")
        if view == "card_endgame":
            player_cte, player_parameters = _player_scope_cte(scope)
            ctes = player_cte + ", " + ctes
            parameters = player_parameters + parameters
    else:
        ctes, parameters = _played_ctes(scope, retain_round=view == "card_round")
    if view == "card_map":
        return f"""
        WITH {ctes}, components AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type, AVG(elo_delta) AS delta_general
          FROM played GROUP BY card_name
        ), contexts AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type, map_name,
            AVG(elo_delta) AS delta_map, STDDEV_SAMP(elo_delta) AS delta_map_ci_sd,
            COUNT(elo_delta) AS delta_map_ci_n, AVG(pre_match_elo) AS avg_elo,
            COUNT(*) AS n_played
          FROM played GROUP BY card_name, map_name
        )
        SELECT x.card_name, x.card_type, x.map_name,
          ROUND(c.delta_general, 3) AS delta_general,
          ROUND(x.delta_map, 3) AS delta_map,
          x.delta_map AS delta_map_ci_mean, x.delta_map_ci_sd, x.delta_map_ci_n,
          ROUND(x.delta_map - c.delta_general, 3) AS interaction,
          ROUND(x.avg_elo, 0) AS avg_elo, x.n_played
        FROM contexts x JOIN components c USING(card_name)
        ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, map_name
        LIMIT ? OFFSET ?
        """, parameters
    if view == "card_round":
        return f"""
        WITH {ctes}, distinct_cards AS (
          SELECT DISTINCT table_id, player, card_name, card_type, elo_delta, pre_match_elo
          FROM played
        ), components AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type, AVG(elo_delta) AS delta_general
          FROM distinct_cards GROUP BY card_name
        ), contexts AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type,
            CASE WHEN played_round >= 6 THEN '6+' ELSE CAST(played_round AS VARCHAR) END AS round_name,
            AVG(elo_delta) AS delta_round, STDDEV_SAMP(elo_delta) AS delta_round_ci_sd,
            COUNT(elo_delta) AS delta_round_ci_n, AVG(pre_match_elo) AS avg_elo,
            COUNT(*) AS n_played
          FROM played WHERE played_round IS NOT NULL GROUP BY card_name, round_name
        )
        SELECT x.card_name, x.card_type, x.round_name,
          ROUND(c.delta_general, 3) AS delta_general,
          ROUND(x.delta_round, 3) AS delta_round,
          x.delta_round AS delta_round_ci_mean, x.delta_round_ci_sd, x.delta_round_ci_n,
          ROUND(x.delta_round - c.delta_general, 3) AS interaction,
          ROUND(x.avg_elo, 0) AS avg_elo, x.n_played
        FROM contexts x JOIN components c USING(card_name)
        ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, round_name
        LIMIT ? OFFSET ?
        """, parameters
    if view == "card_endgame":
        return f"""
        WITH {ctes}, endgames AS (
          SELECT e.table_id, e.player, e.endgame_name, s.elo_delta
          FROM endgame_score_event_narrow e
          JOIN scoped_players s USING(table_id, player)
        ), card_components AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type, AVG(elo_delta) AS delta_card
          FROM played GROUP BY card_name
        ), endgame_components AS (
          SELECT endgame_name, AVG(elo_delta) AS delta_endgame
          FROM endgames GROUP BY endgame_name
        ), pairs AS (
          SELECT p.card_name, ANY_VALUE(p.card_type) AS card_type, e.endgame_name,
            AVG(p.elo_delta) AS delta_actual,
            STDDEV_SAMP(p.elo_delta) AS delta_actual_ci_sd,
            COUNT(p.elo_delta) AS delta_actual_ci_n,
            AVG(p.pre_match_elo) AS avg_elo, COUNT(*) AS n_played
          FROM played p JOIN endgames e USING(table_id, player)
          GROUP BY p.card_name, e.endgame_name
        )
        SELECT p.card_name, p.card_type, ROUND(c.delta_card, 3) AS delta_card,
          p.endgame_name, ROUND(e.delta_endgame, 3) AS delta_endgame,
          ROUND(c.delta_card + e.delta_endgame, 3) AS delta_combined,
          ROUND(p.delta_actual, 3) AS delta_actual,
          p.delta_actual AS delta_actual_ci_mean,
          p.delta_actual_ci_sd, p.delta_actual_ci_n,
          ROUND(p.delta_actual - c.delta_card - e.delta_endgame, 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo, p.n_played
        FROM pairs p JOIN card_components c USING(card_name)
        JOIN endgame_components e USING(endgame_name)
        ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, endgame_name
        LIMIT ? OFFSET ?
        """, parameters
    raise ValueError(f"unknown combinations view: {view}")


def _card_card_pair_fact_sql(scope: Mapping[str, Any], *,
                             paired_components: bool = False) -> tuple[str, list[Any]]:
    suffix = 'mw' if scope.get('is_mw') == 1 else 'base'
    sides, side_parameters = paired_side_scope_sql(scope)
    played_cte, played_parameters = _played_filter_cte(scope, compact=True)
    bits = {'1':1, '2':2, '3':4, '4':8, '5':16, '6+':32}
    mask = sum(bits[r] for r in scope.get('rounds') or [])
    round_where = f'AND (p.round_mask_1 & {mask})>0 AND (p.round_mask_2 & {mask})>0' if mask else ''
    excluded = ', '.join(_quoted(value) for value in EXCLUDED_PROJECTS)
    component_ctes = f'''{played_cte}, components AS (
      SELECT card_id, AVG(elo_delta) AS delta FROM played GROUP BY card_id
    ), sides AS ({sides})'''
    parameters = [*played_parameters, *side_parameters]
    if paired_components:
        # A component counts one played player-game/card, not every repeated
        # log round. Share the filtered numeric player sides with pair moments
        # instead of rescanning wide per-card filter dimensions and strings.
        # Side-specific round presence retains asymmetric and FPA eligibility;
        # the two cards can match different rounds in a multi-round selection.
        columns = {'1': 'played_r1', '2': 'played_r2', '3': 'played_r3',
                   '4': 'played_r4', '5': 'played_r5', '6+': 'played_r6plus'}
        presence = [' + '.join(f'f.{columns[r]}_{side}' for r in scope.get('rounds') or [])
                    or f'f.played_count_{side}' for side in (0, 1)]
        component_ctes = f'''sides AS MATERIALIZED ({sides}), components AS (
          SELECT f.card_id, AVG(s.elo_delta) AS delta
          FROM cards_pair_fact_{suffix}_narrow f JOIN sides s
            ON f.table_key = s.player_key // 2
          WHERE (s.side=0 AND ({presence[0]})>0)
             OR (s.side=1 AND ({presence[1]})>0)
          GROUP BY f.card_id
        )'''
        parameters = side_parameters
    return f'''WITH {component_ctes}, pair_moments AS (
      SELECT p.card_1, p.card_2, AVG(s.elo_delta) AS delta_actual,
        STDDEV_SAMP(s.elo_delta) AS delta_actual_ci_sd,
        COUNT(s.elo_delta) AS delta_actual_ci_n,
        AVG(s.pre_match_elo) AS avg_elo, COUNT(*) AS n_played
      FROM combo_card_pair_fact_{suffix}_narrow p JOIN sides s USING(player_key)
      WHERE TRUE {round_where} GROUP BY p.card_1,p.card_2
    ), pairs AS (
      SELECT k1.card_name AS card_1, k1.card_type AS type_1,
        k2.card_name AS card_2, k2.card_type AS type_2,
        p.* EXCLUDE(card_1,card_2), c1.delta AS delta_1, c2.delta AS delta_2
      FROM pair_moments p JOIN card_catalog_narrow k1 ON k1.card_id=p.card_1
      JOIN card_catalog_narrow k2 ON k2.card_id=p.card_2
      JOIN components c1 ON c1.card_id=p.card_1 JOIN components c2 ON c2.card_id=p.card_2
      WHERE NOT (k1.card_type='project' AND LOWER(k1.card_name) IN ({excluded}))
        AND NOT (k2.card_type='project' AND LOWER(k2.card_name) IN ({excluded}))
    ) SELECT p.card_1,p.type_1,p.card_2,p.type_2,
      ROUND(p.delta_1,3) AS delta_1, ROUND(p.delta_2,3) AS delta_2,
      ROUND(p.delta_1+p.delta_2,3) AS delta_combined,
      ROUND(p.delta_actual,3) AS delta_actual, p.delta_actual AS delta_actual_ci_mean,
      p.delta_actual_ci_sd,p.delta_actual_ci_n,
      ROUND(p.delta_actual-p.delta_1-p.delta_2,3) AS interaction,
      ROUND(p.avg_elo,0) AS avg_elo,p.n_played,{CARD_PAIR_TYPE_SQL} AS pair_type
      FROM pairs p ORDER BY interaction DESC NULLS LAST,n_played DESC,card_1,card_2
      LIMIT ? OFFSET ?''', parameters


def _card_action_pair_fact_sql(scope: Mapping[str, Any]) -> tuple[str, list[Any]]:
    """Aggregate refresh-expanded numeric pairs; do not rebuild a big join."""
    pair_where, pair_parameters = scope_predicates(scope, 'p', include_corrupted=True)
    action_where, action_parameters = _mw_selection_scope(scope, 'a')
    round_where = _played_summary_round_clause('p', scope.get('rounds') or [])
    excluded = ', '.join(_quoted(value) for value in EXCLUDED_PROJECTS)
    return f"""WITH pair_moments AS MATERIALIZED (
      SELECT p.card_id, p.action_card_order, AVG(p.elo_delta) AS delta_actual,
        STDDEV_SAMP(p.elo_delta) AS delta_actual_ci_sd,
        COUNT(p.elo_delta) AS delta_actual_ci_n,
        AVG(p.pre_match_elo) AS avg_elo, COUNT(*) AS n_played
      FROM card_action_pair_filter_fact_narrow p
      WHERE {pair_where} {round_where}
      GROUP BY p.card_id, p.action_card_order
    ), card_components AS (
      SELECT card_id, SUM(delta_actual * delta_actual_ci_n)
        / NULLIF(SUM(delta_actual_ci_n), 0) AS delta_card
      FROM pair_moments GROUP BY card_id
    ), action_components AS (
      SELECT a.card_order AS action_card_order, AVG(a.elo_delta) AS delta_action
      FROM mw_action_card_selection_narrow a WHERE {action_where}
      GROUP BY a.card_order
    )
    SELECT c.card_name, c.card_type, ROUND(b.delta_card, 3) AS delta_card,
      p.action_card_order, a.card_key AS action_card_key,
      a.card_name AS action_card_name, a.card_type AS action_card_type,
      a.card_number AS action_card_number,
      ROUND(d.delta_action, 3) AS delta_action,
      ROUND(b.delta_card + d.delta_action, 3) AS delta_combined,
      ROUND(p.delta_actual, 3) AS delta_actual,
      p.delta_actual AS delta_actual_ci_mean,
      p.delta_actual_ci_sd, p.delta_actual_ci_n,
      ROUND(p.delta_actual - b.delta_card - d.delta_action, 3) AS interaction,
      ROUND(p.avg_elo, 0) AS avg_elo, p.n_played,
      UPPER(SUBSTR(c.card_type, 1, 1)) || SUBSTR(c.card_type, 2)
        || ' + ' || a.card_type AS pair_type
    FROM pair_moments p JOIN card_components b USING(card_id)
    JOIN action_components d USING(action_card_order)
    JOIN card_catalog_narrow c USING(card_id)
    JOIN mw_action_card_catalog_narrow a ON a.card_order = p.action_card_order
    WHERE NOT (c.card_type = 'project' AND LOWER(c.card_name) IN ({excluded}))
    ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, action_card_order
    LIMIT ? OFFSET ?""", pair_parameters + action_parameters


def _draft_scope(scope: Mapping[str, Any]) -> tuple[str, list[Any]]:
    clauses = ["TRUE"]
    parameters: list[Any] = []
    maps = scope.get("maps") or []
    if maps:
        marks = ", ".join("?" for _ in maps)
        clauses.extend([f"d.first_map IN ({marks})", f"d.second_map IN ({marks})"])
        parameters.extend(maps)
        parameters.extend(maps)
    player_bounds = (("player_elo_min", ">="), ("player_elo_max", "<="))
    opponent_bounds = (("opponent_elo_min", ">="), ("opponent_elo_max", "<="))
    def orientation(player_col: str, opponent_col: str) -> tuple[str, list[Any]]:
        local, values = [], []
        for key, operator in player_bounds:
            if scope.get(key) is not None:
                local.append(f"{player_col} {operator} ?")
                values.append(scope[key])
        for key, operator in opponent_bounds:
            if scope.get(key) is not None:
                local.append(f"{opponent_col} {operator} ?")
                values.append(scope[key])
        return " AND ".join(local) or "TRUE", values
    first_sql, first_values = orientation("d.first_pre_match_elo", "d.second_pre_match_elo")
    second_sql, second_values = orientation("d.second_pre_match_elo", "d.first_pre_match_elo")
    positions = scope.get("starting_positions") or []
    if positions == ["First player"]:
        clauses.append(f"({first_sql})"); parameters.extend(first_values)
    elif positions == ["Second player"]:
        clauses.append(f"({second_sql})"); parameters.extend(second_values)
    else:
        clauses.append(f"(({first_sql}) OR ({second_sql}))")
        parameters.extend(first_values); parameters.extend(second_values)
    if scope.get("date_from"):
        clauses.append("CAST(d.game_ended_at AS DATE) >= CAST(? AS DATE)")
        parameters.append(scope["date_from"])
    if scope.get("date_to"):
        clauses.append("CAST(d.game_ended_at AS DATE) <= CAST(? AS DATE)")
        parameters.append(scope["date_to"])
    if scope.get("completed_only") is True:
        clauses.append("d.is_completed_game")
    if scope.get("arena_seasons"):
        marks = ", ".join("?" for _ in scope["arena_seasons"])
        clauses.append(f"d.arena_season IN ({marks})")
        parameters.extend(scope["arena_seasons"])
    elif scope.get("arena_only"):
        clauses.append("d.is_arena_game")
    if scope.get("tournament_only"):
        clauses.append("d.is_tournament")
    return " AND ".join(clauses), parameters


def _mw_selection_scope(scope: Mapping[str, Any], alias: str) -> tuple[str, list[Any]]:
    """Selection/pair facts already enforce telemetry and corruption eligibility."""
    prepared_scope = dict(scope)
    prepared_scope["is_mw"] = None
    where, parameters = scope_predicates(
        prepared_scope, alias, hard_completed=False, include_corrupted=True
    )
    return where.replace(f"{alias}.Map", f"{alias}.map_name") or "TRUE", parameters


def mw_action_cards_sql(request: Mapping[str, Any], view: str) -> tuple[str, list[Any]]:
    scoped_request = dict(request); scoped_request["is_mw"] = 1
    scope = normalize_scope(scoped_request)
    if view in {"general", "draft"}:
        predicates, player_params = scope_predicates(scope, "f", hard_completed=False)
        if request.get("_mw_filter_facts"):
            selection_where, player_params = _mw_selection_scope(scope, "s")
            selected_cte = f"""selected AS (
              SELECT s.* FROM mw_action_card_selection_narrow s WHERE {selection_where}
            )"""
        else:
            selected_cte = f"""scoped_players AS (
              SELECT f.table_id, f.player FROM prepared_full_sample_narrow f
              JOIN mw_action_card_eligible_tables_narrow e USING(table_id)
              WHERE {predicates}
            ), selected AS (
              SELECT s.* FROM mw_action_card_selection_narrow s
              JOIN scoped_players p USING(table_id, player)
            )"""
        draft_where, draft_params = _draft_scope(scope)
        return f"""
        WITH {selected_cte}, player_stats AS (
          SELECT card_key,
            AVG(elo_delta) AS delta_picked, STDDEV_SAMP(elo_delta) AS delta_picked_ci_sd,
            COUNT(elo_delta) AS delta_picked_ci_n,
            AVG(elo_delta) FILTER (WHERE upgraded) AS delta_picked_upgraded,
            STDDEV_SAMP(elo_delta) FILTER (WHERE upgraded) AS delta_picked_upgraded_ci_sd,
            COUNT(elo_delta) FILTER (WHERE upgraded) AS delta_picked_upgraded_ci_n,
            AVG(elo_delta) FILTER (WHERE NOT upgraded) AS delta_picked_basic,
            STDDEV_SAMP(elo_delta) FILTER (WHERE NOT upgraded) AS delta_picked_basic_ci_sd,
            COUNT(elo_delta) FILTER (WHERE NOT upgraded) AS delta_picked_basic_ci_n,
            AVG(pre_match_elo) AS elo_picked
          FROM selected GROUP BY card_key
        ), filtered_drafts AS (
          SELECT * FROM mw_action_card_draft_narrow d WHERE {draft_where}
        ), draft_stats AS (
          SELECT card_key, COUNT(*) AS available_n,
            COUNT(*) FILTER (WHERE picked) AS picked_n,
            COUNT(*) FILTER (WHERE drafted_first) AS drafted_first_n,
            COUNT(*) FILTER (WHERE drafted_second) AS drafted_second_n,
            COUNT(*) FILTER (WHERE undrafted) AS undrafted_n
          FROM filtered_drafts GROUP BY card_key
        )
        SELECT c.card_order, c.card_type AS type, c.card_type, c.card_number, c.card_name,
          ROUND(p.delta_picked, 3) AS delta_picked,
          p.delta_picked AS delta_picked_ci_mean, p.delta_picked_ci_sd,
          COALESCE(p.delta_picked_ci_n, 0) AS delta_picked_ci_n,
          ROUND(p.delta_picked_upgraded, 3) AS delta_picked_upgraded,
          p.delta_picked_upgraded AS delta_picked_upgraded_ci_mean,
          p.delta_picked_upgraded_ci_sd, COALESCE(p.delta_picked_upgraded_ci_n, 0) AS delta_picked_upgraded_ci_n,
          ROUND(p.delta_picked_basic, 3) AS delta_picked_basic,
          p.delta_picked_basic AS delta_picked_basic_ci_mean,
          p.delta_picked_basic_ci_sd, COALESCE(p.delta_picked_basic_ci_n, 0) AS delta_picked_basic_ci_n,
          ROUND(p.elo_picked, 0) AS elo_picked,
          COALESCE(d.available_n, 0) AS available_n, COALESCE(d.picked_n, 0) AS picked_n,
          ROUND(100.0 * d.picked_n / NULLIF(d.available_n, 0), 4) AS picked_pct,
          COALESCE(d.drafted_first_n, 0) AS drafted_first_n,
          ROUND(100.0 * d.drafted_first_n / NULLIF(d.available_n, 0), 4) AS drafted_first_pct,
          COALESCE(d.drafted_second_n, 0) AS drafted_second_n,
          ROUND(100.0 * d.drafted_second_n / NULLIF(d.available_n, 0), 4) AS drafted_second_pct,
          COALESCE(d.undrafted_n, 0) AS undrafted_n,
          ROUND(100.0 * d.undrafted_n / NULLIF(d.available_n, 0), 4) AS undrafted_pct
        FROM mw_action_card_catalog_narrow c
        LEFT JOIN player_stats p USING(card_key) LEFT JOIN draft_stats d USING(card_key)
        ORDER BY c.card_order LIMIT ? OFFSET ?
        """, player_params + draft_params
    if view == "by_map":
        no_maps = dict(scoped_request); no_maps["maps"] = []
        map_scope = normalize_scope(no_maps)
        predicates, parameters = scope_predicates(map_scope, "f", hard_completed=False)
        if request.get("_mw_filter_facts"):
            selection_where, parameters = _mw_selection_scope(map_scope, "s")
            same_map_sql = f"""
              SELECT s.*, s.map_name AS Map
              FROM mw_action_card_selection_narrow s
              JOIN mw_action_card_same_map_tables_narrow e USING(table_id)
              WHERE {selection_where}
                AND s.map_name IN ({', '.join(_quoted(value) for value in STANDARD_MAPS)})
            """
        else:
            same_map_sql = f"""
              SELECT s.*, f.Map FROM prepared_full_sample_narrow f
              JOIN prepared_full_sample_narrow o ON o.table_id = f.table_id AND o.player <> f.player
              JOIN mw_action_card_eligible_tables_narrow e ON e.table_id = f.table_id
              JOIN mw_action_card_selection_narrow s
                ON s.table_id = f.table_id AND s.player = f.player
              WHERE {predicates} AND f.Map = o.Map
                AND f.Map IN ({', '.join(_quoted(value) for value in STANDARD_MAPS)})
            """
        map_cols = []
        for index, full_name in enumerate(STANDARD_MAPS):
            code = list(MAP_CODE_TO_NAME.keys())[index].lower()
            key = f"map_{code}"
            name = _quoted(full_name)
            map_cols.extend([
                f"ROUND(AVG(s.elo_delta) FILTER (WHERE s.Map = {name}), 3) AS {key}",
                f"AVG(s.elo_delta) FILTER (WHERE s.Map = {name}) AS {key}_ci_mean",
                f"STDDEV_SAMP(s.elo_delta) FILTER (WHERE s.Map = {name}) AS {key}_ci_sd",
                f"COUNT(s.elo_delta) FILTER (WHERE s.Map = {name}) AS {key}_ci_n",
            ])
        return f"""
        WITH same_map AS ({same_map_sql}), stats AS (
          SELECT s.card_key, AVG(s.elo_delta) AS delta_overall,
            STDDEV_SAMP(s.elo_delta) AS delta_overall_ci_sd,
            COUNT(s.elo_delta) AS delta_overall_ci_n,
            {', '.join(map_cols)}
          FROM same_map s
          GROUP BY s.card_key
        )
        SELECT c.card_order, c.card_type AS type, c.card_type, c.card_number, c.card_name,
          {', '.join(f's.{part.split(" AS ")[-1]}' for part in map_cols)},
          ROUND(s.delta_overall, 3) AS delta_overall,
          s.delta_overall AS delta_overall_ci_mean, s.delta_overall_ci_sd,
          COALESCE(s.delta_overall_ci_n, 0) AS delta_overall_ci_n
        FROM mw_action_card_catalog_narrow c LEFT JOIN stats s USING(card_key)
        ORDER BY c.card_order LIMIT ? OFFSET ?
        """, parameters
    if view == "synergies":
        predicates, parameters = scope_predicates(scope, "f", hard_completed=False)
        if request.get("_mw_filter_facts"):
            selection_where, selection_params = _mw_selection_scope(scope, "s")
            pair_where, pair_params = _mw_selection_scope(scope, "p")
            parameters = selection_params + pair_params
            selected_cte = f"""selected AS (
              SELECT s.* FROM mw_action_card_selection_narrow s WHERE {selection_where}
            )"""
            pair_population = f"FROM mw_action_card_pair_narrow p WHERE {pair_where}"
        else:
            selected_cte = f"""scoped_players AS (
              SELECT f.table_id, f.player FROM prepared_full_sample_narrow f
              JOIN mw_action_card_eligible_tables_narrow e USING(table_id)
              WHERE {predicates}
            ), selected AS (
              SELECT s.* FROM mw_action_card_selection_narrow s
              JOIN scoped_players p USING(table_id, player)
            )"""
            pair_population = "FROM mw_action_card_pair_narrow p JOIN scoped_players s USING(table_id, player)"
        return f"""
        WITH {selected_cte}, components AS (
          SELECT card_key, AVG(elo_delta) AS delta FROM selected GROUP BY card_key
        ), pairs AS (
          SELECT p.card_1_order, p.card_1_key, p.card_1_type, p.card_1_number, p.card_1_name,
            p.card_2_order, p.card_2_key, p.card_2_type, p.card_2_number, p.card_2_name,
            AVG(p.elo_delta) AS delta_actual, STDDEV_SAMP(p.elo_delta) AS delta_actual_ci_sd,
            COUNT(p.elo_delta) AS delta_actual_ci_n, AVG(p.pre_match_elo) AS avg_elo,
            COUNT(*) AS n_picked
          {pair_population}
          GROUP BY p.card_1_order, p.card_1_key, p.card_1_type, p.card_1_number, p.card_1_name,
            p.card_2_order, p.card_2_key, p.card_2_type, p.card_2_number, p.card_2_name
        )
        SELECT p.*, ROUND(c1.delta, 3) AS delta_1, ROUND(c2.delta, 3) AS delta_2,
          ROUND(c1.delta + c2.delta, 3) AS delta_combined,
          ROUND(p.delta_actual, 3) AS delta_actual,
          p.delta_actual AS delta_actual_ci_mean, p.delta_actual_ci_sd, p.delta_actual_ci_n,
          ROUND(p.delta_actual - c1.delta - c2.delta, 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo,
          p.card_1_type || ' + ' || p.card_2_type AS pair_type
        FROM pairs p JOIN components c1 ON c1.card_key = p.card_1_key
        JOIN components c2 ON c2.card_key = p.card_2_key
        ORDER BY interaction DESC NULLS LAST, n_picked DESC, card_1_order, card_2_order
        LIMIT ? OFFSET ?
        """, parameters
    raise ValueError(f"unknown MW Action Cards view: {view}")


def component_row_key(stats_page: str, view: str, row: Mapping[str, Any]) -> str:
    if stats_page == "mw_action_cards": values = [row.get("card_1_key"), row.get("card_2_key")]
    elif view == "card_card": values = [row.get("card_1"), row.get("card_2")]
    elif view == "card_map": values = [row.get("card_name"), row.get("map_name")]
    elif view == "card_round": values = [row.get("card_name"), row.get("round_name")]
    elif view == "card_endgame": values = [row.get("card_name"), row.get("endgame_name")]
    elif view == "card_action_card": values = [row.get("card_name"), row.get("action_card_key")]
    else: raise ValueError("component confidence intervals are unavailable for this view")
    if any(value is None or not str(value).strip() for value in values):
        raise ValueError("component confidence interval row is missing its identifier")
    return json.dumps([str(value).strip() for value in values], ensure_ascii=False, separators=(",", ":"))


def component_ci_sql(
    request: Mapping[str, Any], stats_page: str, view: str, rows: Sequence[Mapping[str, Any]],
) -> tuple[str, list[Any]]:
    """Build table-clustered ordinary-mean intervals for visible components."""
    if len(rows) > 100: raise ValueError("component_ci_rows may contain at most 100 rows")
    unique: list[tuple[str, Mapping[str, Any]]] = []
    seen = set()
    for row in rows:
        if not isinstance(row, Mapping): raise ValueError("component_ci_rows items must be objects")
        key = component_row_key(stats_page, view, row)
        if key not in seen: seen.add(key); unique.append((key, row))
    if not unique:
        return "SELECT NULL AS row_key WHERE FALSE LIMIT ? OFFSET ?", []
    values_sql = ", ".join("(" + ", ".join("?" for _ in range(7)) + ")" for _ in unique)
    value_params: list[Any] = []
    for key, row in unique:
        value_params.extend([key, row.get("card_1"), row.get("card_2"), row.get("card_name"),
                             row.get("map_name") or row.get("round_name") or row.get("endgame_name"),
                             row.get("action_card_key"), row.get("card_1_key") or row.get("card_2_key")])
    # Pair keys need two independent MW columns; use the generic card columns.
    if stats_page == "mw_action_cards":
        value_params = []
        for key, row in unique:
            value_params.extend([key, row.get("card_1_key"), row.get("card_2_key"), None, None, None, None])
    scoped = dict(request); scoped["is_mw"] = 1 if stats_page == "mw_action_cards" or view == "card_action_card" else request.get("is_mw")
    scope = normalize_scope(scoped)
    predicates, scope_params = scope_predicates(scope, "g", hard_completed=False)
    round_clause = _round_clause("cp", scope.get("rounds") or [])
    excluded = ", ".join(_quoted(value) for value in EXCLUDED_PROJECTS)
    common = f"""
    request_rows(row_key, first_key, second_key, card_name, context_key, action_key, spare_key) AS (VALUES {values_sql}),
    scoped_players AS (
      SELECT g.table_id, g.player, g.elo_delta, g.pre_match_elo, g.Map AS map_name
      FROM prepared_full_sample_narrow g
      {'JOIN mw_action_card_eligible_tables_narrow e USING(table_id)' if stats_page == 'mw_action_cards' or view == 'card_action_card' else ''}
      WHERE {predicates}
    ), played_events AS (
      SELECT DISTINCT s.table_id, s.player, cp.card_name, cp.card_type, cp.played_round,
        s.map_name, s.elo_delta
      FROM scoped_players s JOIN card_play_narrow cp USING(table_id, player)
      WHERE NOT (cp.card_type = 'project' AND LOWER(cp.card_name) IN ({excluded})){round_clause}
    ), played AS (
      SELECT DISTINCT table_id, player, card_name, card_type, map_name, elo_delta FROM played_events
    )
    """
    if stats_page == "mw_action_cards":
        raw = """
        SELECT r.row_key, 'first' AS component, s.table_id, COUNT(s.elo_delta) AS n, SUM(s.elo_delta) AS value_sum
        FROM request_rows r JOIN mw_action_card_selection_narrow s ON s.card_key = r.first_key
        JOIN scoped_players p USING(table_id, player) GROUP BY r.row_key, s.table_id
        UNION ALL
        SELECT r.row_key, 'second', s.table_id, COUNT(s.elo_delta), SUM(s.elo_delta)
        FROM request_rows r JOIN mw_action_card_selection_narrow s ON s.card_key = r.second_key
        JOIN scoped_players p USING(table_id, player) GROUP BY r.row_key, s.table_id
        """
    elif view == "card_card":
        raw = """
        SELECT r.row_key, 'first' AS component, p.table_id, COUNT(p.elo_delta) AS n, SUM(p.elo_delta) AS value_sum
        FROM request_rows r JOIN played p ON p.card_name = r.first_key GROUP BY r.row_key, p.table_id
        UNION ALL SELECT r.row_key, 'second', p.table_id, COUNT(p.elo_delta), SUM(p.elo_delta)
        FROM request_rows r JOIN played p ON p.card_name = r.second_key GROUP BY r.row_key, p.table_id
        """
    elif view == "card_map":
        raw = """
        SELECT r.row_key, 'first' AS component, p.table_id, COUNT(p.elo_delta), SUM(p.elo_delta)
        FROM request_rows r JOIN played p ON p.card_name = r.card_name GROUP BY r.row_key, p.table_id
        UNION ALL SELECT r.row_key, 'second', p.table_id, COUNT(p.elo_delta), SUM(p.elo_delta)
        FROM request_rows r JOIN played p ON p.card_name = r.card_name AND p.map_name = r.context_key
        GROUP BY r.row_key, p.table_id
        """
    elif view == "card_round":
        raw = """
        SELECT r.row_key, 'first' AS component, p.table_id, COUNT(p.elo_delta), SUM(p.elo_delta)
        FROM request_rows r JOIN played p ON p.card_name = r.card_name GROUP BY r.row_key, p.table_id
        UNION ALL SELECT r.row_key, 'second', p.table_id, COUNT(p.elo_delta), SUM(p.elo_delta)
        FROM request_rows r JOIN played_events p ON p.card_name = r.card_name
          AND (CASE WHEN p.played_round >= 6 THEN '6+' ELSE CAST(p.played_round AS VARCHAR) END) = r.context_key
        GROUP BY r.row_key, p.table_id
        """
    elif view == "card_endgame":
        raw = """
        SELECT r.row_key, 'first' AS component, p.table_id, COUNT(p.elo_delta), SUM(p.elo_delta)
        FROM request_rows r JOIN played p ON p.card_name = r.card_name GROUP BY r.row_key, p.table_id
        UNION ALL SELECT r.row_key, 'second', e.table_id, COUNT(s.elo_delta), SUM(s.elo_delta)
        FROM request_rows r JOIN endgame_score_event_narrow e ON e.endgame_name = r.context_key
        JOIN scoped_players s USING(table_id, player) GROUP BY r.row_key, e.table_id
        """
    elif view == "card_action_card":
        raw = """
        SELECT r.row_key, 'first' AS component, p.table_id, COUNT(p.elo_delta), SUM(p.elo_delta)
        FROM request_rows r JOIN played p ON p.card_name = r.card_name GROUP BY r.row_key, p.table_id
        UNION ALL SELECT r.row_key, 'second', a.table_id, COUNT(a.elo_delta), SUM(a.elo_delta)
        FROM request_rows r JOIN mw_action_card_selection_narrow a ON a.card_key = r.action_key
        JOIN scoped_players s USING(table_id, player) GROUP BY r.row_key, a.table_id
        """
    else: raise ValueError("component confidence intervals are unavailable for this view")
    # Standalone component populations do not depend on their paired row. A
    # hundred cards sharing one action card must not produce a hundred copies
    # of that action card's table-level observations. Representatives preserve
    # the original component grain; expand only the tiny final statistics.
    if stats_page == 'mw_action_cards' or view == 'card_card':
        first_keys, second_keys = ['first_key'], ['second_key']
    else:
        first_keys = ['card_name']
        second_keys = (['card_name', 'context_key'] if view in {'card_map', 'card_round'}
                       else ['context_key'] if view == 'card_endgame' else ['action_key'])
    representatives = []
    joins = []
    for role, keys in (('first', first_keys), ('second', second_keys)):
        columns = ', '.join(keys)
        representatives.append(f'''{role}_requests AS (
            SELECT MIN(row_key) AS row_key, {columns}
            FROM request_rows GROUP BY {columns})''')
        joins.append(f"LEFT JOIN {role}_requests {role} ON " + ' AND '.join(
            f'{role}.{key} IS NOT DISTINCT FROM q.{key}' for key in keys))
    first_raw, second_raw = raw.split('UNION ALL', 1)
    raw = (first_raw.replace('FROM request_rows r', 'FROM first_requests r')
           + ' UNION ALL ' + second_raw.replace('FROM request_rows r', 'FROM second_requests r'))
    common += ', ' + ', '.join(representatives) + f''', request_mapping AS (
        SELECT q.row_key, first.row_key AS first_row_key, second.row_key AS second_row_key
        FROM request_rows q {' '.join(joins)})'''
    query = f"""
    WITH {common}, raw(row_key, component, table_id, n, value_sum) AS ({raw}), means AS (
      SELECT row_key, component, SUM(n) AS total_n, SUM(value_sum) / NULLIF(SUM(n), 0) AS mean
      FROM raw WHERE n > 0 GROUP BY row_key, component
    ), stats AS (
      SELECT m.row_key, m.component, m.total_n, m.mean, COUNT(r.table_id) AS cluster_n,
        CASE WHEN COUNT(r.table_id) >= 2 THEN SQRT(
          COUNT(r.table_id) * 1.0 / (COUNT(r.table_id) - 1)
          * SUM(POW((r.value_sum - r.n * m.mean) / m.total_n, 2))
        ) END AS se
      FROM means m JOIN raw r USING(row_key, component)
      WHERE r.n > 0
      GROUP BY m.row_key, m.component, m.total_n, m.mean
    ), expanded_stats AS (
      SELECT q.row_key, s.* EXCLUDE(row_key)
      FROM request_mapping q JOIN stats s ON s.row_key = q.first_row_key
      WHERE s.component = 'first'
      UNION ALL
      SELECT q.row_key, s.* EXCLUDE(row_key)
      FROM request_mapping q JOIN stats s ON s.row_key = q.second_row_key
      WHERE s.component = 'second'
    )
    SELECT q.row_key,
      MAX(s.mean) FILTER (WHERE component = 'first') AS component_1_mean,
      MAX(s.mean - 1.96 * s.se) FILTER (WHERE component = 'first' AND cluster_n >= 2) AS component_1_ci95_low,
      MAX(s.mean + 1.96 * s.se) FILTER (WHERE component = 'first' AND cluster_n >= 2) AS component_1_ci95_high,
      MAX(s.se) FILTER (WHERE component = 'first') AS component_1_ci95_se,
      COALESCE(MAX(s.total_n) FILTER (WHERE component = 'first'), 0) AS component_1_ci95_n,
      COALESCE(MAX(s.cluster_n) FILTER (WHERE component = 'first'), 0) AS component_1_ci95_cluster_n,
      MAX(s.mean) FILTER (WHERE component = 'second') AS component_2_mean,
      MAX(s.mean - 1.96 * s.se) FILTER (WHERE component = 'second' AND cluster_n >= 2) AS component_2_ci95_low,
      MAX(s.mean + 1.96 * s.se) FILTER (WHERE component = 'second' AND cluster_n >= 2) AS component_2_ci95_high,
      MAX(s.se) FILTER (WHERE component = 'second') AS component_2_ci95_se,
      COALESCE(MAX(s.total_n) FILTER (WHERE component = 'second'), 0) AS component_2_ci95_n,
      COALESCE(MAX(s.cluster_n) FILTER (WHERE component = 'second'), 0) AS component_2_ci95_cluster_n,
      'table_cluster_delta' AS method
    FROM request_rows q LEFT JOIN expanded_stats s USING(row_key)
    GROUP BY q.row_key ORDER BY q.row_key LIMIT ? OFFSET ?
    """
    return query, value_params + scope_params
