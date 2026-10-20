"""Source-bound digital realization of a feedback node, using the existing journal.

This consumer reads a completed execution. It never launches a physics solver.
Engineering views, native outputs and reports retain their source identities.
"""
import csv
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ..store import canonical, identity
from .contracts import sealed
from .repository import file_hash, name
from .repository_task_execution import current_execution
from .repository_task_reports import report_font

MANIFEST = 'notes/engineering-realization.json'
VERSION = 'bf-node-realization-v1'


def specification():
    return {'schema_version': VERSION, 'manifest_path': MANIFEST,
        'required': {'schema_version': VERSION,
            'mechanical': {'clamp_length_mm': '5..20', 'base_thickness_mm': '2..8',
                'board_size_mm': '[width 30..100, height 20..100, thickness 0.8..2.4] mm',
                'board_origin_mm': '[x >= -clamp_length, y >= beam_width+5, z >=3] mm; lower-left-bottom corner',
                'coordinate_system': 'x: free beam 0..length; y: beam 0..width; z: substrate bottom 0. Clamp extends x=-clamp_length..0; free length is unchanged.',
                'motion_clearance_mm': '1..10 mm added beyond measured peak displacement; do not estimate or include peak displacement again'},
            'target': {'module': 'E73-2G4M04S1B', 'mcu': 'nRF52832-QFAA',
                'pgood_gpio': 'P0.11', 'sensing': 'internal TEMP',
                'protocol': 'BLE manufacturer data', 'supply_v': 2.5},
            'judgment': 'design decisions and task scope in Chinese',
            'assumptions': ['unmeasured current, module/assembly assumptions'],
            'issues': ['remaining concrete engineering work']},
        'operation': 'task_realize(system_id,operation_id) reads the frozen manifest, completed converged execution and native attachments; returns views and portable handoff. No new simulation.',
        'identity': 'System Commit + exact execution + manifest + generators + native receipts',
        'target_sources': 'notes/target/main.c, notes/target/sdk_config.h, notes/target/custom_board.h; fixed nRF5 SDK/S132 build only',
        'board_facts': {'PMIC': 'D1=GND, D0=VIN2 hardwired, 2.5V; neither pin is connected to MCU',
            'module': 'E73 module includes 32MHz/32.768kHz crystals and DEC decoupling; LFRC is a supported deliberate clock choice',
            'PGOOD': 'module physical pin27=P0.11; do not invent a software D0/D1 interface',
            'SAADC': 'VDD internal input; configured gain/reference/resolution determine conversion. Validate these against nRF52832 PS.',
            'reference': 'reference currents are task scenario declarations; nominal waves are simulation, not measurements'}}


def validate_manifest(value, design):
    if value.get('schema_version') != VERSION: raise ValueError('NODE_MANIFEST_VERSION')
    def number(x): return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    mechanical = value['mechanical']; target = value['target']
    for field, low, high in [('clamp_length_mm', 5, 20), ('base_thickness_mm', 2, 8), ('motion_clearance_mm', 1, 10)]:
        x = mechanical.get(field)
        if not number(x) or not low <= x <= high: raise ValueError('NODE_GEOMETRY_RANGE:'+field)
    for field in ('board_size_mm', 'board_origin_mm'):
        if not isinstance(mechanical.get(field), list) or len(mechanical[field]) != 3 or not all(number(x) for x in mechanical[field]):
            raise ValueError('NODE_GEOMETRY_VECTOR:'+field)
    w, h, thickness = mechanical['board_size_mm']
    x, y, z = mechanical['board_origin_mm']
    if not (30 <= w <= 100 and 20 <= h <= 100 and .8 <= thickness <= 2.4 and z >= 3):
        raise ValueError('NODE_BOARD_SIZE: width 30..100, height 20..100, thickness 0.8..2.4 mm; board origin z>=3 mm. Read task_schema.engineering_realization for coordinates.')
    # Side-by-side mounting leaves the active beam and its whole swept volume free.
    if y < design['width_m']*1000 + 5 or x < -mechanical['clamp_length_mm']:
        raise ValueError('NODE_BOARD_BEAM_INTERFERENCE: beam y=0..width, free x=0..length; board lower corner y>=beam width+5 mm, x>=-clamp length. Clamp does not shorten free beam.')
    expected = {'module':'E73-2G4M04S1B','mcu':'nRF52832-QFAA','pgood_gpio':'P0.11',
                'sensing':'internal TEMP','protocol':'BLE manufacturer data','supply_v':2.5}
    if target != expected: raise ValueError('NODE_TARGET_ADAPTER_UNSUPPORTED')
    for field in ('assumptions', 'issues'):
        if not isinstance(value.get(field), list) or any(not isinstance(v, str) or not v.strip() for v in value[field]):
            raise ValueError('NODE_TEXT_LIST:'+field)
    if not isinstance(value.get('judgment'), str) or not value['judgment'].strip(): raise ValueError('NODE_DESIGN_REASON_REQUIRED')
    return value


def bound_read(repo, system, path):
    ref = system['files'].get(path)
    if not ref: raise ValueError('NODE_SOURCE_REQUIRED:'+path)
    source = repo.root/'blobs'/ref['sha256']
    if file_hash(source) != ref['sha256']: raise ValueError('NODE_SOURCE_TAMPER')
    return source.read_text()


def timeline(repo, system, execution, folder):
    import numpy as np
    from .feedback_native import waveform
    refs = execution['artifacts']
    def raw(path): return (repo.root/'blobs'/refs[path]['sha256']).read_bytes()
    convergence = json.loads(raw('fine/convergence.json'))
    if convergence.get('converged') is not True or not execution['metrics'].get('converged'): raise ValueError('NODE_CONVERGED_EXECUTION_REQUIRED')
    with tempfile.TemporaryDirectory(prefix='bf-node-wave-') as tmp:
        root = Path(tmp); (root/'system.raw.zlib').write_bytes(raw('fine/system.raw.zlib'))
        t, signals = waveform(root, system['task_definition']['scenario']['duration_s'])
    from .feedback_native import coefficients
    design = json.loads(bound_read(repo, system, 'design.json'))
    stiffness = coefficients(design, system['task_definition']['scenario'])['stiffness_n_m']
    # LTspice retains the two nodes separately. Their voltage difference is
    # spring force in the force/voltage analogy, so divide by stiffness.
    displacement = (signals['v(spring)'] - signals['v(coupling)']) / stiffness
    signals['displacement_m'] = displacement
    rows = list(csv.DictReader(io.StringIO(raw('fine/program.csv').decode())))
    events = json.loads(raw('fine/events.json'))
    indices = {0, len(t)-1}
    # Min/max in every bin preserve narrow supply dips; exact event bounds are added.
    for bucket in np.array_split(np.arange(len(t)), 1500):
        if not len(bucket): continue
        indices.add(int(bucket[0])); indices.add(int(bucket[-1]))
        for key in ('v(vin)','v(out)','v(pgood)','i(bload)','displacement_m'):
            indices.add(int(bucket[np.argmin(signals[key][bucket])]))
            indices.add(int(bucket[np.argmax(signals[key][bucket])]))
    for event in events:
        for at in (event['t_s'], event['t_s']+event['duration_s']):
            k = int(np.searchsorted(t, at))
            indices.update(range(max(0,k-1), min(len(t),k+2)))
    take = np.array(sorted(indices))
    compressed = [{'t_s':float(t[i]), 'vin_v':float(signals['v(vin)'][i]),
        'vout_v':float(signals['v(out)'][i]), 'pgood_v':float(signals['v(pgood)'][i]),
        'current_a':float(signals['i(bload)'][i]), 'displacement_mm':float(displacement[i]*1000)} for i in take]
    # Persist state transitions rather than an unrelated hand-drawn state machine.
    transitions = []; previous = None
    for row in rows:
        state = tuple(row[k] for k in ('powered','boot','state','seq'))
        if state != previous:
            transitions.append({k:float(v) for k,v in row.items()}); previous = state
    value = {'execution_id':execution['id'], 'execution_origin':{'project_id':execution['project_id'],'system_id':execution['target']},
        'system_id':system['id'], 'converged':True, 'sources':{k:refs['fine/'+k] for k in ('system.raw.zlib','program.csv','events.json','convergence.json')},
        'duration_s':float(t[-1]), 'points':compressed, 'transitions':transitions, 'events':events,
        'peak_motion_mm':float(max(abs(displacement))*1000),
        'display_sampling':'1500 bins, each channel extrema + event boundaries; raw waves remain authoritative'}
    (folder/'timeline.json').write_text(canonical(value))
    return value


def native_bundle(repo, system):
    """Operator-imported native receipts are immutable, scoped to design+manifest."""
    pin = repo.root/'node-native'/system['id']/'manifest.json'
    if not pin.is_file(): return None
    value = json.loads(pin.read_text())
    if value.get('system_id') != system['id']: raise ValueError('NODE_NATIVE_SYSTEM_MISMATCH')
    if value.get('design_sha256') != system['files']['design.json']['sha256'] or value.get('manifest_sha256') != system['files'][MANIFEST]['sha256']:
        raise ValueError('NODE_NATIVE_INPUT_MISMATCH')
    for logical, ref in value['files'].items():
        name(logical)
        if file_hash(repo.root/'blobs'/ref['sha256']) != ref['sha256']: raise ValueError('NODE_NATIVE_TAMPER')
    return value


def import_native(repo, owner, body, source):
    """Import a saved native project and its measured readback at one revision."""
    source=Path(source).resolve(); receipt=json.loads((source/'receipt.json').read_text())
    project=repo.leader(body['project_id'],owner); system=repo.system(project['id'],body['system_id'])
    if system['task_definition'].get('phase')!='node-engineering-realization': raise ValueError('NODE_ENGINEERING_PHASE_REQUIRED')
    expected={'system_id':system['id'],'project_id':project['id'],
        'design_sha256':system['files']['design.json']['sha256'],'manifest_sha256':system['files'][MANIFEST]['sha256']}
    if any(receipt.get(k)!=v for k,v in expected.items()): raise ValueError('NODE_NATIVE_INPUT_MISMATCH')
    required={'project.epro2','schematic.svg','pcb.svg','pcb-bottom.svg','schematic-readback.json',
        'pcb-readback.json','pcb-dump.json','pcb-tracks.json','pcb-vias.json','pcb-drc.json','bom.csv','geometry.json'}
    if not required.issubset(receipt.get('files',{})): raise ValueError('NODE_NATIVE_FILES_REQUIRED')
    for logical,ref in receipt['files'].items():
        name(logical);path=source/logical
        if path.is_symlink() or not path.is_file() or file_hash(path)!=ref['sha256']: raise ValueError('NODE_NATIVE_TAMPER')
    import zipfile
    with zipfile.ZipFile(source/'project.epro2') as archive:
        if archive.testzip() is not None: raise ValueError('NODE_NATIVE_ARCHIVE_INVALID')
        documents=set()
        if 'project2.json' not in archive.namelist(): raise ValueError('NODE_NATIVE_ARCHIVE_PROJECT_REQUIRED')
        for path in archive.namelist():
            if path.endswith('.epru'):
                for line in archive.read(path).decode('utf-8').splitlines():
                    if not line.startswith('{"type":"DOCHEAD"'): continue
                    head=json.loads(line.split('||',1)[1].rstrip('|'))
                    documents.add((head.get('docType'),head.get('uuid')))
        if not {('SCH_PAGE',receipt['schematic_document']),('PCB',receipt['pcb_document'])}.issubset(documents):
            raise ValueError('NODE_NATIVE_ARCHIVE_DOCUMENT_MISMATCH')
    def result(logical):
        value=json.loads((source/logical).read_text())
        if value.get('context',{}).get('projectUuid')!=receipt['native_project_uuid']: raise ValueError('NODE_NATIVE_PROJECT_MISMATCH')
        if value.get('ok') is not True: raise ValueError('NODE_NATIVE_READ_FAILED')
        return value['result']
    schematic=result('schematic-readback.json'); pcb=result('pcb-readback.json');drc=result('pcb-drc.json')
    parts={c['designator']:c for c in schematic['components'] if c.get('designator')}
    board={c['designator']:c for c in pcb['components'] if c.get('designator')}
    if set(parts)!=set(board) or set(board)!={'U1','U2','C1','C2','C3','C4','C5','L1','J1','J2'}: raise ValueError('NODE_NATIVE_PART_SET')
    for ref,part in parts.items():
        if not part.get('uniqueId') or part.get('uniqueId')!=board[ref].get('uniqueId'): raise ValueError('NODE_NATIVE_PART_IDENTITY:'+ref)
        sch={str(p['pinNumber']):p.get('net') or '' for p in part['pins']}
        pads={str(p['padNumber']):p.get('net') or '' for p in board[ref]['pads']}
        if sch!=pads: raise ValueError('NODE_NATIVE_PIN_NET_MISMATCH:'+ref)
    expected_nets={'U1':{'1':'PZ_IN','2':'GND','3':'CAP','4':'VIN','5':'SW','6':'VDD_2V5','7':'VIN2','8':'GND','9':'VIN2','10':'PGOOD','11':'GND'},
        'U2':{'17':'VDD_2V5','27':'PGOOD','38':'SWDCLK','39':'SWDIO','37':'RESET'},
        'J2':{'1':'VDD_2V5','2':'GND','3':'SWDCLK','4':'SWDIO','5':'RESET'}}
    for ref,required in expected_nets.items():
        actual={str(p['pinNumber']):p.get('net') for p in parts[ref]['pins']}
        if any(actual.get(pin)!=net for pin,net in required.items()): raise ValueError('NODE_NATIVE_INTERFACE_WIRING:'+ref)
    geometry=json.loads((source/'geometry.json').read_text())
    engineering=json.loads(bound_read(repo,system,MANIFEST))
    if geometry['board_size_mm']!=engineering['mechanical']['board_size_mm']: raise ValueError('NODE_NATIVE_BOARD_SIZE')
    outline=json.loads((source/'pcb-dump.json').read_text())['outline']['points']
    size=[(max(p[i] for p in outline)-min(p[i] for p in outline))*.0254 for i in (0,1)]
    if any(abs(a-b)>1e-4 for a,b in zip(size,geometry['board_size_mm'])): raise ValueError('NODE_NATIVE_OUTLINE_SIZE')
    if {p['ref'] for p in geometry['components']}!=set(board): raise ValueError('NODE_NATIVE_GEOMETRY_PART_SET')
    def apply(db):
        value={**receipt,'files':{logical:repo.asset(db,source/logical,ref['sha256']) for logical,ref in receipt['files'].items()},
            'pin_net_match':True,'native_drc_passed':drc['passed'],'geometry':geometry}
        sealed(repo.root/'node-native'/system['id']/'manifest.json',value)
        return {'id':'NN-'+identity(value),'system_id':system['id'],'project_id':project['id'],
            'part_count':len(board),'pin_net_match':True,'native_drc_passed':drc['passed']}
    return repo.mutate(owner,body,apply)


def target_build(repo, system, folder):
    from .. import nordic_sdk
    from ..engineering_projects import sandbox
    paths = ['main.c','sdk_config.h','custom_board.h']
    if not all('notes/target/'+p in system['files'] for p in paths):
        return {'status':'MISSING_TARGET_SOURCES','scope':'target hardware port'}
    source=folder/'target-source'; source.mkdir(exist_ok=True)
    out=folder/'target'; out.mkdir(exist_ok=True)
    sources={p:bound_read(repo,system,'notes/target/'+p) for p in paths}
    for p, text in sources.items(): (source/p).write_text(text)
    project={'manifest':{'entrypoint':'main.c','files':paths,'interfaces':{
        'units':'SI','target':'nRF52832-QFAA','sdk':'17.1.0_ddde560','softdevice':'S132-7.2.0','board':'CUSTOM'}},'sources':sources}
    # A retained failed build is rebuilt in its own output tree.
    import shutil
    shutil.rmtree(out/'objects',ignore_errors=True)
    commands,reads,metadata,stack,notices=nordic_sdk.prepare_build(project,source,out,folder)
    # This fixed node has no serial or BSP interface. The general SDK builder
    # inherits ble_app_uart's unit list; its legacy UART header is not guarded
    # when UART is disabled. Do not compile unused example adapters.
    omitted={'nrf_drv_uart.c','nrfx_uart.c','nrfx_uarte.c','app_uart_fifo.c','retarget.c',
        'bsp.c','bsp_btn_ble.c','boards.c','ble_nus.c',
        'SEGGER_RTT.c','SEGGER_RTT_Syscalls_GCC.c','SEGGER_RTT_printf.c',
        'nrf_log_backend_rtt.c','nrf_log_backend_serial.c','nrf_log_default_backends.c',
        'nrf_log_frontend.c','nrf_log_str_formatter.c','ble_conn_state.c',
        'ble_conn_params.c','ble_link_ctx_manager.c','nrf_ble_gatt.c','nrf_ble_qwr.c',
        'ble_advertising.c','nrfx_twim.c','nrfx_twi.c','nrf_drv_twi.c','nrfx_saadc.c',
        'nrfx_timer.c','nrfx_spim.c','nrf_drv_spi.c','nrfx_spi.c'}
    removed=set(); filtered=[]
    for command in commands:
        if '-c' in command and Path(command[command.index('-c')+1]).name in omitted:
            removed.add(str(command[command.index('-o')+1])); continue
        filtered.append(command)
    commands=[[arg for arg in command if str(arg) not in removed] for command in filtered]
    metadata['node_omitted_example_units']=sorted(omitted)
    metadata['command_argv']=[[str(arg) for arg in command] for command in commands]
    metadata['portable_roots']={'bundle':str(folder),'sdk':str(nordic_sdk.SDK),'compiler_bin':str(nordic_sdk.GCC9.parent)}
    policy=sandbox([folder,*reads],out)
    env={'PATH':str(nordic_sdk.GCC9.parent)+':/usr/bin:/bin','HOME':str(out),'TMPDIR':str(out),'LANG':'C'}
    with (folder/'target-build.log').open('w') as log:
        failed=0
        for command in commands:
            if failed and '-c' not in command: break
            result=subprocess.run(['/usr/bin/sandbox-exec','-p',policy,*[str(x) for x in command]],
                cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
            failed=failed or result.returncode
        if failed:
            log.flush()
            lines=(folder/'target-build.log').read_text().splitlines()
            diagnostics=list(dict.fromkeys(line for line in lines if 'error:' in line or 'undefined reference' in line))
            return {'status':'BUILD_FAILED','log':'target-build.log','code':failed,
                'diagnostics':diagnostics[-40:],'log_tail':'\n'.join(lines[-35:])}
    (out/'softdevice.hex').write_bytes(stack.read_bytes())
    result=nordic_sdk.inspect(out/'firmware.elf',out/'firmware.hex',out/'softdevice.hex')
    nordic_sdk.merged_hex(nordic_sdk.ihex(out/'firmware.hex'),nordic_sdk.ihex(out/'softdevice.hex'),out/'combined.hex')
    (out/'vendor-license.txt').write_bytes(notices.read_bytes())
    (source/'build-apparatus.json').write_text(canonical(metadata))
    (out/'readback.json').write_text(canonical(result))
    return {'status':'BUILT',**result}


def current(repo, system):
    pointer=repo.root/'node-realizations/by-system'/(system['id']+'.json')
    if not pointer.is_file(): return None
    pin=json.loads(pointer.read_text()); folder=repo.root/'node-realizations'/pin['id']
    value=json.loads((folder/'manifest.json').read_text())
    if identity(value)!=pin['sha256'] or value['system_id']!=system['id']: raise ValueError('NODE_REALIZATION_IDENTITY')
    if value['input']['sources'] != system['files']: raise ValueError('NODE_REALIZATION_SOURCE_CHANGED')
    from .repository_validation import qualification
    if value['input'].get('qualification_sha256')!=identity(qualification(repo,system)): return None
    for logical,ref in value['outputs'].items():
        if file_hash(folder/logical)!=ref['sha256']: raise ValueError('NODE_REALIZATION_OUTPUT_CHANGED')
    return value


def realize(repo, owner, body):
    from .repository_validation import qualification
    from .report_runtime import report_python
    p=repo.leader(body['project_id'],owner); system=repo.system(p['id'],body['system_id'])
    if system['task_definition']['case_adapter']!='piezo-feedback-v1': raise ValueError('NODE_FEEDBACK_PROFILE_REQUIRED')
    if system['task_definition'].get('phase')!='node-engineering-realization': raise ValueError('NODE_ENGINEERING_PHASE_REQUIRED')
    design=json.loads(bound_read(repo,system,'design.json'))
    manifest=validate_manifest(json.loads(bound_read(repo,system,MANIFEST)),design)
    execution=current_execution(repo,system)
    if not execution or execution['status']!='SUCCEEDED': raise ValueError('NODE_COMPLETED_EXECUTION_REQUIRED')
    native=native_bundle(repo,system)
    modules=[Path(__file__),Path(__file__).with_name('repository_node_cad.py'),Path(__file__).with_name('repository_node_report.py')]
    app=Path(__file__).parents[7]/'apps/agent-studio'
    generator_files=[*modules,Path(__file__).with_name('repository_node_rebuild.py'),
        app/'model-viewer.js',*[app/('node-engineering.'+suffix) for suffix in ('html','css','js')]]
    report_deps=repo.root.parents[2]/'node-engineering/report-deps'
    if not (report_deps/'svglib').is_dir(): raise ValueError('NODE_REPORT_DEPENDENCIES_MISSING')
    checked=qualification(repo,system)
    inputs={'system_id':system['id'],'sources':system['files'],'execution_id':execution['id'],'qualification_sha256':identity(checked),
        'native':native,'generators':{m.name:file_hash(m) for m in generator_files},'font':report_font(),
        'report_dependencies':{str(f.relative_to(report_deps)):file_hash(f) for f in report_deps.rglob('*.py')}}
    rid='NR-'+identity(inputs); folder=repo.root/'node-realizations'/rid
    folder.mkdir(parents=True,exist_ok=True)
    import fcntl
    with (folder/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not (folder/'manifest.json').exists():
            sealed(folder/'input.json',inputs)
            (folder/'design.json').write_text(canonical(design)); (folder/'engineering.json').write_text(canonical(manifest))
            (folder/'qualification.json').write_text(canonical(checked))
            wave=timeline(repo,system,execution,folder)
            request={'design':design,'manifest':manifest,'peak_motion_mm':wave['peak_motion_mm'],
                'native_geometry':native['geometry'] if native else None}
            (folder/'cad-input.json').write_text(canonical(request))
            cad=Path(os.environ.get('CAD_PYTHON',str(Path.home()/'.local/share/bf-agent-runtime/product-cad/bin/python')))
            completed=subprocess.run([str(cad),str(modules[1]),str(folder)],capture_output=True,text=True,timeout=90)
            (folder/'cad-build.log').write_text(completed.stdout+completed.stderr)
            if completed.returncode: raise ValueError('NODE_CAD_BUILD_FAILED:'+completed.stderr[-500:])
            target=target_build(repo,system,folder); (folder/'target-status.json').write_text(canonical(target))
            if target['status']!='BUILT':
                return repo.mutate(owner,body,lambda db:{'id':rid,'system_id':system['id'],
                    'target_status':target['status'],'target':target,'new_physics_solves':0})
            if not native:
                return repo.mutate(owner,body,lambda db:{'id':rid,'system_id':system['id'],
                    'target_status':'BUILT','target':target,'native':False,'status':'WAITING_NATIVE_BINDING','new_physics_solves':0})
            if native:
                for logical,ref in native['files'].items():
                    dest=folder/'native'/logical; dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_bytes((repo.root/'blobs'/ref['sha256']).read_bytes())
                (folder/'native/receipt.json').write_text(canonical(native))
            # The handoff contains original source/trace inputs, not local-only paths.
            reference=folder/'reference';reference.mkdir(exist_ok=True)
            for logical in ('fine/system.raw.zlib','fine/system.cir','fine/program.csv','fine/events.json','fine/convergence.json','source-model.json'):
                ref=execution['artifacts'][logical]
                path=repo.root/'blobs'/ref['sha256']
                if file_hash(path)!=ref['sha256']: raise ValueError('NODE_REFERENCE_ARTIFACT_CHANGED')
                (reference/Path(logical).name).write_bytes(path.read_bytes())
            (reference/'main.c').write_text(bound_read(repo,system,'firmware/main.c'))
            (folder/'system.json').write_text(canonical(system))
            (folder/'rebuild-target.py').write_bytes(Path(__file__).with_name('repository_node_rebuild.py').read_bytes())
            env={**os.environ,'PYTHONPATH':os.pathsep.join([str(Path(__file__).parents[3]),str(report_deps)])}
            completed=subprocess.run([report_python(),'-m',__package__+'.repository_node_report',str(folder)],env=env,
                capture_output=True,text=True,timeout=90)
            if completed.returncode: raise ValueError('NODE_REPORT_FAILED:'+completed.stderr[-1000:])
            outputs={str(f.relative_to(folder)):{'sha256':file_hash(f),'bytes':f.stat().st_size}
                for f in folder.rglob('*') if f.is_file() and f.name not in ('lock','manifest.json','handoff.zip')}
            import zipfile
            with zipfile.ZipFile(folder/'handoff.zip','w',zipfile.ZIP_DEFLATED) as archive:
                for logical in outputs: archive.write(folder/logical,logical)
                archive.writestr('checksums.json',canonical(outputs))
            outputs['handoff.zip']={'sha256':file_hash(folder/'handoff.zip'),'bytes':(folder/'handoff.zip').stat().st_size}
            sealed(folder/'manifest.json',{'id':rid,'system_id':system['id'],'execution_id':execution['id'],
                'input':inputs,'outputs':outputs,'target':target,'native':native is not None,'new_physics_solves':0})
        value=json.loads((folder/'manifest.json').read_text())
        pointer=repo.root/'node-realizations/by-system'/(system['id']+'.json'); pointer.parent.mkdir(exist_ok=True)
        pointer.write_text(canonical({'id':rid,'sha256':identity(value)}))
    current(repo,system)
    return repo.mutate(owner,body,lambda db:{'id':rid,'system_id':system['id'],'execution_id':execution['id'],
        'outputs':value['outputs'],'target_status':value['target']['status'],'native':value['native'],'new_physics_solves':0})
