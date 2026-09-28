"""Content-bound protocols, quiet checkpoints and isolated trial workspaces.

This is an operator study adapter, not another scientific-world authority. It
uses the workbench's canonical identity and retains original product evidence.
Only declared, quiet artifact checkpoints are supported; live native jobs and
opaque native application state are deliberately not replayed.
"""
from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import platform
import sys
import tempfile
import time
import fcntl

from ..store import canonical, identity

SCHEMA = 'bf-research-v1'
KEY = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$')
KINDS = {'protocols', 'checkpoints', 'evidence', 'supports', 'audits', 'reports', 'inventories'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_key(value):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise ValueError('RESEARCH_INVALID_KEY')
    return value


def relative(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or str(p) != value:
        raise ValueError('RESEARCH_PATH_ESCAPE')
    if any(x in {'.git', '.env', 'secrets', 'node_modules', '__pycache__'} for x in p.parts) or p.suffix in {'.key', '.token'}:
        raise ValueError('RESEARCH_PRIVATE_PATH')
    return p


def checked_file(root, name):
    root = Path(root).resolve()
    p = root / relative(name)
    if any(x.is_symlink() for x in [p, *p.parents] if x != root and root in x.parents):
        raise ValueError('RESEARCH_SYMLINK_DENIED')
    if not p.resolve().is_relative_to(root) or not p.is_file():
        raise ValueError('RESEARCH_SOURCE_MISSING')
    return p


def write_atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def implementation_binding():
    base = Path(__file__).resolve().parent
    paths = list(base.glob('*.py')) + [base.parent/'product_energy.py', base.parent/'programmed.py',
                                     base.parent/'provider.py', base.parent/'recovery.py',
                                     base.parent/'store.py', base.parent/'experiments.py',
                                     base.parent.parent/'coupled'/'engine.py', base.parent.parent/'coupled'/'profiled.py',
                                     base.parent.parent/'kernel'/'canonical.py']
    return {str(p.relative_to(base.parent.parent)): sha(p.read_bytes()) for p in sorted(paths)}


class Research:
    def __init__(self, home, study='abc-development-v1'):
        self.home = Path(home).resolve()
        self.root = self.home/'research'/safe_key(study)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def locked(self):
        with (self.root/'lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def put(self, kind, value):
        if kind not in KINDS:
            raise ValueError('RESEARCH_KIND')
        raw = canonical(value).encode()
        key = sha(raw)
        path = self.root/kind/(key+'.json')
        with self.locked():
            if path.exists():
                if path.read_bytes() != raw:
                    raise ValueError('RESEARCH_IMMUTABLE_TAMPER')
            else:
                write_atomic(path, raw)
        return key

    def get(self, kind, key):
        if kind not in KINDS or not re.fullmatch('[a-f0-9]{64}', key or ''):
            raise ValueError('RESEARCH_RECORD_KEY')
        raw = (self.root/kind/(key+'.json')).read_bytes()
        if sha(raw) != key:
            raise ValueError('RESEARCH_RECORD_TAMPER')
        return json.loads(raw)

    def journal(self):
        p = self.root/'events.jsonl'
        if not p.exists():
            return []
        raw = p.read_bytes()
        if raw and not raw.endswith(b'\n'):
            raise ValueError('RESEARCH_JOURNAL_INCOMPLETE_RECONCILE_REQUIRED')
        out = []
        for line in raw.splitlines():
            row = json.loads(line)
            digest = row.pop('hash')
            if digest != identity(row) or row['previous'] != (out[-1]['hash'] if out else None) or row['seq'] != len(out):
                raise ValueError('RESEARCH_JOURNAL_TAMPER')
            out.append({**row, 'hash': digest})
        return out

    def event(self, kind, data):
        with self.locked():
            rows = self.journal()
            row = dict(seq=len(rows), previous=rows[-1]['hash'] if rows else None,
                       time=time.time(), kind=kind, data=data)
            row['hash'] = identity(row)
            with (self.root/'events.jsonl').open('ab') as f:
                f.write((canonical(row)+'\n').encode())
                f.flush()
                os.fsync(f.fileno())
        return row

    def register(self, protocol):
        required = {'id', 'paper', 'hypothesis', 'falsifier', 'arms', 'units', 'repetitions',
                    'budget', 'split', 'primary_metric', 'failure_rule', 'claim_boundary',
                    'implementation', 'model', 'world_revision', 'harness_revision', 'verifier_revision', 'checkpoints'}
        if not required <= protocol.keys() or protocol['paper'] not in {'A', 'B', 'C'}:
            raise ValueError('RESEARCH_PROTOCOL_INCOMPLETE')
        safe_key(protocol['id'])
        for field in ['arms', 'units']:
            if not protocol[field] or len(set(protocol[field])) != len(protocol[field]):
                raise ValueError('RESEARCH_PROTOCOL_DUPLICATE')
            for item in protocol[field]:
                safe_key(item)
        if type(protocol['repetitions']) is not int or not 1 <= protocol['repetitions'] <= 100:
            raise ValueError('RESEARCH_REPETITIONS')
        if protocol['split'] not in {'development', 'mechanism-pilot', 'prospective-confirmation'}:
            raise ValueError('RESEARCH_SPLIT')
        b = protocol['budget']
        for k in ['study_usd', 'trial_usd', 'study_wall_s', 'trial_wall_s', 'model_calls_per_trial']:
            if type(b.get(k)) not in (int, float) or not math.isfinite(b[k]) or b[k] < 0:
                raise ValueError('RESEARCH_BUDGET_MISSING')
        if b['trial_usd'] > b['study_usd'] or b['trial_wall_s'] <= 0 or b['study_wall_s'] < b['trial_wall_s']:
            raise ValueError('RESEARCH_BUDGET_INVALID')
        if protocol['implementation'] != implementation_binding():
            raise ValueError('RESEARCH_IMPLEMENTATION_DRIFT')
        if set(protocol['checkpoints']) != set(protocol['units']):
            raise ValueError('RESEARCH_UNIT_CHECKPOINT_BINDINGS')
        for checkpoint in protocol['checkpoints'].values():
            if checkpoint is not None:
                self.verify_checkpoint(checkpoint)
        source_root = Path(__file__).resolve().parent.parent.parent
        for name, digest in protocol['implementation'].items():
            raw = checked_file(source_root, name).read_bytes()
            if sha(raw) != digest:
                raise ValueError('RESEARCH_IMPLEMENTATION_DRIFT')
            target = self.root/'blobs'/digest
            with self.locked():
                if target.exists() and target.read_bytes() != raw:
                    raise ValueError('RESEARCH_BLOB_TAMPER')
                if not target.exists():
                    write_atomic(target, raw)
        key = self.put('protocols', {**protocol, 'schema_version': SCHEMA,
            'runtime': {'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine()}})
        self.event('protocol_registered', {'protocol': key, 'paper': protocol['paper']})
        return key

    def checkpoint(self, source, files, state, *, active_jobs=(), native_state='archive-only'):
        if active_jobs:
            raise ValueError('RESEARCH_CHECKPOINT_REQUIRES_QUIESCENCE')
        if native_state not in {'none', 'archive-only', 'fresh-reimport-verified'}:
            raise ValueError('RESEARCH_NATIVE_STATE')
        required = {'product_revision', 'world_revision', 'harness_revision', 'requirements',
                    'assumptions', 'public_context', 'evidence', 'split'}
        if not required <= state.keys():
            raise ValueError('RESEARCH_CHECKPOINT_STATE_INCOMPLETE')
        entries = {}
        if len(set(files)) != len(files):
            raise ValueError('RESEARCH_DUPLICATE_FILE')
        for name in sorted(files):
            p = checked_file(source, name)
            before = p.stat()
            raw = p.read_bytes()
            after = p.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('RESEARCH_SOURCE_CHANGED')
            if len(raw) > 100_000_000:
                raise ValueError('RESEARCH_FILE_TOO_LARGE')
            digest = sha(raw)
            target = self.root/'blobs'/digest
            with self.locked():
                if target.exists() and sha(target.read_bytes()) != digest:
                    raise ValueError('RESEARCH_BLOB_TAMPER')
                if not target.exists():
                    write_atomic(target, raw)
            entries[name] = {'sha256': digest, 'bytes': len(raw)}
        # Detect changes to an earlier file while later files were being read.
        for name, entry in entries.items():
            if sha(checked_file(source, name).read_bytes()) != entry['sha256']:
                raise ValueError('RESEARCH_SOURCE_CHANGED')
        value = dict(schema_version=SCHEMA, state=state, files=entries,
                     native_state=native_state, source=str(Path(source).resolve()),
                     recovery_scope='declared artifact files and explicit public context; no live native process or opaque Pi session')
        key = self.put('checkpoints', value)
        self.event('checkpoint_frozen', {'checkpoint': key, 'files': len(entries)})
        return key

    def verify_checkpoint(self, key):
        value = self.get('checkpoints', key)
        for name, item in value['files'].items():
            relative(name)
            raw = (self.root/'blobs'/item['sha256']).read_bytes()
            if sha(raw) != item['sha256'] or len(raw) != item['bytes']:
                raise ValueError('RESEARCH_BLOB_TAMPER')
        return value

    def branch(self, protocol, checkpoint, arm, unit, repeat):
        p = self.get('protocols', protocol)
        if p['implementation'] != implementation_binding():
            raise ValueError('RESEARCH_IMPLEMENTATION_DRIFT')
        if arm not in p['arms'] or unit not in p['units'] or type(repeat) is not int or not 1 <= repeat <= p['repetitions']:
            raise ValueError('RESEARCH_UNDECLARED_CELL')
        if p.get('checkpoints', {}).get(unit) != checkpoint:
            raise ValueError('RESEARCH_UNIT_CHECKPOINT_BINDING_REQUIRED')
        cp = self.verify_checkpoint(checkpoint)
        binding = dict(protocol=protocol, checkpoint=checkpoint, arm=arm, unit=unit, repeat=repeat)
        key = identity(binding)
        path = self.root/'trials'/key
        with self.locked():
            if (path/'claim.json').exists():
                old = json.loads((path/'claim.json').read_text())
                if old['binding'] != binding:
                    raise ValueError('RESEARCH_CLAIM_CONFLICT')
                return key
            if path.exists():
                raise ValueError('RESEARCH_PARTIAL_BRANCH_RECONCILE_REQUIRED')
            path.mkdir(parents=True)
            started = time.time()
            claims = list((self.root/'trials').glob('*/claim.json'))
            study_start = min([json.loads(x.read_text())['started'] for x in claims
                               if json.loads(x.read_text())['binding']['protocol'] == protocol] or [started])
            claim = dict(schema_version=SCHEMA, binding=binding, started=started,
                         deadline=min(started+p['budget']['trial_wall_s'], study_start+p['budget']['study_wall_s']),
                         budget=p['budget'], state_hash=identity(cp['state']),
                         implementation=p['implementation'], status='CLAIMED')
            # Claim before materializing files. An interrupted attempt cannot disappear.
            write_atomic(path/'claim.json', canonical(claim).encode())
            for name, item in cp['files'].items():
                write_atomic(path/'workspace'/name, (self.root/'blobs'/item['sha256']).read_bytes())
            write_atomic(path/'public-context.json', canonical(cp['state']['public_context']).encode())
            write_atomic(path/'branch-ready.json', canonical({'claim_hash': identity(claim)}).encode())
        self.event('branch_ready', {'trial': key, **binding})
        return key

    def restore(self, checkpoint, name):
        """Fresh isolated artifact restore; native process reimport remains separate."""
        cp = self.verify_checkpoint(checkpoint)
        destination = self.root/'restores'/safe_key(name)
        with self.locked():
            if destination.exists():
                raise ValueError('RESEARCH_RESTORE_DESTINATION_EXISTS')
            destination.mkdir(parents=True)
            for file, item in cp['files'].items():
                write_atomic(destination/'workspace'/file, (self.root/'blobs'/item['sha256']).read_bytes())
            write_atomic(destination/'public-context.json', canonical(cp['state']['public_context']).encode())
            verified = {file: sha(checked_file(destination/'workspace', file).read_bytes()) == item['sha256']
                        for file, item in cp['files'].items()}
            receipt = {'checkpoint': checkpoint, 'destination': str(destination), 'files': verified,
                       'passed': all(verified.values()), 'context_hash': identity(cp['state']['public_context']),
                       'native_state': cp['native_state'], 'restored_at': time.time()}
            write_atomic(destination/'receipt.json', canonical(receipt).encode())
        self.event('artifact_restore_verified', receipt)
        return receipt

    def claim(self, trial):
        if not re.fullmatch('[a-f0-9]{64}', trial or ''):
            raise ValueError('RESEARCH_TRIAL_KEY')
        path = self.root/'trials'/trial
        c = json.loads((path/'claim.json').read_text())
        if identity(c['binding']) != trial:
            raise ValueError('RESEARCH_CLAIM_TAMPER')
        ready = json.loads((path/'branch-ready.json').read_text())
        if ready['claim_hash'] != identity(c):
            raise ValueError('RESEARCH_CLAIM_TAMPER')
        return c

    def check_trial(self, trial):
        c = self.claim(trial)
        if (self.root/'trials'/trial/'result.json').exists():
            raise ValueError('RESEARCH_TRIAL_ALREADY_FINISHED')
        if time.time() >= c['deadline']:
            raise ValueError('RESEARCH_CUMULATIVE_WALL_LIMIT')
        if c['implementation'] != implementation_binding():
            raise ValueError('RESEARCH_IMPLEMENTATION_DRIFT')
        context = json.loads((self.root/'trials'/trial/'public-context.json').read_text())
        cp = self.get('checkpoints', c['binding']['checkpoint'])
        if context != cp['state']['public_context']:
            raise ValueError('RESEARCH_CONTEXT_DRIFT')
        return c

    def finish(self, trial, status, result, *, cost_usd=0, model_calls=0):
        c = self.claim(trial)
        if status not in {'PASS', 'FAIL', 'UNKNOWN', 'BLOCKED', 'INFRA_ERROR'}:
            raise ValueError('RESEARCH_OUTCOME')
        if type(cost_usd) not in (int, float) or not math.isfinite(cost_usd) or cost_usd < 0 or type(model_calls) is not int or model_calls < 0:
            raise ValueError('RESEARCH_COST_INVALID')
        ended = time.time()
        value = dict(schema_version=SCHEMA, trial=trial, **c['binding'], started=c['started'], ended=ended,
                     wall_s=ended-c['started'], status=status, result=result,
                     cost_upper_usd=cost_usd, model_calls=model_calls, claim_hash=identity(c))
        if ended > c['deadline'] and status == 'PASS':
            value.update(status='FAIL', failure='CUMULATIVE_WALL_LIMIT')
        if cost_usd > c['budget']['trial_usd'] or model_calls > c['budget']['model_calls_per_trial']:
            value.update(status='FAIL', failure='TRIAL_BUDGET_EXCEEDED')
        with self.locked():
            path = self.root/'trials'/trial/'result.json'
            if path.exists():
                raise ValueError('RESEARCH_RESULT_ALREADY_SEALED')
            value['hash'] = identity(value)
            write_atomic(path, canonical(value).encode())
        self.event('trial_finished', {'trial': trial, 'status': value['status'], 'result_hash': value['hash']})
        return value

    def trials(self):
        rows = []
        for path in sorted((self.root/'trials').glob('*/claim.json')):
            try:
                claim = self.claim(path.parent.name)
                result = path.parent/'result.json'
                if result.exists():
                    row = json.loads(result.read_text())
                    if row['hash'] != identity({k: v for k, v in row.items() if k != 'hash'}) or row['claim_hash'] != identity(claim):
                        raise ValueError('RESEARCH_RESULT_TAMPER')
                    rows.append(row)
                else:
                    rows.append(dict(trial=path.parent.name, **claim['binding'], started=claim['started'],
                                     status='EXPIRED' if time.time() >= claim['deadline'] else 'CLAIMED',
                                     cost_upper_usd=None, model_calls=None, result={}))
            except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
                rows.append(dict(trial=path.parent.name, status='CORRUPT', error=str(exc), result={}))
        return rows

    def project(self):
        protocols = [{**self.get('protocols', p.stem), 'key': p.stem}
                     for p in sorted((self.root/'protocols').glob('*.json'))]
        reports = [{**self.get('reports', p.stem), 'key': p.stem}
                   for p in sorted((self.root/'reports').glob('*.json'))]
        inventories = [{**self.get('inventories', p.stem), 'key': p.stem}
                       for p in sorted((self.root/'inventories').glob('*.json'))]
        setup = json.loads((self.root/'setup.json').read_text()) if (self.root/'setup.json').exists() else {}
        active = {p: setup[p]['protocol'] for p in ['A', 'B', 'C'] if p in setup}
        return dict(schema_version=SCHEMA, study=self.root.name, protocols=protocols, active_protocols=active, trials=self.trials(),
                    reports=reports, inventories=inventories,
                    checkpoints=[dict(key=p.stem, files=len(self.verify_checkpoint(p.stem)['files']),
                                      state=self.get('checkpoints', p.stem)['state'],
                                      native_state=self.get('checkpoints', p.stem)['native_state'])
                                 for p in sorted((self.root/'checkpoints').glob('*.json'))],
                    event_count=len(self.journal()),
                    boundary='开发与机制先导；计算、自检、模型调用和有机现象分别记录，不代表硬件或论文确认。')

    def export(self):
        view = self.project()
        fields = ['trial', 'protocol', 'checkpoint', 'unit', 'arm', 'repeat', 'status', 'wall_s', 'cost_upper_usd', 'model_calls']
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(view['trials'])
        return dict(projection=view, trials_csv=buf.getvalue(), events=self.journal(),
                    records={k: {p.stem: self.get(k, p.stem) for p in sorted((self.root/k).glob('*.json'))}
                             for k in KINDS})
