"""Finite BFA-100 admission, references and independent resource accounting."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

HERE = Path(__file__).resolve().parent
OUT, BASE = HERE.parent, HERE.parent.parent
ROOT = BASE.parents[2]
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
LAB = APP / 'packages/python/bfworld/src'
sys.path.insert(0, str(LAB))
DB = Path('/Users/depengsu/.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite')
PYTHON = Path('/Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python')
PACKAGE = 'BF-PQE-RELATION-SYNTHESIS-20261102-001'
SEEDS = (314159, 271828)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def load(path):
    path = Path(path)
    if path.suffix == '.gz':
        with gzip.open(path, 'rt') as stream:
            return json.load(stream)
    return json.loads(path.read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if path.suffix == '.gz':
        with gzip.open(path, 'wt') as stream:
            stream.write(text)
    else:
        path.write_text(text)


def ref(path):
    path = Path(path)
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def connect():
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def capacity():
    fs = os.statvfs(ROOT)
    free = fs.f_bavail * fs.f_frsize
    stats = [p.stat() for p in OUT.rglob('*') if p.is_file()]
    allocated = sum(max(4096, s.st_blocks * 512) for s in stats)
    if free < 11_000_000_000 or allocated >= 150_000_000:
        raise RuntimeError('STORAGE_HEADROOM_OR_RETAINED_CAP')
    return dict(at=now(), available_bytes=free, allocated_upper_bound_bytes=allocated,
                logical_bytes=sum(s.st_size for s in stats))


def accounting_gate(owner=None):
    from bfworld.agentlab import historical_usage as h
    with connect() as db:
        if owner:
            blockers = h.new_batch_usage_blockers(db, owner)
        else:
            excepted = h.verified_exceptions(db, PACKAGE)
            blockers = [dict(row) for row in db.execute(
                "SELECT * FROM model_requests WHERE status='UNKNOWN' OR (status='SETTLED' AND usage IS NULL)")
                if excepted.get(row['id']) != h.identity(dict(row))]
    if blockers:
        raise RuntimeError('NEW_MISSING_USAGE_STOP:' + ','.join(x['id'] for x in blockers))
    return dict(status='PASS', exact_historical_unknowns=2, new_missing_usage=0)


def ready():
    if time.time() >= load(HERE / 'preflight.json')['absolute_deadline_epoch']:
        raise RuntimeError('PACKAGE_ABSOLUTE_DEADLINE')
    capacity()
    accounting_gate()


def require_sources(protocol):
    for path, sha in protocol.get('source_hashes', {}).items():
        if ref(path)['sha256'] != sha:
            raise RuntimeError('FROZEN_SOURCE_CHANGED:' + path)


def journal(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                                allow_nan=False) + '\n')
