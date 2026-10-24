"""Inactive code installation must never change the serving release."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import unittest
import uuid

from phase5_install_deployment import install, _install_service_units


class DeploymentStagingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / '.test-temp' / ('deployment-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.version = 'deploy-' + 'a' * 20
        self.archive = self.root / 'bundle.tar.gz'
        contents = b'print("candidate")\n'
        manifest = json.dumps({'version': self.version, 'files': [{
            'path': 'phase3_api.py', 'bytes': len(contents),
            'sha256': hashlib.sha256(contents).hexdigest(),
        }]}).encode()
        with tarfile.open(self.archive, 'w:gz') as bundle:
            for name, data in [('phase3_api.py', contents), ('deployment-manifest.json', manifest)]:
                info = tarfile.TarInfo(name); info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
        self.descriptor = self.root / 'descriptor.json'
        self.descriptor.write_text(json.dumps({'version': self.version,
            'archive_sha256': hashlib.sha256(self.archive.read_bytes()).hexdigest()}), encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_stage_does_not_activate_or_create_production_pointer(self):
        result = install(self.root, self.archive, self.descriptor, restart=False, activate=False)
        self.assertFalse(result['activated'])
        self.assertFalse((self.root / 'current-app').exists())
        self.assertFalse((self.root / 'phase2_private_data' / 'deployment-current.json').exists())
        self.assertTrue((self.root / 'releases' / self.version / 'phase3_api.py').is_file())

    def test_existing_installation_is_revalidated(self):
        install(self.root, self.archive, self.descriptor, restart=False, activate=False)
        (self.root / 'releases' / self.version / 'phase3_api.py').write_bytes(b'tampered')
        with self.assertRaises(RuntimeError):
            install(self.root, self.archive, self.descriptor, restart=False, activate=False)

    def test_stage_cannot_restart_production(self):
        with self.assertRaises(ValueError):
            install(self.root, self.archive, self.descriptor, restart=True, activate=False)

    def test_existing_inventory_must_match_the_checksum_verified_archive(self):
        install(self.root, self.archive, self.descriptor, restart=False, activate=False)
        metadata = self.root / 'releases' / self.version / 'deployment-manifest.json'
        metadata.write_text(json.dumps({'version': self.version, 'files': []}), encoding='utf-8')
        with self.assertRaises(RuntimeError):
            install(self.root, self.archive, self.descriptor, restart=False, activate=False)

    def test_service_policy_installs_shared_limit_and_preserves_operator_dropins(self):
        destination = self.root / 'service-policy'
        units = self.root / 'systemd'
        destination.mkdir()
        units.mkdir()
        for name in ('ark-nova-duckdb-api.service', 'ark-nova-duckdb-refresh-worker.service'):
            (destination / name).write_text('[Service]\nSlice=ark-analytics.slice\n')
        config = destination / 'ark-analytics.slice.conf'
        config.write_text('[Slice]\nMemoryMax=1456M\nMemorySwapMax=0\n')
        dropins = units / 'ark-analytics.slice.d'
        dropins.mkdir()
        operator = dropins / 'operator.conf'
        operator.write_text('[Slice]\nCPUWeight=100\n')
        _install_service_units(destination, units)
        owned = dropins / 'ark-nova-memory.conf'
        self.assertEqual(owned.read_text(), config.read_text())
        self.assertTrue(operator.is_file())
        config.unlink()
        _install_service_units(destination, units)
        self.assertFalse(owned.exists())
        self.assertTrue(operator.is_file())


if __name__ == '__main__':
    unittest.main()
