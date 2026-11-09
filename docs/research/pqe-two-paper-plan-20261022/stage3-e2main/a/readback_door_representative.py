"""One stored D04 consequence readback, with zero new scientific execution."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

from freeze_inputs import HERE, CAN, PRIVATE, SRC, PACKAGE, save, digest, identity


class MemoryOnce:
    def __init__(self,value):
        self.value,self.reads=value,0

    def read_text(self):
        self.reads+=1
        assert self.reads==1
        return json.dumps(self.value,allow_nan=False)

    def __str__(self):
        return 'single stored raw read, one independent in-memory pass'


def main():
    output=HERE/'A-DOOR-REPRESENTATIVE-READBACK.json'
    assert not output.exists(),'REPRESENTATIVE_ALREADY_READ_NO_REPEAT'
    registry=json.loads((PRIVATE/'registry.json').read_text())
    row=registry['roles']['d04']
    task=json.loads(Path(row['task_path']).read_text())[row['task_json_key']]
    assert identity(task)==row['task_sha256']
    directory=HERE.parent/'s0/episodes/d04-r1-b0/actions/01'
    decision=json.loads((directory/'decision.json').read_text())
    raw_path=directory/'raw.json'
    data=raw_path.read_bytes()  # Exactly one stored raw file read, no new solve.
    raw=json.loads(data)
    raw_byte_sha256=hashlib.sha256(data).hexdigest()
    assert identity({k:v for k,v in raw.items() if k!='result_sha256'})==raw['result_sha256']
    actual=decision['actual_design']
    changes={k:{'before':task['initial_design'][k],'after':v} for k,v in actual.items() if v!=task['initial_design'][k]}
    assert changes=={'debounce_s':{'before':0.0,'after':.06}}
    assert raw['task_sha256']==identity(task) and raw['design_sha256']==identity(actual)
    assert decision['parent_design_sha256']==identity(task['initial_design'])
    assert decision['problem']==task['initial_problem']
    for name,expected in registry['scientific_sources'].items():
        assert digest(SRC/name)==expected and decision['sources'][name]==expected
    helper_path=CAN/'studies/pqe20261022/engineering/stage2/native/review_coupled.py'
    spec=importlib.util.spec_from_file_location('e2main_representative_independent',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    stream=MemoryOnce(raw)
    readback=helper.review('e2main-d04-r1-b0-debounce-only',stream,task)
    assert readback['independent_service']['verdict']=='PASS'
    assert readback['unique_received_count']==12 and len(readback['independent_service']['truth'])==12
    assert readback['energy']['within_tolerance'] and readback['force']['within_limit']
    initial=json.loads(Path(row['qualification_path']).read_text())
    assert digest(Path(row['qualification_path']))==row['qualification_file_sha256']
    before=initial['independent_readback']
    receipt={'schema':'pqe-e2main-a-representative-causal-readback-v1','package':PACKAGE,'owner':'campaign-a',
        'at_utc':datetime.now(timezone.utc).isoformat(),'status':'INDEPENDENT_READBACK_PASS',
        'raw_path':str(raw_path),'raw_file_sha256':raw_byte_sha256,'raw_result_sha256':raw['result_sha256'],
        'task_sha256':identity(task),'design_sha256':identity(actual),'design_changes':changes,
        'decision_path':str(directory/'decision.json'),'decision_sha256':digest(directory/'decision.json'),
        'initial_qualification_path':row['qualification_path'],'initial_qualification_sha256':row['qualification_file_sha256'],
        'before':{'verdict':before['independent_service']['verdict'],'received_unique':before['unique_received_count'],
                  'truth_events':len(before['independent_service']['truth']),'failures':before['independent_service']['failures']},
        'after':{'verdict':readback['independent_service']['verdict'],'received_unique':readback['unique_received_count'],
                 'truth_events':len(readback['independent_service']['truth']),'failures':readback['independent_service']['failures']},
        'independent_readback':readback,'helper_path':str(helper_path),'helper_sha256':digest(helper_path),
        'counts':{'new_scientific_inputs':0,'stored_raw_file_reads':1,'independent_memory_passes':stream.reads,
                  'original_initial_raw_rereads':0,'paid_requests':0,'native':0},
        'causal_scope':'Same complete frozen Task, initial conditions and five scientific modules; only debounce changed 0 to0.06. Stable real transitions remained12; unique receiver events decreased60 to12 and spurious/duplicate failure cleared. Independent current-level/program/CRC/queue/force/energy replay supports this local modeled consequence.',
        'attribution_boundary':'This is B0 strong generic Agent success, not evidence of B3/full_h increment, unseen-family transfer, learned H, an optimal debounce or hardware reliability. All-method paired effects remain S0/B analysis.'}
    save(output,receipt)
    print(json.dumps({'status':receipt['status'],'path':str(output),'sha256':digest(output),
                      'before':receipt['before'],'after':receipt['after'],'new_science':0},indent=2))


if __name__=='__main__':
    main()
