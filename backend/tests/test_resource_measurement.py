"""Refresh resource measurement is numbers-only, best effort and non-intrusive."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import phase5_refresh_metrics as metrics
from phase5_refresh_metrics import ResourceSampler, TimedConnection
import phase5_snapshot_builder as builder


def _fake_cgroup(root: Path):
    slice_dir = root / 'ark-analytics.slice'
    service = slice_dir / 'worker.service'
    service.mkdir(parents=True)
    (service / 'memory.stat').write_text('anon 1000\nfile 5000\nkernel 7\n')
    (service / 'memory.current').write_text('6500\n')
    (slice_dir / 'memory.stat').write_text('anon 1500\nfile 5100\n')
    (slice_dir / 'memory.current').write_text('7000\n')
    (slice_dir / 'memory.events').write_text('low 0\nhigh 0\nmax 3\noom 0\noom_kill 0\n')
    return service, slice_dir


class ResourceSamplerTests(unittest.TestCase):
    def test_window_reports_cgroup_maxima_and_event_deltas(self):
        with tempfile.TemporaryDirectory() as folder:
            service, slice_dir = _fake_cgroup(Path(folder))
            sampler = ResourceSampler(interval=0.01)
            sampler._service, sampler._slice = service, slice_dir
            window = sampler.begin()
            (slice_dir / 'memory.events').write_text('low 0\nhigh 0\nmax 10\noom 0\noom_kill 0\n')
            time.sleep(0.05)
            result = sampler.end(window)
            self.assertEqual(result['peak_service_cgroup_anon_bytes'], 1000)
            self.assertEqual(result['peak_service_cgroup_file_bytes'], 5000)
            self.assertEqual(result['peak_slice_current_bytes'], 7000)
            self.assertEqual(result['slice_memory_events_delta']['max'], 7)
            self.assertEqual(result['slice_memory_events_delta']['oom_kill'], 0)
            self.assertGreaterEqual(result['resource_samples'], 2)

    def test_missing_cgroup_gives_none_not_an_error(self):
        sampler = ResourceSampler(interval=0.01)
        sampler._service = sampler._slice = Path('/nonexistent/cgroup')
        window = sampler.begin()
        result = sampler.end(window)
        self.assertIsNone(result['peak_slice_current_bytes'])
        self.assertIsNone(result['slice_memory_events_delta'])

    def test_measure_records_failure_and_reraises(self):
        sink = []
        sampler = ResourceSampler(interval=0.01)
        with self.assertRaises(ValueError):
            with sampler.measure(sink, 'step', page='x'):
                raise ValueError('private failure details')
        self.assertEqual(sink[0]['state'], 'failed')
        self.assertNotIn('private failure details', json.dumps(sink))

    def test_a_failing_sink_never_breaks_the_measured_work(self):
        class Broken(list):
            def append(self, _):
                raise OSError('disk full')
        sampler = ResourceSampler(interval=0.01)
        with sampler.measure(Broken(), 'step'):
            value = 3
        self.assertEqual(value, 3)

    def test_measurement_does_not_change_the_lifetime_highwater_semantics(self):
        before = metrics.rss_highwater_bytes()
        sampler = ResourceSampler(interval=0.01)
        window = sampler.begin()
        self.assertGreaterEqual(metrics.rss_highwater_bytes() or 0, (before or 0))
        self.assertIsNotNone(window)
        sampler.end(window)

    def test_failed_thread_start_does_not_leak_a_window(self):
        sampler = ResourceSampler()
        with mock.patch.object(metrics.threading.Thread, 'start', side_effect=RuntimeError('unavailable')):
            self.assertIsNone(sampler.begin())
        self.assertEqual(sampler._windows, [])
        self.assertIsNone(sampler._thread)

    def test_failed_final_sample_detaches_window(self):
        sampler = ResourceSampler()
        window = sampler.begin()
        with mock.patch.object(sampler, '_sample', side_effect=RuntimeError('unavailable')):
            self.assertEqual(sampler.end(window), {})
        self.assertEqual(sampler._windows, [])

    def test_setup_failure_does_not_skip_work_or_mask_its_error(self):
        with mock.patch.object(metrics, 'get_sampler', side_effect=RuntimeError('unavailable')):
            with metrics.measure_resources([], 'test'):
                result = 7
            self.assertEqual(result, 7)
            with self.assertRaisesRegex(ValueError, 'original analytical error'):
                with metrics.measure_resources([], 'test'):
                    raise ValueError('original analytical error')

    def test_finalization_failure_does_not_mask_original_error(self):
        class BrokenContext:
            def __enter__(self):
                return {}

            def __exit__(self, *args):
                raise RuntimeError('telemetry error')

        sampler = mock.Mock()
        sampler.measure.return_value = BrokenContext()
        with mock.patch.object(metrics, 'get_sampler', return_value=sampler):
            with metrics.measure_resources([], 'test'):
                result = 7
            self.assertEqual(result, 7)
            with self.assertRaisesRegex(ValueError, 'original analytical error'):
                with metrics.measure_resources([], 'test'):
                    raise ValueError('original analytical error')


class TimelineTests(unittest.TestCase):
    def test_timeline_file_receives_bounded_numeric_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'timeline.jsonl'
            with mock.patch.dict('os.environ', {'ARK_RESOURCE_TIMELINE_FILE': str(path)}):
                sampler = ResourceSampler(interval=0.01)
                window = sampler.begin()
                time.sleep(0.1)
                sampler.end(window)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            # Rate-limited to ~30 s per sampler; another test's idle sampler may add a row.
            self.assertTrue(1 <= len(rows) <= 3)
            self.assertIn('rss', rows[0])

    def test_unwritable_timeline_is_ignored(self):
        with mock.patch.dict('os.environ', {'ARK_RESOURCE_TIMELINE_FILE': '/nonexistent/dir/t.jsonl'}):
            sampler = ResourceSampler(interval=0.01)
            window = sampler.begin()
            time.sleep(0.05)
            self.assertIn('resource_samples', sampler.end(window))


class TimedConnectionMeasurementTests(unittest.TestCase):
    def test_statement_records_gain_resource_fields_without_sql_or_values(self):
        native = mock.Mock()
        connection = TimedConnection(native)
        connection.execute('CREATE TABLE safe_relation AS SELECT ?', ['private-value'])
        record = connection.statements[0]
        for key in ('peak_process_rss_bytes', 'peak_slice_current_bytes', 'peak_spill_bytes',
                    'slice_memory_events_delta', 'resource_samples'):
            self.assertIn(key, record)
        self.assertEqual(record['relation'], 'safe_relation')
        self.assertNotIn('private-value', json.dumps(record))
        native.execute.assert_called_once()

    def test_sampler_failure_does_not_fail_the_statement(self):
        native = mock.Mock()
        with mock.patch.object(metrics.ResourceSampler, 'begin', side_effect=RuntimeError('boom')), \
                mock.patch.object(metrics.ResourceSampler, 'end', side_effect=RuntimeError('boom')):
            TimedConnection(native).execute('SELECT 1')   # must not raise
        native.execute.assert_called_once()
        sampler = ResourceSampler(interval=0.01)
        with mock.patch.object(ResourceSampler, '_sample', side_effect=RuntimeError('boom')):
            self.assertIsNone(sampler.begin())
            self.assertEqual(sampler.end(None), {})


class SnapshotProfileTests(unittest.TestCase):
    def test_measure_is_a_noop_when_not_profiling(self):
        self.assertIsNone(builder._PROFILE)
        with builder._measure('snapshot', page='x') as record:
            record['ignored'] = 1

    def test_profile_sink_journals_each_record_and_survives_unwritable_path(self):
        with tempfile.TemporaryDirectory() as folder:
            sink = builder._ProfileSink(Path(folder) / 'resource-profile.jsonl')
            sink.append({'label': 'snapshot', 'seconds': 1.0})
            self.assertEqual(len(sink), 1)
            self.assertEqual(json.loads((Path(folder) / 'resource-profile.jsonl').read_text())['label'], 'snapshot')
            broken = builder._ProfileSink(Path(folder) / 'missing' / 'x.jsonl')
            broken.append({'label': 'x'})
            self.assertEqual(len(broken), 1)

    def test_write_resource_profile_is_best_effort_and_numbers_only(self):
        class Adapter:
            class offline_component_cis:
                population_log = [{'label': 'component_population', 'kind': 'card'}]
                lookups = 4
                population_queries = 1
        with tempfile.TemporaryDirectory() as folder:
            builder._PROFILE = builder._ProfileSink(Path(folder) / 'j.jsonl')
            try:
                builder._PROFILE.append({'label': 'default_pack', 'seconds': 2.0})
                builder._write_resource_profile(Path(folder), Adapter)
            finally:
                builder._PROFILE = None
            profile = json.loads((Path(folder) / 'resource-profile.json').read_text())
            self.assertEqual(profile['component_ci_lookups'], 4)
            self.assertEqual(profile['records'][0]['label'], 'default_pack')
            builder._write_resource_profile(Path(folder) / 'absent', Adapter)  # must not raise


if __name__ == '__main__':
    unittest.main()
