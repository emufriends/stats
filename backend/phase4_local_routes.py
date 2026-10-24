"""Page-specific DuckDB SQL adapters for the production query service.

The adapters use immutable local facts and preserve the public route contracts.
Table eligibility and opponent construction precede focal filters; metrics then
apply route-specific scope, grain and aggregation. Shared filters do not imply
shared populations. Compact derivatives and canonical fallbacks must agree on
multiplicity, nulls and unrounded moments, not merely public column names.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

from phase4_local_scope import normalize_scope, scope_predicates
from phase4_combo_mw_contracts import combination_sql, mw_action_cards_sql


def _sql_string(value: str) -> str:
    """Quote a trusted catalogue value for DuckDB SQL."""
    return "'" + str(value).replace("'", "''") + "'"


MAPS = (
    ("1a", "Map 1a: Observation Tower"), ("2a", "Map 2a: Outdoor Areas"),
    ("3a", "Map 3a: Silver Lake"), ("4a", "Map 4a: Commercial Harbor"),
    ("5a", "Map 5a: Park Restaurant"), ("6a", "Map 6a: Research Institute"),
    ("7a", "Map 7a: Ice Cream Parlors"), ("8a", "Map 8a: Hollywood Hills"),
    ("9", "Map 9: Geographical Zoo"), ("10", "Map 10: Rescue Station"),
    ("11", "Map 11: Caves"), ("12", "Map 12: Artificial Intelligence"),
    ("13", "Map 13: Drawing Board"), ("14", "Map 14: Lagoon"),
    ("T1", "Map T1: Tournament 1"),
    ("1", "Map 1: Observation Tower"), ("2", "Map 2: Outdoor Areas"),
    ("3", "Map 3: Silver Lake"), ("4", "Map 4: Commercial Harbor"),
    ("5", "Map 5: Park Restaurant"), ("6", "Map 6: Research Institute"),
    ("7", "Map 7: Ice Cream Parlors"), ("8", "Map 8: Hollywood Hills"),
    ("A", "Map A"), ("0", "Map 0"),
)

# One log row per player-game. The raw producer can export the same (table_id, player)
# log twice; routes whose unit is "player-game" must not count both copies. The first
# physical row (lowest generation-local rowid) is kept. Joining on rowid keeps the
# duplicate scan to the two key columns instead of the wide event arrays.
FIRST_LOG_PER_PLAYER_GAME = (
    "(SELECT MIN(rowid) AS first_log_rowid FROM source_logs GROUP BY table_id, player)"
)
SOURCE_LOGS_ONE_PER_PLAYER_GAME = (
    f"source_logs l JOIN {FIRST_LOG_PER_PLAYER_GAME} first_log ON l.rowid = first_log.first_log_rowid"
)


MAP_KEYS = tuple(f"map_{code}" for code, _ in MAPS)

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

CP_REWARDS = (
    (1, "University", "1 university", False),
    (2, "Partner zoo", "1 partner-zoo", False),
    (3, "Posturing 3", "3 bonus-kiosk-pavilion", True),
    (4, "x2", "1 multiplier", False),
    (5, "10 money", "10 money", False),
    (6, "2 reputation", "2 reputation", False),
    (7, "3 X-tokens", "3 xtoken", False),
    (8, "3-size", "1 size-3", False),
    (9, "Marketing", "1 bonus-sponsor-gray", False),
    (10, "Extra Shift", "1 bonus-extra-shift", True),
    (11, "Bonus icon", "1 bonus-icon", True),
    (12, "3 cards", "3 take-in-range-or-deck", False),
    (13, "Snap + Handsize", "1 bonus-increased-hand", True),
    (14, "Ignore 3", "3 bonus-ignore-conditions", True),
    (15, "Adapt 3", "3 bonus-scoring-cards", True),
    (16, "5 money", "5 money", False),
)


def _map_key(code: str) -> str:
    return f"map_{code.lower()}"


def _tooltip_field(key: str) -> str:
    return {
        "money_spent_animals_pct": "money_spent_animals",
        "money_spent_build_pct": "money_spent_build",
        "money_spent_donations_pct": "money_spent_donations",
        "money_spent_range_pct": "money_spent_range",
    }.get(key, "NULL")

METRICS = (
    ("games", 1, "Games", None, "compact", "COUNT(DISTINCT table_id)"),
    ("turns", 2, "Turns", None, "number", "AVG(Number_of_turns)"),
    ("rounds", 3, "Rounds", None, "number", "AVG(total_breaks + 1)"),
    ("points_per_turn", 4, "Points per turn", None, "number", "AVG(points_per_turn)"),
    ("points_per_money", 5, "Points per money", None, "number", "AVG(points_per_money)"),
    ("money_per_turn", 6, "Money per turn", None, "number", "AVG(Money_gained / NULLIF(Number_of_turns, 0))"),
    ("score", 7, "Score", None, "number", "AVG(Score)"),
    ("appeal", 8, "Appeal", None, "number", "AVG(Appeal)"),
    ("conservation", 9, "Conservation", None, "number", "AVG(Conservation)"),
    ("reputation", 10, "Reputation", None, "number", "AVG(Reputation)"),
    ("projects", 11, "Projects", None, "number", "AVG(Conservation_project_association_tasks)"),
    ("upgrades", 12, "Upgrades", None, "number", "AVG(Upgraded_action_cards)"),
    ("workers", 13, "Workers", None, "number", "AVG(Association_workers)"),
    ("cover_pct", 14, "Cover%", "percentage of map hexes covered", "percent", "AVG(100 * (CASE WHEN Map IN ('Map 5: Park Restaurant', 'Map 5a: Park Restaurant', 'Map 10: Rescue Station') THEN 43 WHEN Map = 'Map 0' THEN 39 ELSE 42 END - Empty_hexes) / NULLIF(CASE WHEN Map IN ('Map 5: Park Restaurant', 'Map 5a: Park Restaurant', 'Map 10: Rescue Station') THEN 43 WHEN Map = 'Map 0' THEN 39 ELSE 42 END, 0))"),
    ("fill_pct", 15, "Fill%", "percentage of games with map fill", "percent", "AVG(CASE WHEN Empty_hexes = 0 THEN 100.0 ELSE 0.0 END)"),
    ("animals_pct", 16, "Animals%", "percentage of games with Animals upgrade", "percent", "AVG(CASE WHEN Upgraded_Animals_action_card THEN 100.0 ELSE 0.0 END)"),
    ("association_pct", 17, "Association%", "percentage of games with Association upgrade", "percent", "AVG(CASE WHEN Upgraded_Association_action_card THEN 100.0 ELSE 0.0 END)"),
    ("build_pct", 18, "Build%", "percentage of games with Build upgrade", "percent", "AVG(CASE WHEN Upgraded_Build_action_card THEN 100.0 ELSE 0.0 END)"),
    ("cards_pct", 19, "Cards%", "percentage of games with Cards upgrade", "percent", "AVG(CASE WHEN Upgraded_Cards_action_card THEN 100.0 ELSE 0.0 END)"),
    ("sponsors_pct", 20, "Sponsors%", "percentage of games with Sponsors upgrade", "percent", "AVG(CASE WHEN Upgraded_Sponsors_action_card THEN 100.0 ELSE 0.0 END)"),
    ("determinations", 21, "Determinations", None, "number", "AVG(determinations)"),
    ("animals_actions", 22, "Animals actions", None, "number", "AVG(Animals_actions)"),
    ("association_actions", 23, "Association actions", None, "number", "AVG(Association_actions)"),
    ("build_actions", 24, "Build actions", None, "number", "AVG(Build_actions)"),
    ("cards_actions", 25, "Cards actions", None, "number", "AVG(Cards_actions)"),
    ("sponsors_actions", 26, "Sponsors actions", None, "number", "AVG(Sponsors_actions)"),
    ("universities", 27, "Universities", None, "number", "AVG(University_association_tasks)"),
    ("partner_zoos", 28, "Partner zoos", None, "number", "AVG(Partner_zoo_association_tasks)"),
    ("reputation_actions", 29, "Reputation actions", None, "number", "AVG(Reputation_association_tasks)"),
    ("x_tokens_gained", 30, "X-token gained", None, "number", "AVG(X_Tokens_gained)"),
    ("x_tokens_spent", 31, "X-token spent", None, "number", "AVG(X_Tokens_used)"),
    ("x_backs", 32, "X-backs", None, "number", "AVG(X_Tokens_gained_instead_of_action)"),
    ("money_gained", 33, "Money gained", None, "number", "AVG(Money_gained)"),
    ("money_gained_income", 34, "Money gained (income)", None, "number", "AVG(Money_gained_through_income)"),
    ("money_spent_animals_pct", 35, "Money spent (Animals)", "Animals spending as a percentage of total money spent", "percent", "100 * AVG(Money_spent_on_animals) / NULLIF(AVG(Money_spent_on_animals + Money_spent_on_enclosures + Money_spent_on_donations + Money_spent_for_playing_cards_from_reputation_range), 0)"),
    ("money_spent_build_pct", 36, "Money spent (Build)", "Build spending as a percentage of total money spent", "percent", "100 * AVG(Money_spent_on_enclosures) / NULLIF(AVG(Money_spent_on_animals + Money_spent_on_enclosures + Money_spent_on_donations + Money_spent_for_playing_cards_from_reputation_range), 0)"),
    ("money_spent_donations_pct", 37, "Money spent (Donations)", "Donations spending as a percentage of total money spent", "percent", "100 * AVG(Money_spent_on_donations) / NULLIF(AVG(Money_spent_on_animals + Money_spent_on_enclosures + Money_spent_on_donations + Money_spent_for_playing_cards_from_reputation_range), 0)"),
    ("money_spent_range_pct", 38, "Money spent (Range)", "Range spending as a percentage of total money spent", "percent", "100 * AVG(Money_spent_for_playing_cards_from_reputation_range) / NULLIF(AVG(Money_spent_on_animals + Money_spent_on_enclosures + Money_spent_on_donations + Money_spent_for_playing_cards_from_reputation_range), 0)"),
    ("cards_drawn_deck", 39, "Cards drawn (deck)", None, "number", "AVG(Cards_drawn_from_deck)"),
    ("cards_drawn_range", 40, "Cards drawn (Range)", None, "number", "AVG(Cards_taken_from_reputation_range)"),
    ("cards_snapped", 41, "Cards snapped", None, "number", "AVG(Snapped_cards)"),
    ("cards_discarded", 42, "Cards discarded", None, "number", "AVG(Discarded_cards)"),
    ("enclosures", 43, "Enclosures", None, "number", "AVG(Built_enclosures)"),
    ("kiosks", 44, "Kiosks", None, "number", "AVG(Built_kiosks)"),
    ("pavilions", 45, "Pavilions", None, "number", "AVG(Built_pavilions)"),
    ("unique_buildings", 46, "Unique buildings", None, "number", "AVG(Built_unique_buildings)"),
    ("animals_played", 47, "Animals played", None, "number", "AVG(Played_animals)"),
    ("animals_released", 48, "Animals released", None, "number", "AVG(Released_animals)"),
    ("sponsors_played", 49, "Sponsors played", None, "number", "AVG(Played_sponsors)"),
    ("bird_icons", 50, "Bird icons", None, "number", "AVG(Bird_icons)"),
    ("herbivore_icons", 51, "Herbivore icons", None, "number", "AVG(Herbivore_icons)"),
    ("predator_icons", 52, "Predator icons", None, "number", "AVG(Predator_icons)"),
    ("primate_icons", 53, "Primate icons", None, "number", "AVG(Primate_icons)"),
    ("reptile_icons", 54, "Reptile icons", None, "number", "AVG(Reptile_icons)"),
    ("sea_animal_icons", 55, "Sea Animal icons", None, "number", "AVG(Sea_Animal_icons)"),
    ("bear_icons", 56, "Bear icons", None, "number", "AVG(Bear_icons)"),
    ("petting_zoo_icons", 57, "Petting zoo icons", None, "number", "AVG(Petting_Zoo_icons)"),
    ("africa_icons", 58, "Africa icons", None, "number", "AVG(Africa_icons)"),
    ("america_icons", 59, "America icons", None, "number", "AVG(Americas_icons)"),
    ("asia_icons", 60, "Asia icons", None, "number", "AVG(Asia_icons)"),
    ("australia_icons", 61, "Australia icons", None, "number", "AVG(Australia_icons)"),
    ("europe_icons", 62, "Europe icons", None, "number", "AVG(Europe_icons)"),
    ("rock_icons", 63, "Rock icons", None, "number", "AVG(Rock_icons)"),
    ("water_icons", 64, "Water icons", None, "number", "AVG(Water_icons)"),
    ("science_icons", 65, "Science icons", None, "number", "AVG(Science_icons)"),
)

PROJECT_REWARDS = (
    (1, "Snapping", "Snapping", None, "generic"),
    (2, "2-size", "2-size", None, "generic"),
    (3, "5 money", "5 Money", None, "generic"),
    (4, "Worker", "Worker", None, "generic"),
    (5, "12 money", "12 Money", None, "generic"),
    (6, "3 X-tokens", "3 X Token", None, "generic"),
    (7, "Marketing (1a)", "Marketing", MAPS[0][1], "map"),
    (8, "1 CP (2a)", "1 CP", MAPS[1][1], "map"),
    (9, "Determination (3a)", "Determination", MAPS[2][1], "map"),
    (10, "University (4a)", "University", MAPS[3][1], "map"),
    (11, "Unique building (5a)", "Aviary/Reptile House", MAPS[4][1], "map"),
    (12, "Clever (6a)", "Clever", MAPS[5][1], "map"),
    (13, "Pouching (7a)", "Pouching", MAPS[6][1], "map"),
    (14, "Partner zoo (8a)", "Partner Zoo", MAPS[7][1], "map"),
    (15, "Token (9)", "Remove Continent Cube", MAPS[8][1], "map"),
    (16, "2 reputation (10)", "2 Reputation", MAPS[9][1], "map"),
    (17, "Upgrade (11)", "Upgrade", MAPS[10][1], "map"),
    (18, "Animal magnet (12)", "Animal Magnet", MAPS[11][1], "map"),
    (19, "Adapt (13)", "Adapt 3", MAPS[12][1], "map"),
    (20, "Person sponsor (14)", "Play a person sponsor", MAPS[13][1], "map"),
    (21, "Draw + ability (T1)", "Draw from range", MAPS[14][1], "map"),
    (22, "3 reputation (T1)", "3 Reputation", MAPS[14][1], "map"),
)

PREDICTOR_SPECIFIC_CONDITIONS = (
    ("More endgame points", "more_endgame_points", False),
    ("More endgame CP", "more_endgame_cp", False),
    ("More ingame CP", "more_ingame_cp", False),
    ("More reefers", "more_reefers", True),
    ("More small animals", "more_small_animals", False),
    ("More medium animals", "more_medium_animals", False),
    ("More large animals", "more_large_animals", False),
    ("Round 1: Upgrade", "round_1_upgrade", False),
    ("Round 1: Project", "round_1_project", False),
    ("Round 1: Release", "round_1_release", False),
    ("Round 1: 2+ association actions", "round_1_two_association", False),
    ("First to 5 CP", "first_to_5", False),
    ("First to 5 CP (with exactly one university/partner zoo bonus)", "first_to_5_bonus", False),
    ("First to 8 CP", "first_to_8", False),
    ("First to 8 CP (with exactly one university/partner zoo bonus)", "first_to_8_bonus", False),
    ("No project in starting hand", "no_project_opening", False),
    ("No sponsor in starting hand", "no_sponsor_opening", False),
    ("No sponsor in starting hand and Sponsors at 5", "no_sponsor_sponsors_5", False),
    ("No sponsor in starting hand and second player and Association at 2 and Sponsors at 5", "no_sponsor_second_assoc_2_sponsors_5", False),
)

SPONSOR_CP_CARDS = (
    "Science Lab", "Federal Grants", "Talented Communicator", "Native Farm Animals",
    "Geologist", "Hydrologist", "Guided School Tours", "Science Library",
    "Excavation Site", "Veterinarian", "Technology Institute", "Franchise Business",
    "Expert On The Americas", "Quarantine Lab", "Foreign Institute", "Aquarium",
    "Conference On Europe", "Cable Car", "Breeding Cooperation", "Breeding Program",
    "Archaeologist", "Polar Bear Exhibit", "Expansion Area", "Baboon Rock",
    "Free-range New World Monkeys", "Penguin Pool", "Farm Cat", "Meerkat Den",
    "Native Lizards", "Native Seabirds", "Expert On Europe",
)
SPONSOR_CP_0_1_2_3PLUS = {
    "Farm Cat", "Free-range New World Monkeys", "Native Farm Animals",
    "Native Lizards", "Native Seabirds",
}
SPONSOR_CP_0_1_2 = {"Polar Bear Exhibit", "Science Lab"}
SPONSOR_APPEAL_VALUES = {
    "Arcade": (0, 2), "Conference On Australia": (0, 1, 2, 3, 4, 5),
    "Diversity Researcher": (0, 2, 4, 6), "Engineer": (0, 5),
    "Expert On Africa": (0, 1, 2, 3, 4, 5), "Reconstruction": (0, 5),
    "Side Entrance": (0, 5), "Underwater Tunnel": (0, 3, 5),
    "Victory Column": (0, 2),
}

EXCLUDED_SUMMARY_PROJECTS = frozenset({
    "reptiles", "europe", "predators", "americas", "australia",
    "birds", "sea animals", "africa", "herbivores", "asia",
    "primates", "habitat diversity", "species diversity",
})


def _card_attribute_groups() -> dict[str, tuple[str, ...]]:
    """Read the canonical card catalogue used by the predictor contract."""
    groups: dict[str, set[str]] = {
        "reefer_animals": set(), "small_animals": set(),
        "medium_animals": set(), "large_animals": set(),
        "project_cards": set(), "sponsor_cards": set(),
    }
    source = Path(__file__).with_name("cards_attributes.csv")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = str(row.get("Name") or "").strip().lower()
            card_type = str(row.get("Type") or "").strip().lower()
            if not name:
                continue
            if card_type == "project":
                groups["project_cards"].add(name)
            elif card_type == "sponsor":
                groups["sponsor_cards"].add(name)
            elif card_type == "animal":
                reefer = str(row.get("Reefer") or "").strip().lower()
                if reefer not in {"", "0", "false", "no"}:
                    groups["reefer_animals"].add(name)
                try:
                    size = int(float(str(row.get("Size") or "").strip()))
                except ValueError:
                    size = None
                if size in (1, 2):
                    groups["small_animals"].add(name)
                elif size == 3:
                    groups["medium_animals"].add(name)
                elif size in (4, 5):
                    groups["large_animals"].add(name)
    return {key: tuple(sorted(values)) for key, values in groups.items()}


def _players_metrics():
    """Return the authorized Players catalog, distinct from Maps/Metrics.

    Players omits Maps' Games and Rounds rows, inserts the two break metrics
    directly after Turns, and otherwise retains the Maps labels and order.
    Keeping this catalog separate prevents a Maps change from silently altering
    the Players table or graph contract again.
    """

    result = []
    next_order = 1
    for key, original_order, label, tooltip, value_format, expression in METRICS:
        if key in {"games", "rounds"}:
            continue
        result.append((
            key, next_order, label, tooltip, original_order <= 20,
            value_format, key == "turns", expression,
        ))
        next_order += 1
        if key == "turns":
            result.extend((
                (
                    "breaks_triggered", next_order, "Breaks triggered", None,
                    False, "number", False,
                    "AVG(TRY_CAST(Number_of_breaks_triggered AS DOUBLE))",
                ),
                (
                    "break_pct", next_order + 1, "Break%",
                    "percentage of available breaks that were triggered",
                    False, "percent", False,
                    "AVG(100.0 * TRY_CAST(Number_of_breaks_triggered AS DOUBLE) "
                    "/ NULLIF(TRY_CAST(total_breaks AS DOUBLE), 0))",
                ),
            ))
            next_order += 2
    return tuple(result)


PLAYERS_METRICS = _players_metrics()
PLAYERS_MONEY_FIELDS = {
    "money_spent_animals_pct": "Money_spent_on_animals",
    "money_spent_build_pct": "Money_spent_on_enclosures",
    "money_spent_donations_pct": "Money_spent_on_donations",
    "money_spent_range_pct": "Money_spent_for_playing_cards_from_reputation_range",
}


def maps_metrics_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=True)
    # Build one aggregate column per metric, then unpivot with explicit UNIONs.
    unions = "\n      UNION ALL\n      ".join(
        f"SELECT map_name, '{key}' AS metric_key, {key} AS value, "
        f"{_tooltip_field(key)} AS tooltip_value FROM per_map"
        for key, _, _, _, _, _ in METRICS
    )
    config_rows = ",\n        ".join(
        f"({order}, '{label}', {('NULL' if tooltip is None else repr(tooltip))}, {('TRUE' if order <= 20 else 'FALSE')}, '{value_format}', {('TRUE' if key in {'turns', 'rounds'} else 'FALSE')}, '{key}')"
        for key, order, label, tooltip, value_format, _ in METRICS
    )
    map_selects = ",\n      ".join(
        f"MAX(value) FILTER (WHERE map_name = '{full}') AS {_map_key(code)}, "
        f"MAX(tooltip_value) FILTER (WHERE map_name = '{full}') AS tooltip_{_map_key(code)}"
        for code, full in MAPS
    )
    sql = f"""
    WITH filtered AS (
      SELECT f.* FROM prepared_full_sample_narrow f WHERE {predicates}
    ),
    per_map AS (
      SELECT *,
        100 * money_spent_animals / NULLIF(money_spent_animals + money_spent_build + money_spent_donations + money_spent_range, 0) AS money_spent_animals_pct,
        100 * money_spent_build / NULLIF(money_spent_animals + money_spent_build + money_spent_donations + money_spent_range, 0) AS money_spent_build_pct,
        100 * money_spent_donations / NULLIF(money_spent_animals + money_spent_build + money_spent_donations + money_spent_range, 0) AS money_spent_donations_pct,
        100 * money_spent_range / NULLIF(money_spent_animals + money_spent_build + money_spent_donations + money_spent_range, 0) AS money_spent_range_pct
      FROM (
        SELECT Map AS map_name,
          {', '.join(
            f"{expression.replace('AVG(Money_spent_on_animals)', 'AVG(Money_spent_on_animals)').replace('AVG(Money_spent_on_enclosures)', 'AVG(Money_spent_on_enclosures)').replace('AVG(Money_spent_on_donations)', 'AVG(Money_spent_on_donations)').replace('AVG(Money_spent_for_playing_cards_from_reputation_range)', 'AVG(Money_spent_for_playing_cards_from_reputation_range)')} AS {key}"
            for key, _, _, _, _, expression in METRICS if key not in {'money_spent_animals_pct', 'money_spent_build_pct', 'money_spent_donations_pct', 'money_spent_range_pct'}
          )},
          AVG(Money_spent_on_animals) AS money_spent_animals,
          AVG(Money_spent_on_enclosures) AS money_spent_build,
          AVG(Money_spent_on_donations) AS money_spent_donations,
          AVG(Money_spent_for_playing_cards_from_reputation_range) AS money_spent_range
        FROM filtered GROUP BY map_name
      ) base
    ),
    metric_values AS (
      {unions}
    ),
    config(sort_order, metric, tooltip, is_default, format, lower_is_better, metric_key) AS (
      VALUES {config_rows}
    )
    SELECT c.sort_order, c.metric, c.tooltip, c.is_default, c.format, c.lower_is_better,
      {map_selects}
    FROM metric_values v JOIN config c USING(metric_key)
    GROUP BY c.sort_order, c.metric, c.tooltip, c.is_default, c.format, c.lower_is_better
    ORDER BY c.sort_order
    """
    return sql + "\n    LIMIT ? OFFSET ?", parameters


def endgames_general_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=True)
    sql = f"""
    WITH filtered AS (
      SELECT f.table_id, f.player, f.elo_delta, f.pre_match_elo
      FROM prepared_full_sample_narrow f
      WHERE {predicates}
    ),
    dealt AS (
      SELECT f.table_id, f.player, f.elo_delta, e.endgame_name AS card_name
      FROM filtered f JOIN endgame_dealt_event_narrow e USING(table_id, player)
    ),
    scored AS (
      SELECT f.table_id, f.player, f.elo_delta, f.pre_match_elo,
        e.endgame_name AS card_name, e.cp
      FROM filtered f JOIN endgame_score_filter_event_narrow e USING(table_id, player)
    ),
    events AS (
      SELECT 'dealt' AS kind, card_name, table_id, elo_delta,
        NULL::DOUBLE AS pre_match_elo, NULL::DOUBLE AS cp FROM dealt
      UNION ALL
      SELECT 'scored', card_name, table_id, elo_delta, pre_match_elo, cp FROM scored
    ), clusters AS (
      SELECT kind, card_name, table_id, COUNT(*) AS row_n,
        COUNT(elo_delta) AS n, SUM(elo_delta) AS s,
        SUM(pre_match_elo) AS elo_sum, COUNT(pre_match_elo) AS elo_n,
        SUM(cp) AS cp_sum, COUNT(cp) AS cp_n
      FROM events GROUP BY kind, card_name, table_id
    ), moments AS (
      SELECT kind, card_name, SUM(row_n) AS row_n, SUM(n) AS ci_n,
        SUM(s) AS ci_sum, COUNT(*) FILTER (WHERE n > 0) AS cluster_n,
        SUM(COALESCE(s, 0) * COALESCE(s, 0)) AS ss,
        SUM(COALESCE(s, 0) * n) AS sn, SUM(n * n) AS nn,
        SUM(elo_sum) / NULLIF(SUM(elo_n), 0) AS avg_elo,
        SUM(cp_sum) / NULLIF(SUM(cp_n), 0) AS avg_cp
      FROM clusters GROUP BY kind, card_name
    ), intervals AS (
      SELECT *, ci_sum / NULLIF(ci_n, 0) AS mean,
        SQRT(cluster_n / NULLIF(cluster_n - 1, 0) * GREATEST(
          ss - 2 * ci_sum / NULLIF(ci_n, 0) * sn
            + POW(ci_sum / NULLIF(ci_n, 0), 2) * nn, 0)
          / NULLIF(ci_n * ci_n, 0)) AS se
      FROM moments
    )
    SELECT 'endgame' AS card_type, s.card_name,
      ROUND(d.mean, 3) AS delta_played,
      ROUND(s.mean, 3) AS delta_in_hand,
      ROUND(s.avg_elo, 0) AS avg_elo,
      s.row_n AS n_played, d.row_n AS n_seen,
      ROUND(100 * s.row_n / NULLIF(d.row_n, 0), 2) AS playrate_pct,
      ROUND(s.avg_cp, 2) AS avg_cp
      , CASE WHEN d.cluster_n >= 2 AND d.ci_n > 0 THEN d.mean - 1.96 * d.se END AS delta_played_ci95_low
      , CASE WHEN d.cluster_n >= 2 AND d.ci_n > 0 THEN d.mean + 1.96 * d.se END AS delta_played_ci95_high
      , d.ci_n AS delta_played_ci95_n
      , CASE WHEN s.cluster_n >= 2 AND s.ci_n > 0 THEN s.mean - 1.96 * s.se END AS delta_in_hand_ci95_low
      , CASE WHEN s.cluster_n >= 2 AND s.ci_n > 0 THEN s.mean + 1.96 * s.se END AS delta_in_hand_ci95_high
      , s.ci_n AS delta_in_hand_ci95_n
    FROM intervals s JOIN intervals d USING(card_name)
    WHERE s.kind = 'scored' AND d.kind = 'dealt'
    ORDER BY delta_played DESC NULLS LAST, card_name
    """
    return sql + "\n    LIMIT ? OFFSET ?", parameters


def _scoring_buckets(view: str, expanded: bool = False) -> tuple[str, list[tuple[str, str, str]]]:
    """Return the source field and fixed Scoring display buckets."""

    if view == "final_score":
        if expanded:
            return "Score", [
                ("under_100", "<100", "metric_value < 100"),
                *((str(value), str(value), f"metric_value = {value}") for value in range(100, 150)),
                ("150_plus", "150+", "metric_value >= 150"),
            ]
        return "Score", [
            ("under_100", "<100", "metric_value < 100"),
            ("100_109", "100–109", "metric_value BETWEEN 100 AND 109"),
            ("110_119", "110–119", "metric_value BETWEEN 110 AND 119"),
            ("120_129", "120–129", "metric_value BETWEEN 120 AND 129"),
            ("130_139", "130–139", "metric_value BETWEEN 130 AND 139"),
            ("140_149", "140–149", "metric_value BETWEEN 140 AND 149"),
            ("150_plus", "150+", "metric_value >= 150"),
        ]
    if view == "appeal":
        if expanded:
            return "Appeal", [
                ("under_40", "<40", "metric_value < 40"),
                *((str(value), str(value), f"metric_value = {value}") for value in range(40, 114)),
            ]
        return "Appeal", [
            ("under_40", "<40", "metric_value < 40"),
            ("40_49", "40–49", "metric_value BETWEEN 40 AND 49"),
            ("50_59", "50–59", "metric_value BETWEEN 50 AND 59"),
            ("60_69", "60–69", "metric_value BETWEEN 60 AND 69"),
            ("70_79", "70–79", "metric_value BETWEEN 70 AND 79"),
            ("80_89", "80–89", "metric_value BETWEEN 80 AND 89"),
            ("90_99", "90–99", "metric_value BETWEEN 90 AND 99"),
            ("100_112", "100–112", "metric_value BETWEEN 100 AND 112"),
            ("113", "113", "metric_value = 113"),
        ]
    if view == "conservation_points":
        if expanded:
            return "Conservation", [
                (str(value), str(value), f"metric_value = {value}") for value in range(42)
            ]
        return "Conservation", [
            ("0_10", "0–10", "metric_value BETWEEN 0 AND 10"),
            ("11_15", "11–15", "metric_value BETWEEN 11 AND 15"),
            ("16_20", "16–20", "metric_value BETWEEN 16 AND 20"),
            ("21_25", "21–25", "metric_value BETWEEN 21 AND 25"),
            ("26_30", "26–30", "metric_value BETWEEN 26 AND 30"),
            ("31_35", "31–35", "metric_value BETWEEN 31 AND 35"),
            ("36_40", "36–40", "metric_value BETWEEN 36 AND 40"),
            ("41", "41", "metric_value = 41"),
        ]
    if view == "reputation":
        return "Reputation", [
            (str(value), str(value), f"metric_value = {value}") for value in range(1, 16)
        ]
    raise ValueError(f"unknown scoring view: {view}")


def scoring_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    """Build one Scoring distribution with a single classified source scan."""

    view = str(request.get("scoring_view") or request.get("view") or "final_score")
    if view.startswith("phase4_scoring_"):
        view = view.removeprefix("phase4_scoring_")
    source_field, buckets = _scoring_buckets(view, bool(request.get("scoring_expanded")))
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=True)
    if view == "conservation_points":
        valid_condition = "metric_value BETWEEN 0 AND 41"
    elif view == "appeal":
        valid_condition = "metric_value BETWEEN 0 AND 113"
    elif view == "reputation":
        valid_condition = "metric_value BETWEEN 1 AND 15"
    else:
        valid_condition = "TRUE"
    bucket_case = "CASE\n" + "\n".join(
        f"WHEN {condition} THEN '{key}'" for key, _, condition in buckets
    ) + "\nELSE NULL END"
    config_rows = ", ".join(
        f"('{key}', '{label}', {order})" for order, (key, label, _) in enumerate(buckets, 1)
    )
    map_denoms = []
    map_output = []
    for code, full in MAPS[:15]:
        key = _map_key(code)
        map_denoms.append(f"SUM(row_n) FILTER (WHERE map_name = '{full}') AS denom_{key}")
        map_output.extend([
            f"MAX(m.avg) FILTER (WHERE m.map_name = '{full}') AS {key}",
            f"COALESCE(MAX(m.count_value) FILTER (WHERE m.map_name = '{full}'), 0) AS count_{key}",
            f"d.denom_{key} AS denom_{key}",
            f"MAX(m.ci_mean) FILTER (WHERE m.map_name = '{full}') AS {key}_ci_mean",
            f"MAX(m.ci_sd) FILTER (WHERE m.map_name = '{full}') AS {key}_ci_sd",
            f"COALESCE(MAX(m.ci_n) FILTER (WHERE m.map_name = '{full}'), 0) AS {key}_ci_n",
        ])
    sql = f"""
    WITH filtered AS (
      SELECT f.Map AS map_name,
        TRY_CAST(f.{source_field} AS DOUBLE) AS metric_value,
        TRY_CAST(f.elo_delta AS DOUBLE) AS elo_delta
      FROM prepared_full_sample_narrow f
      WHERE {predicates}
    ),
    classified AS (
      SELECT *, {bucket_case} AS bucket_key
      FROM filtered
      WHERE metric_value IS NOT NULL AND {valid_condition}
    ),
    cell_moments AS (
      SELECT bucket_key, map_name, COUNT(*) AS row_n,
        COUNT(elo_delta) AS elo_n, SUM(elo_delta) AS elo_sum,
        SUM(elo_delta * elo_delta) AS elo_sumsq
      FROM classified WHERE bucket_key IS NOT NULL
      GROUP BY bucket_key, map_name
    ), by_map AS (
      SELECT bucket_key, map_name, row_n AS count_value,
        elo_sum / NULLIF(elo_n, 0) AS avg,
        elo_sum / NULLIF(elo_n, 0) AS ci_mean,
        SQRT(GREATEST(elo_sumsq - elo_sum * elo_sum / NULLIF(elo_n, 0), 0)
          / NULLIF(elo_n - 1, 0)) AS ci_sd,
        elo_n AS ci_n
      FROM cell_moments
    ), overall_moments AS (
      SELECT bucket_key, SUM(row_n) AS row_n, SUM(elo_n) AS elo_n,
        SUM(elo_sum) AS elo_sum, SUM(elo_sumsq) AS elo_sumsq
      FROM cell_moments GROUP BY bucket_key
    ), aggregates AS (
      SELECT bucket_key, row_n AS count_avg,
        elo_sum / NULLIF(elo_n, 0) AS avg,
        elo_sum / NULLIF(elo_n, 0) AS avg_ci_mean,
        SQRT(GREATEST(elo_sumsq - elo_sum * elo_sum / NULLIF(elo_n, 0), 0)
          / NULLIF(elo_n - 1, 0)) AS avg_ci_sd,
        elo_n AS avg_ci_n
      FROM overall_moments
    ),
    denominators AS (
      SELECT SUM(row_n) AS denom_avg, {', '.join(map_denoms)} FROM cell_moments
    ),
    config(bucket_key, bucket_label, sort_order) AS (VALUES {config_rows})
    SELECT c.bucket_key, c.bucket_label, c.sort_order,
      a.avg, a.count_avg, d.denom_avg,
      a.avg_ci_mean, a.avg_ci_sd, a.avg_ci_n,
      {', '.join(map_output)}
    FROM config c
    LEFT JOIN aggregates a USING(bucket_key)
    LEFT JOIN by_map m USING(bucket_key)
    CROSS JOIN denominators d
    GROUP BY c.bucket_key, c.bucket_label, c.sort_order,
      a.avg, a.count_avg, a.avg_ci_mean, a.avg_ci_sd, a.avg_ci_n,
      d.denom_avg, {', '.join(f'd.denom_{_map_key(code)}' for code, _full in MAPS[:15])}
    ORDER BY c.sort_order
    """
    return sql + "\nLIMIT ? OFFSET ?", parameters


def _simple_scope(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    return scope_predicates(scope, "f", hard_completed=False)


def _simple_map_columns(prefix: str = "") -> tuple[list[str], list[str]]:
    """Return map aggregate expressions and selected map columns."""
    aggregates: list[str] = []
    columns: list[str] = []
    for code, full in MAPS[:15]:
        key = _map_key(code)
        quoted = _sql_string(full)
        condition = f"{prefix}Map = {quoted}"
        aggregates.extend([
            f"AVG(elo_delta) FILTER (WHERE {condition}) AS {key}",
            f"COUNT(*) FILTER (WHERE {condition}) AS count_{key}",
            f"COUNT(*) FILTER (WHERE {condition}) AS denom_{key}",
            f"AVG(elo_delta) FILTER (WHERE {condition}) AS {key}_ci_mean",
            f"STDDEV_SAMP(elo_delta) FILTER (WHERE {condition}) AS {key}_ci_sd",
            f"COUNT(elo_delta) FILTER (WHERE {condition}) AS {key}_ci_n",
        ])
        columns.extend([
            f"a.{key}", f"a.count_{key}", f"a.denom_{key}",
            f"a.{key}_ci_mean", f"a.{key}_ci_sd", f"a.{key}_ci_n",
        ])
    return aggregates, columns


def _simple_actions_upgrades_sql(predicates: str, parameters: list[Any]) -> tuple[str, list[Any]]:
    return f"""
    WITH filtered AS (
      SELECT f.* FROM prepared_full_sample_narrow f
      WHERE {predicates}
    ), number_rows AS (
      SELECT 'number' AS section, c.bucket + 1 AS sort_order,
        CAST(c.bucket AS VARCHAR) AS label,
        AVG(elo_delta) FILTER (WHERE TRY_CAST(Upgraded_action_cards AS INTEGER) = c.bucket) AS delta,
        COUNT(*) FILTER (WHERE TRY_CAST(Upgraded_action_cards AS INTEGER) = c.bucket) AS count,
        COUNT(Upgraded_action_cards) AS denominator,
        AVG(elo_delta) FILTER (WHERE TRY_CAST(Upgraded_action_cards AS INTEGER) = c.bucket) AS delta_ci_mean,
        STDDEV_SAMP(elo_delta) FILTER (WHERE TRY_CAST(Upgraded_action_cards AS INTEGER) = c.bucket) AS delta_ci_sd,
        COUNT(elo_delta) FILTER (WHERE TRY_CAST(Upgraded_action_cards AS INTEGER) = c.bucket) AS delta_ci_n
      FROM filtered CROSS JOIN (VALUES (0),(1),(2),(3),(4),(5)) c(bucket)
      GROUP BY c.bucket
    ), upgrade_rows AS (
      SELECT 'upgrade' AS section, c.sort_order, c.label,
        AVG(f.elo_delta) FILTER (WHERE c.upgraded) AS delta,
        COUNT(*) FILTER (WHERE c.upgraded) AS count, COUNT(*) AS denominator,
        AVG(f.elo_delta) FILTER (WHERE c.upgraded) AS delta_ci_mean,
        STDDEV_SAMP(f.elo_delta) FILTER (WHERE c.upgraded) AS delta_ci_sd,
        COUNT(f.elo_delta) FILTER (WHERE c.upgraded) AS delta_ci_n
      FROM filtered f CROSS JOIN (
        VALUES (1, 'Animals', COALESCE(f.Upgraded_Animals_action_card, FALSE)),
               (2, 'Association', COALESCE(f.Upgraded_Association_action_card, FALSE)),
               (3, 'Build', COALESCE(f.Upgraded_Build_action_card, FALSE)),
               (4, 'Cards', COALESCE(f.Upgraded_Cards_action_card, FALSE)),
               (5, 'Sponsors', COALESCE(f.Upgraded_Sponsors_action_card, FALSE))
      ) c(sort_order, label, upgraded)
      GROUP BY c.sort_order, c.label
    )
    SELECT * FROM number_rows UNION ALL SELECT * FROM upgrade_rows
    ORDER BY section, sort_order LIMIT ? OFFSET ?
    """, parameters


def _simple_actions_upgrade_order_sql(predicates: str, parameters: list[Any]) -> tuple[str, list[Any]]:
    return f"""
    WITH filtered AS (
      SELECT l.*, f.table_id AS full_table_id, f.elo_delta AS full_elo_delta
      FROM {SOURCE_LOGS_ONE_PER_PLAYER_GAME} JOIN prepared_full_sample_narrow f USING(table_id, player)
      WHERE {predicates.replace('f.', 'f.')}
    ), config AS (
      VALUES (1, 'Animals'), (2, 'Association'), (3, 'Build'), (4, 'Cards'), (5, 'Sponsors')
    ), base AS (
      SELECT c.column0 AS sort_order, c.column1 AS label,
        COUNT(*) FILTER (WHERE first_upgrade = c.column1 OR second_upgrade = c.column1
          OR third_upgrade = c.column1 OR fourth_upgrade = c.column1) AS denominator,
        AVG(full_elo_delta) FILTER (WHERE first_upgrade = c.column1) AS delta_1,
        COUNT(*) FILTER (WHERE first_upgrade = c.column1) AS count_1,
        AVG(full_elo_delta) FILTER (WHERE first_upgrade = c.column1) AS delta_1_ci_mean,
        STDDEV_SAMP(full_elo_delta) FILTER (WHERE first_upgrade = c.column1) AS delta_1_ci_sd,
        COUNT(full_elo_delta) FILTER (WHERE first_upgrade = c.column1) AS delta_1_ci_n,
        AVG(full_elo_delta) FILTER (WHERE second_upgrade = c.column1) AS delta_2,
        COUNT(*) FILTER (WHERE second_upgrade = c.column1) AS count_2,
        AVG(full_elo_delta) FILTER (WHERE second_upgrade = c.column1) AS delta_2_ci_mean,
        STDDEV_SAMP(full_elo_delta) FILTER (WHERE second_upgrade = c.column1) AS delta_2_ci_sd,
        COUNT(full_elo_delta) FILTER (WHERE second_upgrade = c.column1) AS delta_2_ci_n,
        AVG(full_elo_delta) FILTER (WHERE third_upgrade = c.column1) AS delta_3,
        COUNT(*) FILTER (WHERE third_upgrade = c.column1) AS count_3,
        AVG(full_elo_delta) FILTER (WHERE third_upgrade = c.column1) AS delta_3_ci_mean,
        STDDEV_SAMP(full_elo_delta) FILTER (WHERE third_upgrade = c.column1) AS delta_3_ci_sd,
        COUNT(full_elo_delta) FILTER (WHERE third_upgrade = c.column1) AS delta_3_ci_n,
        AVG(full_elo_delta) FILTER (WHERE fourth_upgrade = c.column1) AS delta_4,
        COUNT(*) FILTER (WHERE fourth_upgrade = c.column1) AS count_4,
        AVG(full_elo_delta) FILTER (WHERE fourth_upgrade = c.column1) AS delta_4_ci_mean,
        STDDEV_SAMP(full_elo_delta) FILTER (WHERE fourth_upgrade = c.column1) AS delta_4_ci_sd,
        COUNT(full_elo_delta) FILTER (WHERE fourth_upgrade = c.column1) AS delta_4_ci_n
      FROM filtered CROSS JOIN config c(column0, column1)
      GROUP BY c.column0, c.column1
    ) SELECT * FROM base ORDER BY sort_order LIMIT ? OFFSET ?
    """, parameters


def _simple_actions_by_map_sql(predicates: str, parameters: list[Any]) -> tuple[str, list[Any]]:
    action_fields = (
        (1, "Animals", "Upgraded_Animals_action_card"),
        (2, "Association", "Upgraded_Association_action_card"),
        (3, "Build", "Upgraded_Build_action_card"),
        (4, "Cards", "Upgraded_Cards_action_card"),
        (5, "Sponsors", "Upgraded_Sponsors_action_card"),
    )
    config = ", ".join(
        f"({sort_order}, {_sql_string(label)})"
        for sort_order, label, _field in action_fields
    )
    observation_values = ", ".join(
        f"({sort_order}, {_sql_string(label)}, COALESCE(f.{field}, FALSE))"
        for sort_order, label, field in action_fields
    )
    map_denominators = ", ".join(
        f"COUNT(*) FILTER (WHERE Map = {_sql_string(full)}) AS denom_{_map_key(code)}"
        for code, full in MAPS[:15]
    )
    map_output = ", ".join(
        expression
        for code, full in MAPS[:15]
        for expression in (
            f"MAX(m.avg) FILTER (WHERE m.Map = {_sql_string(full)}) AS {_map_key(code)}",
            f"COALESCE(MAX(m.count_value) FILTER (WHERE m.Map = {_sql_string(full)}), 0) AS count_{_map_key(code)}",
            f"d.denom_{_map_key(code)} AS denom_{_map_key(code)}",
            f"MAX(m.ci_mean) FILTER (WHERE m.Map = {_sql_string(full)}) AS {_map_key(code)}_ci_mean",
            f"MAX(m.ci_sd) FILTER (WHERE m.Map = {_sql_string(full)}) AS {_map_key(code)}_ci_sd",
            f"COALESCE(MAX(m.ci_n) FILTER (WHERE m.Map = {_sql_string(full)}), 0) AS {_map_key(code)}_ci_n",
        )
    )
    return f"""
    WITH filtered AS (
      SELECT f.Map, f.elo_delta,
        f.Upgraded_Animals_action_card, f.Upgraded_Association_action_card,
        f.Upgraded_Build_action_card, f.Upgraded_Cards_action_card,
        f.Upgraded_Sponsors_action_card
      FROM prepared_full_sample_narrow f WHERE {predicates}
    ), config(sort_order, label) AS (VALUES {config}),
    denominators AS (
      SELECT COUNT(*) AS total_count, {map_denominators} FROM filtered
    ), observations AS (
      SELECT u.sort_order, u.label, f.Map, f.elo_delta
      FROM filtered f
      CROSS JOIN LATERAL (VALUES {observation_values})
        u(sort_order, label, upgraded)
      WHERE u.upgraded
    ), overall AS (
      SELECT sort_order, label, AVG(elo_delta) AS avg,
        COUNT(*) AS count_value, AVG(elo_delta) AS ci_mean,
        STDDEV_SAMP(elo_delta) AS ci_sd, COUNT(elo_delta) AS ci_n
      FROM observations GROUP BY sort_order, label
    ), by_map AS (
      SELECT sort_order, Map, AVG(elo_delta) AS avg,
        COUNT(*) AS count_value, AVG(elo_delta) AS ci_mean,
        STDDEV_SAMP(elo_delta) AS ci_sd, COUNT(elo_delta) AS ci_n
      FROM observations GROUP BY sort_order, Map
    )
    SELECT c.sort_order, c.label, o.avg,
      COALESCE(o.count_value, 0) AS count_avg, d.total_count AS denom_avg,
      o.ci_mean AS avg_ci_mean, o.ci_sd AS avg_ci_sd,
      COALESCE(o.ci_n, 0) AS avg_ci_n, {map_output}
    FROM config c LEFT JOIN overall o USING(sort_order, label)
    LEFT JOIN by_map m USING(sort_order) CROSS JOIN denominators d
    GROUP BY c.sort_order, c.label, o.avg, o.count_value, d.total_count,
      o.ci_mean, o.ci_sd, o.ci_n,
      {', '.join(f'd.denom_{_map_key(code)}' for code, _full in MAPS[:15])}
    ORDER BY c.sort_order LIMIT ? OFFSET ?
    """, parameters


def _simple_build_enclosures_sql(predicates: str, parameters: list[Any]) -> tuple[str, list[Any]]:
    config = "VALUES ('1-size','standard'),('2-size','standard'),('3-size','standard'),('4-size','standard'),('5-size','standard'),('Aviary','unique'),('Reptile House','unique'),('Petting Zoo','unique'),('Large Aquarium','unique'),('Small Aquarium','unique')"
    count_expr = "CASE e.column0 WHEN '1-size' THEN TRY_CAST(f.\"1_size_enclosure_built\" AS INTEGER) WHEN '2-size' THEN TRY_CAST(f.\"2_size_enclosure_built\" AS INTEGER) WHEN '3-size' THEN TRY_CAST(f.\"3_size_enclosure_built\" AS INTEGER) WHEN '4-size' THEN TRY_CAST(f.\"4_size_enclosure_built\" AS INTEGER) WHEN '5-size' THEN TRY_CAST(f.\"5_size_enclosure_built\" AS INTEGER) WHEN 'Aviary' THEN TRY_CAST(f.aviary_built AS INTEGER) WHEN 'Reptile House' THEN TRY_CAST(f.reptile_house_built AS INTEGER) WHEN 'Petting Zoo' THEN TRY_CAST(f.petting_zoo_built AS INTEGER) WHEN 'Large Aquarium' THEN TRY_CAST(f.large_aquarium_built AS INTEGER) WHEN 'Small Aquarium' THEN TRY_CAST(f.small_aquarium_built AS INTEGER) END"
    fields = []
    for suffix, condition in [(str(value), f"enclosure_count = {value}") for value in range(5)] + [("5_plus", "enclosure_count >= 5")]:
        fields += [f"AVG(elo_delta) FILTER (WHERE {condition}) AS delta_{suffix}", f"COUNT(*) FILTER (WHERE {condition}) AS count_{suffix}", f"AVG(elo_delta) FILTER (WHERE {condition}) AS delta_{suffix}_ci_mean", f"STDDEV_SAMP(elo_delta) FILTER (WHERE {condition}) AS delta_{suffix}_ci_sd", f"COUNT(elo_delta) FILTER (WHERE {condition}) AS delta_{suffix}_ci_n"]
    empty_condition = (
        "enclosure = 'Petting Zoo' AND enclosure_count = 1 "
        "AND COALESCE(TRY_CAST(Petting_Zoo_icons AS INTEGER), 0) = 0 "
        "AND NOT has_horse_whisperer"
    )
    fields += [
        f"AVG(elo_delta) FILTER (WHERE {empty_condition}) AS delta_empty",
        f"COUNT(*) FILTER (WHERE {empty_condition}) AS count_empty",
        f"AVG(elo_delta) FILTER (WHERE {empty_condition}) AS delta_empty_ci_mean",
        f"STDDEV_SAMP(elo_delta) FILTER (WHERE {empty_condition}) AS delta_empty_ci_sd",
        f"COUNT(elo_delta) FILTER (WHERE {empty_condition}) AS delta_empty_ci_n",
        "COUNT(*) FILTER (WHERE enclosure = 'Petting Zoo' AND enclosure_count = 1) AS empty_denominator",
    ]
    return f"""
    WITH filtered AS (
      SELECT f.elo_delta, f.Petting_Zoo_icons,
        l.\"1_size_enclosure_built\", l.\"2_size_enclosure_built\",
        l.\"3_size_enclosure_built\", l.\"4_size_enclosure_built\",
        l.\"5_size_enclosure_built\", l.aviary_built,
        l.reptile_house_built, l.petting_zoo_built,
        l.large_aquarium_built, l.small_aquarium_built,
        EXISTS (
          SELECT 1 FROM UNNEST(COALESCE(l.played_sponsors, []))
            AS ps(sponsor_event)
          WHERE sponsor_event.sponsor = 'Horse Whisperer'
        ) AS has_horse_whisperer
      FROM {SOURCE_LOGS_ONE_PER_PLAYER_GAME} JOIN prepared_full_sample_narrow f USING(table_id, player)
      WHERE {predicates}
    ), observations AS (
      SELECT e.column0 AS enclosure, e.column1 AS category, f.elo_delta,
        f.Petting_Zoo_icons, f.has_horse_whisperer,
        {count_expr} AS enclosure_count
      FROM filtered f CROSS JOIN ({config}) e(column0, column1)
    ) SELECT enclosure, category, COUNT(enclosure_count) AS n_total, {', '.join(fields)}
    FROM observations WHERE enclosure_count IS NOT NULL GROUP BY enclosure, category
    ORDER BY CASE category WHEN 'standard' THEN 0 ELSE 1 END, enclosure LIMIT ? OFFSET ?
    """, parameters


def _simple_build_hexes_sql(
    predicates: str, parameters: list[Any], expanded: bool = False,
) -> tuple[str, list[Any]]:
    bucket_rows = (
        [(str(value), str(value), value) for value in range(24)]
        + [("24_plus", "24+", 24)]
        if expanded else
        [("0", "0", 0), ("1_5", "1-5", 1), ("6_11", "6-11", 2),
         ("12_17", "12-17", 3), ("18_23", "18-23", 4), ("24_plus", "24+", 5)]
    )
    buckets = "VALUES " + ",".join(
        f"({_sql_string(key)},{_sql_string(label)},{bucket})"
        for key, label, bucket in bucket_rows
    )
    map_denominators = []
    map_output = []
    for code, full in MAPS[:15]:
        key = _map_key(code); q = _sql_string(full)
        map_denominators.append(f"COUNT(*) FILTER (WHERE Map = {q}) AS denom_{key}")
        map_output.extend([
            f"MAX(m.avg) FILTER (WHERE m.Map = {q}) AS {key}",
            f"COALESCE(MAX(m.count_value) FILTER (WHERE m.Map = {q}), 0) AS count_{key}",
            f"d.denom_{key} AS denom_{key}",
            f"MAX(m.ci_mean) FILTER (WHERE m.Map = {q}) AS {key}_ci_mean",
            f"MAX(m.ci_sd) FILTER (WHERE m.Map = {q}) AS {key}_ci_sd",
            f"COALESCE(MAX(m.ci_n) FILTER (WHERE m.Map = {q}), 0) AS {key}_ci_n",
        ])
    bucket_case = (
        "CASE WHEN empty_hexes BETWEEN 0 AND 23 THEN empty_hexes WHEN empty_hexes >= 24 THEN 24 END"
        if expanded else
        "CASE WHEN empty_hexes = 0 THEN 0 WHEN empty_hexes BETWEEN 1 AND 5 THEN 1 WHEN empty_hexes BETWEEN 6 AND 11 THEN 2 WHEN empty_hexes BETWEEN 12 AND 17 THEN 3 WHEN empty_hexes BETWEEN 18 AND 23 THEN 4 WHEN empty_hexes >= 24 THEN 5 END"
    )
    return f"""
    WITH filtered AS (SELECT Map, TRY_CAST(Empty_hexes AS INTEGER) AS empty_hexes, elo_delta FROM prepared_full_sample_narrow f WHERE {predicates}), classified AS (SELECT *, {bucket_case} AS bucket FROM filtered),
    denominators AS (SELECT COUNT(empty_hexes) AS denom_avg, {', '.join(map_denominators)} FROM classified),
    aggregates AS (
      SELECT bucket, AVG(elo_delta) AS avg, COUNT(*) AS count_avg,
        AVG(elo_delta) AS avg_ci_mean, STDDEV_SAMP(elo_delta) AS avg_ci_sd,
        COUNT(elo_delta) AS avg_ci_n
      FROM classified WHERE bucket IS NOT NULL GROUP BY bucket
    ), by_map AS (
      SELECT bucket, Map, AVG(elo_delta) AS avg, COUNT(*) AS count_value,
        AVG(elo_delta) AS ci_mean, STDDEV_SAMP(elo_delta) AS ci_sd,
        COUNT(elo_delta) AS ci_n
      FROM classified WHERE bucket IS NOT NULL GROUP BY bucket, Map
    )
    SELECT c.column0 AS bucket_key, c.column1 AS bucket_label, c.bucket + 1 AS sort_order,
      a.avg, a.count_avg, d.denom_avg, a.avg_ci_mean, a.avg_ci_sd, a.avg_ci_n,
      {', '.join(map_output)}
    FROM ({buckets}) c(column0, column1, bucket)
    LEFT JOIN aggregates a USING(bucket) LEFT JOIN by_map m USING(bucket)
    CROSS JOIN denominators d
    GROUP BY c.column0, c.column1, c.bucket, a.avg, a.count_avg,
      a.avg_ci_mean, a.avg_ci_sd, a.avg_ci_n, d.denom_avg,
      {', '.join(f'd.denom_{_map_key(code)}' for code, _full in MAPS[:15])}
    ORDER BY sort_order LIMIT ? OFFSET ?
    """, parameters


def _simple_icons_sql(predicates: str, parameters: list[Any]) -> tuple[str, list[Any]]:
    icon_fields = [
        ('Birds','Bird_icons'),('Herbivores','Herbivore_icons'),('Predators','Predator_icons'),('Primates','Primate_icons'),('Reptiles','Reptile_icons'),('Sea Animals','Sea_Animal_icons'),('Bears','Bear_icons'),('Petting Zoo Animals','Petting_Zoo_icons'),('Africa','Africa_icons'),('Americas','Americas_icons'),('Asia','Asia_icons'),('Australia','Australia_icons'),('Europe','Europe_icons'),('Rock','Rock_icons'),('Water','Water_icons'),('Science','Science_icons')]
    buckets = [(f'delta_{v}', f'amount = {v}') for v in range(7)] + [('delta_7_plus','amount >= 7')]
    fields: list[str] = []
    for key, condition in buckets:
        count_key = key.replace('delta_', '')
        n = f"SUM(elo_n) FILTER (WHERE {condition})"
        total = f"SUM(elo_sum) FILTER (WHERE {condition})"
        sumsq = f"SUM(elo_sumsq) FILTER (WHERE {condition})"
        mean = f"{total} / NULLIF({n}, 0)"
        sd = (
            f"SQRT(GREATEST({sumsq} - {total} * {total} / NULLIF({n}, 0), 0) "
            f"/ NULLIF({n} - 1, 0))"
        )
        fields += [
            f"{mean} AS {key}",
            f"COALESCE(SUM(row_n) FILTER (WHERE {condition}), 0) AS count_{count_key}",
            f"{mean} AS {key}_ci_mean",
            f"{sd} AS {key}_ci_sd",
            f"COALESCE({n}, 0) AS {key}_ci_n",
        ]
    config = ','.join(f"('{name}')" for name, _field in icon_fields)
    distributions = " UNION ALL ".join(
        f"""SELECT {_sql_string(name)} AS icon,
          {field}::DOUBLE AS amount, COUNT(*) AS row_n,
          COUNT(elo_delta) AS elo_n, SUM(elo_delta) AS elo_sum,
          SUM(elo_delta * elo_delta) AS elo_sumsq
        FROM filtered WHERE {field} IS NOT NULL
        GROUP BY {field}"""
        for name, field in icon_fields
    )
    return f"""
    WITH filtered AS (
      SELECT f.elo_delta, {', '.join(f'f.{field}' for _name, field in icon_fields)}
      FROM icon_filter_fact_narrow f WHERE {predicates}
    ), distributions AS ({distributions}), stats AS (
      SELECT icon, SUM(amount * row_n) / NULLIF(SUM(row_n), 0) AS amount,
        SUM(row_n) AS n_total, {', '.join(fields)}
      FROM distributions GROUP BY icon
    ), config(icon) AS (VALUES {config})
    SELECT c.icon, s.* EXCLUDE(icon)
    FROM config c LEFT JOIN stats s USING(icon)
    ORDER BY s.amount DESC NULLS LAST, c.icon LIMIT ? OFFSET ?
    """, parameters


def _simple_conservation_projects_sql(predicates: str, parameters: list[Any]) -> tuple[str, list[Any]]:
    map_denominators = []
    output_fields = []
    for code, full in MAPS[:15]:
        key = _map_key(code); q = _sql_string(full)
        map_denominators.append(f"COUNT(*) FILTER (WHERE Map = {q}) AS denom_{key}")
        output_fields += [
            f"MAX(m.avg) FILTER (WHERE m.Map = {q}) AS {key}",
            f"COALESCE(MAX(m.count_value) FILTER (WHERE m.Map = {q}), 0) AS count_{key}",
            f"d.denom_{key}",
            f"MAX(m.ci_mean) FILTER (WHERE m.Map = {q}) AS {key}_ci_mean",
            f"MAX(m.ci_sd) FILTER (WHERE m.Map = {q}) AS {key}_ci_sd",
            f"COALESCE(MAX(m.ci_n) FILTER (WHERE m.Map = {q}), 0) AS {key}_ci_n",
        ]
    return f"""
    WITH filtered AS (
      SELECT Map, elo_delta,
        TRY_CAST(Conservation_project_association_tasks AS INTEGER) AS projects,
        TRY_CAST(Released_animals AS INTEGER) AS releases
      FROM prepared_full_sample_narrow f WHERE {predicates}
    ), classified AS (
      SELECT Map, elo_delta, 'projects' AS subject, projects AS subject_count FROM filtered
      UNION ALL
      SELECT Map, elo_delta, 'releases' AS subject, releases AS subject_count FROM filtered
    ), aggregates AS (
      SELECT subject, subject_count,
        AVG(elo_delta) AS avg, COUNT(*) AS count_avg,
        AVG(elo_delta) AS avg_ci_mean, STDDEV_SAMP(elo_delta) AS avg_ci_sd,
        COUNT(elo_delta) AS avg_ci_n
      FROM classified
      WHERE subject_count BETWEEN 0 AND 7
      GROUP BY subject, subject_count
    ), by_map AS (
      SELECT subject, subject_count, Map, AVG(elo_delta) AS avg,
        COUNT(*) AS count_value, AVG(elo_delta) AS ci_mean,
        STDDEV_SAMP(elo_delta) AS ci_sd, COUNT(elo_delta) AS ci_n
      FROM classified WHERE subject_count BETWEEN 0 AND 7
      GROUP BY subject, subject_count, Map
    ), denominators AS (
      SELECT subject, COUNT(subject_count) AS denom_avg,
        {', '.join(map_denominators)}
      FROM classified WHERE subject_count BETWEEN 0 AND 7 GROUP BY subject
    ), config AS (
      SELECT s.subject, r.range AS count_value
      FROM (VALUES ('projects'), ('releases')) s(subject)
      CROSS JOIN range(0, 8) r
    )
    SELECT c.subject, c.count_value, c.count_value + 1 AS sort_order,
      a.avg, a.count_avg, d.denom_avg, a.avg_ci_mean, a.avg_ci_sd, a.avg_ci_n,
      {', '.join(output_fields)}
    FROM config c LEFT JOIN aggregates a
      ON c.subject = a.subject AND c.count_value = a.subject_count
    LEFT JOIN by_map m
      ON c.subject = m.subject AND c.count_value = m.subject_count
    LEFT JOIN denominators d ON d.subject = c.subject
    GROUP BY c.subject, c.count_value, a.avg, a.count_avg, d.denom_avg,
      a.avg_ci_mean, a.avg_ci_sd, a.avg_ci_n,
      {', '.join(f'd.denom_{_map_key(code)}' for code, _full in MAPS[:15])}
    ORDER BY c.subject, c.count_value LIMIT ? OFFSET ?
    """, parameters


def _simple_conservation_project_rewards_sql(predicates: str, parameters: list[Any]) -> tuple[str, list[Any]]:
    config = ", ".join(
        f"({order}, {_sql_string(label)}, LOWER({_sql_string(raw)}), "
        f"{('NULL' if map_name is None else _sql_string(map_name))}, {_sql_string(group)})"
        for order, label, raw, map_name, group in PROJECT_REWARDS
    )
    delta_fields = [
        "AVG(elo_delta) AS delta_overall", "COUNT(*) AS count_delta_overall",
        "AVG(elo_delta) AS delta_overall_ci_mean",
        "STDDEV_SAMP(elo_delta) AS delta_overall_ci_sd",
        "COUNT(elo_delta) AS delta_overall_ci_n",
    ]
    frequency_fields = [
        "COUNT(DISTINCT table_id || ':' || player) AS freq_overall_numer"
    ]
    for order in range(1, 8):
        condition = f"reward_order = {order}"
        delta_fields.extend([
            f"AVG(elo_delta) FILTER (WHERE {condition}) AS delta_order_{order}",
            f"COUNT(*) FILTER (WHERE {condition}) AS count_delta_order_{order}",
            f"AVG(elo_delta) FILTER (WHERE {condition}) AS delta_order_{order}_ci_mean",
            f"STDDEV_SAMP(elo_delta) FILTER (WHERE {condition}) AS delta_order_{order}_ci_sd",
            f"COUNT(elo_delta) FILTER (WHERE {condition}) AS delta_order_{order}_ci_n",
        ])
        frequency_fields.extend([
            f"COUNT(*) FILTER (WHERE {condition}) AS freq_order_{order}_numer",
            f"COUNT(*) AS freq_order_{order}_denom",
        ])
    return f"""
    WITH configured(sort_order, label, raw_value, map_name, group_name) AS (
      VALUES {config}
    ), filtered AS (SELECT f.table_id, f.player, f.Map, f.elo_delta
      FROM log_player_filter_fact_narrow f WHERE {predicates}),
    events AS (
      SELECT f.table_id, f.player, f.Map, f.elo_delta,
        f.reward AS raw_value, f.reward_order
      FROM project_reward_choice_narrow f WHERE {predicates}
    ), matched AS (
      SELECT c.sort_order, e.* FROM configured c JOIN events e
        ON e.raw_value = c.raw_value AND (c.map_name IS NULL OR e.Map = c.map_name)
    ), event_aggregates AS (
      SELECT sort_order, {', '.join(delta_fields)}, {', '.join(frequency_fields)}
      FROM matched GROUP BY sort_order
    ), denominators AS (
      SELECT c.sort_order,
        COUNT(*) FILTER (WHERE c.map_name IS NULL OR f.Map = c.map_name) AS freq_overall_denom,
        COUNT(*) FILTER (WHERE (c.map_name IS NULL OR f.Map = c.map_name)
          AND NOT (c.raw_value = '2-size' AND f.Map = 'Map 13: Drawing Board')
          AND NOT (c.raw_value = 'snapping' AND f.Map = 'Map T1: Tournament 1')) > 0 AS available
      FROM configured c CROSS JOIN filtered f GROUP BY c.sort_order
    )
    SELECT c.sort_order, c.label, c.group_name, c.map_name AS applicable_map,
      COALESCE(d.available, FALSE) AS available,
      e.* EXCLUDE(sort_order), d.freq_overall_denom
    FROM configured c LEFT JOIN event_aggregates e USING(sort_order)
    LEFT JOIN denominators d USING(sort_order)
    ORDER BY c.sort_order LIMIT ? OFFSET ?
    """, [*parameters, *parameters]


def _simple_workers_sql(predicates: str, parameters: list[Any], two_cp: bool) -> tuple[str, list[Any]]:
    if two_cp:
        source = f"{SOURCE_LOGS_ONE_PER_PLAYER_GAME} JOIN prepared_full_sample_narrow f USING(table_id, player)"
        bucket = "CASE WHEN l.\"2cp_worker\" THEN 2 ELSE 1 END"
        labels = "VALUES (1, 'Upgrade'), (2, 'Worker')"
        valid = "l.\"2cp_worker\" IS NOT NULL"
    else:
        source = "prepared_full_sample_narrow f"
        bucket = "TRY_CAST(f.Association_workers AS INTEGER)"
        labels = "VALUES (1, '1'), (2, '2'), (3, '3'), (4, '4')"
        valid = f"{bucket} BETWEEN 1 AND 4"
    map_denominators = ", ".join(
        f"COUNT(*) FILTER (WHERE Map = {_sql_string(full)}) AS denom_{_map_key(code)}, "
        f"AVG(worker_value) FILTER (WHERE Map = {_sql_string(full)}) AS worker_avg_{_map_key(code)}"
        for code, full in MAPS[:15]
    )
    map_output = ", ".join(
        expression
        for code, full in MAPS[:15]
        for expression in (
            f"MAX(m.avg) FILTER (WHERE m.Map = {_sql_string(full)}) AS {_map_key(code)}",
            f"COALESCE(MAX(m.count_value) FILTER (WHERE m.Map = {_sql_string(full)}), 0) AS count_{_map_key(code)}",
            f"d.denom_{_map_key(code)} AS denom_{_map_key(code)}",
            f"MAX(m.ci_mean) FILTER (WHERE m.Map = {_sql_string(full)}) AS {_map_key(code)}_ci_mean",
            f"MAX(m.ci_sd) FILTER (WHERE m.Map = {_sql_string(full)}) AS {_map_key(code)}_ci_sd",
            f"COALESCE(MAX(m.ci_n) FILTER (WHERE m.Map = {_sql_string(full)}), 0) AS {_map_key(code)}_ci_n",
            f"d.worker_avg_{_map_key(code)} AS worker_avg_{_map_key(code)}",
        )
    )
    worker_avg = "TRY_CAST(f.Association_workers AS DOUBLE)" if not two_cp else "CAST(NULL AS DOUBLE)"
    return f"""
    WITH filtered AS (
      SELECT {bucket} AS bucket, f.Map, f.elo_delta, {worker_avg} AS worker_value
      FROM {source} WHERE {predicates} AND {valid}
    ), config AS ({labels}), denominators AS (
      SELECT COUNT(*) AS denom_avg, AVG(worker_value) AS worker_avg_avg,
        {map_denominators} FROM filtered
    ), overall AS (
      SELECT bucket, AVG(elo_delta) AS avg, COUNT(*) AS count_value,
        AVG(elo_delta) AS ci_mean, STDDEV_SAMP(elo_delta) AS ci_sd,
        COUNT(elo_delta) AS ci_n
      FROM filtered GROUP BY bucket
    ), by_map AS (
      SELECT bucket, Map, AVG(elo_delta) AS avg, COUNT(*) AS count_value,
        AVG(elo_delta) AS ci_mean, STDDEV_SAMP(elo_delta) AS ci_sd,
        COUNT(elo_delta) AS ci_n
      FROM filtered GROUP BY bucket, Map
    )
    SELECT c.column0 AS sort_order, c.column1 AS label, o.avg,
      COALESCE(o.count_value, 0) AS count_avg, d.denom_avg,
      o.ci_mean AS avg_ci_mean, o.ci_sd AS avg_ci_sd,
      COALESCE(o.ci_n, 0) AS avg_ci_n, d.worker_avg_avg, {map_output}
    FROM config c(column0, column1) LEFT JOIN overall o ON o.bucket = c.column0
    LEFT JOIN by_map m ON m.bucket = c.column0 CROSS JOIN denominators d
    GROUP BY c.column0, c.column1, o.avg, o.count_value, o.ci_mean,
      o.ci_sd, o.ci_n, d.denom_avg, d.worker_avg_avg,
      {', '.join(value for code, _full in MAPS[:15] for value in (f'd.denom_{_map_key(code)}', f'd.worker_avg_{_map_key(code)}'))}
    ORDER BY c.column0 LIMIT ? OFFSET ?
    """, parameters


def _simple_metric_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    view = str(request.get("simple_view") or "")
    scope = normalize_scope(request)
    hard_completed = view in {
        "actions_upgrades", "actions_upgrade_order", "actions_upgrades_by_map",
        "build_hexes", "icons_default", "conservation_projects",
        "conservation_project_rewards", "workers_general",
    }
    predicates, parameters = scope_predicates(
        scope, "f", hard_completed=hard_completed
    )
    if view == "actions_upgrades": return _simple_actions_upgrades_sql(predicates, parameters)
    if view == "actions_upgrade_order": return _simple_actions_upgrade_order_sql(predicates, parameters)
    if view == "actions_upgrades_by_map": return _simple_actions_by_map_sql(predicates, parameters)
    if view == "build_enclosures": return _simple_build_enclosures_sql(predicates, parameters)
    if view == "build_hexes": return _simple_build_hexes_sql(
        predicates, parameters, bool(request.get("build_expanded"))
    )
    if view == "icons_default": return _simple_icons_sql(predicates, parameters)
    if view == "conservation_projects": return _simple_conservation_projects_sql(predicates, parameters)
    if view == "conservation_project_rewards": return _simple_conservation_project_rewards_sql(predicates, parameters)
    if view == "workers_general": return _simple_workers_sql(predicates, parameters, False)
    if view == "workers_two_cp_worker": return _simple_workers_sql(predicates, parameters, True)
    raise ValueError(f"unknown local metric view: {view}")


def _completed_tables_sql() -> str:
    return ("f.table_id IN (SELECT table_id FROM prepared_full_sample_narrow GROUP BY table_id "
            "HAVING COUNT(*) = 2 AND SUM(CASE WHEN COALESCE(concede, FALSE) "
            "THEN 1 ELSE 0 END) = 0 AND SUM(CASE WHEN end_game_triggered "
            "IS NOT TRUE THEN 1 ELSE 0 END) = 0)")


def _next_endgames_sql(request: Mapping[str, Any], by_map: bool) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=True)
    map_fields = []
    if by_map:
        for code, full in MAPS[:15]:
            map_fields.append(
                f"AVG(cp) FILTER (WHERE map_name = {_sql_string(full)}) AS {_map_key(code)}"
            )
    return f"""
    WITH scoped AS (
      SELECT f.table_id, f.player, f.Map, f.elo_delta
      FROM prepared_full_sample_narrow f
      WHERE {predicates}
    ), events AS (
      SELECT s.table_id, s.player, s.Map AS map_name, s.elo_delta,
        e.endgame_name AS card_name, e.cp
      FROM scoped s JOIN endgame_score_filter_event_narrow e USING(table_id, player)
      WHERE e.cp BETWEEN 0 AND 4
    )
    SELECT 'endgame' AS card_type, card_name, CAST(NULL AS DOUBLE) AS delta_played,
      CAST(NULL AS DOUBLE) AS delta_in_hand, CAST(NULL AS DOUBLE) AS avg_elo,
      COUNT(*) AS n_played, CAST(NULL AS BIGINT) AS n_seen, CAST(NULL AS DOUBLE) AS playrate_pct,
      ROUND(AVG(cp), 2) AS avg_cp,
      {', '.join(f"100 * COUNT(*) FILTER (WHERE cp = {v}) / NULLIF(COUNT(*), 0) AS cp_{v}_pct" for v in range(5))}
      {(',' if map_fields else '') + ', '.join(map_fields)}
    FROM events GROUP BY card_name ORDER BY avg_cp DESC NULLS LAST, n_played DESC, card_name
    LIMIT ? OFFSET ?
    """, parameters


def _next_maps_h2h_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=False)
    return f"""
    WITH scoped AS (
      SELECT CAST(f.table_id AS VARCHAR) AS table_id, f.player, f.Map AS map_name,
        TRY_CAST(f.Score AS DOUBLE) AS score,
        TRY_CAST(f.Conservation_project_association_tasks AS DOUBLE) AS projects,
        LOWER(TRIM(f.Starting_position_in_first_round)) AS start_position,
        f.elo_delta
      FROM prepared_full_sample_narrow f
      WHERE {predicates} AND EXISTS (SELECT 1 FROM tournament_tables_metadata t
        WHERE t.table_id = f.table_id)
    ), opponents AS (
      SELECT CAST(f.table_id AS VARCHAR) AS table_id, f.player, f.Map AS map_name,
        TRY_CAST(f.Score AS DOUBLE) AS score,
        TRY_CAST(f.Conservation_project_association_tasks AS DOUBLE) AS projects,
        LOWER(TRIM(f.Starting_position_in_first_round)) AS start_position
      FROM prepared_full_sample_narrow f
      WHERE f.is_tournament AND NOT f.is_corrupted_game
    ), valid AS (
      SELECT table_id FROM opponents GROUP BY table_id
      HAVING COUNT(*) = 2 AND COUNT(DISTINCT map_name) = 2 AND COUNT(score) = 2
    ), paired AS (
      SELECT a.map_name AS row_map, b.map_name AS col_map, a.elo_delta,
        CASE WHEN a.score > b.score THEN 1.0 WHEN a.score < b.score THEN 0.0
          WHEN a.projects > b.projects THEN 1.0 WHEN a.projects < b.projects THEN 0.0
          WHEN a.start_position = 'second player' AND b.start_position <> 'second player' THEN 1.0
          WHEN b.start_position = 'second player' AND a.start_position <> 'second player' THEN 0.0 END AS row_win
      FROM scoped a JOIN opponents b USING(table_id) JOIN valid v USING(table_id)
      WHERE a.player <> b.player AND a.map_name <> b.map_name
    ), resolved AS (SELECT * FROM paired WHERE row_win IS NOT NULL),
    rows AS (
      SELECT 'matchup' AS row_type, row_map, col_map, COUNT(*) AS games,
        CAST(SUM(row_win) AS BIGINT) AS wins, CAST(COUNT(*) - SUM(row_win) AS BIGINT) AS losses,
        100 * AVG(row_win) AS win_pct, AVG(elo_delta) AS elo_delta FROM resolved GROUP BY row_map, col_map
      UNION ALL
      SELECT 'overall', row_map, CAST(NULL AS VARCHAR), COUNT(*), CAST(SUM(row_win) AS BIGINT),
        CAST(COUNT(*) - SUM(row_win) AS BIGINT), 100 * AVG(row_win), AVG(elo_delta)
      FROM resolved GROUP BY row_map
    ) SELECT * FROM rows ORDER BY row_type, row_map, col_map LIMIT ? OFFSET ?
    """, parameters


def _next_sponsor_sql(request: Mapping[str, Any], appeal: bool) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=True)
    value_field = "appeal" if appeal else "cp"
    if appeal:
        sponsor_values = SPONSOR_APPEAL_VALUES
    else:
        sponsor_values = {
            sponsor: tuple(range(4)) if sponsor in SPONSOR_CP_0_1_2_3PLUS
            else tuple(range(3)) if sponsor in SPONSOR_CP_0_1_2
            else (0, 1)
            for sponsor in SPONSOR_CP_CARDS
        }
    config = ", ".join(
        f"({_sql_string(sponsor)}, [{', '.join(map(str, values))}])"
        for sponsor, values in sponsor_values.items()
    )
    buckets = range(7) if appeal else range(4)
    bucket_fields = []
    for value in buckets:
        condition = (
            f"value = {value} AND LIST_CONTAINS(possible_values, {value})"
            if appeal or value < 3 else
            "value >= 3 AND LIST_CONTAINS(possible_values, 3)"
        )
        key = f"delta_{value}" if appeal or value < 3 else "delta_3_plus"
        bucket_fields.extend([
            f"AVG(elo_delta) FILTER (WHERE {condition}) AS {key}",
            f"COUNT(*) FILTER (WHERE {condition}) AS count_{key.replace('delta_', '')}",
            f"AVG(elo_delta) FILTER (WHERE {condition}) AS {key}_ci_mean",
            f"STDDEV_SAMP(elo_delta) FILTER (WHERE {condition}) AS {key}_ci_sd",
            f"COUNT(elo_delta) FILTER (WHERE {condition}) AS {key}_ci_n",
        ])
    return f"""
    WITH scoped AS (
      SELECT f.table_id, f.player, f.elo_delta
      FROM prepared_full_sample_narrow f
      WHERE {predicates}
    ), played AS (
      SELECT DISTINCT s.table_id, s.player, s.elo_delta, p.sponsor_name AS sponsor
      FROM scoped s JOIN sponsor_play_filter_event_narrow p USING(table_id, player)
      WHERE p.sponsor_name IN ({', '.join(_sql_string(value) for value in sponsor_values)})
    ), rewards AS (
      SELECT s.table_id, s.player, e.sponsor_name AS sponsor,
        MAX(e.{value_field}) AS value
      FROM scoped s JOIN sponsor_endgame_filter_event_narrow e USING(table_id, player)
      GROUP BY s.table_id, s.player, sponsor
    ), events AS (
      SELECT p.sponsor, p.elo_delta, COALESCE(r.value, 0) AS value
      FROM played p LEFT JOIN rewards r USING(table_id, player, sponsor)
    ), config(sponsor, possible_values) AS (VALUES {config})
    SELECT c.sponsor, c.possible_values, AVG(e.value) AS avg_{value_field}, COUNT(e.sponsor) AS n_played,
      {', '.join(bucket_fields)} FROM config c LEFT JOIN events e USING(sponsor)
      GROUP BY c.sponsor, c.possible_values
      ORDER BY avg_{value_field} DESC NULLS LAST, n_played DESC, sponsor LIMIT ? OFFSET ?
    """, parameters


def predictor_specific_feature_sql() -> str:
    """Generation-time features with the raw producer's per-log-row counts.

    source_logs is an imported physical table. Its generation-local rowid
    distinguishes duplicate player-game log rows without deduplicating the
    analytical population or counting one row's events in another row.
    """
    metadata = _card_attribute_groups()
    list_sql = lambda values: ", ".join(_sql_string(value) for value in values)
    sponsor_cp = list_sql(sorted(value.lower() for value in SPONSOR_CP_CARDS))
    sponsor_appeal = list_sql(sorted(value.lower() for value in SPONSOR_APPEAL_VALUES))
    return f"""
    WITH base AS (
      SELECT f.table_id, f.player, f.is_mw, f.Map, f.game_ended_at,
        l.rowid AS source_log_row_id,
        f.starting_position, f.pre_match_elo, f.opponent_pre_match_elo,
        f.elo_delta, f.is_completed_game, f.is_corrupted_game,
        f.arena_season, f.is_arena_game, f.is_tournament, f.Conservation,
        COALESCE(l.has_round_1_upgrade, FALSE) AS has_round_1_upgrade,
        COALESCE(l.has_round_1_release, FALSE) AS has_round_1_release,
        l.chosen_5cp_bonus, l.chosen_8cp_bonus,
        TRY_CAST(l.association_starting_strength AS INTEGER) AS association_starting_strength,
        TRY_CAST(l.sponsors_starting_strength AS INTEGER) AS sponsors_starting_strength
      FROM prepared_full_sample_narrow f JOIN source_logs l USING(table_id, player)
      WHERE f.is_completed_game AND NOT f.is_corrupted_game
    ), sponsor_per_card AS (
      SELECT b.table_id, b.player, LOWER(TRIM(e.event.sponsor)) AS sponsor,
        MAX(COALESCE(TRY_CAST(e.event.cp AS DOUBLE), 0)) AS cp,
        MAX(COALESCE(TRY_CAST(e.event.appeal AS DOUBLE), 0)) AS appeal
      FROM source_logs b CROSS JOIN UNNEST(b.endgame_from_sponsors) AS e(event)
      GROUP BY b.table_id, b.player, sponsor
    ), sponsor_totals AS (
      SELECT table_id, player,
        SUM(CASE WHEN sponsor IN ({sponsor_cp}) THEN cp ELSE 0 END) AS sponsor_cp,
        SUM(CASE WHEN sponsor IN ({sponsor_appeal}) THEN appeal ELSE 0 END) AS sponsor_appeal
      FROM sponsor_per_card GROUP BY table_id, player
    ), endgame_totals AS (
      SELECT b.table_id, b.player,
        SUM(COALESCE(TRY_CAST(e.score.cp AS DOUBLE), 0)) AS endgame_card_cp
      FROM source_logs b CROSS JOIN UNNEST(b.endgame_scores) AS e(score)
      GROUP BY b.table_id, b.player
    ), animal_features AS (
      SELECT b.rowid AS source_log_row_id,
        COUNT(*) FILTER (WHERE LOWER(TRIM(animal_event.animal))
          IN ({list_sql(metadata['reefer_animals'])})) AS reefer_count,
        COUNT(*) FILTER (WHERE LOWER(TRIM(animal_event.animal))
          IN ({list_sql(metadata['small_animals'])})) AS small_animal_count,
        COUNT(*) FILTER (WHERE LOWER(TRIM(animal_event.animal))
          IN ({list_sql(metadata['medium_animals'])})) AS medium_animal_count,
        COUNT(*) FILTER (WHERE LOWER(TRIM(animal_event.animal))
          IN ({list_sql(metadata['large_animals'])})) AS large_animal_count
      FROM source_logs b CROSS JOIN UNNEST(b.played_animals) a(animal_event)
      GROUP BY b.rowid
    ), association_features AS (
      SELECT b.rowid AS source_log_row_id,
        BOOL_OR(TRY_CAST(action_event.round AS INTEGER) = 1 AND action_event.project IS NOT NULL) AS round_1_project,
        COUNT(*) FILTER (WHERE TRY_CAST(action_event.round AS INTEGER) = 1) >= 2 AS round_1_two_association
      FROM source_logs b CROSS JOIN UNNEST(b.association_action_history) a(action_event)
      GROUP BY b.rowid
    ), cp_features AS (
      SELECT b.rowid AS source_log_row_id,
        MIN(TRY_CAST(cp_event."move" AS INTEGER)) FILTER (WHERE TRY_CAST(cp_event.cp AS INTEGER) >= 5) AS first_5_move,
        MIN(TRY_CAST(cp_event."move" AS INTEGER)) FILTER (WHERE TRY_CAST(cp_event.cp AS INTEGER) >= 8) AS first_8_move
      FROM source_logs b CROSS JOIN UNNEST(b.cp_history) h(cp_event)
      GROUP BY b.rowid
    ), opening_features AS (
      SELECT b.rowid AS source_log_row_id,
        COUNT(*) FILTER (WHERE LOWER(TRIM(card))
          IN ({list_sql(metadata['project_cards'])})) = 0 AS no_project_opening,
        COUNT(*) FILTER (WHERE LOWER(TRIM(card))
          IN ({list_sql(metadata['sponsor_cards'])})) = 0 AS no_sponsor_opening
      FROM source_logs b CROSS JOIN UNNEST(b.opening_cards) c(card)
      GROUP BY b.rowid
    )
    SELECT b.* EXCLUDE(source_log_row_id),
      COALESCE(st.sponsor_cp, 0) + COALESCE(et.endgame_card_cp, 0) AS endgame_cp,
      3 * (COALESCE(st.sponsor_cp, 0) + COALESCE(et.endgame_card_cp, 0))
        + COALESCE(st.sponsor_appeal, 0) AS endgame_points,
      TRY_CAST(b.Conservation AS DOUBLE) - COALESCE(st.sponsor_cp, 0)
        - COALESCE(et.endgame_card_cp, 0) AS ingame_cp,
      COALESCE(a.reefer_count, 0) AS reefer_count,
      COALESCE(a.small_animal_count, 0) AS small_animal_count,
      COALESCE(a.medium_animal_count, 0) AS medium_animal_count,
      COALESCE(a.large_animal_count, 0) AS large_animal_count,
      COALESCE(assoc.round_1_project, FALSE) AS round_1_project,
      COALESCE(assoc.round_1_two_association, FALSE) AS round_1_two_association,
      cp.first_5_move, cp.first_8_move,
      COALESCE(o.no_project_opening, TRUE) AS no_project_opening,
      COALESCE(o.no_sponsor_opening, TRUE) AS no_sponsor_opening
    FROM base b LEFT JOIN sponsor_totals st USING(table_id, player)
    LEFT JOIN endgame_totals et USING(table_id, player)
    LEFT JOIN animal_features a USING(source_log_row_id)
    LEFT JOIN association_features assoc USING(source_log_row_id)
    LEFT JOIN cp_features cp USING(source_log_row_id)
    LEFT JOIN opening_features o USING(source_log_row_id)
    """


def _next_predictor_sql(request: Mapping[str, Any], predictor_view: str) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicate_alias = "f" if predictor_view == "specific" else "p"
    predicates, parameters = scope_predicates(scope, predicate_alias, hard_completed=True)
    if predictor_view == "general":
        fields = [
            ("More conservation", "Conservation"), ("More appeal", "Appeal"),
            ("More reputation", "Reputation"), ("More conservation projects", "Conservation_project_association_tasks"),
            ("More release projects", "Released_animals"), ("More money gained", "Money_gained"),
            ("More money gained through income", "Money_gained_through_income"),
            ("More money spent on animals", "Money_spent_on_animals"),
            ("More money spent on enclosures", "Money_spent_on_enclosures"),
            ("More money spent on donations", "Money_spent_on_donations"),
            ("More money spent on playing from range", "Money_spent_for_playing_cards_from_reputation_range"),
            ("More breaks triggered", "Number_of_breaks_triggered"), ("More sponsors played", "Played_sponsors"),
            ("More animals played", "Played_animals"), ("More cards drawn", "Cards_drawn_from_deck"),
            ("More cards snapped", "Snapped_cards"), ("More cards discarded", "Discarded_cards"),
            ("More Animals actions", "Animals_actions"), ("More Association actions", "Association_actions"),
            ("More Build actions", "Build_actions"), ("More Cards actions", "Cards_actions"),
            ("More Sponsors actions", "Sponsors_actions"), ("More determinations", "determinations"),
            ("More X-backs", "X_Tokens_gained_instead_of_action"), ("More X-tokens gained", "X_Tokens_gained"),
            ("More X-tokens used", "X_Tokens_used"), ("More empty hexes", "Empty_hexes"),
            ("More pavilions built", "Built_pavilions"), ("More kiosks built", "Built_kiosks"),
            ("More special buildings", "Built_unique_buildings"),
        ]
    elif predictor_view == "icon":
        fields = [(name, column) for name, column in [
            ("Birds", "Bird_icons"), ("Herbivores", "Herbivore_icons"), ("Predators", "Predator_icons"),
            ("Primates", "Primate_icons"), ("Reptiles", "Reptile_icons"), ("Sea Animals", "Sea_Animal_icons"),
            ("Bears", "Bear_icons"), ("Petting Zoo Animals", "Petting_Zoo_icons"), ("Africa", "Africa_icons"),
            ("Americas", "Americas_icons"), ("Asia", "Asia_icons"), ("Australia", "Australia_icons"),
            ("Europe", "Europe_icons"), ("Rock", "Rock_icons"), ("Water", "Water_icons"), ("Science", "Science_icons")]]
    else:
        first_5 = "me.first_5_move IS NOT NULL AND (opp.first_5_move IS NULL OR me.first_5_move < opp.first_5_move)"
        first_8 = "me.first_8_move IS NOT NULL AND (opp.first_8_move IS NULL OR me.first_8_move < opp.first_8_move)"
        condition_by_key = {
            "more_endgame_points": "me.endgame_points > opp.endgame_points",
            "more_endgame_cp": "me.endgame_cp > opp.endgame_cp",
            "more_ingame_cp": "me.ingame_cp > opp.ingame_cp",
            "more_reefers": "me.reefer_count > opp.reefer_count",
            "more_small_animals": "me.small_animal_count > opp.small_animal_count",
            "more_medium_animals": "me.medium_animal_count > opp.medium_animal_count",
            "more_large_animals": "me.large_animal_count > opp.large_animal_count",
            "round_1_upgrade": "me.has_round_1_upgrade",
            "round_1_project": "me.round_1_project",
            "round_1_release": "me.has_round_1_release",
            "round_1_two_association": "me.round_1_two_association",
            "first_to_5": first_5,
            "first_to_5_bonus": (
                f"({first_5}) AND LOWER(TRIM(COALESCE(me.chosen_5cp_bonus, ''))) "
                "IN ('1 university', '1 partner-zoo') AND "
                "LOWER(TRIM(COALESCE(opp.chosen_5cp_bonus, ''))) "
                "NOT IN ('1 university', '1 partner-zoo')"
            ),
            "first_to_8": first_8,
            "first_to_8_bonus": (
                f"({first_8}) AND LOWER(TRIM(COALESCE(me.chosen_8cp_bonus, ''))) "
                "IN ('1 university', '1 partner-zoo') AND "
                "LOWER(TRIM(COALESCE(opp.chosen_8cp_bonus, ''))) "
                "NOT IN ('1 university', '1 partner-zoo')"
            ),
            "no_project_opening": "me.no_project_opening",
            "no_sponsor_opening": "me.no_sponsor_opening",
            "no_sponsor_sponsors_5": (
                "me.no_sponsor_opening AND me.sponsors_starting_strength = 5"
            ),
            "no_sponsor_second_assoc_2_sponsors_5": (
                "me.no_sponsor_opening AND me.starting_position = 'Second player' "
                "AND me.association_starting_strength = 2 "
                "AND me.sponsors_starting_strength = 5"
            ),
        }
        stat_fields = []
        output_rows = []
        for index, (label, key, mw_only) in enumerate(PREDICTOR_SPECIFIC_CONDITIONS, 1):
            if mw_only and scope.get('is_mw') == 0:
                continue
            eligible = "me.is_mw = 1" if mw_only else "TRUE"
            condition = f"({eligible}) AND ({condition_by_key[key]})"
            prefix = f"c{index}"
            stat_fields.extend([
                f"AVG(me.elo_delta) FILTER (WHERE {condition}) AS {prefix}_delta",
                f"COUNT(*) FILTER (WHERE {condition}) AS {prefix}_count",
                f"COUNT(*) FILTER (WHERE {eligible}) AS {prefix}_denominator",
                f"AVG(me.elo_delta) FILTER (WHERE {condition}) AS {prefix}_ci_mean",
                f"STDDEV_SAMP(me.elo_delta) FILTER (WHERE {condition}) AS {prefix}_ci_sd",
                f"COUNT(me.elo_delta) FILTER (WHERE {condition}) AS {prefix}_ci_n",
            ])
            output_rows.append(
                f"SELECT {index} AS sort_order, {_sql_string(label)} AS condition, "
                f"{prefix}_delta AS delta, {prefix}_count AS count, "
                f"{prefix}_denominator AS denominator, {prefix}_ci_mean AS delta_ci_mean, "
                f"{prefix}_ci_sd AS delta_ci_sd, {prefix}_ci_n AS delta_ci_n FROM stats"
            )
        return f"""
        WITH values_by_player AS (
          SELECT * FROM predictor_specific_player_fact_narrow
        ), stats AS (
          SELECT {', '.join(stat_fields)}
          FROM values_by_player me JOIN values_by_player opp
            ON me.table_id = opp.table_id AND me.player <> opp.player
          -- Sidebar scope selects the focal observation, never its opponent.
          WHERE {predicates.replace('f.', 'me.')}
        )
        {' UNION ALL '.join(output_rows)}
        ORDER BY sort_order LIMIT ? OFFSET ?
        """, parameters
    mask_column = "general_mask" if predictor_view == "general" else "icon_mask"
    config = ", ".join(
        f"({index}, {_sql_string(label)}, {1 << (index - 1)}::UBIGINT)"
        for index, (label, _field) in enumerate(fields, 1)
    )
    return f"""
    WITH distributions AS (
      SELECT p.{mask_column}, COUNT(*) AS row_n, COUNT(p.elo_delta) AS elo_n,
        SUM(p.elo_delta) AS elo_sum, SUM(p.elo_delta * p.elo_delta) AS elo_sumsq
      FROM predictor_pair_fact_narrow p
      WHERE {predicates}
      GROUP BY p.{mask_column}
    ), config(sort_order, condition, mask_bit) AS (VALUES {config}),
    stats AS (
      SELECT c.sort_order, SUM(p.row_n) AS row_n, SUM(p.elo_n) AS elo_n,
        SUM(p.elo_sum) AS elo_sum, SUM(p.elo_sumsq) AS elo_sumsq
      FROM distributions p JOIN config c ON (p.{mask_column} & c.mask_bit) <> 0
      GROUP BY c.sort_order
    ), denominator AS (SELECT COALESCE(SUM(row_n), 0) AS denominator FROM distributions)
    SELECT c.sort_order, c.condition, s.elo_sum / NULLIF(s.elo_n, 0) AS delta,
      COALESCE(s.row_n, 0) AS count, d.denominator,
      s.elo_sum / NULLIF(s.elo_n, 0) AS delta_ci_mean,
      SQRT(GREATEST(s.elo_sumsq - s.elo_sum * s.elo_sum / NULLIF(s.elo_n, 0), 0)
        / NULLIF(s.elo_n - 1, 0)) AS delta_ci_sd,
      COALESCE(s.elo_n, 0) AS delta_ci_n
    FROM config c LEFT JOIN stats s USING(sort_order) CROSS JOIN denominator d
    ORDER BY sort_order LIMIT ? OFFSET ?
    """, parameters


def _next_actions_starting_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=True)
    return f"""
    WITH paired AS (
      SELECT f.elo_delta, f.association_strength, f.build_strength,
        f.cards_strength, f.sponsors_strength, f.higher_association,
        f.higher_build, f.higher_cards, f.higher_sponsors, f.starting_position
      FROM action_starting_fact_narrow f
      WHERE {predicates}
    ),
    observations AS (
      SELECT 'strength' AS section, 1 AS sort_order, 'Association' AS label,
        association_strength AS bucket, CAST(NULL AS BOOLEAN) AS condition_met, elo_delta FROM paired
      UNION ALL SELECT 'strength', 2, 'Build', build_strength, NULL, elo_delta FROM paired
      UNION ALL SELECT 'strength', 3, 'Cards', cards_strength, NULL, elo_delta FROM paired
      UNION ALL SELECT 'strength', 4, 'Sponsors', sponsors_strength, NULL, elo_delta FROM paired
      UNION ALL SELECT 'comparison', 1, 'Higher Association strength', NULL,
        higher_association, elo_delta FROM paired
      UNION ALL SELECT 'comparison', 2, 'Higher Build strength', NULL,
        higher_build, elo_delta FROM paired
      UNION ALL SELECT 'comparison', 3, 'Higher Cards strength', NULL,
        higher_cards, elo_delta FROM paired
      UNION ALL SELECT 'comparison', 4, 'Higher Sponsors strength', NULL,
        higher_sponsors, elo_delta FROM paired
      UNION ALL SELECT 'comparison', 5, 'First player', NULL,
        starting_position = 'First player', elo_delta FROM paired
    ), strength AS (
    SELECT section, sort_order, label,
      AVG(elo_delta) FILTER (WHERE bucket = 2) AS delta_2, COUNT(*) FILTER (WHERE bucket = 2) AS count_2,
      AVG(elo_delta) FILTER (WHERE bucket = 2) AS delta_2_ci_mean, STDDEV_SAMP(elo_delta) FILTER (WHERE bucket = 2) AS delta_2_ci_sd,
      COUNT(elo_delta) FILTER (WHERE bucket = 2) AS delta_2_ci_n,
      AVG(elo_delta) FILTER (WHERE bucket = 3) AS delta_3, COUNT(*) FILTER (WHERE bucket = 3) AS count_3,
      AVG(elo_delta) FILTER (WHERE bucket = 3) AS delta_3_ci_mean, STDDEV_SAMP(elo_delta) FILTER (WHERE bucket = 3) AS delta_3_ci_sd,
      COUNT(elo_delta) FILTER (WHERE bucket = 3) AS delta_3_ci_n,
      AVG(elo_delta) FILTER (WHERE bucket = 4) AS delta_4, COUNT(*) FILTER (WHERE bucket = 4) AS count_4,
      AVG(elo_delta) FILTER (WHERE bucket = 4) AS delta_4_ci_mean, STDDEV_SAMP(elo_delta) FILTER (WHERE bucket = 4) AS delta_4_ci_sd,
      COUNT(elo_delta) FILTER (WHERE bucket = 4) AS delta_4_ci_n,
      AVG(elo_delta) FILTER (WHERE bucket = 5) AS delta_5, COUNT(*) FILTER (WHERE bucket = 5) AS count_5,
      AVG(elo_delta) FILTER (WHERE bucket = 5) AS delta_5_ci_mean, STDDEV_SAMP(elo_delta) FILTER (WHERE bucket = 5) AS delta_5_ci_sd,
      COUNT(elo_delta) FILTER (WHERE bucket = 5) AS delta_5_ci_n
    FROM observations WHERE section = 'strength' GROUP BY section, sort_order, label
    ), comparison AS (
    SELECT section, sort_order, label, AVG(elo_delta) FILTER (WHERE condition_met), COUNT(*) FILTER (WHERE condition_met),
      AVG(elo_delta) FILTER (WHERE condition_met), STDDEV_SAMP(elo_delta) FILTER (WHERE condition_met), COUNT(elo_delta) FILTER (WHERE condition_met),
      NULL, NULL, NULL, NULL, NULL,
      NULL, NULL, NULL, NULL, NULL,
      NULL, NULL, NULL, NULL, NULL FROM observations WHERE section = 'comparison'
      GROUP BY section, sort_order, label
    )
    SELECT * FROM strength UNION ALL SELECT * FROM comparison
    ORDER BY section DESC, sort_order LIMIT ? OFFSET ?
    """, parameters


def _next_conservation_cp_rewards_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "me", hard_completed=False)
    configured = ", ".join(
        f"({order}, {_sql_string(label)}, {_sql_string(raw)}, {str(mw_only).upper()})"
        for order, label, raw, mw_only in CP_REWARDS
    )
    aggregate_columns = []
    for key, map_name in [("overall", None)] + [
        (_map_key(code), full_name) for code, full_name in MAPS[:15]
    ]:
        condition = "table_id IS NOT NULL" if map_name is None else (
            f"table_id IS NOT NULL AND map_name = {_sql_string(map_name)}"
        )
        aggregate_columns.extend([
            f"AVG(elo_delta) FILTER (WHERE {condition}) AS delta_{key}",
            f"COUNT(*) FILTER (WHERE {condition}) AS count_delta_{key}",
            f"AVG(elo_delta) FILTER (WHERE {condition}) AS delta_{key}_ci_mean",
            f"STDDEV_SAMP(elo_delta) FILTER (WHERE {condition}) AS delta_{key}_ci_sd",
            f"COUNT(elo_delta) FILTER (WHERE {condition}) AS delta_{key}_ci_n",
        ])
        aggregate_columns.extend([
            f"COUNT(*) FILTER (WHERE {condition} AND chosen) AS freq_{key}_numer",
            f"COUNT(*) FILTER (WHERE {condition}) AS freq_{key}_denom",
        ])
    select_columns = ",\n      ".join(aggregate_columns)
    return f"""
    WITH configured AS (
      SELECT * FROM (VALUES {configured})
        c(sort_order, label, raw_value, mw_only)
      WHERE mw_only = FALSE OR CAST(? AS INTEGER) = 1
    ),
    base AS (
      SELECT f.*, c.chosen_5cp_bonus, c.chosen_8cp_bonus,
        c.my_5_move, c.my_8_move
      FROM prepared_full_sample_narrow f
      JOIN conservation_cp_player_narrow c USING(table_id, player)
    ), paired AS (
      SELECT me.*,
        opp.my_5_move AS opp_5_move, opp.my_8_move AS opp_8_move
      FROM base me LEFT JOIN conservation_cp_player_narrow opp
        ON me.table_id = opp.table_id AND me.player <> opp.player
      WHERE {predicates}
    ),
    chosen_base AS (
      SELECT table_id, player, Map AS map_name, elo_delta, 5 AS threshold,
        LOWER(TRIM(chosen_5cp_bonus)) AS raw_value
      FROM paired WHERE chosen_5cp_bonus IS NOT NULL
      UNION ALL
      SELECT table_id, player, Map, elo_delta, 8, LOWER(TRIM(chosen_8cp_bonus))
      FROM paired WHERE chosen_8cp_bonus IS NOT NULL
    ), chosen_scoped AS (
      SELECT CAST(threshold AS VARCHAR) AS scope, table_id, player, map_name, elo_delta, raw_value
      FROM chosen_base
      UNION ALL
      SELECT 'combined', table_id, player, map_name, ANY_VALUE(elo_delta), raw_value
      FROM chosen_base GROUP BY table_id, player, map_name, raw_value
    ), opportunity_raw AS (
      SELECT p.table_id, p.player, p.Map AS map_name, o.threshold, o.raw_value,
        CASE o.threshold
          WHEN 5 THEN p.chosen_5cp_bonus = o.raw_value
          ELSE p.chosen_8cp_bonus = o.raw_value
        END AS chosen
      FROM paired p JOIN conservation_cp_opportunity_narrow o USING(table_id, player)
      WHERE (o.threshold = 5 AND p.my_5_move IS NOT NULL
              AND (p.opp_5_move IS NULL OR p.my_5_move < p.opp_5_move))
         OR (o.threshold = 8 AND p.my_8_move IS NOT NULL
              AND (p.opp_8_move IS NULL OR p.my_8_move < p.opp_8_move))
    ), opportunity_base AS (
      SELECT table_id, player, map_name, threshold, raw_value, BOOL_OR(chosen) AS chosen
      FROM opportunity_raw GROUP BY table_id, player, map_name, threshold, raw_value
    ), opportunity_scoped AS (
      SELECT CAST(threshold AS VARCHAR) AS scope, table_id, player, map_name, raw_value, chosen
      FROM opportunity_base
      UNION ALL SELECT 'combined', table_id, player, map_name, raw_value, chosen FROM opportunity_base
    ), scopes(scope) AS (VALUES ('5'), ('8'), ('combined')),
    delta_aggregates AS (
      SELECT c.sort_order, s.scope,
        {', '.join(column for column in aggregate_columns if 'freq_' not in column)}
      FROM configured c CROSS JOIN scopes s LEFT JOIN chosen_scoped d
        ON d.scope = s.scope AND d.raw_value = c.raw_value
      GROUP BY c.sort_order, s.scope
    ), frequency_aggregates AS (
      SELECT c.sort_order, s.scope,
        {', '.join(column for column in aggregate_columns if 'freq_' in column)}
      FROM configured c CROSS JOIN scopes s LEFT JOIN opportunity_scoped d
        ON d.scope = s.scope AND d.raw_value = c.raw_value
      GROUP BY c.sort_order, s.scope
    )
    SELECT c.sort_order, c.label, c.mw_only, s.scope,
      d.* EXCLUDE(sort_order, scope), f.* EXCLUDE(sort_order, scope)
    FROM configured c CROSS JOIN scopes s
    LEFT JOIN delta_aggregates d USING(sort_order, scope)
    LEFT JOIN frequency_aggregates f USING(sort_order, scope)
    ORDER BY s.scope, c.sort_order LIMIT ? OFFSET ?
    """, [scope.get("is_mw"), *parameters]


def _next_route_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    view = str(request.get("next_view") or "")
    if view == "endgames_cp_distribution": return _next_endgames_sql(request, False)
    if view == "endgames_cp_by_map": return _next_endgames_sql(request, True)
    if view == "maps_tournament_h2h": return _next_maps_h2h_sql(request)
    if view == "sponsor_endgames_cp": return _next_sponsor_sql(request, False)
    if view == "sponsor_endgames_appeal": return _next_sponsor_sql(request, True)
    if view in {"predictors_general", "predictors_icon", "predictors_specific"}:
        return _next_predictor_sql(request, view.removeprefix("predictors_"))
    if view == "actions_starting_position": return _next_actions_starting_sql(request)
    if view == "conservation_cp_rewards": return _next_conservation_cp_rewards_sql(request)
    raise ValueError(f"unknown local route view: {view}")


def _next_home_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request, require_dataset=False)
    predicates, parameters = scope_predicates(
        scope, "f", hard_completed=False, include_corrupted=True
    )
    return f"""
    WITH scoped AS (
      SELECT f.* FROM home_filter_fact_narrow f WHERE {predicates}
    ), totals AS (
      SELECT COUNT(DISTINCT table_id) AS games_indexed,
        COUNT(DISTINCT table_id) FILTER (WHERE has_log) AS games_logged,
        SUM(COALESCE(played_animals, 0)) AS animals_played,
        SUM(COALESCE(played_sponsors, 0)) AS sponsors_played,
        SUM(COALESCE(projects_supported, 0)) AS projects_supported,
        SUM(COALESCE(breaks_triggered, 0)) AS breaks_triggered,
        SUM(COALESCE(x_tokens_gained, 0)) AS x_tokens_gained,
        SUM(emus_played) AS emus_played,
        SUM(two_cp_workers_taken) AS two_cp_workers_taken,
        SUM(empty_petting_zoos_played) AS empty_petting_zoos_played,
        SUM(free_unis_and_partner_zoos) AS free_unis_and_partner_zoos,
        SUM(bignose_project_blocks) AS bignose_project_blocks
      FROM scoped
    )
    SELECT metric, value FROM totals CROSS JOIN (VALUES
      ('games_indexed', games_indexed), ('animals_played', animals_played),
      ('sponsors_played', sponsors_played), ('projects_supported', projects_supported),
      ('breaks_triggered', breaks_triggered), ('x_tokens_gained', x_tokens_gained),
      ('games_logged', games_logged), ('emus_played', emus_played),
      ('two_cp_workers_taken', two_cp_workers_taken),
      ('empty_petting_zoos_played', empty_petting_zoos_played),
      ('free_unis_and_partner_zoos', free_unis_and_partner_zoos),
      ('bignose_project_blocks', bignose_project_blocks)
    ) m(metric, value)
    LIMIT ? OFFSET ?
    """, parameters


def _next_opening_hand_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False)
    excluded = ", ".join(_sql_string(value) for value in sorted(EXCLUDED_SUMMARY_PROJECTS))
    return f"""
    WITH scoped AS (
      SELECT g.table_id, g.player, g.elo_delta, g.pre_match_elo
      FROM prepared_full_sample_narrow g WHERE {predicates}
    ), card_universe AS (
      SELECT card_name, ANY_VALUE(card_type) AS card_type
      FROM card_play_narrow
      WHERE NOT (card_type = 'project' AND LOWER(card_name) IN ({excluded}))
      GROUP BY card_name
    ), opening AS (
      SELECT h.table_id, h.player, h.card_name, h.kept,
        s.elo_delta, s.pre_match_elo
      FROM opening_hand_narrow h JOIN scoped s USING(table_id, player)
      WHERE LOWER(h.card_name) NOT IN ({excluded})
    ), dealt AS (
      SELECT card_name, COUNT(*) AS n_dealt,
        ROUND(AVG(elo_delta), 3) AS delta_dealt,
        AVG(elo_delta) AS delta_dealt_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_dealt_ci_sd,
        COUNT(elo_delta) AS delta_dealt_ci_n
      FROM opening GROUP BY card_name
    ), kept AS (
      SELECT card_name, COUNT(*) AS n_kept,
        ROUND(AVG(elo_delta), 3) AS delta_kept,
        AVG(elo_delta) AS delta_kept_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_kept_ci_sd,
        COUNT(elo_delta) AS delta_kept_ci_n,
        ROUND(AVG(pre_match_elo), 0) AS avg_elo
      FROM opening WHERE kept GROUP BY card_name
    )
    SELECT u.card_name, u.card_type,
      COALESCE(d.delta_dealt, 0) AS delta_played,
      COALESCE(k.delta_kept, 0) AS delta_in_hand,
      d.delta_dealt_ci_mean AS delta_played_ci_mean,
      d.delta_dealt_ci_sd AS delta_played_ci_sd,
      COALESCE(d.delta_dealt_ci_n, 0) AS delta_played_ci_n,
      k.delta_kept_ci_mean AS delta_in_hand_ci_mean,
      k.delta_kept_ci_sd AS delta_in_hand_ci_sd,
      COALESCE(k.delta_kept_ci_n, 0) AS delta_in_hand_ci_n,
      COALESCE(k.avg_elo, 0) AS avg_elo,
      COALESCE(k.n_kept, 0) AS n_played,
      COALESCE(d.n_dealt, 0) AS n_seen,
      CASE WHEN COALESCE(d.n_dealt, 0) = 0 THEN 0
        ELSE ROUND(100.0 * COALESCE(k.n_kept, 0) / d.n_dealt, 2)
      END AS playrate_pct,
      CAST(NULL AS DOUBLE) AS avg_cp
    FROM card_universe u
    LEFT JOIN dealt d USING(card_name)
    LEFT JOIN kept k USING(card_name)
    ORDER BY u.card_type, playrate_pct DESC, n_seen DESC, u.card_name
    LIMIT ? OFFSET ?
    """, parameters


def _next_card_played_sql(request: Mapping[str, Any], view: str) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False)
    round_predicate = ""
    selected_rounds = request.get("rounds") or request.get("selected_rounds") or []
    if isinstance(selected_rounds, list) and selected_rounds:
        values = [str(value) for value in selected_rounds]
        exact = [int(value) for value in values if value.isdigit()]
        round_parts = [f"cp.played_round IN ({', '.join(str(v) for v in exact)})"] if exact else []
        if "6+" in values:
            round_parts.append("cp.played_round >= 6")
        if round_parts:
            round_predicate = " AND (" + " OR ".join(round_parts) + ")"
    common = f"""
      SELECT cp.card_name, cp.card_type, cp.map_name, cp.played_round,
        g.table_id, g.player, g.elo_delta, g.pre_match_elo
      FROM card_play_narrow cp JOIN prepared_full_sample_narrow g USING(table_id, player)
      WHERE {predicates}{round_predicate}
    """
    if view == "card_map":
        return f"""
        WITH played AS ({common}), individual AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type, AVG(elo_delta) AS delta_general,
            STDDEV_SAMP(elo_delta) AS component_1_ci_sd,
            COUNT(elo_delta) AS component_1_ci_n
          FROM played GROUP BY card_name
        ), grouped AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type, map_name,
            AVG(elo_delta) AS delta_map, AVG(pre_match_elo) AS avg_elo, COUNT(*) AS n_played,
            STDDEV_SAMP(elo_delta) AS delta_map_ci_sd, COUNT(elo_delta) AS delta_map_ci_n
          FROM played GROUP BY card_name, map_name
        )
        SELECT p.card_name, p.card_type, p.map_name, i.delta_general,
          p.delta_map, p.delta_map AS delta_map_ci_mean, p.delta_map_ci_sd,
          p.delta_map_ci_n, p.delta_map - i.delta_general AS interaction,
          p.avg_elo, p.n_played,
          i.delta_general AS component_1_ci_mean,
          i.component_1_ci_sd, i.component_1_ci_n,
          p.delta_map AS component_2_ci_mean,
          p.delta_map_ci_sd AS component_2_ci_sd,
          p.delta_map_ci_n AS component_2_ci_n
        FROM grouped p JOIN individual i USING(card_name)
        ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, map_name
        LIMIT ? OFFSET ?
        """, parameters
    return f"""
    WITH played AS ({common}), individual AS (
      SELECT card_name, ANY_VALUE(card_type) AS card_type, AVG(elo_delta) AS delta_general,
        STDDEV_SAMP(elo_delta) AS component_1_ci_sd,
        COUNT(elo_delta) AS component_1_ci_n
      FROM played GROUP BY card_name
    ), grouped AS (
      SELECT card_name, ANY_VALUE(card_type) AS card_type,
        CASE WHEN played_round >= 6 THEN '6+' ELSE CAST(played_round AS VARCHAR) END AS round_name,
        AVG(elo_delta) AS delta_round, AVG(pre_match_elo) AS avg_elo, COUNT(*) AS n_played,
        STDDEV_SAMP(elo_delta) AS delta_round_ci_sd, COUNT(elo_delta) AS delta_round_ci_n
      FROM played WHERE played_round IS NOT NULL GROUP BY card_name, round_name
    )
    SELECT p.card_name, p.card_type, p.round_name, i.delta_general,
      p.delta_round, p.delta_round AS delta_round_ci_mean, p.delta_round_ci_sd,
      p.delta_round_ci_n, p.delta_round - i.delta_general AS interaction,
      p.avg_elo, p.n_played,
      i.delta_general AS component_1_ci_mean,
      i.component_1_ci_sd, i.component_1_ci_n,
      p.delta_round AS component_2_ci_mean,
      p.delta_round_ci_sd AS component_2_ci_sd,
      p.delta_round_ci_n AS component_2_ci_n
    FROM grouped p JOIN individual i USING(card_name)
    ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, round_name
    LIMIT ? OFFSET ?
    """, parameters


def _next_card_endgame_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False)
    return f"""
    WITH scoped AS (
      SELECT g.table_id, g.player, g.elo_delta, g.pre_match_elo
      FROM prepared_full_sample_narrow g WHERE {predicates}
    ), card_counts AS (
      SELECT cp.table_id, cp.player, cp.card_name, ANY_VALUE(cp.card_type) AS card_type,
        COUNT(*) AS card_n, ANY_VALUE(s.elo_delta) AS elo_delta,
        ANY_VALUE(s.pre_match_elo) AS pre_match_elo
      FROM card_play_narrow cp JOIN scoped s USING(table_id, player)
      GROUP BY cp.table_id, cp.player, cp.card_name
    ), eligible_games AS (
      SELECT table_id, player, SUM(card_n) AS total_card_n
      FROM card_counts GROUP BY table_id, player
    ), endgame_counts AS (
      SELECT s.table_id, s.player, TRIM(e.score.endgame) AS endgame_name,
        COUNT(*) AS event_n, COUNT(*) * eg.total_card_n AS endgame_n,
        ANY_VALUE(s.elo_delta) AS elo_delta
      FROM eligible_games eg JOIN scoped s USING(table_id, player)
      JOIN source_logs l USING(table_id, player)
      CROSS JOIN UNNEST(COALESCE(l.endgame_scores, [])) AS e(score)
      WHERE e.score.endgame IS NOT NULL
      GROUP BY s.table_id, s.player, endgame_name, eg.total_card_n
    ), pair_agg AS (
      SELECT c.card_name, c.card_type, e.endgame_name,
        SUM(c.card_n * e.event_n) AS n_played,
        SUM(c.card_n * e.event_n * c.elo_delta) AS delta_sum,
        SUM(c.card_n * e.event_n * c.elo_delta * c.elo_delta) AS delta_sumsq,
        SUM(c.card_n * e.event_n * c.pre_match_elo) AS elo_sum
      FROM card_counts c JOIN endgame_counts e USING(table_id, player)
      GROUP BY c.card_name, c.card_type, e.endgame_name
    ), cards AS (
      SELECT card_name, ANY_VALUE(card_type) AS card_type,
        SUM(card_n) AS n_card, SUM(card_n * elo_delta) AS card_sum,
        SUM(card_n * elo_delta * elo_delta) AS card_sumsq
      FROM card_counts GROUP BY card_name
    ), endgames AS (
      SELECT endgame_name, SUM(endgame_n) AS n_endgame,
        SUM(endgame_n * elo_delta) AS endgame_sum,
        SUM(endgame_n * elo_delta * elo_delta) AS endgame_sumsq
      FROM endgame_counts GROUP BY endgame_name
    ), pairs AS (
      SELECT p.*, p.delta_sum / p.n_played AS delta_actual,
        SQRT(GREATEST(p.delta_sumsq - p.delta_sum * p.delta_sum / p.n_played, 0)
          / NULLIF(p.n_played - 1, 0)) AS delta_actual_ci_sd,
        p.n_played AS delta_actual_ci_n,
        p.elo_sum / p.n_played AS avg_elo
      FROM pair_agg p
    )
    SELECT p.card_name, p.card_type, c.card_sum / c.n_card AS delta_card,
      p.endgame_name, e.endgame_sum / e.n_endgame AS delta_endgame,
      c.card_sum / c.n_card + e.endgame_sum / e.n_endgame AS delta_combined,
      p.delta_actual, p.delta_actual AS delta_actual_ci_mean,
      p.delta_actual_ci_sd, p.delta_actual_ci_n,
      p.delta_actual - c.card_sum / c.n_card - e.endgame_sum / e.n_endgame AS interaction,
      p.avg_elo, p.n_played,
      c.card_sum / c.n_card AS component_1_ci_mean,
      SQRT(GREATEST(c.card_sumsq - c.card_sum * c.card_sum / c.n_card, 0)
        / NULLIF(c.n_card - 1, 0)) AS component_1_ci_sd,
      c.n_card AS component_1_ci_n,
      e.endgame_sum / e.n_endgame AS component_2_ci_mean,
      SQRT(GREATEST(e.endgame_sumsq - e.endgame_sum * e.endgame_sum / e.n_endgame, 0)
        / NULLIF(e.n_endgame - 1, 0)) AS component_2_ci_sd,
      e.n_endgame AS component_2_ci_n
    FROM pairs p JOIN cards c USING(card_name) JOIN endgames e USING(endgame_name)
    ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, endgame_name
    LIMIT ? OFFSET ?
    """, parameters


def _next_card_action_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False)
    values_sql = ", ".join(
        f"({order}, {_sql_string(card_type)}, {number}, {_sql_string(name)})"
        for order, card_type, number, name in MW_ACTION_CARDS
    )
    return f"""
    WITH action_catalog AS (
      SELECT * FROM (VALUES {values_sql})
        v(action_card_order, action_card_type, action_card_number, action_card_name)
    ),
    scoped AS (
      SELECT g.table_id, g.player, g.elo_delta, g.pre_match_elo,
        g.Animals_Action_Card_Number, g.Association_Action_Card_Number,
        g.Build_Action_Card_Number, g.Cards_Action_Card_Number,
        g.Sponsors_Action_Card_Number
      FROM prepared_full_sample_narrow g WHERE {predicates}
    ), card_counts AS (
      SELECT cp.table_id, cp.player, cp.card_name, ANY_VALUE(cp.card_type) AS card_type,
        COUNT(*) AS card_n, ANY_VALUE(s.elo_delta) AS elo_delta,
        ANY_VALUE(s.pre_match_elo) AS pre_match_elo
      FROM card_play_narrow cp JOIN scoped s USING(table_id, player)
      GROUP BY cp.table_id, cp.player, cp.card_name
    ), selected_actions AS (
      SELECT s.table_id, s.player, a.action_card_order, a.action_card_type,
        a.action_card_number, a.action_card_name,
        a.action_card_type || ' ' || CAST(a.action_card_number AS VARCHAR) AS action_card_key,
        s.elo_delta, s.pre_match_elo
      FROM scoped s CROSS JOIN action_catalog a
      WHERE TRY_CAST(CASE a.action_card_type
          WHEN 'Animals' THEN s.Animals_Action_Card_Number
          WHEN 'Association' THEN s.Association_Action_Card_Number
          WHEN 'Build' THEN s.Build_Action_Card_Number
          WHEN 'Cards' THEN s.Cards_Action_Card_Number
          ELSE s.Sponsors_Action_Card_Number END AS INTEGER) = a.action_card_number
    ), pair_agg AS (
      SELECT c.card_name, c.card_type, a.action_card_order, a.action_card_key,
        a.action_card_name, a.action_card_type, a.action_card_number,
        SUM(c.card_n) AS n_played,
        SUM(c.card_n * c.elo_delta) AS delta_sum,
        SUM(c.card_n * c.elo_delta * c.elo_delta) AS delta_sumsq,
        SUM(c.card_n * c.pre_match_elo) AS elo_sum
      FROM card_counts c JOIN selected_actions a USING(table_id, player)
      GROUP BY c.card_name, c.card_type, a.action_card_order, a.action_card_key,
        a.action_card_name, a.action_card_type, a.action_card_number
    ), cards AS (
      SELECT card_name, ANY_VALUE(card_type) AS card_type,
        SUM(card_n) AS n_card, SUM(card_n * elo_delta) AS card_sum,
        SUM(card_n * elo_delta * elo_delta) AS card_sumsq
      FROM card_counts GROUP BY card_name
    ), actions_avg AS (
      SELECT action_card_key, COUNT(elo_delta) AS n_action,
        SUM(elo_delta) AS action_sum, SUM(elo_delta * elo_delta) AS action_sumsq
      FROM selected_actions GROUP BY action_card_key
    ), pairs AS (
      SELECT p.*, p.delta_sum / p.n_played AS delta_actual,
        SQRT(GREATEST(p.delta_sumsq - p.delta_sum * p.delta_sum / p.n_played, 0)
          / NULLIF(p.n_played - 1, 0)) AS delta_actual_ci_sd,
        p.n_played AS delta_actual_ci_n,
        p.elo_sum / p.n_played AS avg_elo
      FROM pair_agg p
    )
    SELECT p.card_name, p.card_type, c.card_sum / c.n_card AS delta_card,
      p.action_card_order, p.action_card_key, p.action_card_name,
      p.action_card_type, p.action_card_number,
      a.action_sum / a.n_action AS delta_action,
      c.card_sum / c.n_card + a.action_sum / a.n_action AS delta_combined,
      p.delta_actual, p.delta_actual AS delta_actual_ci_mean,
      p.delta_actual_ci_sd, p.delta_actual_ci_n,
      p.delta_actual - c.card_sum / c.n_card - a.action_sum / a.n_action AS interaction,
      p.avg_elo, p.n_played,
      p.card_type || ' + ' || p.action_card_type AS pair_type,
      c.card_sum / c.n_card AS component_1_ci_mean,
      SQRT(GREATEST(c.card_sumsq - c.card_sum * c.card_sum / c.n_card, 0)
        / NULLIF(c.n_card - 1, 0)) AS component_1_ci_sd,
      c.n_card AS component_1_ci_n,
      a.action_sum / a.n_action AS component_2_ci_mean,
      SQRT(GREATEST(a.action_sumsq - a.action_sum * a.action_sum / a.n_action, 0)
        / NULLIF(a.n_action - 1, 0)) AS component_2_ci_sd,
      a.n_action AS component_2_ci_n
    FROM pairs p JOIN cards c USING(card_name) JOIN actions_avg a USING(action_card_key)
    ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, action_card_name
    LIMIT ? OFFSET ?
    """, parameters


def _players_cohort_moments_sql(predicates: str) -> str:
    """Scan each focal observation once, then combine at most six buckets.

    Separate non-null counts are required for every mean. Money percentages
    are ratios of two means, not means of row percentages; each denominator
    therefore retains its own count. Null Elo belongs only to all/winners.
    """
    moments = ["COUNT(*) AS observation_count"]
    pooled = ["SUM(b.observation_count)::BIGINT AS observation_count"]
    for key, *_rest, expression in PLAYERS_METRICS:
        if key in PLAYERS_MONEY_FIELDS:
            continue
        if not expression.startswith('AVG(') or not expression.endswith(')'):
            raise ValueError(f'Unsupported Players mean expression: {key}')
        value = expression[4:-1]
        moments.extend([f"AVG({value}) AS {key}", f"COUNT({value}) AS n_{key}"])
        pooled.append(f"SUM(b.{key} * b.n_{key}) / NULLIF(SUM(b.n_{key}), 0) AS {key}")
    total_money = ' + '.join(PLAYERS_MONEY_FIELDS.values())
    moments.extend([f"AVG({total_money}) AS raw_money_total", f"COUNT({total_money}) AS n_money_total"])
    denominator = "(SUM(b.raw_money_total * b.n_money_total) / NULLIF(SUM(b.n_money_total), 0))"
    for key, column in PLAYERS_MONEY_FIELDS.items():
        moments.extend([f"AVG(TRY_CAST({column} AS DOUBLE)) AS raw_{key}",
                        f"COUNT(TRY_CAST({column} AS DOUBLE)) AS n_raw_{key}"])
        numerator = f"SUM(b.raw_{key} * b.n_raw_{key}) / NULLIF(SUM(b.n_raw_{key}), 0)"
        pooled.extend([f"{numerator} AS raw_{key}",
                       f"100 * ({numerator}) / NULLIF({denominator}, 0) AS {key}"])
    return f"""cohort_buckets AS MATERIALIZED (
      SELECT CASE WHEN f.pre_match_elo >= 700 THEN 2
                  WHEN f.pre_match_elo >= 500 THEN 1 ELSE 0 END AS elo_band,
        COALESCE(f.Game_result = 1, FALSE) AS winner, {', '.join(moments)}
      FROM players_metrics_narrow f WHERE {predicates}
      GROUP BY elo_band, winner
    ), cohort_aggregate AS MATERIALIZED (
      SELECT c.cohort, {', '.join(pooled)}
      FROM cohort_buckets b JOIN
        (VALUES ('all'), ('winners'), ('experts'), ('masters')) c(cohort)
        ON c.cohort = 'all' OR (c.cohort = 'winners' AND b.winner)
          OR (c.cohort = 'experts' AND b.elo_band >= 1)
          OR (c.cohort = 'masters' AND b.elo_band = 2)
      GROUP BY c.cohort
    )"""


def _players_metric_sql(request: Mapping[str, Any], view: str) -> tuple[str, list[Any]]:
    scope = normalize_scope(request)
    hard_completed = view != "performance_by_map"
    predicates, parameters = scope_predicates(
        scope, "f", hard_completed=hard_completed,
        population_prepared=(view != "performance_by_map"),
    )
    last_x = int(request.get("last_x_games") or 0)

    def aggregate_fields():
        fields = ["COUNT(*) AS observation_count"]
        fields.extend(f"{expression} AS {key}" for key, *_rest, expression in PLAYERS_METRICS)
        fields.extend(
            f"AVG(TRY_CAST({column} AS DOUBLE)) AS raw_{key}"
            for key, column in PLAYERS_MONEY_FIELDS.items()
        )
        return ", ".join(fields)

    if view == "general":
        selected_player = str(request.get("players_player") or "").strip()
        default_maps = {full for _code, full in MAPS[:15]}
        default_scope = (
            bool(request.get("_players_filter_facts"))
            and set(scope.get("maps") or []) == default_maps
            and scope.get("player_elo_min") == 0
            and scope.get("player_elo_max") is None
            and scope.get("opponent_elo_min") == 0
            and scope.get("opponent_elo_max") is None
            and scope.get("date_from") is None
            and scope.get("date_to") is None
            and set(scope.get("starting_positions") or []) == {
                "First player", "Second player"
            }
            and not scope.get("arena_seasons")
            and not scope.get("arena_only")
            and not scope.get("tournament_only")
        )
        row_queries = []
        value_rows = []
        field_names = []
        for key, order, label, tooltip, is_default, value_format, lower_is_better, _expression in PLAYERS_METRICS:
            tooltip_sql = "NULL" if tooltip is None else _sql_string(tooltip)
            tooltip_player = f"p.raw_{key}" if key in PLAYERS_MONEY_FIELDS else "CAST(NULL AS DOUBLE)"
            tooltip_all = lambda alias: f"{alias}.raw_{key}" if key in PLAYERS_MONEY_FIELDS else "CAST(NULL AS DOUBLE)"
            fields = [
                (str(order), "sort_order"), (_sql_string(label), "metric"),
                (tooltip_sql, "tooltip"), (str(is_default).upper(), "is_default"),
                (_sql_string(value_format), "format"), (str(lower_is_better).upper(), "lower_is_better"),
                (f"p.{key}", "player"), ("p.observation_count", "count_player"),
                (tooltip_player, "tooltip_player"),
                ("(SELECT player_identity FROM target)", "player_identity"),
                ("(SELECT LIST(STRUCT_PACK(name := player, game_count := game_count) ORDER BY player) FROM selected_accounts)", "account_counts"),
                (f"a.{key}", "all"), ("a.observation_count", "count_all"),
                (f"w.{key}", "winners"), ("w.observation_count", "count_winners"),
                (f"e.{key}", "experts"), ("e.observation_count", "count_experts"),
                (f"m.{key}", "masters"), ("m.observation_count", "count_masters"),
                (tooltip_all("a"), "tooltip_all"), (tooltip_all("w"), "tooltip_winners"),
                (tooltip_all("e"), "tooltip_experts"), (tooltip_all("m"), "tooltip_masters"),
            ]
            field_names = [name for _, name in fields]
            row_queries.append(f"""
              SELECT {', '.join(f'{expression} AS "{name}"' for expression, name in fields)}
              FROM all_aggregate a CROSS JOIN winners_aggregate w
              CROSS JOIN experts_aggregate e CROSS JOIN masters_aggregate m
              CROSS JOIN player_aggregate p
            """)
            # The no-player snapshot joins the four one-row summaries once,
            # rather than expanding 65 repeated join/CTE operator trees.
            value_rows.append("(" + ", ".join(
                "NULL::VARCHAR" if name == "player_identity" else
                "NULL::STRUCT(name VARCHAR, game_count BIGINT)[]" if name == "account_counts" else expression
                for expression, name in fields) + ")")
        if default_scope:
            route_parameters = parameters if selected_player else []
            # Default snapshots have no selected identity and use these same
            # generation-local cohorts. Never rescan all player observations
            # merely to serialize summaries already prepared by the builder.
            # A missing cohort still yields one null-valued, zero-count row,
            # just like the filtered aggregate path (including empty datasets).
            dataset = int(scope["is_mw"])
            if selected_player:
                selected_ctes = f"""
            selected_ranked AS (
              SELECT f.*, ROW_NUMBER() OVER (
                ORDER BY f.game_ended_at DESC, CAST(f.table_id AS VARCHAR) DESC
              ) AS player_rank
              FROM players_by_identity_narrow f, target
              WHERE f.player_identity = target.player_identity AND {predicates}
            ),
            selected AS (
              SELECT * FROM selected_ranked
              WHERE {last_x} = 0 OR player_rank <= {last_x}
            ),
            selected_accounts AS (
              SELECT player, COUNT(*) AS game_count FROM selected GROUP BY player
            )"""
                player_aggregate_sql = f"SELECT {aggregate_fields()} FROM selected"
            else:
                # Do not even bind the large identity fact table. DuckDB can
                # load substantial column/row-group metadata before folding
                # a WHERE FALSE scan, despite the final result being empty.
                selected_ctes = """selected_accounts AS (
                    SELECT NULL::VARCHAR AS player, 0::BIGINT AS game_count WHERE FALSE
                )"""
                empty_fields = ["0::BIGINT AS observation_count"]
                empty_fields.extend(f"NULL::DOUBLE AS {key}" for key, *_ in PLAYERS_METRICS)
                empty_fields.extend(f"NULL::DOUBLE AS raw_{key}" for key in PLAYERS_MONEY_FIELDS)
                player_aggregate_sql = "SELECT " + ", ".join(empty_fields)
            source_ctes = f"""
            {selected_ctes},
            all_aggregate AS (
              SELECT a.* EXCLUDE(cohort, observation_count), COALESCE(a.observation_count, 0) AS observation_count
              FROM (VALUES ('all')) c(cohort) LEFT JOIN players_default_cohorts_narrow a
                ON a.cohort = c.cohort AND a.is_mw = {dataset}
            ),
            winners_aggregate AS (
              SELECT a.* EXCLUDE(cohort, observation_count), COALESCE(a.observation_count, 0) AS observation_count
              FROM (VALUES ('winners')) c(cohort) LEFT JOIN players_default_cohorts_narrow a
                ON a.cohort = c.cohort AND a.is_mw = {dataset}
            ),
            experts_aggregate AS (
              SELECT a.* EXCLUDE(cohort, observation_count), COALESCE(a.observation_count, 0) AS observation_count
              FROM (VALUES ('experts')) c(cohort) LEFT JOIN players_default_cohorts_narrow a
                ON a.cohort = c.cohort AND a.is_mw = {dataset}
            ),
            masters_aggregate AS (
              SELECT a.* EXCLUDE(cohort, observation_count), COALESCE(a.observation_count, 0) AS observation_count
              FROM (VALUES ('masters')) c(cohort) LEFT JOIN players_default_cohorts_narrow a
                ON a.cohort = c.cohort AND a.is_mw = {dataset}
            ),
            player_aggregate AS ({player_aggregate_sql})
            """
        else:
            route_parameters = [*parameters, *parameters]
            source_ctes = f"""
            selected_ranked AS (
              SELECT f.*, ROW_NUMBER() OVER (
                ORDER BY f.game_ended_at DESC, CAST(f.table_id AS VARCHAR) DESC
              ) AS player_rank
              FROM players_by_identity_narrow f, target
              WHERE f.player_identity = target.player_identity AND {predicates}
            ),
            selected AS (
              SELECT * FROM selected_ranked
              WHERE {last_x} = 0 OR player_rank <= {last_x}
            ),
            selected_accounts AS (
              SELECT player, COUNT(*) AS game_count FROM selected GROUP BY player
            ),
            {_players_cohort_moments_sql(predicates)},
            all_aggregate AS (
              SELECT a.* EXCLUDE(cohort, observation_count), COALESCE(a.observation_count, 0) AS observation_count
              FROM (VALUES ('all')) c(cohort) LEFT JOIN cohort_aggregate a USING(cohort)
            ),
            winners_aggregate AS (
              SELECT a.* EXCLUDE(cohort, observation_count), COALESCE(a.observation_count, 0) AS observation_count
              FROM (VALUES ('winners')) c(cohort) LEFT JOIN cohort_aggregate a USING(cohort)
            ),
            experts_aggregate AS (
              SELECT a.* EXCLUDE(cohort, observation_count), COALESCE(a.observation_count, 0) AS observation_count
              FROM (VALUES ('experts')) c(cohort) LEFT JOIN cohort_aggregate a USING(cohort)
            ),
            masters_aggregate AS (
              SELECT a.* EXCLUDE(cohort, observation_count), COALESCE(a.observation_count, 0) AS observation_count
              FROM (VALUES ('masters')) c(cohort) LEFT JOIN cohort_aggregate a USING(cohort)
            ),
            player_aggregate AS (SELECT {aggregate_fields()} FROM selected)
            """
        if default_scope and not selected_player:
            return f"""WITH {source_ctes}
                SELECT metric_values.*
                FROM all_aggregate a CROSS JOIN winners_aggregate w
                CROSS JOIN experts_aggregate e CROSS JOIN masters_aggregate m
                CROSS JOIN player_aggregate p
                CROSS JOIN LATERAL (VALUES {', '.join(value_rows)})
                    metric_values({', '.join('"'+name+'"' for name in field_names)})
                ORDER BY sort_order LIMIT ? OFFSET ?""", []
        return f"""
        WITH target AS (
          SELECT COALESCE(
            (SELECT player_identity FROM player_identity_metadata
             WHERE player_casefold = LOWER(TRIM(CAST(? AS VARCHAR))) LIMIT 1),
            CASE WHEN CAST(? AS VARCHAR) = '' THEN NULL
                 ELSE 'player:' || CAST(? AS VARCHAR) END
          ) AS player_identity
        ),
        {source_ctes}
        {' UNION ALL '.join(row_queries)}
        ORDER BY sort_order LIMIT ? OFFSET ?
        """, [selected_player, selected_player, selected_player, *route_parameters]

    requested_players = [str(value).strip() for value in request.get("players_players") or []]
    values_sql = ", ".join(f"({index}, ?)" for index in range(len(requested_players)))
    if not values_sql:
        values_sql = "(0, '')"
    requested_parameters: list[Any] = list(requested_players)
    source_relation = "prepared_full_sample_narrow" if view == "performance_by_map" else "players_metrics_narrow"
    completion_guard = "AND NOT f.is_corrupted_game" if view == "performance_by_map" else ""

    if view == "performance_by_map":
        return f"""
        WITH requested(position, player) AS (VALUES {values_sql}),
        resolved AS (
          SELECT r.position, r.player,
            COALESCE(m.player_identity, 'player:' || r.player) AS player_identity
          FROM requested r LEFT JOIN player_identity_metadata m
            ON m.player_casefold = LOWER(TRIM(r.player))
          WHERE r.player <> ''
        ),
        filtered AS (
          SELECT r.position, r.player AS requested_player, f.Map,
            TRY_CAST(f.elo_delta AS DOUBLE) AS elo_delta,
            ROW_NUMBER() OVER (
              PARTITION BY r.position, f.Map
              ORDER BY f.game_ended_at DESC, CAST(f.table_id AS VARCHAR) DESC
            ) AS recent_rank
          FROM {source_relation} f JOIN resolved r USING(player_identity)
          WHERE {predicates} {completion_guard}
        ),
        moments AS (
          SELECT position, requested_player AS player, Map,
            COUNT(elo_delta) AS ci_n,
            AVG(elo_delta) AS value,
            STDDEV_SAMP(elo_delta) AS ci_sd
          FROM filtered
          WHERE {last_x} = 0 OR recent_rank <= {last_x}
          GROUP BY position, requested_player, Map
        )
        SELECT r.position AS sort_order, r.player, m.Map AS map_name,
          m.value, m.value AS ci_mean, m.ci_sd, COALESCE(m.ci_n, 0) AS ci_n
        FROM resolved r LEFT JOIN moments m USING(position, player)
        ORDER BY r.position, m.Map
        LIMIT ? OFFSET ?
        """, [*requested_parameters, *parameters]

    metric_rows = []
    for key, order, label, tooltip, is_default, value_format, lower_is_better, _expression in PLAYERS_METRICS:
        tooltip_sql = "NULL" if tooltip is None else _sql_string(tooltip)
        tooltip_value = (
            f"a.raw_{key}" if key in PLAYERS_MONEY_FIELDS
            else "CAST(NULL AS DOUBLE)"
        )
        metric_rows.append(f"""
          SELECT {order} AS sort_order, {_sql_string(label)} AS metric,
            {tooltip_sql} AS tooltip, {str(is_default).upper()} AS is_default,
            {_sql_string(value_format)} AS format,
            {str(lower_is_better).upper()} AS lower_is_better,
            r.position, r.player, r.player_identity,
            a.{key} AS value, {tooltip_value} AS tooltip_value,
            COALESCE(a.observation_count, 0) AS game_count,
            (SELECT LIST(STRUCT_PACK(name := exact_player, game_count := exact_count)
                         ORDER BY exact_player)
             FROM account_counts c WHERE c.position = r.position) AS account_counts
          FROM resolved r LEFT JOIN aggregated a USING(position)
        """)
    return f"""
    WITH requested(position, player) AS (VALUES {values_sql}),
    resolved AS (
      SELECT r.position, r.player,
        COALESCE(m.player_identity, 'player:' || r.player) AS player_identity
      FROM requested r LEFT JOIN player_identity_metadata m
        ON m.player_casefold = LOWER(TRIM(r.player))
      WHERE r.player <> ''
    ),
    filtered AS (
      SELECT r.position, f.*,
        ROW_NUMBER() OVER (
          PARTITION BY r.position ORDER BY f.game_ended_at DESC, CAST(f.table_id AS VARCHAR) DESC
        ) AS recent_rank
      FROM {source_relation} f JOIN resolved r USING(player_identity)
      WHERE {predicates}
    ),
    limited AS (
      SELECT * FROM filtered WHERE {last_x} = 0 OR recent_rank <= {last_x}
    ),
    account_counts AS (
      SELECT position, player AS exact_player, COUNT(*) AS exact_count
      FROM limited GROUP BY position, player
    ),
    aggregated AS (
      SELECT position, {aggregate_fields()} FROM limited GROUP BY position
    )
    {' UNION ALL '.join(metric_rows)}
    ORDER BY sort_order, position
    LIMIT ? OFFSET ?
    """, [*requested_parameters, *parameters]


def _next_players_arena_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    """players/arena_top_100: compatibility alias that returns the Arena roster.

    Contract (contracts/dashboard-routes.v1.json): one row per Arena roster player with
    season, rank, player, player_id and end (ending rating); the only request field is
    arena_season. Full Arena statistics live in the arena/top_100 bundle, which these
    player IDs join to. It deliberately ignores the Full Sample filters.
    """
    season = str(request.get("arena_season") or "").strip()
    return f"""
    SELECT r.season, r.rank, r.player, r.player_id, r.ending_rating AS "end"
    FROM arena_roster_narrow r
    {"WHERE r.season = ?" if season else ""}
    ORDER BY r.season, r.rank LIMIT ? OFFSET ?
    """, [season] if season else []


def _remaining_route_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    view = str(request.get("remaining_view") or "")
    if view == "home": return _next_home_sql(request)
    if view == "opening_hand": return _next_opening_hand_sql(request)
    if view in {"card_map", "card_round", "card_endgame", "card_action_card"}:
        return combination_sql(request, view)
    if view in {"players_general", "players_comparison", "players_performance_by_map"}:
        return _players_metric_sql(request, view.removeprefix("players_"))
    if view == "players_arena_top_100": return _next_players_arena_sql(request)
    raise ValueError(f"unknown local analytical view: {view}")


def _final_records_sql(request: Mapping[str, Any], view: str, *, paginate: bool = True) -> tuple[str, list[Any]]:
    # Only the private Most Icons snapshot writer consumes an unpaged cursor.
    # Public callers always retain their existing LIMIT/OFFSET contract.
    if not paginate and view != "most_icons":
        raise ValueError("unpaged Records SQL is restricted to Most Icons snapshots")
    scope = normalize_scope(request, require_dataset=False)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=False)
    if view == "elo_leaderboard":
        return """
        SELECT rank, source_row, country, player, peak_elo, peak_arena
        FROM records_elo_leaderboard_narrow
        ORDER BY rank LIMIT ? OFFSET ?
        """, []

    table_outcomes = """
    table_outcomes AS (
      SELECT table_id, COUNT(*) AS result_row_count,
        SUM(CASE WHEN TRY_CAST(Game_result AS INTEGER) = 1 THEN 1 ELSE 0 END) AS result_one_count,
        SUM(CASE WHEN TRY_CAST(Game_result AS INTEGER) = 2 THEN 1 ELSE 0 END) AS result_two_count,
        SUM(CASE WHEN COALESCE(concede, FALSE) THEN 1 ELSE 0 END) AS concede_count,
        SUM(CASE WHEN end_game_triggered IS TRUE THEN 1 ELSE 0 END) AS triggered_count
      FROM prepared_full_sample_narrow
      WHERE table_id NOT IN (SELECT table_id FROM corrupted_tables_narrow)
      GROUP BY table_id
    )
    """
    complete_join = "o.result_row_count = 2 AND o.concede_count = 0 AND o.triggered_count = 2"
    result_code = """
      CASE
        WHEN o.result_row_count = 2 AND f.Game_result = 1 AND o.result_two_count = 1 THEN 'W'
        WHEN o.result_row_count = 2 AND f.Game_result = 1 AND o.result_one_count = 2 THEN 'D'
        WHEN o.result_row_count = 2 AND f.Game_result = 2 AND o.result_one_count = 1 THEN 'L'
        ELSE NULL
      END AS result_code
    """
    arena_expr = """
      EXISTS (SELECT 1 FROM arena_seasons_metadata arena
        WHERE TRY_CAST(f.game_ended_at AS TIMESTAMPTZ) >= arena.start_utc
          AND TRY_CAST(f.game_ended_at AS TIMESTAMPTZ) < arena.end_utc
          AND CAST(f.is_mw AS INTEGER) = CASE WHEN arena.mode = 'mw' THEN 1 ELSE 0 END
          AND f.arena_rating_delta IS NOT NULL)
    """
    tournament_expr = "EXISTS (SELECT 1 FROM tournament_tables_metadata t WHERE t.table_id = f.table_id)"
    records_player = request.get("records_player")
    records_arena_only = bool(request.get("records_arena_only"))
    records_tournament_only = bool(request.get("records_tournament_only"))
    manual_filters = []
    manual_params: list[Any] = []
    if records_player:
        manual_filters.append("lower(player) = lower(?)")
        manual_params.append(str(records_player).strip())
    if records_arena_only:
        manual_filters.append("is_arena")
    if records_tournament_only:
        manual_filters.append("is_tournament")
    manual_where = " AND ".join(manual_filters) or "TRUE"
    manual_source_dataset = ""
    if scope.get("is_mw") is not None:
        manual_source_dataset = (
            " AND CASE WHEN m.mode = 'MW' THEN 1 ELSE 0 END = "
            + str(int(scope["is_mw"]))
        )
    auto_filters = []
    auto_params: list[Any] = []
    if records_player:
        auto_filters.append("lower(f.player) = lower(?)")
        auto_params.append(str(records_player).strip())
    if records_arena_only:
        auto_filters.append(arena_expr)
    if records_tournament_only:
        auto_filters.append(tournament_expr)
    auto_where = (" AND " + " AND ".join(auto_filters)) if auto_filters else ""

    if view == "fastest_games":
        return f"""
        WITH {table_outcomes},
        automatic_records AS (
          SELECT TRY_CAST(f.Number_of_turns AS DOUBLE) AS turns,
            TRY_CAST(f.Score AS DOUBLE) AS score, f.player, f.Map AS map_name, f.table_id,
            CAST(CAST(f.game_ended_at AS DATE) AS VARCHAR) AS game_date, {result_code},
            CAST(0 AS BIGINT) AS ept, TRY_CAST(f.opponent_elo AS DOUBLE) AS opponent_elo,
            f.Starting_position_in_first_round AS starting_position, TRUE AS source_enriched,
            {arena_expr} AS is_arena, {tournament_expr} AS is_tournament,
            CAST(NULL AS BIGINT) AS source_row
          FROM prepared_full_sample_narrow f JOIN table_outcomes o USING(table_id)
          WHERE {predicates} AND {complete_join}{auto_where}
            AND TRY_CAST(f.Game_result AS INTEGER) = 1 AND o.result_two_count = 1
            AND TRY_CAST(f.Number_of_turns AS DOUBLE) <= 23
            AND NOT EXISTS (SELECT 1 FROM records_manual_narrow m
              WHERE m.record_view = 'fastest_games' AND m.table_id = f.table_id
                AND lower(m.player) = lower(f.player))
        ),
        manual_matches AS (
          SELECT m.*, s.Map AS source_map_name,
            CAST(CAST(s.game_ended_at AS DATE) AS VARCHAR) AS source_game_date,
            TRY_CAST(s.opponent_elo AS DOUBLE) AS source_opponent_elo,
            s.Starting_position_in_first_round AS source_starting_position,
            s.player IS NOT NULL AS matched_player,
            ROW_NUMBER() OVER (PARTITION BY m.source_row ORDER BY s.player) AS rn
          FROM records_manual_narrow m LEFT JOIN prepared_full_sample_narrow s
            ON s.table_id = m.table_id AND CAST(s.is_mw AS INTEGER) = CASE WHEN m.mode='MW' THEN 1 ELSE 0 END
            AND lower(s.player) = lower(m.player)
          WHERE m.record_view = 'fastest_games'
            AND m.table_id NOT IN (SELECT table_id FROM corrupted_tables_narrow)
            {manual_source_dataset}
        ),
        manual_records_raw AS (
          SELECT turns, score, player, COALESCE(source_map_name, '') AS map_name,
            CAST(table_id AS VARCHAR) AS table_id, source_game_date AS game_date,
            CAST(NULL AS VARCHAR) AS result_code, ept, source_opponent_elo AS opponent_elo,
            source_starting_position AS starting_position, matched_player AS source_enriched,
            EXISTS (SELECT 1 FROM arena_seasons_metadata a
              WHERE TRY_CAST(source_game_date AS TIMESTAMPTZ) >= a.start_utc
                AND TRY_CAST(source_game_date AS TIMESTAMPTZ) < a.end_utc
                AND CASE WHEN mode='MW' THEN 1 ELSE 0 END = CASE WHEN a.mode='mw' THEN 1 ELSE 0 END) AS is_arena,
            EXISTS (SELECT 1 FROM tournament_tables_metadata t WHERE t.table_id = manual_matches.table_id) AS is_tournament,
            source_row
          FROM manual_matches WHERE rn=1
        ),
        manual_records AS (
          SELECT * FROM manual_records_raw WHERE {manual_where}
        )
        SELECT * FROM automatic_records
        UNION ALL
        SELECT * FROM manual_records
        ORDER BY turns ASC, score DESC NULLS LAST, player, table_id
        LIMIT ? OFFSET ?
        """, parameters + auto_params + manual_params
    if view == "highest_scores":
        return f"""
        WITH {table_outcomes}
        SELECT TRY_CAST(f.Number_of_turns AS DOUBLE) AS turns,
          TRY_CAST(f.Score AS DOUBLE) AS score, f.player, f.Map AS map_name, f.table_id,
          CAST(CAST(f.game_ended_at AS DATE) AS VARCHAR) AS game_date, {result_code}, CAST(0 AS BIGINT) AS ept,
          TRY_CAST(f.opponent_elo AS DOUBLE) AS opponent_elo,
          f.Starting_position_in_first_round AS starting_position, TRUE AS source_enriched,
          {arena_expr} AS is_arena, {tournament_expr} AS is_tournament, CAST(NULL AS BIGINT) AS source_row
        FROM prepared_full_sample_narrow f JOIN table_outcomes o USING(table_id)
        WHERE {predicates} AND {complete_join}{auto_where}
          AND TRY_CAST(f.Score AS DOUBLE) >= 170
          AND TRY_CAST(f.Game_result AS INTEGER) = 1 AND o.result_two_count = 1
          AND TRY_CAST(f.Number_of_turns AS DOUBLE) <= 100
        ORDER BY score DESC, turns ASC NULLS LAST, player, table_id LIMIT ? OFFSET ?
        """, parameters + auto_params
    if view == "biggest_turns":
        # Map shown for a Biggest Turns row: the Full Sample's full map name when
        # the row matches a Full Sample game; otherwise the sheet's short code
        # (e.g. '1a') translated to the same full name the frontend filters on.
        sheet_map_name = "CASE lower(m.map_code) " + " ".join(
            f"WHEN {_sql_string(code.lower())} THEN {_sql_string(full)}" for code, full in MAPS
        ) + " ELSE m.map_code END"
        return f"""
        WITH manual_biggest_rows AS (
          SELECT m.turns, m.score, m.player, COALESCE(s.Map, {sheet_map_name}) AS map_name,
          CAST(m.table_id AS VARCHAR) AS table_id,
          COALESCE(CAST(CAST(s.game_ended_at AS DATE) AS VARCHAR), m.game_date) AS game_date,
          m.result_code, m.ept, m.flat, m."end", m.total, m.move, m.actions,
          TRY_CAST(s.opponent_elo AS DOUBLE) AS opponent_elo,
          s.Starting_position_in_first_round AS starting_position,
          s.player IS NOT NULL AS source_enriched,
          EXISTS (SELECT 1 FROM arena_seasons_metadata a
            WHERE TRY_CAST(s.game_ended_at AS TIMESTAMPTZ) >= a.start_utc
              AND TRY_CAST(s.game_ended_at AS TIMESTAMPTZ) < a.end_utc
              AND CAST(m.mode='MW' AS INTEGER) = CASE WHEN a.mode='mw' THEN 1 ELSE 0 END) AS is_arena,
          EXISTS (SELECT 1 FROM tournament_tables_metadata t WHERE t.table_id=m.table_id) AS is_tournament,
          m.source_row
          FROM records_manual_narrow m LEFT JOIN prepared_full_sample_narrow s
          ON s.table_id=m.table_id AND lower(s.player)=lower(m.player)
          AND CAST(s.is_mw AS INTEGER)=CASE WHEN m.mode='MW' THEN 1 ELSE 0 END
          WHERE m.record_view='biggest_turns' AND m.table_id NOT IN (SELECT table_id FROM corrupted_tables_narrow)
          {manual_source_dataset}
        )
        SELECT * FROM manual_biggest_rows
        WHERE {manual_where}
        ORDER BY total DESC NULLS LAST, source_row ASC LIMIT ? OFFSET ?
        """, manual_params
    icon_fields = (
        ("Birds", "Bird_icons"), ("Herbivores", "Herbivore_icons"),
        ("Predators", "Predator_icons"), ("Primates", "Primate_icons"),
        ("Reptiles", "Reptile_icons"), ("Sea Animals", "Sea_Animal_icons"),
        ("Africa", "Africa_icons"), ("Americas", "Americas_icons"),
        ("Asia", "Asia_icons"), ("Australia", "Australia_icons"),
        ("Europe", "Europe_icons"), ("Rock", "Rock_icons"),
        ("Water", "Water_icons"), ("Science", "Science_icons"),
    )
    icon_values = ", ".join(
        f"({_sql_string(label)}, TRY_CAST(f.{field} AS DOUBLE))"
        for label, field in icon_fields
    )
    # Expand the fourteen icon measures only after the scoped game rows have
    # been selected. This preserves the Records contract while avoiding
    # fourteen independent scans of the same prepared relation.
    return f"""
    WITH {table_outcomes}, scoped_records AS (
      SELECT f.*, {result_code}, {arena_expr} AS is_arena,
        {tournament_expr} AS is_tournament
      FROM prepared_full_sample_narrow f JOIN table_outcomes o USING(table_id)
      WHERE {predicates} AND {complete_join}{auto_where}
    )
    SELECT icons.n, icons.icon, f.player,
      TRY_CAST(f.Number_of_turns AS DOUBLE) AS turns,
      TRY_CAST(f.Score AS DOUBLE) AS score, f.Map AS map_name,
      CAST(f.table_id AS VARCHAR) AS table_id,
      CAST(CAST(f.game_ended_at AS DATE) AS VARCHAR) AS game_date,
      f.result_code, CAST(0 AS BIGINT) AS ept,
      TRY_CAST(f.opponent_elo AS DOUBLE) AS opponent_elo,
      f.Starting_position_in_first_round AS starting_position,
      TRUE AS source_enriched, f.is_arena, f.is_tournament,
      CAST(NULL AS BIGINT) AS source_row
    FROM scoped_records f
    CROSS JOIN LATERAL (VALUES {icon_values}) AS icons(icon, n)
    WHERE icons.n >= 10
    ORDER BY icons.n DESC, turns ASC NULLS LAST, f.player, f.table_id
    {'LIMIT ? OFFSET ?' if paginate else ''}
    """, parameters + auto_params


def _final_arena_sql(request: Mapping[str, Any], *, histories_only: bool = False) -> tuple[str, list[Any]]:
    # Arena is a season bundle.  The roster (rank, player ID, and ending
    # rating) is imported once per immutable generation; game aggregates and
    # rating history are joined from the local Full Sample by player ID.
    series_player_ids = sorted({int(value) for value in (request.get("arena_series_player_ids") or [])})
    series_players = [str(value).strip() for value in (request.get("arena_series_players") or []) if str(value).strip()]
    series_predicate = (
        "f.player_id IN (" + ", ".join(str(value) for value in series_player_ids) + ")"
        if series_player_ids else (
            "lower(f.player) IN (" + ", ".join(_sql_string(value.casefold()) for value in series_players) + ")"
            if series_players else "FALSE"
        )
    )
    season = str(request.get("arena_season") or "").strip()
    season_filter = "WHERE r.season = ?" if season else ""
    # Trusted offline history batches reuse the exact joins/population below,
    # but do not recompute roster statistics or histories for unrelated players.
    # This keyword is not a public request option or a new route.
    if histories_only:
        if not series_player_ids:
            raise ValueError('offline Arena histories require player IDs')
        season_filter += (' AND ' if season_filter else 'WHERE ') + 'r.player_id IN (' + ','.join(map(str, series_player_ids)) + ')'
    metrics = """
      MAX(TRY_CAST(f.post_match_arena_rating AS DOUBLE)) AS peak,
      COUNT(DISTINCT f.table_id) FILTER (WHERE f.arena_rating_delta IS NOT NULL) AS games,
      AVG(CASE
        WHEN TRY_CAST(f.Game_result AS INTEGER) = 2 THEN 0.0
        WHEN TRY_CAST(f.Game_result AS INTEGER) = 1 AND EXISTS (
          SELECT 1 FROM prepared_full_sample_narrow opponent
          WHERE opponent.table_id = f.table_id AND opponent.player <> f.player
            AND TRY_CAST(opponent.Game_result AS INTEGER) = 2) THEN 1.0
        WHEN TRY_CAST(f.Game_result AS INTEGER) = 1 THEN 0.5
      END) FILTER (WHERE f.arena_rating_delta IS NOT NULL) AS arena_score_rate,
      AVG(TRY_CAST(f.opponent_pre_match_elo AS DOUBLE))
        FILTER (WHERE f.arena_rating_delta IS NOT NULL) AS opponent_elo,
      AVG(TRY_CAST(f.opponent_pre_match_elo AS DOUBLE)) FILTER (
        WHERE f.arena_rating_delta IS NOT NULL AND TRY_CAST(f.Game_result AS INTEGER) IN (1, 2)
      ) AS pr_opponent_elo,
      AVG(TRY_CAST(f.Number_of_turns AS DOUBLE)) FILTER (
        WHERE f.arena_rating_delta IS NOT NULL AND f.is_completed_game
      ) AS turns,
      AVG(TRY_CAST(f.points_per_turn AS DOUBLE)) FILTER (
        WHERE f.arena_rating_delta IS NOT NULL AND f.is_completed_game
      ) AS ppt,
    """ if not histories_only else ""
    return f"""
    SELECT r.season,
      MAX(TRY_CAST(regexp_extract(r.season, '[0-9]+') AS INTEGER)) AS number,
      s.mode, CAST(s.start_utc AS VARCHAR) AS start_utc,
      CAST(s.end_utc AS VARCHAR) AS end_utc, r.rank, r.player, r.player_id,
      r.ending_rating AS end,
      {metrics}
      LIST(CAST(f.game_ended_at AS VARCHAR) ORDER BY f.game_ended_at, f.table_id)
        FILTER (WHERE f.post_match_arena_rating IS NOT NULL AND {series_predicate}) AS timestamps,
      LIST(TRY_CAST(f.post_match_arena_rating AS DOUBLE) ORDER BY f.game_ended_at, f.table_id)
        FILTER (WHERE f.post_match_arena_rating IS NOT NULL AND {series_predicate}) AS ratings
    FROM arena_roster_narrow r
    JOIN arena_seasons_metadata s ON s.season = r.season
    LEFT JOIN prepared_full_sample_narrow f
      ON f.player_id = r.player_id
     AND CAST(f.is_mw AS INTEGER) = CASE WHEN s.mode = 'mw' THEN 1 ELSE 0 END
     AND TRY_CAST(f.game_ended_at AS TIMESTAMPTZ) >= s.start_utc
     AND TRY_CAST(f.game_ended_at AS TIMESTAMPTZ) < s.end_utc
      AND f.table_id NOT IN (SELECT table_id FROM corrupted_tables_narrow)
    {season_filter}
    GROUP BY r.season, s.mode, s.start_utc, s.end_utc,
      r.rank, r.player, r.player_id, r.ending_rating
    ORDER BY r.season, r.rank
    """, [season] if season else []


def _final_mw_sql(request: Mapping[str, Any], view: str) -> tuple[str, list[Any]]:
    # All MW Action Card views share the strict telemetry relations and the
    # authoritative twenty-card catalogue at this dispatch boundary.
    return mw_action_cards_sql(request, view)
    # No execution may continue below the delegated return.
    scoped_request = dict(request)
    scoped_request["is_mw"] = 1
    scope = normalize_scope(scoped_request)
    predicates, parameters = scope_predicates(scope, "f", hard_completed=False)
    action_fields = [
        (1, "Animals", "Animals_Action_Card_Number"),
        (2, "Association", "Association_Action_Card_Number"),
        (3, "Build", "Build_Action_Card_Number"),
        (4, "Cards", "Cards_Action_Card_Number"),
        (5, "Sponsors", "Sponsors_Action_Card_Number"),
    ]
    if view == "general":
        upgrade_fields = {
            "Animals": "Upgraded_Animals_action_card",
            "Association": "Upgraded_Association_action_card",
            "Build": "Upgraded_Build_action_card",
            "Cards": "Upgraded_Cards_action_card",
            "Sponsors": "Upgraded_Sponsors_action_card",
        }
        branches = " UNION ALL ".join(
            f"SELECT {order} AS card_order, {_sql_string(label)} AS card_type, "
            f"TRY_CAST(f.{field} AS INTEGER) AS card_number, f.elo_delta, "
            f"f.pre_match_elo, COALESCE(f.{upgrade_fields[label]}, FALSE) AS upgraded "
            f"FROM prepared_full_sample_narrow f WHERE {predicates} AND f.{field} IS NOT NULL"
            for order, label, field in action_fields
        )
        action_name_case = "CASE card_order " + " ".join(
            f"WHEN {order} THEN {_sql_string(name)}"
            for order, _, _, name in MW_ACTION_CARDS
        ) + " ELSE NULL END"
        return f"""
        WITH actions AS ({branches}), stats AS (
          SELECT card_order, card_type, card_number,
            AVG(elo_delta) AS delta_picked,
            AVG(elo_delta) AS delta_picked_ci_mean,
            STDDEV_SAMP(elo_delta) AS delta_picked_ci_sd,
            COUNT(elo_delta) AS delta_picked_ci_n,
            AVG(elo_delta) FILTER (WHERE upgraded) AS delta_picked_upgraded,
            AVG(elo_delta) FILTER (WHERE upgraded) AS delta_picked_upgraded_ci_mean,
            STDDEV_SAMP(elo_delta) FILTER (WHERE upgraded) AS delta_picked_upgraded_ci_sd,
            COUNT(elo_delta) FILTER (WHERE upgraded) AS delta_picked_upgraded_ci_n,
            AVG(elo_delta) FILTER (WHERE NOT upgraded) AS delta_picked_basic,
            AVG(elo_delta) FILTER (WHERE NOT upgraded) AS delta_picked_basic_ci_mean,
            STDDEV_SAMP(elo_delta) FILTER (WHERE NOT upgraded) AS delta_picked_basic_ci_sd,
            COUNT(elo_delta) FILTER (WHERE NOT upgraded) AS delta_picked_basic_ci_n,
            AVG(pre_match_elo) AS elo_picked, COUNT(*) AS picked_n
          FROM actions WHERE card_number IS NOT NULL
          GROUP BY card_order, card_type, card_number
        )
        SELECT card_order, card_type AS type, card_number,
          card_type AS card_type,
          {action_name_case} AS card_name,
          delta_picked, delta_picked AS delta,
          delta_picked_ci_mean, delta_picked_ci_sd,
          delta_picked_ci_n, delta_picked_upgraded,
          delta_picked_upgraded_ci_mean, delta_picked_upgraded_ci_sd,
          delta_picked_upgraded_ci_n, delta_picked_basic,
          delta_picked_basic_ci_mean, delta_picked_basic_ci_sd,
          delta_picked_basic_ci_n, elo_picked,
          CAST(NULL AS BIGINT) AS available_n, picked_n,
          picked_n AS n_picked,
          CAST(NULL AS DOUBLE) AS picked_pct,
          CAST(NULL AS BIGINT) AS drafted_first_n,
          CAST(NULL AS DOUBLE) AS drafted_first_pct,
          CAST(NULL AS BIGINT) AS drafted_second_n,
          CAST(NULL AS DOUBLE) AS drafted_second_pct,
          CAST(NULL AS BIGINT) AS undrafted_n,
          CAST(NULL AS DOUBLE) AS undrafted_pct
        FROM stats ORDER BY card_order LIMIT ? OFFSET ?
        """, parameters * 5
    if view == "draft":
        branches = " UNION ALL ".join(
            f"SELECT {_sql_string(position)} AS draft_position, TRIM(CAST(f.{field} AS VARCHAR)) AS card_name, f.elo_delta, f.pre_match_elo FROM prepared_full_sample_narrow f WHERE {predicates} AND f.{field} IS NOT NULL"
            for position, field in (("First", "First_drafted_action_card"), ("Second", "Second_drafted_action_card"), ("Third", "Third_drafted_action_card"))
        )
        return f"""
        WITH drafts AS ({branches})
        SELECT draft_position, card_name, AVG(elo_delta) AS delta, AVG(pre_match_elo) AS avg_elo,
          COUNT(*) AS n_drafted, COUNT(elo_delta) AS delta_ci_n,
          AVG(elo_delta) AS delta_ci_mean, STDDEV_SAMP(elo_delta) AS delta_ci_sd
        FROM drafts GROUP BY draft_position, card_name ORDER BY draft_position, card_name
        LIMIT ? OFFSET ?
        """, parameters * 3
    values_sql = ", ".join(f"({number}, {_sql_string(label)}, {_sql_string(field)})" for number, label, field in action_fields)
    if view == "by_map":
        standard_map_columns = []
        for code, full_name in MAPS[:15]:
            key = _map_key(code)
            quoted_name = _sql_string(full_name)
            standard_map_columns.extend([
                f"AVG(elo_delta) FILTER (WHERE map_name = {quoted_name}) AS {key}",
                f"AVG(elo_delta) FILTER (WHERE map_name = {quoted_name}) AS {key}_ci_mean",
                f"STDDEV_SAMP(elo_delta) FILTER (WHERE map_name = {quoted_name}) AS {key}_ci_sd",
                f"COUNT(elo_delta) FILTER (WHERE map_name = {quoted_name}) AS {key}_ci_n",
            ])
        action_name_cases = "CASE " + " ".join(
            f"WHEN card_order = {order} AND card_number = {number} THEN {_sql_string(name)}"
            for order, _, number, name in MW_ACTION_CARDS
        ) + " ELSE NULL END"
        map_projection = ", ".join(
            f"{_map_key(code)}, {_map_key(code)}_ci_mean, "
            f"{_map_key(code)}_ci_sd, {_map_key(code)}_ci_n"
            for code, _ in MAPS[:15]
        )
        return f"""
        WITH config AS (SELECT * FROM (VALUES {values_sql}) v(card_order, card_type, field_name)), actions AS (
          SELECT c.card_order, c.card_type, TRY_CAST(CASE c.field_name
            WHEN 'Animals_Action_Card_Number' THEN f.Animals_Action_Card_Number
            WHEN 'Association_Action_Card_Number' THEN f.Association_Action_Card_Number
            WHEN 'Build_Action_Card_Number' THEN f.Build_Action_Card_Number
            WHEN 'Cards_Action_Card_Number' THEN f.Cards_Action_Card_Number
            ELSE f.Sponsors_Action_Card_Number END AS INTEGER) AS card_number,
            f.Map AS map_name, f.elo_delta, f.pre_match_elo
          FROM prepared_full_sample_narrow f CROSS JOIN config c WHERE {predicates}
        ), grouped AS (
          SELECT card_order, card_type, card_number,
            AVG(elo_delta) AS delta_overall,
            AVG(elo_delta) AS delta_overall_ci_mean,
            STDDEV_SAMP(elo_delta) AS delta_overall_ci_sd,
            COUNT(elo_delta) AS delta_overall_ci_n
            {', ' if standard_map_columns else ''}{', '.join(standard_map_columns)}
          FROM actions
          WHERE card_number IS NOT NULL
          GROUP BY card_order, card_type, card_number
        )
        SELECT card_order, card_type AS type, card_number,
          {action_name_cases} AS card_name,
          delta_overall, delta_overall_ci_mean, delta_overall_ci_sd,
          delta_overall_ci_n,
          {map_projection}
        FROM grouped
        ORDER BY card_order, card_number LIMIT ? OFFSET ?
        """, parameters
    return f"""
    WITH config AS (SELECT * FROM (VALUES {values_sql}) v(card_order, card_type, field_name)),
    actions AS (
      SELECT c.card_order, c.card_type, TRY_CAST(CASE c.field_name
        WHEN 'Animals_Action_Card_Number' THEN f.Animals_Action_Card_Number
        WHEN 'Association_Action_Card_Number' THEN f.Association_Action_Card_Number
        WHEN 'Build_Action_Card_Number' THEN f.Build_Action_Card_Number
        WHEN 'Cards_Action_Card_Number' THEN f.Cards_Action_Card_Number
        ELSE f.Sponsors_Action_Card_Number END AS INTEGER) AS card_number,
        f.table_id, f.player, f.elo_delta, f.pre_match_elo
      FROM prepared_full_sample_narrow f CROSS JOIN config c WHERE {predicates}
    ), pairs AS (
      SELECT a.card_order AS card_1_order, a.card_type AS card_1_type,
        a.card_number AS card_1_number, b.card_order AS card_2_order,
        b.card_type AS card_2_type, b.card_number AS card_2_number,
        AVG(a.elo_delta) AS delta_actual, AVG(a.pre_match_elo) AS avg_elo,
        COUNT(*) AS n_picked, STDDEV_SAMP(a.elo_delta) AS delta_actual_ci_sd,
        COUNT(a.elo_delta) AS delta_actual_ci_n
      FROM actions a JOIN actions b USING(table_id, player)
      WHERE a.card_order < b.card_order AND a.card_number IS NOT NULL AND b.card_number IS NOT NULL
      GROUP BY a.card_order, a.card_type, a.card_number,
        b.card_order, b.card_type, b.card_number
    ), components AS (
      SELECT card_order, card_type, card_number,
        AVG(elo_delta) AS delta,
        AVG(elo_delta) AS component_ci_mean,
        STDDEV_SAMP(elo_delta) AS component_ci_sd,
        COUNT(elo_delta) AS component_ci_n
      FROM actions
      WHERE card_number IS NOT NULL
      GROUP BY card_order, card_type, card_number
    )
    SELECT p.card_1_order,
      p.card_1_type || ' ' || CAST(p.card_1_number AS VARCHAR) AS card_1_key,
      p.card_1_type, p.card_1_number,
      CASE p.card_1_order
        {''.join(f"WHEN {order} THEN {_sql_string(name)} " for order, _, _, name in MW_ACTION_CARDS)}
      END AS card_1_name,
      c1.delta AS delta_1,
      p.card_2_order,
      p.card_2_type || ' ' || CAST(p.card_2_number AS VARCHAR) AS card_2_key,
      p.card_2_type, p.card_2_number,
      CASE p.card_2_order
        {''.join(f"WHEN {order} THEN {_sql_string(name)} " for order, _, _, name in MW_ACTION_CARDS)}
      END AS card_2_name,
      c2.delta AS delta_2,
      p.delta_actual, p.avg_elo, p.n_picked,
      p.card_1_type || ' + ' || p.card_2_type AS pair_type,
      c1.delta + c2.delta AS delta_combined,
      p.delta_actual - c1.delta - c2.delta AS interaction,
      p.delta_actual AS delta_actual_ci_mean,
      p.delta_actual_ci_sd, p.delta_actual_ci_n,
      c1.component_ci_mean AS component_1_ci_mean,
      c1.component_ci_sd AS component_1_ci_sd,
      c1.component_ci_n AS component_1_ci_n,
      c2.component_ci_mean AS component_2_ci_mean,
      c2.component_ci_sd AS component_2_ci_sd,
      c2.component_ci_n AS component_2_ci_n
    FROM pairs p
    JOIN components c1 ON c1.card_order = p.card_1_order
      AND c1.card_type = p.card_1_type AND c1.card_number = p.card_1_number
    JOIN components c2 ON c2.card_order = p.card_2_order
      AND c2.card_type = p.card_2_type AND c2.card_number = p.card_2_number
    ORDER BY interaction DESC NULLS LAST, n_picked DESC,
      card_1_order, card_2_order LIMIT ? OFFSET ?
    """, parameters


def _final_route_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
    view = str(request.get("final_view") or "")
    if view == "arena_top_100": return _final_arena_sql(request)
    if view.startswith("records_"): return _final_records_sql(request, view.removeprefix("records_"))
    if view.startswith("mw_action_cards_"): return _final_mw_sql(request, view.removeprefix("mw_action_cards_"))
    raise ValueError(f"unknown external-data route view: {view}")


SIMPLE_METRIC_FAMILY_ROUTES = {
    ("actions", "starting_position"), ("actions", "upgrades"),
    ("actions", "upgrade_order"), ("actions", "upgrades_by_map"),
    ("icons", "default"), ("build", "enclosures"), ("build", "hexes"),
    ("conservation", "projects"), ("conservation", "project_rewards"),
    ("conservation", "cp_rewards"), ("scoring", "final_score"),
    ("scoring", "appeal"), ("scoring", "conservation_points"),
    ("scoring", "reputation"), ("workers", "general"),
    ("workers", "two_cp_worker"),
}
