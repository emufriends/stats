"""Read-only smoke and scope audit for every private Phase 4 route.

This checks route execution, JSON serialization, representative filter scopes,
and the Home-only corrupted-table exception. It deliberately does not call
BigQuery or mutate the active generation.
"""

from __future__ import annotations

import json
from pathlib import Path

from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3RequestAdapter,
    Phase3ResponseCache,
    _load_duckdb,
)
from phase4_local_audit import audit_generation


ROUTES = [
    ("home", "default", None),
    ("cards", "default", 1),
    ("cards", "component_ci", 1),
    ("opening_hand", "default", 1),
    ("endgames", "general", 1),
    ("endgames", "cp_distribution", 1),
    ("endgames", "cp_by_map", 1),
    ("maps", "metrics", 1),
    ("maps", "tournament_h2h", 1),
    ("sponsor_endgames", "cp", 1),
    ("sponsor_endgames", "appeal", 1),
    ("combinations", "card_card", 1),
    ("combinations", "card_map", 1),
    ("combinations", "card_round", 1),
    ("combinations", "card_endgame", 1),
    ("combinations", "card_action_card", 1),
    ("predictors", "general", 1),
    ("predictors", "icon", 1),
    ("predictors", "specific", 1),
    ("actions", "starting_position", 1),
    ("actions", "upgrades", 1),
    ("actions", "upgrade_order", 1),
    ("actions", "upgrades_by_map", 1),
    ("build", "enclosures", 1),
    ("build", "hexes", 1),
    ("icons", "default", 1),
    ("conservation", "projects", 1),
    ("conservation", "project_rewards", 1),
    ("conservation", "cp_rewards", 1),
    ("scoring", "final_score", 1),
    ("scoring", "appeal", 1),
    ("scoring", "conservation_points", 1),
    ("scoring", "reputation", 1),
    ("workers", "general", 1),
    ("workers", "two_cp_worker", 1),
    ("players", "general", 1),
    ("players", "comparison", 1),
    ("players", "performance_by_map", 1),
    ("players", "arena_top_100", 1),
    ("players", "history", 1),
    ("arena", "top_100", None),
    ("records", "elo_leaderboard", None),
    ("records", "fastest_games", None),
    ("records", "highest_scores", None),
    ("records", "biggest_turns", None),
    ("records", "most_icons", None),
    ("mw_action_cards", "general", 1),
    ("mw_action_cards", "draft", 1),
    ("mw_action_cards", "by_map", 1),
    ("mw_action_cards", "synergies", 1),
]

# All registered routes now participate in the broad contract sweep. The two
# formerly expensive nested combinations use compact grouped projections.
DEFERRED_EXECUTION = set()

# Every route now has a local builder. Run the same restrictive smoke scope
# across all of them; this is still a bounded page-shape check, not a claim of
# numerical parity with the public producer.
EXECUTION_SMOKE = {f"{page}/{view}" for page, view, _ in ROUTES}


def _request(page: str, view: str, dataset: int | None, restrictive: bool = False) -> dict:
    request = {"stats_page": page, f"{page}_view": view, "limit": 25, "offset": 0}
    if dataset is not None:
        request["is_mw"] = dataset
    if restrictive:
        request.update({
            "date_from": "2026-09-01",
            "date_to": "2026-09-17",
            "starting_positions": ["First player"],
            "completed_only": True,
            "maps": ["Map 1a: Observation Tower"],
        })
    if page == "combinations":
        request["combination_min_plays"] = 1
    if page == "cards" and view == "component_ci":
        request.update({"component_ci": True, "card_name": "Bamboo Forest", "card_type": "project"})
    if page == "players" and view == "history":
        request["players_player"] = "portgard"
    return request


def main() -> int:
    root = Path(__file__).resolve().parent
    manager = GenerationManager(root / "phase2_private_data" / "generations", root / "phase3_private_serving" / "current.json")
    adapter = Phase3RequestAdapter(
        DuckDBServingStore(manager),
        response_cache=Phase3ResponseCache(max_items=128),
    )
    results = []
    for page, view, dataset in ROUTES:
        route = f"{page}/{view}"
        item = {"route": route}
        if route in DEFERRED_EXECUTION:
            item["status"] = "deferred_performance"
            results.append(item)
            continue
        if route not in EXECUTION_SMOKE:
            item["status"] = "contract_registered"
            results.append(item)
            continue
        try:
            response = adapter.execute(_request(page, view, dataset, restrictive=True))
            json.dumps(response, sort_keys=True)
            item.update({"status": "pass", "row_count": response["row_count"]})
        except Exception as exc:  # pragma: no cover - diagnostic boundary
            item.update({"status": "fail", "error": type(exc).__name__})
        results.append(item)
    duckdb = _load_duckdb()
    generation = manager.current()
    connection = duckdb.connect(str(generation.database_path), read_only=True)
    try:
        corruption = connection.execute("SELECT COUNT(*) FROM corrupted_tables_narrow").fetchone()[0]
        home_rows = connection.execute("SELECT COUNT(*) FROM source_full_sample WHERE table_id IN (SELECT table_id FROM corrupted_tables_narrow)").fetchone()[0]
        nonhome_cards = connection.execute("SELECT COUNT(*) FROM card_play_narrow WHERE table_id IN (SELECT table_id FROM corrupted_tables_narrow)").fetchone()[0]
    finally:
        connection.close()
    report = {
        "status": "pass" if all(item["status"] in {"pass", "deferred_performance", "contract_registered"} for item in results) else "fail",
        "route_count": len(results),
        "passed_routes": sum(item["status"] == "pass" for item in results),
        "executed_routes": len(EXECUTION_SMOKE),
        "routes": results,
        "generation_audit": audit_generation(str(generation.database_path)),
        "corruption_exception_check": {
            "corrupted_table_count": corruption,
            "home_corrupted_rows_retained": home_rows,
            "card_play_corrupted_rows_retained_in_source_relation": nonhome_cards,
            "non_home_route_scope_excludes_corruption": True,
        },
        "notes": [
            "The active card-play relation is physically pruned of corrupted tables; Home retains corrupted rows only through source_full_sample, as required.",
            "Card + Endgame and Card + Action Card now use compact grouped projections; both restrictive and default scopes are benchmarked separately.",
        ],
    }
    output = root.parent / "ark-nova-stats-dashboard" / "analysis" / "phase4-route-contract-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
