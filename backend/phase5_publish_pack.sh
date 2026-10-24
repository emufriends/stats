#!/bin/bash
set -eu

ROOT=${ARK_ROOT:-/home/ascri}
GENERATION=${1:?usage: phase5_publish_pack.sh GENERATION [RUN_ID]}
RUN_ID=${2:-}

ARGS=("$ROOT/phase5_publish_release.py" "$GENERATION" --root "$ROOT")
if [ -n "$RUN_ID" ]; then
  ARGS+=(--run-id "$RUN_ID")
fi

exec /usr/bin/python3 "${ARGS[@]}"
