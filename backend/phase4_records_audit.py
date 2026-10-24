"""Read-only smoke test for the private Records moving-source routes."""

from __future__ import annotations

import json
from pathlib import Path

from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3RequestAdapter,
    Phase3ResponseCache,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    manager = GenerationManager(root / "phase2_private_data" / "generations",
                                root / "phase3_private_serving" / "current.json")
    adapter = Phase3RequestAdapter(DuckDBServingStore(manager), Phase3ResponseCache(max_items=32))
    routes = ("elo_leaderboard", "fastest_games", "highest_scores", "biggest_turns", "most_icons")
    report = {"generation": manager.current().generation_id, "routes": {}}
    for view in routes:
        request = {"stats_page": "records", "records_view": view, "limit": 100, "offset": 0}
        response = adapter.execute(request)
        rows = response["data"]
        report["routes"][view] = {
            "row_count": response["row_count"],
            "sample": rows[:2],
            "placeholder": any(row.get("player") is None for row in rows),
        }
    filtered = adapter.execute({
        "stats_page": "records", "records_view": "fastest_games", "records_player": "wuxuanwuyan",
        "limit": 100, "offset": 0,
    })
    report["player_filter"] = {
        "row_count": filtered["row_count"],
        "players": sorted({row.get("player") for row in filtered["data"]}),
    }
    report["status"] = "pass" if all(
        not item["placeholder"] for item in report["routes"].values()
    ) and report["player_filter"]["players"] in (["wuxuanwuyan"], []) else "fail"
    output = root.parent / "ark-nova-stats-dashboard" / "analysis" / "phase4-records-audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
