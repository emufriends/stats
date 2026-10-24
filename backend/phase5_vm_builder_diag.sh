#!/bin/bash
set +e
OUT=/home/ascri/phase5-builder-diagnostic.txt
DB=/home/ascri/phase2_private_data/staging/phase5-refresh-20260921-102633-phase5.duckdb
{
  date -u
  /usr/bin/python3 -c 'import duckdb; print("duckdb", duckdb.__version__)'
  /usr/bin/python3 - <<'PY'
import importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location("builder", "/home/ascri/phase2_local_vertical_slice.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("builder loaded")
status = module.run(
    Path("/home/ascri/phase2_private_data/staging/phase5-refresh-20260921-102633-phase5.duckdb"),
    Path("/home/ascri/phase2_private_data/worker/builder-diagnostic.json"),
    threads=2,
    memory_limit="2800MB",
    temp_directory=Path("/home/ascri/phase2_private_data/worker/builder-diagnostic-spill"),
)
print("builder status", status)
PY
} > "$OUT" 2>&1
/usr/bin/gcloud storage cp --quiet "$OUT" "gs://ark-nova-stats-dashboard-cache/card-stats/refresh/diagnostics/builder-direct.txt" || true
/usr/bin/systemctl poweroff || true
