"""Check the exact Git publication file set for private artifacts and credentials.

Reports only rule names/locations, never credential values. This is a focused
pre-push safeguard, not a claim that arbitrary data is safe to publish.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

PRIVATE_PARTS={'phase2_private_data','phase3_private_serving','agent-coordination','release-source',
               '__pycache__','.venv','node_modules'}
PRIVATE_SUFFIXES={'.duckdb','.wal','.parquet','.sqlite','.sqlite3','.zip','.pem','.key','.pyc','.pyo'}
PATTERNS={
    'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'oauth_access_token':re.compile(r'ya29\.[A-Za-z0-9_-]{25,}'),
    'github_token':re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'google_api_key':re.compile(r'AIza[A-Za-z0-9_-]{30,}'),
    'slack_token':re.compile(r'xox[baprs]-[A-Za-z0-9-]{20,}'),
    'credential_webhook':re.compile(r'https://(?:hooks\.slack\.com/services|discord(?:app)?\.com/api/webhooks)/[^\s\"\']+'),
    'literal_auth_secret':re.compile(r'''(?im)(?:MAINTENANCE_TOKEN|REFRESH_PAGE_PASSWORD|client_secret|refresh_token|access_token|private_key)\s*["']?\s*[:=]\s*["']([^"'\n]{12,})["']'''),
}


def run(repository):
    output=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z'],
                          cwd=repository,check=True,capture_output=True).stdout
    names=sorted(set(n.decode('utf-8') for n in output.split(b'\0') if n))
    issues=[];emails=[];inventory={};python_count=0
    for name in names:
        path=repository/name
        if not path.is_file():
            continue
        parts=set(Path(name).parts)
        if parts & PRIVATE_PARTS or path.suffix in PRIVATE_SUFFIXES or path.name.startswith('.env'):
            issues.append({'path':name,'rule':'private_artifact_path'})
        raw=path.read_bytes();inventory[name]=hashlib.sha256(raw).hexdigest()
        if len(raw)>5*1024*1024:
            issues.append({'path':name,'rule':'unexpected_large_file','bytes':len(raw)})
        if path.suffix.lower() in {'.png','.jpg','.jpeg','.gif','.ico','.woff','.woff2'}:
            continue
        try:
            text=raw.decode('utf-8-sig')
        except UnicodeError:
            issues.append({'path':name,'rule':'unexpected_binary'})
            continue
        if path.suffix=='.py':
            try:
                ast.parse(text,filename=name);python_count+=1
            except SyntaxError as error:
                issues.append({'path':name,'rule':'python_syntax','line':error.lineno})
        for rule,pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                # Synthetic test values are deliberately not real credentials.
                if rule=='literal_auth_secret' and 'tests' in parts:
                    continue
                issues.append({'path':name,'rule':rule,'line':text.count('\n',0,match.start())+1})
        personal=re.findall(r'[A-Za-z0-9._%+-]+@(?:gmail|outlook|hotmail|yahoo)\.[A-Za-z]{2,}',text)
        if personal:
            emails.append({'path':name,'count':len(set(personal))})
    return {'status':'passed' if not issues else 'failed','files':len(inventory),
            'python_syntax_checked':python_count,'issues':issues,
            'personal_email_review':emails,'inventory':inventory}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository',type=Path,required=True)
    parser.add_argument('--inventory',action='store_true')
    args=parser.parse_args();result=run(args.repository.resolve())
    if not args.inventory:result.pop('inventory')
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='passed' else 1)
