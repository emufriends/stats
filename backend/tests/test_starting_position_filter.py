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


class StartingPositionFilterTests(unittest.TestCase):
    def test_prepared_full_sample_normalizes_starting_position(self):
        source = function_source("_refresh_prepared_full_stats_table")
        self.assertIn("Starting_position_in_first_round", source)
        self.assertIn("WHEN 'first player' THEN 'First player'", source)
        self.assertIn("WHEN 'second player' THEN 'Second player'", source)
        self.assertIn("END AS starting_position", source)

    def test_all_shared_filter_builders_accept_starting_positions(self):
        for name in (
            "_build_where_sql",
            "_build_maps_metrics_where_sql",
            "_build_full_sample_where_sql",
        ):
            source = function_source(name)
            self.assertIn("starting_positions=None", source)
            self.assertIn('"starting_positions", "STRING"', source)
            self.assertIn("IN UNNEST(@starting_positions)", source)

    def test_players_history_filters_before_ordering_and_last_x(self):
        source = function_source("_query_players_history")
        predicate = source.index("f.starting_position IN UNNEST(@starting_positions)")
        newest = source.index("newest AS")
        self.assertLess(predicate, newest)

    def test_records_payload_exposes_starting_position(self):
        query_source = function_source("_build_records_query")
        handler_source = function_source("_query_card_stats")
        self.assertIn("AS starting_position", query_source)
        self.assertIn('"starting_position": getattr(row, "starting_position", None)', handler_source)

    def test_request_parser_rejects_empty_and_unknown_positions(self):
        source = function_source("get_card_stats")
        self.assertIn("starting_positions must be a non-empty array", source)
        self.assertIn("starting_positions contains an invalid value", source)
        self.assertIn('{"First player", "Second player"}', source)

    def test_mw_draft_uses_fixed_starting_position_orientation(self):
        prepared = function_source("_refresh_prepared_mw_action_card_tables")
        query = function_source("_build_mw_action_cards_query")
        self.assertIn("IF(starting_position = 'First player', 1, 2)", prepared)
        self.assertIn('starting_positions == ["First player"]', query)
        self.assertIn('starting_positions == ["Second player"]', query)

    def test_predictor_comparisons_filter_only_the_focal_row(self):
        source = function_source("_build_predictors_query")
        self.assertIn(
            'where_sql.replace(\n            "f.starting_position IN UNNEST(@starting_positions)"',
            source,
        )
        self.assertIn(
            "WHERE me.starting_position IN UNNEST(@starting_positions)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
