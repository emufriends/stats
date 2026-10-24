"""Verify non-route endpoints and ancillary artifacts for Increment 8.

The canonical route catalog is reconciled separately.  This gate deliberately
covers only contracts that would otherwise be easy to omit from a route count:
component-CI batches, Players graph histories, and Arena graph artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path
from typing import Any

from phase5_snapshot_builder import _component_descriptor, _component_key, _request


COMPONENT_CASES = (
    ("combinations", "card_card", "card-stats/combinations/card-card/default-mw.json"),
    ("combinations", "card_map", "card-stats/combinations/card-map/default-mw.json"),
    ("combinations", "card_round", "card-stats/combinations/card-round/default-mw.json"),
    ("combinations", "card_endgame", "card-stats/combinations/card-endgame/default-mw.json"),
    ("combinations", "card_action_card", "card-stats/combinations/card-action-card/default-mw.json"),
    ("mw_action_cards", "synergies", "card-stats/mw-action-cards/synergies/default-mw.json"),
)


def _post(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _close(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-10)
    except (TypeError, ValueError):
        return left == right


def _component_checks(
    url: str, snapshot_root: Path, generation: str, data_version: str, timeout: float,
) -> list[dict[str, Any]]:
    results = []
    for page, view, relative in COMPONENT_CASES:
        item: dict[str, Any] = {"id": f"component_batch/{page}/{view}"}
        try:
            snapshot = json.loads((snapshot_root / relative).read_text(encoding="utf-8"))
            row = next(value for value in snapshot.get("data", []) if isinstance(value, dict))
            descriptor = _component_descriptor(page, view, row)
            request = _request(page, view, 1, 100, 0)
            request.update(component_ci=True, component_ci_rows=[descriptor])
            response = _post(url, request, timeout)
            returned = response.get("data") or []
            assert response.get("status") == "ok"
            assert response.get("generation") == generation
            assert response.get("data_version") == data_version
            assert len(returned) == 1
            ci = returned[0]
            assert ci.get("row_key") == _component_key(page, view, row)
            assert ci.get("method") == "table_cluster_delta"
            assert int(ci.get("component_1_ci95_n") or 0) > 0
            assert int(ci.get("component_1_ci95_cluster_n") or 0) >= 2
            for index in (1, 2):
                expected = row.get(f"component_{index}_mean")
                if expected is not None:
                    assert _close(ci.get(f"component_{index}_mean"), expected)
                    assert int(ci.get(f"component_{index}_ci95_n") or 0) > 0
            item.update(
                status="pass",
                row_key=ci.get("row_key"),
                cache_status=response.get("cache_status"),
            )
        except Exception as exc:  # diagnostic boundary
            item.update(status="fail", error=type(exc).__name__, message=str(exc)[:400])
        results.append(item)
    return results


def _history_checks(
    url: str, generation: str, data_version: str, timeout: float,
) -> list[dict[str, Any]]:
    cases = (
        (
            "players_history/general",
            {
                "stats_page": "players", "players_view": "general",
                "players_history": True, "players_player": "trusting-seagull275",
                "players_history_metrics": ["turns", "reputation_actions"], "is_mw": 1,
            },
            {"turns", "reputation_actions"},
        ),
        (
            "players_history/comparison",
            {
                "stats_page": "players", "players_view": "comparison",
                "players_history": True,
                "players_players": ["trusting-seagull275", "portgard"],
                "players_history_metrics": ["score"], "is_mw": 1,
            },
            {"score"},
        ),
        (
            "players_history/elo_combined",
            {
                "stats_page": "players", "players_view": "general",
                "players_history": True, "players_player": "trusting-seagull275",
                "players_history_metrics": ["elo"], "is_mw": 0,
            },
            {"elo"},
        ),
    )
    results = []
    for name, request, expected_metrics in cases:
        item: dict[str, Any] = {"id": name}
        try:
            response = _post(url, request, timeout)
            assert response.get("status") == "ok"
            assert response.get("generation") == generation
            assert response.get("data_version") == data_version
            assert response.get("players_history") is True
            metrics = {entry.get("key") for entry in response.get("metrics") or []}
            assert expected_metrics <= metrics
            players = response.get("players") or []
            assert players
            for player in players:
                series = player.get("series")
                assert isinstance(series, dict) and series
                assert expected_metrics <= set(series)
                assert all(isinstance(series[key], list) and series[key] for key in expected_metrics)
            item.update(status="pass", players=len(players), metrics=sorted(metrics))
        except Exception as exc:  # diagnostic boundary
            item.update(status="fail", error=type(exc).__name__, message=str(exc)[:400])
        results.append(item)
    return results


def _arena_check(snapshot_root: Path, data_version: str) -> dict[str, Any]:
    item: dict[str, Any] = {"id": "arena_graph/artifact_bundle"}
    try:
        base = snapshot_root / "card-stats/players"
        latest = json.loads((base / "arena/latest.json").read_text(encoding="utf-8"))
        bundle = json.loads((base / "arena-top-100/all-seasons.json").read_text(encoding="utf-8"))
        manifest = json.loads((base / "arena/manifest.json").read_text(encoding="utf-8"))
        assert latest.get("data_version") == data_version
        assert bundle.get("data_version") == data_version
        assert manifest.get("data_version") == data_version
        latest_season = latest.get("latest_season")
        assert latest_season
        seasons = bundle.get("data") or bundle.get("rows") or {}
        assert isinstance(seasons, dict) and latest_season in seasons
        bucket = seasons[latest_season]
        rows = bucket.get("rows") or []
        series = bucket.get("series") or []
        assert rows and series
        assert any(entry.get("ratings") for entry in series)
        assert all(entry.get("player_id") is not None for entry in rows)
        item.update(
            status="pass", latest_season=latest_season,
            season_count=len(seasons), latest_rows=len(rows), latest_series=len(series),
        )
    except Exception as exc:  # diagnostic boundary
        item.update(status="fail", error=type(exc).__name__, message=str(exc)[:400])
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/ascri"))
    parser.add_argument("--url", default="http://127.0.0.1:8787/v1/query")
    parser.add_argument("--timeout", type=float, default=95.0)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--generation-id", help="Pin checks to the generation served by the supplied candidate URL")
    args = parser.parse_args()
    pointer = json.loads(
        (args.root / "phase3_private_serving/current.json").read_text(encoding="utf-8")
    )
    generation = args.generation_id or str(pointer["generation"])
    generation_manifest = json.loads(
        (args.root / "phase2_private_data/generations" / f"{generation}.manifest.json").read_text(encoding="utf-8")
    )
    data_version = str(generation_manifest["data_version"])
    snapshot_root = args.root / "phase2_private_data/snapshots" / generation
    checks = [
        *_component_checks(args.url, snapshot_root, generation, data_version, args.timeout),
        *_history_checks(args.url, generation, data_version, args.timeout),
        _arena_check(snapshot_root, data_version),
    ]
    failed = [item["id"] for item in checks if item.get("status") != "pass"]
    report = {
        "status": "pass" if not failed else "fail",
        "generation": generation,
        "data_version": data_version,
        "check_count": len(checks),
        "passed": len(checks) - len(failed),
        "failed": failed,
        "checks": checks,
    }
    encoded = json.dumps(report, indent=2, sort_keys=True)
    print(encoded)
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
