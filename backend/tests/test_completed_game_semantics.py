import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
SOURCE = MAIN_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function_source(name):
    node = next(
        item for item in TREE.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


def literal_assignment(name):
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


class CompletedGameSemanticsTests(unittest.TestCase):
    def test_shared_predicate_requires_both_completion_signals(self):
        source = function_source("_completed_game_sql")
        self.assertIn("table_conceded", source)
        self.assertIn("end_game_triggered", source)
        self.assertIn("SAFE_CAST", source)
        self.assertIn("AND", source)

    def test_both_filter_builders_use_the_shared_predicate(self):
        self.assertIn(
            "_completed_game_sql()",
            function_source("_build_where_sql"),
        )
        self.assertIn(
            '_completed_game_sql("f")',
            function_source("_build_full_sample_where_sql"),
        )

    def test_prepared_sources_propagate_trigger_state(self):
        for function_name in (
            "_refresh_prepared_logs_table",
            "_refresh_prepared_full_stats_table",
            "_refresh_prepared_players_table",
            "_refresh_prepared_card_plays_table",
            "_refresh_prepared_card_pairs_table",
            "_refresh_prepared_card_play_aggregates_table",
            "_refresh_prepared_card_pair_aggregates_table",
        ):
            self.assertIn(
                "end_game_triggered",
                function_source(function_name),
                function_name,
            )

    def test_specific_predictors_have_no_trigger_condition(self):
        conditions = literal_assignment("PREDICTOR_SPECIFIC_CONDITIONS")
        self.assertEqual(len(conditions), 19)
        self.assertNotIn("Triggered endgame", [row[0] for row in conditions])
        self.assertNotIn("triggered_endgame", [row[1] for row in conditions])
        self.assertNotIn("Triggered_end_of_game", SOURCE)
        self.assertIn(
            '_completed_game_sql("f")',
            function_source("_build_predictors_specific_query"),
        )

    def test_no_direct_concession_only_sql_remains(self):
        # The literal belongs only inside the canonical shared predicate.
        self.assertEqual(SOURCE.count("table_conceded, 0) = 0"), 1)


if __name__ == "__main__":
    unittest.main()
