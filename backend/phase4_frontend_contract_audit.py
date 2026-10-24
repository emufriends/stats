"""Historical field-presence audit against the current frontend contract.

This audit is local and read-only.  It checks the response envelope, JSON
serializability, and representative row fields used by the dashboard.  It
does not query BigQuery or connect the public frontend to DuckDB. Field presence
does not prove labels, populations, values, paging, or rendering semantics; the
restoration release gate is defined in ``contracts/dashboard-routes.v1.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3RequestAdapter,
    Phase3ResponseCache,
)
from phase4_route_contract_audit import DEFERRED_EXECUTION, EXECUTION_SMOKE, ROUTES, _request


REQUIRED_FIELDS = {
    "home/default": {"metric", "value", "observations"},
    "cards/default": {"card_name", "card_type", "delta_played", "n_played"},
    "opening_hand/default": {"card_name", "delta_in_hand", "n_played"},
    "endgames/general": {"card_name", "delta_played", "n_played"},
    "maps/metrics": {"sort_order", "metric"},
    "sponsor_endgames/cp": {"sponsor", "avg_cp", "n_played"},
    "combinations/card_card": {"card_1", "type_1", "card_2", "type_2", "interaction", "n_played"},
    "combinations/card_endgame": {"card_name", "endgame_name", "interaction", "n_played"},
    "combinations/card_action_card": {"card_name", "action_card_name", "interaction", "n_played"},
    "predictors/general": {"sort_order", "condition"},
    "actions/upgrades": {"sort_order", "label"},
    "conservation/projects": {"subject", "count_value", "sort_order", "avg"},
    "scoring/final_score": {"bucket_key", "bucket_label"},
    "workers/general": {"sort_order", "label"},
    "players/general": {"player", "metric", "all"},
    "players/performance_by_map": {"map_name", "games"},
    "arena/top_100": {"player", "games"},
    "records/elo_leaderboard": {"player"},
    "mw_action_cards/general": {"card_type", "card_number", "delta", "n_picked"},
    "build/hexes": {"bucket_key", "bucket_label", "avg"},
}


def run() -> dict:
    root = Path(__file__).resolve().parent
    dashboard = root.parent / "ark-nova-stats-dashboard"
    manager = GenerationManager(
        root / "phase2_private_data" / "generations",
        root / "phase3_private_serving" / "current.json",
    )
    adapter = Phase3RequestAdapter(
        DuckDBServingStore(manager),
        response_cache=Phase3ResponseCache(max_items=64),
    )
    generation = manager.current()
    route_results = []
    for page, view, dataset in ROUTES:
        route = f"{page}/{view}"
        item = {"route": route}
        if route in DEFERRED_EXECUTION:
            item["status"] = "deferred_default_performance"
            route_results.append(item)
            continue
        if route not in EXECUTION_SMOKE:
            item["status"] = "registered_not_sampled"
            route_results.append(item)
            continue
        try:
            payload = adapter.execute(_request(page, view, dataset, restrictive=True))
            json.dumps(payload, sort_keys=True)
            data = payload.get("data") or []
            if route == "arena/top_100" and isinstance(data, dict):
                rows = next((value.get("rows", []) for value in data.values()
                             if isinstance(value, dict) and value.get("rows")), [])
            else:
                rows = data if isinstance(data, list) else []
            item.update({
                "status": "pass",
                "row_count": payload.get("row_count"),
                "envelope_fields": sorted(payload.keys()),
                "data_version": payload.get("data_version"),
            })
            required = REQUIRED_FIELDS.get(route, set())
            if rows:
                missing = sorted(required - set(rows[0]))
                if missing:
                    item.update({"status": "fail", "missing_row_fields": missing})
            else:
                item["row_field_check"] = "no_rows_under_restrictive_scope"
        except Exception as exc:  # pragma: no cover - diagnostic boundary
            item.update({"status": "fail", "error": type(exc).__name__})
        route_results.append(item)

    failures = [item for item in route_results if item["status"] == "fail"]
    report = {
        "status": "pass" if not failures else "fail",
        "generation": generation.generation_id,
        "data_version": generation.data_version,
        "route_count": len(route_results),
        "executed_routes": sum(item["status"] == "pass" for item in route_results),
        "deferred_default_routes": sum(item["status"] == "deferred_default_performance" for item in route_results),
        "registered_not_sampled": sum(item["status"] == "registered_not_sampled" for item in route_results),
        "frontend_source": {
            "index": str(dashboard / "index.html"),
            "page_modules": len(list((dashboard / "assets" / "js" / "pages").glob("*.js"))),
        },
        "routes": route_results,
        "notes": [
            "Envelope and field checks are representative; empty restricted result sets cannot expose row fields.",
            "Numerical parity remains a separate gate and is only claimed where same-generation producer references exist.",
            "The public frontend is not connected to this private API yet.",
        ],
    }
    output = dashboard / "analysis" / "phase4-frontend-contract-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    raise SystemExit(0 if run()["status"] == "pass" else 1)
