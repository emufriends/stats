#!/bin/bash
set -eu

OUT="/tmp/phase5-partial-inventory.txt"
/usr/bin/systemctl disable --now ark-nova-duckdb-refresh-worker.service || true
DB=$(/usr/bin/find /home/ascri/phase2_private_data/staging -maxdepth 1 -name '*.duckdb' -printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)
{
  echo "db=$DB"
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "duckdb_files="
  /usr/bin/find /home/ascri/phase2_private_data -iname '*duckdb*' -o -iname '*duckdb_cli*' 2>&1 || true
  echo "service_environment="
  /usr/bin/systemctl show ark-nova-duckdb-api.service --property=Environment --no-pager 2>&1 || true
  echo "service_definition="
  /usr/bin/systemctl cat ark-nova-duckdb-api.service 2>&1 || true
  echo "python_duckdb="
  /usr/bin/python3 -c 'import duckdb; print(duckdb.__file__)' 2>&1 || true
  echo "python314_duckdb="
  /usr/bin/python3 -c 'import sys; sys.path.insert(0, "/home/ascri/phase2_private_data/python314"); import duckdb; print(duckdb.__file__)' 2>&1 || true
  echo "partial_db_header="
  /usr/bin/od -An -tx1 -N32 "$DB" 2>&1 || true
} > "$OUT"
/usr/bin/gcloud storage cp --quiet "$OUT" gs://ark-nova-stats-dashboard-cache/card-stats/refresh/partial-inventory.txt || true
/usr/bin/systemctl unmask ark-nova-duckdb-refresh-worker.service || true
/usr/bin/systemctl poweroff || true
