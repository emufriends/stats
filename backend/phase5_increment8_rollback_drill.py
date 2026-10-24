"""Rehearse an exact public rollback and restore the current DuckDB release.

The drill is intentionally production-shaped: it restores every stable Cloud
Storage alias from the active release's inverse descriptor, activates the
paired data parent, verifies both serving and public-pack state, then republishes
the original generation and verifies that it is current again.  The forward
restore runs from ``finally`` once rollback succeeds so an intermediate
assertion cannot intentionally leave production on the parent generation.
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _utc_now
from phase5_publish_release import _gcloud, _uri, publish
from phase5_rollback_release import rollback


BUCKET = "ark-nova-stats-dashboard-cache"
PACK_KEY = "card-stats/bootstrap/default-pack.json"


def _public_pack(bucket: str) -> dict:
    result = subprocess.run(
        ["gcloud", "storage", "cat", _uri(bucket, PACK_KEY)],
        check=True, capture_output=True, timeout=600,
    )
    payload = result.stdout
    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    return json.loads(payload.decode("utf-8"))


def _summary(manager: GenerationManager, pack: dict) -> dict:
    active = manager.current()
    return {
        "generation": active.generation_id if active else None,
        "data_version": active.data_version if active else None,
        "ready": manager.readiness().get("ready"),
        "rollback_ready": manager.readiness().get("rollback_ready"),
        "pack_data_version": pack.get("data_version"),
        "pack_release_version": pack.get("release_version"),
    }


def drill(root: Path, *, bucket: str) -> dict:
    manager = GenerationManager(
        root / "phase2_private_data/generations",
        root / "phase3_private_serving/current.json",
    )
    original = manager.current()
    if original is None:
        raise RuntimeError("no active generation is available")
    descriptor = dict((original.manifest.get("release") or {}).get("rollback") or {})
    parent_id = str(descriptor.get("previous_generation") or "")
    if not parent_id:
        raise RuntimeError("active generation has no exact rollback parent")
    parent = manager.inspect(parent_id)

    before_pack = _public_pack(bucket)
    before = _summary(manager, before_pack)
    if before["pack_data_version"] != original.data_version:
        raise RuntimeError("public pack is not aligned with the active generation before drill")

    rolled_back = False
    rollback_state: dict = {}
    rollback_error: str | None = None
    restore_result: dict | None = None
    restore_error: str | None = None
    try:
        rollback_result = rollback(root, original.generation_id, bucket=bucket)
        rolled_back = True
        parent_pack = _public_pack(bucket)
        rollback_state = _summary(manager, parent_pack)
        rollback_state["operation"] = rollback_result
        if rollback_state["generation"] != parent_id:
            raise RuntimeError("serving pointer did not activate the rollback parent")
        if rollback_state["pack_data_version"] != parent.data_version:
            raise RuntimeError("public pack did not return to the rollback parent's data version")
    except Exception as exc:  # Preserve evidence while the finally restore runs.
        rollback_error = f"{type(exc).__name__}: {exc}"
    finally:
        if rolled_back:
            try:
                restore_result = publish(root, original.generation_id, bucket=bucket)
            except Exception as exc:
                restore_error = f"{type(exc).__name__}: {exc}"

    after_pack = _public_pack(bucket)
    after = _summary(manager, after_pack)
    restored = (
        restore_error is None
        and after["generation"] == original.generation_id
        and after["data_version"] == original.data_version
        and after["pack_data_version"] == original.data_version
        and after["ready"] is True
    )
    report = {
        "status": "pass" if rollback_error is None and restored else "fail",
        "checked_at": _utc_now(),
        "original_generation": original.generation_id,
        "rollback_parent": parent_id,
        "before": before,
        "rollback": rollback_state,
        "rollback_error": rollback_error,
        "restore": restore_result,
        "restore_error": restore_error,
        "after": after,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/ascri"))
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = drill(args.root.resolve(), bucket=args.bucket)
    encoded = json.dumps(report, indent=2, sort_keys=True)
    print(encoded)
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
