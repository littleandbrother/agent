#!/usr/bin/env python3
"""Prepare or execute separately scoped native paper tasks."""
import argparse,json
from pathlib import Path
from bfworld.agentlab.literature_native import DEFAULT_ROOT,prepare_contract,run_native_tasks

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('papers',nargs='+')
    p.add_argument('--root',type=Path,default=DEFAULT_ROOT);p.add_argument('--resume',action='store_true',help='Continue the original owner, cost cap and deadline; preserve original results')
    p.add_argument('--method-overlay',choices=['M2'],help='Independently qualified async-firmware experiment only; no production adoption');p.add_argument('--phase',choices=['firmware','engineering-repair','engineering-review','delivery','eda'],help='Declared public scoped continuation; original owner and budget required');a=p.parse_args()
    if a.action=='prepare':
        for pid in a.papers:
            c,path=prepare_contract(a.root,pid)
            print(json.dumps({'paper':pid,'contract':str(path/'contract.json'),'source_identity':c['source_identity']},ensure_ascii=False))
    else:
        results=run_native_tasks(a.root,a.papers,resume=a.resume,method_overlay=a.method_overlay,phase=a.phase)
        print(json.dumps({'completed_native_tasks':len(results),'full_products_accepted':0},ensure_ascii=False))

if __name__=='__main__':main()
