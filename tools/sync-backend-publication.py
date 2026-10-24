"""Mirror maintained backend review source, never operator data or deployments.

This is an explicit public-source allowlist, not a recursive desktop copy.
Default mode checks hashes. --write synchronizes current source/publication
copies only; it never changes installed releases, sealed evidence or Git state.
"""
import argparse
import ast
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil

ROOT_SUFFIXES = {'.py','.md','.txt','.yaml','.yml','.sh','.conf','.service'}
SOURCE_DIRS = ('arena','contracts','tests','cloudrun-duckdb-gateway','budget_shutdown_service','elo_peak_updater')
TEST_HELPERS = ('compare_snapshot_memory_20261002.py','profile_snapshot_pages_20261002.py',
                'benchmark_refresh_builder_next_20261004.py')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_merge(frontend, backend):
    path=frontend/'merge_players.csv'; raw=path.read_bytes(); text=raw.decode('utf-8-sig')
    list(csv.reader(io.StringIO(text),strict=True))
    namespace={'csv':csv,'io':io,'hashlib':hashlib,'Path':Path}
    for module,name in [('main.py','_parse_merge_players_csv'),
                        ('phase2_local_vertical_slice.py','_merge_player_rows')]:
        source=backend/module
        node=next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
                  if isinstance(n,ast.FunctionDef) and n.name==name)
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
    metadata=namespace['_parse_merge_players_csv'](text)
    aliases=namespace['_merge_player_rows'](path)
    return raw,{'groups':len(metadata['groups']),'unique_aliases':len(aliases),'sha256':digest(raw)}


def publication_files(backend):
    for path in backend.iterdir():
        if path.is_file() and not path.name.startswith('.') and (
                path.suffix in ROOT_SUFFIXES or path.name in {'budget_policy.json','cards_attributes.csv','merge_players.csv'}):
            yield path,path.name
    for name in ('.gitignore','.gcloudignore'):
        yield backend/name,name
    for folder in SOURCE_DIRS:
        for path in (backend/folder).rglob('*'):
            if (path.is_file() and not any(part in {'__pycache__','.git','.venv','node_modules'} for part in path.parts)
                    and (path.suffix in ROOT_SUFFIXES | {'.json','.csv'} or path.name in {'Dockerfile','Procfile'})):
                yield path,path.relative_to(backend).as_posix()
    for name in TEST_HELPERS:
        yield backend/'reports'/name,'reports/'+name
    yield backend/'reports/README.md','reports/README.md'


def run(frontend, backend, repository, write=False):
    raw,validation=validate_merge(frontend,backend)
    outputs={}
    # Current source copies only. Frozen report/deployment/rollback copies remain immutable.
    outputs[backend/'merge_players.csv']=raw
    outputs[repository/'docs/merge_players.csv']=raw
    for source,relative in publication_files(backend):
        content=raw if relative=='merge_players.csv' else source.read_bytes()
        if relative=='budget_policy.json':
            policy=json.loads(content)
            policy['warning_delivery']='Configured privately in Cloud Billing; not included in public review source'
            content=(json.dumps(policy,indent=2)+'\n').encode()
        outputs[repository/'backend'/relative]=content
    result=[]
    for target,content in sorted(outputs.items(),key=lambda item:str(item[0])):
        before=digest(target.read_bytes()) if target.is_file() else None
        after=digest(content)
        if before!=after:
            result.append({'path':str(target),'previous_sha256':before,'canonical_sha256':after})
            if write:
                target.parent.mkdir(parents=True,exist_ok=True)
                # This is a mechanical mirror operation; do not normalize CSV bytes.
                target.write_bytes(content)
    return {'status':'synchronized' if write else 'checked','merge_validation':validation,
            'public_backend_files':sum(1 for target in outputs if target.is_relative_to(repository/'backend')),
            'sanitized_fields':{'backend/budget_policy.json':['warning_delivery']},'differences':result}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--backend-root',type=Path)
    parser.add_argument('--repository',type=Path)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    frontend=args.frontend_root.resolve()
    backend=(args.backend_root or frontend.parent/'ark-nova-function').resolve()
    repository=(args.repository or frontend/'_publish_repo').resolve()
    report=run(frontend,backend,repository,args.write)
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if args.write or not report['differences'] else 1)
