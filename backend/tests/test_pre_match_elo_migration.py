import ast
import math
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


class PreMatchEloMigrationTests(unittest.TestCase):
    def test_prepared_boundary_derives_unique_opponent_pre_match_elo(self):
        source = function_source("_refresh_prepared_full_stats_table")
        self.assertIn("f.* EXCEPT(elo, opponent_elo, end_game_triggered)", source)
        self.assertIn("COUNT(DISTINCT opponent.player) = 1", source)
        self.assertIn("ANY_VALUE(opponent.pre_match_elo)", source)
        self.assertIn("CAST(NULL AS FLOAT64)", source)

    def test_every_shared_filter_builder_uses_canonical_fields(self):
        for name in (
            "_build_where_sql",
            "_build_maps_metrics_where_sql",
            "_build_full_sample_where_sql",
        ):
            source = function_source(name)
            self.assertIn("pre_match_elo", source, name)
            self.assertIn("opponent_pre_match_elo", source, name)

    def test_crossing_the_threshold_cannot_leave_only_the_loser(self):
        # Winner starts below 300 and finishes above it; loser starts above 300.
        # Canonical filtering compares both pre-game ratings in both directions,
        # so neither row qualifies for a 300+/300+ population.
        winner = {"pre": 295.0, "post": 305.0}
        loser = {"pre": 310.0, "post": 300.0}
        canonical = [
            winner["pre"] >= 300 and loser["pre"] >= 300,
            loser["pre"] >= 300 and winner["pre"] >= 300,
        ]
        legacy = [
            winner["pre"] >= 300 and loser["post"] >= 300,
            loser["pre"] >= 300 and winner["post"] >= 300,
        ]
        self.assertEqual(canonical, [False, False])
        self.assertEqual(legacy, [False, True])

    def test_arena_peak_and_history_remain_post_match(self):
        source = function_source("_arena_top100_season_payload")
        self.assertIn("MAX(post_match_arena_rating) AS peak", source)
        self.assertIn("post_match_arena_rating AS rating", source)
        self.assertIn("AVG(opponent_pre_match_elo)", source)

    def test_sheet_peak_elo_contract_is_unchanged(self):
        source = function_source("_parse_records_elo_leaderboard_sheet")
        self.assertIn('5: {"peak elo"}', source)
        self.assertNotIn("peak pre_match_elo", source)

    def test_peak_arena_n_a_is_a_valid_missing_value(self):
        namespace = {"math": math}
        exec(function_source("_records_sheet_float"), namespace)
        parse_float = namespace["_records_sheet_float"]
        self.assertIsNone(parse_float("n/a", "Peak Arena", 284, allow_na=True))
        with self.assertRaises(ValueError):
            parse_float("n/a", "Peak Elo", 284)

    def test_peak_arena_documentation_describes_missing_ratings(self):
        source = function_source("_parse_records_elo_leaderboard_sheet")
        self.assertIn("literal ``n/a``", source)
        self.assertIn('allow_na=True', source)

    def test_public_elo_leaderboard_paths_are_unchanged(self):
        self.assertIn("records-elo-leaderboard-source.json", SOURCE)
        self.assertIn("records/elo-leaderboard/default-", SOURCE)
        self.assertNotIn("pre_match_elo-leaderboard", SOURCE)


if __name__ == "__main__":
    unittest.main()
