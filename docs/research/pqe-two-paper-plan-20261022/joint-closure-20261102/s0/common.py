"""New finite package context; existing apparatus/runtime dependencies stay read-only."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

HERE=Path(__file__).resolve().parent
OUT,BASE=HERE.parent,HERE.parent.parent
ROOT=BASE.parents[2]
OLD=BASE/'relation-synthesis-20261102'
APP=ROOT/'workbench/bf-campaign-s0-20261019/battery-world'
LAB=APP/'packages/python/bfworld/src'
sys.path.insert(0,str(LAB))
DB=Path('/Users/depengsu/.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite')
PYTHON=Path('/Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python')
PACKAGE='BF-PQE-JOINT-CLOSURE-20261102-001'
REPEATS=(314159,271828)


def module(path,name):
    if name in sys.modules:
        return sys.modules[name]
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec)
    sys.modules[name]=value
    spec.loader.exec_module(value)
    return value


_utility=module(OLD/'s0/common.py','joint_readonly_stateless_utilities')
now,load,save,ref,digest,journal=_utility.now,_utility.load,_utility.save,_utility.ref,_utility.digest,_utility.journal
connect=_utility.connect
require_sources=_utility.require_sources


def capacity():
    fs=os.statvfs(ROOT)
    free=fs.f_bavail*fs.f_frsize
    stats=[p.stat() for p in OUT.rglob('*') if p.is_file()]
    allocated=sum(max(4096,s.st_blocks*512) for s in stats)
    if free<11_000_000_000 or allocated>=200_000_000:
        raise RuntimeError('STORAGE_HEADROOM_OR_RETAINED_CAP')
    return dict(at=now(),available_bytes=free,allocated_upper_bound_bytes=allocated,
                logical_bytes=sum(s.st_size for s in stats))


def accounting_gate(owner=None):
    from bfworld.agentlab import historical_usage as h
    with connect() as db:
        if owner:
            blockers=h.new_batch_usage_blockers(db,owner)
        else:
            excepted=h.verified_exceptions(db,PACKAGE)
            blockers=[dict(r) for r in db.execute("SELECT * FROM model_requests WHERE status='UNKNOWN' OR (status='SETTLED' AND usage IS NULL)") if excepted.get(r['id'])!=h.identity(dict(r))]
    if blockers:
        raise RuntimeError('NEW_MISSING_USAGE_STOP:'+','.join(x['id'] for x in blockers))
    return dict(status='PASS',exact_historical_unknowns=2,new_missing_usage=0)


def ready():
    if time.time()>=load(HERE/'preflight.json')['absolute_deadline_epoch']:
        raise RuntimeError('PACKAGE_ABSOLUTE_DEADLINE')
    capacity();accounting_gate()


def compact_file(path):
    """One canonical gzip, exact byte readback, no duplicate backup."""
    path=Path(path)
    if not path.resolve().is_relative_to(OUT) or path.is_symlink():
        raise RuntimeError('OWNED_RESIDENT_OUTPUT_REQUIRED')
    data=path.read_bytes()
    target=path.with_name(path.name+'.gz')
    if target.exists():
        raise RuntimeError('CANONICAL_COMPRESSION_TARGET_EXISTS')
    with gzip.open(target,'wb') as stream:stream.write(data)
    with gzip.open(target,'rb') as stream:
        if stream.read()!=data:raise RuntimeError('FULL_GZIP_READBACK_FAILED')
    original_sha=hashlib.sha256(data).hexdigest()
    path.unlink()
    return dict(path=str(target),sha256=ref(target)['sha256'],original_sha256=original_sha,original_bytes=len(data))
