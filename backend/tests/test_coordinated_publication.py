"""Code/data cutovers stop serving across the incompatible-schema boundary."""
import json
from pathlib import Path
import shutil
import unittest
from unittest import mock
import uuid

from phase5_coordinated_publication import coordinate, recover_cutover


class CoordinatedPublicationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / '.test-temp' / ('cutover-' + uuid.uuid4().hex)
        private = self.root / 'phase2_private_data'; private.mkdir(parents=True)
        self.old = 'deploy-' + 'a' * 20
        self.new = 'deploy-' + 'b' * 20
        (private / 'deployment-current.json').write_text(json.dumps({'current': self.old}), encoding='utf-8')
        serving = self.root / 'phase3_private_serving'; serving.mkdir()
        (serving / 'current.json').write_text('{"generation":"old"}', encoding='utf-8')
        self.descriptor = self.root / 'bundle.json'
        self.descriptor.write_text(json.dumps({'version': self.new}), encoding='utf-8')
        self.patches = []
        self.mocks = {}
        values = {
            'install': {}, 'verify_installed': self.root / 'releases' / self.old,
            '_load_release': (self.root / 'release.json', {'versions': {
                'code_files': {'phase3_duckdb_service.py': 'digest'}, 'contract_sha256': 'digest'}}),
            'sha256_file': 'digest', 'stop_services': None,
            'publish': {'status': 'ok'}, 'restore_deployment': None, 'recover_interrupted': {},
        }
        for name, result in values.items():
            patch = mock.patch('phase5_coordinated_publication.' + name, return_value=result)
            self.patches.append(patch); self.mocks[name] = patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def call(self):
        return coordinate(self.root, 'candidate', self.root / 'bundle.tar.gz',
                          self.descriptor, bucket='bucket')

    def test_cutover_stops_before_publication_and_records_both_code_versions(self):
        events = mock.Mock()
        for name in ('stop_services', 'publish', 'restore_deployment'):
            events.attach_mock(self.mocks[name], name)
        self.assertEqual(self.call()['status'], 'ok')
        self.assertEqual([call[0] for call in events.mock_calls],
                         ['stop_services', 'publish', 'restore_deployment'])
        self.assertEqual(self.mocks['publish'].call_args.kwargs['deployment_version'], self.new)
        self.assertEqual(self.mocks['publish'].call_args.kwargs['previous_deployment_version'], self.old)

    def test_code_mismatch_fails_before_stopping_production(self):
        self.mocks['sha256_file'].return_value = 'different'
        with self.assertRaises(RuntimeError):
            self.call()
        self.mocks['stop_services'].assert_not_called()
        self.mocks['publish'].assert_not_called()

    def test_publication_failure_restores_the_previous_code(self):
        self.mocks['publish'].side_effect = OSError('injected publication failure')
        with self.assertRaises(OSError):
            self.call()
        self.mocks['recover_interrupted'].assert_called_once()
        self.mocks['restore_deployment'].assert_called_once_with(self.root, self.old)

    def test_activation_failure_rolls_back_the_published_code_data_pair(self):
        self.mocks['restore_deployment'].side_effect = RuntimeError('injected restart failure')
        with mock.patch('phase5_rollback_release.rollback') as rollback:
            with self.assertRaises(RuntimeError):
                self.call()
        rollback.assert_called_once_with(self.root, 'candidate', bucket='bucket')

    def test_recovery_refuses_a_newer_unrelated_generation(self):
        (self.root / 'phase2_private_data/code-cutover.json').write_text(json.dumps({
            'generation': 'candidate', 'previous_generation': 'unrelated',
            'previous_deployment_version': self.old}), encoding='utf-8')
        with self.assertRaises(RuntimeError):
            recover_cutover(self.root, bucket='bucket')
        self.mocks['stop_services'].assert_not_called()

    def test_recovery_restores_old_code_after_a_prepublication_crash(self):
        journal = self.root / 'phase2_private_data/code-cutover.json'
        journal.write_text(json.dumps({'generation': 'candidate', 'previous_generation': 'old',
            'previous_deployment_version': self.old}), encoding='utf-8')
        self.assertEqual(recover_cutover(self.root, bucket='bucket')['status'], 'recovered')
        self.mocks['restore_deployment'].assert_called_once_with(self.root, self.old)
        self.assertFalse(journal.exists())

    def test_partial_publication_uses_its_journal_before_a_rollback_descriptor_exists(self):
        private = self.root / 'phase2_private_data'
        (private / 'code-cutover.json').write_text(json.dumps({
            'generation': 'candidate', 'previous_generation': 'old',
            'previous_deployment_version': self.old}), encoding='utf-8')
        (private / 'publication-transaction.json').write_text('{}', encoding='utf-8')
        (self.root / 'phase3_private_serving/current.json').write_text(
            '{"generation":"candidate"}', encoding='utf-8')
        with mock.patch('phase5_rollback_release.rollback') as rollback:
            recover_cutover(self.root, bucket='bucket')
        rollback.assert_not_called()
        self.mocks['recover_interrupted'].assert_called_once_with(self.root, bucket='bucket')
        self.mocks['restore_deployment'].assert_called_once_with(self.root, self.old)

    def test_partial_service_stop_failure_restores_old_code(self):
        self.mocks['stop_services'].side_effect = OSError('partial stop failure')
        with self.assertRaises(OSError):
            self.call()
        self.mocks['publish'].assert_not_called()
        self.mocks['restore_deployment'].assert_called_once_with(self.root, self.old)


if __name__ == '__main__':
    unittest.main()
