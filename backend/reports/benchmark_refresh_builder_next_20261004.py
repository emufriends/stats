"""Native, serial reuse/canonical trials; no public release changes or BigQuery.

Production inputs are read-only. Only explicitly owned files inside WORK may
be removed, after their complete parity reports are saved. The real refresh
pause, shared memory cap, disk floor and worker priority remain in force.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

BASE = Path('/home/ascri')
WORK = BASE/'refresh-builder-next-20261004'
GROUP = Path('/sys/fs/cgroup/ark.slice/ark-analytics.slice')
INSTALLED = (BASE/'current-app').resolve()
CANDIDATE = WORK/'candidate-app'


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n')
    temporary.replace(path)


def multiset_fingerprint(connection, relation):
    moments = ','.join(f"SUM(CAST('0x'||SUBSTR(digest,{1+16*i},16) AS UBIGINT)::HUGEINT)" for i in range(4))
    return connection.execute(f'''SELECT COUNT(*),{moments} FROM (
      SELECT SHA256(TO_JSON(r)) AS digest FROM {relation} r)''').fetchone()


def prepare():
    assert INSTALLED.name == 'deploy-d92d444bae14542df270'
    assert not CANDIDATE.exists()
    inventory = json.loads((INSTALLED/'deployment-manifest.json').read_text())['files']
    for item in inventory:
        relative = Path(item['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        destination = CANDIDATE/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(INSTALLED/relative,destination)
    shutil.copy2(WORK/'phase2_local_vertical_slice.py',CANDIDATE/'phase2_local_vertical_slice.py')


def child(mode):
    # Reuse is the installed, unchanged producer. Canonical A/B uses the same
    # candidate helper with its exact legacy SQL selected for the control.
    sys.path.insert(0,str(INSTALLED if mode in {'reuse','reuse-parity'} else CANDIDATE))
    from phase3_duckdb_service import _load_duckdb
    from phase5_refresh_dependencies import log_dependency_signature,reuse_log_relations,LOG_RELATIONS,_row_multiset_digest
    from phase5_refresh_metrics import rss_highwater_bytes
    pointer = json.loads((BASE/'phase3_private_serving/current.json').read_text())
    generation = pointer['generation']
    manifest = json.loads((BASE/'phase2_private_data/generations'/(generation+'.manifest.json')).read_text())
    parent = BASE/'phase2_private_data/generations'/(generation+'.duckdb')
    database = WORK/('reuse.duckdb' if mode=='reuse-parity' else mode+'.duckdb')
    assert database.exists() if mode=='reuse-parity' else not database.exists()
    c = _load_duckdb().connect(str(database),read_only=mode=='reuse-parity')
    c.execute("SET memory_limit='800MB'")
    c.execute('SET threads=2')
    c.execute('SET preserve_insertion_order=false')
    spill = WORK/(mode+'-spill')
    spill.mkdir(exist_ok=False)
    c.execute('SET temp_directory=?',[str(spill)])
    c.execute(f"ATTACH '{str(parent).replace(chr(39),chr(39)*2)}' AS reuse_parent (READ_ONLY)")
    names = ([] if mode=='reuse-parity' else ['game_player_narrow','prepared_full_sample_narrow','source_logs']
             if mode=='reuse' else ['source_full_sample','game_player_narrow'])
    for name in names:
        c.execute(f'CREATE VIEW main.{name} AS SELECT * FROM reuse_parent.{name}')
    result = {'status':'running','mode':mode,'generation':generation,'stages':{}}
    path = WORK/(mode+'.json')
    save(path,result)
    try:
        if mode=='reuse-parity':
            earlier = json.loads((WORK/'reuse.json').read_text())
            assert earlier['generation']==generation and earlier['decision']=={'reason':'reused','relation_count':28}
            result['stages'].update(earlier['stages'])
            checks = []
            for name in LOG_RELATIONS:
                schema = c.execute(f'DESCRIBE main.{name}').fetchall()
                assert schema == c.execute(f'DESCRIBE reuse_parent.{name}').fetchall()
                # Every full typed row participates, with multiplicity. Four
                # independently summed 64-bit SHA-256 lanes and the row count
                # provide a cryptographic multiset fingerprint without sorting
                # or repeatedly scanning large immutable copies. HUGEINT sums
                # cannot overflow at this catalogue's measured row counts.
                before,after = multiset_fingerprint(c,'reuse_parent.'+name),multiset_fingerprint(c,'main.'+name)
                assert before == after,name
                checks.append({'relation':name,'rows':before[0],
                    'sha256_lane_sums':list(before[1:]),'multiset_fingerprint_matches':True})
                result['checks'] = checks
                save(path,result)
        elif mode=='reuse':
            started = time.perf_counter()
            signature = log_dependency_signature(c,manifest['source_materialization']['source_manifest'])
            result['stages']['dependency_proof_seconds'] = time.perf_counter()-started
            assert signature == manifest['builder']['log_dependency']
            # Borrow the existing read-only attachment backing the input views.
            # Only duplicate ATTACH/DETACH administration is suppressed; every
            # production signature/scope/key guard and copy SQL executes normally.
            class BorrowedParent:
                def execute(self, sql, parameters=None):
                    if sql.startswith('ATTACH ') and sql.endswith(' AS reuse_parent (READ_ONLY)'):
                        return c
                    if sql == 'DETACH reuse_parent':
                        return c
                    return c.execute(sql) if parameters is None else c.execute(sql,parameters)
            decision = {}
            started = time.perf_counter()
            reused = reuse_log_relations(BorrowedParent(),parent,manifest['builder'],signature,decision)
            c.execute('CHECKPOINT')
            result['stages']['guarded_reuse_seconds'] = time.perf_counter()-started
            assert reused is not None and decision == {'reason':'reused','relation_count':28}
            result['decision'] = decision
            save(path,result)
            checks = []
            for name in LOG_RELATIONS:
                assert c.execute(f'DESCRIBE main.{name}').fetchall() == c.execute(f'DESCRIBE reuse_parent.{name}').fetchall()
                # Exact multiplicity, not rounded means or sampled rows. DuckDB
                # may spill under the unchanged ceiling; the coordinator watches
                # the 4-GiB floor throughout this diagnostic work.
                differences = c.execute(f'''SELECT COUNT(*) FROM (
                  (SELECT * FROM main.{name} EXCEPT ALL SELECT * FROM reuse_parent.{name})
                  UNION ALL (SELECT * FROM reuse_parent.{name} EXCEPT ALL SELECT * FROM main.{name}))''').fetchone()[0]
                assert differences == 0,name
                checks.append({'relation':name,'different_rows':0})
                result['checks'] = checks
                save(path,result)
        else:
            from phase2_local_vertical_slice import create_prepared_full_sample_relation
            result['canonical_producer_sha256'] = hashlib.sha256(
                (CANDIDATE/'phase2_local_vertical_slice.py').read_bytes()).hexdigest()
            started = time.perf_counter()
            strategy = create_prepared_full_sample_relation(c,method='update' if mode=='canonical-update' else 'insert')
            result['stages']['construction_seconds'] = time.perf_counter()-started
            result['strategy'] = strategy
            assert strategy['method'] == ('copy_update' if mode=='canonical-update' else 'bounded_insert')
            assert c.execute('DESCRIBE main.prepared_full_sample_narrow').fetchall() == c.execute('DESCRIBE reuse_parent.prepared_full_sample_narrow').fetchall()
            save(path,result)
            started = time.perf_counter()
            if mode == 'canonical-insert':
                control = json.loads((WORK/'canonical-update.json').read_text())
                assert control['status'] == 'ok' and control['generation'] == generation
                assert control['mode'] == 'canonical-update'
                # The preceding serial control proved this complete digest
                # against the same immutable parent. Reuse that evidence,
                # not a sample or an unverified candidate digest.
                expected = control['exact_row_multiset']
                result['reference_digest_reused_from'] = 'canonical-update.json'
            else:
                expected = _row_multiset_digest(c,'reuse_parent.prepared_full_sample_narrow')
            actual = _row_multiset_digest(c,'main.prepared_full_sample_narrow')
            assert expected == actual
            result['stages']['parity_seconds'] = time.perf_counter()-started
            result['exact_row_multiset'] = actual
        result.update(status='ok',rss_highwater_bytes=rss_highwater_bytes(),database_bytes=database.stat().st_size)
    finally:
        c.close()
        save(path,result)


def run(canonical_only=False):
    os.setpriority(os.PRIO_PROCESS,0,19)
    sys.path.insert(0,str(INSTALLED))
    from phase5_query_pause import RefreshQueryGate
    from phase5_refresh_worker import wait_for_lightweight_api
    sys.path.insert(0,str(BASE/'refresh-duration-20261004'))
    from qualify_refresh_pause_2g_20261003 import outside_nonreclaimable,http
    pointer_path = BASE/'phase3_private_serving/current.json'
    before = pointer_path.read_bytes()
    assert int((GROUP/'memory.max').read_text()) == 1456*1024**2
    assert int((GROUP/'memory.swap.max').read_text()) == 0
    initial = dict(line.split() for line in (GROUP/'memory.events').read_text().splitlines())
    state = {'status':'running','phase':'waiting for lightweight API','stages':{}}
    if canonical_only:
        certified = json.loads((WORK/'reuse-parity.json').read_text())
        assert certified['status'] == 'ok' and len(certified['checks']) == 28
        assert certified['generation'] == json.loads(before)['generation']
        state['stages']['reuse-parity'] = certified
        state['retained_copy_evidence'] = 'qualification-canonical-cleanup.json'
    peak = {'combined_current_bytes':0,'estimated_host_bytes':0}
    stop = threading.Event()
    def sample():
        with (WORK/'memory.jsonl').open('w') as output:
            while not stop.is_set():
                current = int((GROUP/'memory.current').read_text())
                values = {'combined_current_bytes':current,'estimated_host_bytes':current+outside_nonreclaimable()+192*1024**2}
                for key,value in values.items():
                    peak[key] = max(peak[key],value)
                output.write(json.dumps({'time':time.time(),**values})+'\n')
                output.flush()
                stop.wait(1)
    monitor = threading.Thread(target=sample,daemon=True)
    monitor.start()
    try:
        with RefreshQueryGate(BASE/'phase2_private_data/analytical-refresh.lock').pause():
            wait_for_lightweight_api()
            modes = ('canonical-update','canonical-insert') if canonical_only else ('reuse-parity','canonical-update','canonical-insert')
            for mode in modes:
                state['phase'] = mode
                save(WORK/'qualification.json',state)
                started = time.monotonic()
                with (WORK/(mode+'.log')).open('w') as output:
                    process = subprocess.Popen([sys.executable,__file__,'--stage',mode],stdout=output,stderr=subprocess.STDOUT)
                    try:
                        while process.poll() is None:
                            if shutil.disk_usage(WORK).free < 4*1024**3:
                                raise RuntimeError('native trial reached its 4-GiB free-disk floor')
                            if time.monotonic()-started > 7200:
                                raise TimeoutError('native trial exceeded its two-hour window')
                            time.sleep(2)
                        assert process.returncode == 0,'stage failed: '+mode
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            process.wait(timeout=20)
                result = json.loads((WORK/(mode+'.json')).read_text())
                assert result['status'] == 'ok'
                state['stages'][mode] = result
                save(WORK/'qualification.json',state)
                if mode=='reuse-parity':
                    # Remove only our complete, redundant, validated trial copy
                    # after closing DuckDB. Keep all reports and real releases.
                    owned = WORK/'reuse.duckdb'
                    assert owned.resolve().parent == WORK.resolve() and not owned.is_symlink()
                    owned.unlink()
            assert pointer_path.read_bytes() == before and (BASE/'current-app').resolve() == INSTALLED
        deadline = time.monotonic()+120
        while time.monotonic()<deadline:
            try:
                code,value = http('/v1/status')
                if code==200 and not value.get('analytical_requests_paused') and not value.get('maintenance_only'):
                    break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('API did not resume')
        events = dict(line.split() for line in (GROUP/'memory.events').read_text().splitlines())
        delta = {key:int(value)-int(initial.get(key,0)) for key,value in events.items()}
        assert delta.get('oom',0) == delta.get('oom_kill',0) == 0
        assert peak['estimated_host_bytes'] <= 2*1024**3
        state.update(status='ok',phase='complete',memory_events_delta=delta,
            production_release_unchanged=True,api_resumed=True,bigquery_queries=0)
    except BaseException as error:
        state.update(status='failed',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        stop.set()
        monitor.join(5)
        if canonical_only:
            previous = json.loads((WORK/'qualification-canonical-cleanup.json').read_text())
            for key,value in previous['memory'].items():
                peak[key] = max(peak[key],value)
        state['memory'] = peak
        save(WORK/'qualification.json',state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--clean-spill',action='store_true')
    parser.add_argument('--resume-fingerprint',action='store_true')
    parser.add_argument('--resume-canonical',action='store_true')
    parser.add_argument('--canonical-only',action='store_true')
    parser.add_argument('--stage',choices=['reuse','reuse-parity','canonical-update','canonical-insert'])
    args = parser.parse_args()
    if args.resume_canonical:
        unit = subprocess.check_output(['systemctl','show','ark-refresh-builder-next-fingerprint-20261004.service','-p','ActiveState','--value'],text=True).strip()
        assert unit != 'active'
        failed = json.loads((WORK/'qualification.json').read_text())
        assert failed['status']=='failed' and failed['phase']=='canonical-update'
        certified = failed['stages']['reuse-parity']
        assert certified['status']=='ok' and len(certified['checks'])==28
        assert failed['memory']['estimated_host_bytes']<=2*1024**3
        events = dict(line.split() for line in (GROUP/'memory.events').read_text().splitlines())
        assert int(events['oom'])==int(events['oom_kill'])==0
        assert certified['generation']==json.loads((BASE/'phase3_private_serving/current.json').read_text())['generation']
        assert not (WORK/'qualification-canonical-cleanup.json').exists()
        (WORK/'qualification.json').rename(WORK/'qualification-canonical-cleanup.json')
        diagnostic = json.loads((WORK/'canonical-update.json').read_text())
        assert diagnostic['status']!='ok' and diagnostic['mode']=='canonical-update'
        for extension in ('json','log'):
            (WORK/('canonical-update.'+extension)).rename(WORK/('canonical-update-cleanup-failed.'+extension))
        database = WORK/'canonical-update.duckdb'
        assert database.resolve().parent==WORK.resolve() and not database.is_symlink()
        database.unlink()
        spill = WORK/'canonical-update-spill'
        assert spill.resolve().parent==WORK.resolve() and not spill.is_symlink()
        assert not any(path.is_symlink() for path in spill.rglob('*'))
        shutil.rmtree(spill)
        assert (BASE/'current-app').resolve()==INSTALLED and INSTALLED.name=='deploy-d92d444bae14542df270'
        shutil.copy2(WORK/'phase2_local_vertical_slice.py',CANDIDATE/'phase2_local_vertical_slice.py')
    elif args.resume_fingerprint:
        unit = subprocess.check_output(['systemctl','show','ark-refresh-builder-next-bounded-20261004.service','-p','ActiveState','--value'],text=True).strip()
        assert unit != 'active'
        failed = json.loads((WORK/'qualification.json').read_text())
        assert failed['status']=='failed' and failed.get('error_type')=='KeyboardInterrupt'
        assert not (WORK/'qualification-sliced.json').exists()
        (WORK/'qualification.json').rename(WORK/'qualification-sliced.json')
        (WORK/'reuse-parity.json').rename(WORK/'reuse-parity-sliced.json')
        spill = WORK/'reuse-parity-spill'
        assert spill.resolve().parent == WORK.resolve() and not spill.is_symlink()
        assert not any(path.is_symlink() for path in spill.rglob('*'))
        shutil.rmtree(spill)
    elif args.clean_spill:
        unit = subprocess.check_output(['systemctl','show','ark-refresh-builder-next-20261004.service','-p','ActiveState','--value'],text=True).strip()
        assert unit != 'active'
        failed = json.loads((WORK/'qualification.json').read_text())
        assert failed['status']=='failed' and failed['error']=='native trial reached its 4-GiB free-disk floor'
        assert not (WORK/'qualification-disk-floor.json').exists()
        (WORK/'qualification.json').rename(WORK/'qualification-disk-floor.json')
        spill = WORK/'reuse-spill'
        assert spill.resolve().parent == WORK.resolve() and not spill.is_symlink()
        assert not any(path.is_symlink() for path in spill.rglob('*'))
        shutil.rmtree(spill)
    else:
        prepare() if args.prepare else child(args.stage) if args.stage else run(args.canonical_only)
