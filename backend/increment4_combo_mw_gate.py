"""Fail closed unless the repaired Combos and MW Action Cards contracts hold."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT.parent / "ark-nova-stats-dashboard"


def _static_failures() -> list[str]:
    failures: list[str] = []
    builder = (ROOT / "phase2_local_vertical_slice.py").read_text(encoding="utf-8")
    contracts = (ROOT / "phase4_combo_mw_contracts.py").read_text(encoding="utf-8")
    service = (ROOT / "phase3_duckdb_service.py").read_text(encoding="utf-8")
    snapshots = (ROOT / "phase5_snapshot_builder.py").read_text(encoding="utf-8")
    for token in (
        "mw_action_card_catalog_narrow", "mw_action_card_draft_narrow",
        "mw_action_card_pair_narrow", "SELECT is_mw, card_name",
    ):
        if token not in builder:
            failures.append(f"prepared builder omits {token}")
    for token in (
        "def combination_sql", "def mw_action_cards_sql", "def component_ci_sql",
        "table_cluster_delta", "Card + Action Card is only available",
    ):
        if token not in contracts:
            failures.append(f"route contracts omit {token}")
    if "interaction_ci95_low" in contracts or "interaction_ci95_high" in contracts:
        failures.append("additive Synergy intervals were reintroduced")
    for token in (
        "PUBLIC_CONTRACT_SCHEMA_VERSION = 4", "_project_combination_rows",
        "combination_paged", "component_ci_rows",
    ):
        if token not in service:
            failures.append(f"serving contract omits {token}")
    for token in ("_attach_component_cis", '(page, view) == ("combinations", "card_action_card")'):
        if token not in snapshots:
            failures.append(f"snapshot contract omits {token}")
    return failures


def _syntax_failures() -> list[str]:
    failures = []
    for relative in ("assets/js/pages/combos.js", "assets/js/pages/mw-action-cards.js"):
        result = subprocess.run(
            ["node", "--check", str(FRONTEND / relative)], capture_output=True,
            text=True, check=False,
        )
        if result.returncode:
            failures.append(f"JavaScript syntax failed for {relative}: {(result.stderr or result.stdout).strip()}")
    return failures


def main() -> int:
    package = ROOT / "phase2_private_data" / "python314"
    if package.exists():
        sys.path.insert(0, str(package))
    failures = _static_failures() + _syntax_failures()
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for name in (
        "tests.test_increment4_contracts",
        "tests.test_phase2_builder_smoke",
        "tests.test_phase4_legacy_contract",
    ):
        suite.addTests(loader.loadTestsFromName(name))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        failures.append("Increment 4 focused tests failed")
    if failures:
        print("Increment 4 Combos/MW contracts: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Increment 4 Combos/MW contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
