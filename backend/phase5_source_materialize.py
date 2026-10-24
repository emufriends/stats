"""Materialize one controlled Parquet source export into a DuckDB database.

This is the source-import half of the private Phase 5 refresh boundary.  It
only reads a versioned Full Sample/Logs export, writes a new database, and
never changes the active generation pointer.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from phase3_duckdb_service import _load_duckdb, _utc_now
from phase5_source_sync import validate_files


def materialize(
    source_root: Path,
    database_path: Path,
    *,
    threads: int = 2,
    memory_limit: str = "2800MB",
    temp_directory: Path | None = None,
) -> dict[str, Any]:
    manifest_path = source_root / "manifest.json"
    full_files = sorted(source_root.glob("full_sample-*.parquet"))
    log_files = sorted(source_root.glob("logs-*.parquet"))
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not full_files or not log_files:
        raise RuntimeError("source generation must contain Full Sample and Logs Parquet files")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "ok":
        raise RuntimeError("Source manifest is not committed")
    if manifest.get("mode") == "source_sync":
        validate_files(source_root, manifest)
    if database_path.exists():
        raise FileExistsError(database_path)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    spill = temp_directory or database_path.parent / f"{database_path.stem}.spill"
    spill.mkdir(parents=True, exist_ok=True)
    duckdb = _load_duckdb()
    started = time.perf_counter()
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute(f"PRAGMA threads = {max(1, int(threads))}")
        connection.execute("PRAGMA preserve_insertion_order = false")
        connection.execute("PRAGMA enable_progress_bar = false")
        connection.execute("PRAGMA memory_limit = ?", [memory_limit])
        connection.execute("PRAGMA temp_directory = ?", [str(spill)])
        full_glob = (source_root / "full_sample-*.parquet").as_posix()
        logs_glob = (source_root / "logs-*.parquet").as_posix()
        connection.execute(
            "CREATE TABLE source_full_sample AS SELECT * FROM read_parquet(?)",
            [full_glob],
        )
        connection.execute(
            "CREATE TABLE source_logs AS SELECT * FROM read_parquet(?)",
            [logs_glob],
        )
        full_rows = connection.execute("SELECT COUNT(*) FROM source_full_sample").fetchone()[0]
        log_rows = connection.execute("SELECT COUNT(*) FROM source_logs").fetchone()[0]
        full_tables = connection.execute(
            "SELECT COUNT(DISTINCT table_id) FROM source_full_sample"
        ).fetchone()[0]
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    report = {
        "status": "ok",
        "generation": manifest.get("generation"),
        "database": str(database_path),
        "built_at": _utc_now(),
        "source_manifest": str(manifest_path),
        "relations": {
            "source_full_sample": {"rows": int(full_rows), "distinct_tables": int(full_tables)},
            "source_logs": {"rows": int(log_rows)},
        },
        "build_seconds": round(time.perf_counter() - started, 3),
    }
    database_path.with_suffix(".source.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="2800MB")
    parser.add_argument("--temp-directory", type=Path)
    args = parser.parse_args()
    materialize(
        args.source_root,
        args.database_path,
        threads=args.threads,
        memory_limit=args.memory_limit,
        temp_directory=args.temp_directory,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
