#!/usr/bin/env python3
"""Verify that portable visual projections retain source data and identities."""
from __future__ import annotations
import json, math, re, sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from scripts.build_studio import build_payload
from bfworld.bundle.reader import RunBundleReader
from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.verification.verifier import verify_bundle

class StudioError(ValueError): pass

def validate_payload(payload:dict,repo:Path=REPO)->dict:
    unsigned=dict(payload);claimed=unsigned.pop('content_hash')
    if canonical_hash(unsigned)!=claimed:raise StudioError('payload hash mismatch')
    root=repo/'runs/a-rotary-v1'
    verified=verify_bundle(root)
    if payload['bundle_hash']!=verified['bundle_hash']:raise StudioError('source bundle mismatch')
    original=RunBundleReader(root).channels()
    projected=[r for p in payload['phases'] for r in p['rows']]
    if len(original)!=len(projected):raise StudioError('raw samples omitted')
    for a,b in zip(original,projected):
        if any(b.get(k)!=v for k,v in a.items()):raise StudioError('source sample changed')
        s=payload['world']['mission']['storage']
        expected=max(0,a['storage_energy_j']-.5*s['capacitance_f']*s['min_operating_voltage_v']**2)
        if not math.isclose(b['usable_energy_j'],expected,abs_tol=1e-14):raise StudioError('usable energy misbound')
        limit=.5*s['capacitance_f']*(s['max_safe_voltage_v']**2-s['min_operating_voltage_v']**2)
        if not math.isclose(b['energy_fill'],min(1,expected/limit),abs_tol=1e-14):raise StudioError('energy fill misbound')
    for visual,channel in payload['visual_bindings'].items():
        if channel not in payload['channels']:raise StudioError('visual source missing')
        binding=payload['channels'][channel]
        if not {'file','field','unit','source_kind','fidelity','producer','timebase','file_hash'}<=binding.keys():raise StudioError('provenance incomplete')
        if binding['file_hash']!=file_hash(root/binding['file']):raise StudioError('visual source hash mismatch')
    for component in payload['components']:
        if component['id'] in {'pmic','sensor','receiver'} and component['status']!='unimplemented':raise StudioError('absent component promoted')
    if any(payload['coverage'].values()):raise StudioError('A reference capability overstated')
    for phase in payload['phases']:
        if phase['summary']!=payload['manifest']['phases'][phase['id']]:raise StudioError('projected verdict changed')
    if 'coupled' in payload:
        from bfworld.coupled.artifacts import verify_bundle as verify_coupled
        for case in payload['coupled']['cases']:
            source=repo/case['path'];verify_coupled(source)
            run=json.loads((source/'run.json').read_text());view=case['run']
            if len(run['rows'])!=len(view['rows']):raise StudioError('coupled samples omitted')
            for a,b in zip(run['rows'],view['rows']):
                if any(b.get(k)!=v for k,v in a.items()):raise StudioError('coupled sample changed')
                c=run['design']['capacitance_f'];r=run['reference']
                fill=max(0,min(1,(a['energy_j']-.5*c*r['off_v']**2)/(.5*c*(r['max_v']**2-r['off_v']**2))))
                if not math.isclose(fill,b['energy_fill'],abs_tol=1e-14):raise StudioError('coupled energy misbound')
            for k,v in run.items():
                if k!='rows' and view.get(k)!=v:raise StudioError('coupled source metadata changed')
            if case['visual_provenance']['source_hash']!=file_hash(source/'run.json'):raise StudioError('coupled provenance changed')
    if 'learning' in payload:
        learning=json.loads((repo/'docs/knowledge/reference-study.json').read_text())
        if payload['learning']!=learning:raise StudioError('knowledge study projection changed')
    if 'deployments' in payload:
        for scene in payload['deployments']['scenes']:
            for variant in scene['variants']:
                source=json.loads((repo/variant['path']/'run.json').read_text())
                if source!=variant['run']:raise StudioError('deployment source projection changed')
    if 'campaign' in payload:
        from bfworld.campaign.audit import audit
        audit(payload['campaign'])
        if payload['campaign']!=json.loads((repo/'docs/campaign/report.json').read_text()):raise StudioError('campaign projection changed')
        import copy
        for digest,view in payload.get('campaign_traces',{}).items():
            run=copy.deepcopy(view);ref=run['reference'];c=run['design']['capacitance_f']
            for row in run['rows']:
                expected=max(0,min(1,(row['energy_j']-.5*c*ref['off_v']**2)/(.5*c*(ref['max_v']**2-ref['off_v']**2))))
                if not math.isclose(row.pop('energy_fill'),expected,abs_tol=1e-14):raise StudioError('campaign fill changed')
            trace_claimed=run.pop('content_hash')
            if canonical_hash(run)!=digest or trace_claimed!=digest:raise StudioError('campaign replay identity mismatch')
    return {'status':'passed','original_samples':len(original),'projected_samples':len(projected),
            'channel_bindings':len(payload['channels']),'visual_bindings':len(payload['visual_bindings']),
            'bundle_hash':verified['bundle_hash'],'payload_hash':claimed}

def main():
    dist=REPO/'apps/world-studio/dist/index.html'
    html=dist.read_text()
    match=re.search(r'<script id="studio-data" type="application/(json|gzip)">(.*?)</script>',html,re.S)
    if not match:raise StudioError('portable payload absent')
    import base64,gzip
    raw=gzip.decompress(base64.b64decode(match[2],validate=True)) if match[1]=='gzip' else match[2]
    payload=json.loads(raw);report=validate_payload(payload)
    if re.search(r'<(?:script|link)[^>]+(?:src|href)=["\']https?://',html):raise StudioError('external asset dependency')
    report['portable_html_hash']=file_hash(dist)
    write_canonical_json(REPO/'docs/studio/projection-validation.json',report)
    print(json.dumps(report))

if __name__=='__main__':main()
