"""Resource, reuse, and retention controls for the DuckDB refresh pipeline.

The source export, moving spreadsheets, and build-contract code form one
immutable refresh identity.  A matching active release is a no-op; a matching
validated inactive candidate can be published without repeating its build.
Local cleanup always preserves the active release and its rollback parent.
"""

from __future__ import annotations

import hashlib
import ast
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Iterable


GIB = 1024 ** 3
BUILD_INPUT_NAMES = {
    "cards_attributes.csv",
    "merge_players.csv",
    "phase2_local_vertical_slice.py",
    "phase3_duckdb_service.py",
    "phase3_cards_pair_contracts.py",
    "phase4_combo_mw_contracts.py",
    "phase4_local_routes.py",
    "phase4_local_scope.py",
    "phase4_materialize_route_derivatives.py",
    "phase4_metadata.py",
    "phase4_players_routes.py",
    "phase4_records_source.py",
    "phase5_materialize_external.py",
    "phase5_operational_controls.py",
    "phase5_refresh_workflow.py",
    "phase5_snapshot_builder.py",
    "phase5_source_materialize.py",
    "phase5_source_reconcile.py",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_inventory(paths: Iterable[Path], base: Path) -> list[dict[str, Any]]:
    inventory = []
    for path in sorted({item.resolve() for item in paths if item.is_file()}):
        inventory.append({
            "path": path.relative_to(base.resolve()).as_posix()
            if path.is_relative_to(base.resolve()) else path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return inventory


def _runtime_code_paths(root: Path, input_names=None) -> set[Path]:
    """Version producer inputs and their local imports, not diagnostic scripts.

    An audit-only edit must not rebuild unchanged facts. Conversely, importing
    a new runtime helper must automatically include it in the build identity.
    Both top-level and function-local Python imports participate.
    """
    paths: set[Path] = set()
    pending = [root / name for name in (BUILD_INPUT_NAMES if input_names is None else input_names)]
    while pending:
        path = pending.pop()
        if path in paths or not path.is_file():
            continue
        paths.add(path)
        if path.suffix != '.py':
            continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.append(node.module)
        pending.extend(root / (name + '.py') for name in modules
                       if '.' not in name and (root / (name + '.py')).is_file())
    return paths


def _moving_inventory(paths: Iterable[Path], base: Path) -> list[dict[str, Any]]:
    inventory = _file_inventory(paths, base)
    for item in inventory:
        if item["path"] != "tournament-metadata.json":
            continue
        payload = json.loads((base / item["path"]).read_text(encoding="utf-8"))
        source = dict(payload.get("source") or {})
        canonical = {
            "rows": payload.get("rows") or [],
            "source": {
                key: source.get(key)
                for key in ("sha256", "row_count") if source.get(key) is not None
            },
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        item["bytes"] = len(encoded)
        item["sha256"] = hashlib.sha256(encoded).hexdigest()
    return inventory


def refresh_inputs(root: Path, source_root: Path, moving_source_dir: Path) -> dict[str, Any]:
    source_manifest = json.loads((source_root / "manifest.json").read_text(encoding="utf-8"))
    source_identity = {
        "generation": source_manifest.get("generation"),
        "source_fingerprints": source_manifest.get("source_fingerprints"),
        "files": source_manifest.get("files"),
    }
    moving_paths = [
        path for path in moving_source_dir.iterdir()
        if path.is_file() and path.name != "source-status.json"
        and path.suffix.lower() in {".csv", ".json"}
    ]
    code_paths = _runtime_code_paths(root)
    contracts = root / "contracts"
    if contracts.is_dir():
        code_paths.update(path for path in contracts.rglob("*") if path.is_file())
    payload = {
        "schema_version": 1,
        "source": source_identity,
        "moving_sources": _moving_inventory(moving_paths, moving_source_dir),
        "build_contracts": _file_inventory(code_paths, root),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["fingerprint"] = hashlib.sha256(encoded).hexdigest()
    return payload


def validate_reusable_candidate(root: Path, generation: str, fingerprint: str) -> dict[str, Any] | None:
    private = root / "phase2_private_data"
    manifest_path = private / "generations" / f"{generation}.manifest.json"
    database_path = private / "generations" / f"{generation}.duckdb"
    release_path = private / "snapshots" / generation / "release-manifest.json"
    if not (manifest_path.is_file() and database_path.is_file() and release_path.is_file()):
        return None
    try:
        generation_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        release_manifest = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if generation_manifest.get("refresh_fingerprint") != fingerprint:
        return None
    if (generation_manifest.get("release") or {}).get("status") not in {"validated", "published"}:
        return None
    if release_manifest.get("status") != "ok" or release_manifest.get("generation") != generation:
        return None
    artifacts = release_manifest.get("artifacts") or []
    required = release_manifest.get("required_object_keys") or []
    if not artifacts or {item.get("object_key") for item in artifacts} != set(required):
        return None
    for item in artifacts:
        path = Path(str(item.get("path") or ""))
        if not path.is_file() or path.stat().st_size != item.get("bytes"):
            return None
        if sha256_file(path) != item.get("sha256"):
            return None
    return {
        "generation": generation,
        "data_version": release_manifest.get("data_version"),
        "snapshot_count": release_manifest.get("snapshot_count"),
        "artifact_count": len(artifacts),
        "release_version": release_manifest.get("release_version"),
    }


def ensure_refresh_headroom(root: Path, active_database: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(root)
    minimum = int(float(os.environ.get("PHASE5_MIN_FREE_GIB", "8")) * GIB)
    allowance_override = os.environ.get("PHASE5_CANDIDATE_ALLOWANCE_GIB")
    candidate_allowance = (
        int(float(allowance_override) * GIB)
        if allowance_override not in (None, "")
        else int(active_database.stat().st_size * 1.20)
    )
    if candidate_allowance <= 0:
        raise RuntimeError("PHASE5_CANDIDATE_ALLOWANCE_GIB must be positive")
    required = max(minimum, candidate_allowance)
    if usage.free < required:
        raise RuntimeError(
            f"insufficient refresh disk headroom: {usage.free / GIB:.2f} GiB free; "
            f"{required / GIB:.2f} GiB required"
        )
    return {
        "free_bytes": usage.free,
        "required_bytes": required,
        "total_bytes": usage.total,
    }


def prune_local_releases(
    root: Path, keep_completed: int = 2, *, allow_staging_cleanup: bool = False
) -> dict[str, Any]:
    """Remove old local releases without touching serving/rollback identities."""
    private = root / "phase2_private_data"
    generations = private / "generations"
    pointer_path = root / "phase3_private_serving" / "current.json"
    protected: set[str] = set()
    if pointer_path.is_file():
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        active = str(pointer.get("generation") or "")
        previous = str(pointer.get("previous_generation") or "")
        if active:
            protected.add(active)
            active_manifest = generations / f"{active}.manifest.json"
            if active_manifest.is_file():
                payload = json.loads(active_manifest.read_text(encoding="utf-8"))
                parent = str(payload.get("parent_generation") or "")
                if parent:
                    protected.add(parent)
        if previous:
            protected.add(previous)
    journal = private / "publication-transaction.json"
    if journal.is_file():
        payload = json.loads(journal.read_text(encoding="utf-8"))
        protected.update(filter(None, [
            str(payload.get("generation") or ""),
            str(payload.get("previous_generation") or ""),
        ]))
    candidate_pointer = private / 'candidate-current.json'
    if candidate_pointer.is_file():
        candidate = json.loads(candidate_pointer.read_text(encoding='utf-8'))
        if candidate.get('generation'):
            identity = str(candidate['generation'])
            descriptor = generations / f'{identity}.manifest.json'
            payload = json.loads(descriptor.read_text(encoding='utf-8')) if descriptor.is_file() else {}
            # A test pointer must not pin a historical published database
            # forever after it has left the active/rollback pair.
            if (payload.get('release') or {}).get('status') not in {'published','rolled_back'}:
                protected.add(identity)
    manifests = sorted(
        generations.glob("*.manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    protected.update(path.name.removesuffix(".manifest.json") for path in manifests[:keep_completed])
    removed: list[str] = []
    for manifest in manifests:
        generation = manifest.name.removesuffix(".manifest.json")
        if generation in protected:
            continue
        (generations / f"{generation}.duckdb").unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        shutil.rmtree(private / "snapshots" / generation, ignore_errors=True)
        removed.append(generation)

    cutoff = time.time() - int(os.environ.get("PHASE5_STAGING_RETENTION_SECONDS", "86400"))
    staging_removed: list[str] = []
    staging = private / "staging"
    if staging.is_dir() and (
        allow_staging_cleanup or not (private / "refresh.lock").exists()
    ):
        for path in staging.iterdir():
            if path.stat().st_mtime >= cutoff:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            staging_removed.append(path.name)
    return {
        "protected_generations": sorted(protected),
        "removed_generations": removed,
        "removed_staging": staging_removed,
    }


def prune_source_exports(root: Path, *, extra_protected: Iterable[Path] = (),
                         keep_newest: int = 1) -> dict[str, Any]:
    """Bound failed-refresh export growth without losing referenced sources.

    Read every reference before deleting anything (malformed metadata fails
    closed). Only immediate, non-symlink .source-* directories inside the
    configured source root are eligible. Active/rollback/candidate manifests,
    the committed latest source, a caller's in-flight source, the newest complete
    export, and directories less than a day old remain protected.
    """
    private = root.resolve() / 'phase2_private_data'
    source = private / 'source'
    if not source.is_dir():
        return {'protected_sources': [], 'removed_sources': []}
    if source.is_symlink() or source.resolve().parent != private.resolve():
        raise RuntimeError('source cleanup root escaped the configured private directory')
    source = source.resolve()
    protected: set[str] = set()
    latest = source / 'latest'
    references = [*extra_protected]
    if latest.exists():
        references.append(latest)
    for reference in references:
        resolved = reference.resolve()
        if resolved.parent == source:
            protected.add(resolved.name)
        elif reference == latest:
            raise RuntimeError('latest source points outside the configured source root')
    for manifest in (private / 'generations').glob('*.manifest.json'):
        payload = json.loads(manifest.read_text(encoding='utf-8'))
        generation = str(payload.get('source_generation') or '')
        if generation:
            protected.add('.source-' + generation)
        materialized = payload.get('source_materialization') or {}
        if materialized.get('source_manifest'):
            referenced = Path(materialized['source_manifest']).resolve().parent
            if referenced.parent == source:
                protected.add(referenced.name)
    directories = sorted(
        (path for path in source.glob('.source-*')
         if path.is_dir() and not path.is_symlink() and path.resolve().parent == source),
        key=lambda path: path.stat().st_mtime, reverse=True,
    )
    complete = [path for path in directories if (path / 'manifest.json').is_file()]
    protected.update(path.name for path in complete[:max(keep_newest, 0)])
    cutoff = time.time() - int(os.environ.get('PHASE5_SOURCE_RETENTION_SECONDS', '86400'))
    removed = []
    for path in directories:
        if path.name in protected or path.stat().st_mtime >= cutoff:
            continue
        # Re-check the resolved boundary immediately before recursive removal.
        if path.is_symlink() or path.resolve().parent != source:
            raise RuntimeError('source cleanup target escaped its configured root')
        shutil.rmtree(path)
        removed.append(path.name)
    return {'protected_sources': sorted(protected), 'removed_sources': removed}
