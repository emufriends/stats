"""Validate a private Phase 5 snapshot pack before any publication step."""

from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: phase5_snapshot_validate.py MANIFEST")
    manifest_path = Path(sys.argv[1]).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("snapshots")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("manifest has no snapshots")
    artifacts = manifest.get("artifacts")
    required_keys = manifest.get("required_object_keys")
    if manifest.get("status") != "ok" or not isinstance(artifacts, list) or not artifacts:
        raise SystemExit("manifest has no authoritative artifact inventory")
    if not isinstance(required_keys, list) or len(required_keys) != len(set(required_keys)):
        raise SystemExit("manifest required_object_keys is missing or contains duplicates")
    manifest_version = manifest.get("data_version")
    versions = set()
    missing: list[str] = []
    invalid: list[str] = []
    for entry in entries:
        path = Path(entry["path"])
        if not path.exists():
            missing.append(str(path))
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            invalid.append(f"{path}: {exc}")
            continue
        version = payload.get("data_version")
        versions.add(version)
        if version != manifest_version or version != entry.get("data_version"):
            invalid.append(f"{path}: data_version={version!r}")
        rows = payload.get("rows", payload.get("data"))
        if isinstance(rows, dict) and "arena" in str(path):
            bucket_rows = [
                bucket.get("rows")
                for bucket in rows.values()
                if isinstance(bucket, dict)
            ]
            if any(not isinstance(bucket, list) for bucket in bucket_rows):
                invalid.append(f"{path}: an Arena bucket has no rows list")
            rows = [row for bucket in bucket_rows for row in bucket]
        elif path.name == "manifest.json":
            rows = payload.get("seasons", [])
        if not isinstance(rows, list):
            invalid.append(f"{path}: data/rows is not a list")
        declared_count = payload.get("row_count")
        if declared_count is not None and int(declared_count) != len(rows or []):
            invalid.append(f"{path}: row_count does not match data")
    artifact_keys = []
    for artifact in artifacts:
        key = artifact.get("object_key")
        path = Path(str(artifact.get("path") or ""))
        if not isinstance(key, str) or not key or key.startswith("/") or ".." in Path(key).parts:
            invalid.append(f"invalid artifact object key: {key!r}")
            continue
        artifact_keys.append(key)
        if not path.is_file():
            missing.append(str(path))
            continue
        if path.stat().st_size != artifact.get("bytes"):
            invalid.append(f"{path}: byte count does not match manifest")
        if _sha256(path) != artifact.get("sha256"):
            invalid.append(f"{path}: SHA-256 does not match manifest")
    if sorted(artifact_keys) != sorted(required_keys):
        invalid.append("artifact inventory does not match required_object_keys")
    pack_entries = [item for item in artifacts if item.get("kind") == "default_pack"]
    if len(pack_entries) != 1:
        invalid.append("artifact inventory must contain exactly one default pack")
    else:
        try:
            pack = json.loads(Path(pack_entries[0]["path"]).read_text(encoding="utf-8"))
            pack_keys = set((pack.get("snapshots") or {}).keys())
            expected_pack_keys = {
                item["object_key"] for item in entries if item.get("pack_member") is True
            }
            if pack.get("data_version") != manifest_version:
                invalid.append("default pack has the wrong data version")
            if pack.get("release_version") != manifest.get("release_version"):
                invalid.append("default pack has the wrong release version")
            if pack_keys != expected_pack_keys:
                invalid.append("default pack membership is not authoritative")
        except (OSError, ValueError, TypeError) as exc:
            invalid.append(f"default pack cannot be read: {exc}")
    result = {
        "manifest": str(manifest_path),
        "snapshot_count": len(entries),
        "manifest_data_version": manifest_version,
        "payload_data_versions": sorted(versions, key=str),
        "missing_count": len(missing),
        "invalid_count": len(invalid),
        "artifact_count": len(artifacts),
        "release_version": manifest.get("release_version"),
        "status": "ok" if not missing and not invalid and len(versions) == 1 else "failed",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if missing:
        print("Missing files:", *missing, sep="\n- ")
    if invalid:
        print("Invalid files:", *invalid, sep="\n- ")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
