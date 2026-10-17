#!/usr/bin/env python3
"""Run task-profile tests in the configured isolated V2 environment."""
import argparse
from pathlib import Path
import subprocess

from bf_v2_environment import APP, environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=Path.home()/'.local/share/bf-agent-architecture-v2')
    parser.add_argument('--pattern', default='test_repository_task_profiles.py')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    profile, env = environment(args.runtime)
    env['PYTHONPATH'] += ':' + str(APP/'tests/agentlab')
    cmd = [profile['paths']['CAD_PYTHON'], '-m', 'unittest', 'discover', '-s', 'tests/agentlab', '-p', args.pattern, '-v']
    result = subprocess.run(cmd, cwd=APP, env=env, capture_output=True, text=True)
    log = result.stdout + result.stderr
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(log)
    print(log)
    raise SystemExit(result.returncode)


if __name__ == '__main__': main()
