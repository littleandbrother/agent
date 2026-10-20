"""Reconcile the recorded ENOSPC incident from retained bytes; zero solver calls."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import zlib

APP=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(APP/'scripts'))
from bf_v2_environment import environment
from v2_common import RUNTIME, action


def read(path):return json.loads(path.read_text())


def main():
    profile,env=environment(RUNTIME)
    executable=profile['paths']['CAD_PYTHON']
    if Path(sys.executable).resolve()!=Path(executable).resolve():
        os.execve(executable,[executable,str(Path(__file__).resolve())],env)
    os.environ.update(env)
    from bfworld.agentlab.design_lab.contracts import sealed
    from bfworld.agentlab.design_lab.native_slot import native_slot
    from bfworld.agentlab.simulation_chain.solver import read_raw
    from bfworld.agentlab.store import identity
    root=RUNTIME/'continuous-design/reconciliation';root.mkdir(parents=True,exist_ok=True)
    if (root/'result.json').exists():print((root/'result.json').read_text());return
    repo=RUNTIME/'workbench/design-lab/repository'
    key='b2532fe28603223f3e6723897f9a38915bde9b30171d350fb99dd280c2d04c9f'
    native=repo/'feedback-native-cache'/key
    execution=repo/'task-executions/PR-dd2754776accc058195516d558979d27fd4267282ae13b5bc005f6e815de11ec/EX-a736b3f4907b54b1b17ba8565551c9d3dd4a03dafee654de5e30adc6a3a04010'
    owner='pi-chat-c5de1eb091037bf4'
    if action(owner,'repository_state')['status']!='IDLE':raise ValueError('INCIDENT_OWNER_NOT_IDLE')
    dispatch=read(execution/'dispatch.json')
    if dispatch['system_id']!='SC-aa2253b78d4fd121d10e7e7d03549eeb00ff53a41a4569eb31de8231a4ae2fc1':
        raise ValueError('INCIDENT_SYSTEM_CHANGED')
    with native_slot():
        marker=read(native/'dispatch.json');netlist=(native/'system.cir').read_text()
        if key!=identity({'netlist':netlist,'tools':marker['tools'],'reader':inspect.getsource(read_raw)}):
            raise ValueError('INCIDENT_NATIVE_INPUT_CHANGED')
        log=(native/'system.log').read_text()
        if 'Total elapsed time:' not in log or 'Fatal' in log:raise ValueError('NATIVE_NOT_COMPLETED')
        raw=native/'system.raw';sha=hashlib.sha256(raw.read_bytes()).hexdigest()
        t,_=read_raw(raw,20)
        partial=[]
        for path in execution.glob('*/iterations.json'):
            for item in read(path):
                if not item['native']['reused']:partial.append(item['native']['key'])
        partial=list(dict.fromkeys([*partial,key]))
        proof={'system':dispatch['system_id'],'native_key':key,'raw_sha256':sha,
            'native_time_start':float(t[0]),'native_time_end':float(t[-1]),'native_samples':len(t),
            'retained_partial_native_dispatches':partial,'new_native_solves':0,
            'outer_execution':'INCOMPLETE_AFTER_ENOSPC','original_trial_result_preserved':True}
        sealed(root/'proof.json',proof)
        if not (native/'completed.json').exists():
            compressed=zlib.compress(raw.read_bytes(),6)
            if hashlib.sha256(zlib.decompress(compressed)).hexdigest()!=sha:raise ValueError('RAW_COMPRESSION_CHANGED')
            destination=native/'system.raw.zlib'
            if destination.exists() and destination.stat().st_size:raise ValueError('COMPRESSED_OUTPUT_ALREADY_EXISTS')
            temporary=native/'system.raw.zlib.recovered';temporary.write_bytes(compressed)
            os.replace(temporary,destination)
            outputs={name:hashlib.sha256((native/name).read_bytes()).hexdigest()
                     for name in ('system.cir','system.log','launcher.log','system.raw.zlib')}
            sealed(native/'completed.json',{'key':key,'status':'SUCCEEDED','outputs':outputs})
        if hashlib.sha256(zlib.decompress((native/'system.raw.zlib').read_bytes())).hexdigest()!=sha:
            raise ValueError('RECOVERED_NATIVE_READBACK_CHANGED')
    # The interrupted coupled iteration did not finish. Register that failure,
    # preserving the original operation ID, rather than rerunning the candidate.
    metrics={'error':'OPERATOR_CONFIRMED_INCOMPLETE_AFTER_ENOSPC','kind':'execution_failure',
        'native_dispatches':partial,'reconciliation':proof,'new_native_solves':0}
    sealed(execution/'failure.json',metrics)
    ref=hashlib.sha256((execution/'failure.json').read_bytes()).hexdigest()
    sealed(execution/'completed.json',{'descriptor':dispatch['descriptor'],'status':'FAILED',
        'metrics':metrics,'outputs':{'failure.json':{'sha256':ref}}})
    result=action(owner,'repository_task_execute',project_id=execution.parent.name,
        system_id=dispatch['system_id'],operation_id='op-exe-rev1')
    sealed(root/'result.json',{'proof':proof,'registered_execution':result,
        'new_model_requests':0,'new_native_solves':0})
    print(json.dumps({'status':result['status'],'execution':result['id'],
        'partial_native_dispatches':len(partial),'new_native_solves':0}))


if __name__=='__main__':main()
