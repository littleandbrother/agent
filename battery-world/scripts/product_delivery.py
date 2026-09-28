#!/usr/bin/env python3
"""Local operator helper; uses authenticated Studio APIs, never prints credentials."""
import argparse
import json
from pathlib import Path
import time
import urllib.request
import csv
import hashlib
import io
import shutil
import zipfile
import sqlite3

RUNTIME = Path('/Users/depengsu/Documents/bf-agent-workbench')
EVIDENCE = RUNTIME / 'verification/product-delivery'


def api(path, payload=None):
    token = (RUNTIME / 'state/operator.token').read_text().strip()
    request = urllib.request.Request('http://127.0.0.1:8768' + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode()) from None


def run(parameters, operation, engine='jlceda', owner=None):
    owner = owner or json.loads((EVIDENCE / 'live.json').read_text())['owner']
    return api('/api/engineering', {'action': 'run', 'session_id': owner,
        'engine': engine, 'operation_id': operation, 'parameters': parameters})


def wait(key, seconds=55):
    end = time.monotonic() + seconds
    while True:
        result = api('/api/engineering/jobs/' + key)
        if result['status'] not in ('RUNNING', 'QUEUED') or time.monotonic() >= end:
            return result
        time.sleep(2)


def receipt(value):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / (value['id'] + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2))
    r = value.get('result') or {}
    print(json.dumps({'id':value['id'], 'status':value['status'], 'error':value.get('error'),
        'components':len(r.get('components',[])), 'drc':r.get('drc'),
        'digital_checks_passed':r.get('digital_checks_passed'), 'exports':r.get('exports')}, ensure_ascii=False))


def independent_acceptance():
    """Read-only validation of Pi-authored baseline, physical change and control."""
    owner='pi-chat-7bbf6862d7109e25'
    jobs=['eng-179cc34c5f68745a','eng-760462379c246d3d','eng-7d974844fc7d4b65']
    roots=[RUNTIME/'engineering'/job for job in jobs]
    read=lambda p:json.loads(p.read_text())
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assemblies=[read(p/'input.json')['assembly'] for p in roots]
    cad=[read(p/'cad-readback.json') for p in roots]
    stages=[]
    with sqlite3.connect(RUNTIME/'state/workbench.sqlite') as db:
        db.row_factory=sqlite3.Row
        for job,root,a,c in zip(jobs,roots,assemblies,cad):
            assert a['owner']==owner and read(root/'result.json')['digital_checks_passed']
            assert c['step_reopened_valid'] and c['step_solid_count']==26 and not c['collisions']
            glb=read(EVIDENCE/('glb-'+job+'.json'));assert glb['passed'] and len(glb['parts'])==26
            files=[dict(r) for r in db.execute('SELECT * FROM assembly_files WHERE owner=? AND revision=? ORDER BY created',(owner,a['revision']))]
            bound=[]
            for f in files:
                p=RUNTIME/'state/product-assemblies'/owner/'files'/f['id']
                assert digest(p)==f['digest'] and p.stat().st_size==f['bytes']
                if f['name'].endswith('.json') and f['kind']=='source':
                    assert read(p)==a['payload'];bound.append(f)
            assert bound and any(f['kind']=='document' for f in files)
            stages.append({'revision':a['revision'],'job':job,'hashes':a['hashes'],'parts':26,'source_payload_exact_match':True,'files':files,'bounds_mm':c['assembly_bounds'],'native_checks_passed':True,'fresh_glb_import_passed':True})
        ledger=[]
        for who in ['pi-chat-cf37636f82c771a4',owner]:
            rows=[dict(r) for r in db.execute('SELECT id,created,status,charged,reserved,usage,error FROM model_requests WHERE owner=? ORDER BY created',(who,))]
            assert all(r['status']=='SETTLED' for r in rows)
            ledger.append({'owner':who,'requests':len(rows),'charged_usd':round(sum(r['charged'] for r in rows),9),'statuses':{'SETTLED':len(rows)}})
        messages=[dict(r) for r in db.execute('SELECT id,operation,text,status,created FROM chat_messages WHERE conversation=? ORDER BY created',(owner,))]
        assert db.execute('SELECT status FROM conversations WHERE id=?',(owner,)).fetchone()[0]=='IDLE'
    for job in jobs[:2]:
        no_masks=read(EVIDENCE/('contacts-'+job)/'cad-readback.json')
        assert no_masks['allowed_contacts']==[] and no_masks['collisions']==[]
    a,b,c=assemblies
    expected=json.loads(json.dumps(b['payload']));expected['presentation']['camera_deg']=-35
    assert c['payload']==expected
    widths=[]
    for part in ['shell-body','shell-cover','pcb']:
        values=[next(x for x in z['parts'] if x['id']==part)['size_mm'][0] for z in cad]
        assert abs(values[1]-values[0]-6)<.01 and values[1]==values[2]
        widths.append({'part':part,'widths_mm':values})
    controls={
        'physical_change_native_widths':widths,
        'physical_change_changes_geometry':a['hashes']['geometry_hash']!=b['hashes']['geometry_hash'],
        'physical_change_changes_physical':a['hashes']['physical_hash']!=b['hashes']['physical_hash'],
        'overall_bounds_unchanged':cad[0]['assembly_bounds']==cad[1]['assembly_bounds']==cad[2]['assembly_bounds'],
        'energy_identity_unchanged':len({x['hashes']['energy_hash'] for x in assemblies})==1,
        'camera_only_one_input_field_changed':True,
        'camera_geometry_physical_energy_unchanged':all(b['hashes'][k]==c['hashes'][k] for k in ['geometry_hash','physical_hash','energy_hash']),
        'camera_definition_changed':b['hashes']['definition_hash']!=c['hashes']['definition_hash'],
        'camera_cad_readback_byte_identical':digest(roots[1]/'cad-readback.json')==digest(roots[2]/'cad-readback.json'),
        'all_energy_result_bytes_identical':len({digest(p/'energy.json') for p in roots})==1,
        'camera_render_changed':digest(roots[1]/'preview.png')!=digest(roots[2]/'preview.png'),
        'unmasked_collision_audits_passed':True}
    assert all(v for v in controls.values())
    energy=read(roots[-1]/'energy.json')
    assert energy['calculation_passed'] and energy['scenarios']['normal']['accepted_events']>0
    trace=RUNTIME/'sessions'/owner/'trace.jsonl'
    result={'schema_version':'bf-independent-delivery-acceptance-v1','owner':owner,'accepted':True,
        'scope':'Pi-authored digital assembly and revisions with recorded coordinator feedback; not unassisted, hardware, PCB or firmware acceptance.',
        'stages':stages,'controls':controls,'ledger':ledger,'charged_usd_total':round(sum(x['charged_usd'] for x in ledger),9),
        'energy':{k:v for k,v in energy.items() if k!='scenarios'},
        'scenarios':{k:{n:v for n,v in x.items() if n!='samples'} for k,x in energy['scenarios'].items()},
        'operator_feedback':messages,'raw_trace':{'path':str(trace),'bytes':trace.stat().st_size,'sha256':digest(trace)},
        'historical_document_errata':'v13 document/proposal overstated footprint and misstated pulse/standoff coordinates; final v14 document and latest visible proposal supersede these. Old copies retained.',
        'unassisted_trial':False,'hardware_verified':False,'manufacturing_approved':False,'rsi_efficacy_claim':False,
        'camera_control_recomputes_native_outputs':True}
    (EVIDENCE/'independent-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def package_all_deliveries():
    """Package already accepted outputs, preserving the sealed reference archive."""
    import re
    report=Path(__file__).resolve().parents[1]/'docs/agentlab'
    accepted=json.loads((EVIDENCE/'independent-acceptance.json').read_text())
    assert accepted['accepted']
    ui=json.loads((EVIDENCE/'ui-independent-acceptance.json').read_text());assert ui['passed']
    reference=json.loads((EVIDENCE/'package-receipt-v5.json').read_text())
    ref=Path(reference['file']);assert hashlib.sha256(ref.read_bytes()).hexdigest()==reference['sha256']
    root=ref.parent/'five-deliveries-20260923';root.mkdir(exist_ok=False)
    target=ref.parent/'BF-AIoT-five-deliveries-20260923.zip'
    if target.exists():raise FileExistsError(target)
    def copy(src,rel):
        dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    copy(ref,'reference/'+ref.name)
    copy(report/'PRODUCT-DELIVERY.md','README.md')
    copy(report/'PRODUCT-DELIVERY.json','acceptance.json')
    owner=accepted['owner']
    for stage in accepted['stages']:
        prefix='independent/v'+str(stage['revision'])
        for p in (RUNTIME/'engineering'/stage['job']).iterdir():
            if p.suffix in ('.json','.blend','.glb','.step','.stl','.brep','.svg','.png','.py','.log'):
                copy(p,prefix+'/geometry/'+p.name)
        for f in stage['files']:
            copy(RUNTIME/'state/product-assemblies'/owner/'files'/f['id'],prefix+'/published/'+f['id'][:8]+'-'+f['name'])
    trace=Path(accepted['raw_trace']['path'])
    assert hashlib.sha256(trace.read_bytes()).hexdigest()==accepted['raw_trace']['sha256']
    # Do not distribute a raw trace if it unexpectedly contains a credential.
    raw=trace.read_text()
    if re.search(r'\bsk-[A-Za-z0-9_-]{20,}',raw):raise ValueError('TRACE_CREDENTIAL_REVIEW_REQUIRED')
    operator=(RUNTIME/'state/operator.token').read_text().strip()
    if operator in raw:raise ValueError('TRACE_CREDENTIAL_REVIEW_REQUIRED')
    copy(trace,'independent/trace.jsonl')
    copy(Path(__file__),'reproduction/product_delivery.py')
    for name in ['independent-acceptance.json','independent-baseline-accepted.json','change-controls.json','integrated-check-v5.json','archive-readback.json','init-release-final.log','chat-history-final.log','context-recovery-live.json','ui-independent-acceptance.json','ui-independent-check.cjs','ui-independent-model.png','ui-independent-trace.png','ui-independent-panorama.png','verify-glb.py','conversation-reload-receipt.json']:
        copy(EVIDENCE/name,'validation/'+name)
    for stage in accepted['stages']:
        copy(EVIDENCE/('glb-'+stage['job']+'.json'),'validation/glb-'+stage['job']+'.json')
    for stage in accepted['stages'][:2]:
        for name in ['input.json','cad-readback.json']:
            copy(EVIDENCE/('contacts-'+stage['job'])/name,'validation/unmasked-v'+str(stage['revision'])+'/'+name)
    with sqlite3.connect(RUNTIME/'state/workbench.sqlite') as db:
        db.row_factory=sqlite3.Row
        ledger=[dict(r) for r in db.execute('SELECT id,owner,created,status,charged,reserved,usage,error FROM model_requests WHERE owner IN (?,?) ORDER BY created',(owner,'pi-chat-cf37636f82c771a4'))]
    (root/'validation/model-ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
    (root/'verify-package.py').write_text('''import hashlib,json,zipfile\nfrom pathlib import Path\nr=Path(__file__).resolve().parent\nm=json.loads((r/'manifest.json').read_text())\nfor rel,x in m['files'].items():\n p=r/rel\n assert p.is_file() and p.stat().st_size==x['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],rel\nfor p in (r/'reference').glob('*.zip'):\n with zipfile.ZipFile(p) as z: assert z.testzip() is None\nprint('PASS: '+str(len(m['files']))+' files; sealed reference ZIP valid')\n''')
    files={str(p.relative_to(root)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.rglob('*')) if p.is_file()}
    manifest={'schema_version':'bf-five-deliveries-v1','scope':'Digital reference plus Pi-authored independent assembly with recorded coordinator review','hardware_verified':False,'manufacturing_approved':False,'files':files}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file():z.write(p,'BF-AIoT-five-deliveries/'+str(p.relative_to(root)))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for rel,x in files.items():assert hashlib.sha256(z.read('BF-AIoT-five-deliveries/'+rel)).hexdigest()==x['sha256']
    result={'file':str(target),'directory':str(root),'files':len(files),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'reference_unchanged':True}
    (EVIDENCE/'package-receipt-final.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def package_reference(model='eng-d981d142ab5766c1', revision=5):
    """Assemble actual source-bound artifacts, with a verifiable portable manifest."""
    live=json.loads((EVIDENCE/'live.json').read_text());owner=live['owner']
    pcb='eng-5a0b78aa90163b2f';sch='eng-b09b65a6e4b54b55'
    source=json.loads((RUNTIME/'engineering'/model/'input.json').read_text())['assembly']
    if source['revision']!=revision or source['owner']!=owner:raise ValueError('PACKAGE_SOURCE_MISMATCH')
    package=RUNTIME/'participants'/owner/'product-delivery'/('release-v'+str(revision));package.mkdir(parents=True,exist_ok=False)
    def copy(src,rel):
        target=package/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
    for p in (RUNTIME/'engineering'/model).iterdir():
        if p.suffix in ('.json','.blend','.glb','.step','.stl','.brep','.svg','.png','.py'):
            copy(p,'geometry/'+p.name)
    for name in ('project.epro2','gerber.zip','pcb-netlist.net','pcb.epro-source'):
        copy(RUNTIME/'engineering'/pcb/name,'electronics/'+name)
    for name in ('schematic-netlist.net','schematic.epro-source','bom.csv'):
        copy(RUNTIME/'engineering'/sch/name,'electronics/'+('native-bom-utf16.tsv' if name=='bom.csv' else name))
    native=list(csv.DictReader(io.StringIO((RUNTIME/'engineering'/sch/'bom.csv').read_text(encoding='utf-16')),delimiter='\t'))
    bom=[]
    for row in native:
        bom.append({'reference':row['Designator'],'quantity':row['Quantity'],'manufacturer':row['Manufacturer'],
                    'part':row['Manufacturer Part'],'value':row['Value'],'supplier':row['Supplier Part'],'basis':'native EDA library; availability not checked'})
    bom += [{'reference':ref,'quantity':str(n),'manufacturer':m,'part':part,'value':value,'supplier':supplier,'basis':basis} for ref,n,m,part,value,supplier,basis in [
        ('PV1',1,'PowerFilm','LL200-2.4-75','0.289mW at official 200lux point','','official datasheet'),
        ('SC1',1,'Eaton','KR-5R5H105-R','1F 5.5V','','official datasheet'),
        ('D1,D2',2,'Kingbright','WP710A10ID','red 3mm','C5831626','official envelope; low-current brightness unmeasured'),
        ('SW1',1,'XKB','TS-1088-AR02016','momentary switch','C720477','native catalog envelope')]]
    with (package/'electronics/BOM.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(bom[0]));w.writeheader();w.writerows(bom)
    for p in (RUNTIME/'participants'/owner/'product-delivery/firmware').rglob('*'):
        if p.is_file() and p.name!='logic-test':copy(p,'firmware/'+str(p.relative_to(RUNTIME/'participants'/owner/'product-delivery/firmware')))
    for name in ('circuit-pin-map.json','route-v5-rule.json','companion-v3.dsn','companion-v5.dsn','companion-v5.ses','pcb-width-corrected-native.json'):
        copy(EVIDENCE/name,'electronics/'+name)
    for name in ('integrated-check-v5.json','archive-readback.json','change-controls.json'):
        copy(EVIDENCE/name,'validation/'+name)
    (package/'source').mkdir(exist_ok=True)
    (package/'source/integrated-definition.json').write_text(json.dumps(source['payload'],ensure_ascii=False,indent=2))
    copy(RUNTIME/'engineering'/model/'energy.json','energy/energy.json')
    copy(Path(__file__).resolve().parents[1]/'docs/agentlab/PRODUCT-DELIVERY.md','README.md')
    (package/'verify-package.py').write_text('''import hashlib,json\nfrom pathlib import Path\nr=Path(__file__).resolve().parent\nm=json.loads((r/'manifest.json').read_text())\nfor p,x in m['files'].items():\n f=r/p\n assert f.is_file() and f.stat().st_size==x['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==x['sha256'],p\nprint('PASS: '+str(len(m['files']))+' immutable file hashes')\n''')
    files={str(p.relative_to(package)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in sorted(package.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    manifest={'schema_version':'bf-product-release-v1','owner':owner,'assembly_revision':revision,'model_job':model,
              'created_by':'operator-reference','hardware_verified':False,'manufacturing_approved':False,'files':files}
    (package/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    target=package.parent/('BF-Solar-Companion-digital-v'+str(revision)+'.zip')
    if target.exists():raise FileExistsError('PACKAGE_ALREADY_EXISTS')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,'BF-Solar-Companion/'+str(p.relative_to(package)))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for rel,item in files.items():assert hashlib.sha256(z.read('BF-Solar-Companion/'+rel)).hexdigest()==item['sha256']
    result={'file':str(target),'files':len(files),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (EVIDENCE/('package-receipt-v'+str(revision)+'.json')).write_text(json.dumps(result,indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parameters', type=Path)
    parser.add_argument('--operation')
    parser.add_argument('--engine', default='jlceda')
    parser.add_argument('--job')
    args = parser.parse_args()
    result = api('/api/engineering/jobs/'+args.job) if args.job else run(json.loads(args.parameters.read_text()), args.operation, args.engine)
    receipt(wait(result['id']))
