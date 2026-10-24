"""Unchanged source-family transfers reuse only checksum-validated local files."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import phase5_refresh_worker as worker


class SourceReuseTests(unittest.TestCase):
    def fixture(self, root):
        previous = root / 'previous'
        previous.mkdir()
        (previous / 'full_sample-0.parquet').write_bytes(b'old-full')
        (previous / 'logs-0.parquet').write_bytes(b'unchanged-logs')
        worker.commit_source_inventory(previous, {
            'generation': 'old', 'source_fingerprints': {'full_sample': 'a','logs': 'b'},
        })
        remote = {'status': 'ok', 'generation': 'new',
                  'source_fingerprints': {'full_sample': 'c','logs': 'b'},
                  'export': {'full_sample_uri':'gs://private/full_sample-*.parquet',
                             'logs_uri':'gs://private/logs-*.parquet'}}
        return previous, remote

    def test_changed_full_does_not_redownload_unchanged_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous, remote = self.fixture(root)
            def transfer(*args, **kwargs):
                self.assertEqual(args[-2], remote['export']['full_sample_uri'])
                (Path(args[-1]) / 'full_sample-0.parquet').write_bytes(b'new-full')
            with patch.object(worker, 'SOURCE_DIR', root), \
                 patch.object(worker, 'read_json_from', return_value=remote), \
                 patch.object(worker, 'gcloud', side_effect=transfer) as download:
                candidate = worker.materialize_latest_export(previous)
            self.assertEqual(download.call_count, 1)
            self.assertEqual((candidate/'logs-0.parquet').read_bytes(), b'unchanged-logs')
            manifest = json.loads((candidate/'manifest.json').read_text())
            worker.validate_files(candidate, manifest)
            self.assertEqual((previous/'full_sample-0.parquet').read_bytes(), b'old-full')

    def test_corrupt_local_reuse_aborts_without_committing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous, remote = self.fixture(root)
            (previous/'logs-0.parquet').write_bytes(b'broken')
            with patch.object(worker,'SOURCE_DIR',root), \
                 patch.object(worker,'read_json_from',return_value=remote), \
                 patch.object(worker,'gcloud') as download:
                with self.assertRaises(RuntimeError):
                    worker.materialize_latest_export(previous)
            download.assert_not_called()
            self.assertFalse((root/'.source-new').exists())

    def test_accounting_failure_cannot_invalidate_success(self):
        with patch.object(worker,'WORK_DIR',Path('/nonexistent-accounting-directory')), \
             patch.object(worker.sys,'stderr'):
            worker.save_accounting('test', {'state':'succeeded'})

    def test_detailed_failure_stays_local_and_never_uploads_to_public_bucket(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(worker,'WORK_DIR',Path(directory)), \
                 patch.object(worker,'gcloud') as upload:
                worker.write_diagnostic('test', ValueError('private SQL details'))
            upload.assert_not_called()
            self.assertIn('private SQL details', (Path(directory)/'test.failure.txt').read_text())


if __name__ == '__main__':
    unittest.main()
