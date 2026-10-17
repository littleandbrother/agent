#!/usr/bin/env python3
"""Freeze a baseline and operate an explicitly isolated Architecture V2 runtime."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

APP = Path(__file__).resolve().parents[1]
SOURCE = APP.parent
sys.path.insert(0, str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.baseline import digest, freeze, verify


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
    return path


def setup(baseline, runtime, port):
    baseline, runtime = Path(baseline).resolve(), Path(runtime).absolute()
    if runtime.exists() or runtime != runtime.resolve():
        raise ValueError('DEVELOPMENT_NEW_RUNTIME_REQUIRED')
    check = verify(baseline)
    value = json.loads((baseline/'manifest.json').read_text())
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=SOURCE, text=True).strip()
    if branch != 'codex/bf-architecture-v2':
        raise ValueError('DEVELOPMENT_BRANCH_REQUIRED')
    runtime.mkdir(parents=True, mode=0o700)
    home = runtime/'workbench'
    home.mkdir(mode=0o700)
    configuration = runtime/'runtime.json'
    old = json.loads((baseline/'operator/runtime.json').read_text())
    paths = {k: v for k, v in old['paths'].items() if k not in
             {'HOME', 'PI_ROOT', 'DOOR_SELFPOWER_ROOT', 'EDA_NATIVE_PROVIDER', 'EDA_LOCAL_PROJECT_ROOT',
              'RECEIVER_PYTHON_ROOT', 'RECEIVER_ROOT', 'PROVIDER_KEY_FILE'}}
    shared = Path(value['production']['runtime'])
    paths.update({'HOME': str(home), 'PI_ROOT': str(SOURCE/'pi-bf-aiot'),
                  'PROVIDER_KEY_FILE': str(home/'secrets/deepseek.key'),
                  'EDA_LOCAL_PROJECT_ROOT': str(runtime/'native-projects'),
                  'DOOR_SELFPOWER_ROOT': str(runtime/'reference-cases/door-selfpower-v1'),
                  'EDA_NATIVE_PROVIDER': str(runtime/'deployment/easyeda-native/provider.json'),
                  'NATIVE_LOCK': str(shared/'design-native.lock'),
                  'EDA_PROTOCOL_ROOT': str(Path.home()/'Documents/easyeda-agent'),
                  'NODE': shutil.which('node'), 'NGSPICE': shutil.which('ngspice'),
                  'ARM_GCC': shutil.which('arm-none-eabi-gcc') or '/opt/ST/STM32CubeCLT_1.19.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc',
                  'BLENDER': '/Applications/Blender.app/Contents/MacOS/Blender',
                  'COMSOL': '/Applications/COMSOL62/Multiphysics/bin/comsol',
                  'NGSPICE_SHARED': '/opt/homebrew/Cellar/libngspice/46/lib/libngspice.0.dylib',
                  'RENODE': str(shared/'toolchains/renode-1.17.0-arm64/Renode.app/Contents/MacOS/renode'),
                  'GO': str(shared/'toolchains/go1.27.2/go/bin/go')})
    if any(v is None for v in paths.values()):
        raise ValueError('DEVELOPMENT_TOOL_PATH_MISSING')
    connector = next(p for p in (baseline/'environment').iterdir() if p.suffix == '.eext')
    eda = {**old['eda'], 'connector_package': {'path': str(connector), 'sha256': digest(connector)}}
    profile = {'schema_version': 'bf-development-profile-v1', 'kind': 'Architecture V2',
               'id': 'architecture-v2-20261014', 'stage': 'A/B', 'source_root': str(SOURCE),
               'branch': branch, 'base_commit': value['source']['commit'],
               'runtime_root': str(runtime), 'home': str(home), 'configuration': str(configuration),
               'pi_root': str(SOURCE/'pi-bf-aiot'), 'paths': paths, 'eda': eda, 'port': port, 'production_port': 8768,
               'baseline': {'path': str(baseline), 'manifest_sha256': check['manifest_sha256']},
               'protected_roots': [value['source']['worktree'], value['production']['runtime'],
                                   value['production']['native_project'], str(baseline)],
               'protected_owners': value['original_owners']+['pi-chat-8ae12ef0354d33bb'],
               'shared_native_lock': paths['NATIVE_LOCK'], 'native_project_uuids': [],
               'protected_native_project_uuids': [value['p01']['native_project_uuid']],
               'capabilities': {'model': False, 'native': False, 'agent': False}}
    profile_path = write(runtime/'profile.json', profile)
    reference = {'path': str(profile_path), 'sha256': digest(profile_path)}
    write(configuration, {'schema_version': 'bf-runtime-layout-v1', 'paths': paths, 'eda': eda,
                          'development_profile': reference})
    write(SOURCE/'.bf-development-profile.json', reference)
    for p in [profile_path, configuration, SOURCE/'.bf-development-profile.json']:
        p.chmod(0o400)
    # Publish only frozen public inputs, not the historical database or internal traces.
    public = runtime/'inputs/P01'
    public.mkdir(parents=True)
    snapshots = list((baseline/'private/design-lab'/value['p01']['owner']/'designs').rglob('design.json'))
    snapshot = None
    for path in snapshots:
        candidate = json.loads(path.read_text())
        if candidate.get('design_id') == value['p01']['submitted_design']:
            snapshot = candidate
            break
    if snapshot is None:
        # DB is read-only here; it is never attached to a Workbench.
        from bfworld.agentlab.baseline import readonly
        with readonly(baseline/'private/databases/papers.sqlite') as db:
            snapshot = json.loads(db.execute('SELECT value FROM design_snapshots WHERE owner=? AND design_id=?',
                (value['p01']['owner'], value['p01']['submitted_design'])).fetchone()[0])
    files = {}
    for relative, ref in snapshot['files'].items():
        src = baseline/'p01/participant'/relative
        dst = public/relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        dst.chmod(0o400)
        if digest(dst) != ref['sha256']:
            raise ValueError('DEVELOPMENT_PUBLIC_INPUT_CHANGED')
        files[relative] = {'sha256': ref['sha256'], 'bytes': dst.stat().st_size}
    inputs = write(public/'INPUTS.json', {'schema_version': 'bf-public-baseline-inputs-v1',
            'baseline': profile['baseline'], 'source_owner': value['p01']['owner'],
            'source_design': value['p01']['submitted_design'], 'files': files,
            'new_design_history': [], 'adopted_as_passed_product': False})
    inputs.chmod(0o400)
    for p in sorted([p for p in public.rglob('*') if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        p.chmod(0o500)
    public.chmod(0o500)
    native = runtime/'native-projects/P01-B0-copy'
    shutil.copytree(baseline/'p01/native-project', native)
    # The source UUID is preserved as archival data; live access remains disabled
    # until an independently identified native copy is qualified in C.
    for p in native.rglob('*'):
        p.chmod(0o700 if p.is_dir() else 0o600)
    native.chmod(0o700)
    write(runtime/'native-projects/COPY-IDENTITY.json', {'schema_version': 'bf-native-development-copy-v1',
        'source_project_uuid': value['p01']['native_project_uuid'], 'copy_path': str(native),
        'live_project_uuid': None, 'state': 'ARCHIVAL_COPY_NOT_OPENED',
        'baseline': profile['baseline'], 'original_project_mutable_access': False})
    pin = {}
    for name in ['CAD_PYTHON', 'NODE', 'NGSPICE', 'ARM_GCC', 'EDA_CLI', 'EDA_NATIVE_CLI', 'RENODE', 'BLENDER', 'COMSOL', 'GO']:
        path = Path(paths[name])
        pin[name] = {'path': str(path), 'resolved': str(path.resolve()), 'exists': path.is_file(),
                     'sha256': digest(path) if path.is_file() else None}
    write(runtime/'tool-pins.json', {'schema_version': 'bf-development-tool-pins-v1',
          'baseline': profile['baseline'], 'tools': pin, 'policy': 'shared installed assets; no installation or rebuild'})
    write(runtime/'setup.json', {'schema_version': 'bf-development-setup-v1', 'profile': reference,
          'configuration_sha256': digest(configuration), 'public_input_count': len(files),
          'native_copy_files': sum(p.is_file() for p in native.rglob('*')), 'historical_database_imported': False,
          'new_model_requests': 0, 'new_solver_jobs': 0})
    return {'runtime': str(runtime), 'port': port, 'public_input_count': len(files), 'baseline': profile['baseline']}


def environment(runtime):
    runtime = Path(runtime).resolve()
    p = json.loads((runtime/'profile.json').read_text())
    env = {k: v for k, v in os.environ.items() if not k.startswith('BF_')}
    env.update({'BF_RUNTIME_ROOT': str(runtime), 'BF_RUNTIME_CONFIG': str(runtime/'runtime.json'),
                'BF_HOME': p['home'], 'BF_PI_ROOT': p['pi_root'], 'BF_DEVELOPMENT_PROFILE': str(runtime/'profile.json'),
                'PI_CODING_AGENT_DIR': str(Path(p['home'])/'pi-config'),
                'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(SOURCE/'battery-world/packages/python/bfworld/src')})
    return p, env


def launch(runtime, background=False):
    p, env = environment(runtime)
    script = SOURCE/'battery-world'
    python = p['paths']['CAD_PYTHON']
    root = Path(p['home'])/'state'
    command = [python, '-m', 'bfworld.agentlab.server', '--root', str(root), '--port', str(p['port'])]
    if background:
        with (Path(runtime)/'server.log').open('ab') as log:
            child = subprocess.Popen(command, cwd=script, env=env, stdout=log, stderr=log,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
        return {'pid': child.pid, 'port': p['port'], 'log': str(Path(runtime)/'server.log')}
    subprocess.run(command, cwd=script, env=env, check=True)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    f = commands.add_parser('freeze-baseline')
    for name in ['source', 'runtime', 'campaign', 'native-project', 'target', 'tag']:
        f.add_argument('--'+name, required=True)
    v = commands.add_parser('verify-baseline')
    v.add_argument('--baseline', required=True)
    v.add_argument('--origins', action='store_true')
    s = commands.add_parser('setup')
    s.add_argument('--baseline', required=True)
    s.add_argument('--runtime', required=True)
    s.add_argument('--port', type=int, default=8870)
    l = commands.add_parser('launch')
    l.add_argument('--runtime', required=True)
    l.add_argument('--background', action='store_true')
    e = commands.add_parser('identity')
    e.add_argument('--runtime', required=True)
    args = parser.parse_args()
    if args.command == 'freeze-baseline':
        result = freeze(args.source, args.runtime, args.campaign, args.native_project, args.target, args.tag)
    elif args.command == 'verify-baseline':
        result = verify(args.baseline, args.origins)
    elif args.command == 'setup':
        result = setup(args.baseline, args.runtime, args.port)
    elif args.command == 'launch':
        result = launch(args.runtime, args.background)
        if result is None:
            return
    else:
        result, env = environment(args.runtime)
        result = {k: result[k] for k in ['id', 'kind', 'stage', 'branch', 'base_commit', 'source_root', 'runtime_root', 'home', 'pi_root', 'port', 'baseline', 'capabilities']}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
