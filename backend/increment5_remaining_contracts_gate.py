"""Focused gate for the Increment 5 non-card route restoration.

Without ``--database`` the gate validates catalogs and generated SQL.  With an
immutable DuckDB generation it additionally executes the Records and Arena
contracts, reporting their bounded-query latency without mutating that file.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from phase3_duckdb_service import _load_duckdb
from phase4_local_routes import (
    PROJECT_REWARDS,
    PREDICTOR_SPECIFIC_CONDITIONS,
    SPONSOR_APPEAL_VALUES,
    SPONSOR_CP_CARDS,
    _final_arena_sql,
    _final_records_sql,
    _next_home_sql,
    _next_predictor_sql,
    _scoring_buckets,
)


def run(database: Path | None = None) -> dict:
    checks = {
        "predictor_specific_rows": len(PREDICTOR_SPECIFIC_CONDITIONS),
        "project_reward_rows": len(PROJECT_REWARDS),
        "sponsor_cp_rows": len(SPONSOR_CP_CARDS),
        "sponsor_appeal_rows": len(SPONSOR_APPEAL_VALUES),
        "scoring_bucket_rows": {
            view: len(_scoring_buckets(view)[1])
            for view in ("final_score", "appeal", "conservation_points", "reputation")
        },
        "scoring_expanded_rows": {
            view: len(_scoring_buckets(view, True)[1])
            for view in ("final_score", "appeal", "conservation_points", "reputation")
        },
    }
    expected = {
        "predictor_specific_rows": 19, "project_reward_rows": 22,
        "sponsor_cp_rows": 31, "sponsor_appeal_rows": 9,
        "scoring_bucket_rows": {
            "final_score": 7, "appeal": 9, "conservation_points": 8,
            "reputation": 15,
        },
        "scoring_expanded_rows": {
            "final_score": 52, "appeal": 75, "conservation_points": 42,
            "reputation": 15,
        },
    }
    if checks != expected:
        raise RuntimeError(f"catalog contract mismatch: {checks}")
    predictor_sql, _ = _next_predictor_sql({"is_mw": 1}, "specific")
    home_sql, _ = _next_home_sql({})
    if "log_played_animals" not in predictor_sql or "is_corrupted_game" in home_sql:
        raise RuntimeError("generated SQL does not preserve Increment 5 populations")

    timings = {}
    if database is not None:
        duckdb = _load_duckdb()
        connection = duckdb.connect(str(database.resolve()), read_only=True)
        try:
            for view in ("fastest_games", "highest_scores", "biggest_turns", "most_icons"):
                sql, parameters = _final_records_sql({"is_mw": 1}, view)
                started = time.perf_counter()
                rows = connection.execute(sql, [*parameters, 5, 0]).fetchall()
                timings[f"records_{view}"] = {
                    "seconds": round(time.perf_counter() - started, 3),
                    "rows": len(rows),
                }
            season_row = connection.execute(
                "SELECT season FROM arena_seasons_metadata ORDER BY season DESC LIMIT 1"
            ).fetchone()
            if season_row:
                sql, parameters = _final_arena_sql({
                    "arena_season": season_row[0], "arena_series_player_ids": [],
                })
                started = time.perf_counter()
                rows = connection.execute(sql, parameters).fetchall()
                timings["arena"] = {
                    "seconds": round(time.perf_counter() - started, 3),
                    "rows": len(rows),
                }
        finally:
            connection.close()
    return {"status": "ok", "checks": checks, "execution": timings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.database), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
