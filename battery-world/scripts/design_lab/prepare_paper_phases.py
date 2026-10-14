#!/usr/bin/env python3
"""Publish concrete public next stages for the ten existing Pi conversations.

This edits operator plans/queue only. Participant engineering and old receipts
are not touched. Enqueue requires the new tested apparatus publication.
"""
import argparse
import json
from pathlib import Path
import sys
import time

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT, digest, put_once, read
from bfworld.agentlab.literature_continuation import load_authority
from bfworld.agentlab.literature_native import apparatus_identity
from bfworld.agentlab.store import canonical

STAGES = {
 'P01': ('source-circuit-interface-chain', ['campaign/reviews/P01/fault-check-004/result.json'],
  '已通过固件18项反例、CAD和储能局部SPICE先复用。本轮自行核对论文MCU/CDC实际身份、已补建nRF52832/S132与原型差异，建立源/SECE—储能—AFE—MCU的接口和模型适用域。用论文页码与厂商定义给出器件身份、引脚/网络/封装对照、启动及负载边界；优先补一个能够独立读回的真正缺失环节，保留参数未知项。旧54a75cdea45045c6b614f50f6ee80485仅为旧云端项目容器，目前桌面CLI拒绝以该云UUID绑定原生文件；presence UNKNOWN不等于不存在。无本篇原生绑定时不要创建替代工程、不要操作门磁或桌面测试工程，EDA保持BLOCKED，待合法导入映射。当前阶段可编辑已有源码/接口与报告，自行选择是否有必要改变模型；不能把等效储能模型称完整SECE复现。'),
 'P02': ('energy-admission-four-remaining-cases', ['campaign/reviews/P02/r16-independent-energy-002/result.json', 'campaign/reviews/P02/r16-report-conformance-003/result.json'],
  '最新r16是16/20供能任务成立，21行报告已核对，旧8/20和新固件同版70项包均保留。本轮聚焦剩余4种条件及任务能量准入：从最新RAW/源条件、实际任务电流和掉电边界独立定位，BF自己提出和选择有来源的设计修改，处理启动、欠压、重试及任务截断。不得为了PASS任意加大源或删去困难工况。输入未变先分析现有RAW；仅对实际改变且能区分原因的输入运行新作业，固件/CAD未变复用。保留LoRa替代接口及真实TENG模型尚未校准的边界，把供能反例与文件门分开交付。'),
 'P03': ('afe-mcu-wireless-interface', ['campaign/reviews/P03/fault-check-002/result.json'],
  '172文件同版交付和28项固件检查已通过，不重复修包。本轮打通AFE—MCU—无线的板级接口定义：基于原论文和厂商寄存器/引脚建立真实接口、初始化顺序、传感输入/标定未知项、通信帧及失败路径；沿已有STM32L432源码补一个缺失环节并用现有目标执行器实际构建（仅在源码改变后）。用可公开输入的总线/错误/掉电序列验证新接口逻辑，传感读数与评价真值分别处理，不把主机mock等同目标外设/RF。锂电演示与无电池工况保持分开。无原生EDA绑定时给出可导入的网络/封装对应，保持PCB未验收。'),
 'P04': ('s132-packet-target-chain', ['campaign/reviews/P04/portable-draft-check-003/result.json'],
  '裸机启动/STARTED中断修复及eng-3a44315e03c7e441目标构建、portable15项与2负例已关闭。本轮从当前portable核心与官方SDK17/S132资料出发，自行完成nRF52832实际S132应用的采样—帧—发送接口连接，保留周期/容量/断连/旧回调身份等既有反例。现有catalog支持firmware-nrf52832-s132，必须使用该真实目标族构建并读回所选ELF/HEX/MAP、SoftDevice与应用配置。PC端帧解码用实际输出验证；发送接受、链路送达、供能成立分别报告，SDK构建不得升级为射频实测。未变机械/SPICE继续复用，EDA与完整高率源模型保持未完成。'),
 'P05': ('portable-to-target-peripheral-boundary', ['campaign/reviews/P05/fault-check-project-003/result.json'],
  'portable core已14/14，STM32L031目标eng-dd1c9063402dbf8e及50文件同版包保留。现在自行核对portable事件逻辑与实际目标GPIO/EXTI/定时/掉电/发送接口对应，优先补一个真实缺失外设路径或处理未验证时序。利用当前官方STM32定义及已有host检查进行可区分的反例，改变固件后才做新目标构建。不要把27项公共ABI检查器自测当作本篇固件通过。重量标定、真实道路激励及RF仍无验证时写明缺口，不凭代理模型承诺实测速度/重量。'),
 'P06': ('escapement-dynamics-and-energy-port', ['campaign/reviews/P06/shaft-interface-readback-001/result.json'],
  '新CAD eng-7e1f00245b9fd22b、51实体、轴配合9项及旧静态4项已核对，不重复生成或运行相同CAD。此阶段建立擒纵机构输入—机械储能—释放—TENG电端口的最低可解释动力学，参数必须对应论文、既有几何或明确假设；说明接触/摩擦/轴保持尚未校准。现有固定正弦源不能证明不规则输入下持续工作，需自行决定可支持的输入、状态与能量检查，给出适用域及能量收支反例。没有足够材料时封存模型缺口和最小所需条件，不能强加MCU或把静态模型当动力学通过。'),
 'P07': ('electrode-charge-transfer-dynamics', ['campaign/reviews/P07/static-layer-readback-rev5-funded-002/result.json'],
  '61实体、16片PTFE和覆膜、224对0干涉与eng-94961db2140e5818当前包已确认，撤销的001空选集回执仍保留为历史。本轮从真实叠层/电极连接出发建立磁摆运动与电荷分配的接口模型，核对电极拓扑、位置依赖电容/电荷、初始状态及机械输入与电功的边界。BF自己决定有来源的最低动态实现和区分反例，不能以独立正弦源替代磁摆或从零外部储能推出零内部极化。静态输入未变不重建CAD；新模型仅以适用域内计算报告，未校准动力学/材料参数明确UNEVALUABLE。'),
 'P08': ('source-secondary-load-cold-start', ['campaign/reviews/P08/funded-analysis-recheck-002/result.json'],
  '最新独立002已确认F1–F4分析修正，当前13个文件摘要和既有RAW有效；不再修一遍冷启动外推、分支账或来源表。真正剩余是冷启动/持续供能和效率核心链。本轮自行以论文高压高阻源、多级提取/转换及低压负载建立有边界的源—次级—负载检查，明确源Q/V/C(x)、内部初态与外部储能零初态、开关时序和每个效率分母。先查当前RAW覆盖哪些条件，仅在补充真实缺失的初态/负载/拓扑输入时求解；禁止用预充电事件表外推零电压首事件。未知磁参数/损耗或未覆盖冷启动时保持UNEVALUABLE，保留已修正分析作为回归，不增加无关MCU。'),
 'P09': ('physical-encoding-readout-boundary', ['campaign/reviews/P09/condition-document-recheck-003/result.json'],
  '最新003的20项文档修正已核对，不重复改比较口径。当前放电模型与峰值比仅为局部代理、不能判论文错误。本轮推进无芯片的编码—通道—读出链：从论文明确的编码与测量条件建立可编辑执行模型，环境只提供可观测传感/端口信号，接收器自行恢复事件/信息；不能把评价真值直接给解码器。用丢失、噪声/时序变化及重复事件的有条件反例确定当前能检查的范围；RF耦合/端口阻抗/损耗不明仍列缺口。原架构无MCU，不增加固件冒充复现。未变CAD/局部RAW直接复用。'),
 'P10': ('coil-rectifier-regulator-load-boundary', ['campaign/reviews/P10/version-energy-recheck-003/result.json','campaign/reviews/P10/current-coil-readback-002/result.json'],
  '尺寸、间隙版本及能量口径的已有修订已关闭，eng-cf4e0d6931f29142当前线圈CAD与32文件保留。本轮自行建立线圈—耦合—整流—稳压—负载的参数与适用域，区分实际论文原始数据、补建和假设；变化容忍工况必须绑定具体间隙/偏移/源/负载条件。优先扩充一个可独立观察的缺失环节及能量/尺寸负例；原直流接收端模型不能证明无线供电链。原ATtiny25目标与作者固件尚无合格执行器/源码时保持BLOCKED，不用nRF/STM32替代并称同目标。发射器电池边界始终保留，不重复未变CAD/SPICE。')
}

COMMON = ('\n统一结束条件：先修改或证明现有输入无需修改，再保存可编辑源、实际作业/检查、接口/适用范围、明确未通过项与同版报告/清单；文件门、核心功能、Pi/Codex介入、物理验证分别记录。'
          '只在本原会话与原工作目录执行，不清账，不改评价器，不自行采用方法候选。全部已有成功且输入未变的作业复用。运行时间、费用/token/request累计无上限，但每步有界、无进展或缺关键资格时停止该阶段并给出事实阻塞，不无效重试。'
          '这是Codex整理的公开问题边界；设计假设、候选、下一项实验和修改由BF/Pi自己决定。新功能检查未独立完成不得写PASS，不据此称RSI。')

def replace_preserving(path, value, history):
    old = None
    if path.is_file():
        old = {'path':str(path), 'sha256':digest(path)}
        archive = history/(path.stem+'-'+old['sha256']+'.json')
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.exists() and archive.read_bytes()!=path.read_bytes():
            raise ValueError('OPERATOR_HISTORY_CHANGED')
        if not archive.exists():archive.write_bytes(path.read_bytes())
        old['archive']=str(archive)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.next');temporary.write_text(canonical(value));temporary.replace(path)
    return old

parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
parser.add_argument('--enqueue',action='store_true');args=parser.parse_args();root=args.root
authority=load_authority(root)
index=read(root/'campaign/parallel-20261009/pi-session-index.json')
owners={s['paper_id']:s['owner'] for s in index['sessions']}
if set(owners)!=set(STAGES) or len(set(owners.values()))!=10:raise ValueError('TEN_ORIGINAL_OWNERS_REQUIRED')
if args.enqueue:
    q=read(root/'campaign/native-qualification.json');r=read(root/'campaign/parallel-20261009/READY.json')
    if (q.get('apparatus_identity')!=apparatus_identity()[0] or r.get('status')!='PASS' or
        r.get('qualification_sha256')!=digest(root/'campaign/native-qualification.json') or
        r.get('authorization_sha256')!=authority['authority_sha256']):raise ValueError('NEW_QUALIFIED_RELEASE_REQUIRED')
receipt={'schema_version':'bf-ten-paper-next-phase-preparation-v1','created':time.time(),
         'authority_sha256':authority['authority_sha256'],'enqueued':args.enqueue,
         'model_calls':0,'native_jobs':0,'participant_engineering_edits':0,'papers':[]}
order=['P02','P04','P08','P09','P06','P01','P03','P05','P07','P10']
for rank,paper in enumerate(order):
    scope,assets,task=STAGES[paper];owner=owners[paper]
    contract=read(root/'runtime/participants'/owner/'contract.json')
    phase={'schema_version':'bf-paper-recovery-phase-v1','paper_id':paper,'owner':owner,
           'phase':'engineering-review','actor':'Codex public engineering reviewer',
           'source_identity':contract['source_identity'],'stage_scope':scope,
           'model_profile':'engineering-reasoning-v1','task':task+COMMON,
           'assets':[{'path':name,'sha256':digest(root/name)} for name in assets],
           'full_system_scope_retained':True,'physical_verified':False,
           'wall_seconds_cap':None,'usd_cap':None,'fees_reset':False,
           'authority_sha256':authority['authority_sha256'],'created':time.time()}
    path=root/'campaign/recovery'/paper/'phases/engineering-review.json'
    old=replace_preserving(path,phase,path.parent/'history')
    item={'paper':paper,'owner':owner,'stage_scope':scope,'phase_path':str(path.relative_to(root)),
          'phase_sha256':digest(path),'previous_phase':old}
    if args.enqueue:
        queue=root/'campaign/parallel-20261009/pi-queue';queue.mkdir(exist_ok=True)
        qpath=queue/(owner+'.json')
        if qpath.exists() and read(qpath).get('status') in ('RUNNING','QUEUED'):
            raise ValueError('ORIGINAL_OWNER_ALREADY_QUEUED:'+owner)
        value={'schema_version':'bf-paper-continuation-queue-v1','id':'lab-v2-'+paper+'-'+str(time.time_ns()),
               'owner':owner,'paper':paper,'phase':'engineering-review','status':'QUEUED',
               'created':time.time()+rank*.01,'authorization_sha256':authority['authority_sha256'],
               'operator_text':'按当前phase任务推进实际未关闭环节；旧阶段完整包保持有效，新增工程必须明确同版本，不以文件门授予整机通过。',
               'phase_sha256':digest(path),'actor':'Codex apparatus maintainer'}
        item['previous_queue']=replace_preserving(qpath,value,queue/'history')
        item['queue_id']=value['id']
    receipt['papers'].append(item)
folder=root/'deployment/executable-lab-20261012';folder.mkdir(parents=True,exist_ok=True)
path=folder/('phase-preparation-'+str(time.time_ns())+'.json');put_once(path,receipt)
print(json.dumps({'papers':len(receipt['papers']),'enqueued':args.enqueue,'receipt':str(path)},ensure_ascii=False))
