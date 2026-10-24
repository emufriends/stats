"""Upload a verified immutable VM deployment; advance its pointer last."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from phase5_operational_controls import sha256_file


def _run(*args: str) -> None:
    executable = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not executable:
        raise RuntimeError("Google Cloud CLI executable was not found")
    subprocess.run([executable, *args], check=True, timeout=900)


def publish(descriptor_path: Path, *, bucket: str, prefix: str, installer: Path) -> dict:
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    archive = Path(descriptor["archive"])
    if sha256_file(archive) != descriptor.get("archive_sha256"):
        raise RuntimeError("deployment archive checksum mismatch")
    version = str(descriptor["version"])
    base = f"gs://{bucket}/{prefix.strip('/')}/{version}"
    _run("storage", "cp", "--quiet", "--cache-control=private,max-age=31536000,immutable",
         str(archive), f"{base}.tar.gz")
    _run("storage", "cp", "--quiet", "--cache-control=private,max-age=31536000,immutable",
         str(descriptor_path), f"{base}.json")
    _run("storage", "cp", "--quiet", "--cache-control=no-cache,max-age=0",
         str(installer), f"gs://{bucket}/{prefix.strip('/')}/installer.py")
    pointer = {
        "version": version,
        "archive_uri": f"{base}.tar.gz",
        "descriptor_uri": f"{base}.json",
        "archive_sha256": descriptor["archive_sha256"],
    }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(pointer, handle, sort_keys=True)
        path = Path(handle.name)
    try:
        _run("storage", "cp", "--quiet", "--cache-control=no-store,max-age=0", str(path),
             f"gs://{bucket}/{prefix.strip('/')}/current.json")
    finally:
        path.unlink(missing_ok=True)
    return {"status": "ok", **pointer}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("descriptor", type=Path)
    parser.add_argument("--bucket", default="ark-nova-stats-phase2-import-413312054512")
    parser.add_argument("--prefix", default="phase5/deployments")
    parser.add_argument("--installer", type=Path,
                        default=Path(__file__).resolve().with_name("phase5_install_deployment.py"))
    args = parser.parse_args()
    print(json.dumps(publish(args.descriptor.resolve(), bucket=args.bucket,
                             prefix=args.prefix, installer=args.installer.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
