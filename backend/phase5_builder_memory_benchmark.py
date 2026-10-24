"""Inactive, local-source-only refresh memory qualification on the serving VM.

Each stage runs in a fresh process so released DuckDB/Python allocations cannot
accumulate between import, derivative construction and numerical validation.
Run under a systemd memory-limited test unit; never changes production pointers,
hardware, schedules or public artifacts. No BigQuery or moving-source download.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from phase5_refresh_metrics import rss_highwater_bytes


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n', encoding='utf-8')


def exact_differences(connection, name, scope, parameters):
    """Exact null-safe row comparison; duplicate keys retain EXCEPT ALL fallback."""
    keys = ['table_id', 'card_name'] if '_table_fact_' in name else ['table_id', 'player']
    if name == 'mw_action_card_draft_narrow':
        keys = ['table_id', 'card_key']
    elif name not in {'prepared_full_sample_narrow', 'home_filter_fact_narrow'} and 'card_name' not in keys:
        keys.append('card_name')
    columns = ','.join(keys)
    duplicates = connection.execute(f'''SELECT COUNT(*) FROM (
        (SELECT {columns} FROM main.{name} WHERE {scope} GROUP BY {columns} HAVING COUNT(*)>1)
        UNION ALL
        (SELECT {columns} FROM baseline.{name} WHERE {scope} GROUP BY {columns} HAVING COUNT(*)>1))''',
        parameters+parameters).fetchone()[0]
    if duplicates:
        query = f'''WITH
            current_slice AS MATERIALIZED (SELECT * FROM main.{name} WHERE {scope}),
            baseline_slice AS MATERIALIZED (SELECT * FROM baseline.{name} WHERE {scope})
            SELECT COUNT(*) FROM (
            (SELECT * FROM current_slice EXCEPT ALL SELECT * FROM baseline_slice)
            UNION ALL
            (SELECT * FROM baseline_slice EXCEPT ALL SELECT * FROM current_slice))'''
    else:
        joins = ' AND '.join(f'a.{key} IS NOT DISTINCT FROM b.{key}' for key in keys)
        query = f'''WITH
            current_slice AS MATERIALIZED (SELECT *, TRUE AS __parity_present FROM main.{name} WHERE {scope}),
            baseline_slice AS MATERIALIZED (SELECT *, TRUE AS __parity_present FROM baseline.{name} WHERE {scope})
            SELECT COALESCE(SUM(CASE WHEN a.__parity_present IS NULL OR b.__parity_present IS NULL THEN 1
                 WHEN a IS DISTINCT FROM b THEN 2 ELSE 0 END),0)
            FROM current_slice a FULL OUTER JOIN baseline_slice b ON {joins}'''
    return int(connection.execute(query, parameters+parameters).fetchone()[0])


def table_moment_differences(connection, name, scope, parameters):
    """Qualify regrouped moments, not arbitrary ANY_VALUE map representation.

    Observation facts must first match exactly. Summation order may change only
    the last floating-point bits. Map is unused by the table-moment serving
    path (map filters use player facts); each representative must still belong
    to the same table/dataset. All counts, keys and other dimensions are exact.
    """
    floating = ['played_sum', 'played_sumsq', 'pre_match_sum', 'hand_sum', 'hand_sumsq']
    columns = [r[0] for r in connection.execute(f'DESCRIBE main.{name}').fetchall()
               if r[0] not in ['Map']+floating]
    structs = ['struct_pack('+','.join(f'"{n}" := {alias}."{n}"' for n in columns)+')'
               for alias in ('a','b')]
    exact_equal = structs[0]+' IS NOT DISTINCT FROM '+structs[1]
    close = ' AND '.join(f'''(a.{n} IS NOT DISTINCT FROM b.{n} OR
        (a.{n} IS NOT NULL AND b.{n} IS NOT NULL AND isfinite(a.{n}) AND isfinite(b.{n})
         AND abs(a.{n}-b.{n}) <= 1e-12+2e-12*greatest(abs(a.{n}),abs(b.{n}))))''' for n in floating)
    maps = ' AND '.join(f'''EXISTS (SELECT 1 FROM {db}.game_player_narrow g
        WHERE g.table_id IS NOT DISTINCT FROM {alias}.table_id AND g.is_mw={alias}.is_mw
          AND g.map_name IS NOT DISTINCT FROM {alias}.Map)''' for db,alias in [('main','a'),('baseline','b')])
    return connection.execute(f'''WITH
        a AS MATERIALIZED (SELECT *,TRUE AS __present FROM main.{name} WHERE {scope}),
        b AS MATERIALIZED (SELECT *,TRUE AS __present FROM baseline.{name} WHERE {scope}),
        joined AS (SELECT a,b,{exact_equal} AS exact_equal,({close}) AS close,
                   ({maps}) AS valid_maps FROM a FULL OUTER JOIN b
                   ON a.table_id IS NOT DISTINCT FROM b.table_id
                   AND a.card_name IS NOT DISTINCT FROM b.card_name)
        SELECT COUNT(*) FILTER (WHERE a.__present IS NULL OR b.__present IS NULL
            OR NOT exact_equal OR NOT close OR NOT valid_maps),
            COUNT(*) FILTER (WHERE a.Map IS DISTINCT FROM b.Map),
            COUNT(*) FILTER (WHERE {' OR '.join(f'a.{n} IS DISTINCT FROM b.{n}' for n in floating)})
        FROM joined''', parameters+parameters).fetchone()


def stage(args):
    started = time.perf_counter()
    from phase3_duckdb_service import _load_duckdb
    from phase5_source_materialize import materialize
    from phase4_metadata import materialize_metadata_tables, load_arena_settings
    from phase5_refresh_workflow import _tournament_metadata_with_fallback
    from phase2_local_vertical_slice import run, create_seen_card_relation, canonical_update_scopes, create_card_play_filter_summary, create_card_filter_fact_relation, create_mw_action_card_draft_relation
    spec = json.loads(args.spec.read_text())
    folder = args.spec.parent
    database = folder/'candidate.duckdb'
    if args.stage == 'source':
        result = materialize(Path(spec['source_root']), database,
                             threads=args.threads, memory_limit=args.memory_limit,
                             temp_directory=folder/'source-spill')
    elif args.stage == 'metadata':
        moving = Path(spec['moving_root'])
        tournaments, _ = _tournament_metadata_with_fallback(moving, Path(spec['baseline']))
        arena, _ = load_arena_settings(moving/'arena_settings.csv')
        connection = _load_duckdb().connect(str(database))
        try:
            connection.execute('SET threads=1')
            connection.execute('SET memory_limit=?', [args.memory_limit])
            materialize_metadata_tables(connection, tournaments, arena)
            connection.execute('CHECKPOINT')
        finally:
            connection.close()
        result = {'status': 'ok'}
    elif args.stage == 'builder':
        run(database, folder/'builder.json', threads=args.threads,
            memory_limit=args.memory_limit, temp_directory=folder/'builder-spill',
            merge_players_path=Path(spec['app_root'])/'merge_players.csv',
            source_manifest=Path(spec['source_root'])/'manifest.json')
        result = {'status': 'ok', 'report': str(folder/'builder.json')}
    elif args.stage in {'seen', 'play-summary', 'card-facts', 'draft'}:
        connection = _load_duckdb().connect(str(database))
        try:
            connection.execute('SET threads=1')
            connection.execute('SET memory_limit=?', [args.memory_limit])
            connection.execute('SET preserve_insertion_order=false')
            connection.execute('SET temp_directory=?', [str(folder/'seen-spill')])
            rows = (create_mw_action_card_draft_relation(connection) if args.stage == 'draft'
                    else create_seen_card_relation(connection) if args.stage == 'seen'
                    else create_card_play_filter_summary(connection) if args.stage == 'play-summary'
                    else create_card_filter_fact_relation(connection))
        finally:
            connection.close()
        result = {'status': 'ok', 'rows': rows}
    else:
        # Every derivative is count/schema checked. Exact value reconciliation
        # covers canonical rows, seen cards and downstream played-round facts
        # whose construction changed, in bounded
        # table-ID buckets. Full snapshot comparison separately covers public
        # results. Do not allocate a giant wide-row EXCEPT ALL hash table merely
        # to validate a low-memory implementation.
        current = (json.loads((folder/'builder.json').read_text()) if args.stage == 'parity'
                   else {'relations': {}})
        baseline = json.loads(Path(spec['baseline']).with_suffix('.manifest.json').read_text())
        connection = _load_duckdb().connect(str(database), read_only=True)
        try:
            connection.execute('SET threads=1')
            connection.execute('SET memory_limit=?', [args.memory_limit])
            connection.execute('SET temp_directory=?', [str(folder/'validation-spill')])
            escaped = spec['baseline'].replace("'", "''")
            connection.execute(f"ATTACH '{escaped}' AS baseline (READ_ONLY)")
            if args.stage in {'card-facts-parity', 'card-table-parity'}:
                current['relations'] = {name: {'rows': connection.execute(f'SELECT COUNT(*) FROM main.{name}').fetchone()[0]}
                    for name in ('card_filter_fact_mw_narrow','card_filter_fact_base_narrow',
                                 'card_play_filter_fact_mw_narrow','card_play_filter_fact_base_narrow',
                                 'card_filter_table_fact_mw_narrow','card_filter_table_fact_base_narrow')
                    if args.stage != 'card-table-parity' or '_table_fact_' in name}
            elif args.stage == 'partial-parity':
                present = {row[0] for row in connection.execute('SELECT table_name FROM duckdb_tables() WHERE database_name = current_database()').fetchall()}
                current['relations'] = {name: {'rows': connection.execute(f'SELECT COUNT(*) FROM main.{name}').fetchone()[0]}
                    for name in sorted(present & set(baseline['builder']['relations']))}
            checks = []
            for name, info in current['relations'].items():
                if name not in baseline['builder']['relations']:
                    raise ValueError('baseline relation missing: '+name)
                schema = connection.execute(f'DESCRIBE main.{name}').fetchall()
                old_schema = connection.execute(f'DESCRIBE baseline.{name}').fetchall()
                if schema != old_schema:
                    raise ValueError('schema differs: '+name)
                # Counts are checked as well, before the exact multiset gate.
                old_count = connection.execute(f'SELECT COUNT(*) FROM baseline.{name}').fetchone()[0]
                count = connection.execute(f'SELECT COUNT(*) FROM main.{name}').fetchone()[0]
                if count != old_count or count != info['rows']:
                    raise ValueError('count differs: '+name)
                check = {'relation': name, 'rows': count, 'count_schema_match': True}
                if name in {'prepared_full_sample_narrow', 'home_filter_fact_narrow', 'card_seen_narrow', 'mw_action_card_draft_narrow',
                            'card_filter_fact_mw_narrow', 'card_filter_fact_base_narrow',
                            'card_play_filter_fact_mw_narrow', 'card_play_filter_fact_base_narrow',
                            'card_filter_table_fact_mw_narrow', 'card_filter_table_fact_base_narrow'}:
                    differences = 0
                    if name == 'prepared_full_sample_narrow':
                        # Range scopes allow zonemap pruning on wide source-
                        # ordered rows. Include null IDs as a separate exact
                        # population rather than dropping them at boundaries.
                        scopes = [(scope, params[:len(params)//2]) for scope, _target, params
                                  in canonical_update_scopes(connection, 64)]
                        scopes.append(('table_id IS NULL', []))
                    else:
                        validation_batches = int(os.environ.get('DUCKDB_PARITY_BATCHES', '64'))
                        if not 1 <= validation_batches <= 256:
                            raise ValueError('parity batches must be between 1 and 256')
                        scopes = [(f'hash(table_id) % {validation_batches} = {bucket}', [])
                                  for bucket in range(validation_batches)]
                    for bucket, (scope, parameters) in enumerate(scopes):
                        if '_table_fact_' in name:
                            invalid, maps, floats = table_moment_differences(connection, name, scope, parameters)
                            differences += invalid
                            check['valid_representative_map_differences'] = check.get('valid_representative_map_differences', 0)+maps
                            check['floating_sum_order_differences'] = check.get('floating_sum_order_differences', 0)+floats
                        else:
                            differences += exact_differences(connection, name, scope, parameters)
                        write(folder/'parity-progress.json', {'status': 'running', 'checks': checks,
                              'relation': name, 'completed_buckets': bucket+1, 'differences': differences})
                        if differences:
                            raise ValueError('values differ: '+name)
                    check.update(validated_differences=differences, exact_buckets=len(scopes))
                    if '_table_fact_' not in name:
                        check['exact_multiset_differences'] = differences
                checks.append(check)
                write(folder/'parity-progress.json', {'status': 'running', 'checks': checks})
        finally:
            connection.close()
        result = {'status': 'ok', 'partial': args.stage != 'parity', 'checks': checks}
    result['process_rss_highwater_bytes'] = rss_highwater_bytes()
    result['stage_seconds'] = round(time.perf_counter()-started, 3)
    write(folder/f'{args.stage}-result.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--root', type=Path, default=Path('/home/ascri'))
    parser.add_argument('--memory-limit', default='600MB')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--stage', choices=['source','metadata','builder','parity','seen','play-summary','card-facts','draft','card-facts-parity','card-table-parity','partial-parity'])
    parser.add_argument('--spec', type=Path)
    args = parser.parse_args()
    if args.stage:
        stage(args)
        return
    if not args.work or args.work.exists():
        raise ValueError('a new isolated work directory is required')
    args.work.mkdir(parents=True)
    root = args.root
    pointer = json.loads((root/'phase3_private_serving/current.json').read_text())
    baseline = root/'phase2_private_data/generations'/f"{pointer['generation']}.duckdb"
    manifest = json.loads(baseline.with_suffix('.manifest.json').read_text())
    spec = args.work/'spec.json'
    write(spec, {'baseline': str(baseline), 'source_root': str(Path(manifest['source_materialization']['source_manifest']).parent),
                 'moving_root': str(root/'phase2_private_data/moving_sources'),
                 'app_root': str(Path(__file__).resolve().parent), 'memory_limit': args.memory_limit})
    results = []
    for name in ('source','metadata','builder','parity'):
        started = time.perf_counter()
        with (args.work/f'{name}.stdout.log').open('w') as out, (args.work/f'{name}.stderr.log').open('w') as err:
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--stage', name,
                                      '--spec', str(spec), '--memory-limit', args.memory_limit], stdout=out, stderr=err)
        results.append({'stage': name, 'seconds': round(time.perf_counter()-started, 3), 'exit_code': process.returncode})
        write(args.work/'qualification.json', {'status': 'running' if process.returncode == 0 else 'failed', 'stages': results})
        if process.returncode:
            raise RuntimeError('isolated stage failed: '+name)
    write(args.work/'qualification.json', {'status': 'ok', 'stages': results, 'memory_limit': args.memory_limit,
                                          'production_pointer_unchanged': json.loads((root/'phase3_private_serving/current.json').read_text()) == pointer})


if __name__ == '__main__':
    main()
