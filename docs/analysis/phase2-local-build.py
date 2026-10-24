"""Build the first private, read-only DuckDB generation from Phase 2 exports.

The builder deliberately starts with the two canonical source relations. This
keeps the first migration auditable: no BigQuery preparation SQL is silently
rewritten before the source schema and row counts are verified locally. Later
vertical-slice builders can add narrow event relations and compare their
payloads against the existing dashboard.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_duckdb(private_root: Path):
    package_dir = private_root / "python314"
    if not package_dir.exists():
        package_dir = private_root / "python"
    sys.path.insert(0, str(package_dir))
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"DuckDB is not installed in {package_dir}; install it into the private directory."
        ) from exc
    return duckdb


def build(source_root: Path, database_path: Path, threads: int) -> int:
    manifest_path = source_root / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing generation manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    full_glob = (source_root / "full_sample-*.parquet").as_posix()
    logs_glob = (source_root / "logs-*.parquet").as_posix()
    if not list(source_root.glob("full_sample-*.parquet")):
        raise SystemExit("The generation has no Full Sample Parquet files.")
    if not list(source_root.glob("logs-*.parquet")):
        raise SystemExit("The generation has no Logs Parquet files.")

    database_path.parent.mkdir(parents=True, exist_ok=True)
    duckdb = load_duckdb(source_root.parent)
    started = time.perf_counter()
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute(f"PRAGMA threads = {max(1, int(threads))}")
        connection.execute("PRAGMA enable_progress_bar = false")
        connection.execute("DROP TABLE IF EXISTS source_full_sample")
        connection.execute("DROP TABLE IF EXISTS source_logs")
        connection.execute(
            "CREATE TABLE source_full_sample AS SELECT * FROM read_parquet(?)",
            [full_glob],
        )
        connection.execute(
            "CREATE TABLE source_logs AS SELECT * FROM read_parquet(?)",
            [logs_glob],
        )
        full_count = connection.execute(
            "SELECT COUNT(*) FROM source_full_sample"
        ).fetchone()[0]
        logs_count = connection.execute("SELECT COUNT(*) FROM source_logs").fetchone()[0]
        table_ids = connection.execute(
            "SELECT COUNT(DISTINCT table_id) FROM source_full_sample"
        ).fetchone()[0]
        full_columns = connection.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = 'source_full_sample'"
        ).fetchone()[0]
        logs_columns = connection.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = 'source_logs'"
        ).fetchone()[0]
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    local_manifest = {
        "status": "ok",
        "generation": manifest.get("generation"),
        "built_at": utc_now(),
        "database": str(database_path),
        "source_manifest": str(manifest_path),
        "relations": {
            "source_full_sample": {
                "rows": int(full_count),
                "distinct_tables": int(table_ids),
                "columns": int(full_columns),
            },
            "source_logs": {
                "rows": int(logs_count),
                "columns": int(logs_columns),
            },
        },
        "build_seconds": round(time.perf_counter() - started, 3),
        "next_step": "Run the narrow slice builder, Cards snapshot producer, and focused reconcilers before implementing additional page families.",
    }
    output_manifest = database_path.with_suffix(".manifest.json")
    output_manifest.write_text(
        json.dumps(local_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(local_manifest, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    return build(args.source_root, args.database_path, args.threads)


if __name__ == "__main__":
    sys.exit(main())
