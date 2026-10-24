import duckdb
import json
import os
import re
import sys

database = sys.argv[1]
connection = duckdb.connect(database, read_only=True)
try:
    tables = [row[0] for row in connection.execute("SHOW TABLES").fetchall()]
    sizes = connection.execute(
        "SELECT table_name, estimated_size FROM duckdb_tables() "
        "ORDER BY estimated_size DESC"
    ).fetchall()
    columns = {
        table: [row[0] for row in connection.execute(f"DESCRIBE {table}").fetchall()]
        for table in ("source_full_sample", "source_logs")
    }
    code = "".join(
        open(path, encoding="utf-8").read()
        for path in sys.argv[2:]
        if os.path.isfile(path)
    )
    identifiers = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
    referenced = {table: [name for name in names if name in identifiers] for table, names in columns.items()}
    print(json.dumps({"database": database, "size": os.path.getsize(database), "tables": tables, "estimated_sizes": sizes, "columns": columns, "referenced_source_names": referenced}, default=str))
finally:
    connection.close()
