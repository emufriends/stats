"""Stage and atomically activate a generation with current filter metadata.

This is an operator-facing private migration command. It copies the active
immutable database to a temporary writable staging file, adds the validated
metadata relations, writes provenance into the manifest, and only then asks
GenerationManager to stage and activate the candidate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb
from phase4_metadata import fetch_tournament_metadata, load_arena_settings, materialize_metadata_tables


def stage_current_generation(root: str | Path, arena_settings: str | Path = "arena/arena_settings.csv"):
    root = Path(root).resolve()
    pointer = json.loads((root / "phase3_private_serving" / "current.json").read_text(encoding="utf-8"))
    current_id = pointer["generation"]
    current_db = root / "phase2_private_data" / "generations" / f"{current_id}.duckdb"
    current_manifest_path = root / "phase2_private_data" / "generations" / f"{current_id}.manifest.json"
    manifest = json.loads(current_manifest_path.read_text(encoding="utf-8"))
    tournament_rows, tournament_info = fetch_tournament_metadata()
    arena_rows, arena_info = load_arena_settings(root / arena_settings)
    generation_id = f"phase4-{current_id}-metadata"

    manager = GenerationManager(
        root / "phase2_private_data" / "generations",
        pointer_path=root / "phase3_private_serving" / "current.json",
    )

    with tempfile.TemporaryDirectory(prefix="phase4-metadata-", dir=str(root)) as directory:
        staging_db = Path(directory) / f"{generation_id}.duckdb"
        staging_manifest = Path(directory) / f"{generation_id}.manifest.json"
        shutil.copyfile(current_db, staging_db)
        duckdb = _load_duckdb()
        connection = duckdb.connect(str(staging_db))
        try:
            materialize_metadata_tables(connection, tournament_rows, arena_rows)
        finally:
            connection.close()
        candidate_manifest = dict(manifest)
        candidate_manifest.update({
            "generation": generation_id,
            "status": "ok",
            "parent_generation": current_id,
            "metadata_sources": {
                "tournament_sheet": tournament_info,
                "arena_settings": arena_info,
            },
        })
        staging_manifest.write_text(
            json.dumps(candidate_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manager.stage_and_activate(generation_id, staging_db, staging_manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--arena-settings", default="arena/arena_settings.csv")
    args = parser.parse_args()
    generation = stage_current_generation(args.root, args.arena_settings)
    print(json.dumps({
        "generation": generation.generation_id,
        "database": str(generation.database_path),
        "data_version": generation.data_version,
    }))


if __name__ == "__main__":
    main()
