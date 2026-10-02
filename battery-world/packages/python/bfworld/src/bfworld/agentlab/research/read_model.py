"""Bounded, isolated read model for operator research files on slow local providers."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

LIMIT_SECONDS = 8
LIMIT_BYTES = 8_000_000


def read(home, mode='project', kind='', key=''):
    command = [sys.executable, '-m', __name__, '--home', str(home), '--mode', mode]
    if mode == 'record':
        command += ['--kind', kind, '--key', key]
    env = {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': str(Path(__file__).resolve().parents[3]),
           'PYTHONDONTWRITEBYTECODE': '1'}
    try:
        completed = subprocess.run(command, capture_output=True, timeout=LIMIT_SECONDS, env=env)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('RESEARCH_READ_TIMEOUT: historical records preserved; retry after local storage recovers') from exc
    if completed.returncode:
        # Never echo a private file value or an unbounded child traceback.
        raise ValueError('RESEARCH_READ_FAILED: records preserved; local integrity/read check failed')
    if len(completed.stdout) > LIMIT_BYTES:
        raise ValueError('RESEARCH_READ_TOO_LARGE')
    return json.loads(completed.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--mode', choices=('project', 'export', 'record'), required=True)
    parser.add_argument('--kind', default='')
    parser.add_argument('--key', default='')
    args = parser.parse_args()
    from .core import Research
    model = Research(args.home)
    value = model.get(args.kind, args.key) if args.mode == 'record' else getattr(model, args.mode)()
    body = json.dumps(value, ensure_ascii=False).encode()
    if len(body) > LIMIT_BYTES:
        return 2
    sys.stdout.buffer.write(body)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
