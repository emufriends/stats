"""Bounded refresh telemetry: timings and resource counters, never SQL/values."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
import json
import re
import threading
import time
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def rss_highwater_bytes():
    if os.name == 'nt':
        return None
    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def rss_current_bytes():
    """Linux resident memory now, distinct from the process lifetime maximum."""
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def spill_bytes(path):
    if path is None or not path.is_dir():
        return 0
    # DuckDB spill files are flat; avoid recursively traversing private data.
    try:
        return sum(p.stat().st_size for p in path.iterdir() if p.is_file())
    except OSError:
        # Telemetry must never mask a query failure or a spill-file cleanup race.
        return None


# ---------------------------------------------------------------------------
# Resource windows (measurement only)
#
# `ru_maxrss` is a lifetime maximum, so it cannot say WHICH statement or snapshot
# needed the memory. A resource window answers that: while a window is open, a
# daemon thread polls this process' resident memory and (on Linux with cgroup v2)
# the service/slice memory counters that the 1456 MiB systemd ceiling actually
# enforces, and keeps the maxima seen inside the window. DuckDB releases the GIL
# while a query runs, so polling continues during long statements.
#
# Privacy/safety: counters and fixed stage labels, never SQL, values or paths. Every read
# is best-effort; on non-Linux hosts or restricted sandboxes fields are None and
# measurement can never change or fail the measured work. Nothing here alters
# `rss_highwater_bytes()` or any published artifact.
# ---------------------------------------------------------------------------
_CGROUP_ROOT = Path('/sys/fs/cgroup')
_EVENT_KEYS = ('high', 'max', 'oom', 'oom_kill')


def _own_cgroup_directory():
    """cgroup v2 directory of this process (the service), or None."""
    try:
        for line in Path('/proc/self/cgroup').read_text().splitlines():
            if line.startswith('0::'):
                return _CGROUP_ROOT / line[3:].strip().lstrip('/')
    except OSError:
        pass
    return None


def _read_int(path):
    try:
        return int(Path(path).read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _read_keyed(path):
    values = {}
    try:
        for line in Path(path).read_text().splitlines():
            key, _, number = line.partition(' ')
            try:
                values[key] = int(number)
            except ValueError:
                continue
    except OSError:
        pass
    return values


class ResourceSampler:
    """Polls memory counters for every open window (see section comment)."""

    def __init__(self, interval=0.5):
        self.interval = interval
        self._service = _own_cgroup_directory()
        self._slice = self._service.parent if self._service is not None else None
        self._windows = []
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None
        self._tick = 0
        self._last_timeline = 0.0

    def _events(self):
        if self._slice is None:
            return None
        events = _read_keyed(self._slice / 'memory.events')
        return {key: events.get(key) for key in _EVENT_KEYS} if events else None

    def _sample(self):
        sample = {'rss': rss_current_bytes()}
        if self._service is not None:
            stat = _read_keyed(self._service / 'memory.stat')
            sample['service_anon'] = stat.get('anon')
            sample['service_file'] = stat.get('file')
            sample['service_current'] = _read_int(self._service / 'memory.current')
        if self._slice is not None:
            sample['slice_current'] = _read_int(self._slice / 'memory.current')
            sample['slice_anon'] = _read_keyed(self._slice / 'memory.stat').get('anon')
        return sample

    def _timeline(self, sample):
        """Optional coarse memory timeline (ARK_RESOURCE_TIMELINE_FILE), ~every 30 s."""
        path = os.environ.get('ARK_RESOURCE_TIMELINE_FILE')
        now = time.time()
        if not path or now - self._last_timeline < 30:
            return
        self._last_timeline = now
        try:
            with self._lock:
                labels = sorted({window['label'] for window in self._windows if window.get('label')})
            record = {'t': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                      'pid': os.getpid(), 'stage_windows': len(self._windows),
                      'window_labels': labels,
                      'events': self._events(), **sample}
            with Path(path).open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(record, sort_keys=True)+'\n')
        except OSError:
            pass   # diagnostics must never disturb the refresh

    def _absorb(self, window, sample, spill):
        window['samples'] += 1
        for key, value in sample.items():
            if value is not None and (window['peak'].get(key) is None or value > window['peak'][key]):
                window['peak'][key] = value
        if spill is not None and (window['peak_spill'] is None or spill > window['peak_spill']):
            window['peak_spill'] = spill

    def _loop(self):
        while True:
            with self._lock:
                windows = list(self._windows)
            if not windows:
                self._wake.wait()
                self._wake.clear()
                continue
            self._tick += 1
            try:
                sample = self._sample()
                self._timeline(sample)
                spills = {}
                for window in windows:
                    spill = None
                    # Listing a spill directory costs more than reading counters.
                    if window['spill_directory'] is not None and self._tick % 4 == 0:
                        directory = window['spill_directory']
                        if directory not in spills:
                            spills[directory] = spill_bytes(directory)
                        spill = spills[directory]
                    with self._lock:
                        if any(item is window for item in self._windows):
                            self._absorb(window, sample, spill)
            except Exception:
                pass
            time.sleep(self.interval)

    def begin(self, spill_directory=None):
        window = None
        try:
            window = {'peak': {}, 'peak_spill': None, 'samples': 0, 'spill_directory': spill_directory,
                      'events_before': self._events(), 'started': time.perf_counter()}
            self._absorb(window, self._sample(), None)
            with self._lock:
                self._windows.append(window)
                if self._thread is None:
                    thread = threading.Thread(target=self._loop, name='resource-sampler', daemon=True)
                    thread.start()
                    self._thread = thread
            self._wake.set()
            return window
        except Exception:
            with self._lock:
                self._windows = [item for item in self._windows if item is not window]
            return None

    def end(self, window):
        """Close a window and return bounded, numbers-only maxima."""
        if window is None:
            return {}
        # Detach before the final sample so the polling thread cannot mutate a
        # returned peak. Failed telemetry must not leak an open window either.
        with self._lock:
            self._windows = [item for item in self._windows if item is not window]
        try:
            self._absorb(window, self._sample(),
                         spill_bytes(window['spill_directory']) if window['spill_directory'] is not None else None)
            peak = window['peak']
            before, after = window['events_before'], self._events()
            delta = None
            if before and after:
                delta = {key: (after[key] - before[key]) if after[key] is not None and before[key] is not None else None
                         for key in _EVENT_KEYS}
            return {
                'peak_process_rss_bytes': peak.get('rss'),
                'peak_service_cgroup_anon_bytes': peak.get('service_anon'),
                'peak_service_cgroup_file_bytes': peak.get('service_file'),
                'peak_service_cgroup_current_bytes': peak.get('service_current'),
                'peak_slice_current_bytes': peak.get('slice_current'),
                'peak_slice_anon_bytes': peak.get('slice_anon'),
                'slice_memory_events_delta': delta,
                'peak_spill_bytes': window['peak_spill'],
                'resource_samples': window['samples'],
            }
        except Exception:
            return {}

    @contextmanager
    def measure(self, sink, label, **labels):
        """Append {label, seconds, maxima...} to `sink` (a list) when the block ends."""
        try:
            window = self.begin(labels.pop('spill_directory', None))
            if window is not None:
                window['label'] = str(labels.get('stage') or label)
        except Exception:
            window = None
        started = time.perf_counter()
        record = {'label': label, **labels}
        try:
            yield record   # the caller may add its own numbers before the block ends
            record['state'] = 'succeeded'
        except BaseException:
            record['state'] = 'failed'
            raise
        finally:
            try:
                record['seconds'] = round(time.perf_counter()-started, 6)
                record.update(self.end(window))
                record['process_rss_after_bytes'] = rss_current_bytes()
                sink.append(record)
            except Exception:
                pass   # measurement must never fail the measured work


_SAMPLER = None


def get_sampler():
    global _SAMPLER
    if _SAMPLER is None:
        _SAMPLER = ResourceSampler()
    return _SAMPLER


@contextmanager
def measure_resources(sink, label, **labels):
    """Fail-open setup/finalization while preserving the measured exception.

    Context construction itself can fail (missing counters, thread creation,
    disk errors or a patched sampler). Never wrap the caller's block in a broad
    exception handler: its real analytical failure must still propagate.
    """
    context = None
    record = {}
    try:
        context = get_sampler().measure(sink, label, **labels)
        record = context.__enter__()
    except Exception:
        context = None
    try:
        yield record
    except BaseException:
        if context is not None:
            import sys
            try:
                context.__exit__(*sys.exc_info())
            except Exception:
                pass
        raise
    else:
        if context is not None:
            try:
                context.__exit__(None, None, None)
            except Exception:
                pass


@contextmanager
def private_timeline(path):
    """Scope the private run's timeline to this worker and inherited children."""
    previous = os.environ.get('ARK_RESOURCE_TIMELINE_FILE')
    try:
        os.environ['ARK_RESOURCE_TIMELINE_FILE'] = str(path)
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            if previous is None:
                os.environ.pop('ARK_RESOURCE_TIMELINE_FILE', None)
            else:
                os.environ['ARK_RESOURCE_TIMELINE_FILE'] = previous
        except Exception:
            pass


class RefreshTimings:
    def __init__(self):
        self.stages = []

    def record(self, name, started, started_at, *, state='succeeded'):
        self.stages.append({
            'phase': name, 'started_at': started_at, 'completed_at': utc_now(),
            'state': state, 'seconds': round(time.perf_counter()-started, 6),
            'process_rss_highwater_bytes': rss_highwater_bytes(),
            'process_rss_current_bytes': rss_current_bytes(),
        })

    @contextmanager
    def stage(self, name):
        started = time.perf_counter()
        started_at = utc_now()
        state = 'succeeded'
        try:
            with measure_resources([], 'refresh_stage', stage=name):
                yield
        except BaseException:
            state = 'failed'
            raise
        finally:
            self.record(name, started, started_at, state=state)


class TimedConnection:
    """DuckDB proxy that records execution/fetch time without storing query text."""
    def __init__(self, connection, spill_directory=None):
        self.connection = connection
        self.spill_directory = spill_directory
        self.statements = []
        self._last = None
        # Optional private progress journal survives an interrupted qualification.
        # Records contain only fixed operation/relation names and resource counters,
        # never SQL, parameters, exception text or authenticated request values.
        self.progress_path = os.environ.get('DUCKDB_BUILDER_PROGRESS_FILE')

    def _journal(self, record):
        if not self.progress_path:
            return
        try:
            with Path(self.progress_path).open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(record, sort_keys=True)+'\n')
        except OSError:
            # Diagnostics must not turn successful analytical work into failure.
            pass

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def _begin_window(self):
        try:
            return get_sampler().begin(self.spill_directory)
        except Exception:
            return None   # measurement must never fail a statement

    @staticmethod
    def _end_window(window):
        try:
            return get_sampler().end(window)
        except Exception:
            return {}

    def _run(self, method, sql, *args, **kwargs):
        # Only the operation and fixed relation identifier enter the report.
        text = re.sub(r'^\s*(?:--[^\n]*\n\s*)*', '', str(sql))
        match = re.match(r'(CREATE(?: OR REPLACE)?(?: TEMP)? TABLE|INSERT INTO|UPDATE|DROP TABLE(?: IF EXISTS)?|ALTER TABLE)\s+([A-Za-z_][A-Za-z0-9_]*)', text, re.I)
        words = text.split(None, 1)
        record = {'operation': match[1].upper() if match else (words[0].upper() if words else 'EMPTY'),
                  'relation': match[2] if match else None, 'seconds': 0.0,
                  'process_rss_before_bytes': rss_current_bytes()}
        self.statements.append(record)
        self._last = record
        self._journal({**record, 'state': 'started'})
        window = self._begin_window()
        started = time.perf_counter()
        try:
            getattr(self.connection, method)(sql, *args, **kwargs)
            record['state'] = 'succeeded'
        except BaseException:
            record['state'] = 'failed'
            raise
        finally:
            record['seconds'] = round(time.perf_counter()-started, 6)
            record['process_rss_highwater_bytes'] = rss_highwater_bytes()
            record['process_rss_after_bytes'] = rss_current_bytes()
            record['spill_bytes_after'] = spill_bytes(self.spill_directory)
            # Per-statement maxima (measurement only; never affects the statement).
            record.update(self._end_window(window))
            self._journal(record)
        return self

    def execute(self, sql, *args, **kwargs):
        return self._run('execute', sql, *args, **kwargs)

    def executemany(self, sql, *args, **kwargs):
        return self._run('executemany', sql, *args, **kwargs)

    def _fetch(self, method, *args):
        started = time.perf_counter()
        try:
            return getattr(self.connection, method)(*args)
        finally:
            if self._last is not None:
                self._last['seconds'] = round(self._last['seconds'] + time.perf_counter()-started, 6)

    def fetchone(self):
        return self._fetch('fetchone')

    def fetchall(self):
        return self._fetch('fetchall')

    def fetchmany(self, *args):
        return self._fetch('fetchmany', *args)
