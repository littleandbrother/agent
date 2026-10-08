"""Read-only checks for source-bound E2 figures and preserved engineering files."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import zipfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(root):
    root=Path(root).resolve();seal=json.loads((root/'seal.json').read_text())
    for f in seal['files']:
        p=root/f['path']
        if not p.resolve().is_relative_to(root) or p.is_symlink() or digest(p)!=f['sha256'] or p.stat().st_size!=f['bytes']:
            raise ValueError('ATLAS_FILE_CHANGED:'+f['path'])
    index=json.loads((root/'report/figure-index.json').read_text())
    plan=json.loads((root/'report/figure-plan.json').read_text())
    sources=json.loads((root/'report/figure-sources.json').read_text())
    lookup={s['id']:{k:v for k,v in s.items() if k!='archive_file'} for s in sources}
    if list(lookup.values())!=plan['sources']:raise ValueError('ATLAS_SOURCES_CHANGED')
    for source in sources:
        if digest(root/'report'/source['archive_file'])!=source['sha256']:raise ValueError('ATLAS_INPUT_CHANGED')
    if [len(g['panels']) for g in index['groups']]!=[12,12,12,12,12,10]:raise ValueError('ATLAS_PLAN_COUNT')
    if hashlib.sha256(json.dumps(plan['sources'],sort_keys=True).encode()).hexdigest()!=seal['source_identity']:raise ValueError('ATLAS_SOURCE_IDENTITY')
    counts={s:sum(p['status']==s for p in index['panels']) for s in ('available','missing','not_applicable')}
    if counts!=index['counts'] or counts!=seal['counts']:raise ValueError('ATLAS_FALSE_COMPLETION')
    for p in index['panels']:
        provenance=json.loads((root/'report'/p['provenance']).read_text())
        if provenance!=p:raise ValueError('ATLAS_PANEL_RECORD_CHANGED:'+p['id'])
        identity=hashlib.sha256(json.dumps([lookup[s] for s in p['dependencies']],sort_keys=True).encode()).hexdigest()
        if identity!=p['source_identity']:raise ValueError('ATLAS_PANEL_SOURCE_CHANGED:'+p['id'])
        if p['status']!='available' and not p.get('reason'):raise ValueError('ATLAS_MISSING_REASON')
    native=[]
    for c in (22,47,100,220):
        folder=root/'analysis'/f'native-cin-{c}';r=json.loads((folder/'receipt.json').read_text())
        rows=list(csv.DictReader((folder/'waveform.csv').open()))
        times=[float(row['time_s']) for row in rows]
        if any(t2<t1 for t1,t2 in zip(times,times[1:])):raise ValueError('ATLAS_TIME_ORDER')
        for col in ('tip_m','storage_V','supply_V'):
            if not all(math.isfinite(float(row[col])) for row in rows):raise ValueError('ATLAS_NONFINITE')
        peak=max(float(row['storage_V']) for row in rows)
        # CSV is a 4001-point uniform interpolation of the adaptive RAW trace;
        # its sampled peak need not equal the full RAW peak bit for bit.
        native_peak=r['metrics']['peak_storage_V']
        if not math.isclose(peak,native_peak,rel_tol=0,abs_tol=1e-6):raise ValueError('ATLAS_RESULT_WAVEFORM_MISMATCH')
        if r['metrics']['tx_completed']!=0 or r['metrics']['received_events']!=0:raise ValueError('ATLAS_EXPECTED_FAILED_OUTCOME_CHANGED')
        native.append({'cin_uF':c,'VIN_V':native_peak,'sampled_peak_V':peak,'sampling_peak_difference_V':peak-native_peak,'sampling_peak_tolerance_V':1e-6,'TX':0,'RX':0})
    with zipfile.ZipFile(root/'report/scientific-figures.zip') as archive:
        for source in sources:
            if hashlib.sha256(archive.read(source['archive_file'])).hexdigest()!=source['sha256']:raise ValueError('ATLAS_ZIP_INPUT_CHANGED')
        for name in ('figure-index.json','figure-quality.json','door-evidence-report.pdf'):
            if archive.read(name)!=(root/'report'/name).read_bytes():raise ValueError('ATLAS_ZIP_STALE:'+name)
    if any(seal[k] for k in ('product_accepted','hardware_verified','autonomous_agent_verified')):raise ValueError('ATLAS_CLAIM_BOUNDARY')
    return {'status':'passed','files':len(seal['files']),'groups':6,'planned_panels':70,'counts':counts,'new_native_runs':native,
            'source_identity':seal['source_identity'],'scope':'Input, plot, archive and failed-result consistency only; no hardware or autonomous replication qualification.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');a=p.parse_args();print(json.dumps(verify(a.root),ensure_ascii=False))
