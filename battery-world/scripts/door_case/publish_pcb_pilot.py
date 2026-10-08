#!/usr/bin/env python3
"""Preserve a failed or incomplete Pi PCB pilot without promoting its claims.

Copies small participant outputs and independent receipts into a new immutable
case. Does not edit participant files, invoke a model, or touch the native board.
"""
import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from bfworld.agentlab.store import Store
from bfworld.agentlab.product_results import ProductResults


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def publish(runtime, owner, recipients, output):
    runtime=runtime.resolve();workspace=runtime/'workbench/participants'/owner
    evidence=runtime/'reference-cases/door-selfpower-v1/pi-pcb-20261007'
    output.mkdir(parents=True,exist_ok=False)
    copied=[]
    def copy(source, target):
        if source.is_symlink() or not source.is_file() or source.stat().st_size>2*1024*1024:
            raise ValueError('Unexpected source for lightweight pilot package: '+str(source))
        dest=output/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        if sha(dest)!=sha(source): raise ValueError('COPY_HASH_MISMATCH')
        copied.append(target)
    for folder in ('delivery','design'):
        for p in sorted((workspace/folder).iterdir()):
            if p.is_file() and p.suffix in ('.py','.json','.csv','.svg','.txt','.md'):
                copy(p,folder+'/'+p.name)
    copy(workspace/'analysis.json','participant-analysis.json')
    for name in ('system.cir','main_pcb-dimensions.svg'):
        copy(workspace/'reference'/name,'reference/'+name)
    receipts=['responsibility-contract.json','native-create.json','native-summary-01.json',
        'native-schematic-readback-01.json','native-pcb-readback-01.json',
        'independent-pcb-source-review-03.json','D5-Pi-incomplete.epro2',
        'coordinator-save-schematic.json','coordinator-save-pcb.json','coordinator-partial-native-export-02.json',
        'context-wire-replay-02.json','long-history-ingress-repair.json']
    for name in receipts: copy(evidence/name,'evidence/'+name)
    interventions=sorted(evidence.glob('intervention-*.json'))
    for p in interventions:copy(p,'evidence/'+p.name)
    with sqlite3.connect(runtime/'workbench/state/workbench.sqlite') as db:
        db.row_factory=sqlite3.Row
        rows=[dict(r) for r in db.execute('SELECT status,charged,reserved,usage FROM model_requests WHERE owner=?',(owner,))]
        state=dict(db.execute('SELECT status,error,created,updated FROM conversations WHERE id=?',(owner,)).fetchone())
        jobs=[dict(r) for r in db.execute('SELECT id,status,request FROM eda_cli_jobs WHERE owner=?',(owner,))]
    cost={'requests':len(rows),'settled_usd':sum(r['charged'] or 0 for r in rows if r['status']=='SETTLED'),
          'retained_reservations_usd':sum(r['reserved'] or 0 for r in rows if r['status']!='SETTLED'),
          'request_statuses':dict(Counter(r['status'] for r in rows)),
          'provider_tokens':sum(json.loads(r['usage'])['total_tokens'] for r in rows if r['usage']),
          'prospective_study_usd':5,'operator_followups':len(interventions),'native_jobs':len(jobs),
          'native_job_statuses':dict(Counter(j['status'] for j in jobs)),
          'trace_owner':owner,'conversation':state}
    write(output/'cost-and-attribution.json',cost)
    bom=list(csv.DictReader((output/'delivery/D5_BOM.csv').open()))
    schematic=json.loads((output/'evidence/native-summary-01.json').read_text())
    pcb=json.loads((output/'evidence/native-pcb-readback-01.json').read_text())
    audit=json.loads((output/'evidence/independent-pcb-source-review-03.json').read_text())
    layout=json.loads((output/'delivery/D5_layout_offline.json').read_text())
    placed=layout['placements'];collisions=[];overflow=[]
    for i,p in enumerate(placed):
        if abs(p['x'])+p['w']/2>39 or abs(p['y'])+p['h']/2>14:overflow.append(p['ref'])
        for q in placed[i+1:]:
            if 2*abs(p['x']-q['x'])<p['w']+q['w']-1e-6 and 2*abs(p['y']-q['y'])<p['h']+q['h']-1e-6:
                collisions.append([p['ref'],q['ref']])
    geometry={'scope':'Independent check of participant-declared rectangles only; no real pad, package, antenna or copper verification',
              'rectangles':len(placed),'overlap_pairs':collisions,'out_of_frame':overflow,
              'engineering_passed':False,'source_sha256':sha(output/'delivery/D5_layout_offline.json')}
    write(output/'rectangle-review.json',geometry)
    pending=sum(not str(r.get('LCSC','')).startswith('C') or not str(r.get('LCSC',''))[1:].isdigit() for r in bom)
    outcome={'schema_version':'bf-pcb-pilot-outcome-v1','decision':'candidate-rejected',
       'engineering_passed':False,'agent_autonomy_proven':False,'hardware_verified':False,
       'source_sha256':sha(output/'reference/system.cir'),'frozen_reference_modified':False,
       'native_schematic_parts':len(schematic['parts']),'native_wires':schematic['wires'],
       'native_pcb_parts':len(pcb['components']),'native_routed_lines':pcb['routedLines'],
       'native_pcb_partial':pcb['partial'],'bom_rows':len(bom),'unresolved_lcsc_rows':pending,
       'independent_findings':len(audit['findings']),
       'findings_by_kind':dict(Counter(f['kind'] for f in audit['findings'])),
       'responsibility_transfer':'Not demonstrated: repeated operator correction and final coordinator collection were needed.',
       'publication_author':'coordinator; candidate files retained byte-for-byte from Pi'}
    write(output/'independent-outcome.json',outcome)
    report=f'''# D5 新电路 PCB · Pi 试运行与独立验收

**结论：候选未通过验收。登录和原生连接已恢复，新 D5 PCB 尚未完成。**

本包记录 2026-10-07 至 10-08 的真实 Pi 执行。不是旧 D3 改名，不是制造包，也不继承 D5 自供能仿真的合格结论。

## 实际得到的内容

| 内容 | 实际证据 | 判断 |
|---|---|---|
| D5 电路源 | system.cir，SHA-256 `{outcome['source_sha256']}` | 原始源未修改 |
| BOM | {len(bom)} 行；20 个二极管、18 个均流电阻得到补齐；{pending} 行尚未明确有效 LCSC 号 | 候选；不能直接采购 |
| 离线布局 | {len(placed)} 个估计包络；独立矩形检查重叠 {len(collisions)}、越界 {len(overflow)} | 仅证明这些矩形可排入 80×30 mm，不是封装/布线通过 |
| 原生原理图 | {len(schematic['parts'])} 个器件，{schematic['wires']} 条线 | 不完整；多余 PMIC、器件替代及引脚未连 |
| 原生 PCB | {len(pcb['components'])} 个器件，{pcb['routedLines']} 条铜线 | 空板；没有 DRC 通过证据 |
| 原生工程导出 | `evidence/D5-Pi-incomplete.epro2`，已保存并验证 ZIP 完整性 | 可保留和打开的失败现场；没有重新导入验证 |
| 集中交付 | 本报告、候选文件、源程序、原生回读和独立检查 | 由协调器整理，不能归为 Pi 自主完成 |

## 阻止放行的关键问题

1. `design/d5_netlist.csv` 把 U1 声明为 11 端口，却只保留 `net1` 至 `net5`。新增自动检查已实际检测出端口丢失。这不是绘图问题，后续连线不能据此生成。
2. Pi 的旧 `d5_pinmap.json` 对 LTC3588-1 引脚的解释有误。实际器件有 D1、D0 和第 11 脚散热焊盘 GND；官方数据手册和原生引脚回读均可核对。不得将正确源电路改成错误的“10端口”模型。参考：[ADI 数据手册，第2页](https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf)。
3. 最终 BOM 的 Smonitor、Smonitor_high、U_GATE 三行都写成 MIC841L，行为开关到真实门控电路的合并关系没有完成；`MODEL-ONLY` 的 X_MATCH 仍进入布局。模拟元素不能逐行当作物料。
4. nRF52832 和 SWD 已被列入，但时钟、射频外围、天线留空、实际引脚及其供电需求还没有构成完整目标工程。写入一个 MCU 名字不能代表无线节点实现。
5. 估计的通用封装方框没有经过实际焊盘和器件三维包络核对。所谓“零碰撞”只覆盖矩形，不覆盖寄生参数、电流环路、热、电气间距和可布线性。
6. 原生现场仍有 BAT54S，源电路使用 BAT46WJ；没有等效性依据，不能自动替代。新版离线 BOM 已把 BAT46WJ 封装改回 SOD-323F；参考：[Nexperia 器件页](https://www.nexperia.com/product/BAT46WJ)。

独立脚本给出 {len(audit['findings'])} 条检查发现，其中很多是同一“原生实现尚未生成”在不同器件上的表现，不能解读成 {len(audit['findings'])} 个独立根因。完整 R/C/L/X 连接、门控物理实现、厂商封装映射、ERC/DRC 与保存重载仍需分别通过。

## 这次修复了哪些系统问题

- 新增持久分析清单、冻结的来源/职责合同和显式提交入口；只填完表格不授予工程 PASS。
- Pi 可调用绑定到新工程的 typed EasyEDA 工具；旧 D3 保持参考。原生操作、Skill 读取和失败进入 Trace。
- 旧机器快照不再挤占实际工具反馈；完整数据保存在可回读档案中，用户原话和原始 Trace 保留。
- 修复旧长时限 lease 抢占新消息额度的问题；修复长历史在压缩前被本地 2 MB 接口拒绝的问题。模型实际请求仍限制为 128000 字节。
- 区分“仿真实验次数”和“EDA 命令/器件数量”；明确命令拼写错误、绑定路由参数错误不等于未登录或服务器忙。
- typed 批量文件校验覆盖两种 Apply 入口；原生导出的工程与窗口由服务绑定，参与者不能改指向旧板。
- 完成分析提交后可将报告和证据发布到同一产品目录；发布本身始终保留“未独立验收”的状态。本轮 Pi 没有自行到达提交，下面的汇总由协调器执行。

## 执行与责任归属

真实模型请求 {cost['requests']} 次，已结算约 ${cost['settled_usd']:.6f}；另保留 ${cost['retained_reservations_usd']:.6f} 的历史未发送预留。本次预先登记的工程先导为 $5/12小时，最终被 `{state['error']}` 拦住；未修改历史账目来续跑。

保留 {len(interventions)} 次协调器跟进、空工程创建、运行时修复、独立检查及最后保存/导出。Pi 自己编写 BOM、网表和布局脚本，也自己做了少量原生放置；协调器没有替它完成布线。**这次不能证明责任已经转交给 Agent，更不能用“接口已接通”作为自主交付成功。**

## 下一次应如何继续

先修复无损的模型端口→真实器件引脚映射和行为模型→真实功能块的转换。用一个完整供能/门控功能块通过原生连接图差分、真实封装和保存重载，再展开整板。批量物料与连接数据应能在写入前被确定性检查；错误反馈必须定位到来源和具体终端，不能只说“命令失败”。

整板进入布线前需完成 MCU/射频最小系统与真实封装。两次原生布局检查通过后才进行实际铜线、连通性、DRC、3D 与制造导出。重新尝试时保留本次失败数据，不能把协调器补答案后的结果与本次当作同一自主试验。

## 文件与复查

- `delivery/`：Pi 原样生成的 BOM、矩形布局和示意预览；均为未验收候选。
- `design/`：Pi 原样生成的脚本与中间数据，包含上述缺陷，供修订和复查。
- `reference/`：来源电路与板框依据。
- `evidence/`：原生回读、未完成工程、独立检查、干预记录。
- `independent-outcome.json`、`rectangle-review.json`、`cost-and-attribution.json`：可机读的结果及边界。

本轮没有重启已完成的整机仿真，没有新硬件测试，没有提交 GitHub。
'''
    (output/'REPORT.zh.md').write_text(report)
    records=[{'path':str(p.relative_to(output)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(output.rglob('*')) if p.is_file()]
    write(output/'file-manifest.json',{'schema_version':'bf-pcb-pilot-files-v1','files':records})
    archive=output/'D5-Pi-candidate-rejected.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file() and p!=archive:z.write(p,p.relative_to(output))
    with zipfile.ZipFile(archive) as z:
        if z.testzip(): raise ValueError('ZIP_READBACK_FAILED')
    def files(names,sections):
        return [{'path':n,'name':n.replace('/','--'),'sha256':sha(output/n),'sections':sections} for n in names]
    groups=[
      {'id':'review','domain':'system','kind':'engineering-report','title':'D5 新板 · 验收未通过',
       'scope':'Pi 候选被独立检查拒绝；新版原生 PCB 仍为空板；报告和整个候选包可下载',
       'files':files(['REPORT.zh.md','independent-outcome.json','cost-and-attribution.json','D5-Pi-candidate-rejected.zip'],['documents','pcb'])},
      {'id':'bom','domain':'circuit','kind':'bom-candidate','title':'D5 BOM · 待修订',
       'scope':f'{len(bom)}行，{pending}行待选型；存在行为模型重复映射，不能直接采购',
       'files':files(['delivery/D5_BOM.csv','delivery/D5_BOM.json'],['bom'])},
      {'id':'layout','domain':'circuit','kind':'pcb-candidate','title':'D5 布局候选 · 不是已布线 PCB',
       'scope':'仅为估计矩形的排布；没有真实焊盘、铜线或 DRC 验收',
       'files':files(['delivery/D5_floorplan.svg','delivery/D5_layout_offline.json','rectangle-review.json'],['pcb'])},
      {'id':'native','domain':'circuit','kind':'eda-candidate','title':'D5 原生工程 · 未完成现场',
       'scope':'7个原理图器件、0条线；PCB为空；原生导出由协调器保存，未经重新导入验收',
       'files':files(['evidence/D5-Pi-incomplete.epro2','evidence/native-schematic-readback-01.json','evidence/native-pcb-readback-01.json','evidence/independent-pcb-source-review-03.json','design/d5_netlist.csv'],['schematic','pcb'])}]
    for group in groups:group['design_status']='insufficient_evidence'
    manifest={'schema_version':'bf-engineering-case-v1','id':'door-d5-pcb-pilot','version':'D5-P1',
              'title':'D5 新板候选 · 独立验收未通过','authority':'operator-assisted','hardware_verified':False,
              'autonomous_agent_verified':False,'design_sha256':outcome['source_sha256'],'groups':groups}
    catalog=ProductResults(SimpleNamespace(store=Store(runtime/'workbench/state')))
    for target in dict.fromkeys([owner,*recipients]):catalog.cases.publish(target,output,manifest)
    write(output/'publication.json',{'owners':list(dict.fromkeys([owner,*recipients])),'manifest':manifest,'zip_sha256':sha(archive)})
    return {'output':str(output),'bytes':sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),'zip_bytes':archive.stat().st_size,'cost':cost,'outcome':outcome}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--owner',required=True);p.add_argument('--recipient',action='append',default=[]);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(publish(a.runtime,a.owner,a.recipient,a.output),ensure_ascii=False,indent=2))
