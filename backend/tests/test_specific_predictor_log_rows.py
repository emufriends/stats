"""Duplicate source log keys must not pool row-local event features."""
import unittest

from phase3_duckdb_service import _load_duckdb
from phase4_local_routes import predictor_specific_feature_sql


class SpecificPredictorLogRowsTests(unittest.TestCase):
    def test_each_exported_log_row_keeps_its_own_association_count(self):
        connection = _load_duckdb().connect(':memory:')
        try:
            connection.execute('''CREATE TABLE prepared_full_sample_narrow AS
              SELECT 1::BIGINT AS table_id, 'a' AS player, TRUE AS is_mw, 'map' AS Map,
                TIMESTAMP '2026-01-01' AS game_ended_at, 'First player' AS starting_position,
                700.0 AS pre_match_elo, 300.0 AS opponent_pre_match_elo, 1.0 AS elo_delta,
                TRUE AS is_completed_game, FALSE AS is_corrupted_game, NULL::VARCHAR AS arena_season,
                FALSE AS is_arena_game, FALSE AS is_tournament, 10.0 AS Conservation''')
            connection.execute('''CREATE TABLE source_logs AS
              SELECT 1::BIGINT AS table_id, 'a' AS player,
                [{'animal':'Australian Dingo'}] AS played_animals,
                []::VARCHAR[] AS opening_cards,
                []::STRUCT(cp DOUBLE)[] AS endgame_scores,
                []::STRUCT(sponsor VARCHAR, cp DOUBLE, appeal DOUBLE)[] AS endgame_from_sponsors,
                [{'round':'1','project':NULL::VARCHAR}] AS association_action_history,
                [{'move':'10','cp':'5'}] AS cp_history,
                FALSE AS has_round_1_upgrade, FALSE AS has_round_1_release,
                NULL::VARCHAR AS chosen_5cp_bonus, NULL::VARCHAR AS chosen_8cp_bonus,
                2 AS association_starting_strength, 5 AS sponsors_starting_strength
              UNION ALL SELECT 1,'a',
                [{'animal':'Australian Dingo'},{'animal':'Australian Dingo'}], ['Explorer'],
                [], [], [{'round':'1','project':NULL::VARCHAR},{'round':'1','project':NULL::VARCHAR}],
                [{'move':'20','cp':'5'}], FALSE,FALSE,NULL,NULL,2,5''')
            query = predictor_specific_feature_sql()
            rows = connection.execute('''SELECT round_1_two_association, first_5_move,
              no_sponsor_opening FROM (''' + query + ') ORDER BY first_5_move').fetchall()
            self.assertEqual(rows, [(False, 10, True), (True, 20, False)])
            columns = [item[0] for item in connection.execute(query).description]
            self.assertNotIn('source_log_row_id', columns)
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main()
