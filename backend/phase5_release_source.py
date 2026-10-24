"""Assemble an explicit repair overlay over an immutable installed source tree.

This creates a reviewable source tree only. It never activates data or services.
Every overlay file is named explicitly; unlisted editable experiments stay out.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

REPAIR_FILES = (
    'phase3_api.py', 'phase5_process_lock.py', 'phase5_publish_release.py',
    'phase5_rollback_release.py', 'phase5_storage_io.py', 'phase5_source_sync.py',
    'phase5_package_deployment.py', 'phase5_release_source.py',
    'cloudrun-duckdb-gateway/gateway.py', 'cloudrun-duckdb-gateway/http_limits.py',
    'cloudrun-duckdb-gateway/Dockerfile',
)
NAME = 'release-source-manifest.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(root):
    manifest = json.loads((root / NAME).read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or not manifest.get('files'):
        raise RuntimeError('explicit release-source inventory is required')
    for name, digest in manifest['files'].items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or sha(path) != digest:
            raise RuntimeError(f'release source differs from reviewed inventory: {name}')
    return manifest


def prepare(baseline, working, destination):
    if destination.exists():
        raise RuntimeError('choose a new release-source directory')
    baseline_files = {path.relative_to(baseline).as_posix():path for path in baseline.rglob('*')
                      if path.is_file() and '__pycache__' not in path.parts}
    if 'phase3_api.py' not in baseline_files:
        raise RuntimeError('baseline is not an installed backend source tree')
    destination.mkdir(parents=True)
    for name,path in baseline_files.items():
        target=destination/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,target)
    changes=[]
    for name in REPAIR_FILES:
        source=working/name; target=destination/name
        before=sha(target) if target.exists() else None
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
        changes.append({'path':name,'baseline_sha256':before,'sha256':sha(target)})
    files={path.relative_to(destination).as_posix():sha(path) for path in destination.rglob('*') if path.is_file()}
    manifest={'schema_version':1,'baseline':str(baseline.resolve()),'baseline_files':{name:sha(path) for name,path in baseline_files.items()},
              'overlay':changes,'files':files}
    (destination/NAME).write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    verify(destination)
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--working',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    result=prepare(args.baseline.resolve(),args.working.resolve(),args.destination.resolve())
    print(json.dumps({'status':'assembled','files':len(result['files']),'overlay':result['overlay']},indent=2))
