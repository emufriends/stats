"""Concurrency evidence must include reads during a non-reused rebuild."""
import unittest
from unittest import mock
import subprocess
from phase5_increment7_gate import FILTERED_REQUESTS, mixed_refresh_pass, stop_refresh_process, run
from phase3_duckdb_service import Phase3RequestAdapter


class ConcurrentRefreshGateTests(unittest.TestCase):
    def test_invalid_intervals_fail_before_starting_a_refresh(self):
        with mock.patch('phase5_increment7_gate.subprocess.Popen') as launch:
            with self.assertRaises(ValueError):
                run(mock.Mock(), ['builder'], 5, query_interval_seconds=0)
        launch.assert_not_called()

    def test_gate_failure_terminates_its_builder(self):
        process = mock.Mock()
        process.poll.return_value = None
        stop_refresh_process(process)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=10)

    def test_unresponsive_builder_is_killed_after_bounded_wait(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('builder', 10), 0]
        stop_refresh_process(process)
        process.kill.assert_called_once()

    def test_player_probe_reaches_the_selected_identity(self):
        request = next(item for item in FILTERED_REQUESTS if item['stats_page'] == 'players')
        normalized = Phase3RequestAdapter.normalize_request(request)
        self.assertEqual(normalized['players_player'], 'Propaganda Panda')

    def test_startup_only_queries_are_not_refresh_concurrency_evidence(self):
        self.assertFalse(mixed_refresh_pass([
            {'refresh_running': True, 'refresh_progress': 38},
        ], {'status': 'ok'}))

    def test_failed_or_reused_refresh_cannot_pass(self):
        rows = [{'refresh_running': True, 'refresh_progress': 48}]
        self.assertFalse(mixed_refresh_pass(rows, {'status': 'failed'}))
        self.assertFalse(mixed_refresh_pass([
            {'refresh_running': False, 'refresh_progress': 96},
        ], {'status': 'ok'}))

    def test_read_during_derivative_build_is_valid_overlap(self):
        rows = [{'page': r['stats_page'],
                 'view': r.get('combinations_view') or r.get('players_view'),
                 'status':'ok', 'refresh_running':True, 'refresh_progress':48}
                for r in FILTERED_REQUESTS]
        self.assertTrue(mixed_refresh_pass(rows, {'status':'ok'}))
        self.assertFalse(mixed_refresh_pass(rows[:-1], {'status':'ok'}))

    def test_failed_query_does_not_establish_route_overlap(self):
        rows = [{'page': r['stats_page'],
                 'view': r.get('combinations_view') or r.get('players_view'),
                 'status':'ok', 'refresh_running':True, 'refresh_progress':48}
                for r in FILTERED_REQUESTS]
        rows[-1]['status']='error'
        self.assertFalse(mixed_refresh_pass(rows, {'status':'ok'}))


if __name__ == '__main__':
    unittest.main()
