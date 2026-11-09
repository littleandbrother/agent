"""One initial per prospectively frozen task, reusing existing scientific consumers."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import signal
import time

from freeze_inputs import HERE, ROOT, CAN, PRIVATE, SRC, PACKAGE, identity, digest, save


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    assert not (PRIVATE / 'registry.json').exists(), 'INITIALS_ALREADY_SEALED_NO_RERUN'
    freeze = json.loads((PRIVATE / 'freeze.json').read_text())
    path = Path(freeze['input_catalog_path'])
    assert digest(path) == freeze['input_catalog_byte_sha256']
    tasks = json.loads(path.read_text())
    shared = module('prior_accounting_gate_only', HERE.parents[1] / 'stage3-f1first/a/qualify_inputs.py')
    helper = module('e2main_independent_initial_readback', CAN / 'studies/pqe20261022/engineering/stage2/native/review_coupled.py')
    from bfworld.agentlab.pqe20261022.adapter import validate_design, source_identity
    from bfworld.agentlab.pqe20261022.engineering import build_engineering_model, consume_engineering_model
    from bfworld.agentlab.pqe20261022.executor import execute_design
    from bfworld.agentlab.pqe20261022.evaluator import evaluate
    from bfworld.agentlab.pqe20261022.public_projection import project_result
    gate = shared.usage_gate()
    free = shutil.disk_usage(ROOT).free
    assert free >= 11_500_000_000
    began, roles, rows = time.monotonic(), {}, []
    for role, task in tasks.items():
        assert all(digest(SRC / n) == h for n, h in freeze['scientific_sources'].items())
        shared.usage_gate()
        binding = freeze['bindings'][role]
        assert identity(task) == binding['Task_sha256']
        design, problem, dt = task['initial_design'], task['initial_problem'], task['integration']['dt_s']
        assert identity({'Task': task, 'Design': design, 'Problem': problem, 'dt_s': dt,
                         'scientific_sources': freeze['scientific_sources']}) == binding['input_commitment_sha256']
        base = {'task_id': task['task_id'], 'task_path': str(path), 'task_json_key': role,
                'task_file_sha256': digest(path), 'task_sha256': identity(task),
                'design_sha256': identity(design), 'problem_sha256': identity(problem),
                'input_commitment_sha256': binding['input_commitment_sha256'], 'dt_s': dt}
        directory = PRIVATE / 'initial' / role
        assert not directory.exists(), 'ATTEMPT_ALREADY_EXISTS_NO_RETRY:' + role
        directory.mkdir(parents=True)
        save(directory / 'attempt.json', {'package': PACKAGE, 'role': role, 'at_utc': datetime.now(timezone.utc).isoformat(),
             'input_commitment_sha256': binding['input_commitment_sha256'], 'new_scientific_inputs_reserved': 1,
             'retry_or_replacement_permitted': False})
        start = time.monotonic()
        raw = None
        try:
            validate_design(task, design)
            model = build_engineering_model(task, design)
            consumed = consume_engineering_model(model, task, design)
            assert consumed['model_sha256'] == identity(model)
            remaining = freeze['limits']['initial_wall_cap_s'] - (time.monotonic() - began)
            assert remaining > 0, 'INITIAL_WALL_CAP_EXHAUSTED'
            def timeout(signum, frame):
                raise TimeoutError('INITIAL_WALL_CAP_NO_RETRY')
            signal.signal(signal.SIGALRM, timeout)
            signal.alarm(max(1, int(remaining)))
            try:
                raw = execute_design(task, design, dt_s=dt, engineering_model=model)
            finally:
                signal.alarm(0)
            save(directory / 'raw.json', raw)
            assert identity({k:v for k,v in raw.items() if k != 'result_sha256'}) == raw['result_sha256']
            assert raw['task_sha256'] == identity(task) and raw['design_sha256'] == identity(design)
            assessment = evaluate(task, design, raw)
            save(directory / 'assessment.json', assessment)
            reviewed = helper.review('e2main-initial-' + role, shared.InMemoryRaw(raw), task)
            independent = reviewed['independent_service']
            for name in ('verdict', 'failures', 'unknown', 'truth', 'matches'):
                assert independent[name] == assessment[name], 'INDEPENDENT_AUDIT_MISMATCH:' + name
            assert independent['missing'] == assessment['missed_event_ids']
            assert reviewed['energy']['within_tolerance'], 'ENERGY_AUDIT_FAILURE_STOP'
            sources = source_identity()
            assert {n:sources[n] for n in freeze['scientific_sources']} == freeze['scientific_sources']
            public = project_result({'schema_version':'pqe-public-result-v2', 'execution_status':raw['execution_status'],
                'task_id':task['task_id'], 'task_sha256':identity(task), 'input_sha256':identity(design),
                'design':design, 'problem':problem, 'sources':sources, 'model_valid':raw['model_valid'],
                'domain_errors':raw['domain_errors'], 'program_version':raw['program_version'],
                'engineering_model_sha256':raw['engineering_model_sha256'],
                'facts': {**{k:raw[k] for k in ('trace','activity','records','packets','energy','peak_handle_force_n','minimum_tx_terminal_v','program_state')},
                          'receiver_records':assessment['receiver_records']},
                'public_check':{'verdict':assessment['verdict'],'failures':assessment['failures'],
                                'unknown':assessment['unknown'],'received_count':len(assessment['receiver_records'])},
                'usage':{'paid_model_requests':0,'numerical_inputs':1,'wall_s':time.monotonic()-start},
                'result_sha256':raw['result_sha256']})
            save(directory / 'public-result.json', public)
            legal = raw['model_valid'] and not raw['domain_errors'] and raw['execution_status'] == 'COMPLETE'
            qualification = {'role':role,'task_id':task['task_id'],'eligible':bool(legal),
                'initial_verdict':independent['verdict'],'truth_count':len(independent['truth']),
                'initial_service':independent,'independent_readback':reviewed,
                'initial_label': ('NO_CHANGE_CONTROL' if independent['verdict']=='PASS' else 'CONTROL_DESIGNATION_WITHDRAWN_TASK_RETAINED') if role=='d16' else ('FAILURE_REPAIR_ENTRY' if independent['verdict']=='FAIL' else 'INITIAL_PASS_DESIGN_OR_CONTROL_ENTRY'),
                'entry_type':freeze['entry_types'][role], 'wall_s':time.monotonic()-start,
                'scope':'Only this frozen initial; no repair search, feasible-domain or all-domain conclusion.'}
            save(directory / 'qualification.json', qualification)
            roles[role] = {**base, 'eligibility':'ELIGIBLE' if legal else 'MODEL_UNSUPPORTED',
                'reason':None if legal else {'domain_errors':raw['domain_errors'],'execution_status':raw['execution_status']},
                'qualification_status':'INITIAL_VALID_COMPLETE' if legal else 'INITIAL_INVALID',
                'initial_public_result_path':str(directory/'public-result.json'),
                'initial_public_result_sha256':digest(directory/'public-result.json'),
                'initial_public_result_object_sha256':identity(public),
                'raw_path':str(directory/'raw.json'),'raw_file_sha256':digest(directory/'raw.json'),
                'raw_result_sha256':raw['result_sha256'], 'qualification_path':str(directory/'qualification.json'),
                'qualification_file_sha256':digest(directory/'qualification.json'),
                'exact_cache_key':identity({'task':task,'design':design,'dt':dt,'scientific_source':freeze['scientific_sources']})}
            rows.append({k:qualification[k] for k in ('role','eligible','initial_verdict','truth_count','initial_label','entry_type','wall_s')})
        except Exception as error:
            # Audit mismatches are global stop conditions, not unsupported-task exclusions.
            if isinstance(error, AssertionError) and ('AUDIT' in str(error) or 'MISMATCH' in str(error)):
                raise
            reason = type(error).__name__ + ':' + str(error)
            save(directory/'failure.json', {'role':role,'reason':reason,'raw_was_produced':raw is not None,'no_retry':True})
            roles[role] = {**base,'eligibility':'MODEL_UNSUPPORTED','reason':reason}
            rows.append({'role':role,'eligible':False,'reason':reason})
    assert all(digest(SRC/n)==h for n,h in freeze['scientific_sources'].items())
    assert digest(Path(freeze['source_catalog_path'])) == freeze['source_catalog_sha256']
    gate_after = shared.usage_gate()
    registry = {'schema':'pqe-e2main-private-registry-v1','package':PACKAGE,
                'visibility':'S0_HOST_PRIVATE_NOT_B_OR_H_G_FORMATION','roles':roles,
                'scientific_sources':freeze['scientific_sources'],'freeze_path':str(PRIVATE/'freeze.json'),
                'freeze_file_sha256':digest(PRIVATE/'freeze.json'),
                'initial_reuse':'Reuse exact qualified initial results; no new initial solve.',
                'counts':{'attempted_initial_inputs':4,'new_raws':sum('raw_path' in row for row in roles.values()),
                          'paid_requests':0,'native':0,'searches':0,'replacement_tasks':0}}
    save(PRIVATE/'registry.json', registry)
    inventory = [{'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)}
                 for root in (PRIVATE,HERE) for p in sorted(root.rglob('*')) if p.is_file()]
    receipt = {'schema':'pqe-e2main-a-initial-receipt-v1','package':PACKAGE,'owner':'campaign-a',
               'at_utc':datetime.now(timezone.utc).isoformat(),'registry_path':str(PRIVATE/'registry.json'),
               'registry_sha256':digest(PRIVATE/'registry.json'),'rows':rows,'counts':registry['counts'],
               'scientific_sources_and_old_catalog_unchanged':True,'provider_usage_before':gate,'provider_usage_after':gate_after,
               'resource':{'available_before_bytes':free,'available_after_bytes':shutil.disk_usage(ROOT).free,
                           'A_door_retained_bytes_excluding_receipt':sum(x['bytes'] for x in inventory),
                           'elapsed_s':time.monotonic()-began,'new_environments':0,'new_backups':0},
               'inventory_excluding_receipt':inventory,'next':'Door freeze implementation ended; hand registry to S0 and enter isolated LC-PV implementation. Representative main-comparison readback later; no initial re-solve.'}
    save(HERE/'A-INITIAL-RECEIPT.json',receipt)
    print(json.dumps({'registry_path':str(PRIVATE/'registry.json'),'registry_sha256':digest(PRIVATE/'registry.json'),
                      'rows':rows,'counts':registry['counts'],'free_after_bytes':shutil.disk_usage(ROOT).free},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
