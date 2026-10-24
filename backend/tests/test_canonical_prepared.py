import unittest
import tempfile
from pathlib import Path
from unittest import mock

from phase3_duckdb_service import _load_duckdb
from phase2_local_vertical_slice import (
    create_canonical_player_relations, create_prepared_full_sample_relation,
    _drop_relation,
)
import tests.test_phase2_canonical_population as fixtures
from reports.benchmark_refresh_builder_next_20261004 import multiset_fingerprint


class CanonicalPreparedTests(unittest.TestCase):
    def connection(self):
        fixture = fixtures.CanonicalPopulationTests()
        fixture.duckdb = _load_duckdb()
        return fixture._connection()

    def assert_legacy_parity(self, connection, expected_method):
        with mock.patch.dict('os.environ', {'DUCKDB_CANONICAL_UPDATE_BATCHES':'1'}):
            create_canonical_player_relations(connection)
        connection.execute('CREATE TABLE expected AS SELECT * FROM prepared_full_sample_narrow')
        schema = connection.execute('DESCRIBE expected').fetchall()
        for batches in (2, 32):
            with mock.patch.dict('os.environ', {'DUCKDB_CANONICAL_UPDATE_BATCHES':str(batches)}):
                result = create_prepared_full_sample_relation(connection)
            self.assertEqual(result['method'], expected_method)
            self.assertEqual(schema, connection.execute('DESCRIBE prepared_full_sample_narrow').fetchall())
            self.assertEqual(connection.execute('''SELECT COUNT(*) FROM (
              (SELECT * FROM expected EXCEPT ALL SELECT * FROM prepared_full_sample_narrow)
              UNION ALL (SELECT * FROM prepared_full_sample_narrow EXCEPT ALL SELECT * FROM expected)
            )''').fetchone()[0], 0)

    def test_batches_preserve_all_columns_types_corruption_and_malformed_tables(self):
        c = self.connection()
        try:
            self.assert_legacy_parity(c, 'copy_update')
        finally:
            c.close()

    def test_duplicate_keys_fall_back_without_multiplying_observations(self):
        c = self.connection()
        try:
            c.execute("INSERT INTO source_full_sample SELECT * FROM source_full_sample WHERE player='Alice'")
            self.assert_legacy_parity(c, 'copy_update')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM prepared_full_sample_narrow').fetchone()[0], 8)
        finally:
            c.close()

    def test_missing_keys_fall_back_and_preserve_unmatched_null_payload(self):
        for column in ('table_id', 'player'):
            c = self.connection()
            try:
                c.execute(f"UPDATE source_full_sample SET {column}=NULL WHERE player='Alice'")
                self.assert_legacy_parity(c, 'copy_update')
            finally:
                c.close()

    def test_empty_population(self):
        c = self.connection()
        try:
            c.execute('DELETE FROM source_full_sample')
            self.assert_legacy_parity(c, 'copy_update')
        finally:
            c.close()

    def test_multiset_fingerprint_retains_duplicate_weights_nulls_and_field_values(self):
        c = _load_duckdb().connect()
        try:
            c.execute('''CREATE TABLE original AS SELECT * FROM (VALUES
              (1,NULL::VARCHAR,[1,2]),(1,NULL::VARCHAR,[1,2]),
              (2,'é',[]),(2,'é',[])) t(n,label,items)''')
            c.execute('CREATE TABLE reversed AS SELECT * FROM original ORDER BY n DESC')
            self.assertEqual(multiset_fingerprint(c,'original'),multiset_fingerprint(c,'reversed'))
            c.execute('UPDATE reversed SET n=n+2')
            # Both populations have an even duplicate count and XOR would
            # cancel; lane sums must still distinguish their complete rows.
            self.assertNotEqual(multiset_fingerprint(c,'original'),multiset_fingerprint(c,'reversed'))
        finally:
            c.close()

    def test_raw_schema_cannot_shadow_a_derived_field(self):
        c = self.connection()
        try:
            create_canonical_player_relations(c)
            c.execute('ALTER TABLE source_full_sample ADD COLUMN is_completed_game BOOLEAN')
            with self.assertRaises(_load_duckdb().CatalogException):
                create_prepared_full_sample_relation(c)
        finally:
            c.close()

    def test_cleanup_never_drops_an_attached_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory)/'reference.duckdb'
            reference = _load_duckdb().connect(str(filename))
            reference.execute('CREATE TABLE protected AS SELECT 42 AS value')
            reference.close()
            c = _load_duckdb().connect()
            try:
                c.execute("ATTACH '"+str(filename).replace("'", "''")+"' AS reference (READ_ONLY)")
                _drop_relation(c, 'protected')
                for kind in ('VIEW', 'TABLE'):
                    c.execute(f'CREATE {kind} main.protected AS SELECT * FROM reference.protected')
                    _drop_relation(c, 'protected')
                    self.assertEqual(c.execute('SELECT * FROM reference.protected').fetchall(), [(42,)])
            finally:
                c.close()


if __name__ == '__main__':
    unittest.main()
