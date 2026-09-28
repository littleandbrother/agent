#!/usr/bin/env python3
"""Explicit paid opt-in only. Never called by init.sh or a browser page load."""
import argparse
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.campaign.study import Campaign
from bfworld.campaign.budget import BudgetStop
from bfworld.kernel.canonical import write_canonical_json
def main():
 parser=argparse.ArgumentParser();choice=parser.add_mutually_exclusive_group(required=True);choice.add_argument('--prepare',action='store_true');choice.add_argument('--run',action='store_true');args=parser.parse_args()
 campaign=Campaign(REPO)
 try:
  if args.prepare:print(json.dumps(campaign.prepare(),indent=2))
  else:campaign.run()
 except BudgetStop as e:
  report={'status':'stopped','reason':str(e),'budget':campaign.ledger.summary(),'no_implicit_retry':True}
  write_canonical_json(REPO/'docs/campaign/stop.json',report);print(json.dumps(report),flush=True);raise SystemExit(2)
if __name__=='__main__':main()
