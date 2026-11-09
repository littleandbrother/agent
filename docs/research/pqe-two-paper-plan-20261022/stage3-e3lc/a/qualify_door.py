"""Two fixed private executions; no parameter search or Task replacement."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import signal
import time
from common import HERE,ROOT,CAN,STUDY,SRC,PACKAGE,save,digest,identity,module


def main():
    private=STUDY/'private'
    assert not (private/'registry.json').exists(),'QUALIFICATION_ALREADY_CLOSED'
    freeze=json.loads((private/'freeze.json').read_text())
    path=Path(freeze['input_path'])
    assert digest(path)==freeze['input_file_sha256']
    inputs=json.loads(path.read_text())
    assert {n:identity(v) for n,v in inputs.items()}==freeze['input_hashes']
    task=json.loads(Path(freeze['task_path']).read_text())
    assert identity(task)==freeze['task_sha256']
    prior=module('exact_historical_usage_gate',HERE.parents[1]/'stage3-f1first/a/qualify_inputs.py')
    helper_path=CAN/'studies/pqe20261022/engineering/stage2/native/review_coupled.py'
    helper=module('e3_door_independent',helper_path)
    from bfworld.agentlab.pqe20261022.adapter import validate_design,source_identity
    from bfworld.agentlab.pqe20261022.engineering import build_engineering_model,consume_engineering_model
    from bfworld.agentlab.pqe20261022.executor import execute_design
    from bfworld.agentlab.pqe20261022.evaluator import evaluate
    from bfworld.agentlab.pqe20261022.public_projection import project_result
    usage_before=prior.usage_gate()
    free=shutil.disk_usage(ROOT).free
    assert free>=11_000_000_000
    rows=[];began=time.monotonic();public_path=None;initial_raw=None
    for name,item in inputs.items():
        assert all(digest(SRC/n)==v for n,v in freeze['scientific_sources'].items())
        prior.usage_gate()
        design,problem,dt=item['Design'],item['Problem'],task['integration']['dt_s']
        validate_design(task,design)
        model=build_engineering_model(task,design)
        consume_engineering_model(model,task,design)
        directory=private/name
        assert not directory.exists(),'ATTEMPT_EXISTS_NO_RETRY'
        directory.mkdir(parents=True)
        save(directory/'attempt.json',{'package':PACKAGE,'name':name,'input_sha256':identity(item),
             'at_utc':datetime.now(timezone.utc).isoformat(),'new_scientific_reserved':1,'retries':0})
        def timeout(signum,frame):
            raise TimeoutError('DOOR_PRIVATE_WALL_CAP_STOP')
        remaining=freeze['limits']['wall_cap_s']-(time.monotonic()-began)
        assert remaining>0
        signal.signal(signal.SIGALRM,timeout);signal.alarm(max(1,int(remaining)))
        started=time.monotonic()
        try:
            raw=execute_design(task,design,dt_s=dt,engineering_model=model)
        finally:
            signal.alarm(0)
        wall=time.monotonic()-started
        raw_path=directory/'raw.json';save(raw_path,raw)
        assert raw['result_sha256']==identity({k:v for k,v in raw.items() if k!='result_sha256'})
        assessment=evaluate(task,design,raw);save(directory/'assessment.json',assessment)
        independent=helper.review('e3-local-scope-'+name,prior.InMemoryRaw(raw),task)
        service=independent['independent_service']
        for key in ('verdict','failures','unknown','truth','matches'):
            assert service[key]==assessment[key],'INDEPENDENT_AUDIT_MISMATCH_STOP'
        assert service['missing']==assessment['missed_event_ids']
        assert independent['energy']['within_tolerance'] and independent['force']['within_limit']
        valid=raw['model_valid'] and not raw['domain_errors'] and raw['execution_status']=='COMPLETE'
        row={'name':name,'input_sha256':identity(item),'task_sha256':identity(task),'design_sha256':identity(design),
             'problem_sha256':identity(problem),'raw_path':str(raw_path),'raw_file_sha256':digest(raw_path),
             'raw_result_sha256':raw['result_sha256'],'model_valid':raw['model_valid'],'domain_errors':raw['domain_errors'],
             'execution_status':raw['execution_status'],'valid_complete':bool(valid),'verdict':service['verdict'],
             'wall_s':wall,'received_unique':independent['unique_received_count'],'truth_count':len(service['truth']),
             'independent_service':service,'independent_readback':independent,
             'boot_count':sum(a['action']=='boot' for a in raw['activity']),'wire_count':len(raw['packets'])}
        save(directory/'qualification.json',row)
        rows.append(row)
        if name=='initial':
            assert row['boot_count']==0 and row['wire_count']==0,'PRIVATE_NECESSARY_BOUND_CONTRADICTION_STOP'
            sources=source_identity()
            public=project_result({'schema_version':'pqe-public-result-v2','execution_status':raw['execution_status'],
                'task_id':task['task_id'],'task_sha256':identity(task),'input_sha256':identity(design),
                'design':design,'problem':problem,'sources':sources,'model_valid':raw['model_valid'],'domain_errors':raw['domain_errors'],
                'program_version':raw['program_version'],'engineering_model_sha256':raw['engineering_model_sha256'],
                'facts':{**{k:raw[k] for k in ('trace','activity','records','packets','energy','peak_handle_force_n','minimum_tx_terminal_v','program_state')},
                         'receiver_records':assessment['receiver_records']},
                'public_check':{'verdict':assessment['verdict'],'failures':assessment['failures'],'unknown':assessment['unknown'],'received_count':len(assessment['receiver_records'])},
                'usage':{'paid_model_requests':0,'numerical_inputs':1,'wall_s':wall},'result_sha256':raw['result_sha256']})
            public_path=directory/'public-result.json';save(public_path,public);initial_raw=raw_path
        print(json.dumps({'name':name,'valid_complete':bool(valid),'verdict':row['verdict'],'received_unique':row['received_unique'],'truth_count':row['truth_count'],'wall_s':wall}),flush=True)
        del raw
    bound=json.loads((private/'local-necessary-bound.json').read_text())
    assert digest(private/'local-necessary-bound.json')==freeze['bound_file_sha256']
    established=bound['strict_margin_v']>0 and all(r['valid_complete'] for r in rows) and rows[0]['verdict']=='FAIL' and rows[1]['verdict']=='PASS'
    status='ELIGIBLE' if established else 'NOT_ESTABLISHED'
    usage_after=prior.usage_gate()
    assert all(digest(SRC/n)==v for n,v in freeze['scientific_sources'].items())
    assert digest(Path(freeze['source_catalog_path']))==freeze['source_catalog_sha256']
    receipt={'schema':'pqe-e3-private-qualification-receipt-v1','package':PACKAGE,'owner':'campaign-a',
        'at_utc':datetime.now(timezone.utc).isoformat(),'eligibility':status,
        'visibility':'A_S0_PRIVATE_PROOF_REFERENCE_AND_RESULTS_NEVER_B_HG_PARTICIPANTS',
        'reason':'Valid whole-horizon local C/ESR voltage exclusion and one legal expanded-domain full-service witness.' if established else 'The fixed two-input qualification did not establish the required pair; paid DOOR E3 closed without Task replacement or method-failure conclusion.',
        'freeze_path':str(private/'freeze.json'),'freeze_sha256':digest(private/'freeze.json'),
        'bound_path':str(private/'local-necessary-bound.json'),'bound_sha256':digest(private/'local-necessary-bound.json'),
        'scientific_sources':freeze['scientific_sources'],'sources_and_old_catalog_unchanged':True,'rows':rows,
        'counts':{'private_new_scientific_inputs':2,'authorized_max':12,'unused_private_allowance':10,'paid_requests':0,'native':0,'scans':0,'Task_replacements':0,'raw_reexecutions':0},
        'resource':{'available_before_bytes':free,'available_after_bytes':shutil.disk_usage(ROOT).free,
                    'retained_bytes_excluding_receipt':sum(p.stat().st_size for p in private.rglob('*') if p.is_file()),'elapsed_s':time.monotonic()-began},
        'usage_gate_before':usage_before,'usage_gate_after':usage_after,
        'boundary':'Local necessary exclusion is not a full Task impossibility result. Private witness does not solve the task for participants or show B3 increment. No first-crossing startup premise, prior halfspeed/cap-axis replay, hidden service change or hardware claim.',
        'next':'Door qualification ends now. S0 may execute declared E3/OPT only if eligible; A independently enters new LC task work.'}
    receipt_path=HERE/'A-DOOR-QUALIFICATION.json';save(receipt_path,receipt)
    roles={}
    if established:
        roles['scope']={'task_id':task['task_id'],'task_path':str(private/'task.json'),
            'task_file_sha256':digest(private/'task.json'),'task_sha256':identity(task),
            'initial_public_result_path':str(public_path),'initial_public_result_sha256':digest(public_path),
            'initial_raw_path':str(initial_raw),'raw_path':str(initial_raw),'raw_file_sha256':rows[0]['raw_file_sha256'],
            'raw_result_sha256':rows[0]['raw_result_sha256'],'dt_s':task['integration']['dt_s'],
            'exact_cache_key':identity({'task':task,'design':task['initial_design'],'dt':task['integration']['dt_s'],'scientific_source':freeze['scientific_sources']}),
            'eligibility':'ELIGIBLE','expanded_active_variables':list(task['design_domain'])}
    registry={'schema':'pqe-e3-private-registry-v1','package':PACKAGE,'eligibility':status,'reason':receipt['reason'],
        'qualification_receipt':{'path':str(receipt_path),'sha256':digest(receipt_path)},'roles':roles,
        'expanded_active_variables':list(task['design_domain']),'scientific_sources':freeze['scientific_sources'],
        'initial_reuse':'Reuse exact initial public/raw input; no extra initial simulation. Scope-matched group changes only initial Problem activity and provisional fixed choices, never Task or Design.',
        'private_boundary':'Do not forward private proof/qualification/witness. Public Task and materials are separately frozen in shared/.'}
    save(private/'registry.json',registry)
    print(json.dumps({'eligibility':status,'registry_path':str(private/'registry.json'),'registry_sha256':digest(private/'registry.json'),
        'qualification_path':str(receipt_path),'qualification_sha256':digest(receipt_path),'new_scientific_inputs':2,'free_after_bytes':shutil.disk_usage(ROOT).free},indent=2))


if __name__=='__main__':
    main()
