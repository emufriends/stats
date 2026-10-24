"""Finish the interrupted Phase 4 route-derivative staging operation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb, _utc_now


def finalize(generation_id: str) -> dict:
    root = Path(__file__).resolve().parent
    staging = root / "phase2_private_data" / "staging" / f"{generation_id}.duckdb"
    if not staging.is_file():
        raise FileNotFoundError(staging)
    generations = root / "phase2_private_data" / "generations"
    manager = GenerationManager(generations, root / "phase3_private_serving" / "current.json")
    source = manager.current()
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(staging))
    try:
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    manifest = dict(source.manifest)
    manifest.update({
        "generation": generation_id,
        "database": str(generations / f"{generation_id}.duckdb"),
        "parent_generation": source.generation_id,
        "staged_at": _utc_now(),
        "status": "ok",
        "route_derivatives": {
            "arena_roster_narrow": 6236,
        },
    })
    manifest_path = staging.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    candidate = manager.stage(generation_id, staging, manifest_path)
    manager.activate(generation_id)
    staging.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)
    return {"generation": candidate.generation_id, "data_version": candidate.data_version,
            "parent_generation": source.generation_id, "active": manager.current().generation_id}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generation")
    print(json.dumps(finalize(parser.parse_args().generation), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
