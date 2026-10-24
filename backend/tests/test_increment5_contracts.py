import json
import pathlib
import sys
import unittest
import uuid
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = ROOT / "phase2_private_data" / "python314"
if PYTHON.exists():
    sys.path.insert(0, str(PYTHON))

from phase3_duckdb_service import _project_arena_bundle
from phase4_local_routes import (
    PROJECT_REWARDS,
    PREDICTOR_SPECIFIC_CONDITIONS,
    SPONSOR_APPEAL_VALUES,
    SPONSOR_CP_CARDS,
    _final_records_sql,
    _next_home_sql,
    _next_predictor_sql,
    predictor_specific_feature_sql,
    _scoring_buckets,
    _simple_build_hexes_sql,
    _simple_build_enclosures_sql,
    _simple_conservation_project_rewards_sql,
)
from phase5_refresh_workflow import _tournament_metadata_with_fallback


class Increment5ContractTests(unittest.TestCase):
    def test_catalogs_match_the_current_public_contract(self):
        self.assertEqual(len(PREDICTOR_SPECIFIC_CONDITIONS), 19)
        labels = {row[0] for row in PREDICTOR_SPECIFIC_CONDITIONS}
        self.assertNotIn("Round 1: Humphead Wrasse", labels)
        self.assertNotIn("Round 1/2: New Zealand Fur Seal", labels)
        self.assertEqual(len(PROJECT_REWARDS), 22)
        self.assertEqual(len(SPONSOR_CP_CARDS), 31)
        self.assertEqual(len(SPONSOR_APPEAL_VALUES), 9)
        self.assertEqual(len(_scoring_buckets("final_score")[1]), 7)
        self.assertEqual(len(_scoring_buckets("appeal")[1]), 9)
        self.assertEqual(len(_scoring_buckets("conservation_points")[1]), 8)
        self.assertEqual(len(_scoring_buckets("reputation")[1]), 15)
        self.assertEqual(len(_scoring_buckets("final_score", True)[1]), 52)
        self.assertEqual(len(_scoring_buckets("appeal", True)[1]), 75)
        self.assertEqual(len(_scoring_buckets("conservation_points", True)[1]), 42)

    def test_expanded_build_catalog_is_generated_separately(self):
        compact_sql, _ = _simple_build_hexes_sql("TRUE", [], False)
        expanded_sql, _ = _simple_build_hexes_sql("TRUE", [], True)
        self.assertNotEqual(compact_sql, expanded_sql)
        self.assertIn("'0'", expanded_sql)
        self.assertIn("'23'", expanded_sql)
        self.assertIn("'24+'", compact_sql)

    def test_predictor_specific_uses_real_log_predicates(self):
        sql, parameters = _next_predictor_sql({
            "is_mw": 1,
            "maps": ["Map 1a: Observation Tower"],
            "player_elo_min": 300,
            "opponent_elo_min": 300,
            "date_from": "2025-01-01",
        }, "specific")
        self.assertIn("endgame_points > opp.endgame_points", sql)
        features = predictor_specific_feature_sql()
        self.assertIn("UNNEST(b.played_animals)", features)
        self.assertIn("round_1_two_association", sql)
        self.assertIn("no_project_opening", sql)
        self.assertNotIn("More endgame points', 'Conservation", sql)
        # Requests scope the focal player after pairing compact features;
        # filtering both sides first would erase first-only/second-only pairs.
        # Nested expansion belongs to the completed refresh population.
        self.assertIn("FROM predictor_specific_player_fact_narrow", sql)
        self.assertIn("me.Map IN (?)", sql)
        self.assertIn("me.pre_match_elo >= ?", sql)
        self.assertNotIn("opp.Map IN", sql)
        self.assertNotIn("UNNEST", sql)
        self.assertIn("f.is_completed_game AND NOT f.is_corrupted_game", features)
        self.assertNotIn("WHERE me.is_mw = ?", sql)
        self.assertIn(1, parameters)

    def test_build_empty_petting_zoo_contract_is_explicit(self):
        sql, _ = _simple_build_enclosures_sql("TRUE", [])
        self.assertIn("Petting_Zoo_icons", sql)
        self.assertIn("Horse Whisperer", sql)
        self.assertIn("enclosure_count = 1", sql)
        self.assertNotIn("enclosure_count IS NULL", sql)
        self.assertNotIn(" AS delta_5,", sql)

    def test_project_rewards_use_twenty_two_configured_rows(self):
        sql, _ = _simple_conservation_project_rewards_sql("TRUE", [])
        self.assertIn("3 reputation (T1)", sql)
        self.assertIn("Aviary/Reptile House", sql)
        self.assertIn("freq_overall_denom", sql)
        self.assertIn("Map 13: Drawing Board", sql)

    def test_project_rewards_preserve_log_population_and_parameter_order(self):
        sql, parameters = _simple_conservation_project_rewards_sql("f.pre_match_elo >= ?", [300])
        self.assertIn("FROM log_player_filter_fact_narrow f WHERE", sql)
        self.assertIn("FROM project_reward_choice_narrow f WHERE", sql)
        self.assertNotIn("filtered f JOIN project_reward_choice", sql)
        self.assertEqual(parameters, [300, 300])

    def test_home_keeps_corrupted_games_and_returns_twelve_measures(self):
        sql, _ = _next_home_sql({})
        self.assertNotIn("is_corrupted_game", sql)
        for metric in (
            "games_indexed", "animals_played", "sponsors_played",
            "projects_supported", "breaks_triggered", "x_tokens_gained",
            "games_logged", "emus_played", "two_cp_workers_taken",
            "empty_petting_zoos_played", "free_unis_and_partner_zoos",
            "bignose_project_blocks",
        ):
            self.assertIn(f"'{metric}'", sql)

    def test_records_winner_and_date_contracts_are_restored(self):
        fastest, _ = _final_records_sql({"is_mw": 1}, "fastest_games")
        highest, _ = _final_records_sql({"is_mw": 1}, "highest_scores")
        icons, _ = _final_records_sql({"is_mw": 1}, "most_icons")
        self.assertIn("f.Game_result AS INTEGER) = 1", fastest)
        self.assertIn("f.Game_result AS INTEGER) = 1", highest)
        self.assertIn("Number_of_turns AS DOUBLE) <= 100", highest)
        self.assertIn("CAST(CAST(f.game_ended_at AS DATE) AS VARCHAR)", fastest)
        self.assertIn("'Sea Animals'", icons)
        self.assertIn("CROSS JOIN LATERAL", icons)
        self.assertNotIn("UNION ALL SELECT TRY_CAST(f.", icons)

    def test_arena_projection_uses_draws_and_fide_lookup(self):
        payload = _project_arena_bundle([{
            "season": "S14", "number": 14, "mode": "mw", "rank": 1,
            "player": "A", "player_id": 1, "end": 600, "peak": 620,
            "games": 2, "arena_score_rate": 0.5, "opponent_elo": 500,
            "pr_opponent_elo": 500, "turns": 30, "ppt": 3.2,
            "timestamps": [], "ratings": [],
        }])
        row = payload["S14"]["rows"][0]
        self.assertEqual(row["winrate"], 50.0)
        self.assertEqual(row["pr"], 500)

    def test_tournament_last_known_good_is_reported(self):
        source = ROOT / f".increment5-metadata-{uuid.uuid4().hex}"
        source.mkdir()
        try:
            (source / "tournament-metadata.json").write_text(json.dumps({
                "rows": [{"table_id": 1, "tournament_name": "T", "season": "S"}],
                "source": {"row_count": 1, "sha256": "abc"},
            }), encoding="utf-8")
            (source / "source-status.json").write_text(json.dumps({
                "sources": {"tournament-metadata.json": {"state": "last_known_good"}},
            }), encoding="utf-8")
            rows, info = _tournament_metadata_with_fallback(source, source / "unused.duckdb")
            self.assertEqual(rows[0]["table_id"], 1)
            self.assertEqual(info["state"], "last_known_good")
        finally:
            for path in source.iterdir():
                path.unlink()
            source.rmdir()


if __name__ == "__main__":
    unittest.main()
