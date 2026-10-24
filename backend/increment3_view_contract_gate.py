"""Fail closed unless the repaired Cards, Opening Hand, and Players contracts hold."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT.parent / "ark-nova-stats-dashboard"


def _static_failures() -> list[str]:
    failures: list[str] = []
    service = (ROOT / "phase3_duckdb_service.py").read_text(encoding="utf-8")
    routes = (ROOT / "phase4_local_routes.py").read_text(encoding="utf-8")
    gateway = (ROOT / "cloudrun-duckdb-gateway" / "gateway.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "EXCLUDED_SUMMARY_PROJECTS",
        "round_filter_active",
        "PUBLIC_CONTRACT_SCHEMA_VERSION = 4",
        "_project_players_general",
        "_project_players_comparison",
        "_project_players_performance",
        "_project_players_history",
    ):
        if token not in service:
            failures.append(f"serving contract omits {token}")
    for token in (
        "FROM opening_hand_narrow",
        "FROM opening WHERE kept",
        "PLAYERS_METRICS",
    ):
        if token not in routes:
            failures.append(f"route contract omits {token}")
    if "post_match_elo" not in service:
        failures.append("serving contract omits graph-only post_match_elo")
    for token in ("MAX_REQUEST_BODY", "MAX_RESPONSE_BODY"):
        if token not in gateway:
            failures.append(f"gateway omits {token}")
    if "MAX_BODY" in gateway:
        failures.append("gateway still uses one shared body limit")

    for relative in ("assets/js/pages/cards.js", "assets/js/pages/opening-hand.js"):
        path = FRONTEND / relative
        if not path.exists():
            failures.append(f"missing frontend module: {relative}")
            continue
        source = path.read_text(encoding="utf-8")
        for token in ("statsRequestToken", "statsAbortController", ".abort()"):
            if token not in source:
                failures.append(f"{relative} lacks stale-request guard {token}")
    return failures


def _syntax_failures() -> list[str]:
    failures: list[str] = []
    for relative in (
        "assets/js/pages/cards.js",
        "assets/js/pages/opening-hand.js",
        "assets/js/pages/players.js",
    ):
        completed = subprocess.run(
            ["node", "--check", str(FRONTEND / relative)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            failures.append(f"JavaScript syntax failed for {relative}: {detail}")
    return failures


def main() -> int:
    failures = _static_failures() + _syntax_failures()
    package = ROOT / "phase2_private_data" / "python314"
    if package.exists():
        sys.path.insert(0, str(package))
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for name in (
        "tests.test_increment3_contracts",
        "tests.test_phase4_local_scope",
        "tests.test_phase2_builder_smoke",
    ):
        suite.addTests(loader.loadTestsFromName(name))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        failures.append("Increment 3 focused tests failed")
    if failures:
        print("Increment 3 view contracts: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Increment 3 view contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
