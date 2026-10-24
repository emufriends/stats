import json
import tempfile
import unittest
from pathlib import Path

from phase3_duckdb_service import _load_duckdb
from phase5_refresh_dependencies import log_dependency_signature,reuse_log_relations,LOG_RELATIONS
from phase3_cards_pair_contracts import create_cards_pair_scope
from phase5_operational_controls import _runtime_code_paths
from phase5_refresh_dependencies import LOG_PRODUCER_INPUTS


class RefreshDependencyTests(unittest.TestCase):
    def test_producer_inventory_excludes_snapshot_and_publication(self):
        root = Path(__file__).resolve().parents[1]
        names = {path.name for path in _runtime_code_paths(root, LOG_PRODUCER_INPUTS)}
        self.assertIn('phase5_refresh_metrics.py', names)
        self.assertIn('phase4_local_scope.py', names)
        self.assertNotIn('phase5_snapshot_builder.py', names)
        self.assertNotIn('phase5_publish_release.py', names)

    def fixture(self,path,*, extra_id=None,delta=0.5,duplicate=False):
        conn=_load_duckdb().connect(str(path))
        conn.execute('''CREATE TABLE game_player_narrow AS SELECT
            10::BIGINT AS table_id,player,1 AS is_mw,'Map 1' AS map_name,
            TIMESTAMP '2026-01-01' AS game_ended_at,player AS starting_position,
            400.0 AS pre_match_elo,400.0 AS opponent_pre_match_elo,?::DOUBLE AS elo_delta,
            TRUE AS is_completed_game,'S14' AS arena_season,TRUE AS is_arena_game,
            FALSE AS is_tournament,FALSE AS is_corrupted_game
            FROM (VALUES ('a'),('b')) p(player)''',[delta])
        if extra_id is not None:
            conn.execute('INSERT INTO game_player_narrow SELECT * REPLACE(? AS table_id) FROM game_player_narrow',[extra_id])
        conn.execute('CREATE TABLE prepared_full_sample_narrow AS SELECT * FROM game_player_narrow')
        conn.execute("CREATE TABLE source_logs AS SELECT 10::BIGINT AS table_id,'a' AS player,[NULL,'x'] AS events")
        if duplicate:
            conn.execute('INSERT INTO source_logs SELECT * FROM source_logs')
        for name in LOG_RELATIONS:
            conn.execute(f'CREATE TABLE {name} AS SELECT 42 AS payload UNION ALL SELECT 42 AS payload')
        for suffix,dataset in (('mw',1),('base',0)):
            create_cards_pair_scope(conn,suffix,dataset)
        return conn

    def test_nonlog_growth_reuses_but_key_shift_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory)/'parent.duckdb'
            conn=self.fixture(parent)
            signature=log_dependency_signature(conn)
            conn.close()
            for extra, expected in ((20,True),(1,False)):
                candidate=Path(directory)/f'candidate-{extra}.duckdb'
                conn=self.fixture(candidate,extra_id=extra)
                try:
                    current=log_dependency_signature(conn)
                    self.assertEqual(current,signature)
                    decision={}
                    result=reuse_log_relations(conn,parent,{'log_dependency':signature},current,decision)
                    self.assertEqual(result is not None,expected)
                    self.assertEqual(decision['reason'], 'reused' if expected else 'shifted_numeric_table_keys')
                    if expected:
                        self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_seen_narrow').fetchone()[0],2)
                        self.assertEqual(result[0]['cards_pair_scope_mw_narrow'],2)
                finally:
                    conn.close()

    def test_logged_correction_and_duplicate_multiplicity_invalidate(self):
        with tempfile.TemporaryDirectory() as directory:
            conn=self.fixture(Path(directory)/'parent.duckdb')
            before=log_dependency_signature(conn)
            conn.close()
            for index,options in enumerate(({'delta':0.7},{'duplicate':True})):
                conn=self.fixture(Path(directory)/f'candidate-{index}.duckdb',**options)
                try:
                    after=log_dependency_signature(conn)
                    self.assertNotEqual(before['population_sha256'],after['population_sha256'])
                    self.assertIsNone(reuse_log_relations(conn,Path(directory)/'parent.duckdb',{'log_dependency':before},after))
                finally:
                    conn.close()


if __name__=='__main__':
    unittest.main()
