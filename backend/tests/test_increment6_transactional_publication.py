import base64
import hashlib
import inspect
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from phase3_duckdb_service import GenerationManager
from phase5_publish_release import publish, recover_interrupted
from phase5_refresh_workflow import _lock
from phase5_refresh_worker import run_refresh
from phase5_rollback_release import rollback


class Increment6TransactionalPublicationTests(unittest.TestCase):
    def setUp(self):
        # Unit publication must never obtain ADC or contact real buckets.
        for target in ('copy_object', 'delete_object'):
            patcher = mock.patch('phase5_publish_release.storage_io.' + target)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch('phase5_publish_release.storage_io.object_state',
                             return_value={'generation': 0, 'owner': None, 'crc32c': None})
        patcher.start()
        self.addCleanup(patcher.stop)
    def _generation(self, root: pathlib.Path, generation: str, version: str) -> None:
        directory = root / "phase2_private_data" / "generations"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{generation}.duckdb").write_bytes(b"duckdb-placeholder")
        (directory / f"{generation}.manifest.json").write_text(json.dumps({
            "status": "ok", "generation": generation, "data_version": version,
        }), encoding="utf-8")

    def _release(self, root: pathlib.Path, generation: str, version: str) -> None:
        release = root / "phase2_private_data" / "snapshots" / generation
        snapshot = release / "card-stats" / "default-mw.json"
        pack = release / "card-stats" / "bootstrap" / "default-pack.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        pack.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps({"status": "ok", "data_version": version, "data": []}), encoding="utf-8")
        pack.write_text(json.dumps({
            "status": "ok", "schema_version": 23, "data_version": version,
            "release_version": "release-2", "snapshots": {"card-stats/default-mw.json": {}},
        }), encoding="utf-8")

        def artifact(path, key, kind):
            return {
                "path": str(path), "object_key": key, "kind": kind,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }

        artifacts = [
            artifact(snapshot, "card-stats/default-mw.json", "snapshot"),
            artifact(pack, "card-stats/bootstrap/default-pack.json", "default_pack"),
        ]
        (release / "release-manifest.json").write_text(json.dumps({
            "status": "ok", "generation": generation, "data_version": version,
            "release_version": "release-2", "artifacts": artifacts,
            "required_object_keys": [item["object_key"] for item in artifacts],
        }), encoding="utf-8")
        (release / "manifest.json").write_text("{}", encoding="utf-8")

    def _root(self, directory: str) -> tuple[pathlib.Path, GenerationManager]:
        root = pathlib.Path(directory)
        self._generation(root, "old", "v1")
        self._generation(root, "candidate", "v2")
        self._release(root, "candidate", "v2")
        manager = GenerationManager(
            root / "phase2_private_data" / "generations",
            root / "phase3_private_serving" / "current.json",
        )
        manager.activate("old")
        pointer = root / "phase2_private_data" / "snapshots" / "current.json"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text('{"generation":"old"}', encoding="utf-8")
        return root, manager

    @mock.patch("phase5_publish_release._remote_exists", return_value=False)
    @mock.patch("phase5_publish_release._gcloud")
    @mock.patch("phase5_publish_release._upload")
    @mock.patch("phase5_publish_release.warm_interactive_generation")
    def test_pack_failure_restores_previous_public_success(
        self, _warm, _upload, _gcloud, _exists,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self._root(directory)
            with mock.patch("phase5_publish_release._upload_pack", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    publish(root, "candidate", bucket="bucket")
            self.assertEqual(manager.current().generation_id, "old")
            pointer = root / "phase2_private_data" / "snapshots" / "current.json"
            self.assertEqual(json.loads(pointer.read_text(encoding="utf-8"))["generation"], "old")
            self.assertFalse((root / "phase2_private_data" / "publication-transaction.json").exists())

    @mock.patch("phase5_publish_release._remote_exists", return_value=False)
    @mock.patch("phase5_publish_release._gcloud")
    @mock.patch("phase5_publish_release._upload_pack")
    @mock.patch("phase5_publish_release._upload")
    @mock.patch("phase5_publish_release.warm_interactive_generation")
    def test_success_advances_serving_and_snapshot_pointers(
        self, _warm, _upload, _upload_pack, _gcloud, _exists,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self._root(directory)
            result = publish(root, "candidate", bucket="bucket")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(manager.current().generation_id, "candidate")
            _warm.assert_called_once_with(mock.ANY, generation_id="candidate")
            pointer = root / "phase2_private_data" / "snapshots" / "current.json"
            self.assertEqual(json.loads(pointer.read_text(encoding="utf-8"))["generation"], "candidate")

    @mock.patch("phase5_publish_release._gcloud")
    def test_restart_recovery_rolls_back_a_killed_publication(self, _gcloud):
        _gcloud.return_value = subprocess.CompletedProcess([], 0)
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self._root(directory)
            old_pointer = (root / "phase2_private_data" / "snapshots" / "current.json").read_bytes()
            manager.activate("candidate")
            journal = root / "phase2_private_data" / "publication-transaction.json"
            journal.write_text(json.dumps({
                "generation": "candidate", "previous_generation": "old",
                "previous_snapshot_pointer": base64.b64encode(old_pointer).decode("ascii"),
                "activated": True, "changed": ["card-stats/default-mw.json"],
                "backups": {"card-stats/default-mw.json": "gs://bucket/rollback/default-mw.json"},
            }), encoding="utf-8")
            result = recover_interrupted(root, bucket="bucket")
            self.assertEqual(result["status"], "recovered")
            self.assertEqual(manager.current().generation_id, "old")
            self.assertFalse(journal.exists())

    @mock.patch("phase5_publish_release.storage_io.copy_object", side_effect=OSError('injected inverse failure'))
    def test_failed_inverse_upload_keeps_the_recovery_journal(self, _gcloud):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self._root(directory)
            manager.activate("candidate")
            journal = root / "phase2_private_data/publication-transaction.json"
            journal.write_text(json.dumps({
                "generation": "candidate", "previous_generation": "old", "activated": True,
                "changed": ["card-stats/default-mw.json"],
                "backups": {"card-stats/default-mw.json": "gs://bucket/rollback/default-mw.json"},
            }), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "failed to restore"):
                recover_interrupted(root, bucket="bucket")
            self.assertEqual(manager.current().generation_id, "old")
            self.assertTrue(journal.exists())

    @mock.patch("phase5_publish_release._gcloud", return_value=subprocess.CompletedProcess([], 0))
    def test_pointer_advance_without_completion_flag_is_recoverable(self, _gcloud):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self._root(directory)
            manager.activate("candidate")
            journal = root / "phase2_private_data/publication-transaction.json"
            journal.write_text(json.dumps({
                "generation": "candidate", "previous_generation": "old", "activated": False,
                "changed": [], "backups": {},
            }), encoding="utf-8")
            recover_interrupted(root, bucket="bucket")
            self.assertEqual(manager.current().generation_id, "old")
            self.assertFalse(journal.exists())

    @mock.patch("phase5_publish_release._remote_exists", return_value=False)
    @mock.patch("phase5_publish_release._gcloud", return_value=subprocess.CompletedProcess([], 0))
    @mock.patch("phase5_publish_release._upload_pack")
    @mock.patch("phase5_publish_release._upload")
    @mock.patch("phase5_publish_release.warm_interactive_generation")
    def test_code_bound_publication_rolls_back_the_exact_code_data_pair(
        self, _warm, _upload, _pack, _cloud, _exists,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self._root(directory)
            old_code = 'deploy-' + 'a' * 20
            new_code = 'deploy-' + 'b' * 20
            publish(root, 'candidate', bucket='bucket', deployment_version=new_code,
                    previous_deployment_version=old_code)
            descriptor = manager.current().manifest['release']['rollback']
            self.assertEqual(descriptor['schema_version'], 2)
            self.assertEqual(descriptor['previous_deployment_version'], old_code)
            with mock.patch('phase5_install_deployment.verify_installed') as verify, \
                 mock.patch('phase5_coordinated_publication.stop_services') as stop, \
                 mock.patch('phase5_coordinated_publication.restore_deployment') as restore, \
                 mock.patch('phase5_rollback_release._gcloud',
                            return_value=subprocess.CompletedProcess([], 0)):
                result = rollback(root, 'candidate', bucket='bucket')
            self.assertEqual(result['restored_generation'], 'old')
            self.assertEqual(manager.current().generation_id, 'old')
            self.assertEqual(json.loads((root / 'phase2_private_data/snapshots/current.json')
                                       .read_text())['generation'], 'old')
            verify.assert_called_once_with(root, old_code)
            stop.assert_called_once()
            restore.assert_called_once_with(root, old_code)

    def test_killed_workflow_lock_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "refresh.lock"
            path.write_text(json.dumps({
                "pid": 999999999, "created_unix": 0,
            }), encoding="utf-8")
            descriptor = _lock(path)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotEqual(payload["pid"], 999999999)
            finally:
                import os
                os.close(descriptor)
                path.unlink(missing_ok=True)

    def test_worker_defers_activation_and_commits_status_after_publication(self):
        from phase5_refresh_worker import _run_refresh
        worker_source = inspect.getsource(_run_refresh)
        from phase5_publish_release import _publish_locked
        publisher_source = inspect.getsource(_publish_locked)
        self.assertIn('"--defer-activation"', worker_source)
        self.assertNotIn('publish(run_id, "succeeded"', worker_source)
        self.assertLess(
            publisher_source.index("_upload_pack("),
            publisher_source.index("_upload_status("),
        )
        self.assertIn('"last_completed_at": completed_at', publisher_source)

    def test_cloud_refresh_lock_outlives_the_worker_window(self):
        import ast
        from phase5_refresh_worker import REFRESH_WINDOW_SECONDS
        main_source = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        assignment = next(node for node in ast.parse(main_source).body
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'REFRESH_LOCK_MAX_AGE'
                for target in node.targets))
        self.assertIsInstance(assignment.value, ast.Call)
        self.assertEqual(assignment.value.func.id, 'timedelta')
        hours = next(ast.literal_eval(keyword.value) for keyword in assignment.value.keywords
                     if keyword.arg == 'hours')
        self.assertGreater(hours * 3600, REFRESH_WINDOW_SECONDS)


if __name__ == "__main__":
    unittest.main()
