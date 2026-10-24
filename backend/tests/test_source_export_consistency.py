"""Offline production-export lifecycle tests: no SDK/network or cloud jobs."""
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from phase5_source_export import prepare_source_export, metadata_differences, SourceChangedDuringExport


GIB = 1024 ** 3


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fingerprints(value):
    return {key: digest(item) for key, item in value.items()}


class Blob:
    def __init__(self, name, owner):
        self.name, self.owner, self.generation = name, owner, 12
        self.value = None

    def exists(self, **kwargs):
        return self.value is not None

    def reload(self, **kwargs):
        pass

    def download_as_text(self, **kwargs):
        return json.dumps(self.value)

    def upload_from_string(self, body, **kwargs):
        if self.owner.fail_diagnostics and '-diagnostics/' in self.name:
            raise OSError('private diagnostics failed')
        if self.owner.fail_latest and self.name.endswith('/latest-manifest.json'):
            raise RuntimeError('precondition failed')
        self.value = json.loads(body)
        self.owner.writes.append((self.name, self.value, kwargs))


class Bucket:
    name = 'private-source-bucket'

    def __init__(self):
        self.blobs, self.writes = {}, []
        self.fail_diagnostics = self.fail_latest = False

    def blob(self, name):
        return self.blobs.setdefault(name, Blob(name, self))


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.base = {'full_sample': {'raw': {'numRows': '7206060', 'numBytes': '5106253413',
            'lastModifiedTime': '1792110631172', 'schema': {'fields': [{'name': 'id'}]}},
            'view': {'query': 'original'}, 'routine': {'definitionBody': 'original'}},
            'logs': {'numRows': '436526', 'lastModifiedTime': '1786407160093'}}
        self.changed = copy.deepcopy(self.base)
        self.changed['full_sample']['raw']['numBytes'] = '5106253369'
        self.bucket = Bucket()
        self.sync = SimpleNamespace(read_metadata=Mock(), fingerprints=fingerprints, digest=digest,
            make_plan=Mock(return_value={'estimated_query_bytes': 5 * GIB}),
            FULL_SQL='SELECT source', LOGS='source.logs')
        self.client = Mock()
        self.client.query.side_effect = self.job
        self.client.extract_table.side_effect = self.job
        self.t = 0
        self.n = 0

    def job(self, *args, **kwargs):
        return SimpleNamespace(job_id=kwargs.get('job_id', 'dry-run'), total_bytes_billed=5 * GIB,
                               result=Mock(), cancel=Mock())

    def unique(self):
        self.n += 1
        return f'{self.n:032x}'

    def sleep(self, seconds):
        self.t += seconds

    def run_export(self, reads, **kwargs):
        if reads is not None:
            self.sync.read_metadata.side_effect = copy.deepcopy(reads)
        options = dict(source_sync=self.sync, bucket=self.bucket, client=self.client,
            query_config=lambda **kw: kw, extract_config=lambda **kw: kw,
            prefix='phase5/source-sync', maintenance_budget=64 * GIB, per_export_cap=8 * GIB,
            clock=lambda: self.t, sleep=self.sleep, unique=self.unique,
            now=lambda: '2026-10-23T23:00:00+00:00')
        options.update(kwargs)
        return prepare_source_export(**options)

    def diagnostics(self):
        return [value for name, value, _ in self.bucket.writes if '-diagnostics/' in name]

    def manifests(self):
        return [value for name, value, _ in self.bucket.writes if name.endswith('/manifest.json')]

    def test_stable_export_commits_with_original_fingerprints(self):
        result = self.run_export([self.base] * 3)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(self.manifests()), 1)
        self.assertEqual(self.manifests()[0]['source_fingerprints'], fingerprints(self.base))
        self.assertEqual(self.diagnostics(), [])
        self.assertEqual(self.client.query.call_count, 1)
        self.assertEqual(self.client.query.call_args.kwargs['job_config']['maximum_bytes_billed'], 8 * GIB)
        self.assertIsNone(self.sync.make_plan.call_args.args[2])

    def test_unchanged_does_not_plan_wait_or_export(self):
        self.bucket.blob('phase5/source-sync/latest-manifest.json').value = {
            'source_fingerprints': fingerprints(self.base), 'generation': 'prior'}
        self.assertEqual(self.run_export([self.base]), {'status': 'unchanged', 'generation': 'prior'})
        self.sync.make_plan.assert_not_called()
        self.client.query.assert_not_called()
        self.assertEqual(self.t, 0)

    def test_44_byte_drift_reexports_once_and_never_commits_bad_attempt(self):
        result = self.run_export([self.base, self.base, self.changed, self.changed, self.changed, self.changed])
        self.assertEqual(result['source_export_attempts'], 2)
        self.assertEqual(self.client.query.call_count, 2)
        self.assertEqual(len(self.manifests()), 1)
        diag = self.diagnostics()[0]
        self.assertEqual(diag['differences'], [{'path': '/full_sample/raw/numBytes',
            'before': '5106253413', 'after': '5106253369'}])
        self.assertNotEqual(diag['generation'], result['generation'])
        self.assertEqual(self.manifests()[0]['source_metadata'], self.changed)
        self.assertEqual(len(diag['jobs']), 2)
        self.assertTrue(all(job['complete'] for job in diag['jobs']))
        self.assertEqual(self.manifests()[0]['source_consistency']['charged_or_reserved_bytes'], 10 * GIB)

    def test_preflight_drift_does_not_export_unstable_snapshot(self):
        self.run_export([self.base, self.changed, self.changed, self.changed, self.changed])
        self.assertEqual(self.client.query.call_count, 1)
        self.assertEqual(self.diagnostics()[0]['phase'], 'metadata_preflight')
        self.assertEqual(self.diagnostics()[0]['jobs'], [])

    def test_repeated_drift_is_bounded_and_leaves_latest_untouched(self):
        with self.assertRaises(SourceChangedDuringExport):
            self.run_export([self.base, self.base, self.changed, self.base, self.base, self.changed])
        self.assertEqual(self.client.query.call_count, 2)
        self.assertEqual(len(self.diagnostics()), 2)
        self.assertEqual(self.manifests(), [])
        self.assertFalse(any(name.endswith('latest-manifest.json') for name, _, _ in self.bucket.writes))

    def test_semantic_and_unknown_changes_are_not_waived(self):
        for family, path, value in [('full_sample', 'view', {'query': 'new SQL'}),
                                    ('full_sample', 'routine', {'definitionBody': 'new code'}),
                                    ('full_sample', 'raw', {'numRows': '1'}),
                                    ('logs', 'unreviewed', {'new': 1})]:
            with self.subTest(family=family, path=path):
                self.setUp()
                changed = copy.deepcopy(self.base)
                changed[family][path] = value
                with self.assertRaises(SourceChangedDuringExport):
                    self.run_export([self.base, self.base, changed], max_attempts=1)
                self.assertEqual(self.manifests(), [])
                self.assertTrue(self.diagnostics()[0]['differences'])

    def test_remaining_budget_caps_retry_query(self):
        self.run_export([self.base, self.base, self.changed, self.changed, self.changed, self.changed],
                        maintenance_budget=11 * GIB)
        caps = [call.kwargs['job_config']['maximum_bytes_billed'] for call in self.client.query.call_args_list]
        self.assertEqual(caps, [8 * GIB, 6 * GIB])

    def test_budget_exhaustion_prevents_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'budget prevents retry'):
            self.run_export([self.base, self.base, self.changed], maintenance_budget=5 * GIB)
        self.assertEqual(self.client.query.call_count, 1)
        self.assertEqual(self.manifests(), [])

    def test_unknown_billed_bytes_reserve_worst_case(self):
        def job(*args, **kw):
            j = self.job(*args, **kw)
            j.total_bytes_billed = None
            return j
        self.client.query.side_effect = job
        with self.assertRaisesRegex(RuntimeError, 'budget prevents retry'):
            self.run_export([self.base, self.base, self.changed], maintenance_budget=8 * GIB)
        self.assertEqual(self.diagnostics()[0]['charged_or_reserved_bytes'], 8 * GIB)

    def test_query_failure_is_not_retried(self):
        self.client.query.side_effect = RuntimeError('query failed')
        with self.assertRaisesRegex(RuntimeError, 'query failed'):
            self.run_export([self.base, self.base])
        self.assertEqual(self.client.query.call_count, 1)
        self.assertEqual(self.diagnostics()[0]['charged_or_reserved_bytes'], 8 * GIB)
        self.assertEqual(self.manifests(), [])

    def test_timeout_cancels_job_without_retry_or_commit(self):
        j = SimpleNamespace(job_id='active-job', result=Mock(side_effect=TimeoutError('timeout')), cancel=Mock())
        self.client.query.side_effect = None
        self.client.query.return_value = j
        with self.assertRaises(TimeoutError):
            self.run_export([self.base, self.base])
        j.cancel.assert_called_once()
        self.assertEqual(self.client.query.call_count, 1)
        self.assertEqual(self.manifests(), [])

    def test_deadline_prevents_retry_before_new_query(self):
        with self.assertRaises(TimeoutError):
            self.run_export([self.base, self.base, self.changed], window_seconds=7)
        self.assertEqual(self.client.query.call_count, 1)
        self.assertEqual(self.manifests(), [])

    def test_diagnostic_storage_failure_never_accepts_mismatch(self):
        self.bucket.fail_diagnostics = True
        with self.assertRaises(SourceChangedDuringExport):
            self.run_export([self.base, self.base, self.changed], max_attempts=1)
        self.assertEqual(self.manifests(), [])

    def test_latest_manifest_uses_generation_precondition(self):
        self.bucket.blob('phase5/source-sync/latest-manifest.json').value = {'source_fingerprints': {}, 'generation': 'old'}
        self.run_export([self.base] * 3)
        latest = next(item for item in self.bucket.writes if item[0].endswith('/latest-manifest.json'))
        self.assertEqual(latest[2]['if_generation_match'], 12)
        self.assertEqual(self.bucket.writes[0][2]['if_generation_match'], 0)

    def test_latest_cas_failure_is_not_retried(self):
        self.bucket.fail_latest = True
        with self.assertRaisesRegex(RuntimeError, 'precondition'):
            self.run_export([self.base] * 3)
        self.assertEqual(self.client.query.call_count, 1)
        self.assertFalse(any(name.endswith('latest-manifest.json') for name, _, _ in self.bucket.writes))

    def test_plan_rejects_over_budget_without_export(self):
        self.sync.make_plan.side_effect = RuntimeError('ceiling')
        with self.assertRaisesRegex(RuntimeError, 'ceiling'):
            self.run_export([self.base, self.base])
        self.client.query.assert_not_called()
        self.assertEqual(self.manifests(), [])

    def test_diff_preserves_type_missing_null_and_array_order(self):
        self.assertTrue(metadata_differences({'a': 1}, {'a': True}))
        self.assertTrue(metadata_differences({}, {'a': None}))
        self.assertTrue(metadata_differences([1, 2], [2, 1]))
        self.assertEqual(metadata_differences({'b': 2, 'a': 1}, {'a': 1, 'b': 2}), [])

    def test_invalid_limits_and_prefix_rejected(self):
        for kw in [{'max_attempts': 3}, {'window_seconds': 901}, {'maintenance_budget': 0},
                   {'per_export_cap': 9 * GIB}, {'prefix': "bad'prefix"}]:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.run_export([], **kw)

    def test_metadata_and_plan_requests_have_bounded_timeouts_and_no_hidden_retries(self):
        def read(client):
            client.get_table('source.raw')
            client.get_routine('source.routine')
            return self.base
        self.sync.read_metadata = Mock(side_effect=read)
        def plan(client, *args):
            client.query('dry run', job_config={'dry_run': True})
            return {'estimated_query_bytes': 1}
        self.sync.make_plan.side_effect = plan
        self.run_export(None)
        for method in (self.client.get_table, self.client.get_routine):
            self.assertTrue(method.call_args_list)
            for call in method.call_args_list:
                self.assertLessEqual(call.kwargs['timeout'], 30)
                self.assertIsNone(call.kwargs['retry'])
        self.assertIsNone(self.client.query.call_args_list[0].kwargs['job_retry'])
        self.assertIsNone(self.client.query.call_args_list[0].kwargs['retry'])


class WrapperTests(unittest.TestCase):
    def test_working_and_sealed_main_delegate_only_to_helper(self):
        root = Path(__file__).resolve().parents[1]
        # A public source checkout has no private sealed deployment candidate.
        # Validate that extra control too whenever it is present locally.
        paths = [root / 'main.py']
        candidate = root / 'reports/fingerprint-investigation-20261023/repair-candidate/main.py'
        if candidate.is_file():
            paths.append(candidate)
        for path in paths:
            with self.subTest(path=path):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_prepare_private_source_export')
                ns = {'storage': SimpleNamespace(Client=Mock()), 'bigquery': SimpleNamespace(QueryJobConfig=Mock(), ExtractJobConfig=Mock()),
                    'PRIVATE_SOURCE_BUCKET': 'private-source', 'PRIVATE_SOURCE_PREFIX': 'phase5/source-sync',
                    'MAINTENANCE_BIGQUERY_MAX_BYTES_BILLED': 64 * GIB, '_utc_now_iso': lambda: 'now'}
                exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
                fake_sync = SimpleNamespace(cloud_client=Mock())
                with patch.dict('sys.modules', {'phase5_source_sync': fake_sync}), \
                     patch('phase5_source_export.prepare_source_export', return_value={'status': 'mocked'}) as prepare:
                    self.assertEqual(ns['_prepare_private_source_export'](), {'status': 'mocked'})
                self.assertEqual(prepare.call_args.kwargs['per_export_cap'], 8 * GIB)
                self.assertEqual(prepare.call_args.kwargs['maintenance_budget'], 64 * GIB)


if __name__ == '__main__':
    unittest.main()
