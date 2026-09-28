"""Sealed v2 runs with their load contract and exact numerical reproduction."""
from __future__ import annotations
import html
import json
import os
import shutil
import tempfile
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from bfworld.kernel.canonical import canonical_bytes, file_hash, write_canonical_json
from .profiled import VERSION, verify

NAMES={'run.json','world.ir.json','events.jsonl','channels.parquet','evidence.json','views.json','replay.html'}

def world_ir(run):
    return {k:run[k] for k in ('schema_version','design','reference','load_profile','model_artifact','fidelity','time_semantics')}

def verify_bundle(root:Path, *, reproduce=False):
    m=json.loads((root/'run-manifest.json').read_text())
    if m.get('schema_version')!='profiled-manifest-v2' or set(m['inventory'])!=NAMES or m.get('sealed') is not True:
        raise ValueError('profiled inventory mismatch')
    for name in NAMES:
        if file_hash(root/name)!=m['inventory'][name]:raise ValueError('profiled file integrity mismatch: '+name)
    run=json.loads((root/'run.json').read_text())
    if run['content_hash']!=m['content_hash']:raise ValueError('manifest identity mismatch')
    if json.loads((root/'world.ir.json').read_text())!=world_ir(run):raise ValueError('world projection mismatch')
    if pq.read_table(root/'channels.parquet').to_pylist()!=run['rows']:raise ValueError('channel projection mismatch')
    if [json.loads(x) for x in (root/'events.jsonl').read_text().splitlines()]!=run['events']:raise ValueError('event projection mismatch')
    evidence=json.loads((root/'evidence.json').read_text())
    if evidence!=evidence_for(run):raise ValueError('evidence projection mismatch')
    return verify(run,reproduce)

def evidence_for(run):
    return {'physical_mission_pass':run['physical_mission_pass'],'verified_mission_success':False,
            'source_kind':'synthetic-computational-reference','claim_boundary':run['claim_boundary']}

def seal_run(base:Path,run):
    verify(run)
    root=base/run['content_hash'].split(':')[1]
    if root.exists():verify_bundle(root);return root
    base.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.profiled-pending-',dir=base))
    try:
        for name,obj in [('run.json',run),('world.ir.json',world_ir(run)),('evidence.json',evidence_for(run)),
                         ('views.json',{'content_hash':run['content_hash'],'time':'rows[].time_s','voltage':'rows[].input_voltage_v','state':'rows[].mcu_state'})]:
            write_canonical_json(temp/name,obj)
        (temp/'events.jsonl').write_bytes(b''.join(canonical_bytes(e)+b'\n' for e in run['events']))
        pq.write_table(pa.Table.from_pylist(run['rows']),temp/'channels.parquet',compression='zstd')
        ymax=max(r['storage_voltage_v'] for r in run['rows']) * 1.1
        points=' '.join(f"{r['time_s']/run['reference']['duration_s']*900:.2f},{250-r['input_voltage_v']/ymax*240:.2f}" for r in run['rows'])
        info={k:run[k] for k in ('content_hash','load_profile','summary','physical_mission_pass','claim_boundary')}
        (temp/'replay.html').write_text('<!doctype html><meta charset="utf-8"><title>Profiled reference</title><style>body{font:16px system-ui;max-width:1000px;margin:3em auto;background:#10251e;color:#e8ebd8}pre{white-space:pre-wrap}</style><h1>Explicit phase-load reference</h1><p>Terminal voltage (V), horizontal axis time (s). Synthetic reference, not measurement.</p><svg viewBox="0 0 900 260"><polyline points="'+points+'" fill="none" stroke="#b9ec8e" stroke-width="2"/></svg><pre>'+html.escape(json.dumps(info,indent=2))+'</pre>')
        write_canonical_json(temp/'run-manifest.json',{'schema_version':'profiled-manifest-v2','reference_version':VERSION,
            'sealed':True,'content_hash':run['content_hash'],'inventory':{name:file_hash(temp/name) for name in sorted(NAMES)}})
        verify_bundle(temp,reproduce=True)
        os.rename(temp,root)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return root
