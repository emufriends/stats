"""Bounded private DuckDB benchmarks for the remaining Phase 4 routes.

This is intentionally a local diagnostic.  It never calls BigQuery, changes
the active generation, or writes benchmark output unless the caller redirects
stdout.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb
from phase4_local_routes import _remaining_route_sql, _simple_metric_sql


def _active():
    root = Path(__file__).resolve().parent
    manager = GenerationManager(
        root / "phase2_private_data" / "generations",
        root / "phase3_private_serving" / "current.json",
    )
    generation = manager.current()
    duckdb = _load_duckdb()
    return generation, duckdb.connect(str(generation.database_path), read_only=True)


def _scope() -> dict:
    return {
        "is_mw": 1,
        "limit": 25,
        "offset": 0,
        "date_from": "2026-09-01",
        "date_to": "2026-09-17",
        "starting_positions": ["First player"],
        "completed_only": True,
        "maps": ["Map 1a: Observation Tower"],
        "combination_min_plays": 1,
    }


def run() -> int:
    generation, connection = _active()
    try:
        catalog = connection.execute(
            "SELECT table_name FROM duckdb_tables() ORDER BY table_name"
        ).fetchall()
        counts = connection.execute(
            "SELECT COUNT(*) FROM card_play_narrow"
            " UNION ALL SELECT COUNT(*) FROM source_full_sample"
            " UNION ALL SELECT COUNT(*) FROM source_logs"
        ).fetchall()
        print(json.dumps({
            "generation": generation.generation_id,
            "data_version": generation.data_version,
            "relations": catalog,
            "counts": {
                "card_play_narrow": counts[0][0],
                "source_full_sample": counts[1][0],
                "source_logs": counts[2][0],
            },
        }, default=str))

        cases = [
            ("build/hexes", {"stats_page": "build", "simple_view": "build_hexes"}, True),
            ("combinations/card_endgame", {"stats_page": "combinations", "remaining_view": "card_endgame", "combinations_view": "card_endgame"}, False),
            ("combinations/card_action_card", {"stats_page": "combinations", "remaining_view": "card_action_card", "combinations_view": "card_action_card"}, False),
        ]
        for route, request, simple in cases:
            full_request = dict(_scope(), **request)
            sql, parameters = (
                _simple_metric_sql(full_request)
                if simple else _remaining_route_sql(full_request)
            )
            started = time.perf_counter()
            rows = connection.execute(sql, parameters + [25, 0]).fetchall()
            print(json.dumps({
                "route": route,
                "scope": "restrictive",
                "seconds": round(time.perf_counter() - started, 3),
                "rows": len(rows),
            }))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
