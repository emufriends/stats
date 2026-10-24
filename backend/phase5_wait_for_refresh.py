"""Wait for one already-queued private refresh to finish.

This helper lets the Increment 7 mixed-workload gate attach to the authenticated
Scheduler/worker refresh rather than creating a second request.  It reads only
the sanitized public status object and exits non-zero if that exact run fails,
is replaced, or exceeds the requested timeout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time


def read_status(uri: str) -> dict:
    result = subprocess.run(
        ["gcloud", "storage", "cat", uri],
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode:
        return {}
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument(
        "--status-uri",
        default="gs://ark-nova-stats-dashboard-cache/card-stats/refresh/status.json",
    )
    parser.add_argument("--timeout", type=int, default=3 * 60 * 60)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        status = read_status(args.status_uri)
        if status.get("run_id") == args.run_id:
            state = status.get("state")
            if state == "succeeded":
                print(json.dumps({
                    "status": "ok", "run_id": args.run_id,
                    "completed_data_version": status.get("completed_data_version"),
                }))
                return 0
            if state == "failed":
                print(json.dumps({"status": "failed", "run_id": args.run_id}))
                return 1
        elif status.get("run_id") and status.get("state") in {"running", "succeeded", "failed"}:
            print(json.dumps({
                "status": "replaced", "expected_run_id": args.run_id,
                "observed_run_id": status.get("run_id"),
            }))
            return 1
        time.sleep(args.interval)
    print(json.dumps({"status": "timeout", "run_id": args.run_id}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
