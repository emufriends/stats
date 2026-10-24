"""Benchmark the compact Phase 4 combination projections in a fresh process.

This is a private, read-only diagnostic.  Each route gets a fresh DuckDB
connection so a failed or memory-heavy plan cannot contaminate the next run.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb
from phase4_local_routes import _remaining_route_sql


ROOT = Path(__file__).resolve().parent
GENERATION_DIR = ROOT / "phase2_private_data" / "generations"
POINTER = ROOT / "phase3_private_serving" / "current.json"


def run() -> int:
    manager = GenerationManager(GENERATION_DIR, POINTER)
    generation = manager.current()
    duckdb = _load_duckdb()
    request_base = {
        "is_mw": 1,
        "completed_only": True,
        "starting_positions": ["First player", "Second player"],
        "limit": 25,
        "offset": 0,
    }
    for route, view in (
        ("combinations/card_endgame", "card_endgame"),
        ("combinations/card_action_card", "card_action_card"),
    ):
        connection = duckdb.connect(str(generation.database_path), read_only=True)
        try:
            request = dict(request_base, remaining_view=view, combinations_view=view)
            sql, parameters = _remaining_route_sql(request)
            started = time.perf_counter()
            rows = connection.execute(sql, parameters + [25, 0]).fetchall()
            print(json.dumps({
                "route": route,
                "generation": generation.generation_id,
                "data_version": generation.data_version,
                "scope": "default_mw_completed",
                "seconds": round(time.perf_counter() - started, 3),
                "rows": len(rows),
            }))
        finally:
            connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
