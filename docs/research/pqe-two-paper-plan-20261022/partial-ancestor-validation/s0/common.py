"""Shared finite-package paths, immutable bindings, and resource admission."""
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
OUT = HERE.parent
BASE = OUT.parent
ROOT = BASE.parents[2]
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
LAB = APP / 'packages/python/bfworld/src'
sys.path.insert(0, str(LAB))
DB = Path('/Users/depengsu/.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite')
PYTHON = Path('/Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python')
PACKAGE = 'BF-PQE-PARTIAL-ANCESTOR-VALIDATION-20261026-001'
SEEDS = (314159, 271828, 161803)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def load(path):
    path = Path(path)
    if path.suffix == '.gz':
        with gzip.open(path, 'rt') as stream:
            return json.load(stream)
    return json.loads(path.read_text())


def ref(path):
    path = Path(path)
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def capacity():
    fs = os.statvfs(ROOT)
    available = fs.f_bavail * fs.f_frsize
    allocated = sum(p.stat().st_blocks * 512 for p in OUT.rglob('*') if p.is_file())
    if available < 11_500_000_000 or allocated >= 200_000_000:
        raise RuntimeError('STORAGE_HEADROOM_OR_RETAINED_CAP')
    return dict(at=now(), available_bytes=available, allocated_upper_bound_bytes=allocated)


def connect():
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    return db


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


def require_capacity_and_time():
    preflight = load(HERE / 'preflight.json')
    if time.time() >= preflight['absolute_deadline_epoch']:
        raise RuntimeError('PACKAGE_ABSOLUTE_DEADLINE')
    capacity()
    accounting_gate()
    return preflight


def require_sources(protocol):
    for path, sha in protocol['source_hashes'].items():
        if ref(ROOT / path)['sha256'] != sha:
            raise RuntimeError('FROZEN_SOURCE_CHANGED:' + path)


def journal(path, value):
    with Path(path).open('a') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                                allow_nan=False) + '\n')
