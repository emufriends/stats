import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from reports.profile_snapshot_pages_20261002 import PhaseProfiler


class SnapshotPageProfilerTests(unittest.TestCase):
    def test_each_phase_has_its_own_resident_peak(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch('threading.Thread'):
            values = iter((10, 20, 3, 8))
            profiler = PhaseProfiler(Path(folder) / 'measurements.json', lambda: next(values))
            first = profiler.wrap(lambda: 1, lambda a, k: {'page': 'first'})
            second = profiler.wrap(lambda: 2, lambda a, k: {'page': 'second'})
            self.assertEqual(first(), 1)
            self.assertEqual(second(), 2)
            profiler.close()
            self.assertEqual([r['sampled_rss_peak_bytes'] for r in profiler.records], [20, 8])
            self.assertEqual(json.loads(profiler.output.read_text()), profiler.records)

    def test_failure_is_recorded_and_propagated(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch('threading.Thread'):
            profiler = PhaseProfiler(Path(folder) / 'measurements.json', lambda: 10)
            def fail():
                raise ValueError('fixture')
            measured = profiler.wrap(fail, lambda a, k: {'page': 'failed'})
            with self.assertRaises(ValueError):
                measured()
            self.assertEqual(profiler.records[0]['status'], 'failed')
            self.assertEqual(profiler.records[0]['error_type'], 'ValueError')
            self.assertIsNone(profiler.current)
            profiler.close()


if __name__ == '__main__':
    unittest.main()
