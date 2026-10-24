"""Create an immutable code/config deployment bundle and rollback pairing."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from phase3_duckdb_service import GenerationManager
from phase5_operational_controls import sha256_file
from phase5_release_source import verify as verify_release_source


def package(
    root: Path, output_dir: Path, deployment_state: Path | None = None,
) -> dict:
    approved = verify_release_source(root)
    if deployment_state is not None:
        state = json.loads(deployment_state.read_text(encoding="utf-8"))
        active_generation = str(state.get("generation") or "")
        rollback = dict((state.get("release") or {}).get("rollback") or {})
        if not active_generation:
            raise RuntimeError("deployment state has no active generation")
    else:
        manager = GenerationManager(
            root / "phase2_private_data" / "generations",
            root / "phase3_private_serving" / "current.json",
        )
        active = manager.current()
        if active is None:
            raise RuntimeError("cannot package deployment without an active generation")
        active_generation = active.generation_id
        rollback = dict((active.manifest.get("release") or {}).get("rollback") or {})
    if not rollback:
        raise RuntimeError(
            "active generation predates exact rollback descriptors; publish one "
            "transactional release before creating a production deployment bundle"
        )
    files = sorted({
        *root.glob("phase*.py"),
        *root.glob("*.service"),
        *root.glob("*.conf"),
        *root.glob("*.sh"),
        root / "main.py",
        root / "requirements.txt",
        root / "cards_attributes.csv",
        root / "merge_players.csv",
        root / "budget_policy.json",
        *root.glob("contracts/**/*"),
        *root.glob("cloudrun-duckdb-gateway/*"),
        *root.glob("budget_shutdown_service/*"),
    })
    files = [path for path in files if path.is_file() and "__pycache__" not in path.parts]
    if any(path.relative_to(root).as_posix() not in approved['files'] for path in files):
        raise RuntimeError('deployment includes an unreviewed source file')
    inventory = [{
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    } for path in files]
    identity = hashlib.sha256(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    version = f"deploy-{identity[:20]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{version}.tar.gz"
    raw_archive = output_dir / f".{version}.tar"
    with tarfile.open(raw_archive, "w") as bundle:
        for path in files:
            info = bundle.gettarinfo(str(path), arcname=path.relative_to(root).as_posix())
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if path.suffix == ".sh" else 0o644
            with path.open("rb") as handle:
                bundle.addfile(info, handle)
        metadata = json.dumps({
            "version": version,
            "schema_version": 2,
            "files": inventory,
        }, indent=2, sort_keys=True).encode("utf-8")
        info = tarfile.TarInfo("deployment-manifest.json")
        info.size = len(metadata)
        info.mtime = 0
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mode = 0o644
        bundle.addfile(info, io.BytesIO(metadata))
    try:
        archive.write_bytes(gzip.compress(raw_archive.read_bytes(), compresslevel=6, mtime=0))
    finally:
        raw_archive.unlink(missing_ok=True)
    result = {
        "status": "ok",
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "archive": str(archive),
        "archive_sha256": sha256_file(archive),
        "file_count": len(inventory),
        "active_generation": active_generation,
        "rollback": rollback,
        "release_source_sha256": sha256_file(root / 'release-source-manifest.json'),
        "rollback_ready": bool(rollback),
        "rollback_command": (
            f"python phase5_rollback_release.py {active_generation} --root {root}"
            if rollback else None
        ),
    }
    manifest = output_dir / f"{version}.json"
    manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--deployment-state", type=Path,
        help="Validated active generation manifest from the deployment host.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or root / "phase2_private_data" / "deployments").resolve()
    state = args.deployment_state.resolve() if args.deployment_state else None
    print(json.dumps(package(root, output, state), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
