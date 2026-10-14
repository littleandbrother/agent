"""Append-only current qualification over immutable P01 system inputs.

Native execution is consumed, never dispatched here. Firmware public counterexamples
are the pinned P01 fault-check-005 host tests; original product gate scopes remain.
"""
import array
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

from ..store import identity
from .repository import file_hash
from .repository_contracts import check, fingerprint
from .repository_load import normalize_timeline, load_binding

VERSION = 'p01-system-independent-review-v2'
FIXTURES = Path(__file__).with_name('repository-review-fixtures.json')


def text(repo, ref):
    p=repo.root/'blobs'/ref['sha256']
    if file_hash(p)!=ref['sha256']:raise ValueError('VALIDATION_BLOB_CHANGED')
    return p.read_text()


def selected_job(repo, system, kind, manifest):
    """All sources actually submitted to the worker must equal current system bytes."""
    matches=[]
    for jid,record in system['jobs'].items():
        refs=record.get('artifacts',{})
        if 'input.json' not in refs or 'result.json' not in refs:continue
        request=json.loads(text(repo,refs['input.json']));result=json.loads(text(repo,refs['result.json']))
        if result.get('kind')!=kind:continue
        project=request.get('project',{});signature=identity(project)
        if signature!=request.get('project_sha256') or signature!=record.get('project_sha256') or signature!=result.get('project_sha256'):
            raise ValueError('SYSTEM_JOB_IDENTITY_CONFLICT')
        if not result.get('readback_passed'):raise ValueError('SYSTEM_JOB_READBACK_FAILED')
        if manifest not in system['files'] or json.loads(text(repo,system['files'][manifest]))!=project.get('manifest'):
            raise ValueError('SYSTEM_JOB_MANIFEST_CONFLICT: '+manifest)
        prefix=str(Path(manifest).parent)
        sources={}
        for path,source in project['sources'].items():
            logical=prefix+'/'+path;digest=hashlib.sha256(source.encode()).hexdigest()
            if system['files'].get(logical,{}).get('sha256')!=digest:
                raise ValueError('SYSTEM_JOB_CONSUMED_SOURCE_CONFLICT: '+logical)
            sources[logical]=digest
        archive_ref=refs.get('project-source.zip')
        if not archive_ref:raise ValueError('WORKER_SOURCE_ARCHIVE_REQUIRED')
        archive=repo.root/'blobs'/archive_ref['sha256']
        if file_hash(archive)!=archive_ref['sha256']:raise ValueError('WORKER_SOURCE_ARCHIVE_TAMPER')
        with zipfile.ZipFile(archive) as z:
            if json.loads(z.read('project.json'))!=project['manifest']:raise ValueError('WORKER_ARCHIVE_MANIFEST_CONFLICT')
            for path,source in project['sources'].items():
                if z.read(path)!=source.encode():raise ValueError('WORKER_COMPILED_SOURCE_CONFLICT: '+path)
        matches.append({'job_id':jid,'project_sha256':signature,'consumed_sources':sources,
                        'request':request,'result':result,'record':record})
    if len(matches)!=1:raise ValueError('EXACT_SYSTEM_JOB_REQUIRED: '+kind)
    return matches[0]


def firmware_review(repo, system, job):
    fixtures=json.loads(FIXTURES.read_text());sources=job['request']['project']['sources'];main=sources['main.c']
    start=main.index('{',main.index('case BLE_GATTS_EVT_HVN_TX_COMPLETE:'));depth=0;end=None
    for i in range(start,len(main)):
        depth+=int(main[i]=='{')-int(main[i]=='}')
        if depth==0:end=i+1;break
    if end is None:raise ValueError('FIRMWARE_EVENT_BRANCH_UNCLOSED')
    host=fixtures['host'].replace('BRIDGE_BODY',main[start:end])
    # Consume the actual configuration while keeping the original event requirements.
    config=re.search(r'static const app_cfg_t m_cfg\s*=\s*(\{.*?\});',main,re.S)
    if not config:raise ValueError('FIRMWARE_CONFIG_NOT_EXTRACTABLE')
    host=re.sub(r'const app_cfg_t m_cfg=\{.*?\};','const app_cfg_t m_cfg='+config[1]+';',host,count=1,flags=re.S)
    defines='\n'.join(line for line in main.splitlines() if line.startswith('#define APP_POLICY_'))
    host=defines+'\n#include "ad7156_nrf.h"\n'+host
    host=host.replace('app_tick(&m_app,&m_cfg,4999)','app_tick(&m_app,&m_cfg,m_cfg.sample_period_ms-1u)')
    host=host.replace('app_tick(&m_app,&m_cfg,5000)==APP_ACT_START_SAMPLE','app_tick(&m_app,&m_cfg,m_cfg.sample_period_ms)==APP_ACT_START_SAMPLE')
    host=host.replace('declared_five_second_sample_cadence','declared_sample_cadence')
    checks={};logs={}
    with tempfile.TemporaryDirectory(prefix='bf-v2-fault-') as directory:
        root=Path(directory)
        for name,source in sources.items():
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(source)
        extra={'independent_policy.c':host,'nrf_drv_twi.h':fixtures['mock'],
            'nrf_delay.h':'static inline void nrf_delay_ms(unsigned n){(void)n;}\n',
            'app_error.h':'/* fixed host mock */\n','app_util_platform.h':'#define APP_IRQ_PRIORITY_LOWEST 7\n',
            'independent_driver.c':fixtures['driver']}
        for name,source in extra.items():(root/name).write_text(source)
        for label,files in [('policy',['app_policy.c','independent_policy.c']),('driver',['ad7156_nrf.c','independent_driver.c'])]:
            compile_=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-I.',*files,'-o','replay-'+label],
                cwd=root,capture_output=True,text=True,timeout=30)
            logs[label+'-compile']=compile_.stdout+compile_.stderr
            if compile_.returncode:return {'status':'UNEVALUABLE','error':'PUBLIC_HOST_COMPILE_FAILED','logs':logs}
            run=subprocess.run([str(root/('replay-'+label))],cwd=root,capture_output=True,text=True,timeout=5)
            logs[label+'-run']=run.stdout+run.stderr
            if run.returncode:raise ValueError('PUBLIC_HOST_REPLAY_FAILED')
            checks.update({k:bool(int(v)) for k,v in (s.split('=') for s in run.stdout.splitlines())})
    if not checks:raise ValueError('EMPTY_FIRMWARE_CHECK_SELECTION')
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'logs':logs,
            'job_id':job['job_id'],'consumed_sources':job['consumed_sources'],'fixture_sha256':file_hash(FIXTURES),
            'scope':'actual policy, extracted HVN branch, AD7156 driver; fixed host bus mock'}


def power_review(repo, system, job, interface_result):
    params=json.loads(text(repo,system['files']['project-chain/interface-params.json']))
    timeline=normalize_timeline(json.loads(text(repo,system['files']['project-chain/load-timeline.json'])))
    circuit=job['request']['project']['sources'][job['request']['project']['manifest']['entrypoint']]
    match=re.search(r'Iload\s+mcu_rail\s+0\s+PWL\((.*?)\)',circuit,re.S|re.I)
    if not match:raise ValueError('UNSUPPORTED_LOAD_EXPRESSION')
    numbers=[float(v) for v in re.sub(r'^\s*\+',' ',match[1],flags=re.M).split()]
    times,currents=numbers[::2],numbers[1::2]
    if not times or len(times)!=len(currents) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('LOAD_PWL_TIME_INVALID')
    charge=sum((b-a)*(y+x)/2 for a,b,x,y in zip(times,times[1:],currents,currents[1:]))
    declared=timeline.get('window_charge_storage_rail_c')
    actual_pairs=list(map(list,zip(times,currents)))
    binding=load_binding(timeline,circuit,actual_pairs)
    pair_match=binding['pwl_equal']
    raw_ref=job['record']['artifacts'].get('project-trace.raw')
    if not raw_ref:raise ValueError('NATIVE_TRANSIENT_RAW_REQUIRED')
    raw=repo.root/'blobs'/raw_ref['sha256']
    if file_hash(raw)!=raw_ref['sha256']:raise ValueError('RAW_HASH_CONFLICT')
    header,payload=raw.read_bytes().split(b'Binary:\n',1)
    count=int(re.search(rb'No. Points:\s*(\d+)',header)[1]);width=int(re.search(rb'No. Variables:\s*(\d+)',header)[1])
    if len(payload)!=count*width*8 or count<2:raise ValueError('RAW_DIMENSION_CONFLICT')
    channels={m[2].decode():int(m[1]) for m in re.finditer(rb'^\s*(\d+)\s+(\S+)\s+\S+\s*$',header.split(b'Variables:')[-1],re.M)}
    values=array.array('d');values.frombytes(payload)
    if sys.byteorder!='little':values.byteswap()
    def series(name):return values[channels[name]::width]
    supply=series('v(supply_1v8)');storage=series('v(storage_rail)');mcu=series('v(mcu_rail)');clock=series('time')
    required=params['regulator']['v_out_v'];findings=[]
    radio=timeline['actual_radio_timing'];period_checks={}
    for label,expected in [('advertising',radio['advertising_period_ms']),('connection',radio['connection_period_ms_used'])]:
        starts=sorted(s['t0_s'] for s in timeline.get('segments',[]) if s.get('name','').lower().startswith(label))
        if len(starts)>1:
            period_checks[label]=all(abs((b-a)*1000-expected)<1e-5 for a,b in zip(starts,starts[1:]))
    samples=timeline.get('events_covered',{}).get('sample_and_notify_2byte_s',[])
    if len(samples)>1:period_checks['sampling']=all(abs((b-a)*1000-radio['sample_period_ms'])<1e-5 for a,b in zip(samples,samples[1:]))
    if not all(period_checks.values()):findings.append('load event cadence differs from actual firmware timing')
    if interface_result['status']!='PASS':findings.append('firmware activity and power declaration disagree')
    if binding['status']=='FAIL':findings.append('netlist load differs from the declared load witness')
    if declared is not None and abs(charge-declared)>max(1e-10,abs(charge)*1e-6):findings.append('load charge differs from timeline')
    if min(supply)<required-1e-6:findings.append('supply falls below the declared operating voltage')
    if min(mcu)<-1e-3:findings.append('manual admission produces a negative MCU rail')
    applicability={'status':'UNEVALUABLE','pending':params.get('unresolved_device_parameters',[])+params.get('sece',{}).get('unresolved',[])}
    status='FAIL' if findings else 'UNEVALUABLE'
    return {'status':status,'findings':findings,'model_applicability':applicability,'job_id':job['job_id'],
            'consumed_sources':job['consumed_sources'],'load_pwl_equal':pair_match,'load_binding':binding,'pwl_points':len(times),
            'evaluation_gaps':([binding['error']] if binding['status']=='UNEVALUABLE' else [])+(['declared Iload charge unavailable'] if declared is None else []),
            'event_cadence_checks':period_checks,
            'load_charge_c':charge,'declared_charge_c':declared,'raw_sha256':raw_ref['sha256'],
            'time_span_s':[clock[0],clock[-1]],'points':count,'storage_v':[storage[0],storage[-1]],
            'minimum_supply_v':min(supply),'minimum_mcu_v':min(mcu),
            'scope':'fixed nominal/manual-admission load and actual native transient; source calibration pending'}


def qualification(repo, system, db=None):
    if db is None:
        with repo.store.connect() as connection:return qualification(repo,system,connection)
    gates={k:{**v,'input_fingerprint':fingerprint(system,k)} for k,v in system.get('validations',{}).items()}
    # Newest evidence for the same source/contract/job fingerprint wins; history is retained.
    rows=[json.loads(r['value']) for r in db.execute('SELECT value FROM design_repository_validations WHERE project=? ORDER BY rowid',(system['project_id'],))]
    for record in rows:
        for gate,value in record['result'].get('gates',{}).items():
            if value.get('input_fingerprint')==fingerprint(system,gate):
                gates[gate]={**gates.get(gate,{}),**value,'validation_id':record['id'],'evidence_target':record['target']}
    required=repo.project(system['project_id'],db=db)['requirements']['required_gates']
    for g in required:gates.setdefault(g,{'status':'NOT_CHECKED','input_fingerprint':fingerprint(system,g)})
    status='PASS' if all(gates[g]['status']=='PASS' for g in required) else ('REPAIR_REQUIRED' if any(gates[g]['status']=='FAIL' for g in required) else 'CHECKS_PENDING')
    return {'schema_version':'bf-system-qualification-v1','system_commit':system['id'],'status':status,
            'gates':gates,'product_passed':status=='PASS','physical':'NOT_TESTED'}


def native_review_reuse(repo, system, gate, original=None):
    """Reuse sealed native checks only against their unchanged native consumers.

    A load-table change does not alter a saved PCB. The imported review remains
    authoritative for those native bytes, including its failures and missing data.
    """
    if original is None:
        origin=system.get('validations',{}).get(gate,{}).get('origin_design_id')
        if not origin:return None
        with repo.store.connect() as db:
            candidates=[json.loads(r['value']) for r in db.execute(
                'SELECT value FROM design_system_commits WHERE project=?',(system['project_id'],))]
        matches=[s for s in candidates if s.get('origin_design_id')==origin and s.get('parent') is None]
        if len(matches)!=1:raise ValueError('ORIGINAL_NATIVE_REVIEW_BASE_REQUIRED')
        original=matches[0]
    def relevant(path):
        native=path.startswith('public-round3-facts-20261014/') and (
            '/native-project/' in path or path.endswith(('PCB1.epcb2','-readback.json','native-parts-readback.csv')))
        return native or (gate=='schematic_bom_pins' and path=='docs/BOM-interfaces.md') or (
            gate=='geometry_fit' and (path.startswith('project-cad/') or path=='assembly.json'))
    before={p:r['sha256'] for p,r in original['files'].items() if relevant(p)}
    after={p:r['sha256'] for p,r in system['files'].items() if relevant(p)}
    if not before or before!=after:
        return {'status':'RECHECK_REQUIRED','changed_native_inputs':sorted(p for p in before.keys()|after.keys() if before.get(p)!=after.get(p))}
    path='public-round3-facts-20261014/independent-reviews/'+gate+'.json'
    ref=system['files'].get(path)
    if not ref or ref!=original['files'].get(path):raise ValueError('ORIGINAL_NATIVE_REVIEW_CHANGED')
    review=json.loads(text(repo,ref))
    if review.get('actor')!='independent-checker' or review.get('gate_id')!=gate:
        raise ValueError('ORIGINAL_NATIVE_REVIEW_IDENTITY_CONFLICT')
    for support in review.get('supporting_sources',[]):
        if after.get(support['path'])!=support['sha256']:
            raise ValueError('NATIVE_REVIEW_SOURCE_BINDING_CONFLICT')
    for bound in review.get('bindings',[]):
        record=system['jobs'].get(bound['job_id'],{})
        if record.get('project_sha256')!=bound['project_sha256']:
            raise ValueError('NATIVE_REVIEW_JOB_BINDING_CONFLICT')
        if gate=='geometry_fit':selected_job(repo,system,'cadquery','project-cad/project.json')
    for path in after:
        if file_hash(repo.root/'blobs'/after[path])!=after[path]:raise ValueError('NATIVE_REVIEW_INPUT_TAMPER')
    return {'status':review['status'],'exact_native_evidence_reuse':{
        'original_system':original['id'],'review_sha256':ref['sha256'],
        'inputs':after,'bindings':review.get('bindings',[])},'findings':review['findings'],
        'scope':'original independent native review on identical saved EDA/CAD inputs'}


def evaluate(repo, system):
    required=repo.project(system['project_id'])['requirements']['required_gates'];gates={}
    def record(gate,status,findings,scope):
        gates[gate]={'status':status,'findings':findings,'scope':scope,'input_fingerprint':fingerprint(system,gate)}
    interface=check(lambda p:text(repo,system['files'][p]),system['files'],
        {d:json.loads(text(repo,system['files']['interfaces/'+d+'.json'])) for d in ('power','firmware') if 'interfaces/'+d+'.json' in system['files']})
    jobs={};errors={}
    for domain,kind,manifest in [('firmware','firmware-nrf52832-s132','project-fw-s132/project.json'),('power','spice','project-chain/project.json')]:
        try:jobs[domain]=selected_job(repo,system,kind,manifest)
        except (ValueError,KeyError) as e:errors[domain]=str(e)
    # Carry exact unaffected original product checks; changed gates need fresh evidence.
    current=qualification(repo,system)
    for gate in required:
        if gate in ('firmware_event_logic','power_load_chain','source_domain','board_firmware_interfaces','delivery_version'):continue
        prior=current['gates'][gate]
        try: native=native_review_reuse(repo,system,gate)
        except (ValueError,KeyError) as e:native={'status':'UNEVALUABLE','error':str(e)}
        if native:
            record(gate,native['status'],native,native.get('scope','native review input binding'))
        else:
            record(gate,prior['status'],{'exact_reuse':{k:prior.get(k) for k in ('status','validation_id','evidence','origin_design_id')}} if prior['status']!='RECHECK_REQUIRED' else {'pending':'fresh native check for changed inputs'},'original P01 independent product gate')
    if 'firmware' in jobs:
        try:
            prior=current['gates'].get('firmware_event_logic',{})
            if prior.get('status')=='PASS' and prior.get('validation_id'):
                fw={'status':'PASS','exact_reuse_validation':prior['validation_id'],'scope':'exact validated firmware input reuse','consumed_sources':jobs['firmware']['consumed_sources']}
            else:fw=firmware_review(repo,system,jobs['firmware'])
            record('firmware_event_logic',fw['status'],fw,fw.get('scope','public host replay'))
        except (ValueError,KeyError,subprocess.TimeoutExpired) as e:record('firmware_event_logic','UNEVALUABLE',{'error':str(e)},'public host replay')
    else:record('firmware_event_logic','RECHECK_REQUIRED',{'error':errors.get('firmware')},'target/source binding')
    if 'power' in jobs:
        try:
            power=power_review(repo,system,jobs['power'],interface);record('power_load_chain',power['status'],power,power['scope'])
            record('source_domain',power['model_applicability']['status'],power['model_applicability'],'original source calibration and SECE applicability')
        except (ValueError,KeyError,IndexError) as e:
            record('power_load_chain','UNEVALUABLE',{'error':str(e)},'native transient and load binding')
            record('source_domain','UNEVALUABLE',{'error':str(e)},'source calibration')
    else:
        record('power_load_chain','RECHECK_REQUIRED',{'error':errors.get('power')},'power/source binding')
        record('source_domain','UNEVALUABLE',{'error':errors.get('power')},'source calibration')
    # Keep the original board audit requirements as well as the new timing contract.
    board=current['gates'].get('board_firmware_interfaces',{})
    record('board_firmware_interfaces','FAIL' if interface['status']=='FAIL' else 'UNEVALUABLE',
        {'timing_contract':interface,'prior_board_status':board.get('status'),'pending':['native PCB peripheral initialization and full pin/interface audit']},'native board and firmware interfaces')
    for ref in list(system['files'].values())+[r for j in system['jobs'].values() for r in j.get('artifacts',{}).values()]:
        if file_hash(repo.root/'blobs'/ref['sha256'])!=ref['sha256']:raise ValueError('REVIEW_MANIFEST_TAMPER')
    record('delivery_version','PASS' if not errors else 'FAIL',{'execution_bindings':{d:{k:v for k,v in j.items() if k not in ('request','result','record')} for d,j in jobs.items()},'errors':errors,'file_count':len(system['files'])},'current source and selected worker inputs; immutable review manifest')
    return {'checker':VERSION,'checker_sha256':file_hash(__file__),
            'load_checker_sha256':file_hash(Path(__file__).with_name('repository_load.py')),'fixture_sha256':file_hash(FIXTURES),
            'target':system['id'],'scope':'eight original P01 digital gates plus source timing contract',
            'interface':interface,'gates':gates,'status':'PASS' if all(gates[g]['status']=='PASS' for g in required) else 'FAIL',
            'native_jobs_dispatched':0,'physical':'NOT_TESTED'}
