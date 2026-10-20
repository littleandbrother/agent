#!/usr/bin/env python3
"""Source-bound default-case preparation and P08 transfer; no legacy writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from run import APP, ROOT, action, create_pi, save

P08 = Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/runtime/participants/pi-chat-e0028698d50802cb')


def transfer():
    if (ROOT/'p08/identity.json').exists(): return json.loads((ROOT/'p08/identity.json').read_text())
    source = P08/'engineering-artifacts/eng-19eb09030ae354a8/project-trace.raw'
    expected = '597413343e2f6869bf82a84ea39440bf7be73ba55ab93063eae95499727daab8'
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected: raise ValueError('P08_RAW_IDENTITY')
    header, values = raw.decode().split('Values:', 1)
    names = [line.split()[1] for line in header.rsplit('Variables:',1)[1].splitlines() if line.strip()]
    n = int(re.search(r'No. Points:\s*(\d+)', header)[1])
    width = len(names)+1; flat = values.split()
    if len(flat) != n*width: raise ValueError('P08_RAW_SHAPE')
    x = [.5,1.,2.,4.,8.,16.]; paper = [473,379,272,175,103,56]
    times = [float(flat[i*width+1+names.index('time')]) for i in range(n)]
    rows=[]
    for k,(v,reference) in enumerate(zip(x,paper),1):
        column = names.index(f'i(l_b{k})')+1
        last=max(i for i in range(n) if abs(float(flat[i*width+column]))>1e-3)
        duration=times[last]*1e6
        rows.append({'initial_v':v,'paper_us':reference,'native_us':duration,'relative_percent':100*(duration/reference-1)})
    evidence={'source_owner':'pi-chat-e0028698d50802cb','source_job':'eng-19eb09030ae354a8',
        'raw_path':str(source),'raw_sha256':expected,'points':n,'new_native_runs':0,
        'paper_location':'P08 supplement Note S13 pp27-28','extraction':'last |inductor current| > 1 mA',
        'rows':rows,'raw_reused':True,'case_exposure':'previous development case; not held-out'}
    save(ROOT/'p08/readback.json',evidence)
    files={'reference.csv':'x,y\n'+''.join(f'{v},100\n' for v in x),
        'observation.csv':'x,y\n'+''.join(f"{r['initial_v']},{100+r['relative_percent']:.12f}\n" for r in rows),
        'notes/source-readback.json':json.dumps(evidence,ensure_ascii=False,indent=2),
        'notes/original-scope.md':(P08/'analysis-spice/REPORT.md').read_text()[:22000]}
    for name in ['delivery/requirements.json','delivery/interfaces.json']:
        files['notes/'+Path(name).name]=(P08/name).read_text()
    definition={'profile':'curve-reproduction-v1','intent':'audit',
        'goal':'复核 P08 原生一级降压模型在六个初始输出电压下的电流衰减时长，与论文 Note S13 对照；从任务定义完成到同版审查交付。',
        'scenario':{'axis_units':{'x':'V','y':'percent of paper duration'},'raw_sha256':expected,'raw_source_job':'eng-19eb09030ae354a8','current_cutoff':.001,'paper_durations':paper},
        'parameters':[{'name':'current_cutoff','value':.001,'unit':'A','source':'reference','role':'constraint'},
                      {'name':'paper_durations','value':paper,'unit':'us','source':'literature','role':'constraint','locator':'P08 Note S13 pp27-28'}],
        'acceptance':{'curve_binding':{'condition':'六个相同电压点，原始波形来源哈希一致'},
                      'curve_accuracy':{'condition':'六个衰减时长相对论文的最大偏差不超过 1%','max_abs_error':1.0},
                      'delivery_version':{'condition':'原始来源、提取结果、检查和报告绑定本候选'}}}
    save(ROOT/'p08/task-definition-v2.json',definition)
    who=create_pi('P08 · 原波形复核与任务范式迁移','task-evaluation-p08-transfer-20261017')
    made=action(who['id'],'repository_task_create',operation_id='p08-transfer-source-bound-v1',title='P08 · 一级降压模型复核',definition=definition,files=files)
    auth=action(who['id'],'authorize',wall_authorization_text='持续运行 不设置时间限制',model_profile='engineering-reasoning-efficient-v5')
    identity={'owner':who['id'],'project_id':made['project_id'],'initial_system':made['id'],'source_owner':evidence['source_owner'],'authority':auth}
    save(ROOT/'p08/identity.json',identity)
    goal='请完成当前任务的整条推进流程：阅读任务和来源，检查复用的原始结果及六点对照，执行当前表格检查，作出有依据的判断，生成 PDF 和同版 release 并 close。说明原论文整机中尚未覆盖的环节。没有输入变化，不启动原生仿真。'
    save(ROOT/'p08/dispatch.json',action(who['id'],'repository_start',goal=goal))
    return identity


def reference():
    owner='pi-chat-f6463f6b0b663ebc'
    if (ROOT/'default/dispatch.json').exists(): return json.loads((ROOT/'default/dispatch.json').read_text())
    summary=action(owner,'repository_summary');current=summary['current_system']
    facts={'source':'https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf',
        'article':'https://www.analog.com/en/resources/technical-articles/energy-harvester-produces-power-from-local-environment.html',
        'part':'LTC3588-1','datasheet_revision':'Rev C',
        'for_2p5V_output':{'D1':0,'D0':1,'uvlo_rising_typ_v':4.04,'uvlo_rising_min_max_v':[3.77,4.30],
            'uvlo_falling_typ_v':2.87,'uvlo_falling_min_max_v':[2.66,3.08]},
        'pgood_falling_fraction':.92,'datasheet_pages':[3,9,10],
        'existing_model':'Current reference uses a resistively loaded piezo modal source and fixed average conversion efficiency. Existing input/output storage placement is an abstract reference; physical PMIC selection requires distinct input/output capacitors and voltage thresholds.',
        'authorship':'Codex source extraction; Pi owns selection and design decisions'}
    save(ROOT/'default/source-facts.json',facts)
    added=action(owner,'repository_task_commit',operation_id='default-source-facts-20261017',base_system=current,
        expected_revision=summary['revision'],files={'notes/adi-source-facts.json':json.dumps(facts,ensure_ascii=False,indent=2)},
        rationale='补入用户指定 ADI 参考的器件来源与电压条件，供原 Pi 选择默认实现。')
    save(ROOT/'default/source-commit.json',added)
    goal=('完成常规压电梁＋低功耗感知节点的默认参考交付。沿用当前候选与已有有效执行，先读 notes/adi-source-facts.json。'
          '由你选择具体电源实现路线，解释源、储能、MCU活动和接收要求如何衔接，核对器件电压条件与当前模型之间的接口差异。'
          '在 notes/default-design.json 写清推荐器件、输入/输出储能的区别、信号/电源接口、实际已执行与待补模型；不要把未执行的器件行为写成通过。'
          '如确有需要可修订允许的设计参数或程序；输入不变直接复用。完成独立检查、决定、报告、release 并 close。')
    dispatched=action(owner,'repository_start',goal=goal)
    save(ROOT/'default/dispatch.json',{'owner':owner,'goal':goal,**dispatched})
    return dispatched


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['p08','default']);a=p.parse_args()
    print(json.dumps(transfer() if a.mode=='p08' else reference(),ensure_ascii=False))
