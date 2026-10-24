"""Exact focal-player filtering and event weighting of the paired Cards fact."""
import unittest
from phase3_cards_pair_contracts import create_cards_pair_relations, create_combo_card_pair_relations
from phase3_duckdb_service import Phase3RequestAdapter, EXCLUDED_SUMMARY_PROJECTS
from phase4_combo_mw_contracts import combination_sql
from phase2_local_vertical_slice import create_card_table_filter_relations


class CardsPairContracts(unittest.TestCase):
    def setUp(self):
        try:
            import duckdb
        except ImportError:
            self.skipTest('DuckDB is unavailable')
        self.c = duckdb.connect(':memory:')
        self.c.execute('''CREATE TABLE game_player_narrow (
          table_id BIGINT, player VARCHAR, is_mw BIGINT, is_corrupted_game BOOLEAN,
          map_name VARCHAR, game_ended_at TIMESTAMP, starting_position VARCHAR,
          pre_match_elo DOUBLE, opponent_pre_match_elo DOUBLE, elo_delta DOUBLE,
          is_completed_game BOOLEAN, arena_season VARCHAR, is_arena_game BOOLEAN,
          is_tournament BOOLEAN)''')
        players = [
            (1,'A',1,False,'Map A','2025-01-01','First player',700,300,1.2,True,'S1',True,False),
            (1,'B',1,False,'Map B','2025-01-01','Second player',300,700,-.8,True,'S1',True,False),
            (2,'A',1,False,'Map A','2025-02-01','Second player',600,600,2.4,False,None,False,True),
            (2,'B',1,False,'Map A','2025-02-01','First player',600,600,None,False,None,False,True),
            (3,'A',1,False,'Map B','2025-03-01','First player',None,400,-1.4,True,None,False,False),
            (3,'B',1,False,None,'2025-03-01','Second player',400,None,.6,True,None,False,False),
        ]
        self.c.executemany('INSERT INTO game_player_narrow VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', players)
        self.c.execute("CREATE TABLE card_catalog_narrow AS SELECT 1::SMALLINT AS card_id, 'Animal' AS card_name, 'animal' AS card_type UNION ALL SELECT 2,'Africa','project'")
        self.c.execute('''CREATE TABLE core (table_id BIGINT, player VARCHAR, card_name VARCHAR,
          played_count BIGINT, played_r1 BIGINT, played_r2 BIGINT, played_r3 BIGINT,
          played_r4 BIGINT, played_r5 BIGINT, played_r6plus BIGINT, in_hand BIGINT, seen BIGINT)''')
        self.c.executemany('INSERT INTO core VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [
            (1,'A','Animal',3,1,2,0,0,0,0,1,1),
            (1,'B','Animal',1,0,0,0,0,0,1,1,1),
            (2,'A','Animal',1,0,1,0,0,0,0,0,1),
            (2,'B','Animal',1,1,0,0,0,0,0,1,1),
            (3,'A','Animal',2,1,0,0,0,0,1,1,1),
            (3,'B','Animal',0,0,0,0,0,0,0,1,1),
            (1,'A','Africa',1,1,0,0,0,0,0,1,1),
        ])
        self.c.execute('''CREATE TABLE card_filter_fact_mw_narrow AS
          SELECT c.*, k.card_type, g.* EXCLUDE(table_id,player,map_name), g.map_name AS Map
          FROM core c JOIN game_player_narrow g USING(table_id,player)
          JOIN card_catalog_narrow k USING(card_name)''')
        self.c.execute('CREATE TABLE card_filter_fact_base_narrow AS SELECT * FROM card_filter_fact_mw_narrow WHERE FALSE')

    def tearDown(self):
        if hasattr(self, 'c'):
            self.c.close()

    def test_all_supported_filters_match_exact_player_fact(self):
        create_card_table_filter_relations(self.c)
        counts = create_cards_pair_relations(self.c)
        self.assertEqual(counts['cards_pair_fact_mw_narrow'], 4)
        scopes = [
            {}, {'maps':['Map A']}, {'maps':['Map B']}, {'maps':['Map A','Map B']},
            {'player_elo_min':700,'opponent_elo_min':300},
            {'player_elo_max':650,'opponent_elo_max':650},
            {'starting_positions':['First player']}, {'starting_positions':['Second player']},
            {'rounds':['1']}, {'rounds':['2','6+']}, {'completed_only':True},
            {'arena_only':True}, {'arena_seasons':['S1']}, {'tournament_only':True},
            {'date_from':'2025-02-01','date_to':'2025-03-01'},
            {'maps':['Map A'],'rounds':['2'],'starting_positions':['Second player']},
        ]
        for scope in scopes:
            with self.subTest(scope=scope):
                request = Phase3RequestAdapter.normalize_request(dict(stats_page='cards',is_mw=1,**scope))
                outputs = []
                for pair in (False, True):
                    sql, params = Phase3RequestAdapter._cards_sql(dict(request,
                        _cards_filter_fact=True, _cards_pair_fact=pair, _cards_pair_pooled_fact=pair))
                    cur = self.c.execute(sql, [*params, request['limit'], request['offset']])
                    outputs.append([dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()])
                self.assertEqual(len(outputs[0]),len(outputs[1]))
                for left,right in zip(*outputs):
                    self.assertEqual(left.keys(),right.keys())
                    for key in left:
                        if key.endswith(('_ci_mean','_ci_sd')) and isinstance(left[key],float):
                            self.assertAlmostEqual(left[key],right[key],places=12)
                        else:
                            self.assertEqual(left[key],right[key])
                self.assertNotIn('Africa', [r['card_name'] for r in outputs[1]])

    def test_malformed_player_grain_does_not_publish_a_partial_fast_fact(self):
        self.c.execute("DELETE FROM game_player_narrow WHERE table_id=1 AND player='B'")
        counts = create_cards_pair_relations(self.c)
        self.assertNotIn('cards_pair_fact_mw_narrow', counts)

    def test_combo_pairs_preserve_independent_round_matches_and_null_deltas(self):
        self.c.execute("INSERT INTO card_catalog_narrow VALUES (3,'Sponsor','sponsor')")
        self.c.execute('''INSERT INTO card_filter_fact_mw_narrow
          SELECT * REPLACE('Sponsor' AS card_name, 'sponsor' AS card_type,
            1 AS played_count, 0 AS played_r1, 1 AS played_r2, 0 AS played_r6plus)
          FROM card_filter_fact_mw_narrow WHERE card_name='Animal' ''')
        for suffix in ('mw','base'):
            self.c.execute(f'''CREATE TABLE card_play_filter_fact_{suffix}_narrow AS
              SELECT c.*, k.card_id FROM card_filter_fact_{suffix}_narrow c
              JOIN card_catalog_narrow k USING(card_name) WHERE played_count>0''')
        create_cards_pair_relations(self.c)
        create_combo_card_pair_relations(self.c, EXCLUDED_SUMMARY_PROJECTS)
        for scope in ({}, {'maps':['Map A']}, {'rounds':['1']}, {'rounds':['2']},
                      {'rounds':['1','2']}, {'rounds':['6+','2']},
                      {'starting_positions':['First player']},
                      {'starting_positions':['Second player']},
                      {'player_elo_min':700,'opponent_elo_min':300},
                      {'player_elo_max':650,'opponent_elo_max':650},
                      {'completed_only':True}, {'arena_seasons':['S1']},
                      {'tournament_only':True},
                      {'date_from':'2025-02-01','date_to':'2025-03-01'},
                      {'maps':['Map A'],'rounds':['2'],
                       'starting_positions':['Second player']}):
            with self.subTest(scope=scope):
                request = Phase3RequestAdapter.normalize_request(dict(stats_page='combinations',
                    combinations_view='card_card', is_mw=1, **scope))
                outputs=[]
                for fast, paired_components in ((False,False),(True,False),(True,True)):
                    sql, params = combination_sql(dict(request, _combos_played_fact=True,
                        _combos_filter_fact=True,_combo_card_pair_fact=fast,
                        _combo_card_component_pair_fact=paired_components), 'card_card')
                    cur = self.c.execute(sql,[*params,request['limit'],request['offset']])
                    outputs.append([dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()])
                for output in outputs[1:]:
                    self.assertEqual(len(outputs[0]),len(output))
                    for left,right in zip(outputs[0],output):
                        for key in left:
                            if isinstance(left[key],float):
                                self.assertAlmostEqual(left[key],right[key],places=12)
                            else:
                                self.assertEqual(left[key],right[key])


if __name__ == '__main__':
    unittest.main()
