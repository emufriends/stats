"""Perform the exact rollback paired with one published DuckDB release."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _utc_now
from phase5_publish_release import _gcloud, _uri, _restore_aliases
from phase5_process_lock import exclusive


def rollback(root: Path, generation: str, *, bucket: str) -> dict:
    with exclusive(root / 'phase2_private_data/publication.lock'):
        return _rollback_locked(root, generation, bucket=bucket)


def _rollback_locked(root: Path, generation: str, *, bucket: str) -> dict:
    private = root / "phase2_private_data"
    manager = GenerationManager(
        private / "generations", root / "phase3_private_serving" / "current.json"
    )
    current = manager.current()
    if current is None or current.generation_id != generation:
        raise RuntimeError("rollback target is not the active generation")
    release = dict(current.manifest.get("release") or {})
    descriptor = dict(release.get("rollback") or {})
    if descriptor.get("schema_version") not in {1, 2}:
        raise RuntimeError("published generation has no exact rollback descriptor")
    previous = str(descriptor.get("previous_generation") or "")
    manager.inspect(previous)
    backups = dict(descriptor.get("backups") or {})
    keys = list(descriptor.get("published_object_keys") or [])
    if set(keys) != set(backups):
        raise RuntimeError("rollback descriptor object inventory is incomplete")
    previous_deployment = descriptor.get('previous_deployment_version')
    if descriptor.get('schema_version') == 2 and not previous_deployment:
        raise RuntimeError('paired rollback descriptor has no previous code version')
    if previous_deployment:
        from phase5_install_deployment import verify_installed
        verify_installed(root, str(previous_deployment))

    if (private / 'publication-transaction.json').exists():
        raise RuntimeError('recover the interrupted publication before rollback')
    if previous_deployment:
        from phase5_coordinated_publication import stop_services
        stop_services()
    # Restore public aliases first. The default pack and status are part of
    # the same inventory and therefore return to the exact prior release.
    if descriptor.get('object_guards') is not None:
        _restore_aliases(bucket, backups, keys, descriptor['object_guards'], descriptor.get('transaction_id'))
    else:
        # Compatibility with exact rollback descriptors from older releases.
        for key in reversed(keys):
            destination = _uri(bucket, key)
            backup = backups[key]
            if backup:
                result = _gcloud("storage", "cp", "--quiet", backup, destination, check=False)
            else:
                result = _gcloud("storage", "rm", "--quiet", destination, check=False)
            if result.returncode:
                raise RuntimeError(f"failed to restore rollback object: {key}")
    manager.activate(previous)
    pointer = private / "snapshots" / "current.json"
    encoded = descriptor.get("previous_snapshot_pointer")
    if encoded is None:
        pointer.unlink(missing_ok=True)
    else:
        temporary = pointer.with_suffix(".rollback.tmp")
        temporary.write_bytes(base64.b64decode(encoded))
        os.replace(temporary, pointer)
    payload = dict(current.manifest)
    payload["release"] = {
        **release,
        "status": "rolled_back",
        "rolled_back_at": _utc_now(),
        "rolled_back_to": previous,
    }
    temporary = current.manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, current.manifest_path)
    if previous_deployment:
        from phase5_coordinated_publication import restore_deployment
        restore_deployment(root, str(previous_deployment))
    return {"status": "ok", "generation": generation, "restored_generation": previous}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--bucket", default="ark-nova-stats-dashboard-cache")
    args = parser.parse_args()
    print(json.dumps(rollback(args.root.resolve(), args.generation, bucket=args.bucket), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
