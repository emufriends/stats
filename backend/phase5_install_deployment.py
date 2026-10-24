"""Verify and atomically install or roll back one immutable VM code bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_members(bundle: tarfile.TarFile):
    for member in bundle.getmembers():
        path = Path(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise RuntimeError(f"unsafe deployment member: {member.name}")
        yield member


def verify_installed(root: Path, version: str) -> Path:
    """Validate an installed code inventory before any pointer/service change."""
    if not re.fullmatch(r"deploy-[0-9a-f]{20}", version):
        raise RuntimeError("invalid deployment version")
    destination = root / 'releases' / version
    if not destination.is_dir() or destination.is_symlink():
        raise RuntimeError(f"deployment release is not installed: {version}")
    manifest = json.loads((destination / 'deployment-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != version or not manifest.get('files'):
        raise RuntimeError('installed deployment identity/inventory mismatch')
    for item in manifest['files']:
        path = destination / item['path']
        if (not path.resolve().is_relative_to(destination.resolve()) or path.is_symlink()
                or not path.is_file() or path.stat().st_size != item['bytes']
                or sha256_file(path) != item['sha256']):
            raise RuntimeError(f"installed deployment inventory mismatch: {item['path']}")
    return destination


def _install_service_units(destination: Path, unit_root: Path) -> None:
    """Install the verified service policy, including its shared memory ceiling."""
    for name in ("ark-nova-duckdb-api.service", "ark-nova-duckdb-refresh-worker.service"):
        shutil.copy2(destination / name, unit_root / name)
    # This exact filename belongs to this application; unrelated operator
    # drop-ins must survive both installation and rollback to an older bundle.
    limits = unit_root / 'ark-analytics.slice.d' / 'ark-nova-memory.conf'
    source = destination / 'ark-analytics.slice.conf'
    if source.is_file():
        limits.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, limits)
    else:
        limits.unlink(missing_ok=True)


def _activate(root: Path, version: str, *, restart: bool) -> dict:
    destination = verify_installed(root, version)
    pointer_path = root / "phase2_private_data" / "deployment-current.json"
    old = None
    previous = None
    if pointer_path.is_file():
        existing = json.loads(pointer_path.read_text(encoding="utf-8"))
        old = existing.get("current")
        previous = existing.get('previous')
    link = root / "current-app"
    temporary_link = root / ".current-app.tmp"
    temporary_link.unlink(missing_ok=True)
    temporary_link.symlink_to(destination, target_is_directory=True)
    os.replace(temporary_link, link)
    payload = {"current": version, "previous": old if old != version else previous}
    temporary = pointer_path.with_suffix(".tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, pointer_path)
    if restart:
        _install_service_units(destination, Path("/etc/systemd/system"))
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", "ark-nova-duckdb-api.service"], check=True)
        subprocess.run(["systemctl", "restart", "ark-nova-duckdb-refresh-worker.service"], check=True)
    return payload


def install(
    root: Path, archive: Path, descriptor_path: Path, *, restart: bool,
    activate: bool = True,
) -> dict:
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    if sha256_file(archive) != descriptor.get("archive_sha256"):
        raise RuntimeError("deployment archive checksum mismatch")
    version = str(descriptor["version"])
    if not re.fullmatch(r"deploy-[0-9a-f]{20}", version):
        raise RuntimeError("invalid deployment version")
    if restart and not activate:
        raise ValueError("an inactive deployment cannot restart production services")
    releases = root / "releases"
    destination = releases / version
    if destination.is_symlink():
        raise RuntimeError("deployment directory must not be a symlink")
    if not destination.exists():
        staging = releases / f".{version}.tmp"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(staging, members=_safe_members(bundle), filter="data")
        manifest = json.loads((staging / "deployment-manifest.json").read_text(encoding="utf-8"))
        if manifest.get("version") != version:
            raise RuntimeError("embedded deployment version mismatch")
        for item in manifest.get("files") or []:
            path = staging / item["path"]
            if not path.is_file() or path.stat().st_size != item["bytes"]:
                raise RuntimeError(f"deployment file is missing: {item['path']}")
            if sha256_file(path) != item["sha256"]:
                raise RuntimeError(f"deployment file checksum mismatch: {item['path']}")
        os.replace(staging, destination)
    # Verify existing installations too. A previously extracted directory is
    # not evidence that the on-disk bundle still matches its archive inventory.
    with tarfile.open(archive, 'r:gz') as bundle:
        embedded = bundle.extractfile('deployment-manifest.json')
        if embedded is None:
            raise RuntimeError('deployment archive has no inventory')
        trusted = json.loads(embedded.read())
    installed = json.loads((destination / 'deployment-manifest.json').read_text(encoding='utf-8'))
    if installed != trusted:
        raise RuntimeError('installed inventory differs from the verified archive')
    verify_installed(root, version)
    pointer = _activate(root, version, restart=restart) if activate else None
    return {"status": "ok", "version": version, "activated": activate, "pointer": pointer}


def rollback(root: Path, *, restart: bool) -> dict:
    pointer_path = root / "phase2_private_data" / "deployment-current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    previous = str(pointer.get("previous") or "")
    if not previous:
        raise RuntimeError("deployment has no rollback pair")
    result = _activate(root, previous, restart=restart)
    return {"status": "ok", "rolled_back_to": previous, "pointer": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/ascri"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--descriptor", type=Path)
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--activate-version", help="Activate a specific previously verified installed code bundle")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--stage-only", action="store_true",
                        help="Verify and install the immutable bundle without changing production pointers")
    args = parser.parse_args()
    if args.activate_version:
        if args.rollback or args.stage_only:
            parser.error("--activate-version cannot be combined with rollback or stage-only")
        result = {'status': 'ok', 'pointer': _activate(args.root.resolve(), args.activate_version, restart=args.restart)}
    elif args.rollback:
        result = rollback(args.root.resolve(), restart=args.restart)
    else:
        if not args.archive or not args.descriptor:
            parser.error("--archive and --descriptor are required for installation")
        result = install(
            args.root.resolve(), args.archive.resolve(), args.descriptor.resolve(),
            restart=args.restart, activate=not args.stage_only,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
