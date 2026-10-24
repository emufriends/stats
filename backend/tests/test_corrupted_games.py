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
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


def classified(game_result, turns, *components):
    values = (turns, *components)
    return (
        game_result == 2
        and all(value is not None for value in values)
        and turns - sum(components) >= 2
    )


class CorruptedGameTests(unittest.TestCase):
    def test_boundary_and_loser_semantics(self):
        self.assertTrue(classified(2, 20, 3, 3, 3, 3, 3, 3))
        self.assertFalse(classified(2, 20, 4, 3, 3, 3, 3, 3))
        self.assertFalse(classified(1, 20, 0, 0, 0, 0, 0, 0))
        self.assertFalse(classified(2, 20, 3, 3, 3, 3, 3, None))

    def test_sql_predicate_requires_all_source_values(self):
        source = function_source("_corrupted_loser_sql")
        for field in (
            "Number_of_turns", "Animals_actions", "Association_actions",
            "Build_actions", "Cards_actions", "Sponsors_actions",
            "X_Tokens_gained_instead_of_action",
        ):
            self.assertIn(field, source)
        self.assertIn("Game_result", source)
        self.assertIn(">= 2", source)
        self.assertIn("IS NOT NULL", source)
        self.assertNotIn("COALESCE", source)

    def test_flag_is_table_wide_and_propagated_to_logs(self):
        prepared = function_source("_refresh_prepared_full_stats_table")
        self.assertIn("corrupted_tables AS", prepared)
        self.assertIn('WHERE {_corrupted_loser_sql("f")}', prepared)
        self.assertIn("corrupted.table_id IS NOT NULL AS is_corrupted_game", prepared)
        self.assertIn("LEFT JOIN corrupted_tables corrupted", prepared)
        self.assertIn("f.is_corrupted_game", function_source("_refresh_prepared_logs_table"))

    def test_home_is_the_only_game_population_without_exclusion(self):
        self.assertNotIn(
            "_non_corrupted_game_sql",
            function_source("_refresh_prepared_home_observations_table"),
        )
        self.assertNotIn(
            "_non_corrupted_game_sql",
            function_source("_build_home_stats_query"),
        )
        for name in (
            "_refresh_prepared_players_table",
            "_refresh_prepared_card_plays_table",
            "_refresh_prepared_endgame_events_table",
            "_refresh_prepared_mw_action_card_tables",
            "_build_maps_tournament_h2h_query",
            "_build_records_query",
        ):
            self.assertIn("_non_corrupted_game_sql", function_source(name), name)

    def test_tournament_h2h_uses_prepared_full_sample(self):
        source = function_source("_build_maps_tournament_h2h_query")
        self.assertIn("PREPARED_FULL_STATS_TABLE", source)
        self.assertNotIn("all_games_stat", source)


if __name__ == "__main__":
    unittest.main()
