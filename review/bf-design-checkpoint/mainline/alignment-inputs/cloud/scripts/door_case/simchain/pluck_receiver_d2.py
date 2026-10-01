#!/usr/bin/env python3
"""Receive the case BLE manufacturer payload or replay JSONL captures.

Live mode requires bleak and Bluetooth permission. Hardware capture is never
started during simulation. Silence grouping does not recover true direction.
"""
import argparse
import asyncio
import json
import math
from pathlib import Path
import time

def decode(data):
    if len(data)!=12 or data[:4]!=b'BFD2':return None
    return {'device_id':data[4:].hex(),'protocol':'BFD2','direction':'unknown'}


def fit_direction(calibration):
    """Separate class envelopes or abstain. No synthetic data imply calibration."""
    groups = {label: [] for label in ('open', 'close')}
    ids = set()
    for row in calibration:
        if row.get('id') in ids or row.get('label') not in groups or type(row.get('packets')) is not int or row['packets'] < 1:
            raise ValueError('INVALID_CALIBRATION')
        ids.add(row['id']); groups[row['label']].append(row['packets'])
    if any(len(v) < 3 for v in groups.values()):
        return {'qualified':False,'reason':'insufficient-distributions','calibration_ids':sorted(ids)}
    ranges = {k:[min(v),max(v)] for k,v in groups.items()}
    separated = ranges['open'][1] < ranges['close'][0] or ranges['close'][1] < ranges['open'][0]
    return {'qualified':separated,'ranges':ranges,'calibration_ids':sorted(ids),
            'reason':'disjoint-observed-envelopes' if separated else 'overlapping-packet-counts',
            'scope':'Classifier acceptance applies only to bound calibration source and receive model, not real hardware.'}


def direction(packets, classifier=None):
    if not classifier or not classifier.get('qualified'):
        return 'unknown'
    matches=[label for label,(low,high) in classifier['ranges'].items() if low<=packets<=high]
    return matches[0] if len(matches)==1 else 'unknown'

def group(records, silence_s=.35, classifier=None):
    if not math.isfinite(silence_s) or silence_s<=0:raise ValueError('INVALID_SILENCE')
    for r in records:
        if not isinstance(r.get('time_s'),(int,float)) or not math.isfinite(r['time_s']) or r['time_s']<0:raise ValueError('INVALID_CAPTURE_TIME')
    latest={};events=[];seen={}
    for r in sorted(records,key=lambda x:x['time_s']):
        try:data=decode(bytes.fromhex(r['payload_hex']))
        except (ValueError,KeyError,TypeError):continue
        if data is None:continue
        # Deduplicate copied capture rows, not identical BLE payloads. BFD2 has
        # no per-TX sequence, so radio-level duplicate identity is unavailable.
        rid=r.get('capture_id')
        if rid is not None:
            signature=(r['time_s'],r['payload_hex'])
            if rid in seen:
                if seen[rid]!=signature:raise ValueError('CAPTURE_ID_CONFLICT')
                continue
            seen[rid]=signature
        key=data['device_id'];t=r['time_s'];event=latest.get(key)
        if event is None or t-event['last_packet_s']>silence_s:
            event={**data,'first_packet_s':t,'last_packet_s':t,'packets':0,'origin':r.get('origin','unspecified')};events.append(event);latest[key]=event
        event['packets']+=1;event['last_packet_s']=t
    for event in events:
        event['direction']=direction(event['packets'],classifier)
        event['event_identity']='silence-group-estimate'
        event['radio_duplicates_resolved']=False
        event['reboot_identity_available']=False
    return events

async def live(path, seconds):
    from bleak import BleakScanner
    start=time.monotonic()
    with path.open('x') as stream:
        def callback(device, adv):
            payload=adv.manufacturer_data.get(0xffff,b'')
            if decode(payload):
                r={'time_s':time.monotonic()-start,'utc_ns':time.time_ns(),'payload_hex':payload.hex(),'rssi':adv.rssi,'origin':'bluetooth-observation'}
                stream.write(json.dumps(r)+'\n');stream.flush()
        async with BleakScanner(detection_callback=callback):await asyncio.sleep(seconds)

def main():
    p=argparse.ArgumentParser();p.add_argument('--replay',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--seconds',type=float,default=30);a=p.parse_args()
    if bool(a.replay)==bool(a.capture):p.error('choose replay OR capture')
    if not 0<a.seconds<=600:p.error('seconds must be 0..600')
    if a.capture:asyncio.run(live(a.capture,a.seconds));source=a.capture
    else:source=a.replay
    print(json.dumps({'events':group([json.loads(x) for x in source.read_text().splitlines() if x.strip()]),'scope':'receiver observation; no physical motion ground truth or direction qualification'},indent=2))
if __name__=='__main__':main()
