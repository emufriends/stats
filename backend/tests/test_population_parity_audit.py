import pathlib
import unittest

import audit_population_parity as audit


class PopulationParityAuditTests(unittest.TestCase):
    def test_contract_inventory_covers_every_active_family(self):
        pages = {row[0] for row in audit.CONTRACTS}
        self.assertTrue({
            "home", "cards", "opening_hand", "endgames", "sponsor_endgames",
            "combinations", "actions", "predictors", "icons", "mw_action_cards",
            "build", "conservation", "scoring", "workers", "maps", "players",
            "arena", "records",
        }.issubset(pages))

    def test_pack_audit_rejects_old_point_version(self):
        path = "card-stats/combinations/card-card/default-mw.json"
        pack = {
            "data_version": "current",
            "snapshots": {
                path: {
                    "data_version": "old",
                },
            },
        }
        failures, _ = audit.audit_pack(pack)
        self.assertTrue(any("version mismatch" in failure for failure in failures))

    def test_display_audit_catches_action_component_drift(self):
        pack = {
            "snapshots": {
                "card-stats/mw-action-cards/general/default-mw.json": {
                    "data": [{"card_name": "Snap", "delta_picked": -0.809}],
                },
                "card-stats/mw-action-cards/synergies/default-mw.json": {
                    "data": [{
                        "card_1_name": "Snap", "delta_1": -0.802,
                        "card_2_name": "Money", "delta_2": 0.1,
                    }],
                },
                "card-stats/combinations/card-action-card/default-mw.json": {"data": []},
            },
        }
        failures, _ = audit.audit_display_parity(pack)
        self.assertTrue(any("Snap" in failure for failure in failures))

    def test_endgame_parity_uses_the_scored_shared_response_field(self):
        pack = {
            "snapshots": {
                "card-stats/default-mw.json": {"data": []},
                "card-stats/endgames/default-mw.json": {
                    "data": [{
                        "card_name": "Favorite Zoo",
                        "delta_played": -1.0,
                        "delta_in_hand": 0.5,
                    }],
                },
                "card-stats/combinations/card-endgame/default-mw.json": {
                    "data": [{
                        "card_name": "Test Card",
                        "delta_card": None,
                        "endgame_name": "Favorite Zoo",
                        "delta_endgame": 0.5,
                    }],
                },
                "card-stats/default-base.json": {"data": []},
                "card-stats/endgames/default-base.json": {"data": []},
            },
        }
        failures, _ = audit.audit_display_parity(pack)
        self.assertFalse(any("endgame component" in failure for failure in failures))

    def test_combo_component_baselines_use_the_cards_moment_population(self):
        source = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FROM `{PREPARED_CARD_MOMENTS_TABLE}`\n    WHERE moment = 'played'", source)
        self.assertIn("AND moment = 'played'", source)


if __name__ == "__main__":
    unittest.main()
