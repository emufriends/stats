"""Private full/partial snapshot test with phase-specific sampled resident RAM.

The original immutable database is read-only. Each phase peak is observed RSS,
not an additive allocation; the process lifetime maximum is reported separately.
"""
import argparse
import functools
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time


def rss_current_bytes():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):
            return int(line.split()[1]) * 1024
    return None


class PhaseProfiler:
    def __init__(self, output, rss):
        self.output, self.rss = output, rss
        self.records = []
        self.lock = threading.Lock()
        self.current = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self):
        while not self.stop.wait(.1):
            value = self.rss() or 0
            with self.lock:
                if self.current is not None:
                    self.current['sampled_rss_peak_bytes'] = max(self.current['sampled_rss_peak_bytes'], value)
                    self.current['samples'] += 1

    def wrap(self, function, identify):
        @functools.wraps(function)
        def measured(*args, **kwargs):
            before = self.rss() or 0
            record = {**identify(args, kwargs), 'rss_before_bytes': before,
                      'sampled_rss_peak_bytes': before, 'samples': 0, 'status': 'running'}
            started = time.perf_counter()
            with self.lock:
                self.current = record
            try:
                result = function(*args, **kwargs)
                record['status'] = 'ok'
                return result
            except BaseException as error:
                record.update(status='failed', error_type=type(error).__name__)
                raise
            finally:
                after = self.rss() or 0
                record.update(rss_after_bytes=after, seconds=round(time.perf_counter()-started, 3))
                with self.lock:
                    record['sampled_rss_peak_bytes'] = max(record['sampled_rss_peak_bytes'], after)
                    self.records.append(record)
                    self.current = None
                self.output.write_text(json.dumps(self.records, indent=2)+'\n')
                print(json.dumps({'event': 'phase_memory', **record}), flush=True)
        return measured

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--memory-limit', default='600MB')
    parser.add_argument('--only-page')
    parser.add_argument('--only-view')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(args.work).free < 5 * 1024**3:
        raise RuntimeError('snapshot qualification requires at least 5 GiB free')
    sys.path.insert(0, str(args.app))
    import phase5_snapshot_builder as builder
    from phase5_refresh_metrics import rss_highwater_bytes
    from phase3_duckdb_service import _load_duckdb
    production_root = Path('/home/ascri')
    pointer = production_root / 'phase3_private_serving/current.json'
    original_pointer = pointer.read_bytes()
    current = json.loads(original_pointer)
    generation = current['generation']
    root = args.work / 'root'
    target = root / 'phase2_private_data/generations'
    target.mkdir(parents=True)
    source = production_root / 'phase2_private_data/generations'
    (target / (generation+'.duckdb')).symlink_to(source / (generation+'.duckdb'))
    (target / (generation+'.manifest.json')).write_bytes((source / (generation+'.manifest.json')).read_bytes())
    local_pointer = root / 'phase3_private_serving/current.json'
    local_pointer.parent.mkdir(parents=True)
    local_pointer.write_bytes(original_pointer)
    os.environ['DUCKDB_SNAPSHOT_MEMORY_LIMIT'] = args.memory_limit
    os.environ['DUCKDB_SERVING_THREADS'] = '1'
    # A symlinked read-only database still resolves its default spill folder
    # beside the real database. Separate test processes must never share that
    # folder with each other or the live API. Keep the instance open so every
    # diagnostic connection inherits this private spill path and engine budget.
    keeper = _load_duckdb().connect(str(source / (generation+'.duckdb')), read_only=True)
    keeper.execute('SET memory_limit=?', [args.memory_limit])
    keeper.execute('SET threads=1')
    keeper.execute('SET preserve_insertion_order=false')
    keeper.execute('SET temp_directory=?', [str(args.work / 'spill')])
    profiler = PhaseProfiler(args.work / 'page-memory.json', rss_current_bytes)
    builder.build_arena_bundle = profiler.wrap(builder.build_arena_bundle,
        lambda a, k: {'page': 'arena', 'view': 'top_100', 'dataset': None})
    builder.build_one = profiler.wrap(builder.build_one,
        lambda a, k: {'page': a[1], 'view': a[2], 'dataset': a[3], 'path': str(a[4])})
    for name, label in (('_build_player_indexes', 'player_indexes'),
                        ('_build_home_bootstrap', 'home_bootstrap'), ('_build_pack', 'default_pack')):
        setattr(builder, name, profiler.wrap(getattr(builder, name),
                lambda a, k, label=label: {'page': label, 'view': None, 'dataset': None}))
    started = time.perf_counter()
    report = {'status': 'running', 'generation': generation, 'memory_limit': args.memory_limit,
              'partial': bool(args.only_page or args.only_view), 'threads': 1}
    try:
        result = builder.build(root, args.work / 'snapshots', generation, 100000,
                               only_page=args.only_page, only_view=args.only_view)
        (args.work / 'snapshots/manifest.json').write_text(json.dumps(result, indent=2)+'\n')
        report.update(status='ok' if result['status'] in {'ok', 'partial'} else 'failed',
                      snapshot_count=result['snapshot_count'], artifact_count=result.get('artifact_count'))
    except BaseException as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        profiler.close()
        report.update(seconds=round(time.perf_counter()-started, 3),
                      process_rss_highwater_bytes=rss_highwater_bytes(),
                      production_pointer_unchanged=pointer.read_bytes() == original_pointer,
                      phases=profiler.records)
        (args.work / 'result.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({'event': 'profile_result', **report}), flush=True)
        keeper.close()
    if not report['production_pointer_unchanged'] or report['status'] != 'ok':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
