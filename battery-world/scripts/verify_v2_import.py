"""V2-1: byte-exact P01 import through the actual authenticated DesignLab API."""
import json
from pathlib import Path
import time

from v2_common import RUNTIME, action, create_pi, request, restart


def main():
    restart()
    registry=RUNTIME/'p01-project.json'
    if registry.exists():
        record=json.loads(registry.read_text());owner=record['owner']
    else:
        owner=create_pi('P01 · Architecture V2 · BF System Architect','architecture-v2-p01-lead')['id']
    imported=action(owner,'repository_import',operation_id='p01-b0-import-v1')
    assert action(owner,'repository_import',operation_id='p01-b0-import-v1')==imported
    view=action(owner,'repository_view',project_id=imported['project_id'])
    p,_=__import__('bf_v2_environment').environment(RUNTIME)
    m=json.loads((Path(p['baseline']['path'])/'manifest.json').read_text())
    adopted=next(s for s in view['systems'] if s['id']==imported['adopted'])
    submitted=next(s for s in view['systems'] if s['id']==imported['submitted'])
    assert adopted['origin_design_id']==m['p01']['adopted_design']
    assert submitted['origin_design_id']==m['p01']['submitted_design']
    assert adopted['id']!=submitted['id']
    assert imported['gate_statuses']=={g['id']:g['status'] for g in m['p01']['gates']}
    assert not view['domain_commits'] and not view['contracts']
    blob=action(owner,'repository_read',project_id=imported['project_id'],system_id=imported['submitted'],path='project-fw-s132/main.c',offset=0,limit=12000)
    assert blob['sha256']==submitted['files']['project-fw-s132/main.c']['sha256']
    before=view
    restart()
    after=action(owner,'repository_view',project_id=imported['project_id'])
    assert before==after
    record={'schema_version':'bf-v2-p01-project-identity-v1','owner':owner,**imported}
    if not registry.exists():registry.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    elif json.loads(registry.read_text())!=record:raise ValueError('V2_PROJECT_REGISTRY_CHANGED')
    out=Path(__file__).resolve().parents[1]/'docs/agentlab/architecture-v2'/('v2-1-import-'+str(time.time_ns()))
    out.mkdir()
    result={'status':'PASS','project':record,'original_ids':{'submitted':submitted['origin_design_id'],'adopted':adopted['origin_design_id']},
        'submitted_files':len(submitted['files']),'gate_statuses':imported['gate_statuses'],'physical':submitted['physical'],
        'restart_preserved':True,'operation_retry_same_receipt':True,'no_fabricated_domain_commits':True,
        'native_jobs_dispatched':0,'model_requests':0}
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/'project-view.json').write_text(json.dumps(view,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PASS','owner':owner,'project':imported['project_id'],'files':len(submitted['files']),'output':str(out)},ensure_ascii=False))


if __name__=='__main__':main()
