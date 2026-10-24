"""Repair the latest Arena alias after an all-season bundle build."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["row_count"] = sum(
        len(bucket.get("rows") or [])
        for bucket in (payload.get("data") or {}).values()
        if isinstance(bucket, dict)
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
