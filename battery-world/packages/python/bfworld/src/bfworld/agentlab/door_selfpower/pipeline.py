"""Versioned D5 apparatus; immutable native runs and explicit qualification."""
import argparse
import errno
import json
import shutil
import time
import zipfile
from pathlib import Path
from ..door_system import native, model, pipeline as d4_pipeline, contracts as d4_contracts
from ..simulation_chain.contracts import ChainError, write_json, file_hash
from . import contracts, solver, extraction, firmware, ratings

MIN_FREE_BYTES=3*1024**3


def storage_observation(directory):
    p=Path(directory).resolve()
    while not p.exists():p=p.parent
    usage=shutil.disk_usage(p)
    return {'filesystem_path':str(p),'free_bytes':usage.free,'minimum_free_bytes':MIN_FREE_BYTES,
            'ready':usage.free>=MIN_FREE_BYTES,'observed_at':time.time()}


def failure_facts(exc):
    resource=isinstance(exc,OSError) and exc.errno in (errno.ENOSPC,errno.EDQUOT,errno.ENOMEM)
    return {'run_status':'environment_fail' if resource else getattr(exc,'status','tool_fail'),
            'error':str(exc),**({'os_errno':exc.errno,'failure_kind':'execution_resource','design_infeasible':False}
                              if resource else {})}


def reference_base(original):
    # D5 nests the unchanged D4 physical design; both references retain their
    # identity/frozen-value checks before any stage is reused. The coupled solve
    # and C program are always freshly executed below.
    if original.get('schema_version') in contracts.SCHEMAS:
        return contracts.verify_design(original)['base_design']
    return d4_contracts.verify_design(original)


def qualification(result):
    checks=result.get('checks',{})
    keys=('rom_domain','force_interpolation','energy_balance','drive_balance',
          'electrical_energy_lower_bound','component_ratings','program_power_fixed_point','time_step')
    eligible=result.get('run_status')=='completed' and all(checks.get(k) is True for k in keys)
    m=result.get('metrics',{})
    return {'nominal_prediction_eligible':eligible,
        'nominal_status':('satisfied' if m.get('cold_start_reached') and m.get('received_events',0)>=1
                          else 'unsatisfied') if eligible else 'not_evaluable',
        'physical_qualification':False,'fabrication_released':False,'hardware_verified':False,
        'reason':'Native finite model, powered behavioral MIC841 and assumed stage loads. Rotating FEM, full device loss/temperature, PCB, RF and hardware remain unqualified.'}


def confirmation_check(metrics,fine):
    """Agreement is meaningful only when the finer solve is itself eligible."""
    fine_checks={'rom_domain':fine.get('peak_tip_mm',float('inf'))<=8.,
                 'energy_balance':fine.get('numerical_energy_passed') is True,
                 'drive_balance':fine.get('drive_ledger',{}).get('numerical_passed') is True,
                 'electrical_energy_lower_bound':fine.get('energy_ledger',{}).get('energy_lower_bound_passed') is True,
                 'component_ratings':fine.get('ratings',{}).get('passed') is True,
                 'program_power_fixed_point':fine.get('coupling_converged') is True}
    step={'relative_storage_error':abs(metrics['peak_storage_V']-fine['peak_storage_V'])/max(fine['peak_storage_V'],1e-9),
          'relative_tip_error':abs(metrics['peak_tip_mm']-fine['peak_tip_mm'])/max(fine['peak_tip_mm'],1e-9),
          'TX_count_equal':metrics['tx_completed']==fine['tx_completed'],
          'RX_count_equal':metrics['received_events']==fine['received_events'],
          'coarse_s':5e-5,'fine_s':2.5e-5,'target':.01,'fine_checks':fine_checks}
    step['passed']=bool(max(step['relative_storage_error'],step['relative_tip_error'])<=.01
                        and step['TX_count_equal'] and step['RX_count_equal'] and all(fine_checks.values()))
    return step


def run(design,directory,*,source_reference=None,confirm=True,authority='unrecorded'):
    contracts.verify_design(design)
    directory=Path(directory)
    # Engineering may have already created input.json/log files, but no existing
    # stage or result can be overwritten, including a failed/partial candidate.
    if (directory/'design-spec.json').exists() or (directory/'joint').exists():
        raise ValueError('SELFPOWER_RUN_ALREADY_EXISTS')
    directory.mkdir(parents=True,exist_ok=True);started=time.time();source_hash=contracts.template_hash()
    write_json(directory/'design-spec.json',design)
    storage=storage_observation(directory)
    if not storage['ready']:
        result={'schema_version':'bf-door-selfpower-result-v1','rating_protocol':ratings.VERSION,'design_id':design['design_id'],
                'run_status':'environment_fail','error':'SELFPOWER_STORAGE_UNAVAILABLE','failure_kind':'execution_resource',
                'failed_stage':'preflight','storage':storage,'checks':{},'metrics':{},'model_calls':0,
                'scope':contracts.SCOPE,'execution_authority':authority,'operator_assisted':authority.startswith('operator'),
                'reference_reused':False,'source_stable':True,'elapsed_s':time.time()-started}
        result['qualification']=qualification(result)
        result['artifacts']=[{'name':'design-spec.json','bytes':(directory/'design-spec.json').stat().st_size,
                             'sha256':file_hash(directory/'design-spec.json')}]
        write_json(directory/'result.json',result)
        return result
    src=directory/'executor-source';src.mkdir()
    for folder in (Path(__file__).parent,Path(__file__).parent.parent/'door_system',Path(__file__).parent.parent/'simulation_chain'):
        target=src/folder.name;target.mkdir()
        for p in folder.glob('*'):
            if p.is_file() and p.suffix in ('.py','.c'):shutil.copy2(p,target/p.name)
    dependencies={str(p):file_hash(p) for p in (d4_pipeline.ROM_FILE,Path(extraction.PMIC),
       extraction.WORK/'reference-cases/door-selfpower-v1/sources/MMBT5551.spice.txt',
       extraction.WORK/'reference-cases/door-selfpower-v1/sources/MIC841-20005758A.pdf',
       Path(extraction.PMIC).parent.parent/'cmp/standard.bjt',
       Path(extraction.PMIC).parent.parent/'cmp/standard.dio',
       Path(extraction.PMIC).parent.parent/'cmp/standard.mos',
       Path(extraction.PMIC).parent.parent/'sym/PowerProducts/LTC3588-1.asy')}
    if design.get('gate_switch')=='Si2333CDS':
        for name,expected in (('Si2333CDS.spice.txt',contracts.SI2333_MODEL_HASH),
                              ('Si2333CDS.pdf',contracts.SI2333_DATASHEET_HASH)):
            path=extraction.SWITCH_SOURCE_ROOT/name
            if file_hash(path)!=expected:raise ChainError('input_error','Load switch source hash mismatch:'+name)
            dependencies[str(path)]=expected
    stages=[]
    result={'schema_version':'bf-door-selfpower-result-v1','rating_protocol':ratings.VERSION,'design_id':design['design_id'],'run_status':'running',
            'checks':{},'metrics':{},'model_calls':0,'scope':contracts.SCOPE,'failed_stage':None,
            'reference_reused':bool(source_reference),'operator_assisted':authority.startswith('operator'),
            'execution_authority':authority}
    def stage(name,fn):
        p=directory/name;p.mkdir();before=time.time();result['failed_stage']=name
        receipt=fn(p);entry={'stage':name,'elapsed_s':time.time()-before,'receipt':receipt}
        stages.append(entry);write_json(p/'stage-receipt.json',entry);return receipt
    try:
        if file_hash(d4_pipeline.ROM_FILE)!=d4_pipeline.ROM_HASH:
            raise ChainError('input_error','Sealed mechanical ROM changed')
        rom=json.loads(d4_pipeline.ROM_FILE.read_text());shutil.copy2(d4_pipeline.ROM_FILE,directory/'rom.json')
        base=design['base_design']
        if source_reference:
            ref=Path(source_reference);original=reference_base(json.loads((ref/'design-spec.json').read_text()))
            # Same actual mechanics, frozen model and task; storage/policy can
            # differ in a controlled electrical comparison. No cache success is
            # implied: every native solve below runs cold.
            for k in ('mechanical','frozen'):
                if base[k]!=original[k]:raise ChainError('input_error','Source reference mismatch: '+k)
            if file_hash(ref/'rom.json')!=d4_pipeline.ROM_HASH:raise ChainError('input_error','Reference ROM hash mismatch')
            for name in ('cad','force','firmware'):
                if not (ref/name).is_dir():raise ChainError('input_error','Reference missing '+name)
            shutil.copytree(ref/'cad',directory/'cad');shutil.copytree(ref/'force',directory/'force')
            stages.append({'stage':'cad/force','reference':str(ref),'reused':True,
                'force_sha256':file_hash(ref/'force/force-table.npz'),'cad_sha256':file_hash(ref/'cad/assembly.step')})
            domain=json.loads((directory/'force/force-domain.json').read_text())
        else:
            cad=stage('cad',lambda p:native.cad(p,base))
            if cad['collisions']:raise ChainError('out_of_domain','Native BREP interference')
            domain=stage('force',lambda p:model.force_table(p,base)[1])
        if not domain['interpolation_passed']:raise ChainError('numerical_fail','Magnetic interpolation failed')
        stage('firmware',lambda p:firmware.build(p,design))
        metrics=stage('joint',lambda p:solver.solve(p,design,rom,directory/'force/force-table.npz',directory/'firmware'))
        result['metrics']=metrics
        step={'passed':False,'not_run':True}
        if confirm:
            fine=stage('time-step',lambda p:solver.solve(p,design,rom,directory/'force/force-table.npz',directory/'firmware',max_step_scale=.5))
            step=confirmation_check(metrics,fine)
        write_json(directory/'time-step-check.json',step)
        result['checks']={'rom_domain':metrics['peak_tip_mm']<=8.,'force_interpolation':True,
            'energy_balance':metrics['numerical_energy_passed'],'drive_balance':metrics['drive_ledger']['numerical_passed'],
            'electrical_energy_lower_bound':metrics['energy_ledger']['energy_lower_bound_passed'],
            'component_ratings':metrics['ratings']['passed'],'program_power_fixed_point':True,'time_step':step['passed']}
        result['run_status']='completed';result['failed_stage']=None
    except Exception as exc:
        result.update(failure_facts(exc))
        partial=directory/'joint/provisional-solve.json'
        if partial.exists():result['provisional_observations']=json.loads(partial.read_text())
    stable=source_hash==contracts.template_hash() and all(file_hash(Path(p))==h for p,h in dependencies.items())
    result['source_stable']=stable
    if not stable:result['run_status']='input_error';result['error']='D5 source changed during run; retained, not admitted'
    for folder,names in [('joint',['waveform.csv','program.csv','receiver.json','energy.json','rating-check.json','gate-observation.json','drive-ledger.csv','drive-ledger.json','coupling-iterations.json','system.cir','system.log','provisional-solve.json','provisional-program.csv','provisional-waveform.csv']),
                         ('cad',['assembly.step','installation.step','d4-cad-receipt.json']),
                         ('firmware',['program.c','policy.h','build-receipt.json'])]:
        for name in names:
            p=directory/folder/name
            if p.exists():
                try:shutil.copy2(p,directory/name)
                except OSError as exc:result.update(failure_facts(exc));result['failed_stage']='artifact_finalization'
    result['qualification']=qualification(result);result['elapsed_s']=time.time()-started
    manifest={'schema_version':'bf-door-selfpower-manifest-v1','rating_protocol':ratings.VERSION,'design_id':design['design_id'],'revision':'D5',
        'executor_sha256':source_hash,'source_dependencies':dependencies,'stages':stages,
        'qualification':result['qualification'],'product_verified':False,
        'board_status':'D4 PCB does not implement D5 extractor/gate; stale and not fabrication-released.',
        'claim_boundary':contracts.SCOPE,
        'native_files':[{'path':str(p.relative_to(directory)),'bytes':p.stat().st_size,'sha256':file_hash(p)}
                        for p in directory.rglob('*.raw')],
        'native_archives':[{'path':str(p.relative_to(directory)),**json.loads(p.read_text())}
                           for p in directory.rglob('*.raw.archive.json')]}
    write_json(directory/'system-manifest.json',manifest)
    result['artifacts']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':file_hash(p)}
         for p in sorted(directory.iterdir()) if p.is_file() and p.name not in ('result.json','engineering-evidence.zip')]
    write_json(directory/'result.json',result)
    try:
        with zipfile.ZipFile(directory/'engineering-evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(directory.rglob('*')):
                if p.is_file() and p.suffix not in ('.raw','.gz','.xz','.mph','.zip','.dylib','.o','.pyc'):
                    z.write(p,p.relative_to(directory))
    except OSError as exc:
        result.update(failure_facts(exc));result['failed_stage']='evidence_packaging'
        result['qualification']=qualification(result);write_json(directory/'result.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();value=json.loads(a.input.read_text())
    authority='operator-engineering' if value.get('initiator')=='operator' else 'participant-native'
    print(json.dumps(run(value['parameters']['candidate'],a.output,authority=authority),ensure_ascii=False),flush=True)
