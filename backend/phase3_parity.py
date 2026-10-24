"""Reconcile the representative Phase 3 DuckDB routes with local snapshots.

This is deliberately local and read-only. It never queries BigQuery and never
publishes a snapshot. The full route-by-route migration remains Phase 4.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3RequestAdapter,
    Phase3ResponseCache,
)


POINT_TOLERANCE = 0.000500001


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("data"), list):
        raise ValueError(f"snapshot has no data array: {path}")
    return value


def _index(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    result: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in fields)
        if key in result:
            raise ValueError(f"duplicate parity key: {key}")
        result[key] = row
    return result


def _compare_rows(
    actual_rows: list[Mapping[str, Any]],
    expected_rows: list[Mapping[str, Any]],
    key_fields: tuple[str, ...],
    integer_fields: tuple[str, ...],
    point_fields: tuple[str, ...],
    max_examples: int = 20,
) -> dict[str, Any]:
    actual = _index(actual_rows, key_fields)
    expected = _index(expected_rows, key_fields)
    missing = sorted(expected.keys() - actual.keys())
    unexpected = sorted(actual.keys() - expected.keys())
    field_mismatches: list[dict[str, Any]] = []
    mismatch_count = 0
    for key in sorted(actual.keys() & expected.keys()):
        for field in integer_fields:
            if actual[key].get(field) != expected[key].get(field):
                mismatch_count += 1
                if len(field_mismatches) < max_examples:
                    field_mismatches.append({
                        "key": key,
                        "field": field,
                        "actual": actual[key].get(field),
                        "expected": expected[key].get(field),
                    })
        for field in point_fields:
            left = actual[key].get(field)
            right = expected[key].get(field)
            equal = left is None and right is None
            if left is not None and right is not None:
                equal = abs(float(left) - float(right)) <= POINT_TOLERANCE
            if not equal:
                mismatch_count += 1
                if len(field_mismatches) < max_examples:
                    field_mismatches.append({
                        "key": key,
                        "field": field,
                        "actual": left,
                        "expected": right,
                    })
    passed = not missing and not unexpected and mismatch_count == 0
    return {
        "status": "pass" if passed else "fail",
        "actual_rows": len(actual),
        "expected_rows": len(expected),
        "missing_key_count": len(missing),
        "unexpected_key_count": len(unexpected),
        "field_mismatch_count": mismatch_count,
        "missing_key_examples": missing[:max_examples],
        "unexpected_key_examples": unexpected[:max_examples],
        "field_mismatch_examples": field_mismatches,
    }


def run_parity(
    manager: GenerationManager,
    cards_snapshot_path: Path,
    card_card_snapshot_path: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    adapter = Phase3RequestAdapter(
        DuckDBServingStore(manager),
        response_cache=Phase3ResponseCache(max_items=8),
    )
    cards_snapshot = _load(cards_snapshot_path)
    card_card_snapshot = _load(card_card_snapshot_path)
    cards = adapter.execute({"stats_page": "cards", "limit": 1000})
    card_card = adapter.execute({
        "stats_page": "combinations",
        "combinations_view": "card_card",
        "combination_min_plays": 1000,
        "limit": 1000,
    })

    versions = {
        "active": cards.get("data_version"),
        "cards_snapshot": cards_snapshot.get("data_version"),
        "card_card_snapshot": card_card_snapshot.get("data_version"),
    }
    version_match = len({str(value) for value in versions.values()}) == 1
    cards_result = _compare_rows(
        cards["data"],
        cards_snapshot["data"],
        ("card_name", "card_type"),
        ("n_played",),
        ("delta_played",),
    )

    # Phase 3 intentionally caps a private API response at 1,000 rows. Compare
    # that deterministic leading slice; full payload publication belongs to the
    # producer and the route-by-route Phase 4 migration.
    pair_expected_index = _index(
        card_card_snapshot["data"],
        ("card_1", "type_1", "card_2", "type_2"),
    )
    expected_pair_slice = [
        pair_expected_index[(row["card_1"], row["type_1"], row["card_2"], row["type_2"])]
        for row in card_card["data"]
        if (row["card_1"], row["type_1"], row["card_2"], row["type_2"]) in pair_expected_index
    ]
    card_card_result = _compare_rows(
        card_card["data"],
        expected_pair_slice,
        ("card_1", "type_1", "card_2", "type_2"),
        ("n_played",),
        ("delta_1", "delta_2", "delta_combined", "delta_actual", "interaction"),
    )
    card_card_result["scope"] = "deterministic_first_1000_api_rows"
    card_card_result["reference_total_rows"] = len(card_card_snapshot["data"])

    passed = (
        version_match
        and cards_result["status"] == "pass"
        and card_card_result["status"] == "pass"
        and len(card_card["data"]) == min(1000, len(card_card_snapshot["data"]))
    )
    return {
        "status": "pass" if passed else "fail",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "versions": versions,
        "data_version_match": version_match,
        "cards": cards_result,
        "card_card": card_card_result,
        "notes": [
            "This check reads the active private DuckDB generation and local same-generation snapshots only.",
            "It does not query BigQuery or modify public serving.",
            "Standalone EV intervals remain supported; additive Synergy intervals are intentionally absent.",
        ],
    }


def main() -> int:
    root = Path(__file__).resolve().parent
    dashboard = root.parent / "ark-nova-stats-dashboard"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations-dir", type=Path, default=root / "phase2_private_data" / "generations")
    parser.add_argument("--pointer", type=Path, default=root / "phase3_private_serving" / "current.json")
    parser.add_argument("--cards-snapshot", type=Path, default=dashboard / "analysis" / "phase2-local-cards-snapshot.json")
    parser.add_argument("--card-card-snapshot", type=Path, default=dashboard / "analysis" / "phase2-local-card-card-snapshot.json")
    parser.add_argument("--output", type=Path, default=dashboard / "analysis" / "phase3-parity-report.json")
    args = parser.parse_args()
    report = run_parity(
        GenerationManager(args.generations_dir, pointer_path=args.pointer),
        args.cards_snapshot,
        args.card_card_snapshot,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
