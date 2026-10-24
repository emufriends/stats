"""cards/component_ci honours every Cards filter instead of the hard-coded default scope."""
import unittest
from pathlib import Path
from types import SimpleNamespace

from phase3_duckdb_service import Generation, Phase3RequestAdapter, _load_duckdb


def build():
    con = _load_duckdb().connect(':memory:')
    # Four tables, one focal player each. Table 1-2 in 2025, tables 3-4 in 2024 (older).
    con.execute("""CREATE TABLE prepared_full_sample_narrow AS
      SELECT * FROM (VALUES
        (1, 'a', 1, 'Map 1a: Observation Tower', 500.0, 500.0, TIMESTAMP '2025-03-01', 'First player', FALSE, TRUE, NULL, FALSE, FALSE),
        (2, 'b', 1, 'Map 1a: Observation Tower', 500.0, 500.0, TIMESTAMP '2025-03-02', 'First player', FALSE, TRUE, NULL, FALSE, FALSE),
        (3, 'c', 1, 'Map 1a: Observation Tower', 500.0, 500.0, TIMESTAMP '2024-03-01', 'First player', FALSE, TRUE, NULL, FALSE, FALSE),
        (4, 'd', 1, 'Map 2a: Outdoor Areas', 500.0, 500.0, TIMESTAMP '2025-03-04', 'First player', FALSE, TRUE, NULL, FALSE, FALSE)
      ) t(table_id, player, is_mw, Map, pre_match_elo, opponent_pre_match_elo, game_ended_at,
          starting_position, is_corrupted_game, is_completed_game, arena_season, is_arena_game, is_tournament)""")
    con.execute("""CREATE TABLE card_play_narrow AS
      SELECT * FROM (VALUES
        (1,'a',1,'Zebra','animal',10.0,1),(2,'b',1,'Zebra','animal',20.0,1),
        (3,'c',1,'Zebra','animal',100.0,1),(4,'d',1,'Zebra','animal',40.0,3)
      ) t(table_id, player, is_mw, card_name, card_type, elo_delta, played_round)""")
    return con


def run(con, extra):
    request = {"stats_page": "cards", "component_ci": True, "is_mw": 1,
               "card_name": "Zebra", "card_type": "animal", "player_elo_min": 300,
               "opponent_elo_min": 300, "date_from": "2025-01-01"}
    request.update(extra)
    normalized = Phase3RequestAdapter.normalize_request(request)
    sql, params = Phase3RequestAdapter._ordinary_ci_sql(normalized)
    return con.execute(sql, params).fetchone()


class OrdinaryCardCiFilterTests(unittest.TestCase):
    def setUp(self):
        self.con = build()

    def tearDown(self):
        self.con.close()

    def test_date_filter_applies(self):
        delta, n, *_ = run(self.con, {})
        self.assertEqual(n, 3)                       # 2024 table excluded by date_from
        self.assertAlmostEqual(delta, (10 + 20 + 40) / 3)
        delta, n, *_ = run(self.con, {"date_from": None})
        self.assertEqual(n, 4)                       # blank date = all time

    def test_map_and_round_filters_apply(self):
        _, n, *_ = run(self.con, {"maps": ["Map 1a: Observation Tower"]})
        self.assertEqual(n, 2)
        _, n, *_ = run(self.con, {"rounds": ["3"]})
        self.assertEqual(n, 1)

    def test_removed_validation_tables_are_not_required(self):
        request = Phase3RequestAdapter.normalize_request({
            'stats_page':'cards','component_ci':True,'is_mw':1,
            'card_name':'Zebra','card_type':'animal'})
        sql, _ = Phase3RequestAdapter._ordinary_ci_sql(request)
        self.assertNotIn('card_component_by_table_narrow',sql)
        self.assertNotIn('card_component_aggregate_narrow',sql)
        self.assertEqual(set(request['starting_positions']),{'First player','Second player'})

    def test_public_adapter_dispatches_without_validation_relations(self):
        generation = Generation('ordinary-ci-test',Path('unused.duckdb'),Path('unused.json'),
                                {'data_version':'ordinary-ci-test','builder':{'relations':{}}})
        def query(sql,params):
            cursor=self.con.execute(sql,params)
            columns=[item[0] for item in cursor.description]
            return {'generation':generation.generation_id,'data_version':generation.data_version,
                    'rows':[dict(zip(columns,row)) for row in cursor.fetchall()]}
        store=SimpleNamespace(generation=lambda:generation,query=query,
                              manager=SimpleNamespace(inspect=lambda _id:generation))
        adapter=Phase3RequestAdapter(store,allow_default_snapshots=False)
        response=adapter.execute({'stats_page':'cards','component_ci':True,'is_mw':1,
                                  'card_name':'Zebra','card_type':'animal','date_from':'2025-01-01'})
        self.assertEqual(response['status'],'ok')
        self.assertEqual(response['view'],'ordinary_card_ci')
        self.assertEqual(response['data'][0]['n_played'],3)
        self.assertEqual(response['data'][0]['cluster_n'],3)
        self.assertIsNotNone(response['data'][0]['ci95_low'])

    def test_starting_position_completion_and_tournament_scope(self):
        self.con.execute("UPDATE prepared_full_sample_narrow SET starting_position='Second player',is_completed_game=FALSE,is_tournament=TRUE WHERE table_id=4")
        _, n, *_ = run(self.con,{'starting_positions':['First player']})
        self.assertEqual(n,2)
        _, n, *_ = run(self.con,{'starting_positions':['Second player']})
        self.assertEqual(n,1)
        _, n, *_ = run(self.con,{'completed_only':True})
        self.assertEqual(n,2)
        _, n, *_ = run(self.con,{'tournament_only':True})
        self.assertEqual(n,1)

    def test_repeated_plays_nulls_and_corruption_preserve_component_grain(self):
        self.con.execute("INSERT INTO card_play_narrow VALUES (1,'a',1,'Zebra','animal',10.0,2),(2,'b',1,'Zebra','animal',NULL,2)")
        mean,n,*_ = run(self.con,{})
        self.assertEqual(n,3)
        self.assertAlmostEqual(mean,(10+20+40)/3)
        self.con.execute('UPDATE prepared_full_sample_narrow SET is_corrupted_game=TRUE WHERE table_id=1')
        mean,n,*_ = run(self.con,{})
        self.assertEqual(n,2)
        self.assertEqual(mean,30)


if __name__ == "__main__":
    unittest.main()
