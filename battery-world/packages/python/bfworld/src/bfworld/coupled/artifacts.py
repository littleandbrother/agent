"""Content-addressed computational runs. A sealed directory is never overwritten."""
from __future__ import annotations
import html
import json
import os
import shutil
import tempfile
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from bfworld.kernel.canonical import canonical_bytes,canonical_hash,file_hash,write_canonical_json
from .engine import Design,Reference,execute

def validate_run(run:dict,*,reproduce:bool=False)->dict:
    unsigned={k:v for k,v in run.items() if k!='content_hash'}
    if canonical_hash(unsigned)!=run['content_hash']:raise ValueError('run identity mismatch')
    rows=run['rows'];events=run['events']
    if not rows or any(b['time_s']<=a['time_s'] for a,b in zip(rows,rows[1:])):raise ValueError('invalid timebase')
    if [(e['time_s'],e['priority'],e['seq']) for e in events]!=sorted((e['time_s'],e['priority'],e['seq']) for e in events):raise ValueError('event ordering violated')
    if run['energy_ledger']['normalized_residual']>1e-7:raise ValueError('energy closure failed')
    if run['verified_mission_success']:raise ValueError('computational reference cannot self-qualify VMS')
    request=run['request']
    if request['receive_s'] is not None and not any(e['type']=='receiver_delivered' for e in events):raise ValueError('receiver evidence missing')
    if reproduce and execute(Design(**run['design']),Reference(**run['reference']))['content_hash']!=run['content_hash']:raise ValueError('deterministic reproduction failed')
    return {'status':'pass','content_hash':run['content_hash'],'samples':len(rows),'events':len(events),'reproduced':reproduce}

def verify_bundle(root:Path,*,reproduce:bool=False)->dict:
    manifest=json.loads((root/'run-manifest.json').read_text())
    for name,expected in manifest['inventory'].items():
        if file_hash(root/name)!=expected:raise ValueError(f'artifact integrity mismatch: {name}')
    run=json.loads((root/'run.json').read_text())
    if manifest['content_hash']!=run['content_hash']:raise ValueError('manifest identity mismatch')
    if pq.read_table(root/'channels.parquet').to_pylist()!=run['rows']:raise ValueError('channel projection mismatch')
    if [json.loads(s) for s in (root/'events.jsonl').read_text().splitlines()]!=run['events']:raise ValueError('event projection mismatch')
    return validate_run(run,reproduce=reproduce)

def seal_run(base:Path,run:dict)->Path:
    validate_run(run)
    root=base/run['content_hash'].split(':')[1]
    if root.exists():verify_bundle(root);return root
    base.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.pending-',dir=base))
    try:
        write_canonical_json(temporary/'run.json',run)
        write_canonical_json(temporary/'world.ir.json',{'design':run['design'],'reference':run['reference'],'fidelity':run['fidelity'],'time_semantics':run['time_semantics']})
        write_canonical_json(temporary/'evidence.json',{'physical_mission_pass':run['physical_mission_pass'],'evidence_admissibility':run['evidence_admissibility'],'verified_mission_success':False,'claim_boundary':run['claim_boundary']})
        write_canonical_json(temporary/'views.json',{'time':'rows[].time_s','voltage':'rows[].storage_voltage_v','prediction':'rows[].predicted_voltage_v','state':'rows[].mcu_state','source_kind':'computational-reference','content_hash':run['content_hash']})
        (temporary/'events.jsonl').write_bytes(b''.join(canonical_bytes(e)+b'\n' for e in run['events']))
        pq.write_table(pa.Table.from_pylist(run['rows']),temporary/'channels.parquet',compression='zstd')
        points=' '.join(f"{r['time_s']/run['reference']['duration_s']*900:.2f},{250-r['storage_voltage_v']*30:.2f}" for r in run['rows'])
        (temporary/'replay.html').write_text('<!doctype html><meta charset="utf-8"><title>Coupled computational run</title><style>body{background:#10251e;color:#e8ebd8;font:16px system-ui;max-width:1000px;margin:4em auto}svg{background:#16342a}pre{white-space:pre-wrap}</style><h1>Coupled mission · offline evidence</h1><p>'+html.escape(run['claim_boundary'])+'</p><svg viewBox="0 0 900 260"><polyline points="'+points+'" fill="none" stroke="#b9ec8e" stroke-width="2"/></svg><pre>'+html.escape(json.dumps({'identity':run['content_hash'],'outcome':run['physical_mission_pass'],'request':run['request'],'summary':run['summary'],'fidelity':run['fidelity']},indent=2))+'</pre>')
        inventory={p.name:file_hash(p) for p in sorted(temporary.iterdir())}
        write_canonical_json(temporary/'run-manifest.json',{'schema_version':'coupled-manifest-v1','content_hash':run['content_hash'],'inventory':inventory,'sealed':True})
        verify_bundle(temporary)
        os.rename(temporary,root)
    finally:
        if temporary.exists():shutil.rmtree(temporary)
    return root
