"""Publish result readback after both design runs; then ask Pi to correct its reports."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

APP=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(APP/'scripts'))
from v2_common import RUNTIME,action,restart
from task_design_ops import audit


def save(path,value):
    if path.exists():raise ValueError('RECEIPT_EXISTS: '+str(path))
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['publish','dispatch']);args=parser.parse_args()
    root=RUNTIME/'task-design';who=json.loads((root/'owner.json').read_text());owner=who['owner']
    before=action(owner,'repository_state')
    if before['status']!='IDLE':raise ValueError('CONTROLLER_MUST_BE_IDLE')
    if args.mode=='publish':
        if audit()['active']:raise ValueError('ALL_V2_CONTROLLERS_MUST_BE_IDLE')
        receipt=root/'result-readback-publication.json'
        if receipt.exists():raise ValueError('PUBLICATION_RECEIPT_EXISTS')
        files=['packages/python/bfworld/src/bfworld/agentlab/design_lab/repository_task_result.py',
               'packages/python/bfworld/src/bfworld/agentlab/design_lab/repository_task_reports.py',
               '../pi-bf-aiot/packages/bf-agent/src/extensions/bf-repository.ts',
               '../pi-bf-aiot/packages/bf-harness/resources/skills/bf-task-design/SKILL.md']
        pins={path:hashlib.sha256((APP/path).read_bytes()).hexdigest() for path in files}
        publication=restart()
        result=action(owner,'repository_task_result',system_id=before['current_system'])
        after=action(owner,'repository_state')
        if before!=after:raise ValueError('PUBLICATION_CHANGED_DESIGN_STATE')
        save(receipt,{'before':before,'after':after,'sources':pins,'publication':publication,'actual_result_readback':result})
        print(json.dumps({'status':'PASS','unchanged_state':True,'result_facts':len(result['facts'])}));return
    goal=('这是两轮设计完成后的报告核对，Codex 提供了公开的单位与表述问题反馈。工程候选、采用状态和检查保持，'
          '本轮只更新两份报告与对应审查包，不执行 task_commit/task_execute/validate/decide。'
          '先加载 bf-task-design，再用新的 task_result 查询 R6（SC-e4cb777644f4a192133f9834cf4ee8cd4834975f5129d5ca041a055fa2187588）'
          '和当前 R7 的已有结果；path/offset/limit 可直接读取已有原始数据。'
          '修正这些报告问题：负载能量必须使用固定 2.5 V 负载轨；相对残差的分子分母统一为 J；'
          '窗口最低电压从已保存波形读取；储能下限与可用功率无关的结论超出了当前固定条件扫描；'
          '连续双帧试验仍有源注入，不能描述成断源续航或零再充；统一写仿真结果，避免写成物理实测；'
          '修正“突发育额”等错字。自行用工具事实重算、改写两版说明，并明确第二轮容量与时序的实际差异。'
          '报告简洁，保留事实、判断及必要条件；五节均附来源。为两版分别 task_report 与 release，随后 close。')
    receipt=root/'report-correction-dispatch.json'
    if receipt.exists():raise ValueError('REPORT_CORRECTION_ALREADY_DISPATCHED')
    before_path=root/'before-report-correction.json'
    if before_path.exists():
        if json.loads(before_path.read_text())['state']!=before:raise ValueError('REPORT_BASE_CHANGED')
    else:save(before_path,{'state':before,'view':action(owner,'repository_view')})
    result=action(owner,'repository_start',goal=goal)
    save(receipt,{'goal':goal,'intervention':'Codex public report arithmetic and wording review; no product design changes',**result})
    print(json.dumps(result))


if __name__=='__main__':main()
