#!/usr/bin/env python3
"""Preflight by default. Explicit authorized dispatch or read-only reconciliation.

No credentials are loaded in preflight/reconcile-only mode. The latter uses a
SQLite read-only connection and cannot reserve, settle or dispatch provider calls.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.campaign.budget import Ledger,BudgetStop
from bfworld.campaign.provider import Provider
from bfworld.campaign.repair_bridge import ProviderRepairAdapter,check_authority,run_provider_repair

class ReconcileOnly(ProviderRepairAdapter):
    def __call__(self,request):raise BudgetStop('reconcile-only has no dispatch capability; no settled response to recover')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,default=REPO/'studies/b2-003/protocol-draft.json')
    parser.add_argument('--initial',type=Path,required=True);parser.add_argument('--contexts',type=Path,required=True)
    parser.add_argument('--trial-id',required=True);parser.add_argument('--output',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--execute',action='store_true');mode.add_argument('--reconcile-only',action='store_true')
    parser.add_argument('--key-file',type=Path)
    args=parser.parse_args();protocol=json.loads(args.protocol.read_text());initial=json.loads(args.initial.read_text());contexts=json.loads(args.contexts.read_text())
    if not args.reconcile_only:
        try:authority=check_authority(protocol,REPO,initial,contexts)
        except BudgetStop as exc:
            print(json.dumps({'status':'not-authorized','reason':str(exc),'provider_calls':0,'credentials_loaded':False}));return 2
        if not args.execute:
            print(json.dumps({'status':'preflight-ready-no-dispatch','authority':authority,'provider_calls':0,'credentials_loaded':False}));return 0
        if args.key_file is None:raise BudgetStop('explicit private credential file required after successful preflight')
        ledger=Ledger(REPO/'.bfworld/paid-campaign/cost.sqlite')
        provider=Provider(args.key_file,ledger);adapter_type=ProviderRepairAdapter
    else:
        path=(REPO/'.bfworld/paid-campaign/cost.sqlite').resolve()
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        ledger=SimpleNamespace(db=db,total=19_000_000,per_trial=2_000_000,max_calls=120,max_tokens=600_000)
        provider=SimpleNamespace(ledger=ledger);adapter_type=ReconcileOnly
    try:
        adapter=adapter_type(protocol,REPO,initial,contexts,provider,args.output/'provider',args.trial_id)
        result=run_provider_repair(initial,contexts,args.output/'repair',adapter)
        print(json.dumps({'status':result['mechanical_result']['status'],'result_hash':result['content_hash'],
            'local_cost_complete':result['local_cost_complete'],'scientific_qualified':False,
            'reconcile_only':args.reconcile_only,'cost':result['mechanical_result']['cost']}))
        return 0
    finally:ledger.db.close()

if __name__=='__main__':
    try:sys.exit(main())
    except (BudgetStop,ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({'status':'stopped','reason':str(exc),'no_automatic_retry':True}));sys.exit(2)
