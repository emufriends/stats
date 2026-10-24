"""Validate one private DuckDB generation and its complete snapshot pack."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase5_snapshot_builder import expected_snapshot_object_keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("generation")
    parser.add_argument(
        "--candidate",
        action="store_true",
        help=(
            "validate an unactivated candidate pack without requiring the "
            "serving and snapshot pointers to reference it"
        ),
    )
    args = parser.parse_args()
    private = args.root / "phase2_private_data"
    snapshot_root = private / "snapshots" / args.generation
    manifest_path = snapshot_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_version = manifest["data_version"]
    entries = manifest["snapshots"]
    expected_keys = set(expected_snapshot_object_keys())
    actual_keys = {
        str(entry.get("object_key") or "")
        for entry in entries
        if isinstance(entry, dict)
    }
    missing_snapshot_keys = sorted(expected_keys - actual_keys)
    unexpected_snapshot_keys = sorted(actual_keys - expected_keys)
    missing = []
    mismatched = []
    statuses = set()
    for entry in entries:
        path = Path(entry["path"])
        if not path.is_file():
            missing.append(str(path))
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        statuses.add(payload.get("status"))
        if payload.get("data_version") != expected_version:
            mismatched.append(str(path))
    serving = json.loads((private.parent / "phase3_private_serving" / "current.json").read_text(encoding="utf-8"))
    snapshots = json.loads((private / "snapshots" / "current.json").read_text(encoding="utf-8"))
    result = {
        "generation": args.generation,
        "manifest_generation": manifest.get("generation"),
        "snapshot_count": len(entries),
        "expected_snapshot_count": manifest.get("snapshot_count"),
        "catalog_snapshot_count": len(expected_keys),
        "missing_snapshot_keys": missing_snapshot_keys,
        "unexpected_snapshot_keys": unexpected_snapshot_keys,
        "data_version": expected_version,
        "payload_statuses": sorted(statuses),
        "missing_files": missing,
        "mismatched_payloads": mismatched,
        "serving_generation": serving.get("generation"),
        "snapshot_generation": snapshots.get("generation"),
        "snapshot_data_version": snapshots.get("data_version"),
        "validation_mode": "candidate" if args.candidate else "active",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if (
        manifest.get("generation") != args.generation
        or len(entries) != len(expected_keys)
        or manifest.get("snapshot_count") != len(expected_keys)
        or missing_snapshot_keys
        or unexpected_snapshot_keys
        or missing
        or mismatched
        or statuses != {"ok"}
        or (
            not args.candidate
            and (
                serving.get("generation") != args.generation
                or snapshots.get("generation") != args.generation
                or snapshots.get("data_version") != expected_version
            )
        )
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
