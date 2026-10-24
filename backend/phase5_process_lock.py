"""Process-owned exclusive file locks. Lock files are never unlinked.

Kernel ownership survives neither process exit nor a kill. Persistent inodes
prevent a second process from locking a replacement file while an owner lives.
"""
from contextlib import contextmanager
import os
from pathlib import Path


def acquire(path: Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(fd).st_size == 0:
                os.write(fd, b'\0')
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def exclusive(path: Path):
    try:
        fd = acquire(path)
    except OSError as error:
        raise RuntimeError(f'another process owns {Path(path).name}') from error
    try:
        yield fd
    finally:
        os.close(fd)
