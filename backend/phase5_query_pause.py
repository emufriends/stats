"""Linux process-owned refresh barrier; no stale flag files or public controls.

An intent lock rejects new queries before the worker waits for existing shared
query leases to drain. The work lock is exclusive throughout refresh. Files are
never unlinked: replacing a locked inode could bypass the barrier. Kernel locks
release on process exit; systemd's control-group kill stops refresh children.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import time


class AnalyticalRequestsPaused(RuntimeError):
    pass


class RefreshQueryGate:
    def __init__(self, path: str | Path):
        if os.name != 'posix':
            raise RuntimeError('refresh query barrier requires Linux process locks')
        import fcntl
        self.locking = fcntl
        self.path = Path(path)
        self.intent = self.path.with_name(self.path.name + '.intent')
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _open(self, path):
        return os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)

    def _shared(self, path):
        fd = self._open(path)
        try:
            self.locking.flock(fd, self.locking.LOCK_SH | self.locking.LOCK_NB)
            return fd
        except BlockingIOError:
            os.close(fd)
            raise AnalyticalRequestsPaused() from None
        except BaseException:
            os.close(fd)
            raise

    def blocked(self):
        try:
            fd = self._shared(self.intent)
        except AnalyticalRequestsPaused:
            return True
        os.close(fd)
        return False

    def fully_paused(self):
        try:
            fd = self._shared(self.path)
        except AnalyticalRequestsPaused:
            return True
        os.close(fd)
        return False

    @contextmanager
    def query(self):
        intent = self._shared(self.intent)
        try:
            work = self._shared(self.path)
        finally:
            os.close(intent)
        try:
            yield
        finally:
            os.close(work)

    @contextmanager
    def pause(self, timeout=130):
        deadline = time.monotonic() + timeout
        opened = []
        try:
            for path in (self.intent, self.path):
                fd = self._open(path)
                opened.append(fd)
                while True:
                    try:
                        self.locking.flock(fd, self.locking.LOCK_EX | self.locking.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError('analytical requests did not drain before refresh')
                        time.sleep(0.05)
            yield
        finally:
            for fd in reversed(opened):
                os.close(fd)
