"""Validate the checked-in EUR billing rails and optional live inventory."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def verify(root: Path, live_inventory: Path | None = None) -> dict:
    policy = json.loads((root / "budget_policy.json").read_text(encoding="utf-8"))
    errors = []
    if policy.get("billing_currency") != "EUR":
        errors.append("billing policy must use the account's EUR currency")
    if float(policy.get("warning_budget_amount") or 0) != 20:
        errors.append("warning budget must be EUR 20")
    if float(policy.get("hard_stop_budget_amount") or 0) != 40:
        errors.append("hard-stop budget must be EUR 40")
    if policy.get("automatic_restart") is not False:
        errors.append("budget shutdown must not automatically restart the VM")
    inventory = None
    if live_inventory:
        inventory = json.loads(live_inventory.read_text(encoding="utf-8"))
        amounts = sorted(float(item.get("amount") or 0) for item in inventory.get("budgets", []))
        if 20.0 not in amounts or 40.0 not in amounts:
            errors.append("live inventory does not contain both EUR 20 and EUR 40 budgets")
        if not inventory.get("hard_stop_subscription"):
            errors.append("live inventory has no hard-stop Pub/Sub subscription")
    return {
        "status": "ok" if not errors else "failed",
        "policy": policy,
        "live_inventory_checked": live_inventory is not None,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--live-inventory", type=Path)
    args = parser.parse_args()
    result = verify(args.root.resolve(), args.live_inventory)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
