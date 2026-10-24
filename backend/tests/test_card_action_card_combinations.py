import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function_source(name):
    node = next(
        item for item in TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


class CardActionCardCombinationTests(unittest.TestCase):
    def test_view_is_registered_and_mw_only(self):
        self.assertIn('COMBINATIONS_VIEW_CARD_ACTION_CARD = "card_action_card"', SOURCE)
        handler = function_source("get_card_stats")
        self.assertIn("Card + Action Card is only available for Marine Worlds", handler)

    def test_prepared_join_pairs_played_cards_with_selected_action_cards(self):
        source = function_source("_refresh_prepared_mw_action_card_tables")
        self.assertIn("GROUP BY table_id, player, card_name", source)
        self.assertIn("a.table_id = n.table_id AND a.player = n.player", source)
        self.assertIn("played_rounds_json", source)
        self.assertIn("PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE", source)

    def test_query_uses_three_component_synergy_formula(self):
        source = function_source("_build_combinations_query")
        self.assertIn("COMBINATIONS_VIEW_CARD_ACTION_CARD", source)
        self.assertIn("c.individual_delta + a.individual_delta", source)
        self.assertIn("p.delta_actual - (c.individual_delta + a.individual_delta)", source)
        self.assertIn("PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE", source)

    def test_snapshot_pack_has_mw_asset_only(self):
        source = function_source("_default_snapshot_pack_blob_names")
        self.assertIn("combinations/card-action-card/default-mw.json", source)
        self.assertNotIn("combinations/card-action-card/default-base.json", source)


if __name__ == "__main__":
    unittest.main()
