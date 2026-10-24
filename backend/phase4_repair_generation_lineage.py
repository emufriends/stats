"""Create an immutable metadata-only alias with the correct source version."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _utc_now


def _source_data_version(source) -> str | None:
    source_manifest = source.manifest.get("source_manifest")
    if source_manifest:
        path = Path(str(source_manifest))
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if payload.get("generation"):
                return str(payload["generation"])
    explicit = source.manifest.get("data_version")
    if explicit:
        return str(explicit)
    parent = source.manifest.get("parent_generation")
    return str(parent) if parent else source.data_version


def repair(generation_id: str) -> dict:
    root = Path(__file__).resolve().parent
    generations = root / "phase2_private_data" / "generations"
    manager = GenerationManager(
        generations,
        root / "phase3_private_serving" / "current.json",
    )
    source = manager.current()
    if generation_id == source.generation_id:
        raise ValueError("candidate generation must differ from the active generation")
    database = generations / f"{generation_id}.duckdb"
    manifest_path = generations / f"{generation_id}.manifest.json"
    if database.exists() or manifest_path.exists():
        raise FileExistsError(f"generation already exists: {generation_id}")

    # The source file is already immutable and fully validated.  A hard link
    # avoids copying several gigabytes merely to correct manifest lineage.
    os.link(source.database_path, database)
    manifest = dict(source.manifest)
    manifest.update({
        "generation": generation_id,
        "data_version": _source_data_version(source),
        "database": str(database),
        "parent_generation": source.generation_id,
        "staged_at": _utc_now(),
        "status": "ok",
        "lineage_repair": "source data version made explicit",
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        candidate = manager.inspect(generation_id)
        manager.activate(generation_id)
    except Exception:
        database.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    return {
        "generation": candidate.generation_id,
        "data_version": candidate.data_version,
        "parent_generation": source.generation_id,
        "active": manager.current().generation_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generation")
    args = parser.parse_args()
    print(json.dumps(repair(args.generation), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
