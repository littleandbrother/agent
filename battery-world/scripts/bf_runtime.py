#!/usr/bin/env python3
"""One resident entry for service, scoped checks and release verification."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'packages/python/bfworld/src'))
from bfworld.agentlab import runtime_config as config


def environment():
    env = os.environ.copy()
    env['PYTHONPATH'] = str(REPO / 'packages/python/bfworld/src')
    for name in ('HOME', 'PI_ROOT', 'CAD_PYTHON', 'DOOR_SELFPOWER_ROOT'):
        if name in config._CONFIG.get('paths', {}):
            env.setdefault('BF_' + name, str(config.configured(name, '')))
    env['BFWORLD_PYTHON'] = str(config.CAD)
    return env


def doctor():
    paths = config.public_paths()
    paths['launcher_python'] = {'path': str(Path(sys.executable).resolve()), 'exists': True}
    paths['execution_python'] = {'path': str(config.CAD), 'exists': config.CAD.is_file()}
    paths['database'] = {'path': str(config.HOME_ROOT / 'state/workbench.sqlite'),
                         'exists': (config.HOME_ROOT / 'state/workbench.sqlite').is_file()}
    required = ['home', 'pi', 'node', 'cad', 'database']
    resident = all('/Documents/' not in str(Path(paths[k]['path']).resolve()) for k in required)
    return {'schema_version': 'bf-runtime-doctor-v1', 'config': str(config.CONFIG_PATH),
            'paths': paths, 'resident_required_paths': resident,
            'ready': resident and all(paths[k]['exists'] for k in required)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    service = sub.add_parser('serve'); service.add_argument('--port', type=int, default=8768)
    tests = sub.add_parser('test'); tests.add_argument('--pattern', default='test_runtime_efficiency.py')
    sub.add_parser('verify-release')
    a = p.parse_args()
    if a.command == 'doctor':
        result = doctor(); print(json.dumps(result, indent=2)); return 0 if result['ready'] else 1
    python = str(config.CAD)
    if a.command == 'serve':
        argv = [python, '-u', '-m', 'bfworld.agentlab.server', '--root',
                str(config.HOME_ROOT / 'state'), '--port', str(a.port)]
    elif a.command == 'test':
        argv = [python, '-m', 'unittest', 'discover', '-s', 'tests/agentlab', '-p', a.pattern, '-v']
    else:
        argv = ['bash', str(REPO / 'init.sh')]
    return subprocess.call(argv, env=environment(), cwd=REPO)


if __name__ == '__main__':
    raise SystemExit(main())
