"""Focused regression coverage for exact compact serving populations."""
import inspect
import math
import re
import unittest

from phase2_local_vertical_slice import create_log_filter_relations
from phase3_duckdb_service import Phase3RequestAdapter
from phase4_combo_mw_contracts import combination_sql
from phase4_local_routes import (endgames_general_sql, _next_endgames_sql,
    _next_sponsor_sql, _players_cohort_moments_sql, PLAYERS_METRICS, PLAYERS_MONEY_FIELDS)


class CompactFilterContracts(unittest.TestCase):
    def test_cards_fact_does_not_drop_explicit_completion(self):
        request = Phase3RequestAdapter.normalize_request({
            'stats_page': 'cards', 'is_mw': 1, 'completed_only': True,
        })
        request['_cards_filter_fact'] = True
        sql, _ = Phase3RequestAdapter._cards_sql(request)
        self.assertIn('c.is_completed_game', sql)

    def test_table_cards_fact_cannot_pool_different_player_maps(self):
        request = Phase3RequestAdapter.normalize_request({
            'stats_page': 'cards', 'is_mw': 1, 'maps': ['1a'],
        })
        request.update(_cards_filter_fact=True, _cards_table_fact=True)
        sql, _ = Phase3RequestAdapter._cards_sql(request)
        self.assertIn('FROM card_filter_fact_mw_narrow c', sql)
        self.assertIn('c.Map IN (?)', sql)
        self.assertNotIn('FROM card_filter_table_fact_mw_narrow c', sql)

    def test_page_log_facts_do_not_inherit_card_log_eligibility(self):
        source = inspect.getsource(create_log_filter_relations)
        self.assertNotIn('valid_log_ids_narrow', source)
        self.assertIn('NOT g.is_corrupted_game', source)
        self.assertIn('source_logs l JOIN game_player_narrow', source)

    def test_endgame_and_sponsor_routes_use_their_own_log_facts(self):
        sql, _ = endgames_general_sql({'is_mw': 1})
        self.assertIn('endgame_score_filter_event_narrow', sql)
        sql, _ = _next_endgames_sql({'is_mw': 1}, False)
        self.assertIn('endgame_score_filter_event_narrow', sql)
        sql, _ = _next_sponsor_sql({'is_mw': 1}, False)
        self.assertIn('sponsor_play_filter_event_narrow', sql)
        self.assertIn('sponsor_endgame_filter_event_narrow', sql)

    def test_round_expansion_preserves_distinct_raw_rounds(self):
        sql, _ = combination_sql({'is_mw': 1, '_combos_played_fact': True}, 'card_round')
        self.assertIn('UNNEST(b.played_rounds)', sql)
        self.assertNotIn(', UNNEST(g.played_rounds)', sql)
        self.assertIn("played_round >= 6 THEN '6+'", sql)

    def test_encoded_pair_order_remains_card_name_order(self):
        sql, _ = combination_sql({
            'is_mw': 1, '_combos_filter_fact': True, '_combos_played_fact': True,
        }, 'card_card')
        self.assertIn('a.card_id < b.card_id', sql)
        self.assertIn('JOIN card_catalog_narrow k1', sql)
        self.assertIn('c1.card_name = p.card_1', sql)

    def test_card_action_pair_fact_retains_action_population_independently(self):
        sql, parameters = combination_sql({
            'is_mw': 1, '_card_action_pair_fact': True, 'rounds': ['1'],
            'starting_positions': ['First player'],
        }, 'card_action_card')
        self.assertIn('FROM card_action_pair_filter_fact_narrow p', sql)
        self.assertIn('p.played_r1 > 0', sql)
        self.assertIn('FROM mw_action_card_selection_narrow a WHERE', sql)
        self.assertEqual(parameters.count('First player'), 2)
        self.assertNotIn('JOIN actions a USING(table_id, player)', sql)

    def test_cohort_buckets_preserve_null_counts_and_ratios_of_means(self):
        try:
            import duckdb
        except ImportError:
            self.skipTest('DuckDB is unavailable')
        c = duckdb.connect(':memory:')
        try:
            # A cohort unit test must not depend on whichever historical local
            # generation happens to sort last or on its available derivatives.
            expressions = ' '.join(metric[-1] for metric in PLAYERS_METRICS)
            expressions = re.sub(r"'[^']*'", '', expressions)
            keywords = {'AVG','TRY_CAST','AS','DOUBLE','NULLIF','CASE','WHEN',
                        'THEN','ELSE','END','IN','NULL','TRUE','FALSE'}
            fields = {name for name in re.findall(r'\b[A-Za-z_]\w*\b', expressions)
                      if name.upper() not in keywords}
            fields.update(('pre_match_elo','Game_result'))
            values = ["'Map 1a: Observation Tower' AS Map" if name == 'Map'
                      else f'CAST(i+1 AS DOUBLE) AS {name}' for name in sorted(fields)]
            c.execute(f"CREATE TEMP TABLE sample AS SELECT {', '.join(values)} FROM range(8) r(i)")
            c.execute('ALTER TABLE sample ADD COLUMN test_row INTEGER')
            c.execute('UPDATE sample SET test_row = rowid')
            c.execute('''UPDATE sample SET
              pre_match_elo = CASE test_row % 4 WHEN 0 THEN NULL WHEN 1 THEN 499 WHEN 2 THEN 500 ELSE 700 END,
              Game_result = CASE WHEN test_row % 2 = 0 THEN 1 ELSE 2 END,
              Number_of_turns = CASE WHEN test_row = 0 THEN NULL ELSE 42 END,
              Money_spent_on_animals = CASE WHEN test_row = 1 THEN NULL ELSE 12 END,
              Money_spent_on_enclosures = CASE WHEN test_row = 2 THEN NULL ELSE 8 END,
              Money_spent_on_donations = 3,
              Money_spent_for_playing_cards_from_reputation_range = 2''')
            query = _players_cohort_moments_sql('TRUE').replace('players_metrics_narrow f', 'sample f')
            rows = c.execute('WITH ' + query + ' SELECT * FROM cohort_aggregate').fetchall()
            columns = [d[0] for d in c.description]
            actual = {r[0]: dict(zip(columns, r)) for r in rows}
            fields = ['COUNT(*) AS observation_count', *[f'{e} AS {k}' for k, *_, e in PLAYERS_METRICS],
                      *[f'AVG(TRY_CAST({col} AS DOUBLE)) AS raw_{k}' for k, col in PLAYERS_MONEY_FIELDS.items()]]
            for cohort, where in [('all', 'TRUE'), ('winners', 'Game_result=1'), ('experts', 'pre_match_elo>=500'), ('masters', 'pre_match_elo>=700')]:
                cur = c.execute(f"SELECT {', '.join(fields)} FROM sample WHERE {where}")
                expected = dict(zip([d[0] for d in cur.description], cur.fetchone()))
                for key, value in expected.items():
                    with self.subTest(cohort=cohort, metric=key):
                        if value is None:
                            self.assertIsNone(actual[cohort][key])
                        else:
                            self.assertTrue(math.isclose(value, actual[cohort][key], rel_tol=1e-12, abs_tol=1e-12))
        finally:
            c.close()


if __name__ == '__main__':
    unittest.main()
