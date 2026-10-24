import json
import os
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
import time
import unittest
from unittest import mock

from phase5_query_pause import RefreshQueryGate, AnalyticalRequestsPaused
from phase3_api import Phase3Application
import phase5_refresh_worker as worker


@unittest.skipUnless(os.name == 'posix', 'actual flock qualification runs on Linux VM')
class QueryPauseLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.gate = RefreshQueryGate(Path(self.temp.name) / 'gate')

    def test_pause_rejects_queries_and_resumes_after_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'test'):
            with self.gate.pause():
                self.assertTrue(self.gate.blocked())
                self.assertTrue(self.gate.fully_paused())
                with self.assertRaises(AnalyticalRequestsPaused):
                    with self.gate.query():
                        self.fail('query admitted')
                raise RuntimeError('test')
        with self.gate.query():
            self.assertFalse(self.gate.blocked())
        self.assertTrue(self.gate.path.exists())

    def test_intent_blocks_new_queries_while_existing_query_drains(self):
        acquired = threading.Event()
        release = threading.Event()
        def pauser():
            with self.gate.pause():
                acquired.set()
                release.wait(3)
        with self.gate.query():
            thread = threading.Thread(target=pauser)
            thread.start()
            deadline = time.monotonic() + 3
            while not self.gate.blocked() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(self.gate.blocked())
            self.assertFalse(acquired.is_set())
            self.assertFalse(self.gate.fully_paused())
            with self.assertRaises(AnalyticalRequestsPaused):
                with self.gate.query():
                    pass
        self.assertTrue(acquired.wait(3))
        release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertFalse(self.gate.blocked())

    def test_timeout_releases_intent(self):
        with self.gate.query():
            with self.assertRaises(TimeoutError):
                with self.gate.pause(timeout=.01):
                    pass
            self.assertFalse(self.gate.blocked())

    def test_killed_owner_cannot_leave_stale_pause(self):
        code = ('from phase5_query_pause import RefreshQueryGate; import time; '
                f'g=RefreshQueryGate({str(self.gate.path)!r}); '
                'p=g.pause(); p.__enter__(); print("locked",flush=True); time.sleep(60)')
        child = subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'locked')
            self.assertTrue(self.gate.blocked())
        finally:
            child.kill()
            child.wait(timeout=5)
            child.stdout.close()
        with self.gate.query():
            self.assertFalse(self.gate.blocked())


class APIQueryPauseTests(unittest.TestCase):
    def test_refresh_window_allows_six_hours(self):
        self.assertEqual(worker.REFRESH_WINDOW_SECONDS, 21600)

    def test_paused_process_never_executes_query_even_after_lock_release(self):
        gate = mock.Mock()
        gate.fully_paused.return_value = True
        manager, adapter = mock.Mock(), mock.Mock()
        app = Phase3Application(manager, adapter, query_gate=gate)
        status, payload = app.dispatch('POST', '/v1/query', b'{}')
        self.assertEqual(status, 503)
        self.assertEqual(payload['error'], 'refresh_in_progress')
        adapter.execute.assert_not_called()
        gate.query.assert_not_called()

    def test_gate_rejection_and_status_are_sanitized(self):
        gate = mock.Mock()
        gate.fully_paused.return_value = False
        gate.query.side_effect = AnalyticalRequestsPaused()
        gate.blocked.return_value = True
        manager = mock.Mock()
        manager.status.return_value = {'state':'active','database':'private-secret-path'}
        app = Phase3Application(manager, mock.Mock(), query_gate=gate)
        code, value = app.dispatch('POST','/v1/query',b'{}')
        self.assertEqual(code,503)
        self.assertEqual(value['error'],'refresh_in_progress')
        code, value = app.dispatch('GET','/v1/status')
        self.assertEqual(code,200)
        self.assertTrue(value['analytical_requests_paused'])
        self.assertNotIn('database',value)

    def test_worker_releases_barrier_on_success_and_failure(self):
        for fail in (False,True):
            with self.subTest(fail=fail):
                gate = mock.MagicMock()
                context = gate.pause.return_value
                with mock.patch.dict(os.environ,{'REFRESH_PAUSE_ANALYTICS':'true',
                    'PHASE5_QUERY_PAUSE_LOCK':'test-lock'}), \
                     mock.patch.object(worker,'RefreshQueryGate',return_value=gate), \
                     mock.patch.object(worker,'wait_for_lightweight_api') as wait, \
                     mock.patch.object(worker,'_run_refresh',
                         side_effect=RuntimeError('test') if fail else None,
                         return_value={'status':'ok'}) as run:
                    if fail:
                        with self.assertRaises(RuntimeError):
                            worker.run_refresh('test',{})
                    else:
                        self.assertEqual(worker.run_refresh('test',{}),{'status':'ok'})
                    wait.assert_called_once()
                    run.assert_called_once()
                    context.__exit__.assert_called_once()

    def test_missing_gate_fails_closed(self):
        with mock.patch.dict(os.environ,{'REFRESH_PAUSE_ANALYTICS':'true'},clear=True), \
             mock.patch.object(worker,'_run_refresh') as run:
            with self.assertRaises(RuntimeError):
                worker.run_refresh('test',{})
            run.assert_not_called()

    def test_publication_arguments_preserve_exact_prior_code(self):
        version='deploy-'+'a'*20
        previous='deploy-'+'b'*20
        with mock.patch.object(worker,'APP_ROOT',Path('/releases')/version), \
             mock.patch.object(worker,'read_json_file',side_effect=[{'generation':'old'},
                 {'release':{'deployment_version':previous}}]):
            self.assertEqual(worker.publication_code_arguments(),
                ['--deployment-version',version,'--previous-deployment-version',previous])


if __name__ == '__main__':
    unittest.main()
