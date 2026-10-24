"""Cache retention/concurrency and complete offline Records serialization."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

from phase3_duckdb_service import (Phase3ResponseCache, Phase3PersistentResponseCache,
                                  DuckDBServingStore, QueryDeadlineExceeded)
from phase4_local_routes import _final_records_sql
from phase5_snapshot_builder import _build_most_icons_stream, _write_json


class CacheBudgetTests(unittest.TestCase):
    def test_bytes_eviction_replacement_and_mutation_isolation(self):
        cache = Phase3ResponseCache(max_items=10, max_bytes=100, max_entry_bytes=100)
        value = {'data': ['é' * 10, None, -0.0, 1.2345678901234567]}
        cache.put('a', value)
        original = json.loads(json.dumps(value))
        value['data'][0] = 'changed'
        self.assertEqual(cache.get('a'), original)
        cache.get('a')['data'].append('changed')
        self.assertEqual(cache.get('a'), original)
        cache.put('b', original)
        self.assertIsNone(cache.get('a'))
        cache.put('b', {'data': [1]})
        self.assertEqual(cache._bytes, len(cache._items['b']))
        cache.put('b', {'data': ['x' * 101]})
        self.assertIsNone(cache.get('b'))
        self.assertEqual(cache._bytes, 0)

    def test_oversize_entries_keep_persistent_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            persistent = Phase3PersistentResponseCache(Path(folder) / 'cache.sqlite3')
            cache = Phase3ResponseCache(persistent=persistent, max_bytes=100,
                                        max_entry_bytes=20)
            value = {'data': ['large response'] * 100}
            cache.put('large', value)
            self.assertEqual(cache._bytes, 0)
            first = cache.get('large')
            self.assertEqual(first, value)
            first['data'].clear()
            self.assertEqual(cache.get('large'), value)
            self.assertEqual(cache._items, {})

    def test_concurrent_insert_and_persistent_hits_keep_exact_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Phase3ResponseCache(max_items=8, max_bytes=1000, max_entry_bytes=200,
                persistent=Phase3PersistentResponseCache(Path(folder) / 'cache.sqlite3'))
            for index in range(40):
                cache.persistent.put(str(index), {'data': [index, 'x' * 60]})

            def access(index):
                key = str(index % 40)
                value = cache.get(key)
                self.assertIsNotNone(value)
                value['data'].append('caller mutation')
                cache.put('writer-' + key, {'data': [index]})

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(access, range(160)))
            self.assertEqual(cache._bytes, sum(map(len, cache._items.values())))
            self.assertLessEqual(cache._bytes, cache.max_bytes)
            self.assertLessEqual(len(cache._items), cache.max_items)
            self.assertEqual(cache.get('1')['data'], [1, 'x' * 60])


class RecordsStreamTests(unittest.TestCase):
    def test_cursor_is_bounded_and_closes_on_early_exit_and_deadline(self):
        closed = []
        interrupted = threading.Event()

        class Cursor:
            description = [('value',)]
            calls = 0
            slow = False

            def execute(self, sql, parameters):
                return self

            def fetchmany(self, size):
                self.calls += 1
                if self.slow:
                    time.sleep(0.04)
                    if interrupted.is_set():
                        raise RuntimeError('interrupted')
                return [(1,), (2,)] if self.calls == 1 else []

            def interrupt(self):
                interrupted.set()

            def fetchall(self):
                raise AssertionError('offline path must not fetchall')

        cursor = Cursor()

        @contextmanager
        def connection():
            try:
                yield SimpleNamespace(generation_id='g1'), cursor
            finally:
                closed.append(True)

        store = DuckDBServingStore(SimpleNamespace(), query_timeout_seconds=1)
        store.connection = connection
        with store.query_batches('SELECT value', batch_size=2) as (_, batches):
            self.assertEqual(list(next(batches)), [{'value': 1}, {'value': 2}])
        self.assertEqual(closed, [True])
        cursor.calls = 0
        cursor.slow = True
        store.query_timeout_seconds = 0.01
        with self.assertRaises(QueryDeadlineExceeded):
            with store.query_batches('SELECT value', batch_size=2) as (_, batches):
                list(next(batches))
        self.assertEqual(closed, [True, True])

    def test_complete_stream_preserves_json_bytes_and_uses_one_query(self):
        rows = [{'n': 10.0, 'icon': 'Birds', 'player': 'Zoë', 'score': None,
                 'table_id': str(index)} for index in range(2501)]
        generation = SimpleNamespace(generation_id='g1', data_version='v1')
        calls = []

        class Store:
            @contextmanager
            def query_batches(self, sql, parameters, *, batch_size):
                calls.append(batch_size)
                yield generation, (iter(rows[start:start + batch_size])
                                   for start in range(0, len(rows), batch_size))

        adapter = SimpleNamespace(store=Store(), normalize_request=lambda request:
                                  {**request, 'view': 'phase4_final_records_most_icons'})
        expected = {'status': 'ok', 'source': 'duckdb_private', 'generation': 'g1',
                    'data_version': 'v1', 'view': 'phase4_final_records_most_icons',
                    'data': rows, 'row_count': len(rows), 'cache_status': 'private_miss',
                    'contract_schema_version': 18}
        from phase3_duckdb_service import PUBLIC_CONTRACT_SCHEMA_VERSION
        expected['contract_schema_version'] = PUBLIC_CONTRACT_SCHEMA_VERSION
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'stream.json'
            reference = Path(folder) / 'reference.json'
            profile = {}
            result = _build_most_icons_stream(adapter, 1, output, profile)
            _write_json(reference, expected)
            self.assertEqual(output.read_bytes(), reference.read_bytes())
            self.assertEqual(result['row_count'], 2501)
            self.assertEqual(calls, [1024])
            self.assertEqual(profile['query_count'], 1)
            self.assertEqual(list(Path(folder).glob('records-icons-*')), [])

    def test_offline_scope_uses_identical_sql_except_pagination(self):
        request = {'is_mw': 1, 'opponent_elo_min': 0}
        public_sql, public_parameters = _final_records_sql(request, 'most_icons')
        offline_sql, offline_parameters = _final_records_sql(request, 'most_icons', paginate=False)
        self.assertEqual(public_sql.replace('LIMIT ? OFFSET ?', '').strip(), offline_sql.strip())
        self.assertEqual(public_parameters, offline_parameters)
        with self.assertRaises(ValueError):
            _final_records_sql(request, 'highest_scores', paginate=False)


if __name__ == '__main__':
    unittest.main()
