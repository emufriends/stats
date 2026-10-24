"""Independent scratch references and fail-closed numerical validation."""
import hashlib
from pathlib import Path
import unittest

from phase5_card_reference_check import compare_results, reconcile
from phase5_card_validation_references import create_validation_references, VALIDATION_RELATIONS
from phase5_refresh_dependencies import LOG_RELATIONS
from phase5_refresh_workflow import EXPECTED_RELATIONS


class IndependentCardReferenceTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.c=duckdb.connect()
        self.c.execute('SET threads=1')
        self.c.execute('SET preserve_insertion_order=false')

    def tearDown(self):
        self.c.close()

    def seed_comparison(self):
        self.c.execute("CREATE TABLE expected AS SELECT 'A' AS card_1,'B' AS card_2,1.0::DOUBLE AS delta_1,2::BIGINT AS n_played")
        self.c.execute('CREATE TABLE observed AS SELECT * FROM expected')

    def test_fail_closed_counts_missing_pairs_nulls_and_mean_changes(self):
        self.seed_comparison()
        self.assertEqual(compare_results(self.c)['status'],'pass')
        for change in ('UPDATE observed SET n_played=3',
                       'UPDATE observed SET delta_1=1.1',
                       'UPDATE observed SET delta_1=NULL',
                       'DELETE FROM observed'):
            self.c.execute(change)
            self.assertEqual(compare_results(self.c)['status'],'fail')
            self.c.execute('DELETE FROM observed')
            self.c.execute('INSERT INTO observed SELECT * FROM expected')
        self.c.execute('INSERT INTO observed SELECT * FROM expected')
        with self.assertRaises(ValueError):compare_results(self.c)

    def test_only_unrounded_reduction_noise_is_tolerated(self):
        self.seed_comparison()
        self.c.execute('UPDATE observed SET delta_1=1.0000000000000002')
        self.assertEqual(compare_results(self.c)['status'],'pass')
        self.c.execute('UPDATE observed SET delta_1=1.0000001')
        self.assertEqual(compare_results(self.c)['status'],'fail')

    def test_validation_only_inventory_is_not_a_serving_requirement(self):
        self.assertTrue(set(VALIDATION_RELATIONS).isdisjoint(LOG_RELATIONS))
        self.assertTrue(set(VALIDATION_RELATIONS).isdisjoint(EXPECTED_RELATIONS))

    def test_archived_sample_references_preserve_values_and_source_file(self):
        root=Path(__file__).resolve().parents[1]
        source=root/'reports/quick-win-qualification-20261006/candidate-sample/phase2_private_data/generations/quick-win-sample.duckdb'
        if not source.exists():self.skipTest('Archived qualification sample unavailable')
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        self.c.execute(f"ATTACH '{source.as_posix()}' AS baseline (READ_ONLY)")
        for name in ('card_play_narrow','game_player_narrow','corrupted_tables_narrow'):
            self.c.execute(f'CREATE VIEW {name} AS SELECT * FROM baseline.{name}')
        create_validation_references(self.c)
        for name in VALIDATION_RELATIONS:
            self.assertEqual(self.c.execute(f'DESCRIBE {name}').fetchall(),self.c.execute(f'DESCRIBE baseline.{name}').fetchall())
            diff=self.c.execute(f'''SELECT COUNT(*) FROM (
                (SELECT * FROM {name} EXCEPT ALL SELECT * FROM baseline.{name})
                UNION ALL (SELECT * FROM baseline.{name} EXCEPT ALL SELECT * FROM {name}))''').fetchone()[0]
            self.assertEqual(diff,0,name)
        self.assertEqual(reconcile(source)['status'],'pass')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
