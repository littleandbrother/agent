#!/usr/bin/env python3
"""Operate the reference/learning campaign without resetting any runtime ledger."""
import argparse,json
from pathlib import Path
from bfworld.agentlab.literature_campaign import register,projection,DEFAULT_ROOT
p=argparse.ArgumentParser();p.add_argument('action',choices=['register','status']);p.add_argument('--root',type=Path,default=DEFAULT_ROOT);a=p.parse_args()
r=register(a.root) if a.action=='register' else projection(a.root)
print(json.dumps(r,ensure_ascii=False,indent=2))
