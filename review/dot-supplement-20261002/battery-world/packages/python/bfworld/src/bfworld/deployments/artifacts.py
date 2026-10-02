import json
import tempfile
import os
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from bfworld.kernel.canonical import canonical_hash,canonical_bytes,file_hash,write_canonical_json

def validate(run:dict):
    if canonical_hash({k:v for k,v in run.items() if k!='content_hash'})!=run['content_hash']:raise ValueError('deployment identity mismatch')
    if run['ledger']['relative_residual']>1e-7:raise ValueError('deployment energy ledger mismatch')
    ledger=run['ledger']
    if abs(ledger['raw_harvest']-ledger['harvest']-ledger['source_conversion_loss'])>1e-9:raise ValueError('source converter energy mismatch')
    if abs(sum(run['summary']['energy_by_source_j'].values())-ledger['harvest'])>1e-9:raise ValueError('hybrid allocation mismatch')
    if run['summary']['verified_mission_success']:raise ValueError('deployment cannot self-qualify')
    events=run['events']
    if [(e['time_s'],e['priority']) for e in events]!=sorted((e['time_s'],e['priority']) for e in events):raise ValueError('event order violated')
    for row in run['rows']:
        for port in row['ports']:
            if abs(port['raw_power_w']-port['bus_power_w']-port['conversion_loss_w'])>1e-12:raise ValueError('port conservation failed')
    return {'status':'pass','identity':run['content_hash'],'samples':len(run['rows'])}

def seal(base:Path,run:dict)->Path:
    validate(run);root=base/run['content_hash'].split(':')[1]
    if root.exists():verify(root);return root
    base.mkdir(parents=True,exist_ok=True)
    destination=root
    root=Path(tempfile.mkdtemp(prefix='.pending-',dir=base))
    write_canonical_json(root/'run.json',run)
    write_canonical_json(root/'world.ir.json',{'config':run['config'],'scene':run['scene'],'fidelity':run['fidelity']})
    write_canonical_json(root/'evidence.json',{'summary':run['summary'],'claim_boundary':run['claim_boundary']})
    write_canonical_json(root/'views.json',run['visual_bindings'])
    (root/'events.jsonl').write_bytes(b''.join(canonical_bytes(e)+b'\n' for e in run['events']))
    pq.write_table(pa.Table.from_pylist(run['rows']),root/'channels.parquet',compression='zstd')
    write_canonical_json(root/'run-manifest.json',{'content_hash':run['content_hash'],'inventory':{p.name:file_hash(p) for p in sorted(root.iterdir())},'sealed':True})
    verify(root)
    try:os.rename(root,destination)
    except OSError:
        if not destination.exists():raise
        verify(destination)
    return destination

def verify(root:Path):
    manifest=json.loads((root/'run-manifest.json').read_text())
    for name,digest in manifest['inventory'].items():
        if file_hash(root/name)!=digest:raise ValueError('deployment artifact tamper')
    run=json.loads((root/'run.json').read_text())
    if run['content_hash']!=manifest['content_hash']:raise ValueError('manifest reference mismatch')
    return validate(run)
