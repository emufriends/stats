"""Reconcile complete source exports into a copy of an immutable DuckDB DB.

Only changed game tables are replaced. Comparing complete table-level SHA-256
multisets includes late arrivals, historical corrections, removed rows, duplicate
multiplicity and whole-game deletions. A date/max-ID cursor cannot do this.
The active DB and serving pointer are never modified here. Derivatives in the
copy are stale until the normal builder finishes; do not serve this staging DB.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from phase3_duckdb_service import _load_duckdb, _utc_now
from phase5_source_sync import validate_files


def reconcile_family(connection, table, parquet_glob):
    if table not in {"source_full_sample", "source_logs"}:
        raise ValueError("Unknown source family")
    # DuckDB does not bind parameters in CREATE VIEW. Quote only the path
    # literal; relation names above are a fixed allowlist.
    quoted_glob = parquet_glob.replace("'", "''")
    connection.execute(f"CREATE OR REPLACE TEMP VIEW incoming AS SELECT * FROM read_parquet('{quoted_glob}')")
    old_schema = [(r[0], r[1]) for r in connection.execute(f'DESCRIBE "{table}"').fetchall()]
    new_schema = [(r[0], r[1]) for r in connection.execute("DESCRIBE incoming").fetchall()]
    if old_schema != new_schema:
        raise RuntimeError(f"{table} schema changed; an explicit full materialization/schema review is required")
    if connection.execute("SELECT COUNT(*) FROM incoming WHERE table_id IS NULL").fetchone()[0]:
        raise RuntimeError("Cannot reconcile source rows without table_id")
    if connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE table_id IS NULL').fetchone()[0]:
        raise RuntimeError("Existing source contains null table IDs")
    for name, relation in (("before", table), ("after", "incoming")):
        # Sort hashes within each table so row ordering is immaterial, while
        # repeated identical source observations retain their multiplicity.
        connection.execute(f'''CREATE OR REPLACE TEMP TABLE sync_{name} AS
            SELECT table_id, COUNT(*) AS n,
                sha256(string_agg(row_hash, '' ORDER BY row_hash)) AS fingerprint
            FROM (SELECT table_id, sha256(to_json(r)) AS row_hash FROM "{relation}" r)
            GROUP BY table_id''')
    connection.execute('''CREATE OR REPLACE TEMP TABLE sync_changed AS
        SELECT COALESCE(b.table_id, a.table_id) AS table_id,
            b.n AS old_n, a.n AS new_n
        FROM sync_before b FULL OUTER JOIN sync_after a USING (table_id)
        WHERE b.fingerprint IS DISTINCT FROM a.fingerprint OR b.n IS DISTINCT FROM a.n''')
    counts = connection.execute('''SELECT
        COUNT(*) FILTER (WHERE old_n IS NULL),
        COUNT(*) FILTER (WHERE new_n IS NULL),
        COUNT(*) FILTER (WHERE old_n IS NOT NULL AND new_n IS NOT NULL),
        COALESCE(SUM(old_n), 0), COALESCE(SUM(new_n), 0)
        FROM sync_changed''').fetchone()
    connection.execute(f'DELETE FROM "{table}" WHERE table_id IN (SELECT table_id FROM sync_changed)')
    connection.execute(f'INSERT INTO "{table}" SELECT * FROM incoming WHERE table_id IN (SELECT table_id FROM sync_changed)')
    expected = connection.execute("SELECT COALESCE(SUM(n), 0) FROM sync_after").fetchone()[0]
    actual = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    if actual != expected:
        raise RuntimeError(f"{table} reconciliation row count mismatch")
    return dict(zip(("added_tables", "deleted_tables", "corrected_tables", "replaced_rows", "inserted_rows"), map(int, counts)), rows=int(actual))


def reconcile(source_root, base_database, database_path, *, threads=2, memory_limit="2800MB", temp_directory=None):
    started = time.perf_counter()
    source_root, base_database, database_path = map(Path, (source_root, base_database, database_path))
    manifest = json.loads((source_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "ok":
        raise RuntimeError("Source manifest is not committed")
    if manifest.get("mode") == "source_sync":
        validate_files(source_root, manifest)
    if database_path.exists() or database_path.resolve() == base_database.resolve():
        raise FileExistsError("Reconciliation requires a new staging database")
    if not base_database.is_file():
        raise FileNotFoundError(base_database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    spill = temp_directory or database_path.parent / f"{database_path.stem}.sync-spill"
    Path(spill).mkdir(parents=True, exist_ok=True)
    # Copying the immutable parent preserves rollback and ensures failures cannot
    # leave partially updated source tables in the serving database.
    shutil.copy2(base_database, database_path)
    connection = None
    try:
        connection = _load_duckdb().connect(str(database_path))
        connection.execute(f"SET threads = {max(1, int(threads))}")
        connection.execute("SET memory_limit = ?", [memory_limit])
        connection.execute("SET temp_directory = ?", [str(spill)])
        connection.execute("SET preserve_insertion_order = false")
        connection.execute("BEGIN TRANSACTION")
        results = {}
        for family in ("full_sample", "logs"):
            results[f"source_{family}"] = reconcile_family(connection, f"source_{family}", (source_root / f"{family}-*.parquet").as_posix())
        connection.execute("COMMIT")
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None
    except Exception:
        if connection:
            connection.close()
        database_path.unlink(missing_ok=True)
        database_path.with_suffix(database_path.suffix + ".wal").unlink(missing_ok=True)
        raise
    report = {"status": "ok", "mode": "source_reconcile", "generation": manifest.get("generation"),
              "built_at": _utc_now(), "database": str(database_path), "base_database": str(base_database),
              "relations": results, "build_seconds": round(time.perf_counter() - started, 3)}
    database_path.with_suffix(".source.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("base_database", type=Path)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--memory-limit", default="2800MB")
    args = parser.parse_args()
    print(json.dumps(reconcile(args.source_root, args.base_database, args.database_path,
                               memory_limit=args.memory_limit), indent=2))


if __name__ == "__main__":
    main()
