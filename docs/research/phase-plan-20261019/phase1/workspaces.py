#!/usr/bin/env python3
"""Freeze the current S0 input and restore two lean, independent worktrees.

Only deltas from the already-preserved first baseline enter the content store.
The original source, its Git index, experimental roots and secrets are untouched.
"""
import argparse
import copy
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'workbench/bf-campaign-s0-20261019'
FIRST = ROOT / 'docs/research/parallel-campaign-20261019/baseline-v1/manifest.json'
SNAP = HERE / 'baseline-v2'
ADMIN = Path.home() / '.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/campaign.git'
RUNTIME = Path.home() / '.local/share/bf-phase1-20261020'
HEAD = '317d40fef0137d3c1ad1873e53c3e9968b31200a'
PEAK = 900_000_000
RESERVE = 10_000_000_000


def sha(path):
    p = Path(path)
    h = hashlib.sha256()
    if p.is_symlink():
        h.update(os.readlink(p).encode())
    else:
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def git(*args, cwd=None):
    command = ['git', '-c', 'core.fsmonitor=false']
    if cwd is None:
        command += ['--git-dir=' + str(ADMIN)]
    return subprocess.run(command + list(args), cwd=cwd, check=True,
                          capture_output=True, timeout=25).stdout


def clone(src, dst):
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        dst.symlink_to(os.readlink(src))
        return 'symlink'
    libc = ctypes.CDLL(None, use_errno=True)
    fn = libc.clonefile
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    fn.restype = ctypes.c_int
    if fn(os.fsencode(src), os.fsencode(dst), 0) == 0:
        method = 'independent-apfs-clone'
    else:
        if dst.exists():
            raise OSError('partial clone destination: ' + str(dst))
        if shutil.disk_usage(ROOT).free < RESERVE + src.stat().st_size:
            raise OSError('reserved fallback capacity unavailable')
        shutil.copy2(src, dst)
        method = 'reserved-full-copy'
    if src.stat().st_ino == dst.stat().st_ino or sha(src) != sha(dst):
        raise ValueError('clone readback mismatch: ' + str(dst))
    return method


def freeze():
    if SNAP.exists():
        raise FileExistsError('Baseline already frozen; verify instead.')
    free = shutil.disk_usage(ROOT).free
    if free < RESERVE + PEAK:
        raise OSError('10 GB + complete batch peak unavailable')
    assert git('rev-parse', 'HEAD', cwd=SOURCE).decode().strip() == HEAD
    raw = git('ls-files', '-c', '-o', '--exclude-standard', '-z', cwd=SOURCE)
    names = sorted(set(raw.decode().split('\0')) - {''})
    old = {e['path']: e for e in json.loads(FIRST.read_text())['entries']}
    entries, delta_bytes, methods = [], 0, {}
    SNAP.mkdir()
    for name in names:
        p = SOURCE / name
        if not p.is_file() and not p.is_symlink():
            continue
        st = p.lstat()
        if st.st_flags & 0x40000000:
            raise ValueError('Dataless source excluded from new execution: ' + name)
        e = {'path': name, 'sha256': sha(p), 'bytes': st.st_size,
             'kind': 'symlink' if p.is_symlink() else 'file',
             'executable': bool(st.st_mode & stat.S_IXUSR)}
        prior = old.get(name)
        if prior is None or any(prior.get(k) != e[k] for k in ('sha256', 'kind', 'executable')):
            blob = SNAP / 'delta' / e['sha256']
            if not blob.exists() and not blob.is_symlink():
                method = clone(p, blob)
                methods[method] = methods.get(method, 0) + 1
                delta_bytes += st.st_size
            e['delta_blob'] = e['sha256']
        entries.append(e)
    identity = hashlib.sha256(json.dumps(entries, sort_keys=True,
                            separators=(',', ':')).encode()).hexdigest()
    value = {'schema_version': 'bf-common-baseline-v2', 'id': 'CB2-' + identity,
             'head': HEAD, 'source': str(SOURCE), 'parent_manifest': str(FIRST),
             'parent_sha256': sha(FIRST), 'entries': entries,
             'source_bytes': sum(e['bytes'] for e in entries),
             'delta_bytes': delta_bytes, 'delta_copy_methods': methods,
             'deleted_from_parent': sorted(set(old) - {e['path'] for e in entries}),
             'free_bytes_before': free, 'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'git_commit_created': False, 'full_tree_backup_created': False,
             'original_source_and_index_modified': False}
    save(SNAP / 'manifest.json', value)
    return value


def profile(role, target, baseline):
    original = json.loads((Path.home() / '.local/share/bf-campaign-20261019-s0/profile.json').read_text())
    p = copy.deepcopy(original)
    runtime = RUNTIME / role
    home = runtime / 'workbench'
    p.update(id='bf-phase1-20261020-' + role, source_root=str(target),
             runtime_root=str(runtime), home=str(home), pi_root=str(target / 'pi-bf-aiot'),
             port=8981 if role == 'a' else 8982,
             branch='codex/phase1-' + role + '-20261020',
             stage='phase-one preparation; paid and native capabilities disabled',
             configuration=str(runtime / 'runtime.json'),
             baseline={'path': str(SNAP), 'manifest_sha256': sha(SNAP / 'manifest.json')},
             capabilities={'model': False, 'native': False, 'agent': False})
    p['paths'].update(HOME=str(home), PI_ROOT=p['pi_root'],
                      PROVIDER_KEY_FILE=str(home / 'secrets/deepseek.key'),
                      EDA_LOCAL_PROJECT_ROOT=str(runtime / 'native-projects'))
    save(runtime / 'profile.json', p)
    ref = {'path': str(runtime / 'profile.json'), 'sha256': sha(runtime / 'profile.json')}
    save(runtime / 'runtime.json', {'schema_version': 'bf-runtime-layout-v1',
                                  'paths': p['paths'], 'eda': p['eda'], 'development_profile': ref})
    marker = target / '.bf-development-profile.json'
    marker.unlink(missing_ok=True)
    save(marker, ref)
    marker.chmod(0o644)
    return ref


def materialize(m):
    reports = []
    for role, fid in [('a', 'BFA-052-ar-service-repair'), ('b', 'BFA-053-bf-interface-protocol')]:
        target = ROOT / ('workbench/bf-campaign-' + role + '-20261019')
        existing = target.exists()
        if existing:
            if git('rev-parse', 'HEAD', cwd=target).decode().strip() != HEAD:
                raise ValueError('Existing workspace has another identity')
            if git('branch', '--show-current', cwd=target).decode().strip() != 'codex/phase1-' + role + '-20261020':
                raise ValueError('Existing workspace belongs to another branch')
        else:
            git('worktree', 'add', '--no-checkout', '-b', 'codex/phase1-' + role + '-20261020', str(target), HEAD)
        methods = {}
        for e in m['entries']:
            src, dst = SOURCE / e['path'], target / e['path']
            if sha(src) != e['sha256']:
                raise ValueError('Source drift during materialization: ' + e['path'])
            if existing:
                if e['path'] == 'battery-world/PROJECT.yaml':
                    text = dst.read_text().replace('active_feature: ' + fid, 'active_feature: BFA-051-bf-phase1-integration', 1)
                    if hashlib.sha256(text.encode()).hexdigest() != e['sha256']:
                        raise ValueError('Existing role overlay drift')
                elif sha(dst) != e['sha256']:
                    raise ValueError('Existing partial workspace drift: ' + e['path'])
                method = 'existing-verified'
            else:
                method = clone(src, dst)
            methods[method] = methods.get(method, 0) + 1
            if not dst.is_symlink():
                dst.chmod(0o555 if e['executable'] else 0o444)
        git('read-tree', HEAD, cwd=target)
        p = target / 'battery-world/PROJECT.yaml'
        text = p.read_text().replace('active_feature: BFA-051-bf-phase1-integration', 'active_feature: ' + fid, 1)
        p.chmod(0o644)
        p.write_text(text)
        ref = profile(role, target, m)
        reports.append({'role': role, 'workspace': str(target), 'baseline': m['id'],
                        'files': len(m['entries']), 'copy_methods': methods,
                        'profile': ref, 'capabilities': 'all disabled until a separately leased episode',
                        'role_overlays': ['battery-world/PROJECT.yaml', '.bf-development-profile.json'],
                        'status': 'PASS'})
    save(SNAP / 'workspaces.json', {'workspaces': reports, 'free_bytes_after': shutil.disk_usage(ROOT).free})
    return reports


def verify(m):
    result = []
    for role in ('a', 'b'):
        target = ROOT / ('workbench/bf-campaign-' + role + '-20261019')
        failures = [e['path'] for e in m['entries']
                    if e['path'] not in ('battery-world/PROJECT.yaml', '.bf-development-profile.json')
                    and sha(target / e['path']) != e['sha256']]
        if failures:
            raise ValueError('Common baseline drift: ' + str(failures[:5]))
        result.append({'role': role, 'status': 'PASS', 'common_files': sum(e['path'] not in ('battery-world/PROJECT.yaml', '.bf-development-profile.json') for e in m['entries'])})
    save(SNAP / 'readback.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'verify'])
    action = parser.parse_args().action
    if action == 'prepare':
        m = json.loads((SNAP / 'manifest.json').read_text()) if (SNAP / 'manifest.json').exists() else freeze()
        materialize(m)
    else:
        m = json.loads((SNAP / 'manifest.json').read_text())
    result = verify(m)
    print(json.dumps({'id': m['id'], 'files': len(m['entries']), 'delta_bytes': m['delta_bytes'],
                      'readback': result, 'available_bytes': shutil.disk_usage(ROOT).free}, ensure_ascii=False))
