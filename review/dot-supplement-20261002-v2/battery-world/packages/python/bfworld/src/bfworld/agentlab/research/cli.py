import argparse
import json
from pathlib import Path

from .core import Research, write_atomic
from ..store import canonical


def main():
    p = argparse.ArgumentParser(description='Source-bound development studies; never auto-promote research claims.')
    p.add_argument('command', choices=['prepare', 'status', 'export', 'pilot-b', 'pilot-a', 'audit-c', 'authorize-a', 'audit-energy', 'audit-scope'])
    p.add_argument('--home', type=Path, default=Path('/Users/depengsu/Documents/bf-agent-workbench'))
    p.add_argument('--study', default='abc-development-v1')
    p.add_argument('--input', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--port', type=int, default=8768)
    p.add_argument('--usd', type=float, default=.8)
    p.add_argument('--wall', type=int, default=7200)
    p.add_argument('--authorization')
    args = p.parse_args()
    if args.command.startswith('audit-') and args.command != 'audit-c':
        if not args.input:
            p.error('--input required')
        from . import evidence, scope
        value = (evidence.full_evaluate if args.command == 'audit-energy' else scope.evaluate)(json.loads(args.input.read_text()))
    else:
        r = Research(args.home, args.study)
        from . import pilots, paid
        if args.command == 'prepare':
            value = pilots.setup(r)
        elif args.command == 'pilot-b':
            value = {'report': pilots.run_b(r)}
        elif args.command == 'pilot-a':
            value = {'report': pilots.run_a(r, args.port)}
        elif args.command == 'audit-c':
            value = {'report': pilots.run_c(r)}
        elif args.command == 'authorize-a':
            value = paid.authorize(r, pilots.read_setup(r)['A']['protocol'], max_usd=args.usd,
                                   wall_s=args.wall, authorization=args.authorization)
        elif args.command == 'export':
            value = r.export()
        else:
            value = r.project()
    if args.output:
        write_atomic(args.output, canonical(value).encode())
        print(canonical({'output': str(args.output)}))
    else:
        print(canonical(value))


if __name__ == '__main__':
    main()
