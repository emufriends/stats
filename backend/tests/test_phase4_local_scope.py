import unittest
from pathlib import Path

from phase4_local_routes import (
    MW_ACTION_CARDS,
    _next_card_action_sql,
    _next_card_endgame_sql,
    _players_metric_sql,
    _simple_metric_sql,
    endgames_general_sql,
    maps_metrics_sql,
    _next_predictor_sql,
    _next_home_sql,
)
from phase4_local_scope import normalize_scope, scope_predicates
from phase3_duckdb_service import Phase3RequestAdapter


class Phase4ScopeTests(unittest.TestCase):
    def test_default_scope_is_canonical_and_symmetric(self):
        scope = normalize_scope({"is_mw": 1})
        self.assertEqual(scope["is_mw"], 1)
        self.assertEqual(scope["starting_positions"], ["First player", "Second player"])
        self.assertEqual(scope["player_elo_min"], 0)
        self.assertEqual(scope["player_elo_max"], None)

    def test_frontend_map_codes_are_canonicalized(self):
        scope = normalize_scope({"is_mw": 1, "maps": ["1a", "T1", "0"]})
        self.assertEqual(scope["maps"], [
            "Map 0",
            "Map 1a: Observation Tower",
            "Map T1: Tournament 1",
        ])
        sql, parameters = scope_predicates(scope)
        self.assertIn("f.Map IN (?, ?, ?)", sql)
        self.assertIn("Map 1a: Observation Tower", parameters)

    def test_canonical_map_names_remain_unchanged(self):
        name = "Map 14: Lagoon"
        self.assertEqual(normalize_scope({"is_mw": 0, "maps": [name]})["maps"], [name])

    def test_restrictive_starting_position_is_parameterized(self):
        scope = normalize_scope({"is_mw": 0, "starting_positions": ["Second player"]})
        sql, parameters = scope_predicates(scope)
        self.assertIn("starting_position IN (?)", sql)
        self.assertIn("Second player", parameters)
        self.assertNotIn("Second player", sql)

    def test_unknown_scope_dimensions_fail_closed(self):
        with self.assertRaises(ValueError):
            normalize_scope({"is_mw": 1, "starting_positions": []})
        with self.assertRaises(ValueError):
            normalize_scope({"is_mw": 1, "arena_seasons": "S14"})
        # Optional Players Arena scope is omitted when unrestricted. If a
        # client explicitly sends it, an empty selection is invalid rather
        # than an alias for the unrestricted population.
        with self.assertRaises(ValueError):
            normalize_scope({"is_mw": 1, "players_arena_seasons": []})

    def test_rounds_and_players_arena_aliases_are_preserved(self):
        scope = normalize_scope({
            "is_mw": 1,
            "rounds": ["1", "6+"],
            "players_arena_only": True,
            "players_arena_seasons": ["S14"],
        })
        self.assertEqual(scope["rounds"], ["1", "6+"])
        self.assertTrue(scope["arena_only"])
        self.assertEqual(scope["arena_seasons"], ["S14"])

    def test_asymmetric_elo_uses_canonical_opponent_column(self):
        sql, parameters = scope_predicates(normalize_scope({
            "is_mw": 1,
            "player_elo_min": 700,
            "opponent_elo_min": 300,
        }))
        self.assertIn("f.pre_match_elo >= ?", sql)
        self.assertIn("f.opponent_pre_match_elo >= ?", sql)
        self.assertNotIn("f.opponent_elo", sql)
        self.assertEqual(parameters[:3], [1, 700.0, 300.0])

    def test_selected_players_general_is_not_misrouted_to_history(self):
        self.assertEqual(
            Phase3RequestAdapter._route({
                "stats_page": "players", "players_view": "general",
                "players_player": "portgard",
            }),
            ("players", "general"),
        )
        self.assertEqual(
            Phase3RequestAdapter._route({
                "stats_page": "players", "players_history": True,
                "players_player": "portgard",
            }),
            ("players", "history"),
        )

    def test_players_request_aliases_survive_normalization_and_cache_identity(self):
        normalized = Phase3RequestAdapter.normalize_request({
            "stats_page": "players", "players_view": "general", "is_mw": 1,
            "players_player": "portgard", "players_arena_only": True,
            "players_arena_seasons": ["S14"], "last_x_games": 25,
        })
        self.assertEqual(normalized["players_player"], "portgard")
        self.assertEqual(normalized["arena_seasons"], ["S14"])
        self.assertTrue(normalized["arena_only"])
        self.assertEqual(normalized["last_x_games"], 25)

    def test_cards_round_filter_is_not_dropped(self):
        normalized = Phase3RequestAdapter.normalize_request({
            "stats_page": "cards", "is_mw": 1, "rounds": ["1", "6+"],
        })
        sql, parameters = Phase3RequestAdapter._cards_sql(normalized)
        self.assertIn("cp.played_round IN (?)", sql)
        self.assertIn("cp.played_round >= 6", sql)
        self.assertIn(1, parameters)

    def test_home_keeps_corrupted_tables_as_the_global_exception(self):
        sql, _ = _next_home_sql({})
        self.assertNotIn("NOT f.is_corrupted_game", sql)
        self.assertNotIn("corrupted_tables_narrow", sql)

    def test_pair_predictors_filter_only_the_focal_player(self):
        sql, _ = _next_predictor_sql({"is_mw": 1}, "general")
        self.assertIn("FROM predictor_pair_fact_narrow p", sql)
        self.assertIn("NOT p.is_corrupted_game", sql)
        self.assertIn("p.pre_match_elo >= ?", sql)
        self.assertNotIn("opp.pre_match_elo >= ?", sql)

    def test_players_history_filters_before_last_x_and_merges_identity(self):
        normalized = Phase3RequestAdapter.normalize_request({
            "stats_page": "players", "players_history": True,
            "players_player": "portgard", "is_mw": 1,
            "maps": ["1a"], "starting_positions": ["First player"],
            "last_x_games": 25, "players_history_metrics": ["score"],
        })
        sql, parameters = Phase3RequestAdapter._players_history_sql(normalized)
        self.assertIn("player_identity_metadata", sql)
        self.assertIn("f.Map IN (?)", sql)
        self.assertIn("ROW_NUMBER() OVER", sql)
        self.assertIn("JOIN resolved r USING(player_identity)", sql)
        self.assertIn("recent_rank <= 25", sql)
        self.assertNotIn(25, parameters)

    def test_players_elo_history_is_combined_and_ignores_sidebar_scope(self):
        normalized = Phase3RequestAdapter.normalize_request({
            "stats_page": "players", "players_history": True,
            "players_player": "portgard", "is_mw": 1,
            "maps": ["1a"], "completed_only": True,
            "players_history_metrics": ["elo"],
        })
        sql, _ = Phase3RequestAdapter._players_history_sql(normalized)
        self.assertIn("f.post_match_elo IS NOT NULL", sql)
        self.assertNotIn("f.is_mw = ?", sql)
        self.assertNotIn("f.Map IN", sql)
        self.assertNotIn("f.is_completed_game", sql)

    def test_route_builders_use_shared_scope_and_pagination(self):
        maps_sql, maps_parameters = maps_metrics_sql({"is_mw": 1, "maps": ["Map 1a: Observation Tower"]})
        endgames_sql, endgames_parameters = endgames_general_sql({"is_mw": 1})
        self.assertIn("NOT f.is_corrupted_game", maps_sql)
        self.assertIn("NOT f.is_corrupted_game", endgames_sql)
        self.assertTrue(maps_sql.rstrip().endswith("LIMIT ? OFFSET ?"))
        self.assertTrue(endgames_sql.rstrip().endswith("LIMIT ? OFFSET ?"))
        self.assertEqual(maps_parameters[0], 1)
        self.assertEqual(endgames_parameters[0], 1)

    def test_metadata_dimensions_are_parameterized(self):
        sql, parameters = scope_predicates(
            normalize_scope({
                "is_mw": 1,
                "arena_seasons": ["S14"],
                "tournament_only": True,
            })
        )
        self.assertIn("f.arena_season IN (?)", sql)
        self.assertIn("f.is_tournament", sql)
        self.assertIn("S14", parameters)

    def test_completed_scope_uses_refresh_derivative(self):
        sql, parameters = scope_predicates(
            normalize_scope({"is_mw": 1, "completed_only": True})
        )
        self.assertIn("f.is_completed_game", sql)
        self.assertNotIn("GROUP BY table_id", sql)
        self.assertEqual(parameters, [1, 0.0, 0.0])

    def test_prepared_population_skips_redundant_table_filters(self):
        sql, _ = scope_predicates(
            normalize_scope({"is_mw": 1, "completed_only": True}),
            population_prepared=True,
        )
        self.assertNotIn("corrupted_tables_narrow", sql)
        self.assertNotIn("is_completed_game", sql)

    def test_players_general_uses_prepared_split_cohorts(self):
        sql, parameters = _players_metric_sql({"is_mw": 1}, "general")
        self.assertIn("players_metrics_narrow", sql)
        self.assertNotIn("source_full_sample", sql)
        self.assertIn("all_aggregate AS", sql)
        self.assertIn("masters_aggregate AS", sql)
        self.assertNotIn("FILTER (WHERE", sql)
        # Selected identity and global buckets use independent thin scans.
        # Cohorts combine exact per-value moments after the global scan.
        self.assertIn("cohort_buckets AS MATERIALIZED", sql)
        self.assertEqual(parameters.count(1), 2)

    def test_players_prepared_fact_retains_comparison_elo_delta(self):
        source = (
            Path(__file__).resolve().parents[1] / "phase2_local_vertical_slice.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"elo_delta", "Game_result"', source)

    def test_build_hexes_aggregates_once_per_bucket(self):
        sql, parameters = _simple_metric_sql({
            "simple_view": "build_hexes",
            "is_mw": 1,
        })
        self.assertIn("GROUP BY bucket", sql)
        self.assertIn("LEFT JOIN aggregates a USING(bucket)", sql)
        self.assertNotIn("FROM classified CROSS JOIN (VALUES", sql)
        self.assertEqual(parameters[0], 1)

    def test_nested_combinations_use_compact_weighted_aggregates(self):
        endgame_sql, endgame_parameters = _next_card_endgame_sql({"is_mw": 1})
        action_sql, action_parameters = _next_card_action_sql({"is_mw": 1})
        self.assertIn("event_n", endgame_sql)
        self.assertIn("eligible_games", endgame_sql)
        self.assertIn("selected_actions", action_sql)
        self.assertIn("pair_agg", action_sql)
        self.assertEqual(len(MW_ACTION_CARDS), 20)
        self.assertIn("action_card_number", action_sql)
        self.assertIn("= a.action_card_number", action_sql)
        self.assertIn("FROM selected_actions GROUP BY action_card_key", action_sql)
        self.assertIn("component_1_ci_mean", action_sql)
        self.assertIn("component_2_ci_mean", action_sql)
        self.assertNotIn("FROM played p JOIN source_logs", endgame_sql)
        self.assertNotIn(
            "FROM card_play_narrow cp JOIN source_full_sample g USING(table_id, player)\n      CROSS JOIN actions a",
            action_sql,
        )
        self.assertEqual(endgame_parameters[0], 1)
        self.assertEqual(action_parameters[0], 1)


if __name__ == "__main__":
    unittest.main()
