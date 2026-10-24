"""Physically order exact Cards facts in an inactive, unpublished candidate.

No statistical column changes. Each key-bounded chunk is reconciled in both
directions with EXCEPT ALL, preserving duplicate multiplicity before swapping.
Publication eligibility is invalidated before opening the database for writes.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

from phase5_rebuild_filter_relations import candidate_paths
from phase3_duckdb_service import _load_duckdb


def order(root: Path, generation: str) -> dict:
    database, manifest_path = candidate_paths(root, generation)
    if shutil.disk_usage(database.parent).free < 4 * 1024**3:
        raise RuntimeError('at least four GiB free is required for physical ordering')
    manifest = json.loads(manifest_path.read_text())
    manifest.setdefault('release', {})['status'] = 'candidate_requires_revalidation'
    temporary = manifest_path.with_suffix('.ordering.tmp')
    temporary.write_text(json.dumps(manifest, indent=2) + '\n')
    os.replace(temporary, manifest_path)
    connection = _load_duckdb().connect(str(database))
    results = []
    try:
        connection.execute("SET threads=2; SET memory_limit='2000MB'; SET preserve_insertion_order=false")
        spill = root / 'phase2_private_data/staging' / (generation + '.ordering-spill')
        spill.mkdir(exist_ok=True)
        connection.execute('SET temp_directory=?', [str(spill)])
        connection.execute("SET max_temp_directory_size='2GB'")
        for dataset in ('mw', 'base'):
            for prefix in ('cards_pair_fact', 'cards_pair_pooled_fact'):
                relation = f'{prefix}_{dataset}_narrow'
                staged = relation + '_physical_ordering'
                started = time.monotonic()
                connection.execute(f'DROP TABLE IF EXISTS {staged}')
                connection.execute(f'CREATE TABLE {staged} AS SELECT * FROM {relation} ORDER BY table_key,card_id')
                maximum, nulls, count = connection.execute(f'SELECT MAX(table_key), '
                    f'COUNT(*) FILTER (WHERE table_key IS NULL),COUNT(*) FROM {relation}').fetchone()
                if nulls:
                    raise RuntimeError('table keys must be non-null for bounded exact reconciliation')
                if count != connection.execute(f'SELECT COUNT(*) FROM {staged}').fetchone()[0]:
                    raise RuntimeError('physical ordering changed row count')
                for first in range(0, (maximum or 0) + 1, 100000):
                    predicate = f'table_key>={first} AND table_key<{first+100000}'
                    left = f'SELECT * FROM {relation} WHERE {predicate}'
                    right = f'SELECT * FROM {staged} WHERE {predicate}'
                    changed = connection.execute(f'SELECT COUNT(*) FROM '
                        f'(({left} EXCEPT ALL {right}) UNION ALL ({right} EXCEPT ALL {left}))').fetchone()[0]
                    if changed:
                        raise RuntimeError('physical ordering changed exact values or multiplicity')
                connection.execute('BEGIN TRANSACTION')
                connection.execute(f'DROP TABLE {relation}')
                connection.execute(f'ALTER TABLE {staged} RENAME TO {relation}')
                connection.execute('COMMIT')
                connection.execute('CHECKPOINT')
                results.append({'relation': relation, 'rows': count, 'exact_multiset_differences': 0,
                                'seconds': round(time.monotonic() - started, 3)})
                print(json.dumps(results[-1]), flush=True)
                manifest['builder']['relations'][relation]['physical_order'] = 'table_key,card_id'
                temporary.write_text(json.dumps(manifest, indent=2) + '\n')
                os.replace(temporary, manifest_path)
    finally:
        connection.close()
    return {'status': 'ok', 'generation': generation, 'relations': results, 'publication_ready': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('generation')
    parser.add_argument('--root', type=Path, default=Path('/home/ascri'))
    args = parser.parse_args()
    print(json.dumps(order(args.root.resolve(), args.generation), indent=2))
