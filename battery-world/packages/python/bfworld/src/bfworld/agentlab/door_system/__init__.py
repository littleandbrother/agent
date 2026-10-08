"""Versioned door loading/release apparatus; the v1 apparatus remains sealed."""
from .contracts import normalize, template_hash, SCOPE
import json
from ..runtime_config import REPO

SKILL = '''# D4 机械加载—释放设计
使用 bf_engineering run，engine=door-system，parameters={"candidate":{},"confirmation":true}。
先用 bf_reference 搜索、获取、分段读取原论文和器件数据表；报告页码、节点、单位、任务同异条件。引用不能自动改变被冻结的模型假设。
候选只允许 mechanical.gap_mm、closed_dz_mm、polarity；circuit.cin_uF、cout_uF；firmware.interval_ms。任务、阻尼、Br、程序电流、接收条件、初始电储能、外加电流和数值规则均不可修改。
完整过程从65度远磁体平衡、零初始电储能开始，关门2秒、保持0.5秒、开门2秒、衰减2秒。任务为周期内至少一次正确运动通知，不能称作已正确识别开/关状态。
读取 design-spec.json、system-manifest.json、drive-ledger.json、waveform.csv、program.csv、receiver.json 和 result.json；使用 artifact_view 按通道/时间窗读取。真实 CAD 的驱动支架横向位置和磁极方向随候选改变。
原生成功、名义预测、物理充分性与制造放行分别报告。越过±8mm返回out_of_domain；不修改梁域或电流来制造通过。单个FEM锚点不证明整条轨迹；电阻筛选不是PMIC成功。
等待自己的job终态，保持operation_id；重启后先查询原job，禁止重复派发。候选预算结束后 submit 已运行候选及理由，可以如实提交失败。
同一C逻辑在主机与ARM编译，阶段电流仍是文献包络假设，目标硬件/射频/寿命未实测。图和文件数量不能当作自主复现百分比。
'''

def validate(parameters):
    if not isinstance(parameters,dict) or set(parameters)-{'candidate','confirmation'}: raise ValueError('DOOR_PARAMETERS_INVALID')
    if parameters.get('confirmation',True) is not True: raise ValueError('DOOR_CONFIRMATION_REQUIRED')
    candidate=parameters.get('candidate',{})
    if isinstance(candidate,dict) and candidate.get('schema_version')=='bf-door-system-design-v2':
        from .contracts import verify_design
        design=verify_design(candidate)
    else:design=normalize(candidate)
    return {'candidate':design,'confirmation':True}

def run(engine,job,directory,deadline):
    import sys
    args=['env','PYTHONPATH='+str(REPO/'packages/python/bfworld/src'),sys.executable,'-m','bfworld.agentlab.door_system.pipeline','--input',str(directory/'input.json'),'--output',str(directory)]
    engine.command(job['id'],job['owner'],args,directory,deadline)
    result=json.loads((directory/'result.json').read_text());result['_job_status']='SUCCEEDED' if result['run_status']=='completed' else 'FAILED'
    return result
