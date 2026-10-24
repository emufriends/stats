import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from phase5_refresh_metrics import TimedConnection


class BuilderProgressJournalTests(unittest.TestCase):
    def test_journal_is_bounded_metadata_not_sql_or_parameters(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'progress.jsonl'
            with mock.patch.dict('os.environ', {'DUCKDB_BUILDER_PROGRESS_FILE': str(path)}):
                connection = TimedConnection(mock.Mock())
                connection.execute('CREATE TABLE safe_relation AS SELECT ?', ['private-value'])
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([row['state'] for row in rows], ['started', 'succeeded'])
            self.assertEqual(rows[-1]['relation'], 'safe_relation')
            self.assertNotIn('private-value', path.read_text())
            self.assertNotIn('SELECT', path.read_text())

    def test_failed_statement_survives_without_exception_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'progress.jsonl'
            native = mock.Mock()
            native.execute.side_effect = RuntimeError('private failure details')
            with mock.patch.dict('os.environ', {'DUCKDB_BUILDER_PROGRESS_FILE': str(path)}):
                connection = TimedConnection(native)
                with self.assertRaises(RuntimeError):
                    connection.execute('INSERT INTO safe_relation VALUES (?)', ['secret'])
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(rows[-1]['state'], 'failed')
            self.assertNotIn('private failure details', path.read_text())

    def test_journal_write_failure_does_not_break_query(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.dict('os.environ', {'DUCKDB_BUILDER_PROGRESS_FILE': folder}):
                native = mock.Mock()
                TimedConnection(native).execute('SELECT 1')
                native.execute.assert_called_once()


if __name__ == '__main__':
    unittest.main()
