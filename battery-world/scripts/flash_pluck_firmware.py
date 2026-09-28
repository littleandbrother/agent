#!/usr/bin/env python3
"""Prepared target-specific flashing plan. Dry run unless --execute is explicit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

def main():
    p=argparse.ArgumentParser();p.add_argument('--serial',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not re.fullmatch(r'[0-9]+',a.serial):raise ValueError('Numeric J-Link serial required')
    root=Path(__file__).resolve().parent
    soft=root/'s132_nrf52_3.0.0_softdevice.hex'
    apps=list((root/'_build').glob('*.hex'))
    if not soft.is_file() or len(apps)!=1:raise RuntimeError('Images missing or ambiguous')
    receipt=json.loads((root/'receipt.json').read_text())
    for file in [soft,apps[0]]:
        if receipt['files'].get(str(file.relative_to(root)))!=hashlib.sha256(file.read_bytes()).hexdigest():
            raise RuntimeError('Image changed since build receipt; stopped before device access')
    common=['nrfjprog','--snr',a.serial,'--family','NRF52']
    probe=common+['--memrd','0x10000100','--n','4']
    commands=[probe]+[common+['--program',str(f),'--sectorerase','--verify'] for f in [soft,apps[0]]]+[common+['--reset']]
    for cmd in commands:print(' '.join(cmd))
    if not a.execute:print('DRY RUN: nothing connected, erased, written or reset.');return
    result=subprocess.run(probe,capture_output=True,text=True,check=True)
    values=re.findall(r'0x10000100:\s*([0-9A-Fa-f]{8})',result.stdout,re.I)
    if len(values)!=1 or int(values[0],16)!=0x52832:raise RuntimeError('FICR.PART is not nRF52832; stopped before programming')
    for cmd in commands[1:]:subprocess.run(cmd,check=True)

if __name__=='__main__':main()
