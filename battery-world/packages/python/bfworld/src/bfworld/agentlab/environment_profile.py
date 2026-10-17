"""Explicit operator configuration for an isolated development worktree."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

SCHEMA = 'bf-development-profile-v1'
MANDATORY = ('RUNTIME_ROOT', 'RUNTIME_CONFIG', 'HOME', 'PI_ROOT')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def real(path):
    p = Path(path).expanduser().absolute()
    if p != p.resolve():
        raise ValueError('DEVELOPMENT_PATH_SYMLINK:' + str(p))
    return p


def validate(reference, configuration, environ, source_root):
    path = real(reference['path'])
    if sha256(path) != reference['sha256']:
        raise ValueError('DEVELOPMENT_PROFILE_CHANGED')
    value = json.loads(path.read_text())
    if value.get('schema_version') != SCHEMA or value.get('kind') != 'Architecture V2':
        raise ValueError('DEVELOPMENT_PROFILE_SCHEMA')
    source, runtime, home = map(real, [value['source_root'], value['runtime_root'], value['home']])
    if source != real(source_root):
        raise ValueError('DEVELOPMENT_SOURCE_MISMATCH')
    if not home.is_relative_to(runtime) or home == runtime:
        raise ValueError('DEVELOPMENT_HOME_SCOPE')
    if not real(value['pi_root']).is_relative_to(source):
        raise ValueError('DEVELOPMENT_PI_SCOPE')
    protected = [real(p) for p in value['protected_roots']]
    for root in [source, runtime, home]:
        if any(root.is_relative_to(p) or p.is_relative_to(root) for p in protected):
            raise ValueError('DEVELOPMENT_PRODUCTION_COLLISION')
    expected = {'RUNTIME_ROOT': str(runtime), 'RUNTIME_CONFIG': value['configuration'],
                'HOME': str(home), 'PI_ROOT': value['pi_root']}
    for name in MANDATORY:
        supplied = environ.get('BF_' + name)
        if not supplied:
            raise ValueError('DEVELOPMENT_EXPLICIT_PATH_REQUIRED:' + name)
        if real(supplied) != real(expected[name]):
            raise ValueError('DEVELOPMENT_PATH_MISMATCH:' + name)
    if not environ.get('PI_CODING_AGENT_DIR') or real(environ['PI_CODING_AGENT_DIR']) != home/'pi-config':
        raise ValueError('DEVELOPMENT_PI_STATE_SCOPE')
    if environ.get('BF_DEVELOPMENT_PROFILE') != str(path):
        raise ValueError('DEVELOPMENT_PROFILE_REQUIRED')
    if configuration.get('paths') != value['paths']:
        raise ValueError('DEVELOPMENT_CONFIGURATION_CHANGED')
    if configuration.get('eda') != value['eda'] or set(configuration) != {'schema_version', 'paths', 'eda', 'development_profile'}:
        raise ValueError('DEVELOPMENT_CONFIGURATION_CHANGED')
    for name, pinned in value['paths'].items():
        if environ.get('BF_' + name) and Path(environ['BF_' + name]).expanduser().absolute() != Path(pinned).absolute():
            raise ValueError('DEVELOPMENT_OVERRIDE_CHANGED:' + name)
    if value.get('port') == value.get('production_port') or not 1024 <= value['port'] <= 65535:
        raise ValueError('DEVELOPMENT_PORT_COLLISION')
    if real(value['paths']['EDA_LOCAL_PROJECT_ROOT']) != runtime/'native-projects':
        raise ValueError('DEVELOPMENT_NATIVE_PROJECT_SCOPE')
    if real(value['paths']['PROVIDER_KEY_FILE']) != home/'secrets/deepseek.key':
        raise ValueError('DEVELOPMENT_CREDENTIAL_SCOPE')
    if real(value['paths']['NATIVE_LOCK']) != real(value['shared_native_lock']):
        raise ValueError('DEVELOPMENT_SHARED_LOCK_REQUIRED')
    if set(value.get('native_project_uuids', [])) & set(value.get('protected_native_project_uuids', [])):
        raise ValueError('DEVELOPMENT_ORIGINAL_NATIVE_PROJECT_REJECTED')
    baseline = real(value['baseline']['path'])
    if sha256(baseline/'manifest.json') != value['baseline']['manifest_sha256']:
        raise ValueError('DEVELOPMENT_BASELINE_CHANGED')
    if not isinstance(value.get('capabilities'), dict) or set(value['capabilities']) != {'model', 'native', 'agent'}:
        raise ValueError('DEVELOPMENT_CAPABILITIES_INVALID')
    if any(type(flag) is not bool for flag in value['capabilities'].values()):
        raise ValueError('DEVELOPMENT_CAPABILITIES_INVALID')
    return {**value, 'path': str(path), 'sha256': reference['sha256']}


def workbench_root(profile, root):
    if profile is None:
        return
    root = real(root)
    if root != real(profile['home'])/'state':
        raise ValueError('DEVELOPMENT_STATE_ROOT_MISMATCH')
    marker = root/'development-runtime.json'
    db_path = root/'workbench.sqlite'
    if marker.is_symlink() or db_path.is_symlink():
        raise ValueError('DEVELOPMENT_DATABASE_SYMLINK')
    if db_path.exists() and not marker.is_file():
        raise ValueError('DEVELOPMENT_HISTORICAL_DATABASE_REJECTED')
    if marker.is_file():
        identity = json.loads(marker.read_text())
        if identity.get('profile_id') != profile['id'] or identity.get('baseline') != profile['baseline']:
            raise ValueError('DEVELOPMENT_RUNTIME_IDENTITY_MISMATCH')
    if db_path.is_file():
        db = sqlite3.connect(db_path.as_uri()+'?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='conversations'").fetchone():
                owners = profile['protected_owners']
                if db.execute('SELECT 1 FROM conversations WHERE id IN (' + ','.join('?' for _ in owners) + ')', owners).fetchone():
                    raise ValueError('DEVELOPMENT_ORIGINAL_OWNER_REJECTED')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='model_requests'").fetchone():
                owners = profile['protected_owners']
                if db.execute('SELECT 1 FROM model_requests WHERE owner IN (' + ','.join('?' for _ in owners) + ')', owners).fetchone():
                    raise ValueError('DEVELOPMENT_ORIGINAL_LEDGER_REJECTED')
        finally:
            db.close()
    if not marker.exists():
        root.mkdir(parents=True, exist_ok=True)
        identity = {'schema_version': 'bf-development-runtime-identity-v1', 'instance_id': str(uuid.uuid4()),
                    'profile_id': profile['id'], 'baseline': profile['baseline'], 'historical_database_imported': False}
        with marker.open('x') as f:
            json.dump(identity, f, ensure_ascii=False, indent=2)
            f.write('\n')
        marker.chmod(0o600)


def require(profile, capability):
    if profile is not None and not profile['capabilities'][capability]:
        raise PermissionError('DEVELOPMENT_CAPABILITY_DISABLED:' + capability)


def project(profile, project_uuid):
    if profile is None:
        return
    require(profile, 'native')
    if project_uuid not in profile.get('native_project_uuids', []):
        raise PermissionError('DEVELOPMENT_NATIVE_PROJECT_NOT_QUALIFIED')
