"""Check Arena bundle alignment between season metadata, rows, and histories."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    seasons = payload.get("seasons") or []
    data = payload.get("data") or {}
    errors: list[str] = []
    for item in seasons:
        season = item.get("season")
        bucket = data.get(season)
        if not isinstance(bucket, dict):
            errors.append(f"missing data bucket: {season}")
            continue
        rows = bucket.get("rows") or []
        series = bucket.get("series") or []
        if len(rows) != len(series):
            errors.append(f"{season}: rows={len(rows)} series={len(series)}")
        if bucket.get("effective_end_utc") is None:
            errors.append(f"{season}: missing effective_end_utc")
        for row, item_series in zip(rows, series):
            if row.get("player_id") != item_series.get("player_id"):
                errors.append(f"{season}: player ID mismatch")
                break
    result = {
        "status": "ok" if not errors and len(seasons) == len(data) else "failed",
        "season_count": len(seasons),
        "data_bucket_count": len(data),
        "row_count": sum(len((bucket or {}).get("rows") or []) for bucket in data.values()),
        "latest_season": payload.get("latest_season"),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
