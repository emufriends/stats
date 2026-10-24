"""Publish one validated DuckDB release with compensating rollback.

The candidate database and every artifact are validated before this command is
called. Immutable generation-prefixed copies are uploaded first. Stable public
aliases and the local serving pointer then advance as one guarded transaction;
if any stable upload fails, the prior objects and local pointers are restored.
The default pack is deliberately the final public object written.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from phase5_process_lock import acquire as acquire_process_lock, exclusive
from pathlib import Path
from typing import Any

from phase3_duckdb_service import (
    GenerationManager,
    _utc_now,
    warm_interactive_generation,
)
import phase5_storage_io as storage_io
from phase5_refresh_metrics import RefreshTimings


JOURNAL_NAME = "publication-transaction.json"


def _write_journal(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        # Persist the rename as well as the record before any remote mutation.
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _acquire_publication_lock(path: Path, stale_after_seconds: int = 4 * 60 * 60) -> int:
    # Retain the argument for older callers; age never overrides kernel ownership.
    try:
        return acquire_process_lock(path)
    except OSError as error:
        raise RuntimeError('another release publication is already running') from error


def recover_interrupted(root: Path, *, bucket: str) -> dict[str, Any]:
    """Compensate a publication process that was killed after activation."""
    with exclusive(root / 'phase2_private_data/publication.lock'):
        return _recover_interrupted_locked(root, bucket=bucket)


def _recover_interrupted_locked(root: Path, *, bucket: str) -> dict[str, Any]:
    journal_path = root / "phase2_private_data" / JOURNAL_NAME
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "clean"}
    manager = GenerationManager(
        root / "phase2_private_data" / "generations",
        root / "phase3_private_serving" / "current.json",
    )
    previous = str(journal.get("previous_generation") or "")
    current = manager.current()
    if current is None or current.generation_id not in {previous, journal.get("generation")}:
        raise RuntimeError("publication recovery no longer owns the serving generation")
    if previous and (journal.get("activated") or current.generation_id == journal.get("generation")):
        manager.activate(previous)
        pointer = root / "phase2_private_data" / "snapshots" / "current.json"
        encoded = journal.get("previous_snapshot_pointer")
        if encoded is None:
            pointer.unlink(missing_ok=True)
        else:
            temporary = pointer.with_suffix(".recovery.tmp")
            temporary.write_bytes(base64.b64decode(encoded))
            os.replace(temporary, pointer)
    _restore_aliases(bucket, dict(journal.get("backups") or {}), list(journal.get("changed") or []),
                     journal.get('object_guards'), journal.get('transaction_id'))
    journal_path.unlink(missing_ok=True)
    return {"status": "recovered", "generation": journal.get("generation")}


def _restore_aliases(bucket: str, backups: dict, keys: list[str], guards=None, owner=None) -> None:
    """Retain the recovery journal if any inverse upload fails."""
    for key in reversed(keys):
        destination = _uri(bucket, key)
        backup = backups.get(key)
        try:
            options = {}
            if guards is not None:
                current = storage_io.object_state(destination)
                original = guards[key]
                unchanged = current['generation'] == original['generation']
                restored = (current.get('crc32c') and current.get('crc32c') == original.get('crc32c')
                            and current.get('owner') == original.get('owner')
                            and current.get('headers') == original.get('headers'))
                if unchanged or restored:
                    continue
                if not owner or current.get('owner') != owner:
                    raise RuntimeError('destination belongs to another publication')
                options['expected_generation'] = current['generation']
            if backup:
                storage_io.copy_object(backup, destination, **options)
            else:
                storage_io.delete_object(destination, **options)
        except Exception as error:
            raise RuntimeError(f"failed to restore publication object: {key}") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True, capture_output=True, timeout=600)


def _gcloud(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["gcloud", *args], check=check)


def _uri(bucket: str, key: str) -> str:
    return f"gs://{bucket}/{key.lstrip('/')}"


def _remote_exists(uri: str) -> bool:
    return storage_io.exists(uri)


def _content_type(artifact: dict[str, Any]) -> str:
    if artifact.get("kind") == "home_bootstrap":
        return "application/javascript"
    return "application/json"


def _upload(path: Path, uri: str, artifact: dict[str, Any], *, immutable: bool = False,
            expected_generation=None, owner=None) -> None:
    cache_control = (
        "public,max-age=31536000,immutable"
        if immutable else "public,max-age=300,must-revalidate"
    )
    storage_io.upload(path, uri, content_type=_content_type(artifact),
                      cache_control=cache_control, immutable=immutable,
                      expected_generation=expected_generation, owner=owner)


def _upload_pack(path: Path, uri: str, **options) -> None:
    storage_io.upload(path, uri, content_type='application/json',
                      cache_control='no-cache,max-age=0,must-revalidate', **options)


def _upload_status(payload: dict[str, Any], uri: str, **options) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, separators=(",", ":"))
        path = Path(handle.name)
    try:
        storage_io.upload(path, uri, content_type='application/json',
                          cache_control='no-store,max-age=0', compressed=False, **options)
    finally:
        path.unlink(missing_ok=True)


def _remote_json(uri: str) -> dict[str, Any]:
    return storage_io.read_json(uri)


def _load_release(root: Path, generation: str) -> tuple[Path, dict[str, Any]]:
    manifest_path = root / "phase2_private_data" / "snapshots" / generation / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "ok" or manifest.get("generation") != generation:
        raise RuntimeError("release artifact manifest is not publishable")
    artifacts = manifest.get("artifacts") or []
    required = manifest.get("required_object_keys") or []
    if len(artifacts) != len(required) or {item.get("object_key") for item in artifacts} != set(required):
        raise RuntimeError("release artifact manifest is incomplete")
    for item in artifacts:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != item.get("bytes") or _sha256(path) != item.get("sha256"):
            raise RuntimeError(f"release artifact failed validation: {path}")
    if len([item for item in artifacts if item.get("kind") == "default_pack"]) != 1:
        raise RuntimeError("release must contain exactly one default pack")
    return manifest_path, manifest


def _verify_refresh_lock(bucket: str, prefix: str, run_id: str | None) -> None:
    if not run_id:
        return
    payload = _remote_json(_uri(bucket, f"{prefix}/refresh/lock.json"))
    if payload.get("run_id") != run_id:
        raise RuntimeError("publication no longer owns the global refresh lock")


def _write_snapshot_pointer(root: Path, manifest: dict[str, Any]) -> None:
    pointer = root / "phase2_private_data" / "snapshots" / "current.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = pointer.with_suffix(".json.tmp")
    generation = manifest["generation"]
    temporary.write_text(json.dumps({
        "status": "ok",
        "generation": generation,
        "data_version": manifest["data_version"],
        "manifest": str(root / "phase2_private_data" / "snapshots" / generation / "manifest.json"),
        "release_manifest": str(root / "phase2_private_data" / "snapshots" / generation / "release-manifest.json"),
        "release_version": manifest["release_version"],
        "published_at": _utc_now(),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, pointer)


def publish(
    root: Path,
    generation: str,
    *,
    bucket: str,
    prefix: str = "card-stats",
    run_id: str | None = None,
    deployment_version: str | None = None,
    previous_deployment_version: str | None = None,
) -> dict[str, Any]:
    with exclusive(root / 'phase2_private_data/publication.lock'):
        return _publish_locked(root, generation, bucket=bucket, prefix=prefix, run_id=run_id,
            deployment_version=deployment_version, previous_deployment_version=previous_deployment_version)


def _publish_locked(root, generation, *, bucket, prefix='card-stats', run_id=None,
                    deployment_version=None, previous_deployment_version=None):
    if bool(deployment_version) != bool(previous_deployment_version):
        raise ValueError('coordinated publication requires both code versions')
    manifest_path, manifest = _load_release(root, generation)
    _verify_refresh_lock(bucket, prefix, run_id)
    manager = GenerationManager(
        root / "phase2_private_data" / "generations",
        root / "phase3_private_serving" / "current.json",
    )
    previous = manager.current()
    candidate = manager.inspect(generation)
    if previous is None:
        raise RuntimeError("no active generation exists for rollback")
    if deployment_version is None:
        previous_code = (previous.manifest.get('release') or {}).get('deployment_version')
        if previous_code:
            if Path(__file__).resolve().parent.name != previous_code:
                raise RuntimeError('code changes require coordinated code/data publication')
            deployment_version = previous_deployment_version = str(previous_code)
    if candidate.data_version != manifest.get("data_version"):
        raise RuntimeError("candidate and artifact data versions differ")
    pointer = root / "phase2_private_data" / "snapshots" / "current.json"
    previous_snapshot_pointer = pointer.read_bytes() if pointer.is_file() else None
    release = manifest["release_version"]
    immutable_prefix = f"{prefix}/releases/{release}"
    rollback_prefix = f"{prefix}/rollback/{generation}"
    artifacts = list(manifest["artifacts"])
    pack = next(item for item in artifacts if item.get("kind") == "default_pack")
    stable = [item for item in artifacts if item is not pack]
    status_key = f"{prefix}/refresh/status.json" if run_id else None
    backups: dict[str, str | None] = {}
    changed: list[dict[str, Any]] = []
    activated = False
    transaction_id = uuid.uuid4().hex
    object_guards = {}
    journal_path = root / "phase2_private_data" / JOURNAL_NAME

    timing = RefreshTimings()
    if journal_path.exists():
        raise RuntimeError('an interrupted publication requires recovery before another release')
    try:
        # Immutable copies make the exact release inspectable even after stable
        # aliases advance or a later release is rolled back.
        with timing.stage('immutable_uploads'):
            for item in artifacts:
                relative = item["object_key"]
                immutable_key = f"{immutable_prefix}/{relative.removeprefix(prefix + '/') }"
                immutable_uri = _uri(bucket, immutable_key)
                if not _remote_exists(immutable_uri):
                    _upload(Path(item["path"]), immutable_uri, item, immutable=True)
            release_manifest_uri = _uri(bucket, f"{immutable_prefix}/release-manifest.json")
            if not _remote_exists(release_manifest_uri):
                _upload(manifest_path, release_manifest_uri, {"kind": "release_manifest"}, immutable=True)

        # Snapshot every stable destination server-side before the first write.
        stable_keys = [item["object_key"] for item in artifacts]
        if status_key:
            stable_keys.append(status_key)
        with timing.stage('rollback_backups'):
            for key in stable_keys:
                destination = _uri(bucket, key)
                if _remote_exists(destination):
                    object_guards[key] = storage_io.object_state(destination)
                    backup = _uri(bucket, f"{rollback_prefix}/{key.removeprefix(prefix + '/')}")
                    storage_io.copy_object(destination, backup)
                    backups[key] = backup
                else:
                    object_guards[key] = {'generation': 0, 'owner': None, 'crc32c': None}
                    backups[key] = None

        journal = {
            "status": "publishing",
            "generation": generation,
            "previous_generation": previous.generation_id,
            "deployment_version": deployment_version,
            "previous_deployment_version": previous_deployment_version,
            "previous_snapshot_pointer": (
                base64.b64encode(previous_snapshot_pointer).decode("ascii")
                if previous_snapshot_pointer is not None else None
            ),
            "backups": backups,
            "changed": [],
            "activated": False,
            "created_at": _utc_now(),
            'transaction_id': transaction_id,
            'object_guards': object_guards,
        }
        _write_journal(journal_path, journal)

        # Prime the candidate while the previous generation is still public.
        # A failed warm-up aborts safely before either local pointer advances.
        with timing.stage('candidate_warmup'):
            warm_interactive_generation(manager, generation_id=generation)
        # Record the inverse before pointer mutation or any upload. Recovery
        # also safely restores an attempted upload that never reached storage.
        activated = True
        journal["activated"] = True
        _write_journal(journal_path, journal)
        manager.activate(generation)
        _write_snapshot_pointer(root, manifest)
        with timing.stage('stable_alias_uploads'):
            for index, item in enumerate(stable, start=1):
                changed.append(item)
                journal["changed"] = [entry["object_key"] for entry in changed]
                _write_journal(journal_path, journal)
                _upload(Path(item["path"]), _uri(bucket, item["object_key"]), item,
                        expected_generation=object_guards[item['object_key']]['generation'], owner=transaction_id)
                fail_after = int(os.environ.get("PHASE5_FAIL_AFTER_STABLE", "0") or 0)
                if fail_after and index >= fail_after:
                    raise RuntimeError("injected stable-artifact publication failure")
        if os.environ.get("PHASE5_FAIL_BEFORE_PACK") == "1":
            raise RuntimeError("injected default-pack publication failure")
        changed.append(pack)
        journal["changed"] = [entry["object_key"] for entry in changed]
        _write_journal(journal_path, journal)
        with timing.stage('atomic_pack_publication'):
            _upload_pack(Path(pack["path"]), _uri(bucket, pack["object_key"]),
                         expected_generation=object_guards[pack['object_key']]['generation'], owner=transaction_id)
        completed_at = _utc_now()
        if status_key:
            previous_status = _remote_json(_uri(bucket, status_key))
            status_artifact = {"object_key": status_key, "kind": "refresh_status"}
            changed.append(status_artifact)
            journal["changed"] = [entry["object_key"] for entry in changed]
            _write_journal(journal_path, journal)
            _upload_status({
                "state": "succeeded",
                "run_id": run_id,
                "progress_percent": 100,
                "phase": "Refresh complete",
                "started_at": previous_status.get("started_at"),
                "updated_at": completed_at,
                "last_completed_at": completed_at,
                "completed_data_version": manifest["data_version"],
            }, _uri(bucket, status_key), expected_generation=object_guards[status_key]['generation'], owner=transaction_id)

        generation_manifest = candidate.manifest_path
        payload = dict(candidate.manifest)
        payload["release"] = {
            **dict(payload.get("release") or {}),
            "status": "published",
            "release_version": release,
            "published_at": _utc_now(),
            "public_bucket": bucket,
            **({"deployment_version": deployment_version} if deployment_version else {}),
            # This descriptor is the immutable inverse of the publication.
            # It is retained after the transient crash-recovery journal is
            # removed so operators can perform an exact later rollback.
            "rollback": {
                "schema_version": 2 if deployment_version else 1,
                "previous_generation": previous.generation_id,
                **({"previous_deployment_version": previous_deployment_version}
                   if deployment_version else {}),
                "previous_snapshot_pointer": (
                    base64.b64encode(previous_snapshot_pointer).decode("ascii")
                    if previous_snapshot_pointer is not None else None
                ),
                "backup_prefix": rollback_prefix,
                "backups": backups,
                "published_object_keys": [item["object_key"] for item in changed],
                'object_guards': object_guards,
                'transaction_id': transaction_id,
            },
        }
        temporary = generation_manifest.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, generation_manifest)
        journal_path.unlink(missing_ok=True)
        return {
            "status": "ok", "generation": generation,
            "data_version": manifest["data_version"], "release_version": release,
            "artifact_count": len(artifacts), "previous_generation": previous.generation_id,
            "completed_at": completed_at,
            "timings": timing.stages,
        }
    except Exception:
        if activated:
            manager.activate(previous.generation_id)
            if previous_snapshot_pointer is None:
                pointer.unlink(missing_ok=True)
            else:
                temporary = pointer.with_suffix(".rollback.tmp")
                temporary.write_bytes(previous_snapshot_pointer)
                os.replace(temporary, pointer)
        _restore_aliases(bucket, backups, [item["object_key"] for item in changed], object_guards, transaction_id)
        journal_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--bucket", default="ark-nova-stats-dashboard-cache")
    parser.add_argument("--prefix", default="card-stats")
    parser.add_argument("--run-id")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument('--deployment-version')
    parser.add_argument('--previous-deployment-version')
    args = parser.parse_args()
    if args.recover:
        print(json.dumps(recover_interrupted(args.root.resolve(), bucket=args.bucket), indent=2, sort_keys=True))
        return 0
    if bool(args.deployment_version) != bool(args.previous_deployment_version):
        parser.error('both exact deployment versions are required')
    if args.deployment_version:
        from phase5_install_deployment import verify_installed
        root = args.root.resolve()
        for version in {args.deployment_version,args.previous_deployment_version}:
            verify_installed(root,version)
        deployed = root/'releases'/args.deployment_version
        if Path(__file__).resolve().parent != deployed.resolve():
            raise RuntimeError('publication must execute the candidate deployment')
        _, release = _load_release(root,args.generation)
        versions = release.get('versions') or {}
        producers = versions.get('code_files') or {}
        if not producers or any(not (deployed/name).resolve().is_relative_to(deployed.resolve())
            or _sha256(deployed/name) != digest for name,digest in producers.items()):
            raise RuntimeError('candidate snapshot producer differs from installed code')
        if _sha256(deployed/'contracts/dashboard-routes.v1.json') != versions.get('contract_sha256'):
            raise RuntimeError('candidate route contract differs from installed code')
    result = publish(
        args.root.resolve(), args.generation, bucket=args.bucket,
        prefix=args.prefix, run_id=args.run_id,
        deployment_version=args.deployment_version,
        previous_deployment_version=args.previous_deployment_version,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
