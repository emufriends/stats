#!/bin/bash
set -eu

OUT="/tmp/phase5-timeout-inventory.txt"
/usr/bin/systemctl stop ark-nova-duckdb-refresh-worker.service || true
/usr/bin/systemctl mask ark-nova-duckdb-refresh-worker.service || true
{
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "hostname=$(hostname)"
  echo "disk="
  /bin/df -h /
  echo "private_sizes="
  /usr/bin/du -sh /home/ascri/phase2_private_data/* 2>&1 || true
  echo "staging_files="
  /usr/bin/find /home/ascri/phase2_private_data/staging -maxdepth 1 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %p\\n' 2>&1 || true
  echo "generation_files="
  /usr/bin/find /home/ascri/phase2_private_data/generations -maxdepth 1 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %p\\n' 2>&1 || true
  echo "snapshot_files="
  /usr/bin/find /home/ascri/phase2_private_data/snapshots -maxdepth 2 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %p\\n' 2>&1 || true
} > "$OUT"
/usr/bin/gcloud storage cp --quiet "$OUT" gs://ark-nova-stats-dashboard-cache/card-stats/refresh/timeout-inventory.txt || true
/usr/bin/systemctl unmask ark-nova-duckdb-refresh-worker.service || true
/usr/bin/systemctl poweroff || true
