"""Measure Card + Card directly on the private DuckDB service."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from phase3_duckdb_service import DuckDBServingStore, GenerationManager, Phase3RequestAdapter


def main(root: str) -> int:
    root_path = Path(root)
    manager = GenerationManager(
        root_path / "phase2_private_data" / "generations",
        root_path / "phase3_private_serving" / "current.json",
    )
    adapter = Phase3RequestAdapter(DuckDBServingStore(manager))
    results = []
    for offset in (0, 2, 4):
        started = time.perf_counter()
        payload = adapter.execute({
            "stats_page": "combinations",
            "combinations_view": "card_card",
            "limit": 2,
            "offset": offset,
            "combination_min_plays": 1000,
            "is_mw": 1,
        })
        results.append({
            "offset": offset,
            "seconds": round(time.perf_counter() - started, 4),
            "rows": payload.get("row_count"),
            "cache_status": payload.get("cache_status"),
            "generation": payload.get("generation"),
        })
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
