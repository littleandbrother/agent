"""D5 self-powered extraction and energy-ready application environment."""
from .contracts import normalize, verify_design, template_hash, SCOPE, SCHEMA, SCHEMAS
import json
from pathlib import Path
from ..runtime_config import REPO
from ..runtime_config import HOME_ROOT, configured
from ..simulation_chain.contracts import file_hash

# Operator-controlled durable evidence storage can live outside a cloud-backed
# Documents folder. Participants cannot change this process configuration.
REFERENCE_ROOT=configured('DOOR_SELFPOWER_ROOT',HOME_ROOT/'reference-cases/door-selfpower-v1')

SKILL='''# D5 自供能提取与负载门控
调用bf_engineering run，engine=door-selfpower，parameters={"candidate":{},"confirmation":true}。
先用bf_reference搜索和获取ViPSN-Pluck、2025统一仿真论文、LTC3588-1与MIC841数据表；核对节点、器件、电容、极性、初始储能与完整启动负载。参考原图与实际原生网表，不直接把论文数值当成本产品测量。
同一D4梁、磁体、完整门动作与程序负载。只允许 mechanical、circuit、firmware 中原D4设计变量，加 extraction={topology:direct/seh/psshi/sece,envelope_pF:68/100/220/470/680/1000/3000,diodes:BAT46WJ/BAS21HY}，gate=off/reserve-5v5/reserve-5v5-3v0/reserve-e96-6v1/reserve-e96-6v3/reserve-e96-6v3-2v96/reserve-6v5/reserve-8v0，application={packet_policy:one-shot/beacon}。不得修改阻尼、剩磁、电流、任务、数值规则、初始储能或注入外电源。完整BOOT53.8ms/INIT13ms/TX5ms保持；应用计时采用整数微秒以消除浮点累计多执行一拍的问题，固定100us采样和完整负载不变。PGOOD限定初始化入口，实际供电低于1.8V仍复位并丢弃未完成发送；one-shot不是免启动、跨重启恰好一次或实物功耗证明。
提取使用非理想器件；线圈绑定7447471471实际数据表。MIC841L低储能时输出高、关断PMOS，高储能时输出低、开启PMOS；逻辑和推挽输出为明确的有供电行为近似，真实分压、IQ、输出上下管和PMOS损耗进入原生供电网络。reserve-e96-6v1绑定1.74M/634k/604k三只真实阻值，对应6.113775/2.982811V；reserve-e96-6v3绑定1.78M/619k/590k，对应6.281966/3.065641V；reserve-e96-6v3-2v96绑定1.74M/665k/590k，对应6.294576/2.959203V。L推挽输出没有N开漏版本的470k上拉支路，输出级仍从VOUT供电并记录损耗。模型变化有新版本；D4结果与板子不能自动升级成D5。
可选gate_switch=BSS84/Si2333CDS。BSS84旧设计保持v1身份；Si2333CDS采用原厂三引脚非线性子电路，绑定模型及数据表SHA，形成v2设计，在door-selfpower-nominal-v2/v3/v4任务允许。先用独立有外电源夹具验证低压压降；它不是自供能成功。真实供电、门控损耗、电压上限和完整程序负载均保留。
任务door-selfpower-nominal-v3继承v2固定条件，另允许真实E96分压选项reserve-e96-5v43-2v98（1.74M/562k/681kΩ）；该选项仍须通过完整联合计算与半步长检查，不代表已验证成功。不得修改求解积分方式、放宽精度或把未收敛TX记为通过。
任务v4另允许reserve-e96-5v16-2v98（1.74M/523k/715kΩ）。gate-observation.json分别记录整体VIN峰值、监控器已供电时的VIN/控制峰值和实际接通时间；早于监控器供电的峰值不表示门控已能触发。工具返回观测事实，任务成功仍由完整验收决定。
任务v5绑定bf-component-rating-v2：分别检查2N5401集电极电流与电感峰值/RMS，BAT46WJ的2.5A单次浪涌不得用作重复脉冲依据。BAT46WJ-3P仅允许SECE，在六处功率支路各安装三只BAT46WJ与各自0.22Ω均流电阻；共20只二极管，模型按每个真实支路保存电流。只达到250mA逐支路保守筛选不代表容差、热、PCB与硬件资格。v1-v4旧任务不能接收v2判据的新结果。
读取result、energy、rating-check、drive-ledger、waveform、program、receiver、coupling-iterations、system-manifest。失败时读取provisional-solve、provisional-program、provisional-waveform；这些是未收敛观察，不能作为任务成功。使用artifact_view按channels、time_from、time_to、offset分页读取关键时间窗，先定位供电下降和程序状态，避免把整个RAW或工程包放进上下文。必须检查名义评价资格、固定点、器件额定值和步长确认；仅VIN升高不算任务成功。越域与数值失败不是器件不可行。nominal satisfied仍不代表物理充分性、制造或烧录完成。完整原生RAW无损保存为标准XZ（旧记录为gzip），恢复命令与原始SHA留在归档回执中。
保持operation_id，等待原job终态，重启先查询；不重复派发。保持引用来源和实际产物哈希。D5原理图/PCB需一致性检查，旧D4板标记stale。可以提交实算失败及局限，不虚构成功。
'''


def validate(parameters):
    if not isinstance(parameters,dict) or set(parameters)-{'candidate','confirmation'}:
        raise ValueError('SELFPOWER_PARAMETERS_INVALID')
    if parameters.get('confirmation',True) is not True:raise ValueError('SELFPOWER_CONFIRMATION_REQUIRED')
    c=parameters.get('candidate',{})
    design=verify_design(c) if isinstance(c,dict) and c.get('schema_version') in SCHEMAS else normalize(c)
    return {'candidate':design,'confirmation':True}


def reference_ready():
    """No Agent on D5 until an independently checked no-Agent reference passes."""
    root=REFERENCE_ROOT
    try:
        receipt=json.loads((root/'qualified-reference.json').read_text())
        p=Path(receipt['result_path']).resolve()
        if not p.is_relative_to(root.resolve()):return False
        value=json.loads(p.read_text())
        audit_path=Path(receipt['audit_path']).resolve()
        if not audit_path.is_relative_to(root.resolve()) or file_hash(audit_path)!=receipt['audit_sha256']:return False
        audit=json.loads(audit_path.read_text())
        if audit.get('passed') is not True or audit.get('cold_repeat',{}).get('passed') is not True:return False
        runs=audit.get('runs',[])
        if len(runs)!=2 or len({r['path'] for r in runs})!=2:return False
        for r in runs:
            rp=(Path(r['path'])/'result.json').resolve()
            if not rp.is_relative_to(root.resolve()) or file_hash(rp)!=r['result_sha256']:return False
            if r['passed'] is not True or r['executor_sha256']!=template_hash() or r['design_id']!=value['design_id']:return False
        manifest=json.loads((p.parent/'system-manifest.json').read_text())
        if not all(Path(dp).is_file() and file_hash(Path(dp))==dh for dp,dh in manifest['source_dependencies'].items()):return False
        return (file_hash(p)==receipt['result_sha256'] and receipt['executor_sha256']==template_hash()
                and value['qualification']['nominal_prediction_eligible'] is True
                and value['qualification']['nominal_status']=='satisfied'
                and value['model_calls']==0 and value.get('execution_authority') in ('operator-reference','operator-engineering')
                and value['source_stable'] is True)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return False


def run(engine,job,directory,deadline):
    import sys
    args=['env','PYTHONPATH='+str(REPO/'packages/python/bfworld/src'),sys.executable,
          '-m','bfworld.agentlab.door_selfpower.pipeline','--input',str(directory/'input.json'),'--output',str(directory)]
    engine.command(job['id'],job['owner'],args,directory,deadline)
    result=json.loads((directory/'result.json').read_text())
    result['_job_status']='SUCCEEDED' if result['run_status']=='completed' else 'FAILED'
    return result
