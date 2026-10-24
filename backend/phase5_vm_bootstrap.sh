#!/bin/bash
set -eu

DEPLOYMENT_ROOT="gs://ark-nova-stats-phase2-import-413312054512/phase5/deployments"
POINTER="/tmp/ark-nova-deployment-current.json"

# The VM image intentionally has no application Python packages. Install the
# pinned DuckDB wheel before either the immutable or legacy startup path.
if ! /usr/bin/python3 -c 'import duckdb' >/dev/null 2>&1; then
  if ! /usr/bin/python3 -m pip --version >/dev/null 2>&1; then
    /usr/bin/apt-get update -y
    /usr/bin/apt-get install -y python3-pip
  fi
  /usr/bin/python3 -m pip install --user --break-system-packages --no-cache-dir 'duckdb==1.5.5'
fi

# The refresh publisher uses one authenticated, persistent Storage SDK session.
# Serving still only needs DuckDB. Startup runs as root, but the worker runs as
# ascri; install/check in that user's Python environment, not root's .local.
if ! /usr/sbin/runuser -u ascri -- /usr/bin/python3 -c 'from google.cloud import storage' >/dev/null 2>&1; then
  if ! /usr/bin/python3 -m pip --version >/dev/null 2>&1; then
    /usr/bin/apt-get update -y
    /usr/bin/apt-get install -y python3-pip
  fi
  /usr/sbin/runuser -u ascri -- /usr/bin/python3 -m pip install --user --break-system-packages --no-cache-dir 'google-cloud-storage==2.19.0'
fi

# New hosts and code updates use one immutable, checksum-verified bundle. The
# pointer is published only after its archive and descriptor exist. Keep the
# legacy per-file fallback below solely for hosts booting before the first
# deployment bundle has been published.
if /usr/bin/gcloud storage cp --quiet "$DEPLOYMENT_ROOT/current.json" "$POINTER"; then
  VERSION=$(/usr/bin/python3 -c 'import json; print(json.load(open("/tmp/ark-nova-deployment-current.json"))["version"])')
  /usr/bin/gcloud storage cp --quiet "$DEPLOYMENT_ROOT/$VERSION.tar.gz" "/tmp/$VERSION.tar.gz"
  /usr/bin/gcloud storage cp --quiet "$DEPLOYMENT_ROOT/$VERSION.json" "/tmp/$VERSION.json"
  /usr/bin/gcloud storage cp --quiet "$DEPLOYMENT_ROOT/installer.py" "/tmp/phase5_install_deployment.py"
  /usr/bin/python3 /tmp/phase5_install_deployment.py --root /home/ascri \
    --archive "/tmp/$VERSION.tar.gz" --descriptor "/tmp/$VERSION.json" --restart
  exit 0
fi

WORKER_URI="gs://ark-nova-stats-phase2-import-413312054512/phase5/worker/phase5_refresh_worker.py"
WORKER_PATH="/home/ascri/phase5_refresh_worker.py"
WORKFLOW_URI="gs://ark-nova-stats-phase2-import-413312054512/phase5/worker/phase5_refresh_workflow.py"
WORKFLOW_PATH="/home/ascri/phase5_refresh_workflow.py"
BUILDER_URI="gs://ark-nova-stats-phase2-import-413312054512/phase5/worker/phase2_local_vertical_slice.py"
BUILDER_PATH="/home/ascri/phase2_local_vertical_slice.py"

# Production serving keeps this VM online. The worker remains resident so it
# can accept the daily/manual refresh request without powering the VM off.
/usr/bin/install -d -m 0755 /etc/systemd/system/ark-nova-duckdb-refresh-worker.service.d
/usr/bin/printf '%s\n' '[Service]' 'Type=simple' 'TimeoutStartSec=0' \
  'Environment=DUCKDB_WORKER_KEEP_ALIVE=true' \
  > /etc/systemd/system/ark-nova-duckdb-refresh-worker.service.d/keep-alive.conf

# A killed workflow can leave only its VM-local advisory lock behind.  The
# durable Cloud Storage lock is the actual concurrency guard, and this VM is
# single-purpose, so clear the local stale marker before starting a new run.
/usr/bin/rm -f /home/ascri/phase2_private_data/refresh.lock

for attempt in $(seq 1 30); do
  if /usr/bin/gcloud storage cp --quiet "$WORKER_URI" "$WORKER_PATH" \
      && /usr/bin/gcloud storage cp --quiet "$WORKFLOW_URI" "$WORKFLOW_PATH" \
      && /usr/bin/gcloud storage cp --quiet "$BUILDER_URI" "$BUILDER_PATH"; then
    chmod 0755 "$WORKER_PATH"
    /usr/bin/systemctl daemon-reload
    /usr/bin/systemctl unmask ark-nova-duckdb-refresh-worker.service || true
    /usr/bin/systemctl enable --now ark-nova-duckdb-refresh-worker.service || true
    exit 0
  fi
  sleep 2
done
exit 1
