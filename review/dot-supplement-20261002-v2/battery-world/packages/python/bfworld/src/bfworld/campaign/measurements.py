"""Read-only measured-current and receiver-log import, not hardware admission.

No voltage is inferred from current; no heuristic event alignment is relabelled
as a shared clock. Missing phase energy stays null. Imported bytes are sealed
locally and independently auditable after disconnecting the source directory.
"""
from __future__ import annotations
import csv
import json
import math
import os
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash,file_hash,write_canonical_json
from .repair import checked

FILES={
 'current.csv':'origin_onnx_worktree_dev_20260525/measurements/h13_m128_final30/power_rep_0003.csv',
 'mcu-events.csv':'origin_onnx_worktree_dev_20260525/measurements/h13_m128_final30/events_rep_0003.csv',
 'historical-phase-ledger.csv':'origin_onnx_worktree_dev_20260525/measurements/h13_m128_final30/phase_energy_aligned.csv',
 'alignment-method.py':'origin_onnx_worktree_dev_20260525/scripts/h13_phase_energy_align.py',
 'receiver-alignment.csv':'measurements/infoenergy_live_20260831/harvester_watch_v1/ble_rx_v1/tx_rx_alignment.csv',
 'receiver-manifest.json':'measurements/infoenergy_live_20260831/harvester_watch_v1/ble_rx_v1/manifest.json',
 'wiring-state.json':'measurements/infoenergy_live_20260831/harvester_watch_v1/wiring_state.json',
 'collector-manifest.json':'measurements/infoenergy_live_20260831/harvester_watch_v1/collector_manifest.json',
 'unusable-ppk-manifest.json':'measurements/infoenergy_live_20260831/powered_functional_ppk_cache_v2/manifest.json',
}

def read_current(path):
    points=[]
    with path.open(newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=['sample','time_s','current_A']:raise ValueError('explicit seconds/amperes schema required')
        for row in reader:
            t=float(row['time_s']);i=float(row['current_A']);n=int(row['sample'])
            if not math.isfinite(t) or not math.isfinite(i) or t<0:raise ValueError('invalid measured sample')
            if points and (t<=points[-1]['time_s'] or n!=points[-1]['sample']+1):raise ValueError('nonmonotonic current capture')
            points.append({'sample':n,'time_s':t,'current_a':i})
    if len(points)<2:raise ValueError('empty current capture')
    return points

def extrema_projection(points,buckets=1000):
    """Preserve temporal first/min/max/last samples in each fixed index bucket."""
    if buckets<1:raise ValueError('positive bucket count required')
    stride=max(1,math.ceil(len(points)/buckets));out=[]
    for start in range(0,len(points),stride):
        part=points[start:start+stride]
        chosen={p['sample']:p for p in (part[0],min(part,key=lambda p:p['current_a']),max(part,key=lambda p:p['current_a']),part[-1])}
        out.extend(chosen[k] for k in sorted(chosen))
    return out

def derive(root):
    points=read_current(root/'current.csv');dt=[b['time_s']-a['time_s'] for a,b in zip(points,points[1:])]
    charge=sum((a['current_a']+b['current_a'])/2*(b['time_s']-a['time_s']) for a,b in zip(points,points[1:]))
    with (root/'historical-phase-ledger.csv').open(newline='') as f:
        phase_rows=list(csv.DictReader(f))
    # This is a source ledger projection, not an independent realignment. Retain
    # all rows, including absent BLE phase measurements.
    phases=[]
    for row in phase_rows:
        value=lambda k:None if row.get(k,'')=='' else float(row[k])
        phases.append({'rep':row['rep'],'inference_duration_ms':value('infer128_duration_ms'),
            'reported_inference_energy_mj':value('infer128_energy_mJ'),'reported_tx_energy_mj':value('ble_tx_energy_mJ'),
            'alignment':'historical waveform-wake heuristic + MCU event deltas',
            'energy_voltage':'given voltage in source analysis, not synchronized voltage measurement'})
    with (root/'receiver-alignment.csv').open(newline='') as f:rx=list(csv.DictReader(f))
    statuses=dict(sorted(Counter(r['status'] for r in rx).items()))
    # Public projection contains aggregate facts, not receiver addresses or host IDs.
    return {'current':{'source_file':'current.csv','raw_samples':len(points),'duration_s':points[-1]['time_s']-points[0]['time_s'],
        'dt_min_s':min(dt),'dt_max_s':max(dt),'minimum_a':min(p['current_a'] for p in points),'peak_a':max(p['current_a'] for p in points),
        'integrated_charge_c':charge,'measured_energy_j':None,'measured_voltage_v':None,
        'sample_projection':'first/min/max/last per fixed index bucket; raw artifact retains every sample',
        'trace':extrema_projection(points),'scope':'single archived capture, no cross-device representativeness claim'},
        'historical_phases':phases,
        'receiver':{'rows':len(rx),'status_counts':statuses,
            'matched_rows':sum(r['status']=='MATCHED_PAYLOAD_AND_HOST_WINDOW' for r in rx),
            'scope':'independent receiver payload + host-window log matching; not RF ACK or synchronized air latency'},
        'source_boundary':{'current_and_receiver_same_session':False,'harvester_only_power_verified':False,
            'synchronized_storage_voltage_measured':False,'end_to_end_diagnosis_accuracy_verified':False,
            'hardware_mission_admitted':False,'phase_alignment_kind':'heuristic, not shared hardware trigger'},
        'rejected_asset':{'source_file':'unusable-ppk-manifest.json','reason':'source declares unsynchronized GUI cache; cannot bind phase energy or whole-board power'},
        'claim_boundary':'Real archived current and receiver artifacts from DIFFERENT experiments. They do not form one synchronized battery-free hardware episode. No measured energy is derived here.'}

def verify_bundle(root):
    manifest=checked(json.loads((root/'manifest.json').read_text()))
    if set(manifest['sources'])!=set(FILES):raise ValueError('measurement inventory mismatch')
    for name,meta in manifest['sources'].items():
        if file_hash(root/name)!=meta['sha256']:raise ValueError('measurement source changed: '+name)
    report=checked(json.loads((root/'report.json').read_text()))
    if report['manifest_hash']!=manifest['content_hash'] or report['observations']!=derive(root):
        raise ValueError('measurement derived projection mismatch')
    return report

def import_archived(source:Path,base:Path):
    source=source.resolve();sources={}
    for name,relative in FILES.items():
        path=(source/relative).resolve()
        if not path.is_relative_to(source) or not path.is_file():raise ValueError('missing exact measured source: '+relative)
        sources[name]={'source_relative_path':relative,'sha256':file_hash(path),'bytes':path.stat().st_size}
    unsigned={'schema_version':'measured-artifact-import-v1','sources':sources,'importer_hash':file_hash(Path(__file__)),
        'selection':'one explicit archived current capture rep_0003 + complete source phase ledger and receiver alignment table; no outcome-based calibration',
        'side_effects':'read-only source files; no device/collector/control operations'}
    manifest={**unsigned,'content_hash':canonical_hash(unsigned)}
    root=base/manifest['content_hash'].split(':')[1]
    if root.exists():return root,verify_bundle(root)
    base.mkdir(parents=True,exist_ok=True);temp=Path(tempfile.mkdtemp(prefix='.import-pending-',dir=base))
    try:
        for name,meta in sources.items():shutil.copyfile(source/meta['source_relative_path'],temp/name)
        write_canonical_json(temp/'manifest.json',manifest)
        body={'schema_version':'measured-replay-projection-v1','manifest_hash':manifest['content_hash'],'observations':derive(temp)}
        write_canonical_json(temp/'report.json',{**body,'content_hash':canonical_hash(body)})
        report=verify_bundle(temp);os.rename(temp,root)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return root,report

def archive_bundle(root:Path,target:Path):
    verify_bundle(root)
    # Fixed names only; no credentials, generic source tree, or collector binary.
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(set(FILES)|{'manifest.json','report.json'}):z.write(root/name,name)

def restore_archive(archive:Path,base:Path):
    base.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        names=set(FILES)|{'manifest.json','report.json'}
        if len(z.infolist())!=len(names) or set(z.namelist())!=names or sum(i.file_size for i in z.infolist())>30_000_000:
            raise ValueError('invalid or oversized measured archive')
        manifest=checked(json.loads(z.read('manifest.json')))
        root=base/manifest['content_hash'].split(':')[1]
        if root.exists():return root,verify_bundle(root)
        temp=Path(tempfile.mkdtemp(prefix='.restore-pending-',dir=base))
        try:
            for name in names:(temp/name).write_bytes(z.read(name))
            report=verify_bundle(temp);os.rename(temp,root)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return root,report
