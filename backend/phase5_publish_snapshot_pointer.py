"""Atomically publish an already validated private snapshot-pack pointer."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from phase5_uncoordinated_guard import require_uncoordinated_ack


def main() -> int:
    require_uncoordinated_ack(Path(__file__).name)
    root = Path(sys.argv[1])
    generation = sys.argv[2]
    manifest = Path(sys.argv[3]) if len(sys.argv) > 3 else root / generation / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    versions = {item.get("data_version") for item in payload.get("snapshots", [])}
    if len(versions) != 1 or payload.get("data_version") not in versions:
        raise SystemExit("snapshot manifest has inconsistent data versions")
    pointer = root / "current.json"
    temporary = pointer.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({
        "status": "ok",
        "generation": generation,
        "data_version": payload["data_version"],
        "manifest": str(manifest),
        "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, pointer)
    print(json.dumps(json.loads(pointer.read_text(encoding="utf-8")), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
