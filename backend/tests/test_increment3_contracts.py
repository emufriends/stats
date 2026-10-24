import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]

from phase3_duckdb_service import (
    Phase3RequestAdapter,
    _project_players_comparison,
    _project_players_general,
    _project_players_history,
    _project_players_performance,
)
from phase4_local_routes import PLAYERS_METRICS, _next_opening_hand_sql


class Increment3ContractTests(unittest.TestCase):
    def test_players_catalog_is_not_maps_catalog(self):
        labels = [item[2] for item in PLAYERS_METRICS]
        self.assertEqual(labels[:3], ["Turns", "Breaks triggered", "Break%"])
        self.assertNotIn("Games", labels)
        self.assertNotIn("Rounds", labels)
        self.assertIn("Reputation actions", labels)

    def test_opening_hand_uses_dealt_and_kept_events(self):
        sql, _ = _next_opening_hand_sql({"is_mw": 1})
        self.assertIn("FROM opening_hand_narrow", sql)
        self.assertIn("FROM opening WHERE kept", sql)
        self.assertIn("COALESCE(k.n_kept, 0) AS n_played", sql)
        self.assertIn("COALESCE(d.n_dealt, 0) AS n_seen", sql)
        self.assertNotIn("card_in_hand_narrow", sql)

    def test_cards_round_mode_hides_context_and_preserves_play_events(self):
        normalized = Phase3RequestAdapter.normalize_request({
            "stats_page": "cards", "is_mw": 1, "rounds": ["2"],
        })
        sql, _ = Phase3RequestAdapter._cards_sql(normalized)
        self.assertIn("SELECT cp.table_id, cp.player", sql)
        self.assertNotIn("SELECT DISTINCT cp.table_id", sql)
        self.assertIn("CAST(NULL AS DOUBLE) AS delta_in_hand", sql)
        self.assertIn("CAST(NULL AS BIGINT) AS n_seen", sql)
        for excluded in ("africa", "birds", "species diversity"):
            self.assertIn(f"'{excluded}'", sql)

    def test_general_projection_restores_counts_and_removes_internal_metadata(self):
        rows = [{
            "sort_order": 1, "metric": "Turns",
            "player_identity": "merge:alias-and-other", "account_counts": [
                {"name": "Alias", "game_count": 3},
            ],
        }]
        data, extras = _project_players_general(rows, {"players_player": "Alias"})
        self.assertNotIn("account_counts", data[0])
        self.assertNotIn("player_identity", data[0])
        self.assertEqual(extras["player_game_count"], 3)
        self.assertEqual(extras["player_selected_game_count"], 3)
        self.assertEqual(extras["player_associated_game_count"], 0)
        # A filter can leave only one exact alias in scope; merged status is
        # still defined by the global identity relation.
        self.assertTrue(extras["player_is_merged"])

    def test_comparison_projection_matches_frontend_matrix(self):
        base = {
            "sort_order": 1, "metric": "Turns", "tooltip": None,
            "is_default": True, "format": "number", "lower_is_better": True,
        }
        rows = [
            {**base, "position": 0, "player": "A", "player_identity": "player:A",
             "value": 30, "tooltip_value": None, "game_count": 4,
             "account_counts": [{"name": "A", "game_count": 4}]},
            {**base, "position": 1, "player": "B", "player_identity": "player:B",
             "value": 31, "tooltip_value": None, "game_count": 5,
             "account_counts": [{"name": "B", "game_count": 5}]},
        ]
        data, extras = _project_players_comparison(
            rows, {"players_players": ["A", "B"]}
        )
        self.assertEqual(len(data), 1)
        self.assertEqual([item["player"] for item in data[0]["values"]], ["A", "B"])
        self.assertEqual([item["game_count"] for item in extras["players"]], [4, 5])

    def test_performance_projection_pivots_maps_and_attaches_ci(self):
        rows = [{
            "sort_order": 0, "player": "A",
            "map_name": "Map 1a: Observation Tower", "value": 0.5,
            "ci_mean": 0.5, "ci_sd": 1.0, "ci_n": 100,
        }]
        data, _ = _project_players_performance(rows, {"players_players": ["A"]})
        self.assertEqual(data[0]["map_1a"], 0.5)
        self.assertEqual(data[0]["map_1a_ci95_n"], 100)
        # Ordinary mean intervals use the finite-sample Student-t critical
        # value (99 degrees of freedom here), not the asymptotic 1.96 value.
        self.assertAlmostEqual(data[0]["map_1a_ci95_low"], 0.30157830484135867)
        self.assertAlmostEqual(data[0]["map_1a_ci95_high"], 0.6984216951586413)

    def test_history_comparison_request_and_envelope(self):
        normalized = Phase3RequestAdapter.normalize_request({
            "stats_page": "players", "players_view": "comparison",
            "players_history": True, "players_players": ["A", "B"],
            "players_history_metrics": ["reputation_actions"], "is_mw": 1,
        })
        self.assertEqual(normalized["history_aliases"], ["A", "B"])
        rows = []
        for alias in ("A", "B"):
            for number in range(100, 251):
                rows.append({
                    "requested_player": alias, "game_number": number,
                    "game_count": 250, "game_ended_at": f"2026-01-{(number % 28) + 1:02d}",
                    "reputation_actions": number / 100,
                })
        payload = _project_players_history(rows, normalized)
        self.assertTrue(payload["players_history"])
        self.assertEqual(payload["metrics"][0]["group"], "association_bonuses")
        self.assertEqual([item["name"] for item in payload["players"]], ["A", "B"])

    def test_gateway_has_separate_request_and_response_limits(self):
        source = (ROOT / "cloudrun-duckdb-gateway" / "gateway.py").read_text(encoding="utf-8")
        self.assertIn("MAX_REQUEST_BODY", source)
        self.assertIn("MAX_RESPONSE_BODY", source)
        self.assertNotIn("payload = response.read(MAX_BODY + 1)", source)


if __name__ == "__main__":
    unittest.main()
