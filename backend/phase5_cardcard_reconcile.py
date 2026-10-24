"""Run the fail-closed independent Card+Card check without modifying a generation."""

from __future__ import annotations

import json
import sys

from phase5_card_reference_check import reconcile


def main(path: str) -> int:
    result = reconcile(path)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'pass' else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
