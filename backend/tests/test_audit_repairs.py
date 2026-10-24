"""Fault regressions for admission, coalescing, locking and release identity."""
import importlib
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from phase3_api import Phase3Application, Phase3HTTPHandler, BoundedHTTPServer
from phase5_process_lock import acquire, exclusive
from phase5_publish_release import _restore_aliases, recover_interrupted
from phase5_package_deployment import package
gateway = importlib.import_module('cloudrun-duckdb-gateway.gateway')


class RequestFailureTests(unittest.TestCase):
    def test_identical_failures_share_the_same_response(self):
        for failure in (ValueError('bad scope'), RuntimeError('private detail')):
            with self.subTest(failure=type(failure).__name__):
                entered, release = threading.Event(), threading.Event()
                adapter = Mock()
                def fail(request):
                    entered.set(); release.wait(3); raise failure
                adapter.execute.side_effect = fail
                app = Phase3Application(Mock(), adapter)
                responses = []
                threads = [threading.Thread(target=lambda: responses.append(app.dispatch('POST','/v1/query',b'{}'))) for _ in range(2)]
                threads[0].start(); self.assertTrue(entered.wait(3))
                threads[1].start(); time.sleep(.05); release.set()
                for thread in threads: thread.join(3); self.assertFalse(thread.is_alive())
                self.assertEqual(responses[0], responses[1])
                self.assertEqual(adapter.execute.call_count,1)
                self.assertFalse(app._inflight)
                self.assertTrue(app.query_slots.acquire(blocking=False)); app.query_slots.release()

    def test_gateway_forwards_errors_once_and_preserves_retry_after(self):
        for status in (503,504):
            handler=object.__new__(gateway.GatewayHandler)
            handler.path='/v1/query'; handler.headers={'Content-Length':'2','Content-Type':'application/json'}
            handler.rfile=io.BytesIO(b'{}'); handler._send=Mock()
            error=HTTPError('http://fixture',status,'fixture',{'Retry-After':'30'},io.BytesIO(b'{"error":"fixture"}'))
            with patch.object(gateway,'AUTO_START_VM',False), patch.object(gateway,'urlopen',side_effect=error) as request:
                handler._proxy('POST')
            self.assertEqual(request.call_count,1)
            self.assertEqual(handler._send.call_args.kwargs['retry_after'],'30')
            error.close()

    def test_bounded_http_recovers_after_partial_body_timeout(self):
        server=BoundedHTTPServer(('127.0.0.1',0),Phase3HTTPHandler,max_connections=1,read_timeout=.25)
        server.phase3_app=Mock(); server.phase3_app.dispatch.return_value=(200,{'status':'ok'})
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        sockets=[]
        try:
            first=socket.create_connection(server.server_address,timeout=2); sockets.append(first)
            first.sendall(b'POST /v1/query HTTP/1.0\r\nContent-Length: 100\r\n\r\n{')
            time.sleep(.05)
            second=socket.create_connection(server.server_address,timeout=2); sockets.append(second)
            self.assertIn(b'503',second.recv(4096))
            self.assertIn(b'408',first.recv(4096))
            time.sleep(.05)
            third=socket.create_connection(server.server_address,timeout=2); sockets.append(third)
            third.sendall(b'GET /healthz HTTP/1.0\r\n\r\n')
            self.assertIn(b'200',third.recv(4096))
        finally:
            for connection in sockets: connection.close()
            server.shutdown(); server.server_close(); thread.join(2)


class OwnershipTests(unittest.TestCase):
    def test_old_inode_is_reusable_but_live_owner_is_never_stolen(self):
        with tempfile.TemporaryDirectory() as directory:
            lock=Path(directory)/'publication.lock'
            lock.write_text(json.dumps({'pid':0,'created_unix':1}))
            with exclusive(lock):
                with self.assertRaises(OSError): acquire(lock)
            self.assertTrue(lock.exists())
            with exclusive(lock): pass

    def test_process_death_releases_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            lock=Path(directory)/'.sync.lock'
            code='import sys,time; from pathlib import Path; from phase5_process_lock import acquire; fd=acquire(Path(sys.argv[1])); print("locked",flush=True); time.sleep(30)'
            child=subprocess.Popen([sys.executable,'-u','-c',code,str(lock)],stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'locked')
                with self.assertRaises(OSError): acquire(lock)
                child.kill(); child.wait(5)
                with exclusive(lock): pass
            finally:
                if child.poll() is None: child.kill(); child.wait(5)
                child.stdout.close()

    def test_recovery_cannot_touch_an_active_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with exclusive(root/'phase2_private_data/publication.lock'), patch('phase5_publish_release.GenerationManager') as manager:
                with self.assertRaisesRegex(RuntimeError,'another process'):
                    recover_interrupted(root,bucket='fixture')
                manager.assert_not_called()

    def test_foreign_remote_alias_is_not_overwritten(self):
        with patch('phase5_publish_release.storage_io.object_state',return_value={'generation':3,'owner':'foreign','crc32c':'new'}), \
             patch('phase5_publish_release.storage_io.copy_object') as copy:
            with self.assertRaisesRegex(RuntimeError,'failed to restore'):
                _restore_aliases('fixture',{'key':'gs://fixture/backup'},['key'],
                    {'key':{'generation':1,'owner':'previous','crc32c':'old'}},'our-transaction')
            copy.assert_not_called()

    def test_owned_remote_alias_restores_with_generation_precondition(self):
        with patch('phase5_publish_release.storage_io.object_state',return_value={'generation':3,'owner':'ours','crc32c':'new'}), \
             patch('phase5_publish_release.storage_io.copy_object') as copy:
            _restore_aliases('fixture',{'key':'gs://fixture/backup'},['key'],
                {'key':{'generation':1,'owner':'previous','crc32c':'old'}},'ours')
            copy.assert_called_once_with('gs://fixture/backup','gs://fixture/key',expected_generation=3)

    def test_equal_bytes_with_changed_headers_are_not_treated_as_restored(self):
        with patch('phase5_publish_release.storage_io.object_state',return_value={
                'generation':3,'owner':'ours','crc32c':'same','headers':{'cache_control':'wrong'}}), \
             patch('phase5_publish_release.storage_io.copy_object') as copy:
            _restore_aliases('fixture',{'key':'gs://fixture/backup'},['key'],
                {'key':{'generation':1,'owner':'ours','crc32c':'same','headers':{'cache_control':'original'}}},'ours')
            copy.assert_called_once_with('gs://fixture/backup','gs://fixture/key',expected_generation=3)


class PackageIdentityTests(unittest.TestCase):
    def test_data_generation_does_not_change_code_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'main.py').write_text('# fixture')
            (root/'release-source-manifest.json').write_text(json.dumps({'schema_version':1,
                'files':{'main.py':hashlib.sha256((root/'main.py').read_bytes()).hexdigest()}}))
            state=root/'state.json'; outputs=[]
            for generation in ('old','new'):
                state.write_text(json.dumps({'generation':generation,'release':{'rollback':{'previous_generation':generation+'-previous'}}}))
                outputs.append(package(root,root/generation,state))
            self.assertEqual(outputs[0]['version'],outputs[1]['version'])
            self.assertEqual(outputs[0]['archive_sha256'],outputs[1]['archive_sha256'])
            self.assertNotEqual(outputs[0]['rollback'],outputs[1]['rollback'])
