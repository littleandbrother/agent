#!/usr/bin/env python3
"""Publish task semantics while idle; reuse Pi design, native data and authored report."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

APP = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(APP/'scripts'))
from task_design_ops import audit, save
from v2_common import RUNTIME, action, restart
from bf_v2_environment import environment


def main():
    root = RUNTIME/'task-design/standards-publication-v1'
    if root.exists(): raise ValueError('PUBLICATION_EXISTS_USE_RECEIPTS_TO_RECOVER')
    before = audit()
    if before['active']: raise ValueError('ACTIVE_CONTROLLERS')
    profile, _ = environment(RUNTIME); home = Path(profile['home']); repo = home/'design-lab/repository'
    who = json.loads((RUNTIME/'task-design/owner.json').read_text()); owner = who['owner']
    source = action(owner, 'repository_summary')
    db = sqlite3.connect((home/'state/workbench.sqlite').as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row; db.execute('PRAGMA query_only=ON')
    system = json.loads(db.execute('SELECT value FROM design_system_commits WHERE id=?', (source['current_system']['id'] if isinstance(source['current_system'],dict) else source['current_system'],)).fetchone()[0])
    p = dict(db.execute('SELECT * FROM design_projects WHERE owner=?', (owner,)).fetchone())
    request_rows = [dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY rowid', (owner,))]
    executions = db.execute('SELECT COUNT(*) FROM design_task_executions WHERE project=?', (p['id'],)).fetchone()[0]; db.close()
    report_pin = json.loads((repo/'task-reports/by-system'/(system['id']+'.json')).read_text())
    report_input = json.loads((repo/'task-reports'/report_pin['id']/'input.json').read_text())
    save(root/'before.json', {'protected': before, 'reference_project': p,
        'request_sha256': hashlib.sha256(json.dumps(request_rows,sort_keys=True).encode()).hexdigest(),
        'request_count': len(request_rows), 'executions': executions, 'source_report': report_pin['id'], 'source_system': system['id']})
    value = restart(); save(root/'runtime.json', value)
    raw = {k:v for k,v in system['task_definition'].items() if k in ('profile','intent','goal','phase','scenario','parameters','acceptance','report','functions','components','assignments','design_space','service')}
    revised = action(owner,'repository_task_define',operation_id='standard-definition-v2-20261017',
        expected_revision=p['revision'],definition=raw,rationale='以相同服务、场景和设计接入标准化任务定义；保留 Pi 原设计、采用版、执行结果和账本。')
    save(root/'definition.json',revised); sid=revised['id']
    assert revised['task_definition']['standards']['version']=='bf-task-semantics-v1'
    run=action(owner,'repository_task_execute',operation_id='standard-definition-reuse-20261017',system_id=sid)
    if not run.get('reused'):raise ValueError('UNCHANGED_INPUT_WAS_NOT_REUSED')
    save(root/'execution-reuse.json',run)
    checks=action(owner,'repository_validate',operation_id='standard-definition-check-20261017',system_id=sid)
    save(root/'validation.json',checks)
    if checks['status']!='PASS':raise ValueError('STANDARDIZED_CANDIDATE_CHECK_FAILED')
    report=action(owner,'repository_task_report',operation_id='standard-definition-report-20261017',system_id=sid,
        content=json.dumps(report_input['content'],ensure_ascii=False))
    save(root/'report.json',{'source_pi_report':report_pin['id'],'source_content_sha256':hashlib.sha256(json.dumps(report_input['content'],sort_keys=True).encode()).hexdigest(),
        'action':'operator rerenders unchanged Pi-authored content with current validation',**report})
    release=action(owner,'repository_release',operation_id='standard-definition-release-20261017',system_id=sid,
        rationale='标准定义接入版；复用 Pi 原工程、执行数据及报告文字，附当前独立检查。')
    save(root/'release.json',release)
    state=action(owner,'repository_task_state');save(root/'state.json',state)
    contract=action(owner,'repository_task_schema');save(root/'model-visible-contract.json',contract)
    # The former adopted design keeps its identity; append current checker evidence without adoption changes.
    adopted_check=action(owner,'repository_validate',operation_id='standard-check-adopted-20261017',system_id=p['adopted'])
    save(root/'adopted-validation.json',adopted_check)
    after=audit()
    if any(before[k]!=after[k] for k in ('original_runtime','v2_p01','p01')):raise ValueError('PROTECTED_STATE_CHANGED')
    db=sqlite3.connect((home/'state/workbench.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
    new_p=dict(db.execute('SELECT * FROM design_projects WHERE owner=?',(owner,)).fetchone())
    new_s=json.loads(db.execute('SELECT value FROM design_system_commits WHERE id=?',(sid,)).fetchone()[0])
    new_requests=[dict(r) for r in db.execute('SELECT * FROM model_requests WHERE owner=? ORDER BY rowid',(owner,))]
    new_executions=db.execute('SELECT COUNT(*) FROM design_task_executions WHERE project=?',(p['id'],)).fetchone()[0];db.close()
    assert new_s['files']==system['files'] and new_requests==request_rows and new_executions==executions
    assert new_p['adopted']==p['adopted'] and state['stage']=='DELIVERED'
    result={'status':'PASS','source_system':system['id'],'current_system':sid,'adopted_system':p['adopted'],
        'task_definition':revised['task_definition']['id'],'stage':state['stage'],'task_passed':state['qualification']['task_passed'],
        'same_design_files':True,'same_execution':run['id'],'new_native_dispatches':0,'model_requests_added':0,
        'originals_unchanged':True,'ledger_unchanged':True,'source_report':report_pin['id'],'report':report['id'],'release':release['id'],
        'source_author':'operator standardization; original device design and prose by Pi',
        'schema_version':contract['standards']['version'],'runtime':value,
        'sources':{str(p.relative_to(APP.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in list((APP/'packages/python/bfworld/src/bfworld/agentlab/design_lab').glob('repository*.py'))+
            [APP.parent/'pi-bf-aiot/packages/bf-agent/src/repository-task.ts', APP.parent/'pi-bf-aiot/packages/bf-agent/src/extensions/bf-repository.ts',
             APP.parent/'pi-bf-aiot/packages/bf-harness/resources/skills/bf-task-design/SKILL.md', APP.parent/'pi-bf-aiot/packages/bf-harness/resources/plugins.json']}}
    save(root/'result.json',result)
    print(json.dumps({k:result[k] for k in ('status','current_system','adopted_system','stage','task_passed','new_native_dispatches','model_requests_added','originals_unchanged')},ensure_ascii=False))


if __name__=='__main__':main()
