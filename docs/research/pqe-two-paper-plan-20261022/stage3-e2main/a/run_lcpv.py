"""Execute each of four frozen LC-PV inputs once; no search, retry or tuning."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import signal
import time

from freeze_inputs import HERE, ROOT, CAN, PACKAGE, save, digest, identity
from freeze_lcpv import PRIVATE
from readback_lcpv import review


def main():
    assert not (PRIVATE/'execution-freeze.json').exists(), 'EXECUTION_ALREADY_RESERVED_NO_RETRY'
    freeze=json.loads((PRIVATE/'freeze.json').read_text())
    input_path=Path(freeze['inputs_path'])
    assert digest(input_path)==freeze['inputs_file_sha256']
    inputs=json.loads(input_path.read_text())
    assert {n:identity(v) for n,v in inputs.items()}==freeze['input_hashes']
    assert digest(Path(freeze['original_service_path']))==freeze['original_service_file_sha256']
    from bfworld.agentlab.pqe20261022 import lcpv20261023 as model
    for item in inputs.values():
        model.validate(item)
        assert identity(item['Task']['service'])==freeze['original_service_object_sha256']
    source=model.dependency_identity()
    spec=importlib.util.spec_from_file_location('unchanged_usage_gate',HERE.parents[1]/'stage3-f1first/a/qualify_inputs.py')
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    gate=previous.usage_gate()
    free=shutil.disk_usage(ROOT).free
    assert free>=11_500_000_000
    save(PRIVATE/'execution-freeze.json',{'schema':'pqe-lcpv-execution-freeze-v1','package':PACKAGE,
        'at_utc':datetime.now(timezone.utc).isoformat(),'input_freeze_sha256':digest(PRIVATE/'freeze.json'),
        'model_sources':source,'runner_sha256':digest(Path(__file__)),
        'independent_readback_sha256':digest(HERE/'readback_lcpv.py'),
        'targeted_tests':{'command':'PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -p test_pqe_lcpv20261023.py -v',
                          'passed':6,'complete_mission_inputs_in_tests':0},
        'budget':freeze['limits'],'free_before_bytes':free,'provider_usage_gate':gate})
    began=time.monotonic();rows=[]
    for name,item in inputs.items():
        assert model.dependency_identity()==source
        previous.usage_gate()
        directory=PRIVATE/name
        assert not directory.exists(),'ATTEMPT_EXISTS_NO_RETRY:'+name
        directory.mkdir(parents=True)
        save(directory/'attempt.json',{'name':name,'input_sha256':identity(item),'new_complete_chain_reserved':1,
             'at_utc':datetime.now(timezone.utc).isoformat(),'per_input_remaining':0,'retry_or_replacement':False})
        def expired(signum,frame):
            raise TimeoutError('LC_PV_WALL_CAP_STOP_NO_RETRY')
        remaining=freeze['limits']['wall_cap_s']-(time.monotonic()-began)
        assert remaining>0,'LC_PV_WALL_CAP_EXHAUSTED'
        signal.signal(signal.SIGALRM,expired);signal.alarm(max(1,int(remaining)))
        started=time.monotonic()
        try:
            raw=model.simulate(item)
        finally:
            signal.alarm(0)
        wall=time.monotonic()-started
        save(directory/'raw.json',raw)
        readback=review(item,raw)
        save(directory/'independent-readback.json',readback)
        row={'name':name,'input_sha256':identity(item),'raw_path':str(directory/'raw.json'),
             'raw_file_sha256':digest(directory/'raw.json'),'raw_result_sha256':raw['result_sha256'],
             'readback_path':str(directory/'independent-readback.json'),
             'readback_file_sha256':digest(directory/'independent-readback.json'),
             'wall_s':wall,'execution_status':raw['execution_status'],'verdict':readback['verdict'],
             'gates':readback['gates'],'facts':readback['facts']}
        rows.append(row)
        del raw
        retained=sum(p.stat().st_size for p in PRIVATE.rglob('*') if p.is_file())
        assert retained<freeze['limits']['retained_cap_bytes'],'LC_PV_RETAINED_CAP_STOP'
        print(json.dumps({'name':name,'status':'EXECUTED_ONCE_AND_INDEPENDENTLY_READ',
                          'verdict':row['verdict'],'wall_s':wall,'retained_bytes':retained}),flush=True)
    final_gate=previous.usage_gate()
    assert model.dependency_identity()==source
    receipt={'schema':'pqe-lcpv-a-receipt-v1','package':PACKAGE,'owner':'campaign-a',
             'at_utc':datetime.now(timezone.utc).isoformat(),'visibility':'A_S0_PRIVATE_NOT_B_H_G',
             'status':'FOUR_PROSPECTIVE_COMPLETE_CHAIN_INPUTS_EXECUTED_AND_INDEPENDENTLY_READ',
             'freeze_path':str(PRIVATE/'freeze.json'),'freeze_sha256':digest(PRIVATE/'freeze.json'),
             'execution_freeze_sha256':digest(PRIVATE/'execution-freeze.json'),'sources':source,'rows':rows,
             'counts':{'new_complete_chain_inputs':4,'per_input':1,'private_raw_memory_readbacks':4,'raw_reexecutions':0,
                       'parameter_scans':0,'replacements':0,'paid_requests':0,'native':0,'hardware':0},
             'resource':{'available_before_bytes':free,'available_after_bytes':shutil.disk_usage(ROOT).free,
                 'elapsed_s':time.monotonic()-began,'retained_bytes_excluding_receipt':sum(p.stat().st_size for p in PRIVATE.rglob('*') if p.is_file()),
                 'retained_cap_bytes':100_000_000,'estimated_peak_additional_bytes':500_000_000,'new_environments':0,'new_backups':0},
             'provider_usage_gate_after':final_gate,
             'qualification':'Constructed coefficients/one-second hybrid model with analytical thermal and stored-fact service audits. No measured profile, switching/RF/MCU qualification, continuous-time convergence, Agent adaptation or F2 transfer claim.',
             'limitations':['Uniform single-string shading only; fixed declared PV junction temperature.',
                 'Controlled input law is an explicit constructed PMIC, not a vendor fit or MPPT implementation.',
                 'Activity energy impulses and paid positive completion durations are behavioral, not transistor or NVM device traces.',
                 'One-second source integration is the discrete model; no finer-grid verification budget or claim.',
                 'Temperature reference is the designated interior air point; contents core and full enclosure heat transport excluded.',
                 'Device sees powered sensor and actual availability only; missing/unknown observations do not establish normality.']}
    save(HERE/'A-LCPV-RECEIPT.json',receipt)
    public={'schema':'pqe-lcpv-public-model-contract-v1','package':PACKAGE,
        'status':'EXECUTABLE_CONSTRUCTED_CHAIN_AND_INDEPENDENT_READBACK_COMPLETE',
        'model_id':model.MODEL_ID,'complete_chain_inputs_executed':4,'paid_requests':0,
        'model_contract':{'light':'Normalized 380..780 nm constructed SPD; spectral photon/EQE current, active cell area, uniform transmission and incidence; no lux-to-watt conversion.',
            'electrical':'Loaded single-diode I(Vinput); explicit controlled-input cold/operating PMIC relation; storage/ESR/efficiency/leakage and activity costs recomputed for each supplied program.',
            'information':'Specified interior air-point truth, first-order probe lag, quantization; only powered acquisition is available to program.',
            'program':'Paid boot/sense/SAVE/TX/ACK/sync phases; atomic commit after completion, reset-dependent memory/clock, FIFO rank and actual decoded CRC receive/dedup.',
            'services':'Unchanged independent 24h LC-PV service: cold start, 60s sampling including darkness, record retention/order/dedup, accurate acquisition time, 120s recovery history and 10s acquisition-to-receive fresh samples.',
            'missingness':'Missing samples, unknown-time records, retained backlog, late delivery and duplicates are separate facts. Gap markers never satisfy strict sampling; no no-anomaly-to-normality inference.'},
        'reused_modules':['campaign20261019.ar frame and digital receiver','campaign20261019.ar_service visible fields and rank','coupled.engine input_current ESR/constant-power primitive'],
        'gaps':['Measured/calibrated spectral I-V/PMIC/load profiles','Nonuniform per-cell shading and arbitrary junction temperature','Physical RF/NVM/MCU and switching qualification','Continuous-time grid convergence','Held-out LC-PV Agent/F2 transfer'],
        'private_boundary':'Private qualification inputs, purposes, individual outcomes, raw records and reference choices are A/S0 only; this public contract supplies no target solution or selection signal.'}
    save(HERE/'LC-PV-PUBLIC-MODEL-CONTRACT.json',public)
    print(json.dumps({'receipt_path':str(HERE/'A-LCPV-RECEIPT.json'),'receipt_sha256':digest(HERE/'A-LCPV-RECEIPT.json'),
                     'public_contract_path':str(HERE/'LC-PV-PUBLIC-MODEL-CONTRACT.json'),
                     'new_inputs':4,'free_after_bytes':shutil.disk_usage(ROOT).free},indent=2))


if __name__=='__main__':
    main()
