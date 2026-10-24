"""Coordinate a code/schema cutover and its exact paired rollback.

Run only after numerical, performance, and frontend gates pass. The serving
and refresh services are stopped across the code/data boundary, so an old
database is never queried by incompatible new code (or conversely). Ordinary
daily refreshes keep the same code and use the regular publisher directly.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from phase5_install_deployment import install, sha256_file, verify_installed
from phase5_publish_release import _load_release, publish, recover_interrupted

CUTOVER_JOURNAL = 'code-cutover.json'


def recover_cutover(root: Path, *, bucket: str) -> dict:
    """Compensate a killed code/data cutover using its exact prior code pair."""
    journal = root / 'phase2_private_data' / CUTOVER_JOURNAL
    payload = json.loads(journal.read_text(encoding='utf-8'))
    previous_version = str(payload['previous_deployment_version'])
    verify_installed(root, previous_version)
    pointer = json.loads((root / 'phase3_private_serving/current.json').read_text(encoding='utf-8'))
    current = pointer.get('generation')
    if current not in {payload['generation'], payload['previous_generation']}:
        raise RuntimeError('cutover recovery no longer owns the serving generation')
    stop_services()
    # An interrupted publisher may have advanced its pointer without having
    # written the final release rollback descriptor. Its write-ahead journal
    # is the authoritative inverse until publication completes.
    if (root / 'phase2_private_data/publication-transaction.json').exists():
        recover_interrupted(root, bucket=bucket)
        restore_deployment(root, previous_version)
    elif current == payload['generation']:
        from phase5_rollback_release import rollback
        rollback(root, current, bucket=bucket)
    else:
        recover_interrupted(root, bucket=bucket)
        restore_deployment(root, previous_version)
    journal.unlink()
    return {'status': 'recovered', 'generation': payload['previous_generation'],
            'deployment_version': previous_version}


def privileged(command: list[str]) -> list[str]:
    if os.name == 'nt':
        raise RuntimeError('coordinated VM service activation is Linux-only')
    return ([] if os.geteuid() == 0 else ['sudo']) + command


def stop_services() -> None:
    subprocess.run(privileged(['systemctl', 'stop',
        'ark-nova-duckdb-api.service', 'ark-nova-duckdb-refresh-worker.service']), check=True)


def restore_deployment(root: Path, version: str) -> None:
    if not re.fullmatch(r'deploy-[0-9a-f]{20}', version):
        raise RuntimeError('invalid paired deployment version')
    installer = Path(__file__).resolve().with_name('phase5_install_deployment.py')
    subprocess.run(privileged([sys.executable, str(installer), '--root', str(root),
        '--activate-version', version, '--restart']), check=True)


def coordinate(root: Path, generation: str, archive: Path, descriptor_path: Path,
               *, bucket: str) -> dict:
    journal = root / 'phase2_private_data' / CUTOVER_JOURNAL
    if journal.exists():
        raise RuntimeError('an interrupted code cutover requires --recover first')
    if (root / 'phase2_private_data/refresh.lock').exists():
        raise RuntimeError('wait for the running refresh before a code/schema cutover')
    descriptor = json.loads(descriptor_path.read_text(encoding='utf-8'))
    version = str(descriptor['version'])
    # Staging an already-installed bundle is read-only inventory validation.
    install(root, archive, descriptor_path, restart=False, activate=False)
    _, release = _load_release(root, generation)
    previous_pointer = json.loads((root / 'phase2_private_data/deployment-current.json').read_text(encoding='utf-8'))
    previous_version = str(previous_pointer['current'])
    destination = root / 'releases' / version
    code_files = (release.get('versions') or {}).get('code_files') or {}
    if not code_files:
        raise RuntimeError('candidate release has no verified producer code inventory')
    for name, digest in code_files.items():
        path = destination / name
        if not path.resolve().is_relative_to(destination.resolve()) or sha256_file(path) != digest:
            raise RuntimeError('candidate snapshot producer differs from the cutover bundle')
    contract = (release.get('versions') or {}).get('contract_sha256')
    if not contract or sha256_file(destination / 'contracts/dashboard-routes.v1.json') != contract:
        raise RuntimeError('candidate route contract differs from the cutover bundle')
    if not re.fullmatch(r'deploy-[0-9a-f]{20}', previous_version):
        raise RuntimeError('previous production code version is not rollback-ready')
    verify_installed(root, previous_version)
    previous_generation = json.loads(
        (root / 'phase3_private_serving/current.json').read_text(encoding='utf-8'))['generation']
    if previous_generation == generation:
        raise RuntimeError('code cutover requires an inactive candidate generation')
    journal_bytes = (json.dumps({'generation': generation,
        'previous_generation': previous_generation, 'deployment_version': version,
        'previous_deployment_version': previous_version}, indent=2) + '\n').encode('utf-8')
    # Exclusive creation serializes code cutovers before either operator can
    # stop services. Persist the inverse before making any serving mutation.
    descriptor_fd = os.open(journal, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor_fd, journal_bytes)
        os.fsync(descriptor_fd)
    finally:
        os.close(descriptor_fd)
    published = False
    try:
        stop_services()
        result = publish(root, generation, bucket=bucket, deployment_version=version,
                         previous_deployment_version=previous_version)
        published = True
        restore_deployment(root, version)
        journal.unlink()
        return {**result, 'deployment_version': version, 'previous_deployment_version': previous_version}
    except Exception:
        if published:
            from phase5_rollback_release import rollback
            rollback(root, generation, bucket=bucket)
        else:
            recover_interrupted(root, bucket=bucket)
            restore_deployment(root, previous_version)
        journal.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('generation', nargs='?')
    parser.add_argument('--root', type=Path, default=Path('/home/ascri'))
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--descriptor', type=Path)
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--bucket', default='ark-nova-stats-dashboard-cache')
    args = parser.parse_args()
    if args.recover:
        result = recover_cutover(args.root.resolve(), bucket=args.bucket)
    else:
        if not args.generation or not args.archive or not args.descriptor:
            parser.error('generation, --archive and --descriptor are required for a cutover')
        result = coordinate(args.root.resolve(), args.generation, args.archive.resolve(),
                            args.descriptor.resolve(), bucket=args.bucket)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
