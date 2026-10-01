"""One candidate entry; durable native stages, evidence-bound outputs, bounded recovery."""
import fcntl
import json
import shutil
import time
import zipfile
import sys
import importlib.metadata
from pathlib import Path
from .contracts import VERSION,ChainError,digest,file_hash,physical_spec,validate,write_json
from .cache import Cache
from . import native,solver

STAGES=['cad','beam','force','firmware','joint','numerical','magnetic-confirmation']

def implementation():
    return {p.name:file_hash(p) for p in sorted(Path(__file__).parent.glob('*')) if p.suffix in ('.py','.c')}

def tool_identity():
    """Bind cache decisions to local executables and numerical library versions."""
    cc=shutil.which('cc')
    return {'pmic_model':file_hash(native.PMIC),'ltspice_launcher':file_hash(native.WINE),
        'ltspice_executable':file_hash(native.LTROOT/'support/ltspice/drive_c/Program Files/ADI/LTspice/LTspice.exe'),
        'comsol_launcher':file_hash(native.COMSOL),
        'comsol_binary':file_hash(native.COMSOL.parent/'macarm64/comsol'),
        'arm_compiler':file_hash(native.GCC),'host_compiler':file_hash(cc),
        'python':sys.version,'libraries':{name:importlib.metadata.version(name) for name in ('numpy','scipy','cadquery','matplotlib')}}

def compare(a,b):
    names=['peak_tip_mm','peak_piezo_V','peak_storage_V','peak_supply_V']
    relative={k:abs(a[k]-b[k])/max(abs(b[k]),1e-8) for k in names}
    return {'relative_deltas':relative,'same_packet_count':a['tx_completed']==b['tx_completed'],
            'passed':max(relative.values())<.05 and a['tx_completed']==b['tx_completed'],
            'tolerance':.05,'scope':'two max-step / tolerance / program-sampling levels, not a proof of global convergence'}

def _plot(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    a=np.genfromtxt(output/'waveform.csv',delimiter=',',names=True)
    fig,axes=plt.subplots(3,1,figsize=(10,7),sharex=True,layout='constrained')
    for ax,names,label in zip(axes,[['tip_m'],['piezo_V','storage_V'],['supply_V','pgood_V']],['Tip / m','Source / V','Program supply / V']):
        for name in names:ax.plot(a['time_s'],a[name],label=name,lw=1.2)
        ax.set_ylabel(label);ax.grid(alpha=.15);ax.legend(loc='upper right')
    axes[-1].set_xlabel('Time / s');fig.suptitle('Native coupled ROM + LTC3588-1 / shared C software-in-loop\nNominal simulation, not a hardware measurement',fontsize=11)
    fig.savefig(output/'preview.png',dpi=150);plt.close(fig)

def submit_candidate(candidate,output,cache_root,*,confirm=True,interrupt_after=None,event=None):
    """Returns Result even on bounded stage failure. Output must be a NEW run directory.

    Resume means invoking the same candidate with the same cache in a new run;
    completed checkpoints are reused after byte verification. Runs are never overwritten.
    """
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/'result.json').exists():raise ValueError('Immutable run output already exists')
    started=time.time();current='input';stages={};paths={};impl=implementation()
    result={'schema_version':'closed-simulation-result-v1','model_version':VERSION,'run_status':'input_error',
       'design_status':'insufficient_evidence','failed_stage':None,'unreached_stages':[],
       'model_versions':{},'applicability':{},'energy_ledger':{},'events':[],
       'product_verified':False,'hardware_calibrated':False,'stages':stages,
       'limitations':['Uniform hard-magnet force table; sparse FEM anchors do not confirm the entire rotated trajectory.',
        'Small-deflection static-condensed single-mode beam, no contact/nonlinear release/fatigue model.',
        'Shared C policy SIL with assumed timing/current; no nRF52 SoC, SoftDevice or RF emulation.',
        'Encrypted PMIC internal losses are not independently audited; mechanical/piezo port balance is checked.']}
    def emit(kind,data):
        row={'time':time.time(),'kind':kind,**data}
        with (output/'trace.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        if event:event(kind,data)
    cache=Cache(cache_root,emit)
    def stage(name,inputs,producer):
        nonlocal current
        current=name
        if time.time()-started>3600:raise ChainError('tool_fail','Candidate wall limit')
        p,value,key,hit=cache.stage(name,inputs,producer)
        stages[name]={'key':key,'cache_hit':hit,'status':'completed'};paths[name]=p
        result['model_versions'][name]=key
        if interrupt_after==name:raise ChainError('tool_fail','Injected checkpoint interruption after '+name)
        return value
    lock=None
    try:
        spec=validate(candidate);write_json(output/'design-spec.json',spec)
        # Operator tool identities and implementation are part of computational identity.
        tools=tool_identity()
        runtime={'python':tools['python'],'libraries':tools['libraries']}
        field_tool={k:tools[k] for k in ('comsol_launcher','comsol_binary')}
        result['physics_hash']=digest({'spec':physical_spec(spec),'implementation':impl,'tools':tools})
        result['presentation_hash']=digest(spec['presentation']);result['tools']=tools
        Path(cache_root).mkdir(parents=True,exist_ok=True);lock=(Path(cache_root)/'.lock').open('a')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise ChainError('tool_fail','Simulation cache busy') from exc
        mechanical=spec['mechanical'];builder=impl['native.py']
        geometry=stage('cad',{'gap_mm':mechanical['gap_mm'],'builder':builder,'runtime':runtime,
          'source':file_hash(native.REPO/'scripts/door_case/build_cad.py'),
          'definition':file_hash(native.REPO/'scripts/build_pluck_product.py'),
          'design':file_hash(native.REPO/'configs/reference_cases/door-magnetic-v1/design.json'),
          'cad_builder':file_hash(native.REPO/'packages/python/bfworld/src/bfworld/agentlab/engineering_templates/product_cad.py')},
          lambda d:native.cad(d,mechanical['gap_mm']))
        rom=stage('beam',{'source':file_hash(native.REPO/'configs/reference_cases/door-magnetic-v1/DoorBeam.java'),'builder':builder,'tool':field_tool},native.beam)
        force=stage('force',{'mechanical':{k:mechanical[k] for k in ['gap_mm','remanence_T']},'builder':builder,'runtime':runtime},lambda d:native.force_table(d,mechanical))
        firmware=stage('firmware',{'config':spec['firmware'],'builder':builder,'program':impl['program.c'],
           'receiver':file_hash(native.REPO/'scripts/pluck_receiver.py'),
           'compilers':{k:tools[k] for k in ('arm_compiler','host_compiler')}},lambda d:native.firmware(d,spec['firmware']))
        joint_inputs={'spec':physical_spec(spec),'dependencies':dict(result['model_versions']),'solver':impl['solver.py'],
                      'runtime':runtime,'tools':{k:tools[k] for k in ('pmic_model','ltspice_launcher','ltspice_executable')}}
        joint=stage('joint',joint_inputs,lambda d:solver.solve(d,spec,rom,paths['force']/'force-table.npz',paths['firmware']))
        result.update(metrics=joint,energy_ledger=joint['energy_ledger'])
        result['events']=json.loads((paths['joint']/'receiver.json').read_text())['events']
        for filename in ['waveform.csv','program.csv','receiver.json','energy.json','system.cir','coupling-iterations.json']:
            shutil.copy2(paths['joint']/filename,output/filename)
        shutil.copy2(paths['cad']/'assembly.step',output/'assembly.step')
        shutil.copy2(paths['firmware']/'program.c',output/'program.c');shutil.copy2(paths['firmware']/'policy.h',output/'policy.h')
        _plot(output)
        if not joint['numerical_energy_passed']:raise ChainError('numerical_fail','Mechanical/piezo energy residual >1%')
        checks={'energy_balance':True,'force_interpolation':force['max_interpolation_error_over_peak']<.05,
                'beam_mesh':rom['mesh_delta']<.05,'program_power_fixed_point':True}
        if confirm:
            finer=json.loads(json.dumps(spec));finer['solver']['max_step_s']/=2;finer['solver']['firmware_step_s']/=2;finer['solver']['reltol']/=2
            fine=stage('numerical',{'joint':stages['joint']['key'],'solver':impl['solver.py'],'settings':finer['solver']},
                lambda d:solver.solve(d,finer,rom,paths['force']/'force-table.npz',paths['firmware']))
            comparison=compare(joint,fine);write_json(output/'convergence.json',comparison);checks['time_step']=comparison['passed']
            if not comparison['passed']:raise ChainError('numerical_fail','Time-step/firmware-grid convergence failed')
            magnetic=stage('magnetic-confirmation',{'gap_mm':mechanical['gap_mm'],'br':mechanical['remanence_T'],
               'source':file_hash(native.REPO/'configs/reference_cases/door-magnetic-v1/DoorMagnetic.java'),'builder':builder,'tool':field_tool},
               lambda d:native.magnetic_confirmation(d,mechanical))
            shutil.copy2(paths['magnetic-confirmation']/'magnetic-confirmation.json',output/'magnetic-confirmation.json')
            checks['magnetic_mesh']=magnetic['mesh_delta']<.05;checks['magnetic_anchor_agreement']=magnetic['max_reference_error']<.1
        result['checks']=checks
        result['run_status']='completed'
        predicted='satisfied' if joint['cold_start_reached'] and joint['received_events']>=1 else 'unsatisfied'
        result['predicted_design_status']=predicted
        result['design_status']='insufficient_evidence'  # full-trajectory/model-sufficiency gates are still open
        result['module_diagnostic_passed']=joint['diagnostic_only'] and predicted=='satisfied' and checks['energy_balance'] and checks.get('time_step',False)
        result['unreached_stages']=[] if joint['tx_completed'] else ['powered-radio-completion','virtual-reception']
        result['applicability']={'force':force,'beam':rom['scope'],'sufficiency':'not qualified for full product acceptance',
            'full_rotated_FEM_coverage':False,'diagnostic_only':joint['diagnostic_only'],'confirmation_requested':confirm}
        result['numerical_checks_passed']=all(checks.values())
        result['summary_zh']=('受控输入模块诊断：电源、C程序、虚拟接收已贯通。' if joint['diagnostic_only'] and predicted=='satisfied' else
                              '本次联合仿真未达到冷启动/接收目标。' if predicted=='unsatisfied' else '本模型内达到接收目标，仍需确认模型充分性。')
        result['summary_zh']+=' 完整产品依据仍不足；详见适用范围与检查。'
    except Exception as exc:
        result.update(run_status=exc.status if isinstance(exc,ChainError) else 'tool_fail',failed_stage=current,error=str(exc),
                      unreached_stages=[s for s in STAGES if s not in stages and s!=current])
        emit('run_failed',{'stage':current,'status':result['run_status'],'error':str(exc)})
    finally:
        if lock is not None:fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    result['elapsed_s']=time.time()-started;result['implementation']=impl
    # Portable package preserves each checkpoint, sources, raw native outputs and hashes.
    if paths:
        with zipfile.ZipFile(output/'engineering-evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
            for stage_name,path in paths.items():
                for file in sorted(path.rglob('*')):
                    if file.is_file():z.write(file,stage_name+'/'+str(file.relative_to(path)))
        result['evidence_archive_sha256']=file_hash(output/'engineering-evidence.zip')
    result['artifacts']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':file_hash(p)} for p in sorted(output.iterdir()) if p.is_file()]
    write_json(output/'result.json',result);return result
