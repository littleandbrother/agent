"""Prospective, operator-only study preparation after sealed native reference.

No model is called; no historical request, study cap or usage is reset.
The two declared trajectories run serially through the existing application.
"""
import argparse, json, time
from pathlib import Path
from bfworld.agentlab.store import Store, identity, canonical
from bfworld.agentlab.provider import Provider, MODEL
from bfworld.agentlab.simulation_tasks import TASK_ROOT, load_task
from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json
from bfworld.agentlab.door_system.contracts import template_hash

PROTOCOL='door-loading-release-20261006'

def prepare(root):
    root=Path(root);ref=root/'sealed-reference-v2';result=json.loads((ref/'result.json').read_text())
    if result.get('source_stable') is not True or not result['qualification']['nominal_prediction_eligible']:
        raise ValueError('NO_AGENT_BASELINE_NOT_QUALIFIED')
    if json.loads((ref/'system-manifest.json').read_text())['executor_sha256']!=template_hash():
        raise ValueError('BASELINE_EXECUTOR_CHANGED')
    output=root/'pilot';output.mkdir(exist_ok=True)
    protocol={'schema_version':'door-design-pilot-v2','id':PROTOCOL,'task_id':'door-motion-structure-v2','model':MODEL,
        'purpose':'Two serial exploratory real Pi trajectories using primary-reference retrieval and a full loading/release native apparatus; no method comparison.',
        'pi_trials':[{'id':'nominal-r1','initial':'sealed-reference-v2'},{'id':'domain-r1','initial':'screen-v2 gap28'}],
        'pi_max_candidates_per_trial':3,'pi_max_wall_s_per_trial':1800,'requested_paid_allocation_usd':1.,
        'max_usd_per_trial':.5,'max_usd_per_request':.19,'study_wall_s':21600,
        'native_gate':{'result_path':str(ref/'result.json'),'sha256':file_hash(ref/'result.json')},
        'executor_sha256':template_hash(),'task_hash':load_task('door-motion-structure-v2')['task_hash'],
        'cache_policy':'No success cache in D4; each native candidate independently runs the solver and half-step check; report outer job time separately.',
        'intervention_policy':'No operator-chosen next design or result rewriting. Tool/runtime repairs and subsequent prompts are interventions. All failed and out-of-domain candidates retained.',
        'claim_boundary':'Source-supported bounded configuration refinement under nominal hard-magnet/beam/load assumptions. No positive self-powered reference established; not architecture topology synthesis or physical reproduction.'}
    path=TASK_ROOT/'loading-release-protocol.json'
    if path.exists() and json.loads(path.read_text())!=protocol:raise ValueError('PROSPECTIVE_PROTOCOL_IMMUTABLE')
    write_json(path,protocol);write_json(output/'protocol.json',protocol)
    store=Store(root.parents[1]/'state');provider=Provider(store)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM research_model_studies WHERE protocol=?',(PROTOCOL,)).fetchone()
        if old:return json.loads((output/'authorization.json').read_text())
        before=dict(db.execute('SELECT * FROM model_limits WHERE id=1').fetchone())
        rows=[dict(r) for r in db.execute('SELECT * FROM model_requests')]
        held=sum(r['charged'] if r['status']=='SETTLED' else r['reserved'] for r in rows)
        now=time.time();expiry=now+21600
        auth='Persistent human authorization to continue paid experiments and2026-10-06 implementation approval. USD1/6h is the operator prospective bounded allocation; not a newly user-specified numeric cap.'
        db.execute('INSERT INTO research_model_studies VALUES(?,?,?,?,?,?)',(PROTOCOL,now,expiry,1.,MODEL,auth))
        db.execute('INSERT INTO research_usage_continuations VALUES(?,?,?,?)',(PROTOCOL,now,expiry,auth+' Unknown reservations remain fully held; exploratory-only carry-forward, no inferred usage.'))
        for row in rows:
            if row['status']=='UNKNOWN':db.execute('INSERT INTO research_usage_carryforwards VALUES(?,?,?,?,?)',(PROTOCOL,row['id'],identity(row),auth,now))
        # Add a prospective allocation once. Existing limits, caps and rows remain.
        total=max(before['total_usd'],held)+1.
        db.execute('UPDATE model_limits SET total_usd=?,expires=? WHERE id=1',(total,max(before['expires'],expiry)))
        after=dict(db.execute('SELECT * FROM model_limits WHERE id=1').fetchone())
    receipt={'protocol':PROTOCOL,'protocol_sha256':file_hash(path),'created':now,'expires':expiry,'model':MODEL,
        'authorization':auth,'before_limits':before,'after_limits':after,'old_requests_sha256':identity(rows),
        'old_request_count':len(rows),'held_upper_usd':held,'historical_unknown_count':sum(r['status']=='UNKNOWN' for r in rows),
        'historical_usage_unchanged':True,'model_calls_during_preparation':0}
    write_json(output/'authorization.json',receipt)
    for trial in protocol['pi_trials']:
        domain=trial['id']=='domain-r1'
        feedback={'initial_status':'out_of_domain','scope':'Independent resistive screening, not PMIC task failure',
            'candidate':{'mechanical':{'gap_mm':28,'closed_dz_mm':0,'polarity':-1}},'limit_mm':8} if domain else {
                'candidate':json.loads((ref/'design-spec.json').read_text()),'result_sha256':file_hash(ref/'result.json'),
                'metrics':{k:result['metrics'][k] for k in ('peak_tip_mm','peak_piezo_V','peak_storage_V','peak_supply_V','tx_completed','received_events')},
                'qualification':result['qualification'],'drive_ledger':result['metrics']['drive_ledger']}
        prompt=('在冻结的门动作任务中做一次真实、可复核的设计修订。先读取door-system的skill，使用bf_reference搜索并获取ViPSN-Pluck及LTC3588-1原始论文/数据表；核对电容所在节点、单位、UVLO和时间条件，不能把文献结论直接当成我们的测量。'+
            '公开初始反馈：'+canonical(feedback)+'。自主选择下一步，不需要等待操作者给出参数。最多运行3个候选，保持已有任务、模型、电流与数值条件；可改变实际支架位置/磁极、储能和广播间隔。'+
            '每次运行后读取波形、驱动能量账和程序/接收结果，再决定后续动作。记录修订依据与可证伪预测。用submit封存一个已实际运行的候选和理由，允许如实提交失败。简短中文持续说明；不得声称硬件成功或80%复现。')
        write_json(output/(trial['id']+'-request.json'),{'trial_id':trial['id'],'protocol_id':PROTOCOL,'text':prompt})
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.root),indent=2))
