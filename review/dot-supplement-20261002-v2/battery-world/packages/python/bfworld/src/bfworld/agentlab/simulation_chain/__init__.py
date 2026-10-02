"""Agent-facing adapter; numerical dependencies stay in the isolated CAD runtime."""
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from .contracts import validate as validate_spec,ChainError,file_hash,digest
from ..runtime_config import CAD,HOME_ROOT,REPO

SCOPE='CAD尺寸→有限磁体/COMSOL依据→双向机电与原厂PMIC→共享C软件在环→虚拟接收。显式适用域、能量账、缓存、失败分类；不代表实物、完整SoC或RF仿真。'
SKILL='''# 全仿真候选入口
调用 bf_engineering run，engine=closed-simulation，parameters={"candidate":{},"confirmation":true}。
candidate允许 mechanical(gap_mm,opening_s,angle_deg,remanence_T,damping_ratio)、circuit(cin_uF,cout_uF,initial_vin_V,diagnostic_input_A)、firmware(interval_ms,boot_ms,init_ms,tx_ms,boot_mA,init_mA,tx_mA,sleep_uA,reset_uA)、link(loss_probability,seed,scan_duty)、solver和presentation(camera_deg)。省略项采用显式D2基线假设。
使用稳定operation_id，job查询Result。不同候选使用不同operation_id。同输入新job会验证并复用checkpoint；原job/失败/源文件不会覆盖。
区分run_status与design_status/predicted_design_status。out_of_domain不能当作不合格设计；numerical_fail不能用于优化排名。
design_status依据不足时必须保留原因，不得说产品完成。diagnostic_input_A或initial_vin_V非零仅为受控模块诊断，不能冒称动作自供电成功。
firmware在环是共享C状态逻辑，不是nRF52832完整二进制、SoftDevice或RF仿真。PGOOD不是电源开关。磁表外拒绝；超过8mm线性域拒绝。
Trace保留各stage输入/哈希/cache、实际COMSOL/LTspice文件，产品成果中查看waveform、energy、receiver、engineering-evidence.zip。
'''

def validate(parameters):
    if not isinstance(parameters,dict) or set(parameters)-{'candidate','confirmation'}:
        raise ValueError('SIMULATION_PARAMETERS_INVALID')
    if type(parameters.get('confirmation',True)) is not bool:raise ValueError('CONFIRMATION_BOOLEAN_REQUIRED')
    try:spec=validate_spec(parameters.get('candidate',{}))
    except ChainError as exc:raise ValueError(str(exc)) from exc
    return {'candidate':spec,'confirmation':parameters.get('confirmation',True)}

def template_hash():
    return digest({p.name:file_hash(p) for p in sorted(Path(__file__).parent.iterdir()) if p.suffix in ('.py','.c')})

def run(engine,job,directory,deadline):
    cache_root=(engine.store.root.parent/'studies/door-design-pilot-v1/agent-cache'/job['owner']) if job.get('task_binding') else HOME_ROOT/'simulation-chain/cache'
    args=[str(CAD),'-m','bfworld.agentlab.simulation_chain.cli','--input',str(directory/'input.json'),
          '--output',str(directory),'--cache',str(cache_root)]
    engine.event(job['owner'],job['id'],'process_start',{'transport':'cli','argv':args,'cwd':str(directory)})
    env={**os.environ,'PYTHONPATH':str(REPO/'packages/python/bfworld/src')}
    offset=0
    def ingest():
        nonlocal offset
        trace=directory/'trace.jsonl'
        if not trace.exists():return
        with trace.open() as f:
            f.seek(offset)
            for line in f:
                if not line.endswith('\n'):break
                data=json.loads(line);engine.event(job['owner'],job['id'],'simulation_'+data.pop('kind'),data)
                offset+=len(line.encode())
    with (directory/'process.log').open('ab') as log:
        process=subprocess.Popen(args,cwd=directory,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        engine.event(job['owner'],job['id'],'process_spawned',{'transport':'cli','pid':process.pid})
        try:
            while process.poll() is None:
                ingest()
                if time.monotonic()>deadline:raise TimeoutError('SIMULATION_CANDIDATE_TIMEOUT')
                time.sleep(.25)
            ingest()
        except BaseException:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise
    engine.event(job['owner'],job['id'],'process_end',{'transport':'cli','exit_code':process.returncode})
    if process.returncode or not (directory/'result.json').exists():raise RuntimeError('SIMULATION_RUNNER_FAILED')
    result=json.loads((directory/'result.json').read_text())
    result['_job_status']='SUCCEEDED' if result['run_status']=='completed' else 'FAILED'
    return result
