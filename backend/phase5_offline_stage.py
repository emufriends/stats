"""Fresh-process boundary for trusted serial refresh stages.

Only private file paths, resource settings and a fixed stage selector cross this
boundary. It never activates a generation or publishes artifacts. Child errors
leave private diagnostics and propagate to the workflow's existing rollback.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from phase5_refresh_metrics import rss_highwater_bytes, measure_resources

STAGES = frozenset({'source', 'metadata', 'builder', 'rosters_records', 'snapshots'})


def invoke(stage: str, configuration: dict, result_path: Path) -> dict:
    if stage not in STAGES:
        raise ValueError('unknown offline stage')
    result_path.parent.mkdir(parents=True, exist_ok=True)
    specification = result_path.with_suffix('.input.json')
    specification.write_text(json.dumps({'stage': stage, 'configuration': configuration,
                                         'result': str(result_path)}, default=str), encoding='utf-8')
    try:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), str(specification)], check=True)
        result = json.loads(result_path.read_text(encoding='utf-8'))
        if not isinstance(result, dict) or result.get('status') not in {'ok', 'candidate_ready'}:
            raise RuntimeError('offline stage returned an unsuccessful result')
        return result
    finally:
        specification.unlink(missing_ok=True)


def execute(specification: dict) -> dict:
    stage = specification['stage']
    settings = specification['configuration']
    if stage not in STAGES:
        raise ValueError('unknown offline stage')
    if stage == 'source':
        from phase5_source_materialize import materialize
        from phase5_source_reconcile import reconcile
        common = {'threads': settings['threads'], 'memory_limit': settings['memory_limit'],
                  'temp_directory': Path(settings['temp_directory'])}
        if settings.get('incremental_source'):
            result = reconcile(Path(settings['source_root']), Path(settings['previous_database']),
                               Path(settings['database']), **common)
        else:
            result = materialize(Path(settings['source_root']), Path(settings['database']), **common)
    elif stage in {'metadata', 'rosters_records'}:
        from phase3_duckdb_service import _load_duckdb
        from phase4_metadata import load_arena_settings, materialize_metadata_tables
        from phase5_refresh_workflow import _tournament_metadata_with_fallback, _materialize_records
        from phase4_materialize_route_derivatives import _create_relations as create_arena_relations
        connection = _load_duckdb().connect(str(settings['database']))
        try:
            connection.execute('SET threads=?', [max(1, int(settings['threads']))])
            connection.execute('SET memory_limit=?', [settings['memory_limit']])
            connection.execute('SET preserve_insertion_order=false')
            connection.execute('SET temp_directory=?', [str(settings['temp_directory'])])
            moving = Path(settings['moving_source_dir'])
            previous = Path(settings['previous_database'])
            if stage == 'metadata':
                tournaments, tournament_info = _tournament_metadata_with_fallback(moving, previous)
                arena, arena_info = load_arena_settings(Path(settings['arena_settings']))
                materialize_metadata_tables(connection, tournaments, arena)
                result = {'status': 'ok', 'tournament_info': tournament_info, 'arena_info': arena_info}
            else:
                arena_counts = create_arena_relations(connection, moving)
                record_counts = _materialize_records(connection, moving, previous)
                result = {'status': 'ok', 'arena_counts': arena_counts, 'record_counts': record_counts}
            connection.execute('CHECKPOINT')
        finally:
            connection.close()
    elif stage == 'builder':
        from phase5_refresh_workflow import _load_module
        builder = _load_module(Path(settings['builder']), 'phase5_isolated_builder')
        result_file = Path(settings['builder_report'])
        status = builder.run(Path(settings['database']), result_file,
                             threads=settings['threads'], memory_limit=settings['memory_limit'],
                             temp_directory=Path(settings['temp_directory']),
                             merge_players_path=Path(settings['merge_players']),
                             source_manifest=Path(settings['source_manifest']),
                             reuse_database=Path(settings['previous_database']),
                             reuse_report=settings.get('reuse_report') or {})
        if status != 0:
            raise RuntimeError('isolated builder did not succeed')
        result = json.loads(result_file.read_text(encoding='utf-8'))
    else:
        from phase5_snapshot_builder import build
        # These settings belong to this offline process only. Never modify the
        # API service's database-global pool or its independently tested budget.
        os.environ['DUCKDB_SNAPSHOT_MEMORY_LIMIT'] = settings['memory_limit']
        os.environ['DUCKDB_SERVING_THREADS'] = str(settings['threads'])
        result = build(Path(settings['root']), Path(settings['output']),
                       settings['generation'], settings['chunk'])
    result['stage_process_rss_highwater_bytes'] = rss_highwater_bytes()
    return result


if __name__ == '__main__':
    spec = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    with measure_resources([], 'offline_stage', stage=spec.get('stage')):
        output = execute(spec)
    Path(spec['result']).write_text(json.dumps(output, indent=2, sort_keys=True)+'\n', encoding='utf-8')
