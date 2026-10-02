"""Operator-triggered, source-bound checks of the integrated digital product.

This records native rule checks and a real target build. It deliberately does
not assert electrical function, manufacturability, or hardware performance.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile
from .store import canonical, identity


def source_identity(text):
    # Export regenerates the header and viewport; physical primitives/rules stay.
    return identity([line for line in text.splitlines() if line and
                     json.loads(line.split('||', 1)[0]).get('type') not in ('DOCHEAD', 'CANVAS')])


def check_interfaces(payload, components, pin_nets, expected):
    normalized = lambda m: {r: {str(p): n or '' for p, n in pins.items()} for r, pins in m.items()}
    if normalized(pin_nets) != normalized(expected):
        raise ValueError('PRODUCT_PIN_MAP_MISMATCH')
    parts = {p['id']: p for p in payload['parts']}
    board = parts['main_pcb']['geometry']
    width, height = board['size_mm'][:2]
    bx, by, _ = board['center_mm']
    if set('pcb_'+c['ref'] for c in components) != {k for k in parts if k.startswith('pcb_')}:
        raise ValueError('PRODUCT_PCB_COMPONENT_SET_MISMATCH')
    for c in components:
        p = parts['pcb_'+c['ref']]['geometry']
        target = [c['x']*.0254-width/2+bx, c['y']*.0254-height/2+by]
        if any(abs(a-b)>.01 for a,b in zip(p['center_mm'][:2],target)) or p.get('rotation_deg',[0,0,0])[2] != c['rotation']:
            raise ValueError('PRODUCT_PCB_PLACEMENT_MISMATCH:'+c['ref'])
    # Explicit contract of the compiled STM32L031 fixture, not inferred from text.
    firmware_pins = {'6':'BUTTON','14':'LED_L_DRV','15':'LED_R_DRV','23':'SWDIO','24':'SWCLK'}
    if any(pin_nets.get('U2',{}).get(p)!=n for p,n in firmware_pins.items()):
        raise ValueError('PRODUCT_FIRMWARE_PIN_CONFLICT')
    if payload['energy']['pulse_ms'] != 100 or abs(payload['energy']['supply_v']-3)> .02:
        raise ValueError('PRODUCT_FIRMWARE_SERVICE_CONFLICT')
    return {'component_count':len(components),'pin_count':sum(len(x) for x in expected.values()),
            'placement_tolerance_mm':.01,'firmware_pins':firmware_pins}


def verify(assemblies, owner, body):
    current=assemblies.get(owner)
    if body['revision'] != current['revision']:
        raise ValueError('ASSEMBLY_REVISION_STALE')
    app=assemblies.app; eng=app.engineering
    jobs={}
    inputs={}
    for name, document, operation in [('pcb_check','pcb','check'),('sch_check','schematic','check'),
                                     ('pcb_export','pcb','export'),('sch_export','schematic','export')]:
        job=eng.get(owner,body[name])
        if job['status']!='SUCCEEDED' or job['engine']!='jlceda' or job['parameters']!={'operation':operation,'document':document}:
            raise ValueError('PRODUCT_NATIVE_JOB_INVALID:'+name)
        for artifact in job['result']['artifacts']:
            eng.artifact(owner,job['id'],artifact['name'])
        if operation=='check' and job['result'].get('drc',{}).get('raw') is not True:
            raise ValueError('PRODUCT_NATIVE_RULES_NOT_PASSED:'+name)
        jobs[name]=job;inputs[name]={'job_id':job['id'],'artifacts':job['result']['artifacts']}
    if len({j['binding']['project_uuid'] for j in jobs.values()})!=1:
        raise ValueError('PRODUCT_NATIVE_PROJECT_MISMATCH')
    for prefix,doc in [('pcb','pcb'),('sch','schematic')]:
        a=eng.artifact(owner,jobs[prefix+'_check']['id'],doc+'.epro-source').read_text()
        b=eng.artifact(owner,jobs[prefix+'_export']['id'],doc+'.epro-source').read_text()
        if source_identity(a)!=source_identity(b):
            raise ValueError('PRODUCT_NATIVE_EXPORT_CHANGED:'+doc)
    base=assemblies.store.root.parent/'participants'/owner
    def owned(rel):
        p=base/rel
        if Path(rel).is_absolute() or '..' in Path(rel).parts or p.is_symlink() or not p.resolve().is_relative_to(base.resolve()):
            raise PermissionError('PRODUCT_VERIFICATION_PATH_DENIED')
        return p
    pinfile=owned(body['pin_map_path']);expected=json.loads(pinfile.read_text())
    pcb=jobs['pcb_check']['result'];sch=jobs['sch_check']['result']
    interfaces=check_interfaces(current['payload'],pcb['components'],pcb['pin_nets'],expected)
    normalized=lambda m:{r:{p:n or '' for p,n in pins.items()} for r,pins in m.items()}
    if normalized(sch['pin_nets'])!=normalized(expected):raise ValueError('PRODUCT_SCHEMATIC_PIN_MAP_MISMATCH')
    inputs['pin_map']={'path':body['pin_map_path'],'sha256':hashlib.sha256(pinfile.read_bytes()).hexdigest()}
    firmware=owned(body['firmware_path'])
    sources=[p for p in firmware.rglob('*') if p.is_file() and 'build' not in p.relative_to(firmware).parts]
    if not sources or any(p.is_symlink() or not p.resolve().is_relative_to(firmware.resolve()) for p in sources):
        raise ValueError('PRODUCT_FIRMWARE_SOURCE_INVALID')
    inputs['firmware']={str(p.relative_to(firmware)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    key=identity({'physical_hash':current['hashes']['physical_hash'],'inputs':inputs})[:32]
    directory=assemblies.root/owner/'verifications'/key;directory.mkdir(parents=True,exist_ok=True)
    dest=directory/'firmware';dest.mkdir(exist_ok=True)
    for p in sources:
        target=dest/p.relative_to(firmware);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    # Always execute the installed builder, never a participant-authored Python script.
    builder=Path(__file__).with_name('engineering_templates')/'companion_build.py'
    (dest/'companion_build.py').write_bytes(builder.read_bytes())
    result=subprocess.run([sys.executable,str(dest/'companion_build.py')],capture_output=True,text=True,timeout=120)
    (directory/'build.log').write_text(result.stdout+'\n'+result.stderr)
    if result.returncode:raise ValueError('PRODUCT_TARGET_BUILD_FAILED')
    fw=json.loads((dest/'build/firmware-check.json').read_text())
    if not all(fw.get(k) is True for k in ('target_compiled','host_state_machine_tests_passed','memory_fit')):
        raise ValueError('PRODUCT_TARGET_CHECK_FAILED')
    archives={}
    for name in ('project.epro2','gerber.zip'):
        path=eng.artifact(owner,jobs['pcb_export']['id'],name)
        with zipfile.ZipFile(path) as z:
            if z.testzip():raise ValueError('PRODUCT_EXPORT_CORRUPT')
            archives[name]=z.namelist()
    if not all(name in archives['gerber.zip'] for name in ('Gerber_TopLayer.GTL','Gerber_BottomLayer.GBL','Gerber_BoardOutlineLayer.GKO','Drill_NPTH_Through.DRL')):
        raise ValueError('PRODUCT_GERBER_LAYERS_MISSING')
    report={'schema_version':'bf-integrated-digital-check-v1','id':key,'owner':owner,'revision':current['revision'],
        'physical_hash':current['hashes']['physical_hash'],'created':time.time(),'inputs':inputs,'interfaces':interfaces,
        'firmware':fw,'archives':archives,'checks':{'native_schematic_rules':True,'native_pcb_rules':True,
        'schematic_pcb_pin_map':True,'pcb_cad_placements':True,'firmware_pin_service_contract':True,
        'target_build_and_logic_tests':True,'native_export_archives':True},
        'hardware_verified':False,'manufacturing_approved':False,
        'scope':'Digital interfaces, native rules and target build only; not switching stability, EMI, energy measurements or physical assembly acceptance.'}
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    artifacts={str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    with assemblies.store.connect() as db:
        db.execute('INSERT OR REPLACE INTO assembly_verifications VALUES(?,?,?,?,?,?)',(owner,key,current['revision'],current['hashes']['physical_hash'],canonical(report),canonical(artifacts)))
    app.conversations.event(owner,'assembly-verification-'+key,{'type':'assembly_verification','id':key,'revision':current['revision'],'physical_hash':current['hashes']['physical_hash'],'checks':report['checks'],'hardware_verified':False})
    return report


def projection(assemblies,owner,current):
    with assemblies.store.connect() as db:rows=db.execute('SELECT * FROM assembly_verifications WHERE owner=?',(owner,)).fetchall()
    output=[]
    for row in rows:
        report=json.loads(row['report']);root=assemblies.root/owner/'verifications'/row['id']
        report['integrity']=all((root/p).is_file() and hashlib.sha256((root/p).read_bytes()).hexdigest()==digest for p,digest in json.loads(row['artifacts']).items())
        report['stale']=row['physical_hash']!=current['hashes']['physical_hash']
        output.append(report)
    return output
