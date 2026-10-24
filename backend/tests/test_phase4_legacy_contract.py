import unittest

from phase4_legacy_contract_audit import ROUTE_SNAPSHOTS, _request, _retired_fields
from phase3_duckdb_service import project_ordinary_ci_fields


class LegacyContractAuditTests(unittest.TestCase):
    def test_oracle_maps_broad_public_surface(self):
        self.assertGreaterEqual(len(ROUTE_SNAPSHOTS), 40)
        self.assertIn("cards/default", ROUTE_SNAPSHOTS)
        self.assertIn("mw_action_cards/synergies", ROUTE_SNAPSHOTS)

    def test_route_requests_are_default_mw_requests(self):
        request = _request("combinations/card_action_card")
        self.assertEqual(request["stats_page"], "combinations")
        self.assertEqual(request["combinations_view"], "card_action_card")
        self.assertEqual(request["is_mw"], 1)
        self.assertEqual(request["combination_min_plays"], 1)

    def test_only_additive_synergy_ci_contract_is_retired(self):
        retired = _retired_fields("combinations/card_map")
        self.assertIn("interaction_ci95_low", retired)
        self.assertNotIn("component_1_ci95_low", retired)
        self.assertEqual(_retired_fields("cards/default"), set())

    def test_ordinary_ci_projection_uses_student_t_margin(self):
        row = project_ordinary_ci_fields({
            "delta_ci_mean": 2.0,
            "delta_ci_sd": 4.0,
            "delta_ci_n": 16,
        })
        self.assertAlmostEqual(row["delta_ci95_low"], -0.131449545559323, places=10)
        self.assertAlmostEqual(row["delta_ci95_high"], 4.131449545559323, places=10)
        self.assertEqual(row["delta_ci95_n"], 16)

    def test_ordinary_ci_projection_does_not_invent_synergy_ci(self):
        row = project_ordinary_ci_fields({"interaction": 1.0})
        self.assertNotIn("interaction_ci95_low", row)


if __name__ == "__main__":
    unittest.main()
