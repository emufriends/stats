"""Read-only population, snapshot-version, and representative parity audit.

The contract matrix is intentionally executable documentation: every active
dashboard route is listed with its observation unit and the population choices
that can legitimately make a similarly named metric differ elsewhere.

All game-derived contracts except Home exclude prepared Full Sample tables with
``is_corrupted_game = TRUE``. Home intentionally retains those tables.

Usage:
  python audit_population_parity.py
  python audit_population_parity.py --bigquery
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import urllib.request


PROJECT = os.environ.get("BIGQUERY_JOB_PROJECT", "ark-nova-stats-dashboard")
DATASET = "ark-nova-stats-dashboard.dashboard_cache"
TABLES = {
    "logs": f"{DATASET}.card_logs_prepared",
    "full": f"{DATASET}.full_stats_prepared",
    "players": f"{DATASET}.players_stats_prepared",
    "players_identity": f"{DATASET}.players_identity_daily_rollup",
    "players_map": f"{DATASET}.players_map_performance_rollup",
    "card_plays": f"{DATASET}.card_plays_prepared",
    "card_pairs": f"{DATASET}.card_pair_daily_aggregates",
    "home": f"{DATASET}.home_observations_prepared",
    "endgames": f"{DATASET}.endgame_events_prepared",
    "actions": f"{DATASET}.action_starting_observations",
    "conservation": f"{DATASET}.conservation_count_observations",
    "predictors": f"{DATASET}.predictor_specific_observations",
    "sponsor_endgames": f"{DATASET}.sponsor_endgame_observations",
    "mw_players": f"{DATASET}.mw_action_card_player_observations",
    "mw_map": f"{DATASET}.mw_action_card_map_daily_aggregates",
    "mw_synergies": f"{DATASET}.mw_action_card_synergy_daily_aggregates",
    "card_action": f"{DATASET}.card_action_card_observations",
    "card_action_agg": f"{DATASET}.card_action_card_daily_aggregates",
}
CORRUPTED_GAME_POLICY = "exclude from every game-derived contract except Home"
STANDARD_MAPS = (
    "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
    "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
    "Map 5a: Park Restaurant", "Map 6a: Research Institute",
    "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
    "Map 9: Geographical Zoo", "Map 10: Rescue Station",
    "Map 11: Caves", "Map 12: Artificial Intelligence",
    "Map 13: Drawing Board", "Map 14: Lagoon", "Map T1: Tournament 1",
)


CONTRACTS = (
    # page, views, source, observation unit, completion, special population
    ("home", "overview", TABLES["home"], "table/player moments", "optional", "all configured maps"),
    ("cards", "general", TABLES["card_plays"], "player-game-card", "optional", "Full Sample card plays"),
    ("opening_hand", "general", TABLES["logs"], "player-game-card", "optional", "Log Sample"),
    ("endgames", "general|cp_distribution|cp_by_map", TABLES["endgames"], "player-game-endgame", "mixed", "endgame eligibility by view"),
    ("sponsor_endgames", "cp|appeal", TABLES["sponsor_endgames"], "player-game-sponsor-endgame", "mixed", "sponsor reward observations"),
    ("combinations", "card_card|card_map|card_round|card_endgame", TABLES["card_pairs"], "player-game combination", "optional", "view-specific component scopes"),
    ("combinations", "card_action_card", TABLES["card_action_agg"], "player-game-card-action-card", "optional", "telemetry-complete MW only"),
    ("actions", "starting_position|upgrades|upgrade_order|upgrades_by_map", TABLES["actions"], "player-game action observation", "mixed", "view-specific action validity"),
    ("predictors", "general|icon|specific", TABLES["predictors"], "player-game predictor condition", "hard for Specific", "predictor validity by view"),
    ("icons", "general", TABLES["full"], "player-game icon count", "hard", "valid icon values"),
    ("mw_action_cards", "general|draft", TABLES["mw_players"], "player-game-action-card/table-card", "optional", "telemetry-complete MW only"),
    ("mw_action_cards", "by_map", TABLES["mw_map"], "player-game-action-card-map", "optional", "same-map telemetry-complete MW"),
    ("mw_action_cards", "synergies", TABLES["mw_synergies"], "player-game-action-card pair", "optional", "telemetry-complete MW only"),
    ("build", "enclosures|hexes", TABLES["full"], "player-game build observation", "mixed", "valid view-specific values"),
    ("conservation", "projects|project_rewards|cp_rewards", TABLES["conservation"], "player-game/reward opportunity", "mixed", "view-specific denominators"),
    ("scoring", "final_score|appeal|conservation_points|reputation", TABLES["full"], "completed player-game", "hard", "valid scoring value"),
    ("workers", "general|two_cp_worker", TABLES["full"], "player-game worker count", "mixed", "view-specific worker validity"),
    ("maps", "metrics", TABLES["full"], "player-game map", "hard", "analytical map population"),
    ("maps", "tournament_h2h", "static tournament bundle", "table", "bundle-defined", "tournament membership"),
    ("players", "general|comparison", TABLES["players_identity"], "completed player-game", "hard", "merged identity"),
    ("players", "performance_by_map", TABLES["players_map"], "player-game-map", "optional", "merged identity; Last X per map"),
    ("arena", "top_100", "Arena CSV + prepared Players", "exact-alias Arena game", "mixed", "Games is all matched; Turns/PPT completed"),
    ("records", "elo_leaderboard", "Google Sheet Masters", "ranked player", "n/a", "dataset-neutral external source"),
    ("records", "fastest_games|highest_scores|biggest_turns|most_icons", "snapshots + Sheets where documented", "game/player record", "view-specific", "combined MW/Base"),
)

VERSION_NEUTRAL_PATHS = ("/records/elo-leaderboard/",)
PACK_URL = (
    "https://storage.googleapis.com/ark-nova-stats-dashboard-cache/"
    "card-stats/bootstrap/default-pack.json"
)
REQUIRED_SYNERGY_PATHS = {
    *{
        f"card-stats/combinations/{view}/default-{dataset}.json"
        for view in ("card-card", "card-map", "card-round", "card-endgame")
        for dataset in ("mw", "base")
    },
    "card-stats/combinations/card-action-card/default-mw.json",
    "card-stats/mw-action-cards/synergies/default-mw.json",
}


def _load_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def audit_pack(pack: dict) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    version = pack.get("data_version")
    snapshots = pack.get("snapshots") or {}
    missing = sorted(REQUIRED_SYNERGY_PATHS - set(snapshots))
    if missing:
        failures.append(f"missing {len(missing)} required Synergy snapshots")
    for path, payload in snapshots.items():
        neutral = any(marker in path for marker in VERSION_NEUTRAL_PATHS)
        snapshot_version = payload.get("data_version")
        if not neutral and snapshot_version != version:
            failures.append(
                f"version mismatch: {path}={snapshot_version!r}, pack={version!r}"
            )
    for path, payload in snapshots.items():
        if "/records/elo-leaderboard/" not in path:
            continue
        notes.append(
            f"{path}: external source={payload.get('source')!r}, "
            f"source_status={payload.get('source_status')!r}, "
            f"updated={payload.get('cache_updated_at')!r}"
        )
    return failures, notes


def audit_display_parity(pack: dict) -> tuple[list[str], list[str]]:
    """Check rounded public component values after version parity is established."""
    snapshots = pack.get("snapshots") or {}
    failures: list[str] = []
    notes: list[str] = []

    def rows(path):
        return (snapshots.get(path) or {}).get("data") or []

    def compare(label, actual, expected, key):
        if actual is None or expected is None:
            return
        if abs(float(actual) - float(expected)) > 0.0005:
            failures.append(
                f"{label} mismatch for {key}: {actual!r} != {expected!r}"
            )

    for dataset in ("mw", "base"):
        card_means = {
            row.get("card_name"): row.get("delta_played")
            for row in rows(f"card-stats/default-{dataset}.json")
        }
        endgame_means = {
            # Endgames reuses the shared Cards response shape: delta_played is
            # the dealt estimate, while delta_in_hand is the scored estimate.
            row.get("card_name"): row.get("delta_in_hand")
            for row in rows(f"card-stats/endgames/default-{dataset}.json")
        }
        for row in rows(f"card-stats/combinations/card-card/default-{dataset}.json"):
            compare("Card + Card component 1", row.get("delta_1"), card_means.get(row.get("card_1")), row.get("card_1"))
            compare("Card + Card component 2", row.get("delta_2"), card_means.get(row.get("card_2")), row.get("card_2"))
        for view in ("card-map", "card-round"):
            for row in rows(f"card-stats/combinations/{view}/default-{dataset}.json"):
                compare(f"{view} card component", row.get("delta_general"), card_means.get(row.get("card_name")), row.get("card_name"))
        for row in rows(f"card-stats/combinations/card-endgame/default-{dataset}.json"):
            compare("Card + Endgame card component", row.get("delta_card"), card_means.get(row.get("card_name")), row.get("card_name"))
            compare("Card + Endgame endgame component", row.get("delta_endgame"), endgame_means.get(row.get("endgame_name")), row.get("endgame_name"))

    action_means = {
        row.get("card_name"): row.get("delta_picked")
        for row in rows("card-stats/mw-action-cards/general/default-mw.json")
    }
    for row in rows("card-stats/mw-action-cards/synergies/default-mw.json"):
        compare("MW Synergy component 1", row.get("delta_1"), action_means.get(row.get("card_1_name")), row.get("card_1_name"))
        compare("MW Synergy component 2", row.get("delta_2"), action_means.get(row.get("card_2_name")), row.get("card_2_name"))
    for row in rows("card-stats/combinations/card-action-card/default-mw.json"):
        compare("Card + Action Card action component", row.get("delta_action"), action_means.get(row.get("action_card_name")), row.get("action_card_name"))

    notes.extend((
        "Card + Action Card normal-card components intentionally use a telemetry-complete MW subset.",
        "MW By-map versus General same-map parity requires the optional BigQuery audit.",
        "Arena total/completed decomposition requires the optional BigQuery audit.",
    ))
    return failures, notes


def audit_representative_bigquery() -> tuple[list[str], list[str]]:
    """Reconcile the scoped examples that motivated the parity contract."""
    from google.cloud import bigquery

    standard_maps = ", ".join(repr(value) for value in STANDARD_MAPS)
    scope = f"""
      game_date >= DATE '2025-01-01'
      AND Map IN ({standard_maps})
      AND COALESCE(pre_match_elo, 0) >= 300
      AND COALESCE(opponent_pre_match_elo, 0) >= 300
    """
    query = f"""
    WITH
    broad_card AS (
      SELECT table_id, player, card_name, ANY_VALUE(elo_delta) AS elo_delta
      FROM `{TABLES['card_plays']}`
      WHERE CAST(is_mw AS INT64) = 1 AND {scope}
      GROUP BY table_id, player, card_name
    ),
    telemetry_card AS (
      SELECT table_id, player, card_name, ANY_VALUE(elo_delta) AS elo_delta
      FROM `{TABLES['card_action']}`
      WHERE {scope}
      GROUP BY table_id, player, card_name
    ),
    direct_action AS (
      SELECT table_id, player, card_key, ANY_VALUE(elo_delta) AS elo_delta
      FROM `{TABLES['mw_players']}`
      WHERE {scope}
      GROUP BY table_id, player, card_key
    ),
    paired_action AS (
      -- Card + Action Card deliberately sources its displayed action-card
      -- baseline from the complete telemetry-valid MW player population, not
      -- only from rows having a normal-card log observation.
      SELECT table_id, player, card_key, ANY_VALUE(elo_delta) AS elo_delta
      FROM `{TABLES['mw_players']}`
      WHERE {scope}
      GROUP BY table_id, player, card_key
    )
    SELECT 'amazon_broad' AS check_name, COUNT(*) AS n, AVG(elo_delta) AS mean
    FROM broad_card WHERE card_name = 'Amazon House'
    UNION ALL
    SELECT 'amazon_telemetry', COUNT(*), AVG(elo_delta)
    FROM telemetry_card WHERE card_name = 'Amazon House'
    UNION ALL
    SELECT 'snap_general', COUNT(*), AVG(elo_delta)
    FROM direct_action WHERE card_key = 'Cards 3'
    UNION ALL
    SELECT 'snap_card_action', COUNT(*), AVG(elo_delta)
    FROM paired_action WHERE card_key = 'Cards 3'
    """
    rows = {
        row["check_name"]: {"n": int(row["n"]), "mean": float(row["mean"])}
        for row in bigquery.Client(project=PROJECT).query(query).result()
    }
    failures: list[str] = []
    notes = [f"{name}: n={value['n']}, mean={value['mean']:.12f}" for name, value in rows.items()]
    if rows["snap_general"] != rows["snap_card_action"]:
        failures.append("Snap action-card populations disagree under identical scope")
    if rows["amazon_broad"] == rows["amazon_telemetry"]:
        failures.append("Amazon House broad and telemetry scopes unexpectedly collapsed")

    arena_query = f"""
    SELECT
      COUNT(*) AS total,
      COUNTIF(table_conceded = 0 AND end_game_triggered IS TRUE) AS completed,
      COUNTIF(table_conceded = 1) AS conceded,
      COUNTIF(table_conceded = 0 AND end_game_triggered IS NOT TRUE) AS non_triggered
    FROM `{TABLES['players']}`
    WHERE player = 'trusting-seagull275' AND arena_season = 'S13'
    """
    arena = dict(next(iter(bigquery.Client(project=PROJECT).query(arena_query).result())).items())
    if int(arena["total"]) != int(arena["completed"]) + int(arena["conceded"]) + int(arena["non_triggered"]):
        failures.append("Arena population decomposition does not add to total")
    notes.append(
        "Arena trusting-seagull275 S13: "
        f"{arena['total']}={arena['completed']}+{arena['conceded']}+{arena['non_triggered']}"
    )
    return failures, notes


def main_cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bigquery", action="store_true", help="run representative read-only SQL checks")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()
    failures: list[str] = []
    notes: list[str] = [
        f"population contracts: {len(CONTRACTS)} active route/view families",
        f"corrupted games: {CORRUPTED_GAME_POLICY}",
    ]
    pack = _load_json(PACK_URL)
    pack_failures, pack_notes = audit_pack(pack)
    failures.extend(pack_failures)
    notes.extend(pack_notes)
    display_failures, display_notes = audit_display_parity(pack)
    failures.extend(display_failures)
    notes.extend(display_notes)
    if args.bigquery:
        bq_failures, bq_notes = audit_representative_bigquery()
        failures.extend(bq_failures)
        notes.extend(bq_notes)
    result = {"status": "error" if failures else "ok", "failures": failures, "notes": notes}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["status"].upper())
        for line in failures:
            print(f"FAIL: {line}")
        for line in notes:
            print(f"INFO: {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main_cli())
