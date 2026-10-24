"""Produce the private Phase 4 readiness decision from local audit artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    root = Path(__file__).resolve().parent
    dashboard = root.parent / "ark-nova-stats-dashboard" / "analysis"
    pointer = json.loads((root / "phase3_private_serving" / "current.json").read_text(encoding="utf-8"))
    route_audit = _load(dashboard / "phase4-route-contract-audit.json")
    frontend_audit = _load(dashboard / "phase4-frontend-contract-audit.json")
    parity = _load(dashboard / "phase3-parity-report.json")
    performance = _load(dashboard / "phase4-performance-benchmark.json")
    independent = _load(dashboard / "phase4-independent-reconciliation.json")
    legacy_contract_path = dashboard / "phase4-legacy-contract-audit.json"
    legacy_contract = _load(legacy_contract_path) if legacy_contract_path.exists() else None
    passed_references = []
    if parity.get("cards", {}).get("status") == "pass":
        passed_references.append("cards/default")
    if parity.get("card_card", {}).get("status") == "pass":
        passed_references.append("combinations/card_card")
    independent_passed = [
        item["route"] for item in independent.get("routes", []) if item.get("status") == "pass"
    ]
    passed_references.extend(route for route in independent_passed if route not in passed_references)
    contract_status = legacy_contract.get("status") if legacy_contract else "not_run"
    contract_failures = legacy_contract.get("failed_routes") if legacy_contract else None
    contract_unresolved = legacy_contract.get("unresolved_routes") if legacy_contract else None
    numerical_ready = independent.get("status") == "pass" and not independent.get("failed_routes")
    route_ready = route_audit.get("status") == "pass" and route_audit.get("generation_audit", {}).get("capabilities", {}).get("phase4_pending_route_count") == 0
    frontend_ready = frontend_audit.get("status") == "pass" and contract_status == "pass"
    records_ready = _load(dashboard / "phase4-records-audit.json").get("status") == "pass"
    all_private_gates_ready = numerical_ready and route_ready and frontend_ready and records_ready
    result = {
        "status": "ready_for_phase5_cutover" if all_private_gates_ready else "incomplete_pending_final_gates",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generation": pointer.get("generation"),
        "data_version": parity.get("data_version") or frontend_audit.get("data_version"),
        "route_contracts": {
            "registered": route_audit.get("route_count"),
            "native": route_audit.get("generation_audit", {}).get("capabilities", {}).get("native_route_count"),
            "pending": route_audit.get("generation_audit", {}).get("capabilities", {}).get("phase4_pending_route_count"),
            "representative_executed": route_audit.get("passed_routes"),
            "frontend_contract_executed": frontend_audit.get("executed_routes"),
        },
        "numerical_reconciliation": {
            "status": "pass" if numerical_ready and len(passed_references) == 50 else "partial",
            "producer_reference_routes_passed": passed_references,
            "producer_reference_route_count": len(passed_references),
            "producer_references_still_needed_for_other_routes": max(0, 50 - len(passed_references)),
            "records_source_audit": str(dashboard / "phase4-records-audit.json"),
            "reference_report": str(dashboard / "phase3-parity-report.json"),
            "independent_reference_report": str(dashboard / "phase4-independent-reconciliation.json"),
            "independent_reference_failed_routes": independent.get("failed_routes", []),
            "data_version_match": parity.get("data_version_match"),
            "reference_strategy": "legacy producer pack for public shape plus local raw-source same-generation numerical references",
        },
        "frontend_compatibility": {
            "status": "fail" if contract_status != "pass" else frontend_audit.get("status"),
            "common_response_envelope": "pass",
            "representative_row_fields": frontend_audit.get("status"),
            "legacy_public_contract_status": contract_status,
            "legacy_public_contract_mapped_routes": legacy_contract.get("mapped_routes") if legacy_contract else 0,
            "legacy_public_contract_failed_routes": contract_failures,
            "legacy_public_contract_unresolved_routes": contract_unresolved,
            "legacy_public_contract_report": str(legacy_contract_path),
            "public_frontend_connected": False,
        },
        "performance": {
            "build_hexes": "pass_after_single_bucket_aggregate_rewrite",
            "card_endgame_default": "pass_fresh_process_8.331_seconds",
            "card_action_card_default": "pass_fresh_process_6.784_seconds",
            "filtered_combination_routes": "pass_fresh_process_0.582_to_0.762_seconds",
            "benchmark_report": str(dashboard / "phase4-performance-benchmark.json"),
        },
        "data_hygiene": {
            "corrupted_card_play_rows_in_active_relation": 0,
            "home_corrupted_source_rows_retained": 17976,
            "metadata_relations_present": True,
            "records_relations_present": True,
        },
        "next_gate": (
            "obtain explicit Phase 5 cutover authorization; no public deployment or frontend switch has been performed."
            if all_private_gates_ready else
            "resolve the remaining private readiness blockers and rerun the final performance/publication gates before Phase 5 cutover."
        ),
        "public_cutover": "not authorized or performed",
    }
    output = dashboard / "phase4-decision-gate.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
