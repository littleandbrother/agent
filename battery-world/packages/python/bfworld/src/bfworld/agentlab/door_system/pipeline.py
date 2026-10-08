"""Source-bound native D4 execution with full work ledger and independent checks."""
import argparse
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path
import numpy as np
from . import contracts, native, model, solver
from ..runtime_config import REPO
from ..simulation_chain.contracts import write_json, file_hash, ChainError

ROM_FILE=REPO/'configs/reference_cases/door-system-v3/rom.json'
ROM_HASH='854bd9eee771dc4136afd96b46d07d7864345d13343d4ffcca4189c9595735cf'

def qualification(result):
    numerical=('rom_domain','force_interpolation','energy_balance','drive_balance','program_power_fixed_point','time_step')
    eligible=result.get('run_status')=='completed' and all(result.get('checks',{}).get(k) is True for k in numerical)
    m=result.get('metrics',{})
    return {'nominal_prediction_eligible':eligible,
            'nominal_status':('satisfied' if m.get('cold_start_reached') and m.get('received_events',0)>=1 else 'unsatisfied') if eligible else 'not_evaluable',
            'physical_qualification':False,'fabrication_released':False,'hardware_verified':False,
            'reason':'Finite nominal-model confirmation; full rotating FEM grid, bracket/strain, RF, native EDA and physical validation remain separate.'}

def run(design,directory):
    contracts.verify_design(design);directory.mkdir(parents=True,exist_ok=True);started=time.time()
    source_hash=contracts.template_hash();src=directory/'executor-source';src.mkdir()
    for p in sorted(Path(__file__).parent.iterdir()):
        if p.suffix in ('.py','.c','.java'):shutil.copy2(p,src/p.name)
    shared_src=directory/'shared-source';shared_src.mkdir()
    for name in ('contracts.py','native.py','solver.py','program.c'):
        shutil.copy2(Path(__file__).parents[1]/'simulation_chain'/name,shared_src/name)
    dependency_paths=[REPO/'scripts/door_case/build_cad.py',REPO/'scripts/build_pluck_product.py',REPO/'packages/python/bfworld/src/bfworld/agentlab/engineering_templates/product_cad.py',ROM_FILE]
    dependency_paths += [Path(__file__).parents[1]/'simulation_chain'/name for name in ('contracts.py','native.py','solver.py','program.c')]
    dependencies={str(p.relative_to(REPO)):file_hash(p) for p in dependency_paths}
    write_json(directory/'design-spec.json',design)
    result={'schema_version':'bf-door-system-result-v1','design_id':design['design_id'],'run_status':'running',
            'checks':{},'metrics':{},'operator_assisted':False,'model_calls':0,'scope':contracts.SCOPE,'failed_stage':None}
    stages=[]
    def stage(name,func):
        path=directory/name;path.mkdir();before=time.time();result['failed_stage']=name
        value=func(path);entry={'stage':name,'elapsed_s':time.time()-before,'receipt':value};stages.append(entry)
        write_json(path/'stage-receipt.json',entry);return value
    try:
        if file_hash(ROM_FILE)!=ROM_HASH:raise ChainError('input_error','Sealed beam ROM changed')
        rom=json.loads(ROM_FILE.read_text());shutil.copy2(ROM_FILE,directory/'rom.json')
        cad=stage('cad',lambda p:native.cad(p,design))
        if cad['collisions']:raise ChainError('out_of_domain','D4 static CAD interference')
        force_domain=stage('force',lambda p:model.force_table(p,design)[1])
        if not force_domain['interpolation_passed']:raise ChainError('numerical_fail','Force interpolation gate')
        stage('firmware',lambda p:native.firmware(p,design))
        metrics=stage('joint',lambda p:solver.solve(p,native.solver_spec(design),rom,directory/'force/force-table.npz',directory/'firmware'))
        result['metrics']=metrics
        # Half maximum step is an independent operator confirmation, never an
        # Agent design knob or relaxation of the official candidate.
        refined=native.solver_spec(design);refined['solver']['max_step_s']/=2
        fine=stage('time-step',lambda p:solver.solve(p,refined,rom,directory/'force/force-table.npz',directory/'firmware'))
        time_check={'relative_peak_storage_difference':abs(metrics['peak_storage_V']-fine['peak_storage_V'])/max(fine['peak_storage_V'],1e-9),
                    'relative_tip_peak_difference':abs(metrics['peak_tip_mm']-fine['peak_tip_mm'])/max(fine['peak_tip_mm'],1e-9),
                    'tx_count_equal':metrics['tx_completed']==fine['tx_completed'],'received_count_equal':metrics['received_events']==fine['received_events'],
                    'official_max_step_s':5e-5,'confirmation_max_step_s':2.5e-5,'target':.01}
        time_check['passed']=bool(max(time_check['relative_peak_storage_difference'],time_check['relative_tip_peak_difference'])<=.01 and time_check['tx_count_equal'] and time_check['received_count_equal'])
        write_json(directory/'time-step-check.json',time_check)
        result['checks']={'rom_domain':metrics['peak_tip_mm']<=8,'force_interpolation':True,'energy_balance':metrics['numerical_energy_passed'],
                          'drive_balance':metrics['drive_ledger']['numerical_passed'],'program_power_fixed_point':metrics['coupling_converged'],
                          'time_step':time_check['passed'],'rotated_work_domain':False}
        result['run_status']='completed';result['failed_stage']=None
    except Exception as exc:
        result['run_status']=getattr(exc,'status','tool_fail');result['error']=str(exc)
    result['source_stable']=source_hash==contracts.template_hash() and all(file_hash(REPO/p)==h for p,h in dependencies.items())
    if not result['source_stable']:
        result['run_status']='input_error';result['error']='Executor changed during run; outputs retained, excluded from comparison'
    for folder,names in [('joint',['waveform.csv','program.csv','receiver.json','energy.json','drive-ledger.csv','drive-ledger.json','coupling-iterations.json','system.cir','system.log']),('cad',['assembly.step','installation.step','d4-cad-receipt.json']),('firmware',['program.c','policy.h','build-receipt.json'])]:
        for name in names:
            p=directory/folder/name
            if p.exists():shutil.copy2(p,directory/name)
    manifest={'schema_version':'bf-door-system-manifest-v1','design_id':design['design_id'],'revision':'D4','executor_sha256':source_hash,
              'source_rom_sha256':ROM_HASH,'source_dependencies':dependencies,'stages':stages,'qualification':qualification(result),
              'external_native_files':[{'path':str(p.relative_to(directory)),'bytes':p.stat().st_size,'sha256':file_hash(p)} for p in directory.rglob('*') if p.is_file() and p.suffix in ('.raw','.mph')],
              'product_verified':False,'claim_boundary':'CAD and solver inputs share a content-bound design; electronics board, RF and flash images require separate consistency checks.'}
    write_json(directory/'system-manifest.json',manifest);result['qualification']=manifest['qualification'];result['elapsed_s']=time.time()-started
    # The sealed result is part of the replay bundle. Its artifact list excludes
    # the bundle itself, avoiding a circular result/bundle content identity.
    result['artifacts']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':file_hash(p)} for p in sorted(directory.iterdir()) if p.is_file() and p.name not in ('result.json','engineering-evidence.zip')]
    write_json(directory/'result.json',result)
    # Large native data stay separately hash-addressed. Outer job completion,
    # not elapsed_s, measures archival and user-visible turnaround.
    with zipfile.ZipFile(directory/'engineering-evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and p.suffix not in ('.raw','.mph','.zip','.dylib','.o','.pyc'):z.write(p,p.relative_to(directory))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    incoming=json.loads(a.input.read_text());print(json.dumps(run(incoming['parameters']['candidate'],a.output),ensure_ascii=False),flush=True)
