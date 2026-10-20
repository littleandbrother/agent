#!/usr/bin/env python3
"""Read-only verification of the finite design/delegation experiment receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile
import zlib

from v2_common import RUNTIME

ROOT=RUNTIME/'continuous-design'


def read(path):return json.loads(path.read_text())


def verify_consumed(execution,system,blobs):
    if execution['status']!='SUCCEEDED':return
    artifacts=execution['artifacts']
    if artifacts['main.c']['sha256']!=system['files']['firmware/main.c']['sha256']:
        raise ValueError('COMPILER_CONSUMED_OTHER_SOURCE')
    if execution['metrics']['firmware_sha256']!=artifacts['program/firmware']['sha256']:
        raise ValueError('EXECUTED_OTHER_BINARY')
    actual=read(blobs/artifacts['design.json']['sha256'])
    expected=read(blobs/system['files']['design.json']['sha256'])
    if actual!=expected:raise ValueError('SOLVER_CONSUMED_OTHER_DESIGN')


def pdf_summary(path):
    from bfworld.agentlab.design_lab.report_runtime import report_python
    result=subprocess.run([report_python(),'-c',
        'import json,sys; from pypdf import PdfReader; r=PdfReader(sys.argv[1]); '
        'print(json.dumps({"pages":len(r.pages),"nonempty":all(bool(p.extract_text().strip()) for p in r.pages)}))',
        str(path)],capture_output=True,text=True,check=True,timeout=30)
    summary=json.loads(result.stdout)
    if not summary['pages'] or not summary['nonempty']:raise ValueError('EMPTY_REPORT_PDF')
    return {'path':str(path),'pages':summary['pages'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def verify_packaged_report(package, system, release):
    quality=read_record_bytes(package.read('reports/quality.json'))
    report=read_record_bytes(package.read('reports/input.json'))
    if (quality!=release['required_engineering_report'] or
            quality['system_commit']!=system['id'] or report['system_id']!=system['id'] or
            report['files']!=system['files'] or report['task']!=system['task_definition']):
        raise ValueError('PACKAGED_REPORT_CANDIDATE_BINDING')
    for name,ref in quality['outputs'].items():
        if hashlib.sha256(package.read('reports/'+name)).hexdigest()!=ref['sha256']:
            raise ValueError('PACKAGED_REPORT_OUTPUT_CHANGED')
    return quality


def verify_cycles():
    owner=read(RUNTIME/'task-design/owner.json')
    base=read(ROOT/'transition.json')['id'];out=[]
    blobs=RUNTIME/'workbench/design-lab/repository/blobs'
    for cycle in (1,2):
        view=read(ROOT/f'cycle-{cycle}-view.json');p=view['project'];sid=p['submitted']
        systems={s['id']:s for s in view['systems']};s=systems[sid];line=[];cursor=s
        while cursor['id']!=base:
            line.append(cursor)
            if cursor.get('parent') not in systems:raise ValueError('CONTINUOUS_PARENT_CHAIN_BROKEN')
            cursor=systems[cursor['parent']]
        changes=[c for x in line for c in x['design_changes'] if c['path'] in ('design.json','firmware/main.c')]
        if not changes:raise ValueError('REAL_DESIGN_REVISION_REQUIRED')
        from bfworld.agentlab.design_lab.repository_task_execution import descriptor
        desc=descriptor(s)
        executions=[e for e in view['task_executions'] if e['execution_key']==desc['id']]
        if not executions:raise ValueError('CURRENT_INPUT_NOT_EXECUTED')
        e=executions[-1]
        verify_consumed(e,s,blobs)
        for path,digest in desc['inputs'].items():
            if s['files'][path]['sha256'] != digest:raise ValueError('CONSUMED_SOURCE_BINDING')
        for ref in e['artifacts'].values():
            if hashlib.sha256((blobs/ref['sha256']).read_bytes()).hexdigest()!=ref['sha256']:
                raise ValueError('EXECUTION_ARTIFACT_CHANGED')
        releases=[r for r in view['releases'] if r['target']==sid]
        if not releases:raise ValueError('SAME_VERSION_RELEASE_REQUIRED')
        release=releases[-1];archive=RUNTIME/'workbench/design-lab/repository/releases'/(release['id']+'.zip')
        seal=read(archive.with_suffix('.seal.json'))
        if seal['target']!=sid or hashlib.sha256(archive.read_bytes()).hexdigest()!=seal['sha256']:
            raise ValueError('RELEASE_ARCHIVE_CHANGED')
        with zipfile.ZipFile(archive) as package:
            if read_record_bytes(package.read('manifest.json'))!=release:raise ValueError('RELEASE_MANIFEST_CHANGED')
            packaged_quality=verify_packaged_report(package,s,release)
            for name,ref in s['files'].items():
                if hashlib.sha256(package.read('engineering/'+name)).hexdigest()!=ref['sha256']:
                    raise ValueError('RELEASE_SOURCE_BINDING')
            for name,ref in e['artifacts'].items():
                if hashlib.sha256(package.read('execution/'+name)).hexdigest()!=ref['sha256']:
                    raise ValueError('RELEASE_EXECUTION_BINDING')
        report_root=RUNTIME/'workbench/design-lab/repository/task-reports'
        pointer=read(report_root/'by-system'/(sid+'.json'))
        folder=report_root/pointer['id'];quality=read(folder/'quality.json');report=read(folder/'input.json')
        if quality!=packaged_quality or quality['system_commit']!=sid or report['system_id']!=sid:
            raise ValueError('REPORT_CANDIDATE_BINDING')
        for name,ref in quality['outputs'].items():
            if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=ref['sha256']:
                raise ValueError('REPORT_OUTPUT_CHANGED')
        pdfs=[pdf_summary(folder/'task-report.pdf')]
        q=s['current_qualification']
        out.append({'cycle':cycle,'base':base,'system':sid,'changes':changes,'execution':e['id'],
            'qualification':q['status'],'task_passed':q['task_passed'],'release':releases[-1]['id'],
            'pdfs':pdfs,'archive':str(archive),'native_dispatches':len(e['metrics'].get('native_dispatches',[]))})
        base=sid
    return out


def read_record_bytes(raw):return json.loads(raw)


def verify_native_input_uniqueness():
    from run_organization_pilot import read_trial_final
    blobs=RUNTIME/'workbench/design-lab/repository/blobs';keys=[]
    def consume(execution):
        count=len(execution['metrics'].get('native_dispatches',[]))
        if not count:return
        actual=[]
        for path,ref in execution['artifacts'].items():
            if path.endswith('/iterations.json'):
                actual += [i['native']['key'] for i in read(blobs/ref['sha256']) if not i['native']['reused']]
        if len(actual)!=count:raise ValueError('NATIVE_INPUT_COUNT_MISMATCH')
        keys.extend(actual)
    view=read(ROOT/'cycle-2-view.json');base=read(ROOT/'transition.json')['id']
    systems={s['id']:s for s in view['systems']}
    for execution in view['task_executions']:
        source=systems[execution['target']]
        while source['id']!=base and source.get('parent') in systems:source=systems[source['parent']]
        if source['id']==base:consume(execution)
    for entry in read(ROOT/'pilot/registry.json')['trials']:
        folder=ROOT/'pilot/trials'/entry['key']
        for execution in read_trial_final(folder)['view']['task_executions']:consume(execution)
        if (folder/'post-trial-settlement.json').exists():
            keys += read(folder/'post-trial-settlement.json')['unreported_native_dispatches']
    keys += read(ROOT/'reconciliation/proof.json')['retained_partial_native_dispatches']
    if len(keys)!=len(set(keys)):raise ValueError('COMPLETED_NATIVE_INPUT_REDISPATCHED')
    return {'status':'PASS','actual_native_dispatches':len(keys),'unique_native_inputs':len(set(keys)),
        'duplicates':[],'keys':keys,'identity_source':'native.key in coarse/fine iteration receipts',
        'model_requests_during_audit':0,'native_solves_during_audit':0}


def verify_storage_reconciliation(reg, db, blobs):
    """Audit the post-trial failed-execution receipt without replacing its result."""
    folder=ROOT/'reconciliation'
    proof=read(folder/'proof.json');result=read(folder/'result.json')
    execution=result['registered_execution']
    entry=next(e for e in reg['trials'] if e['project_id']==execution['project_id'])
    original=read(ROOT/'pilot/trials'/entry['key']/'final.json')
    source=next(s for s in original['view']['systems'] if s['id']==execution['target'])
    from bfworld.agentlab.design_lab.repository_task_execution import descriptor
    if (result['proof']!=proof or result['new_model_requests'] or result['new_native_solves']
            or execution['status']!='FAILED' or descriptor(source)['id']!=execution['execution_key']
            or proof['system']!=source['id'] or proof['outer_execution']!='INCOMPLETE_AFTER_ENOSPC'):
        raise ValueError('STORAGE_RECONCILIATION_SCOPE_CHANGED')
    saved=[read_record_bytes(row[0]) for row in db.execute(
        'SELECT value FROM design_task_executions WHERE project=?',(entry['project_id'],))]
    if not any(e=={k:v for k,v in execution.items() if k!='reused'} for e in saved):
        raise ValueError('FAILED_EXECUTION_NOT_REGISTERED')
    calls=db.execute('SELECT count(*) FROM model_requests WHERE owner=?',(entry['owner'],)).fetchone()[0]
    if calls!=original['metrics']['model_calls']:raise ValueError('INCIDENT_TRIAL_WAS_RESAMPLED')
    keys=proof['retained_partial_native_dispatches']
    if len(keys)!=len(set(keys)) or execution['metrics']['native_dispatches']!=keys:
        raise ValueError('PARTIAL_NATIVE_ACCOUNTING_CHANGED')
    for ref in execution['artifacts'].values():
        if hashlib.sha256((blobs/ref['sha256']).read_bytes()).hexdigest()!=ref['sha256']:
            raise ValueError('FAILED_EXECUTION_ARTIFACT_CHANGED')
    for key in keys:
        native=blobs.parent/'feedback-native-cache'/key
        completed=read(native/'completed.json')
        if completed['key']!=key or completed['status']!='SUCCEEDED':
            raise ValueError('PARTIAL_NATIVE_RECEIPT_MISSING')
        for name,digest in completed['outputs'].items():
            if hashlib.sha256((native/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('PARTIAL_NATIVE_OUTPUT_CHANGED')
    recovered=blobs.parent/'feedback-native-cache'/proof['native_key']/'system.raw.zlib'
    if hashlib.sha256(zlib.decompress(recovered.read_bytes())).hexdigest()!=proof['raw_sha256']:
        raise ValueError('RECONCILED_RAW_CHANGED')
    return {'trial':entry['key'],'status':'FAILED','execution':execution['id'],
        'partial_native_dispatches':len(keys),'new_model_requests':0,'new_native_solves':0,
        'original_final_sha256':hashlib.sha256((ROOT/'pilot/trials'/entry['key']/'final.json').read_bytes()).hexdigest(),
        'proof_sha256':hashlib.sha256((folder/'proof.json').read_bytes()).hexdigest()}


def verify_pilot():
    from bfworld.agentlab.design_lab.repository_task_execution import descriptor
    from run_organization_pilot import read_trial_final
    reg=read(ROOT/'pilot/registry.json');rows=[];harnesses=set();checked_blobs=set();models=set();frozen=None;preflight_recoveries=[];settlements=[]
    protocol_path=Path(__file__).resolve().parents[1]/'configs/studies/continuous-design-20261018/protocol.json'
    if hashlib.sha256(protocol_path.read_bytes()).hexdigest()!=reg['protocol_sha256']:
        raise ValueError('PILOT_PROTOCOL_CHANGED')
    protocol=read(protocol_path)
    if reg['total_trials']!=20 or reg['automatic_resampling']:
        raise ValueError('FINITE_LIST_CHANGED')
    for case in {e['case'] for e in reg['trials']}:
        matched=[e for e in reg['trials'] if e['case']==case]
        if len({e['task_definition_id'] for e in matched})!=1 or len({
            json.dumps(e['input_hashes'],sort_keys=True) for e in matched})!=1:
            raise ValueError('MATCHED_ARM_INPUTS_DIFFER')
    blobs=RUNTIME/'workbench/design-lab/repository/blobs'
    db=sqlite3.connect((RUNTIME/'workbench/state/workbench.sqlite').as_uri()+'?mode=ro',uri=True)
    for entry in reg['trials']:
        folder=ROOT/'pilot/trials'/entry['key']
        final=read_trial_final(folder);m=final['metrics'];view=final['view']
        settlement_path=folder/'post-trial-settlement.json';late_evaluation_count=0
        if settlement_path.exists():
            value=read(settlement_path)
            late_evaluation_count=len(value['late_executions'])
            if (value['key']!=entry['key'] or value['new_model_requests'] or value['new_native_solves'] or
                    value['original_model_calls']!=m['model_calls'] or
                    value['original_final_sha256']!=hashlib.sha256((folder/'final.json').read_bytes()).hexdigest()):
                raise ValueError('POST_TRIAL_SETTLEMENT_CHANGED')
            stored={read_record_bytes(r[0])['id']:read_record_bytes(r[0]) for r in db.execute(
                'SELECT value FROM design_task_executions WHERE project=?',(entry['project_id'],))}
            native=[]
            for execution in value['late_executions']:
                if execution!=stored.get(execution['id']) or execution['status']!='FAILED':
                    raise ValueError('LATE_EXECUTION_NOT_REGISTERED')
                source=next(s for s in view['systems'] if s['id']==execution['target'])
                if descriptor(source)['id']!=execution['execution_key']:raise ValueError('LATE_EXECUTION_SOURCE_CHANGED')
                for ref in execution['artifacts'].values():
                    if hashlib.sha256((blobs/ref['sha256']).read_bytes()).hexdigest()!=ref['sha256']:
                        raise ValueError('LATE_EXECUTION_ARTIFACT_CHANGED')
                iterations=read(blobs/execution['artifacts']['coarse/iterations.json']['sha256'])
                native += [i['native']['key'] for i in iterations if not i['native']['reused']]
            if native!=value['unreported_native_dispatches']:raise ValueError('LATE_NATIVE_ACCOUNTING_CHANGED')
            for key in native:
                cache=blobs.parent/'feedback-native-cache'/key;completed=read(cache/'completed.json')
                if completed['key']!=key or completed['status']!='SUCCEEDED':raise ValueError('LATE_NATIVE_NOT_COMPLETED')
                for name,digest in completed['outputs'].items():
                    if hashlib.sha256((cache/name).read_bytes()).hexdigest()!=digest:raise ValueError('LATE_NATIVE_CHANGED')
            settlements.append({'trial':entry['key'],'late_executions':len(value['late_executions']),
                'native_dispatches':len(native),'new_model_requests':0,'new_native_solves':0,
                'sha256':hashlib.sha256(settlement_path.read_bytes()).hexdigest()})
        recovery=final.get('preflight_recovery')
        if recovery:
            resumed=read(folder/'recovery-dispatch.json');original_dispatch=read(folder/'dispatch.json')
            if resumed['same_owner']!=entry['owner'] or resumed['same_goal']!=original_dispatch['goal'] or resumed['started']!=recovery['recovery_started']:
                raise ValueError('PREFLIGHT_RECOVERY_GOAL_CHANGED')
            if db.execute('SELECT count(*) FROM model_requests WHERE owner=? AND created<?',
                          (entry['owner'],recovery['recovery_started'])).fetchone()[0]:
                raise ValueError('PREFLIGHT_RECOVERY_HAS_EARLIER_MODEL_REQUEST')
        if final['entry']!=entry:raise ValueError('PILOT_REGISTRATION_CHANGED')
        if not any(p==entry['policy'] for p in view['work_policies']):
            raise ValueError('FROZEN_WORK_POLICY_CHANGED')
        if m['unknown_requests']:raise ValueError('PROVIDER_UNKNOWN_STOP')
        if m['model_calls']>entry['policy']['limits']['requests_per_trial']:raise ValueError('MODEL_ALLOWANCE_EXCEEDED')
        if m['candidate_evaluations']+late_evaluation_count>entry['policy']['limits']['candidate_evaluations_per_trial']:raise ValueError('EVALUATION_ALLOWANCE_EXCEEDED')
        if m['false_adoption']:raise ValueError('FALSE_ADOPTION')
        if len(view['scoped_tasks'])>entry['policy']['max_workers']:raise ValueError('WORKER_ALLOWANCE_EXCEEDED')
        if any(s['task_definition']['id']!=entry['task_definition_id'] for s in view['systems']):
            raise ValueError('MATCHED_TASK_CHANGED')
        initial=next(s for s in view['systems'] if s['id']==entry['initial_system'])
        if {k:v['sha256'] for k,v in initial['files'].items()}!=entry['input_hashes']:
            raise ValueError('MATCHED_INITIAL_INPUT_CHANGED')
        for execution in view['task_executions']:
            source=next(s for s in view['systems'] if s['id']==execution['target'])
            if descriptor(source)['id']!=execution['execution_key']:raise ValueError('PILOT_CONSUMED_SOURCE_BINDING')
            verify_consumed(execution,source,blobs)
            for ref in execution['artifacts'].values():
                digest=ref['sha256']
                if digest not in checked_blobs:
                    if hashlib.sha256((blobs/digest).read_bytes()).hexdigest()!=digest:
                        raise ValueError('PILOT_EXECUTION_ARTIFACT_CHANGED')
                    checked_blobs.add(digest)
        for release in view['releases']:
            source=next(s for s in view['systems'] if s['id']==release['target'])
            archive=RUNTIME/'workbench/design-lab/repository/releases'/(release['id']+'.zip')
            seal=read(archive.with_suffix('.seal.json'))
            if seal['target']!=source['id'] or hashlib.sha256(archive.read_bytes()).hexdigest()!=seal['sha256']:
                raise ValueError('PILOT_RELEASE_CHANGED')
            with zipfile.ZipFile(archive) as package:
                if read_record_bytes(package.read('manifest.json'))!=release:raise ValueError('PILOT_MANIFEST_CHANGED')
                packaged_quality=verify_packaged_report(package,source,release)
                for name,ref in source['files'].items():
                    if hashlib.sha256(package.read('engineering/'+name)).hexdigest()!=ref['sha256']:
                        raise ValueError('PILOT_RELEASE_SOURCE_BINDING')
                key=descriptor(source)['id']
                matching=[e for e in view['task_executions'] if e['execution_key']==key]
                if not matching:raise ValueError('PILOT_RELEASE_EXECUTION_MISSING')
                for name,ref in matching[-1]['artifacts'].items():
                    if hashlib.sha256(package.read('execution/'+name)).hexdigest()!=ref['sha256']:
                        raise ValueError('PILOT_RELEASE_EXECUTION_BINDING')
            pointer=read(RUNTIME/'workbench/design-lab/repository/task-reports/by-system'/(source['id']+'.json'))
            report_folder=RUNTIME/'workbench/design-lab/repository/task-reports'/pointer['id']
            if read(report_folder/'quality.json')!=packaged_quality:raise ValueError('PILOT_REPORT_POINTER_CHANGED')
            for name,ref in packaged_quality['outputs'].items():
                if hashlib.sha256((report_folder/name).read_bytes()).hexdigest()!=ref['sha256']:
                    raise ValueError('PILOT_REPORT_OUTPUT_CHANGED')
            pdf_summary(report_folder/'task-report.pdf')
        for t in view['scoped_tasks']:
            if t['depth']!=1 or t['base_system'] not in {s['id'] for s in view['systems']}:raise ValueError('SCOPED_INPUT_BINDING')
        ledger=[]
        for owner in [entry['owner'],*m['workers']]:
            root=RUNTIME/'workbench/sessions'/owner/'repository-attempts'
            attempts=list(root.glob('*/receipt.json'))
            calls=db.execute('SELECT count(*) FROM model_requests WHERE owner=?',(owner,)).fetchone()[0]
            unsettled=db.execute("SELECT count(*) FROM model_requests WHERE owner=? AND status NOT IN ('SETTLED','FAILED')",(owner,)).fetchone()[0]
            if unsettled:raise ValueError('PILOT_USAGE_UNRECONCILED')
            ledger.extend(db.execute('SELECT status,charged,reserved FROM model_requests WHERE owner=?',(owner,)).fetchall())
            if not attempts and owner!=entry['owner'] and calls==0:continue
            active_attempts=[];skipped=[]
            for path in attempts:
                receipt=read(path)
                if recovery and owner==entry['owner'] and receipt.get('ended',float('inf'))<=recovery['recovery_started']:
                    original=read(folder/'final.json')
                    recorded_error=receipt.get('error')
                    if recorded_error is None:
                        stderr=path.parent/'stderr.log'
                        recorded_error=stderr.read_text().strip() if stderr.exists() else ''
                    if receipt.get('status')!='FAILED' or recorded_error!=original['state']['error'].strip():
                        raise ValueError('INVALID_PREFLIGHT_RECOVERY')
                    skipped.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'error':recorded_error,'model_calls':0})
                else:active_attempts.append(path)
            if recovery and owner==entry['owner'] and len(skipped)!=1:raise ValueError('PREFLIGHT_RECOVERY_ATTEMPT_COUNT')
            if len(active_attempts)!=1:raise ValueError('PILOT_RESAMPLED_OR_RECEIPT_MISSING')
            if skipped:preflight_recoveries.append({'trial':entry['key'],'original_failures':skipped,
                'original_final_sha256':recovery['original_final_sha256'],'same_owner_and_goal':True})
            receipt=read(active_attempts[0]);harnesses.add(receipt['harness_id'])
            if frozen is None:frozen=receipt['harness']
            trace=active_attempts[0].parent/'trace-sealed.jsonl'
            if hashlib.sha256(trace.read_bytes()).hexdigest()!=receipt['trace_sha256']:raise ValueError('PILOT_TRACE_CHANGED')
            for line in trace.read_text().splitlines():
                message=json.loads(line).get('message',{})
                if message.get('role')=='assistant':
                    models.add((message.get('provider'),message.get('model'),message.get('api')))
        cost=sum(charged if status=='SETTLED' else reserved for status,charged,reserved in ledger)
        if len(ledger)!=m['model_calls'] or abs(cost-m['cost_upper_bound_usd'])>1e-9:
            raise ValueError('PILOT_WORKER_BILLING_OMITTED')
        rows.append(m)
    reconciliation=verify_storage_reconciliation(reg,db,blobs)
    db.close()
    if len(harnesses)!=1:raise ValueError('MATCHED_HARNESS_CHANGED')
    if len(models)!=1 or next(iter(models))[1]!=protocol['model']:raise ValueError('MATCHED_MODEL_CHANGED')
    app=Path(__file__).resolve().parents[1]
    package=app.parent/'pi-bf-aiot/packages/bf-agent'
    lab=app/'packages/python/bfworld/src/bfworld/agentlab'
    checked_sources=[]
    for group,folder in (('files',package),('python_bindings',lab/'design_lab'),
                         ('context_bindings',lab),('engineering_bindings',lab)):
        for name,digest in frozen[group].items():
            if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('CONSUMED_HARNESS_SOURCE_CHANGED:'+group+'/'+name)
            checked_sources.append(group+'/'+name)
    return {'trials':rows,'harness_id':next(iter(harnesses)),
        'source_pairs':2,'source_trials':4,'organization_trials':16,'same_task_and_sources':True,
        'verified_execution_blobs':len(checked_blobs),'models':[list(m) for m in models],
        'consumed_sources':checked_sources,'zero_call_preflight_recoveries':preflight_recoveries,
        'post_trial_settlements':settlements,
        'post_trial_storage_reconciliation':reconciliation}


def main():
    from bf_v2_environment import environment
    profile,env=environment(RUNTIME)
    executable=profile['paths']['CAD_PYTHON']
    if Path(sys.executable).resolve()!=Path(executable).resolve():
        os.execve(executable,[executable,str(Path(__file__).resolve()),*sys.argv[1:]],env)
    os.environ.update(env)
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['cycles','pilot','all'],default='all');args=p.parse_args()
    out={}
    if args.stage in ('cycles','all'):out['cycles']=verify_cycles()
    if args.stage in ('pilot','all'):out['pilot']=verify_pilot()
    if args.stage=='all':
        out['native_input_audit']=verify_native_input_uniqueness()
        artifact=Path(__file__).resolve().parents[1]/'docs/agentlab/architecture-v2/continuous-design-20261018/results/native-input-audit.json'
        artifact.write_text(json.dumps(out['native_input_audit'],ensure_ascii=False,indent=2)+'\n')
    (ROOT/('verification-'+args.stage+'.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':main()
