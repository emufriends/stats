"""Strict route-contract gate for a complete dashboard default pack.

Pass ``--pack`` with the candidate pack used for release validation. A stale
workstation copy is never used implicitly: release evidence must identify the
candidate or published pack being checked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from phase3_duckdb_service import Phase3RequestAdapter
from phase4_local_scope import scope_predicates


ROOT = Path(__file__).resolve().parent
EXCLUDED_CARDS = {
    "Africa", "Americas", "Asia", "Australia", "Birds", "Europe",
    "Habitat Diversity", "Herbivores", "Predators", "Primates", "Reptiles",
    "Sea Animals", "Species Diversity",
}


def _snapshot(pack: dict[str, Any], path: str) -> dict[str, Any]:
    return pack["snapshots"][path]


def _check_request_contract() -> None:
    request = {
        "stats_page": "cards", "is_mw": 1, "rounds": [1], "arena_only": True,
        "maps": ["Map 1a: Observation Tower"], "starting_positions": ["First player"],
    }
    normalized = Phase3RequestAdapter.normalize_request(request)
    assert normalized.get("rounds") == ["1"], "rounds was silently discarded"
    assert normalized.get("arena_only") is True, "arena_only was silently discarded"


def _check_player_routing() -> None:
    page, view = Phase3RequestAdapter._route({
        "stats_page": "players", "players_view": "general", "players_player": "portgard",
        "players_history": False,
    })
    assert (page, view) == ("players", "general"), f"selected General player was routed to {view}"


def _check_opponent_elo_contract() -> None:
    sql, _ = scope_predicates({
        "is_mw": 1, "maps": [], "player_elo_min": 0, "player_elo_max": None,
        "opponent_elo_min": 0, "opponent_elo_max": None, "date_from": None,
        "date_to": None, "starting_positions": [], "completed_only": None,
        "arena_seasons": [], "tournament_only": False,
    })
    assert "opponent_pre_match_elo" in sql, "scope still filters on legacy raw opponent_elo"


def _check_cards(pack: dict[str, Any]) -> None:
    rows = _snapshot(pack, "card-stats/default-mw.json")["data"]
    names = {row.get("card_name") for row in rows}
    assert len(rows) == 267, f"Cards catalog has {len(rows)} rows rather than 267"
    assert not names.intersection(EXCLUDED_CARDS), f"excluded cards present: {sorted(names.intersection(EXCLUDED_CARDS))}"


def _check_opening_hand(pack: dict[str, Any]) -> None:
    rows = _snapshot(pack, "card-stats/opening-hand/default-mw.json")["data"]
    invalid = [row.get("card_name") for row in rows if float(row.get("playrate_pct") or 0) > 100]
    assert not invalid, f"opening keep/play rate exceeds 100% for {invalid[:5]}"


def _check_players_catalog(pack: dict[str, Any]) -> None:
    rows = _snapshot(pack, "card-stats/players/general/default-mw.json")["data"]
    metrics = [row.get("metric") for row in rows]
    assert metrics and metrics[0] == "Turns", f"first Players metric is {metrics[0] if metrics else None!r}"
    assert "Games" not in metrics and "Rounds" not in metrics, "Maps-only metrics leaked into Players"


def _check_card_card_dataset(pack: dict[str, Any]) -> None:
    mw = _snapshot(pack, "card-stats/combinations/card-card/default-mw.json")["data"]
    base = _snapshot(pack, "card-stats/combinations/card-card/default-base.json")["data"]
    assert mw != base, "MW and Base Card + Card payloads are exactly identical"


def _check_mw_catalog(pack: dict[str, Any]) -> None:
    rows = _snapshot(pack, "card-stats/mw-action-cards/general/default-mw.json")["data"]
    assert len(rows) == 20, f"MW General has {len(rows)} rows rather than the 20 special cards"


def _check_hexes_snapshot(pack: dict[str, Any]) -> None:
    rows = _snapshot(pack, "card-stats/build/hexes/delta/default-mw.json")["data"]
    assert len(rows) == 6, f"Hexes snapshot has {len(rows)} rows"
    assert all("bucket_key" in row for row in rows), "Hexes snapshot contains a different view schema"


def _check_starting_position_catalog(pack: dict[str, Any]) -> None:
    rows = _snapshot(pack, "card-stats/actions/starting_position/delta/default-mw.json")["data"]
    assert len(rows) == 9, f"Starting Position has {len(rows)} rows rather than 9"


def _check_project_rewards_catalog(pack: dict[str, Any]) -> None:
    rows = _snapshot(pack, "card-stats/conservation/project-rewards/default-mw.json")["data"]
    assert len(rows) == 22, f"Project Rewards has {len(rows)} rows rather than 22 named rewards"


def run(pack_path: Path) -> dict[str, Any]:
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    checks: list[tuple[str, Callable[[], None]]] = [
        ("request_contract", _check_request_contract),
        ("player_routing", _check_player_routing),
        ("opponent_elo_contract", _check_opponent_elo_contract),
        ("cards_catalog", lambda: _check_cards(pack)),
        ("opening_hand_population", lambda: _check_opening_hand(pack)),
        ("players_catalog", lambda: _check_players_catalog(pack)),
        ("card_card_dataset_scope", lambda: _check_card_card_dataset(pack)),
        ("mw_action_card_catalog", lambda: _check_mw_catalog(pack)),
        ("build_hexes_snapshot", lambda: _check_hexes_snapshot(pack)),
        ("actions_starting_position_catalog", lambda: _check_starting_position_catalog(pack)),
        ("conservation_project_rewards_catalog", lambda: _check_project_rewards_catalog(pack)),
    ]
    results = []
    for name, check in checks:
        try:
            check()
        except Exception as exc:  # the report is the gate output
            results.append({"check": name, "status": "fail", "message": str(exc)})
        else:
            results.append({"check": name, "status": "pass"})
    failed = sum(result["status"] == "fail" for result in results)
    return {"status": "fail" if failed else "ok", "failed": failed, "total": len(results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run(args.pack)
    encoded = json.dumps(report, indent=2, sort_keys=True)
    print(encoded)
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
