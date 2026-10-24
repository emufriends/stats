import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from phase5_refresh_metrics import RefreshTimings, TimedConnection
from phase5_storage_io import gzip_file, upload, copy_object, read_json


class RefreshEfficiencyTests(unittest.TestCase):
    def test_gzip_is_deterministic_lossless_and_cleanup_is_guaranteed(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'data.json'
            original.write_bytes(b'{"value":42}\n' * 10000)
            with gzip_file(original) as compressed:
                first = compressed.read_bytes()
                self.assertEqual(gzip.decompress(first), original.read_bytes())
                former_path = compressed
            self.assertFalse(former_path.exists())
            with gzip_file(original) as compressed:
                self.assertEqual(first, compressed.read_bytes())

    @mock.patch('phase5_storage_io.blob')
    def test_upload_headers_and_immutable_precondition(self, blob):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'x.json'
            path.write_text('{"x":1}')
            observed = []
            blob.return_value.upload_from_filename.side_effect = lambda name, **kw: observed.append((gzip.decompress(Path(name).read_bytes()),kw))
            upload(path, 'gs://bucket/x', content_type='application/json', cache_control='immutable', immutable=True)
            self.assertEqual(observed[0][0], path.read_bytes())
            self.assertEqual(observed[0][1]['if_generation_match'], 0)
            self.assertEqual(blob.return_value.content_encoding, 'gzip')
            self.assertEqual(blob.return_value.cache_control, 'immutable')

    @mock.patch('phase5_storage_io.blob')
    def test_copy_pins_source_generation_and_handles_rewrite_token(self, factory):
        source, destination = mock.Mock(), mock.Mock()
        source.generation = 123
        source.cache_control = 'private,no-store,max-age=0'
        source.content_encoding = 'gzip'
        source.content_type = 'application/json'
        factory.side_effect = [source, destination]
        destination.rewrite.side_effect = [('token',1,2),(None,2,2)]
        copy_object('gs://a/x', 'gs://b/x')
        self.assertEqual(destination.rewrite.call_count, 2)
        self.assertEqual(destination.rewrite.call_args.kwargs['if_source_generation_match'],123)
        self.assertEqual(destination.rewrite.call_args.kwargs['token'],'token')
        self.assertEqual(destination.cache_control, source.cache_control)
        self.assertEqual(destination.content_encoding, 'gzip')
        self.assertEqual(destination.content_type, 'application/json')

    @mock.patch('phase5_storage_io.blob')
    def test_control_reads_do_not_hide_transport_failures(self, factory):
        factory.return_value.download_as_bytes.side_effect = OSError('transport')
        with self.assertRaises(OSError):
            read_json('gs://bucket/status')

    def test_timing_reports_do_not_contain_sql_or_parameters(self):
        raw = mock.Mock()
        raw.fetchone.return_value = (2,)
        connection = TimedConnection(raw)
        self.assertEqual(connection.execute('SELECT secret FROM private WHERE password=?', ['never-persist']).fetchone(),(2,))
        connection.execute('CREATE TABLE exact_fact AS SELECT * FROM source')
        text = json.dumps(connection.statements)
        for private in ('password','never-persist','secret','SELECT *'):
            self.assertNotIn(private, text)
        self.assertEqual(connection.statements[1]['relation'], 'exact_fact')

    def test_failed_stage_remains_recorded(self):
        timings = RefreshTimings()
        with self.assertRaises(ValueError):
            with timings.stage('import'):
                raise ValueError('private details')
        self.assertEqual(timings.stages[0]['state'],'failed')
        self.assertNotIn('private details', json.dumps(timings.stages))


if __name__ == '__main__':
    unittest.main()
