"""Plan or execute retention of immutable public release/rollback prefixes.

The default is read-only. Execution requires both ``--execute`` and an exact
``--confirm-bucket`` value. Stable public aliases are never in the deletion
inventory.

This planner is not an approved production deletion inventory: it only protects
the newest prefixes and default-pack references. It does not resolve the VM's
paired code/data rollback descriptors or publication journals, and a missing
default pack does not fail the plan closed. Do not use ``--execute`` until those
references are checked and the exact deletion list is approved by the owner.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gcloud", *args], check=check, text=True, capture_output=True, timeout=900)


def plan(bucket: str, prefix: str, keep: int) -> dict:
    root = f"gs://{bucket}/{prefix.strip('/')}"
    result = _run("storage", "ls", "-l", "--recursive", f"{root}/**", check=False)
    objects = []
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3 and parts[2].startswith("gs://"):
            objects.append((parts[1], parts[2]))
    groups: dict[str, set[str]] = defaultdict(set)
    modified: dict[str, str] = {}
    for timestamp, uri in objects:
        relative = uri.removeprefix(root + "/")
        parts = relative.split("/")
        if len(parts) >= 3 and parts[0] in {"releases", "rollback"}:
            key = f"{parts[0]}/{parts[1]}"
            groups[key].add(uri)
            modified[key] = max(timestamp, modified.get(key, ""))
    ordered = {
        family: sorted(
            (key for key in groups if key.startswith(family + "/")),
            key=lambda key: modified[key], reverse=True,
        )
        for family in ("releases", "rollback")
    }
    retained = {key for keys in ordered.values() for key in keys[:keep]}
    pack_result = _run("storage", "cat", f"{root}/bootstrap/default-pack.json", check=False)
    try:
        pack = json.loads(pack_result.stdout) if pack_result.returncode == 0 else {}
    except json.JSONDecodeError:
        pack = {}
    if pack.get("release_version"):
        retained.add(f"releases/{pack['release_version']}")
    if pack.get("generation"):
        retained.add(f"rollback/{pack['generation']}")
    delete_groups = sorted(set(groups) - retained)
    return {
        "status": "planned",
        "bucket": bucket,
        "prefix": prefix,
        "keep_per_family": keep,
        "retained_groups": sorted(retained),
        "delete_groups": delete_groups,
        "delete_objects": [uri for key in delete_groups for uri in sorted(groups[key])],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default="ark-nova-stats-dashboard-cache")
    parser.add_argument("--prefix", default="card-stats")
    parser.add_argument("--keep", type=int, default=3)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-bucket")
    args = parser.parse_args()
    if args.keep < 2:
        parser.error("--keep must be at least 2")
    report = plan(args.bucket, args.prefix, args.keep)
    if args.execute:
        if args.confirm_bucket != args.bucket:
            parser.error("--confirm-bucket must exactly match --bucket")
        for uri in report["delete_objects"]:
            _run("storage", "rm", "--quiet", uri)
        report["status"] = "executed"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
