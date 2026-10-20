#!/usr/bin/env python3
"""Read-only state audit and byte-exact local delivery of the Pi report release."""
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile

HERE = Path(__file__).resolve().parent
REPO = Path.home()/'.local/share/bf-agent-architecture-v2/workbench/design-lab/repository'
DB = REPO.parent.parent/'state/workbench.sqlite'
RELEASE = 'REL-817a555ffd29e711bc65f94d8689fe0f20aebdb662b117db1b6bbf46ebac7d4f'
REPORT = 'RP-c8401a0608e390d52ddf40a9564c624da83d96a2bda61fbf8be886b3e26bdb0a'
BUILD = 'RB-182027c3f3fc68e3f6a80de6f468963e5cfe889f01f0230ecefeef96837597ba'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, value):
    (HERE/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def main():
    spec = importlib.util.spec_from_file_location('report_collect', HERE.parent/'collect.py')
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    before = json.loads((HERE/'protected-before.json').read_text())
    after = collector.protected_state()
    save('protected-after.json', after)
    checks = {label: before[label] == after[label] for label in ('papers', 'demo', 'native')}
    for table in before['v2']:
        if table not in ('model_requests', 'conversations', 'design_repository_releases'):
            checks['v2_'+table] = before['v2'][table] == after['v2'][table]
    db = sqlite3.connect(DB.as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    old = before['v2']['model_requests']
    digest = hashlib.sha256()
    fields = ','.join('"'+c+'"' for c in old['columns'])
    for row in db.execute('SELECT '+fields+' FROM model_requests ORDER BY rowid LIMIT ?', (old['rows'],)):
        digest.update(json.dumps(tuple(row),sort_keys=True,default=str).encode()+b'\n')
    checks['original_v2_ledger_prefix'] = digest.hexdigest() == old['sha256']
    owners = [r['owner'] for r in json.loads((HERE/'pi-preflight.json').read_text())]
    states = [dict(r) for r in db.execute('SELECT id,status FROM conversations WHERE id IN (?,?,?)', owners)]
    checks['report_owners_idle'] = len(states) == 3 and all(r['status'] == 'IDLE' for r in states)
    requests = [dict(r) for r in db.execute('SELECT * FROM model_requests ORDER BY rowid LIMIT -1 OFFSET ?', (old['rows'],))]
    checks['new_requests_settled'] = bool(requests) and all(r['status'] == 'SETTLED' for r in requests)
    fees = {}
    for owner in owners:
        rows = [r for r in requests if r['owner'] == owner]
        usage = [json.loads(r['usage'] or '{}') for r in rows]
        fees[owner] = {'requests':len(rows), 'local_registered_usd':sum(r['charged'] for r in rows),
            'statuses':sorted({r['status'] for r in rows}),
            'usage':{k:sum(u.get(k,0) for u in usage) for k in ('prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens')}}
    save('cost-final.json', {'owners':fees, 'requests':len(requests),
        'local_registered_usd':sum(r['charged'] for r in requests), 'original_ledger_prefix_preserved':checks['original_v2_ledger_prefix'],
        'billing_records':[{'id':r['id'],'owner':r['owner'],'status':r['status'],'charged':r['charged']} for r in requests]})
    first = min(r['created'] for r in requests)
    runs = []
    for row in db.execute("SELECT data FROM design_events WHERE kind='repository_controller_finished' ORDER BY seq"):
        event = json.loads(row['data']); path = Path(event['receipt_path'])
        receipt = json.loads(path.read_text())
        if receipt['ended'] < first:
            continue
        assert sha(path.read_bytes()) == event['receipt_sha256']
        trace = path.parent/'trace-sealed.jsonl'
        assert sha(trace.read_bytes()) == receipt['trace_sha256']
        facts = []
        for line in trace.open():
            v = json.loads(line)
            if v.get('type') == 'repository_tool_fact' and v.get('time',0) >= receipt['started']:
                args = v.get('input',{}); result = v.get('result',{})
                facts.append({'action':v['action'], 'skill_id':args.get('skill_id'), 'path':args.get('path'),
                    'result_id':result.get('id'), 'reused':result.get('reused'), 'status':result.get('status')})
        runs.append({'owner':receipt['owner'], 'receipt':str(path), 'sha256':event['receipt_sha256'],
            'status':receipt['status'], 'purpose':receipt['purpose'], 'harness_id':receipt['harness_id'],
            'model_profile':receipt['model_profile'], 'actions':facts})
    activations = [dict(r) for r in db.execute('SELECT * FROM skill_activations WHERE updated>=?', (first,))]
    save('pi-consumption.json', {'runs':runs, 'skill_activations':activations,
        'intervention':{'Codex':['shared renderer, tool and checks','report feedback: product task and release reference','sequence direction and self-message review'],
            'Pi':['Power circuit grouping and notes','Firmware source-bound sequence','Lead conclusions, handoff and release']}})
    release = json.loads(db.execute('SELECT value FROM design_repository_releases WHERE id=?', (RELEASE,)).fetchone()['value'])
    archive = REPO/'releases'/(RELEASE+'.zip')
    seal = json.loads(archive.with_suffix('.seal.json').read_text())
    checks['release_seal'] = sha(archive.read_bytes()) == seal['sha256']
    quality = release['required_engineering_report']
    checks['same_candidate'] = quality['system_commit'] == release['target']
    checks['report_passed'] = quality['report_id'] == REPORT and quality['status'] == 'PASS'
    checked = 0
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert json.loads(z.read('manifest.json')) == release
        for name, ref in quality['outputs'].items():
            assert sha(z.read('reports/'+name)) == ref['sha256']; checked += 1
        for name, ref in release['files'].items():
            assert sha(z.read('engineering/'+name)) == ref['sha256']; checked += 1
        for job, record in release['jobs'].items():
            for name, ref in record['artifacts'].items():
                assert sha(z.read('jobs/'+job+'/'+name)) == ref['sha256']; checked += 1
        build_folder = REPO/'reports'/REPORT/'builds'/BUILD
        assert z.read('reports/quality.json') == (build_folder/'quality.json').read_bytes()
        for info in z.infolist():
            path = Path(info.filename)
            assert not path.is_absolute() and '..' not in path.parts
        destination = Path.home()/'Downloads/BF_P01_Engineering_Reports_20261016'
        destination.mkdir(exist_ok=True)
        z.extractall(destination)
    download = destination.with_suffix('.zip')
    shutil.copy2(archive, download)
    for path in (destination/'reports').glob('*.pdf'):
        shutil.copy2(path, destination/path.name)
    checks['download_zip'] = sha(download.read_bytes()) == seal['sha256']
    assert all(checks.values()), checks
    readme = f'''# P01 工程报告与同版审查包\n\n简版：8页。详版：29页。\n\n系统：{release['target']}\n报告：{REPORT}\n构建：{BUILD}\n交付：{RELEASE}\n\nreports/：双PDF、完整连接图、六个回路、CAD/PCB/波形、Pi正文、来源与模板Skill。\nengineering/：89项当前候选工程文件。\njobs/：本版选定原作业的产物。\nmanifest.json：当前工程检查与完整文件摘要。\n\n原理图按实际39器件/172引脚网表连接；固件图采用19条源码定位的交互时序。\n工程结论：2 PASS、2 FAIL、4 UNEVALUABLE；具体供能、DRC、接口和装配问题见报告。\n报告由原Power、Firmware、Lead Pi填充；公共工具与逐页复核由Codex完成。\n\n复用方法：report_prepare → report_schema/report_read → 原专业Pi report_write → Lead report_build → release。\n共享Skill：pi-bf-aiot/packages/bf-harness/resources/skills/bf-engineering-report/。\n'''
    (destination/'README.md').write_text(readme)
    result = {'status':'PASS', 'utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'checks':checks,
        'release_id':RELEASE, 'report_id':REPORT, 'build_id':BUILD, 'system_commit':release['target'],
        'verified_archive_records':checked, 'archive':str(download), 'archive_sha256':seal['sha256'],
        'archive_bytes':download.stat().st_size, 'directory':str(destination), 'owners':states,
        'new_model_requests':len(requests), 'local_registered_usd':sum(r['charged'] for r in requests),
        'new_engineering_jobs':0, 'unchanged_successful_simulation_reruns':0}
    save('result.json', result)
    save('release.json', release)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
