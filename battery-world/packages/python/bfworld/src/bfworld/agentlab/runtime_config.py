"""Process-level paths. Environment overrides are operator configuration, not tools.

No credentials or participant state are read when this module is imported.
"""
import os
import json
from pathlib import Path
import shutil
import hashlib
import re

REPO = Path(__file__).resolve().parents[6]


RUNTIME_ROOT = Path(os.environ.get('BF_RUNTIME_ROOT', str(Path.home() / '.local/share/bf-agent-runtime'))).expanduser().absolute()
CONFIG_PATH = Path(os.environ.get('BF_RUNTIME_CONFIG', str(RUNTIME_ROOT / 'runtime.json'))).expanduser()
# A single local operator file applies to service, CLI, tests and child solvers.
# Explicit BF_* environment overrides retain precedence for isolated tests.
_CONFIG = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.is_file() else {}
if _CONFIG and _CONFIG.get('schema_version') != 'bf-runtime-layout-v1':
    raise ValueError('RUNTIME_CONFIG_SCHEMA_INVALID')


def configured(name, default):
    value = os.environ.get('BF_' + name) or _CONFIG.get('paths', {}).get(name)
    return Path(value).expanduser().absolute() if value else Path(default).expanduser().absolute()


def eda_policy():
    """Operator-owned host policy. No participant can relax or replace it."""
    value = dict(_CONFIG.get('eda', {}))
    host = os.environ.get('BF_EDA_HOST') or value.get('host', 'any')
    modes = value.get('modes', [])
    wait_s = value.get('wait_s', 30)
    transport = value.get('transport', 'easyeda-typed-v1')
    if transport not in ('easyeda-typed-v1', 'native-cli-v1'):
        raise ValueError('EDA_TRANSPORT_POLICY_INVALID')
    if host not in ('any', 'desktop', 'web') or not isinstance(modes, list) or any(
            mode not in ('online', 'half-offline', 'offline') for mode in modes):
        raise ValueError('EDA_HOST_POLICY_INVALID')
    if type(wait_s) not in (int, float) or not 0 <= wait_s <= 60:
        raise ValueError('EDA_STARTUP_WAIT_INVALID')
    policy = {'schema_version': 'bf-eda-host-policy-v1', 'transport': transport,
              'host': host, 'modes': modes, 'wait_s': wait_s}
    version = value.get('connector_version')
    if version is not None:
        if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_-]{0,100}', version):
            raise ValueError('EDA_CONNECTOR_VERSION_POLICY_INVALID')
        policy['connector_version'] = version
    package = value.get('connector_package')
    if package is not None:
        if not version or not isinstance(package, dict) or set(package) != {'path', 'sha256'}:
            raise ValueError('EDA_CONNECTOR_PACKAGE_POLICY_INVALID')
        name, expected = package['path'], package['sha256']
        if not isinstance(name, str) or not Path(name).is_absolute() or not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError('EDA_CONNECTOR_PACKAGE_POLICY_INVALID')
        path = Path(name)
        if path.is_symlink() or not path.is_file() or path.resolve() != path or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('EDA_CONNECTOR_PACKAGE_CHANGED')
        policy['connector_package'] = dict(package)
    return policy


HOME_ROOT = configured('HOME', RUNTIME_ROOT / 'workbench')
PI = configured('PI_ROOT', RUNTIME_ROOT / 'pi-bf-aiot')
NODE = configured('NODE', shutil.which('node') or '/opt/homebrew/bin/node')
KEY_PATH = configured('PROVIDER_KEY_FILE', HOME_ROOT / 'secrets/deepseek.key')
CAD = configured('CAD_PYTHON', RUNTIME_ROOT / 'product-cad/bin/python')
BLENDER = configured('BLENDER', '/Applications/Blender.app/Contents/MacOS/Blender')
COMSOL = configured('COMSOL', '/Applications/COMSOL62/Multiphysics/bin/comsol')
SPICE = configured('NGSPICE', shutil.which('ngspice') or '/opt/homebrew/bin/ngspice')
SPICE_SHARED = configured('NGSPICE_SHARED', '/opt/homebrew/Cellar/libngspice/46/lib/libngspice.0.dylib')
RENODE = configured('RENODE', RUNTIME_ROOT / 'toolchains/renode-1.17.0-arm64/Renode.app/Contents/MacOS/renode')
GCC = configured('ARM_GCC', shutil.which('arm-none-eabi-gcc') or '/opt/ST/STM32CubeCLT_1.19.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc')
CMSIS = configured('CMSIS', HOME_ROOT / 'toolchains/stm32l031')
EDA_PROTOCOL_ROOT = configured('EDA_PROTOCOL_ROOT', Path.home()/'Documents/easyeda-agent')
GO = configured('GO', RUNTIME_ROOT/'toolchains/go1.27.2/go/bin/go')

# A configured V2 worktree cannot silently attach to the default production home.
# Clean baseline/integration checkouts retain the original default behavior.
_SOURCE_PROFILE = REPO.parent / '.bf-development-profile.json'
DEVELOPMENT_PROFILE = None
if _SOURCE_PROFILE.exists() or _CONFIG.get('development_profile') or os.environ.get('BF_DEVELOPMENT_PROFILE'):
    from .environment_profile import validate
    reference = _CONFIG.get('development_profile')
    if not isinstance(reference, dict):
        raise ValueError('DEVELOPMENT_CONFIGURATION_REQUIRED')
    if _SOURCE_PROFILE.is_file() and json.loads(_SOURCE_PROFILE.read_text()) != reference:
        raise ValueError('DEVELOPMENT_WORKTREE_PROFILE_MISMATCH')
    DEVELOPMENT_PROFILE = validate(reference, _CONFIG, os.environ, REPO.parent)


def require_capability(name):
    from .environment_profile import require
    require(DEVELOPMENT_PROFILE, name)


def validate_workbench_root(root):
    from .environment_profile import workbench_root
    workbench_root(DEVELOPMENT_PROFILE, root)


def validate_native_project(project_uuid):
    from .environment_profile import project
    project(DEVELOPMENT_PROFILE, project_uuid)


def public_paths():
    """Operator diagnostics omit secret paths and values."""
    return {k: {'path': str(v), 'exists': v.exists()} for k, v in
            [('home', HOME_ROOT), ('pi', PI), ('node', NODE), ('cad', CAD),
             ('blender', BLENDER), ('comsol', COMSOL), ('ngspice', SPICE),
             ('ngspice_shared', SPICE_SHARED), ('renode', RENODE),
             ('arm_gcc', GCC), ('cmsis', CMSIS)]}


def readonly_tree_hash(root, allowed_roots):
    """Pin runtime contents, including bytecode and resolved executable links."""
    root=Path(root)
    if root.is_symlink() or root.absolute()!=root.resolve() or not root.is_dir():
        raise ValueError('READONLY_RUNTIME_ROOT_INVALID')
    entries=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            target=path.resolve()
            # Bundled Python contains dangling build-time man/pkgconfig links.
            # Pin the link itself. It grants no resolved target access; if an
            # external target later exists qualification must reject it.
            if target.exists() and not any(target.is_relative_to(p) for p in allowed_roots):
                raise ValueError('READONLY_RUNTIME_LINK_ESCAPE')
            entries.append([str(path.relative_to(root)), 'link', os.readlink(path)])
        if path.is_file():
            entries.append([str(path.relative_to(root)), 'file',
                            hashlib.sha256(path.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(entries,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def validate_readonly_runtime(reference, receiver_root, python_root, verify_contents=True):
    """Operator configuration grants two exact public trees, never a home."""
    path=Path(reference['path']).absolute()
    if path.is_symlink() or path!=path.resolve():
        raise ValueError('READONLY_RUNTIME_MANIFEST_SYMLINK')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('READONLY_RUNTIME_MANIFEST_CHANGED')
    value=json.loads(raw)
    workspace=Path(value['workspace']).absolute()
    owner=value['owner']
    if (value.get('schema_version')!='bf-participant-readonly-runtime-v1' or
        value.get('purpose')!='receiver-software' or not owner.startswith('pi-chat-') or
        workspace.name!=owner or workspace.parent.name!='participants' or
        workspace.is_symlink() or workspace!=workspace.resolve() or
        path.is_relative_to(workspace)):
        raise ValueError('READONLY_RUNTIME_OWNER_SCOPE')
    expected=[Path(receiver_root).absolute(),Path(python_root).absolute()]
    roots=[Path(p['path']).absolute() for p in value['roots']]
    if roots!=expected or any(workspace.is_relative_to(p) or p.is_relative_to(workspace) for p in roots):
        raise ValueError('READONLY_RUNTIME_ROOT_SCOPE')
    if verify_contents:
        for item,root in zip(value['roots'],roots):
            if readonly_tree_hash(root,roots)!=item['tree_sha256']:
                raise ValueError('READONLY_RUNTIME_CONTENT_CHANGED')
    interpreter=Path(value['interpreter']).absolute()
    if (not interpreter.is_relative_to(roots[0]) or not interpreter.is_file() or
        not interpreter.resolve().is_relative_to(roots[1])):
        raise ValueError('READONLY_RUNTIME_INTERPRETER_SCOPE')
    evidence=value['qualification'];receipt=Path(evidence['path'])
    if receipt.is_symlink() or hashlib.sha256(receipt.read_bytes()).hexdigest()!=evidence['sha256']:
        raise ValueError('READONLY_RUNTIME_QUALIFICATION_CHANGED')
    if json.loads(receipt.read_text()).get('status')!='PASS':
        raise ValueError('READONLY_RUNTIME_QUALIFICATION_REQUIRED')
    return {**value,'manifest_path':str(path),'manifest_sha256':reference['sha256']}


def readonly_runtime(workspace=None, verify_contents=True):
    """No participant parameter or ancestry can opt into this capability."""
    reference=_CONFIG.get('participant_readonly_runtime')
    if reference is None:return None
    receiver_root=configured('RECEIVER_ROOT',RUNTIME_ROOT/'receiver-runtime-20261013')
    python_root=configured('RECEIVER_PYTHON_ROOT',Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python')
    if (receiver_root.parent!=RUNTIME_ROOT or not re.fullmatch(r'receiver-runtime-\d{8}',receiver_root.name) or
        python_root.name!='python' or python_root.parent.name!='dependencies' or
        not python_root.is_relative_to(Path.home()/'.cache/codex-runtimes')):
        raise ValueError('READONLY_RUNTIME_PUBLIC_ROOT_REQUIRED')
    value=validate_readonly_runtime(reference,receiver_root,python_root,verify_contents=False)
    if workspace is not None:
        supplied=Path(workspace).absolute()
        if supplied.is_symlink() or supplied!=supplied.resolve():
            raise ValueError('READONLY_RUNTIME_WORKSPACE_SYMLINK')
        if str(supplied)!=value['workspace']:return None
    if verify_contents:
        value=validate_readonly_runtime(reference,receiver_root,python_root)
    return value
