#!/bin/bash
set +e
OUT=/home/ascri/phase5-diagnostic.txt
{
  echo "=== timestamps ==="
  date -u
  echo "=== versions ==="
  sha256sum /home/ascri/phase5_refresh_worker.py /home/ascri/phase5_refresh_workflow.py /home/ascri/phase2_local_vertical_slice.py 2>&1
  /usr/bin/python3 --version 2>&1
  /usr/bin/python3 -c 'import duckdb; print("duckdb", duckdb.__version__)' 2>&1
  echo "=== workflow imports ==="
  /usr/bin/python3 -c 'import sys; sys.path.insert(0,"/home/ascri"); import phase3_duckdb_service; print("phase3 import ok"); print(phase3_duckdb_service._load_duckdb().__version__)' 2>&1
  echo "=== builder imports ==="
  /usr/bin/python3 -c 'import importlib.util; s=importlib.util.spec_from_file_location("b","/home/ascri/phase2_local_vertical_slice.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print("builder import ok", hasattr(m,"run"))' 2>&1
  echo "=== files ==="
  find /home/ascri/phase2_private_data -maxdepth 3 -type f \( -name "*.duckdb" -o -name "*.wal" -o -name "*.json" \) -printf "%p %s bytes\n" 2>&1 | sort
  echo "=== service ==="
  systemctl status ark-nova-duckdb-refresh-worker.service --no-pager 2>&1
  echo "=== builder references ==="
  grep -n "card_pair_by_table\|card_pair_aggregate" /home/ascri/phase2_local_vertical_slice.py /home/ascri/phase5_refresh_workflow.py 2>&1
} > "$OUT" 2>&1
/usr/bin/gcloud storage cp --quiet "$OUT" "gs://ark-nova-stats-dashboard-cache/card-stats/refresh/diagnostics/manual.txt" || true
/usr/bin/systemctl poweroff || true
