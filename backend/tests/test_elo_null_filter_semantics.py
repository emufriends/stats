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


class EloNullFilterSemanticsTests(unittest.TestCase):
    def test_shared_range_builders_treat_null_as_zero(self):
        for function_name in (
            "_build_where_sql",
            "_build_maps_metrics_where_sql",
            "_build_full_sample_where_sql",
        ):
            source = function_source(function_name)
            self.assertIn("COALESCE(", source, function_name)
            self.assertIn("pre_match_elo, 0)", source, function_name)
            self.assertIn("opponent_pre_match_elo, 0)", source, function_name)

    def test_players_paths_use_the_same_opponent_elo_rule(self):
        history = function_source("_query_players_history")
        refresh = function_source("_refresh_prepared_players_table")
        self.assertIn("COALESCE(f.opponent_pre_match_elo, 0)", history)
        self.assertIn("COALESCE(opponent_pre_match_elo, 0) >= 0", refresh)

    def test_nulls_are_not_rewritten_for_statistics(self):
        home = function_source("_refresh_prepared_home_observations_table")
        players = function_source("_refresh_prepared_players_table")
        self.assertIn("SAFE_CAST(f.opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo", home)
        self.assertNotIn(
            "COALESCE(SAFE_CAST(f.opponent_pre_match_elo AS FLOAT64), 0) AS opponent_pre_match_elo",
            home,
        )
        self.assertIn("pre_match_elo >= 500 AS is_expert", players)
        self.assertIn("pre_match_elo >= 700 AS is_master", players)

    def test_records_no_longer_exempt_unknown_enrichment(self):
        records = function_source("_build_records_query")
        self.assertNotIn("NOT f.source_enriched OR", records)

    def test_prepared_full_stats_rejects_legacy_rating_fields(self):
        refresh = function_source("_refresh_prepared_full_stats_table")
        self.assertIn("f.* EXCEPT(elo, opponent_elo, end_game_triggered)", refresh)
        self.assertIn("opponent.pre_match_elo", refresh)
        self.assertIn("COUNT(DISTINCT opponent.player) = 1", refresh)
        self.assertIn("AS opponent_pre_match_elo", refresh)
        self.assertNotIn(" AS elo,", refresh)

    def test_elo_delta_remains_source_defined(self):
        refresh = function_source("_refresh_prepared_full_stats_table")
        self.assertNotIn("AS elo_delta", refresh)


if __name__ == "__main__":
    unittest.main()
