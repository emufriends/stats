"""Historical shape audit against the last legacy producer pack.

The legacy default pack is an immutable output of the old BigQuery producer.
It is used only as a schema/shape oracle because its data version predates the
active DuckDB generation.  Numerical parity is deliberately not inferred from
this report.  The script never queries BigQuery and never imports route SQL.
It does not prove labels, populations, or numerical parity and must not be used
alone as a release gate. See ``contracts/dashboard-routes.v1.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3RequestAdapter,
    Phase3ResponseCache,
    _load_duckdb,
    project_ordinary_ci_fields,
)


ROUTE_SNAPSHOTS = {
    "cards/default": "card-stats/default-mw.json",
    "opening_hand/default": "card-stats/opening-hand/default-mw.json",
    "endgames/general": "card-stats/endgames/default-mw.json",
    "endgames/cp_distribution": "card-stats/endgames/cp-distribution/default-mw.json",
    "endgames/cp_by_map": "card-stats/endgames/cp-by-map/default-mw.json",
    "maps/metrics": "card-stats/maps/metrics/default-mw.json",
    "maps/tournament_h2h": "card-stats/maps/tournament_h2h/default-mw.json",
    "sponsor_endgames/cp": "card-stats/sponsor-endgames/cp/default-mw.json",
    "sponsor_endgames/appeal": "card-stats/sponsor-endgames/appeal/default-mw.json",
    "icons/default": "card-stats/icons/default-mw.json",
    "build/enclosures": "card-stats/build/enclosures/delta/default-mw.json",
    "build/hexes": "card-stats/build/hexes/delta/default-mw.json",
    "predictors/general": "card-stats/predictors/general/default-mw.json",
    "predictors/icon": "card-stats/predictors/icon/default-mw.json",
    "predictors/specific": "card-stats/predictors/specific/default-mw.json",
    "actions/starting_position": "card-stats/actions/starting_position/delta/default-mw.json",
    "actions/upgrades": "card-stats/actions/upgrades/delta/default-mw.json",
    "actions/upgrade_order": "card-stats/actions/upgrade_order/delta/default-mw.json",
    "actions/upgrades_by_map": "card-stats/actions/upgrades_by_map/delta/default-mw.json",
    "conservation/projects": "card-stats/conservation/projects/default-mw.json",
    "conservation/project_rewards": "card-stats/conservation/project-rewards/default-mw.json",
    "conservation/cp_rewards": "card-stats/conservation/cp-rewards/default-mw.json",
    "scoring/final_score": "card-stats/scoring/final-score/default-mw.json",
    "scoring/appeal": "card-stats/scoring/appeal/default-mw.json",
    "scoring/conservation_points": "card-stats/scoring/conservation-points/default-mw.json",
    "scoring/reputation": "card-stats/scoring/reputation/default-mw.json",
    "workers/general": "card-stats/workers/general/default-mw.json",
    "workers/two_cp_worker": "card-stats/workers/two-cp-worker/default-mw.json",
    "players/general": "card-stats/players/general/default-mw.json",
    "records/elo_leaderboard": "card-stats/records/elo-leaderboard/default-mw.json",
    "records/fastest_games": "card-stats/records/fastest-games/default-mw.json",
    "records/highest_scores": "card-stats/records/highest-scores/default-mw.json",
    "records/biggest_turns": "card-stats/records/biggest-turns/default-mw.json",
    "records/most_icons": "card-stats/records/most-icons/default-mw.json",
    "combinations/card_card": "card-stats/combinations/card-card/default-mw.json",
    "combinations/card_map": "card-stats/combinations/card-map/default-mw.json",
    "combinations/card_round": "card-stats/combinations/card-round/default-mw.json",
    "combinations/card_endgame": "card-stats/combinations/card-endgame/default-mw.json",
    "combinations/card_action_card": "card-stats/combinations/card-action-card/default-mw.json",
    "arena/top_100": "card-stats/players/arena/latest.json",
    "mw_action_cards/general": "card-stats/mw-action-cards/general/default-mw.json",
    "mw_action_cards/by_map": "card-stats/mw-action-cards/by-map/default-mw.json",
    "mw_action_cards/synergies": "card-stats/mw-action-cards/synergies/default-mw.json",
}


def _request(route: str) -> dict[str, Any]:
    page, view = route.split("/", 1)
    request: dict[str, Any] = {"stats_page": page, "is_mw": 1, "limit": 1}
    field = {
        "endgames": "endgames_view", "maps": "maps_view",
        "sponsor_endgames": "sponsor_endgames_view",
        "combinations": "combinations_view", "build": "build_view",
        "predictors": "predictors_view", "actions": "actions_view",
        "conservation": "conservation_view", "scoring": "scoring_view",
        "workers": "workers_view", "players": "players_view",
        "arena": "arena_view", "records": "records_view",
        "mw_action_cards": "mw_action_cards_view",
    }.get(page)
    if field:
        request[field] = view
    if page == "combinations":
        request["combination_min_plays"] = 1
    return request


def _first_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    def first(value: Any) -> dict[str, Any] | None:
        if isinstance(value, list):
            return value[0] if value and isinstance(value[0], dict) else None
        if isinstance(value, dict):
            if isinstance(value.get("rows"), list) and value["rows"]:
                return value["rows"][0]
            for child in value.values():
                found = first(child)
                if found is not None:
                    return found
        return None
    data = payload.get("data")
    return first(data)


def _retired_fields(route: str) -> set[str]:
    if route.startswith("combinations/") or route == "mw_action_cards/synergies":
        return {name for name in (
            "interaction_ci95_se", "interaction_ci95_low",
            "interaction_ci95_high", "interaction_ci95_cluster_n",
            "interaction_ci95_method",
        )}
    return set()


def run(pack_path: Path, manager: GenerationManager) -> dict[str, Any]:
    pack_bytes = pack_path.read_bytes()
    pack = json.loads(pack_bytes)
    adapter = Phase3RequestAdapter(
        DuckDBServingStore(manager), Phase3ResponseCache(max_items=4)
    )
    generation = manager.current()
    if generation is None:
        raise RuntimeError("no active DuckDB generation")
    connection = _load_duckdb().connect(str(generation.database_path), read_only=True)
    results = []
    try:
        for route, snapshot_path in ROUTE_SNAPSHOTS.items():
            legacy = pack["snapshots"].get(snapshot_path)
            item: dict[str, Any] = {"route": route, "snapshot": snapshot_path}
            if not isinstance(legacy, dict):
                item.update(status="missing_legacy_snapshot")
                results.append(item)
                continue
            expected_row = _first_row(legacy)
            try:
                normalized = adapter.normalize_request(_request(route))
                sql, parameters = adapter._sql_for(normalized)
                if route != "arena/top_100":
                    parameters.extend([0, 0])
                cursor = connection.execute(sql, parameters)
                planned = {column[0]: None for column in cursor.description}
                actual = set(project_ordinary_ci_fields(planned))
            except Exception as exc:  # diagnostic boundary
                item.update(status="candidate_error", error=f"{type(exc).__name__}: {exc}")
                results.append(item)
                continue
            if expected_row is None:
                item.update(status="empty_legacy_contract")
                results.append(item)
                continue
            retired = _retired_fields(route)
            expected = set(expected_row) - retired
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            item.update({
                "status": "pass" if not missing else "fail",
                "legacy_field_count": len(expected),
                "candidate_field_count": len(actual),
                "missing_fields": missing,
                "extra_fields": extra,
                "retired_fields_ignored": sorted(retired & set(expected_row)),
            })
            results.append(item)
    finally:
        connection.close()
    passed = sum(item["status"] == "pass" for item in results)
    failed = sum(item["status"] == "fail" for item in results)
    unresolved = len(results) - passed
    return {
        "status": "pass" if failed == 0 and passed == len(results) else "fail",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "oracle": {
            "path": str(pack_path),
            "sha256": hashlib.sha256(pack_bytes).hexdigest(),
            "source_url": "https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/bootstrap/default-pack.json",
            "producer": "legacy_bigquery_default_pack",
            "data_version": pack.get("data_version"),
            "usage": "schema_and_shape_only",
        },
        "candidate": {
            "generation": generation.generation_id if generation else None,
            "data_version": generation.data_version if generation else None,
        },
        "mapped_routes": len(results),
        "passed_routes": passed,
        "failed_routes": failed,
        "unresolved_routes": unresolved,
        "routes": results,
        "notes": [
            "Different data versions prevent numerical claims from this report.",
            "Retired additive Synergy CI fields are intentionally ignored.",
            "Extra candidate fields are reported but do not fail compatibility; missing legacy fields do.",
            "Unmapped routes require local raw-source reference producers.",
        ],
    }


def main() -> int:
    root = Path(__file__).resolve().parent
    dashboard = root.parent / "ark-nova-stats-dashboard" / "analysis"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pack", type=Path,
        default=root / "phase2_private_data" / "reference_snapshots" / "legacy-default-pack-20260914.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=dashboard / "phase4-legacy-contract-audit.json",
    )
    args = parser.parse_args()
    report = run(
        args.pack,
        GenerationManager(
            root / "phase2_private_data" / "generations",
            root / "phase3_private_serving" / "current.json",
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "mapped_routes": report["mapped_routes"],
        "passed_routes": report["passed_routes"],
        "failed_routes": report["failed_routes"],
        "unresolved_routes": report["unresolved_routes"],
    }, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
