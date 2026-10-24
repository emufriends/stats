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


class FilterPerformanceTests(unittest.TestCase):
    def test_generic_mode_predicates_are_shared(self):
        generic = function_source("_build_where_sql")
        full = function_source("_build_full_sample_where_sql")
        self.assertIn("arena_season IS NOT NULL", generic)
        self.assertIn("COALESCE(is_tournament, FALSE)", generic)
        self.assertIn("f.arena_season IS NOT NULL", full)
        self.assertIn("COALESCE(f.is_tournament, FALSE)", full)

    def test_card_pair_daily_source_preserves_moments(self):
        card_source = function_source(
            "_refresh_prepared_card_play_aggregates_table"
        )
        self.assertIn("PREPARED_CARD_PLAY_AGGREGATES_TABLE", card_source)
        self.assertIn("SUM(SAFE_CAST(elo_delta AS FLOAT64))", card_source)
        source = function_source("_refresh_prepared_card_pair_aggregates_table")
        for field in (
            "observation_count",
            "delta_count",
            "delta_sum",
            "delta_sum_squares",
            "elo_count",
            "elo_sum",
        ):
            self.assertIn(field, source)
        query = function_source("_build_combinations_query")
        self.assertIn("PREPARED_CARD_PAIR_AGGREGATES_TABLE", query)
        self.assertIn("SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count))", query)

    def test_card_card_scope_cache_excludes_table_controls(self):
        source = function_source("_card_card_scope_cache_blob_name")
        self.assertNotIn("combination_min_plays", source)
        self.assertNotIn("combination_page", source)
        self.assertNotIn("combination_sort", source)

    def test_separate_maintenance_operation_warms_default_card_card_scopes(self):
        helper = function_source("_warm_card_card_default_scopes")
        request = function_source("_default_card_card_scope_request")
        refresh = function_source("_run_daily_refresh")
        self.assertIn("_warm_default_card_card_scope", helper)
        self.assertIn("COMBINATION_DEFAULT_MIN_PLAYS", request)
        self.assertNotIn("card_card_scope_futures", refresh)
        self.assertIn('params.get("warm_card_card_defaults")', SOURCE)

    def test_empty_player_no_longer_rejects_retained_last_x(self):
        self.assertNotIn("last_x_games requires a selected player", SOURCE)
        self.assertNotIn(
            "last_x_games requires at least one comparison player", SOURCE
        )
        rollup = function_source("_build_players_rollup_query")
        self.assertIn("FROM UNNEST([1]) WHERE FALSE", rollup)

    def test_players_component_cache_tracks_tournament_and_schema(self):
        source = function_source("_players_component_cache_blob_name")
        self.assertIn('"tournament_only"', source)
        self.assertIn('"rollup_schema"', source)
        query = function_source("_query_players_components")
        self.assertIn("cache_reads", query)
        self.assertIn("cache_writes", query)

    def test_players_use_weighted_daily_rollups_without_last_x(self):
        refresh = function_source("_refresh_prepared_players_table")
        self.assertIn("observation_count", refresh)
        self.assertIn("PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE", refresh)
        general = function_source("_build_players_rollup_query")
        comparison = function_source(
            "_build_players_comparison_rollup_query"
        )
        self.assertIn("SAFE_DIVIDE", general)
        self.assertIn("PREPARED_PLAYERS_BASELINE_TABLE", general)
        self.assertIn(
            "PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE", comparison
        )

    def test_performance_by_map_preserves_moments_and_per_map_last_x(self):
        refresh = function_source("_refresh_prepared_players_table")
        query = function_source("_build_players_performance_by_map_query")
        self.assertIn("PREPARED_PLAYERS_MAP_ROLLUP_TABLE", refresh)
        self.assertIn("COUNT(elo_delta) AS delta_count", refresh)
        self.assertIn("SUM(POW(elo_delta, 2))", refresh)
        self.assertIn("PARTITION BY f.player_identity, f.Map", query)
        self.assertIn("recent_rank <= @last_x_games", query)
        self.assertIn("delta_sum_squares", query)

    def test_players_last_x_uses_identity_hash_partitioned_copy(self):
        refresh = function_source("_refresh_prepared_players_table")
        self.assertIn("PREPARED_PLAYERS_RECENT_TABLE", refresh)
        self.assertIn(
            "CLUSTER BY player_identity, is_mw, Map, arena_season",
            refresh,
        )
        self.assertIn(
            "RANGE_BUCKET(identity_bucket, GENERATE_ARRAY(0, 1024, 1))",
            refresh,
        )
        self.assertIn("SHA256(player_identity)", refresh)
        self.assertNotIn(
            "PARTITION BY game_date\n    CLUSTER BY player_identity",
            refresh.split("recent_query =", 1)[1].split(
                "recent_job =", 1
            )[0],
        )
        query_router = function_source("_query_card_stats")
        self.assertIn("PREPARED_PLAYERS_RECENT_TABLE", query_router)
        last_x_query = function_source("_build_players_query")
        self.assertIn("CROSS JOIN UNNEST([", last_x_query)
        self.assertNotIn("UNION ALL", last_x_query)


if __name__ == "__main__":
    unittest.main()
