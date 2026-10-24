"""Reuse same-data-version snapshots across a metadata-only generation repair."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_generation")
    parser.add_argument("target_generation")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/home/ascri/phase2_private_data/snapshots"),
    )
    args = parser.parse_args()
    source = args.root / args.source_generation
    target = args.root / args.target_generation
    if not source.is_dir():
        raise RuntimeError(f"source snapshot directory is missing: {source}")
    if target.exists():
        raise RuntimeError(f"target snapshot directory already exists: {target}")
    shutil.copytree(source, target)

    updated = 0
    for path in target.rglob("*.json"):
        if path.name == "manifest.json":
            path.unlink()
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "generation" in payload:
            payload["generation"] = args.target_generation
            path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        updated += 1
    print(json.dumps({
        "status": "ok",
        "source_generation": args.source_generation,
        "target_generation": args.target_generation,
        "snapshot_count": updated,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
