"""Operator-imported load captures; capture provenance is not hardware certification."""
import csv
import hashlib
import io
import json
import math
import re
import time
from pathlib import Path

from .store import canonical, identity


def import_capture(app, owner, body):
    """Called only after operator authentication, never from participant tools."""
    required = ('instrument', 'hardware_id', 'captured_at', 'firmware_sha256', 'csv')
    if any(not isinstance(body.get(k), str) or not body[k].strip() for k in required):
        raise ValueError('MEASUREMENT_CAPTURE_FIELDS_REQUIRED')
    if not re.fullmatch('[a-f0-9]{64}', body['firmware_sha256']):
        raise ValueError('MEASUREMENT_FIRMWARE_HASH_INVALID')
    raw = body['csv'].encode()
    if len(raw) > 90000:
        raise ValueError('MEASUREMENT_CAPTURE_TOO_LARGE')
    # Bind to an actual artifact from this owner's completed compilation job.
    builds = [j for j in app.engineering.jobs(owner) if j['status'] == 'SUCCEEDED' and j['engine'] in ('mcu-firmware', 'tinyml-nas')]
    match = next(((j, a) for j in builds for a in (j.get('result') or {}).get('artifacts', [])
                  if a['name'].endswith('.bin') and a['sha256'] == body['firmware_sha256']), None)
    if not match:
        raise ValueError('MEASUREMENT_COMPILED_BINARY_BINDING_REQUIRED')
    app.engineering.artifact(owner, match[0]['id'], match[1]['name'])
    rows = list(csv.DictReader(io.StringIO(body['csv'])))
    if len(rows) < 3 or set(rows[0]) != {'time_s', 'current_a', 'voltage_v', 'stage'}:
        raise ValueError('MEASUREMENT_CSV_SCHEMA')
    stages, seen, previous = [], set(), -1
    for row in rows:
        t, current, voltage = [float(row[k]) for k in ('time_s', 'current_a', 'voltage_v')]
        if not all(math.isfinite(v) for v in (t, current, voltage)) or t <= previous or t < 0 or current < 0 or voltage <= 0:
            raise ValueError('MEASUREMENT_CSV_VALUES')
        name = row['stage']
        if not re.fullmatch('[a-zA-Z0-9_-]{1,40}', name):
            raise ValueError('MEASUREMENT_STAGE_NAME')
        if not stages or stages[-1]['name'] != name:
            if name in seen:
                raise ValueError('MEASUREMENT_REPEATED_STAGE_REQUIRES_SEGMENTED_CAPTURE')
            seen.add(name)
            stages.append({'name': name, 'rows': []})
        stages[-1]['rows'].append((t, current, voltage))
        previous = t
    derived = []
    for stage in stages:
        values = stage['rows']
        if len(values) < 2:
            raise ValueError('MEASUREMENT_STAGE_NEEDS_TWO_SAMPLES')
        duration = values[-1][0] - values[0][0]
        charge = sum((b[0]-a[0])*(a[1]+b[1])/2 for a,b in zip(values,values[1:]))
        energy = sum((b[0]-a[0])*(a[1]*a[2]+b[1]*b[2])/2 for a,b in zip(values,values[1:]))
        derived.append({'name':stage['name'],'duration_s':duration,'current_a':charge/duration,'energy_j':energy})
    record = {'schema_version':'bf-load-capture-v1','owner':owner,'created':time.time(),
              **{k:body[k] for k in required if k != 'csv'}, 'raw_sha256':hashlib.sha256(raw).hexdigest(),
              'firmware_job':match[0]['id'],'stages':derived,'voltage_min_v':min(float(r['voltage_v']) for r in rows),
              'voltage_max_v':max(float(r['voltage_v']) for r in rows),'origin':'operator-imported',
              'boundary':'Operator attests capture origin; this import does not prove flashing, RF reception or product qualification.'}
    key = identity(record)
    root = app.store.root.parent/'measurements'/owner
    root.mkdir(parents=True, exist_ok=True)
    for name, data in [(key+'.csv',raw),(key+'.json',canonical(record).encode())]:
        with (root/name).open('xb') as f:
            f.write(data)
    app.engineering.event(owner,None,'measurement_imported',{'measurement_sha256':key,**record})
    return {'measurement_sha256':key,**record}


def verified_load(home, owner, workload):
    key = workload.get('measurement_sha256')
    if not re.fullmatch('[a-f0-9]{64}',key or '') or not re.fullmatch('[A-Za-z0-9_-]+',owner):
        raise ValueError('MEASUREMENT_ID_INVALID')
    root = Path(home)/'measurements'/owner
    path = root/(key+'.json')
    if not path.is_file():
        raise ValueError('MEASUREMENT_OPERATOR_IMPORT_REQUIRED')
    record = json.loads(path.read_text())
    if identity(record) != key or hashlib.sha256((root/(key+'.csv')).read_bytes()).hexdigest() != record['raw_sha256']:
        raise ValueError('MEASUREMENT_TAMPER')
    if record['owner'] != owner or record['firmware_sha256'] != workload.get('firmware_sha256'):
        raise ValueError('MEASUREMENT_FIRMWARE_MISMATCH')
    stages = [{k:s[k] for k in ('name','duration_s','current_a')} for s in record['stages']]
    if stages != workload.get('stages'):
        raise ValueError('MEASUREMENT_LOAD_PROFILE_MISMATCH')
    return record


def evaluate_receiver(actions, receptions, deadline_s):
    """Evaluate explicit recorded event identities, never synthesize reception."""
    if not math.isfinite(deadline_s) or deadline_s <= 0:
        raise ValueError('RECEIVER_DEADLINE_INVALID')
    if len({a['event_id'] for a in actions}) != len(actions):
        raise ValueError('RECEIVER_ACTION_ID_AMBIGUOUS')
    if any(not isinstance(x['event_id'],str) or not math.isfinite(x['time_s']) for x in actions+receptions):
        raise ValueError('RECEIVER_RECORD_INVALID')
    eligible, misses, duplicates = [], [], []
    action_ids = {a['event_id'] for a in actions}
    for action in actions:
        matches = sorted([r for r in receptions if r['event_id']==action['event_id']],key=lambda r:r['time_s'])
        ontime = [r for r in matches if 0 <= r['time_s']-action['time_s'] <= deadline_s]
        if ontime:
            eligible.append({'event_id':action['event_id'],'latency_s':ontime[0]['time_s']-action['time_s']})
        else:
            misses.append(action['event_id'])
        duplicates.extend(matches[1:])
    false = [r for r in receptions if r['event_id'] not in action_ids]
    return {'successes':eligible,'misses':misses,'duplicates':duplicates,'unmatched_receptions':false,
            'passed':bool(actions) and not (misses or duplicates or false),
            'boundary':'Recorded IDs/timestamps only; raw capture identity and synchronization require separate provenance.'}
