import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = ROOT / "phase2_private_data" / "python314"
if PYTHON.exists():
    sys.path.insert(0, str(PYTHON))

from phase2_local_vertical_slice import MW_ACTION_CARDS as BUILDER_CATALOG
from phase3_duckdb_service import Phase3RequestAdapter, _project_combination_rows
from phase4_combo_mw_contracts import MW_ACTION_CARDS, component_row_key
from phase5_snapshot_builder import _datasets


class Increment4ContractTests(unittest.TestCase):
    def test_authoritative_catalog_is_exactly_twenty_cards(self):
        self.assertEqual(BUILDER_CATALOG, MW_ACTION_CARDS)
        self.assertEqual(len(MW_ACTION_CARDS), 20)
        self.assertEqual([row[0] for row in MW_ACTION_CARDS], list(range(1, 21)))
        self.assertEqual({row[1] for row in MW_ACTION_CARDS}, {
            "Animals", "Association", "Build", "Cards", "Sponsors",
        })

    def test_card_card_normalization_retains_full_scope(self):
        normalized = Phase3RequestAdapter.normalize_request({
            "stats_page": "combinations", "combinations_view": "card_card",
            "is_mw": 0, "maps": ["1a"], "rounds": ["1", "6+"],
            "player_elo_min": 700, "opponent_elo_min": 300,
            "date_from": "2026-01-01", "combination_min_plays": 7,
        })
        self.assertEqual(normalized["is_mw"], 0)
        self.assertEqual(normalized["rounds"], ["1", "6+"])
        self.assertEqual(normalized["player_elo_min"], 700)
        self.assertEqual(normalized["opponent_elo_min"], 300)
        self.assertEqual(normalized["combination_min_plays"], 7)

    def test_component_keys_are_projection_invariant(self):
        forward = component_row_key("combinations", "card_card", {
            "card_1": "A", "card_2": "B",
        })
        self.assertEqual(forward, '["A","B"]')
        self.assertNotEqual(forward, component_row_key("combinations", "card_card", {
            "card_1": "B", "card_2": "A",
        }))

    def test_server_controls_do_not_recalculate_ranks_or_ranges(self):
        rows = [
            {"card_1": "A", "card_2": "B", "pair_type": "animal + sponsor", "interaction": 2.0, "n_played": 8, "avg_elo": 500},
            {"card_1": "A", "card_2": "C", "pair_type": "animal + project", "interaction": 1.0, "n_played": 10, "avg_elo": 600},
            {"card_1": "D", "card_2": "E", "pair_type": "animal + sponsor", "interaction": -1.0, "n_played": 2, "avg_elo": 700},
        ]
        page, extras = _project_combination_rows(rows, {
            "combination_min_plays": 5, "combination_sort": "interaction",
            "combination_sort_dir": "desc", "combination_paged": True,
            "combination_page": 1, "combination_page_size": 1,
            "combination_primary": "A", "combination_pair_types": [],
        }, "card_card")
        self.assertEqual(len(page), 1)
        self.assertEqual(page[0]["global_rank"], 1)
        self.assertEqual(extras["total_rows"], 2)
        self.assertEqual(extras["candidate_count_before_minimum"], 2)
        self.assertEqual(extras["combination_ranges"]["interaction"], {"min": -1.0, "max": 2.0})

    def test_card_card_frontend_type_labels_match_raw_duckdb_rows(self):
        rows = [
            {"card_1": "A", "type_1": "sponsor", "card_2": "B", "type_2": "animal",
             "pair_type": "sponsor + animal", "interaction": 1.0, "n_played": 8},
        ]
        page, extras = _project_combination_rows(rows, {
            "combination_min_plays": 1, "combination_sort": "interaction",
            "combination_sort_dir": "desc", "combination_paged": True,
            "combination_page": 1, "combination_page_size": 50,
            "combination_pair_types": ["Animal + Sponsor"],
        }, "card_card")
        self.assertEqual(extras["total_rows"], 1)
        self.assertEqual(page[0]["pair_type"], "Animal + Sponsor")

    def test_card_action_frontend_type_labels_match_raw_duckdb_rows(self):
        rows = [
            {"card_name": "A", "action_card_key": "Animals 1",
             "pair_type": "animal + Animals", "interaction": 1.0, "n_played": 8},
        ]
        page, extras = _project_combination_rows(rows, {
            "combination_min_plays": 1, "combination_sort": "interaction",
            "combination_sort_dir": "desc", "combination_paged": True,
            "combination_page": 1, "combination_page_size": 50,
            "combination_pair_types": ["Animal + Animals"],
        }, "card_action_card")
        self.assertEqual(extras["total_rows"], 1)
        self.assertEqual(page[0]["pair_type"], "Animal + Animals")

    def test_action_card_snapshot_population_is_mw_only(self):
        self.assertEqual(_datasets("combinations"), [1, 0])
        # The builder's per-view override is source-inspected by this assertion.
        source = (ROOT / "phase5_snapshot_builder.py").read_text(encoding="utf-8")
        self.assertIn('(page, view) == ("combinations", "card_action_card")', source)

    def test_additive_synergy_ci_remains_absent(self):
        source = (ROOT / "phase4_combo_mw_contracts.py").read_text(encoding="utf-8")
        self.assertNotIn("interaction_ci95_low", source)
        self.assertNotIn("interaction_ci95_high", source)


if __name__ == "__main__":
    unittest.main()
