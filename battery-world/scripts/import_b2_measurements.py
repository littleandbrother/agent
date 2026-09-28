#!/usr/bin/env python3
"""Explicit one-time read-only import; normal Studio build does not scan hardware."""
import argparse
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.campaign.measurements import import_archived,archive_bundle
from bfworld.kernel.canonical import write_canonical_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);args=parser.parse_args()
    root,report=import_archived(args.source,REPO/'.bfworld/measured-imports')
    archive_bundle(root,REPO/'docs/b2-development/measured-replay.zip')
    # Pointer is a projection, raw authoritative files stay content-addressed.
    write_canonical_json(REPO/'docs/b2-development/measured-import.json',{'artifact':str(root.relative_to(REPO)),'report':report})
    o=report['observations']
    print(json.dumps({'status':'imported','manifest_hash':report['manifest_hash'],'current_samples':o['current']['raw_samples'],
        'receiver_rows':o['receiver']['rows'],'matched_rows':o['receiver']['matched_rows'],'hardware_admission':False,'provider_calls':0}))

if __name__=='__main__':main()
