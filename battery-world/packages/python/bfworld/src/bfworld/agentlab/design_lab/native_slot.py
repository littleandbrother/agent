"""Cross-process native lease with same-process phase/thread handoff.

Each Workbench still serializes operations with its engineering lock. The
paper dispatcher holds a phase lease; its engineering thread may join that
same process lease without deadlocking. A second process cannot join it.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import threading
from ..runtime_config import RUNTIME_ROOT

_guard = threading.Lock()
_leases = {}


def _fork_child():
    global _guard, _leases
    # Close inherited descriptors without LOCK_UN (the parent owns its lease).
    for value in _leases.values(): value['file'].close()
    _guard = threading.Lock()
    _leases = {}


os.register_at_fork(after_in_child=_fork_child)


@contextmanager
def native_slot(path=None, *, blocking=True):
    path = Path(path) if path is not None else RUNTIME_ROOT / 'design-native.lock'
    key = str(path.resolve())
    with _guard:
        value = _leases.get(key)
        if value is None:
            file = path.open('a')
            try:
                fcntl.flock(file, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BaseException:
                file.close()
                raise
            value = {'file': file, 'references': 0}
            _leases[key] = value
        value['references'] += 1
    try:
        yield {'path': key, 'pid': os.getpid()}
    finally:
        with _guard:
            value['references'] -= 1
            if value['references'] == 0:
                fcntl.flock(value['file'], fcntl.LOCK_UN)
                value['file'].close()
                del _leases[key]
