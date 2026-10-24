"""Read-only validation for a reconciled Phase 5 DuckDB source staging file."""
from __future__ import annotations

import argparse
import json

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    args = parser.parse_args()
    connection = duckdb.connect(args.database, read_only=True)
    try:
        values = connection.execute(
            """SELECT
                (SELECT COUNT(*) FROM source_full_sample),
                (SELECT COUNT(*) FROM source_logs),
                (SELECT COUNT(DISTINCT table_id) FROM source_full_sample),
                (SELECT COUNT(DISTINCT table_id) FROM source_logs)
            """
        ).fetchone()
        result = dict(
            zip(
                (
                    "full_sample_rows",
                    "logs_rows",
                    "full_sample_tables",
                    "logs_tables",
                ),
                map(int, values),
            )
        )
        print(json.dumps(result, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
