"""Independent expected answers, not agreement between two production queries."""
from collections import defaultdict
from decimal import Decimal, localcontext
import unittest

from phase3_duckdb_service import _load_duckdb
from phase5_component_ci import component_population_sql
from phase4_combo_mw_contracts import component_ci_sql
from phase4_local_routes import endgames_general_sql


def independent_oracle(values):
    with localcontext() as context:
        context.prec=70
        groups=defaultdict(list)
        for game,value in values:
            if value is not None:
                groups[game].append(Decimal.from_float(float(value)))
        n=sum(len(values) for values in groups.values())
        if not n:
            return n,0,None,None
        mean=sum((sum(values,Decimal(0)) for values in groups.values()),Decimal(0))/n
        games=len(groups)
        if games<2:
            return n,games,float(mean),None
        influence=sum(((sum(values,Decimal(0))-len(values)*mean)**2
                       for values in groups.values()),Decimal(0))
        se=(Decimal(games)/Decimal(games-1)*influence/Decimal(n*n)).sqrt()
        return n,games,float(mean),float(se)


def fixture(values):
    c=_load_duckdb().connect()
    c.execute('SET threads=1')
    c.execute('''CREATE TABLE prepared_full_sample_narrow(
      table_id BIGINT,player VARCHAR,is_mw INTEGER,Map VARCHAR,
      pre_match_elo DOUBLE,opponent_pre_match_elo DOUBLE,elo_delta DOUBLE,
      is_corrupted_game BOOLEAN,is_completed_game BOOLEAN,game_ended_at TIMESTAMP,
      starting_position VARCHAR,arena_season VARCHAR,is_arena_game BOOLEAN,is_tournament BOOLEAN)''')
    c.executemany("INSERT INTO prepared_full_sample_narrow VALUES (?,?,1,'Map 1a: Observation Tower',500,500,?,FALSE,TRUE,TIMESTAMP '2026-01-01','First player',NULL,FALSE,FALSE)",
                  [(game,f'p{index}',value) for index,(game,value) in enumerate(values)])
    c.execute("CREATE TABLE card_play_narrow AS SELECT table_id,player,'X'card_name,'animal'card_type,1 played_round,elo_delta FROM prepared_full_sample_narrow")
    c.execute("CREATE TABLE endgame_score_event_narrow AS SELECT table_id,player,'E'endgame_name FROM prepared_full_sample_narrow")
    c.execute("CREATE TABLE endgame_dealt_event_narrow AS SELECT * FROM endgame_score_event_narrow")
    c.execute("CREATE TABLE endgame_score_filter_event_narrow AS SELECT *,2.0 cp FROM endgame_score_event_narrow")
    c.execute("CREATE TABLE mw_action_card_selection_narrow AS SELECT table_id,player,'Cards 1'card_key,elo_delta FROM prepared_full_sample_narrow")
    c.execute('CREATE TABLE mw_action_card_eligible_tables_narrow AS SELECT DISTINCT table_id FROM prepared_full_sample_narrow')
    return c


def query(c,sql,params):
    cursor=c.execute(sql,params)
    names=[value[0] for value in cursor.description]
    return [dict(zip(names,row)) for row in cursor.fetchall()]


class IndependentClusterMathTests(unittest.TestCase):
    def assert_statistics(self,n,games,mean,se,actual,prefix=''):
        self.assertEqual(actual[prefix+'ci95_n'],n)
        self.assertEqual(actual[prefix+'ci95_cluster_n'],games)
        self.assertEqual(actual[prefix+'mean'],mean)
        if se is None:
            for field in ('ci95_se','ci95_low','ci95_high'):
                self.assertIsNone(actual[prefix+field])
        else:
            self.assertAlmostEqual(actual[prefix+'ci95_se'],se,places=12)
            self.assertAlmostEqual(actual[prefix+'ci95_low'],mean-1.96*se,places=12)
            self.assertAlmostEqual(actual[prefix+'ci95_high'],mean+1.96*se,places=12)

    def check_population(self,values):
        c=fixture(values)
        try:
            n,games,mean,se=independent_oracle(values)
            for kind in ('card','action_card','endgame'):
                sql,params=component_population_sql({'is_mw':1},telemetry=False,kind=kind)
                rows=query(c,sql,params)
                with self.subTest(kind=kind,values=values):
                    if not n:
                        self.assertEqual(rows,[])
                    else:
                        self.assert_statistics(n,games,mean,se,rows[0])
            sql,params=component_ci_sql({'is_mw':1},'combinations','card_card',
                                       [{'card_1':'X','card_2':'X'}])
            row=query(c,sql,params+[100,0])[0]
            for prefix in ('component_1_','component_2_'):
                self.assert_statistics(n,games,mean,se,row,prefix)
            sql,params=endgames_general_sql({'is_mw':1})
            row=query(c,sql,params+[100,0])[0]
            # Counts of uses/deals and CP observations must not be discarded
            # while excluding empty groups ONLY from uncertainty estimation.
            self.assertEqual(row['n_played'],len(values))
            self.assertEqual(row['n_seen'],len(values))
            self.assertEqual(row['avg_cp'],2.0)
            for prefix in ('delta_played_','delta_in_hand_'):
                self.assertEqual(row[prefix+'ci95_n'],n)
                if se is None:
                    self.assertIsNone(row[prefix+'ci95_low'])
                    self.assertIsNone(row[prefix+'ci95_high'])
                else:
                    self.assertAlmostEqual(row[prefix+'ci95_low'],mean-1.96*se,places=12)
                    self.assertAlmostEqual(row[prefix+'ci95_high'],mean+1.96*se,places=12)
        finally:
            c.close()

    def test_oracle_known_answers(self):
        self.assertEqual(independent_oracle([(1,1.),(2,3.)]),(2,2,2.,1.))
        self.assertEqual(independent_oracle([(1,1.),(2,None)]),(1,1,1.,None))

    def test_valid_two_games(self):
        self.check_population([(1,1.),(2,3.)])

    def test_empty_game_does_not_shrink_interval(self):
        self.check_population([(1,1.),(2,3.),(3,None)])

    def test_one_informative_game_still_has_no_interval(self):
        self.check_population([(1,1.),(2,None)])

    def test_no_informative_games(self):
        self.check_population([(1,None),(2,None)])

    def test_unequal_cluster_sizes_keep_observation_weights(self):
        self.check_population([(1,1.),(1,2.),(2,4.),(3,8.),(3,9.)])

    def test_repeated_play_event_does_not_duplicate_component(self):
        c=fixture([(1,1.),(2,3.)])
        try:
            c.execute('INSERT INTO card_play_narrow SELECT * FROM card_play_narrow WHERE table_id=1')
            c.execute('INSERT INTO card_play_narrow SELECT table_id,player,card_name,card_type,2,elo_delta FROM card_play_narrow WHERE table_id=1 LIMIT 1')
            sql,params=component_population_sql({'is_mw':1},telemetry=False,kind='card')
            self.assert_statistics(2,2,2.,1.,query(c,sql,params)[0])
        finally:
            c.close()


if __name__=='__main__':
    unittest.main()
