import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function_source(name):
    node = next(
        item for item in TREE.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


class PlayersHistoryMetricTests(unittest.TestCase):
    def test_reputation_actions_is_shared_by_maps_and_players(self):
        definitions = function_source("_maps_metric_definitions")
        expressions = function_source("_players_metric_expressions")
        groups = function_source("_players_history_groups")
        self.assertIn('"reputation_actions"', definitions)
        self.assertIn('"Reputation actions"', definitions)
        self.assertIn("Reputation_association_tasks", expressions)
        self.assertIn('"reputation_actions"', groups)

    def test_elo_is_graph_only_and_uses_post_match_rating(self):
        catalog = function_source("_players_history_metric_catalog")
        value_sql = function_source("_players_history_value_sql")
        history_query = function_source("_query_players_history")
        self.assertNotIn('"elo"', function_source("_players_metric_definitions"))
        self.assertIn('"elo"', catalog)
        self.assertIn("post_match_elo", value_sql)
        self.assertIn('"dataset_scope": "combined"', function_source("_players_history_cache_blob_name"))
        self.assertIn("all completion states", history_query)
        self.assertIn("len(metric_keys) == 1 and metric_keys[0] == \"elo\"", history_query)

    def test_elo_history_does_not_apply_standard_sidebar_predicates(self):
        source = function_source("_query_players_history")
        self.assertIn("if not elo_only:", source)
        self.assertIn("_completed_game_sql(\"f\")", source)
        self.assertIn("CAST(f.is_mw AS INT64) = @is_mw", source)

    def test_removed_predictor_conditions_are_not_generated(self):
        self.assertNotIn("round_1_humphead", SOURCE)
        self.assertNotIn("round_1_2_fur_seal", SOURCE)
        self.assertNotIn("Round 1: Humphead Wrasse", SOURCE)
        self.assertNotIn("Round 1/2: New Zealand Fur Seal", SOURCE)


if __name__ == "__main__":
    unittest.main()
