"""Emergency same-generation snapshot repair; never a normal refresh path.

Complete releases must use ``phase5_publish_release.py``. This utility is only
for explicitly selected artifacts whose data version already equals the active
public pack, and it refuses to run while the global refresh lock exists.
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import tempfile
from pathlib import Path


BUCKET = "gs://ark-nova-stats-dashboard-cache"
PACK_KEY = "card-stats/bootstrap/default-pack.json"
LOCK_KEY = "card-stats/refresh/lock.json"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_root", type=Path)
    parser.add_argument("keys", nargs="+")
    parser.add_argument("--schema-version", type=int, default=23)
    args = parser.parse_args()
    lock = subprocess.run(
        ["gcloud", "storage", "ls", f"{BUCKET}/{LOCK_KEY}"],
        check=False, text=True, capture_output=True,
    )
    if lock.returncode == 0:
        raise RuntimeError("cannot patch snapshots while a coordinated release owns the refresh lock")
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        current_pack = temp / "current-pack.json"
        run("gcloud", "storage", "cp", "--quiet", f"{BUCKET}/{PACK_KEY}", str(current_pack))
        pack = json.loads(current_pack.read_text(encoding="utf-8"))
        snapshots = dict(pack.get("snapshots") or {})
        version = None
        for key in args.keys:
            source = args.snapshot_root / key
            payload = json.loads(source.read_text(encoding="utf-8"))
            current = str(payload.get("data_version") or "")
            if not current:
                raise RuntimeError(f"snapshot has no data_version: {source}")
            if version is None:
                version = current
            elif current != version:
                raise RuntimeError("selected snapshots use mixed data versions")
            run(
                "gcloud", "storage", "cp", "--quiet",
                "--cache-control=public,max-age=300,must-revalidate",
                "--content-type=application/json", str(source), f"{BUCKET}/{key}",
            )
            snapshots[key] = payload
        if any(
            payload.get("data_version") != version
            for key, payload in snapshots.items()
            if "/records/elo-leaderboard/" not in key
        ):
            raise RuntimeError("public pack would contain mixed analytical data versions")
        result = {
            "status": "ok",
            "schema_version": args.schema_version,
            "data_version": version,
            "snapshots": snapshots,
        }
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        compressed = temp / "default-pack.json.gz"
        compressed.write_bytes(gzip.compress(encoded, compresslevel=6, mtime=0))
        run(
            "gcloud", "storage", "cp", "--quiet",
            "--cache-control=no-cache,max-age=0,must-revalidate",
            "--content-type=application/json", "--content-encoding=gzip",
            str(compressed), f"{BUCKET}/{PACK_KEY}",
        )
    print(json.dumps({"status": "ok", "data_version": version, "patched": args.keys}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
