"""Stage canonical frontend assets into the GitHub Pages tree or check parity.

Only declared frontend runtime/source paths, test/source helpers and maintained
handoffs are managed. Private generated datasets, backend data, repository README,
operator notes and Git state are untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def pairs(root, repository=None):
    repository = repository or root/'_publish_repo'
    for directory in ('assets', 'arena', 'tests'):
        for path in (root/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                yield path,repository/'docs'/path.relative_to(root)
    for name in ('.nojekyll', 'index.html', 'refresh/index.html', 'favicon.png', 'logo.png',
                 'cards_altnames.csv', 'cards_attributes.csv', 'merge_players.csv',
                 'ark_nova_dashboard_handoff.md','elo_system_handoff.md'):
        source=root/name
        if source.is_file(): yield source,repository/'docs'/name
    # Publish audit/source text, not private generated snapshot datasets.
    for path in (root/'analysis').glob('*'):
        target=repository/'docs/analysis'/path.name
        if path.is_file() and (path.suffix in {'.md','.py','.sql','.txt'} or
                               (path.suffix == '.json' and target.is_file())):
            yield path,target
    yield root/'ark_nova_dashboard_handoff.md',repository/'ark_nova_dashboard_handoff.md'
    for path in (root/'tools').glob('*.py'):
        yield path,repository/'tools'/path.name


def run(root, write=False, repository=None):
    repository = repository or root/'_publish_repo'
    result=[]
    for source,target in pairs(root, repository):
        content=source.read_bytes()
        # Retain original operator evidence locally; omit the personal billing
        # notification contact from its public audit copy.
        if source.relative_to(root).as_posix()=='analysis/increment7-budget-live-inventory.json':
            text=content.decode('utf-8-sig')
            content=re.sub(r'[A-Za-z0-9._%+-]+@(?:gmail|outlook|hotmail|yahoo)\.[A-Za-z]{2,}',
                           '[notification contact omitted]',text).encode('utf-8')
        before=hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        after=hashlib.sha256(content).hexdigest()
        if before!=after:
            result.append({'path':str(target.relative_to(repository)),'previous_sha256':before,'canonical_sha256':after})
            if write:
                target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(content)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--report',type=Path)
    parser.add_argument('--frontend-root',type=Path)
    parser.add_argument('--repository',type=Path)
    args=parser.parse_args()
    root=args.frontend_root or Path(__file__).resolve().parents[1]
    result=run(root,args.write,args.repository)
    report={'status':'staged' if args.write else 'checked','differences':result}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if args.write or not result else 1)
