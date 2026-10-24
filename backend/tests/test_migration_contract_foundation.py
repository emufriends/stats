import hashlib
import json
import unittest
from pathlib import Path

from tests.contract_oracle import (
    canonical_opponent_elos,
    card_event_ev,
    opening_stats,
    unique_card_player_games,
    visible_table_ids,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "dashboard-routes.v1.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "migration-contract-fixture.v1.json"
REAL_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "migration-contract-real-sample.v1.json"
EVIDENCE_PATH = ROOT / "contracts" / "baseline-evidence.v1.json"
EXPECTED_ROUTE_IDS = {
    "home/default", "cards/default", "cards/component_ci", "opening_hand/default",
    "maps/metrics", "maps/tournament_h2h", "endgames/general",
    "endgames/cp_distribution", "endgames/cp_by_map", "sponsor_endgames/cp",
    "sponsor_endgames/appeal", "combinations/card_card", "combinations/card_map",
    "combinations/card_round", "combinations/card_endgame",
    "combinations/card_action_card", "predictors/general", "predictors/icon",
    "predictors/specific", "actions/starting_position", "actions/upgrades",
    "actions/upgrade_order", "actions/upgrades_by_map", "build/enclosures",
    "build/hexes", "icons/default", "conservation/projects",
    "conservation/project_rewards", "conservation/cp_rewards", "scoring/final_score",
    "scoring/appeal", "scoring/conservation_points", "scoring/reputation",
    "workers/general", "workers/two_cp_worker", "players/general",
    "players/comparison", "players/performance_by_map", "players/arena_top_100",
    "players/history", "arena/top_100", "records/elo_leaderboard",
    "records/fastest_games", "records/highest_scores", "records/biggest_turns",
    "records/most_icons", "mw_action_cards/general", "mw_action_cards/draft",
    "mw_action_cards/by_map", "mw_action_cards/synergies",
}


class MigrationContractFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.real_fixture = json.loads(REAL_FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    def test_contract_inventory_is_unique_and_complete(self):
        route_ids = [route["id"] for route in self.contract["routes"]]
        self.assertEqual(len(route_ids), 50)
        self.assertEqual(len(route_ids), len(set(route_ids)))
        self.assertEqual(set(route_ids), EXPECTED_ROUTE_IDS)

    def test_every_route_defines_population_and_output_contract(self):
        for route in self.contract["routes"]:
            with self.subTest(route=route["id"]):
                for field in ("dataset", "completion", "maps", "unit", "eligibility", "request_fields", "required_fields"):
                    self.assertIn(field, route)
                self.assertIsInstance(route["request_fields"], list)
                self.assertIsInstance(route["required_fields"], list)

    def test_current_product_decisions_are_explicit(self):
        text = "\n".join(self.contract["current_product_decisions"])
        for phrase in ("Reputation actions", "post_match_elo", "Synergy values", "Corrupted", "Card + Action Card", "General, Draft, By map"):
            self.assertIn(phrase, text)

    def test_canonical_opponent_elo_ignores_raw_legacy_field(self):
        self.assertEqual(canonical_opponent_elos(self.fixture), self.fixture["expected"]["canonical_opponent_elo"])

    def test_card_oracle_preserves_event_mean_and_distinct_count(self):
        expected = self.fixture["expected"]
        self.assertEqual(card_event_ev(self.fixture, "Test Animal"), expected["test_animal_play_event_ev"])
        self.assertEqual(unique_card_player_games(self.fixture, "Test Animal"), expected["test_animal_unique_player_game_count"])
        self.assertEqual(card_event_ev(self.fixture, "Test Animal", {1}), expected["test_animal_round_1_ev"])
        self.assertEqual(card_event_ev(self.fixture, "Test Animal", {2}), expected["test_animal_round_2_ev"])

    def test_opening_hand_oracle_is_dealt_and_kept_not_played(self):
        stats = opening_stats(self.fixture, "Test Animal")
        expected = self.fixture["expected"]
        self.assertEqual(stats["dealt_ev"], expected["test_animal_opening_dealt_ev"])
        self.assertEqual(stats["kept_ev"], expected["test_animal_opening_kept_ev"])
        self.assertEqual(stats["keep_rate_pct"], expected["test_animal_opening_keep_rate_pct"])

    def test_corrupted_game_exception_is_explicit(self):
        expected = self.fixture["expected"]
        self.assertEqual(visible_table_ids(self.fixture, home=False), expected["non_home_visible_table_ids"])
        self.assertEqual(visible_table_ids(self.fixture, home=True), expected["home_visible_table_ids"])

    def test_real_sample_has_two_complete_player_pairs(self):
        rows = self.real_fixture["games"]
        self.assertEqual(len(rows), self.real_fixture["expected_invariants"]["row_count"])
        by_table = {}
        for row in rows:
            by_table.setdefault(row["table_id"], []).append(row)
        self.assertEqual(len(by_table), self.real_fixture["expected_invariants"]["table_count"])
        self.assertTrue(all(len(group) == 2 for group in by_table.values()))
        for group in by_table.values():
            for row in group:
                opponent = next(other for other in group if other["player"] != row["player"])
                self.assertEqual(row["canonical_opponent_pre_match_elo"], opponent["pre_match_elo"])
                self.assertNotEqual(row["canonical_opponent_pre_match_elo"], row["raw_opponent_elo"])

    def test_real_sample_preserves_opening_and_excluded_card_evidence(self):
        logs = self.real_fixture["logs"]
        self.assertTrue(all(len(row["opening_cards"]) == 8 for row in logs))
        self.assertTrue(all(len(row["opening_keep"]) == 4 for row in logs))
        projects = {
            event["card"] for row in logs for event in row["played_cards"]
            if event["type"] == "project"
        }
        self.assertTrue(set(self.real_fixture["expected_invariants"]["excluded_summary_projects_seen_in_logs"]).issubset(projects))

    def test_baseline_evidence_is_pinned(self):
        self.assertEqual(self.evidence["legacy_frontend_revision"], "9cfe7cb")
        item = self.evidence["legacy_snapshot_pack"]
        digest = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest().upper()
        self.assertEqual(digest, item["sha256"])
        self.assertNotIn("reviewed_current_pack", self.evidence)


if __name__ == "__main__":
    unittest.main()
