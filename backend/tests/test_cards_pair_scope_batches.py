"""Scope batching parity, eligibility and interrupted-build safety fixtures."""
import unittest
import duckdb
import phase3_cards_pair_contracts as p


class Scope(unittest.TestCase):
    def setUp(self):
        self.c=duckdb.connect()
        self.c.execute('SET threads=1')
        self.c.execute('''CREATE TABLE game_player_narrow AS SELECT *,
          'Map 1a'::VARCHAR map_name,TIMESTAMP '2026-01-01' game_ended_at,
          'First player'::VARCHAR starting_position,500.25::DOUBLE pre_match_elo,
          400.5::DOUBLE opponent_pre_match_elo,0.25::DOUBLE elo_delta,
          TRUE is_completed_game,NULL::VARCHAR arena_season,
          FALSE is_arena_game,FALSE is_tournament
          FROM (VALUES(9,'z',1,FALSE),(9,'A',1,FALSE),
                       (2,'é',1,FALSE),(2,'a',1,FALSE),
                       (100,'b',0,FALSE),(100,'a',0,FALSE),
                       (20,'b',0,TRUE),(20,'a',0,TRUE),
                       (NULL,'b',1,FALSE),(NULL,'a',1,FALSE))
          t(table_id,player,is_mw,is_corrupted_game)''')

    def tearDown(self): self.c.close()

    def compare(self,a,z):
        self.assertEqual(self.c.execute(f'DESCRIBE {a}').fetchall(),self.c.execute(f'DESCRIBE {z}').fetchall())
        self.assertEqual(self.c.execute(f'''SELECT COUNT(*) FROM (
          (SELECT * FROM {a} EXCEPT ALL SELECT * FROM {z}) UNION ALL
          (SELECT * FROM {z} EXCEPT ALL SELECT * FROM {a}))''').fetchone()[0],0)

    def test_exact_keys_side_order_nulls_both_datasets(self):
        self.c.execute("UPDATE game_player_narrow SET elo_delta=NULL,map_name=NULL WHERE player='A'")
        for suffix,ds in (('mw',1),('base',0)):
            self.assertTrue(p.create_cards_pair_scope(self.c,suffix,ds,batch_size=None))
            self.c.execute(f'ALTER TABLE cards_pair_scope_{suffix}_narrow RENAME TO expected_{suffix}')
            for size in (1,2,64,65536):
                self.assertTrue(p.create_cards_pair_scope(self.c,suffix,ds,batch_size=size))
                self.compare(f'expected_{suffix}',f'cards_pair_scope_{suffix}_narrow')
            keys=self.c.execute(f'SELECT table_key FROM expected_{suffix} ORDER BY table_key').fetchall()
            self.assertEqual(keys,[(i,) for i in range(len(keys))])
        self.assertEqual(self.c.execute('SELECT Map_0,elo_delta_0 FROM expected_mw WHERE table_id=9').fetchone(),(None,None))

    def test_empty_population(self):
        self.c.execute('DELETE FROM game_player_narrow')
        p.create_cards_pair_scope(self.c,'mw',1,batch_size=None)
        self.c.execute('ALTER TABLE cards_pair_scope_mw_narrow RENAME TO expected')
        self.assertTrue(p.create_cards_pair_scope(self.c,'mw',1))
        self.compare('expected','cards_pair_scope_mw_narrow')

    def test_global_eligibility_guard(self):
        for change in ("DELETE FROM game_player_narrow WHERE table_id=9 AND player='z'",
          "INSERT INTO game_player_narrow SELECT * FROM game_player_narrow WHERE table_id=9 AND player='z'",
          "UPDATE game_player_narrow SET player='A' WHERE table_id=9",
          "UPDATE game_player_narrow SET player=NULL WHERE table_id=9 AND player='z'"):
            self.c.execute('BEGIN')
            try:
                self.c.execute(change)
                self.assertFalse(p.create_cards_pair_scope(self.c,'mw',1,batch_size=1))
                self.assertEqual(self.c.execute("SELECT COUNT(*) FROM duckdb_tables() WHERE table_name='cards_pair_scope_mw_narrow'").fetchone()[0],0)
            finally: self.c.execute('ROLLBACK')

    def test_invalid_budget(self):
        for size in (0,-1,True,1.5,'2'):
            with self.assertRaises(ValueError): p.create_cards_pair_scope(self.c,'mw',1,batch_size=size)

    def test_failed_batch_cleanup(self):
        class Failing:
            def execute(_,sql,*args):
                if sql.startswith('INSERT INTO cards_pair_scope_'): raise RuntimeError('injected')
                return self.c.execute(sql,*args)
        with self.assertRaisesRegex(RuntimeError,'injected'):
            p.create_cards_pair_scope(Failing(),'mw',1,batch_size=1)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM duckdb_tables() WHERE table_name IN ('cards_pair_scope_mw_narrow','cards_pair_index_mw_scratch')").fetchone()[0],0)


if __name__=='__main__': unittest.main()
