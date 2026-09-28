"""Run an explicitly selected local check and bind its real output to snapshots."""
import argparse
import json
from pathlib import Path
from bfworld.agentlab.panorama import Panorama

parser=argparse.ArgumentParser()
parser.add_argument('--state',type=Path,required=True)
parser.add_argument('--label',required=True)
parser.add_argument('--timeout',type=int,default=600)
parser.add_argument('command',nargs=argparse.REMAINDER)
args=parser.parse_args()
command=args.command[1:] if args.command[:1]==['--'] else args.command
if not command:parser.error('command required after --')
result=Panorama(args.state).run_check(command,Path.cwd(),args.label,args.timeout)
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(result['exit_code'])
