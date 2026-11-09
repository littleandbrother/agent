"""One current-task LC initial input; old qualification inputs never run."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import signal
import time
from common import HERE,ROOT,CAN,STUDY,SRC,PACKAGE,save,digest,identity,module
import lc_host


def main():
    private=STUDY/'lcpv-private'
    assert not (private/'registry.json').exists() and not (private/'initial').exists(),'LC_INITIAL_ALREADY_ATTEMPTED_NO_RETRY'
    freeze=json.loads((private/'freeze.json').read_text())
    public=lc_host.load_public()
    inputs=lc_host.bind_inputs(public['Design'],public)
    from bfworld.agentlab.pqe20261022 import lcpv20261023 as model
    model.validate(inputs)
    # Newly added binding checks are static, not extra complete-world inputs.
    wrong={**public['Design'],'sample_period_s':29.0}
    try:
        lc_host.validate_flat(public,wrong)
    except ValueError:
        pass
    else:
        raise AssertionError('OUTSIDE_CURRENT_ACTION_BOX_ACCEPTED')
    assert set(inputs['Design'])==set(public['design_fields'])
    assert all(inputs['Program'][k]==public['Design'][k] for k in public['program_fields'])
    assert inputs['Task']['service']['dark_interval_s']==[23400,66600]
    prior=module('e3lc_exact_usage_gate',HERE.parents[1]/'stage3-f1first/a/qualify_inputs.py')
    gate=prior.usage_gate()
    free=shutil.disk_usage(ROOT).free;assert free>=11_000_000_000
    source=model.dependency_identity()
    directory=private/'initial';directory.mkdir(parents=True)
    save(directory/'attempt.json',{'package':PACKAGE,'at_utc':datetime.now(timezone.utc).isoformat(),
        'new_initial_scientific_reserved':1,'input_sha256':identity(inputs),'sources':source,
        'host_binding_sha256':digest(HERE/'lc_host.py'),'generic_evaluator_sha256':digest(lc_host.REVIEW),
        'static_binding_checks':'PASS; current domain reject, flat-field round trip and new-window binding; zero full simulation in checks',
        'retry_or_instance_replacement':False,'allowed_for_learning':False,'free_before_bytes':free})
    save(directory/'input.json',inputs)
    def timeout(signum,frame):
        raise TimeoutError('LC_INITIAL_WALL_CAP_STOP')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(freeze['limits']['initial_wall_cap_s'])
    started=time.monotonic()
    try:
        raw=model.simulate(inputs)
    finally:
        signal.alarm(0)
    wall=time.monotonic()-started
    save(directory/'raw.json',raw)
    assessment=lc_host.evaluate(inputs,raw)
    save(directory/'assessment.json',assessment)
    result=lc_host.public_result(public['Design'],inputs,raw,assessment,wall_s=wall)
    save(directory/'public-result.json',result)
    assert model.dependency_identity()==source
    assert digest(SRC/'lcpv20261023.py')==freeze['source_model_sha256']
    gate_after=prior.usage_gate()
    receipt={'schema':'pqe-e3lc-a-lc-initial-receipt-v1','package':PACKAGE,'owner':'campaign-a',
        'at_utc':datetime.now(timezone.utc).isoformat(),'status':'ONE_NEW_DEVELOPMENT_INITIAL_COMPLETE',
        'task_id':public['Task']['task_id'],'allowed_for_learning':False,'initial_verdict':assessment['verdict'],
        'failures':assessment['failures'],'facts':assessment['facts'],'gates':assessment['gates'],
        'freeze_path':str(private/'freeze.json'),'freeze_sha256':digest(private/'freeze.json'),
        'public_task_path':str(lc_host.PUBLIC),'public_task_file_sha256':digest(lc_host.PUBLIC),
        'consumer_sources':source,'host_binding_path':str(HERE/'lc_host.py'),'host_binding_sha256':digest(HERE/'lc_host.py'),
        'evaluator_path':str(lc_host.REVIEW),'evaluator_sha256':digest(lc_host.REVIEW),
        'raw_path':str(directory/'raw.json'),'raw_file_sha256':digest(directory/'raw.json'),'raw_result_sha256':raw['result_sha256'],
        'assessment_path':str(directory/'assessment.json'),'assessment_file_sha256':digest(directory/'assessment.json'),
        'initial_public_result_path':str(directory/'public-result.json'),'initial_public_result_sha256':digest(directory/'public-result.json'),
        'counts':{'new_initial_scientific_inputs':1,'paid_requests':0,'native':0,'old_qualification_inputs_reexecuted':0,
                  'replacement_inputs':0,'complete_simulation_calls_in_static_checks':0,'independent_memory_readback':1},
        'resource':{'available_before_bytes':free,'available_after_bytes':shutil.disk_usage(ROOT).free,'wall_s':wall,
                    'retained_current_LC_bytes_excluding_receipt':sum(p.stat().st_size for p in private.rglob('*') if p.is_file())},
        'usage_gate_before':gate,'usage_gate_after':gate_after,
        'handoff':'S0 reuses this initial and routes every selected current flat Design through lc_host.bind_inputs -> unchanged model.simulate -> lc_host.evaluate -> lc_host.public_result. No old qualification configuration/results, ideal air truth or final assessment enter H0/B. One actual H0 development episode only; no F2 claim.'}
    receipt_path=HERE/'A-LC-INITIAL-RECEIPT.json';save(receipt_path,receipt)
    registry={'schema':'pqe-e3lc-private-lc-registry-v1','package':PACKAGE,'task_id':public['Task']['task_id'],
        'eligibility':'ELIGIBLE_CONSTRUCTED_WORLD_DEVELOPMENT_INPUT','allowed_for_learning':False,
        'public_task_path':str(lc_host.PUBLIC),'public_task_file_sha256':digest(lc_host.PUBLIC),
        'host_task_path':freeze['host_task_path'],'host_task_file_sha256':freeze['host_task_file_sha256'],
        'initial_input_path':str(directory/'input.json'),'initial_input_file_sha256':digest(directory/'input.json'),
        'initial_public_result_path':str(directory/'public-result.json'),'initial_public_result_sha256':digest(directory/'public-result.json'),
        'initial_raw_path':str(directory/'raw.json'),'initial_raw_file_sha256':digest(directory/'raw.json'),
        'initial_assessment_path':str(directory/'assessment.json'),'initial_assessment_file_sha256':digest(directory/'assessment.json'),
        'host_module_path':str(HERE/'lc_host.py'),'host_module_file_sha256':digest(HERE/'lc_host.py'),
        'evaluator_path':str(lc_host.REVIEW),'evaluator_file_sha256':digest(lc_host.REVIEW),
        'scientific_sources':source,'initial_exact_cache_key':lc_host.exact_cache_key(public['Design']),
        'receipt':{'path':str(receipt_path),'sha256':digest(receipt_path)},
        'contract_task_id_explanation':'Low-level consumer task_id remains its frozen LC-PV-STRICT-24H-v1 contract. Public task_id, host Task.instance_id, full Task/input hashes and all scenario data identify the new LC-PV-E3LC-DEV-20261023-v1 instance. No low-level science was changed.'}
    save(private/'registry.json',registry)
    print(json.dumps({'status':receipt['status'],'task_id':receipt['task_id'],'initial_verdict':assessment['verdict'],
        'failures':assessment['failures'],'registry_path':str(private/'registry.json'),'registry_sha256':digest(private/'registry.json'),
        'receipt_path':str(receipt_path),'receipt_sha256':digest(receipt_path),'new_scientific_inputs':1,
        'retained_LC_bytes':receipt['resource']['retained_current_LC_bytes_excluding_receipt']},indent=2))


if __name__=='__main__':
    main()
