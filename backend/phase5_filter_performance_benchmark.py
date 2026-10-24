"""Benchmark and reconcile the optimized Cards and Players generation."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3RequestAdapter,
    Phase3ResponseCache,
)


STANDARD_MAPS = [
    "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a",
    "9", "10", "11", "12", "13", "14", "T1",
]


def equivalent(left: Any, right: Any, path: str = "root") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        ignored = {"generation", "source", "cache_status"}
        keys = (set(left) | set(right)) - ignored
        errors = []
        for key in sorted(keys):
            if key not in left or key not in right:
                errors.append(f"{path}.{key}: missing")
            else:
                errors.extend(equivalent(left[key], right[key], f"{path}.{key}"))
        return errors
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [f"{path}: length {len(left)} != {len(right)}"]
        errors = []
        for index, (a, b) in enumerate(zip(left, right)):
            identity = None
            if isinstance(a, dict) and isinstance(b, dict):
                for key in ("card_name", "metric", "player"):
                    if a.get(key) == b.get(key) and a.get(key) is not None:
                        identity = f"{key}={a[key]!r}"
                        break
            item_path = f"{path}[{index}{', ' + identity if identity else ''}]"
            errors.extend(equivalent(a, b, item_path))
        return errors
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-10):
            return []
        # These two public fields are rounded render values. Parallel floating
        # aggregation can land on opposite sides of an exact half-thousandth;
        # the unrounded CI mean/count/moments below remain strict parity gates.
        if path.endswith((".delta_played", ".delta_in_hand")) and math.isclose(
            float(left), float(right), rel_tol=0.0, abs_tol=0.0010000001
        ):
            return []
    return [] if left == right else [f"{path}: {left!r} != {right!r}"]


def run(adapter: Phase3RequestAdapter, request: dict[str, Any]) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = adapter.execute(request)
    return response, time.perf_counter() - started


def adapter(manager: GenerationManager, generation: str) -> Phase3RequestAdapter:
    store = DuckDBServingStore(manager, generation_id=generation)
    return Phase3RequestAdapter(
        store, response_cache=Phase3ResponseCache(max_items=8),
        allow_default_snapshots=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/ascri"))
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--common-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    manager = GenerationManager(
        root / "phase2_private_data" / "generations",
        root / "phase3_private_serving" / "current.json",
    )
    cards_common = {
             "stats_page": "cards", "is_mw": 1,
            "maps": STANDARD_MAPS, "date_from": "2025-01-01",
             "starting_positions": ["First player", "Second player"],
             "limit": 100000,
    }
    requests = {
        "cards_symmetric": {
            **cards_common, "player_elo_min": 701, "opponent_elo_min": 701,
        },
        "cards_asymmetric": {
            **cards_common, "player_elo_min": 700, "opponent_elo_min": 300,
        },
        "cards_round_1": {
            **cards_common, "player_elo_min": 300, "opponent_elo_min": 300,
            "rounds": ["1"],
        },
        "cards_second_player": {
            **cards_common, "player_elo_min": 500, "opponent_elo_min": 500,
            "starting_positions": ["Second player"],
        },
        "cards_base_subset": {
            **cards_common, "is_mw": 0, "maps": ["1a", "2a", "9"],
            "player_elo_min": 400, "opponent_elo_min": 400,
            "completed_only": True,
        },
        "players": {
            "stats_page": "players", "players_view": "general", "is_mw": 1,
            "maps": STANDARD_MAPS, "player_elo_min": 0,
            "opponent_elo_min": 0, "players_player": "trusting-seagull275",
            "starting_positions": ["First player", "Second player"],
            "limit": 100000,
        },
    }
    if args.common_only:
        requests = {
            key: value for key, value in requests.items()
            if key in {"cards_symmetric", "players"}
        }
    report = {}
    for name, request in requests.items():
        baseline, baseline_seconds = run(adapter(manager, args.parent), request)
        candidate_adapter = adapter(manager, args.candidate)
        candidate, candidate_seconds = run(candidate_adapter, request)
        repeat, repeat_seconds = run(candidate_adapter, request)
        errors = equivalent(baseline, candidate)
        report[name] = {
            "baseline_seconds": round(baseline_seconds, 3),
            "candidate_seconds": round(candidate_seconds, 3),
            "candidate_repeat_seconds": round(repeat_seconds, 3),
            "row_count": candidate.get("row_count"),
            "parity": not errors,
            "parity_errors": errors[:20],
            "candidate_repeat_cache": repeat.get("cache_status"),
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(item["parity"] for item in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
