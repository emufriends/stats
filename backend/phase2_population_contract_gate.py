"""Fail closed unless Increment 2's canonical population contract is intact."""

from __future__ import annotations

import sys
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIRED_EVENT_RELATIONS = {
    "card_play_event_narrow",
    "opening_hand_narrow",
    "endgame_score_event_narrow",
    "mw_action_card_eligible_tables_narrow",
    "mw_action_card_selection_narrow",
}


def _static_failures() -> list[str]:
    failures: list[str] = []
    builder = (ROOT / "phase2_local_vertical_slice.py").read_text(encoding="utf-8")
    routes = (ROOT / "phase4_local_routes.py").read_text(encoding="utf-8")
    service = (ROOT / "phase3_duckdb_service.py").read_text(encoding="utf-8")
    workflow = (ROOT / "phase5_refresh_workflow.py").read_text(encoding="utf-8")
    for relation in sorted(REQUIRED_EVENT_RELATIONS):
        if relation not in builder or relation not in workflow:
            failures.append(f"missing refresh-owned relation: {relation}")
    for token in (
        "opponent_pre_match_elo", "is_corrupted_game", "is_completed_game",
        "starting_position", "player_identity", "arena_season", "is_tournament",
    ):
        if token not in builder:
            failures.append(f"canonical player fact omits {token}")
    if re.search(r"(?<!prepared_)\bsource_full_sample\b", routes):
        failures.append("a page route still bypasses prepared_full_sample_narrow")
    if re.search(r"(?<!prepared_)\bsource_full_sample\b", service):
        failures.append("the serving adapter still bypasses prepared_full_sample_narrow")
    if workflow.index("materialize_metadata_tables(connection") > workflow.index("builder.run"):
        failures.append("Arena/tournament metadata is still materialized after the builder")
    if 'request.get("players_history") is True' not in service:
        failures.append("Players selection can still be misrouted to history")
    # The migration requires at least its original invalidation; later cache
    # versions are valid and must not fail this gate merely for being newer.
    cache_version = re.search(r"^RESPONSE_CACHE_SCHEMA_VERSION\s*=\s*(\d+)\s*$", service, re.M)
    if cache_version is None or int(cache_version[1]) < 8:
        failures.append("response-cache schema was not invalidated")
    return failures


def main() -> int:
    failures = _static_failures()
    package = ROOT / "phase2_private_data" / "python314"
    if package.exists():
        sys.path.insert(0, str(package))
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for name in (
        "tests.test_migration_contract_foundation",
        "tests.test_phase2_canonical_population",
        "tests.test_phase2_builder_smoke",
        "tests.test_phase4_local_scope",
    ):
        suite.addTests(loader.loadTestsFromName(name))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        failures.append("Increment 2 focused tests failed")
    if failures:
        print("Increment 2 population contract: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Increment 2 population contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
