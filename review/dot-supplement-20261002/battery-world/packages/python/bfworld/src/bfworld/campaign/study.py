"""Preregistered finite-budget computational pilot, not a benchmark claim.

Final confirmation is evaluated only after all learning and trial actions end.
The controller never sends its source, reference parameters or final outcomes
to participant code. All baseline arms retain identical raw public history and
can write/run their own Python; conditions add distinct accumulation mechanisms.
"""
from __future__ import annotations
import json
import random
import time
from pathlib import Path
from dataclasses import asdict,replace
from bfworld.kernel.canonical import canonical_hash,write_canonical_json,file_hash
from bfworld.coupled.engine import Design,Reference,execute
from bfworld.coupled.artifacts import seal_run as seal_coupled
from .sandbox import execute as run_program,preflight as sandbox_preflight
from .provider import Provider,MODEL
from .budget import Ledger,BudgetStop

SYSTEM='''You are a general coding agent designing a battery-free sensing and diagnosis node.
You may experiment, execute your own Python, inspect history, and submit a design.
Return one JSON object per turn. Use an explicit short decision_summary, not private reasoning.
Actions: {"action":"experiment","candidate_id":"...","decision_summary":"...","predicted_pass":true};
{"action":"python","code":"def plan(ctx): ...","decision_summary":"..."};
{"action":"submit","candidate_id":"...","claim_pass":true,"decision_summary":"..."}.
Python plan(ctx) receives the complete public task and history, runs without filesystem/network access,
and returns JSON. Submission is a claim, never self-qualification. You have at most 3 turns.
Do not invent observations. An untested design may be submitted but remains an unverified claim.
Choose a physically successful, resource-feasible design using few experiments; all formal final
verification is independent of your claimed result. Validated evidence is preferable to confidence.
No internet, no reference source, no hidden test access. JSON only.'''

def immutable(path:Path,value):
    if path.exists():
        if json.loads(path.read_text())!=value:raise RuntimeError('immutable artifact mismatch: '+str(path))
    else:write_canonical_json(path,value)

def task(index:int,split:str):
    # Parameters and permutation are fixed before model calls. No outcome tuning.
    specs=[(.0026,2.60,120.,False,1.),(.0013,2.50,95.,False,1.),(.0033,2.65,145.,False,7.),(.0010,2.45,80.,False,1.),(.0030,2.7,125.,True,1.),(.0022,2.6,110.,False,1.)]
    peak,initial,rpm,lost,surge=specs[index%len(specs)]
    ref=Reference(source_peak_a=peak,initial_v=initial,rpm=rpm,receiver_loss=lost,surge_after_s=.9,surge_multiplier=surge,device_session=f'{split}-{index}')
    designs=[replace(Design(),capacitance_f=c,esr_ohm=r) for c,r in [(.00033,18),(.00068,12),(.001,8),(.0015,5),(.0022,4),(.0047,8)]]
    designs.extend([replace(Design(),clamp_v=None),replace(Design(),model_threshold=120)])
    random.Random(4100+index).shuffle(designs)
    candidates=[{'id':f'design-{i+1}',**asdict(d)} for i,d in enumerate(designs)]
    public={'id':f'{split}-{index}','source_family':'rotary','mission':'Acquire 128 samples, correct diagnosis, receiver-confirmed delivery before 1.1 s; no brownout/overvoltage; C <=4700 uF.',
      'conditions':{'rpm':rpm,'nominal_source_peak_a':peak,'initial_v':initial,'off_v':1.8,'max_v':3.6,'regulator_efficiency':.82,'duration_s':1.6,'receiver_guaranteed':False,'possible_source_surge':surge>1},
      'candidates':candidates,'qualification':'Final confirmation includes unseen source phase and 5% source variation; final feedback never reaches learning.'}
    return {'public':public,'reference':asdict(ref)}

def design_of(t,candidate):
    obj=next((d for d in t['public']['candidates'] if d['id']==candidate),None)
    if obj is None:raise ValueError('unknown candidate identity')
    return Design(**{k:v for k,v in obj.items() if k!='id'})

def observe(t,candidate,root:Path,final=False):
    ref=Reference(**t['reference'])
    if final:ref=replace(ref,source_phase_rad=.73,source_peak_a=ref.source_peak_a*.95,device_session=ref.device_session+'-sealed-confirmation')
    run=execute(design_of(t,candidate),ref)
    bundle=seal_coupled(root,run)
    return {'task_id':t['public']['id'],'candidate_id':candidate,'design':asdict(design_of(t,candidate)),
       'physical':run['physical_mission_pass'],'summary':run['summary'],'run_hash':run['content_hash'],
       'artifact':str(bundle),'receiver_delivered':run['request']['receive_s'] is not None,
       'energy_residual':run['energy_ledger']['normalized_residual'],
       'sample_count':len(run['request']['samples']),'prediction':run['request']['prediction'],
       'conditions':t['public']['conditions']}

def protocol():
    obj={'schema_version':'fixed-model-campaign-v1','study_id':'bc-pilot-20260906-v1','model':MODEL,
      'provider_version':'DeepSeek-V4-Flash-0731 (service-reported alias; not immutable weights)',
      'pricing_source':'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
      'pricing_snapshot_date':'2026-09-06','peak_cny_per_million':{'cache_miss_input':3,'output':9},
      'budget':{'user_trial_cny':2,'user_total_strictly_less_than_cny':20,'engineering_total_cny':19,'max_calls':120,'max_tokens':600000,'max_wall_seconds':3600,'max_trial_turns':3},
      'hypothesis':'Executable accumulation improves future design relative to equal-history retrieval and text memory without false admission.',
      'falsifier':'No improvement, higher total cost, invalid prediction, false admission or sealed regression.',
      'b_arms':['raw-history','text-memory','executable-knowledge'],
      'b_task_indices':[1,3],'b_replicates':[0,1],
      'c_arms':['static','memory-only','harness-only','world-only','joint','joint-without-qualification'],
      'c_generations':2,'c_tasks_per_generation':2,
      'c_indices':[[2,5],[0,4]],
      'learning_indices':[0,2,5],'qualification_indices':[6,7,8],
      'candidate_generation_calls':3,'classical':'enumerate finite design catalogue; all probes charged as local experiments',
      'all_arms_allow_python':True,'same_raw_history_across_matched_arms':True,
      'candidate_dual_gate':{'explanation':'>=85% correct pass predictions on 24 held-out candidate interventions; no false-safe predictions','use':'qualified prediction filtering must reduce median deterministic catalogue-search probes over the same unfiltered order without losing solvable tasks'},
      'final_confirmation':'5% reduced source, phase 0.73; computed after every trial and generation has frozen; never fed to learner',
      'statistical_unit':'whole campaign and task family; two replicates are descriptive, not independent scientific significance',
      'claim_boundary':'Computational finite-catalogue pilot, not T0-T4 official benchmark, hardware, full physical validation or demonstrated RSI.',
      'stop_rules':['uncertain paid call','missing usage','model mismatch','sandbox leak','strict budget/time stop','hash drift','no tuning on final confirmation']}
    obj['content_hash']=canonical_hash(obj);return obj

class Campaign:
    def __init__(self,repo:Path):
        self.repo=repo;self.private=repo/'.bfworld/paid-campaign';self.private.mkdir(parents=True,exist_ok=True)
        self.artifacts=repo/'runs/campaign/bc-pilot-20260906-v1';self.artifacts.mkdir(parents=True,exist_ok=True)
        self.doc=repo/'docs/campaign';self.ledger=Ledger(self.private/'cost.sqlite');self.provider=Provider(repo/'.bfworld/private/deepseek.key',self.ledger)
        self.sandbox=repo/'.bfworld/participants';self.p=protocol();self.started=time.time()
        state_path=self.private/'clock.json'
        # Preparation and waiting for a user continuation are not paid execution.
        # Once the first call is reserved, restarting never resets the clock.
        if state_path.exists() and self.ledger.summary()['calls']:
            self.started=json.loads(state_path.read_text())['started']
    def prepare(self):
        immutable(self.doc/'protocol.json',self.p)
        identity=self.provider.models();isolation=sandbox_preflight(self.sandbox,self.repo/'PROJECT.yaml')
        tasks={f'{split}-{i}':task(i,split) for split,indices in [('learning',[0,2,5]),('qualification',[6,7,8]),('b',[1,3]),('c',[0,2,4,5])] for i in indices}
        immutable(self.private/'tasks.json',tasks)
        history=[]
        for index in self.p['learning_indices']:
            t=task(index,'learning')
            for choice in t['public']['candidates'][::2]:history.append(observe(t,choice['id'],self.artifacts/'experiments'))
        # Participant history carries facts, not absolute host artifact paths.
        for h in history:h.pop('artifact',None)
        immutable(self.artifacts/'equal-history.json',history)
        report={'status':'pass','provider':identity,'isolation':isolation,'history_hash':canonical_hash(history),'tasks_hash':canonical_hash(tasks),
          'protocol_hash':self.p['content_hash'],'budget':self.ledger.summary(),'paid_calls_made':self.ledger.summary()['calls']}
        write_canonical_json(self.doc/'preflight.json',report);return report
    def call(self,key,trial,messages):
        if self.ledger.summary()['calls']==0:
            self.started=time.time()
            write_canonical_json(self.private/'clock.json',{'started':self.started,'origin':'first paid dispatch; preflight idle excluded'})
        if time.time()-self.started>3600:raise BudgetStop('campaign wall-clock cap reached')
        response=self.provider.complete(key,trial,messages)
        immutable(self.artifacts/'calls'/f'{key}.json',response)
        if response['finish_reason']!='stop':return {'action':'invalid','error':'non-stop provider finish','decision_summary':'Truncated or incomplete JSON is not an accepted action.'},response
        try:action=json.loads(response['content'])
        except (ValueError,TypeError):action={'action':'invalid','error':'invalid JSON'}
        return action,response
    def compile(self,generation,history):
        path=self.artifacts/f'knowledge/generation-{generation}.json'
        if path.exists():return json.loads(path.read_text())
        prompt='''Compile reusable scientific design knowledge from these public experiments. Return JSON:
{"text_memory":"concise evidence-grounded rules, limitations and counterexamples",
 "code":"def plan(ctx): ...", "scope":{"source_family":"rotary"},
 "policy":{"order_by":"capacitance_f","descending":false}, "decision_summary":"brief explicit rationale"}.
plan(ctx) must return {"scope_ok": bool, "predictions": {candidate_id: {"pass":bool,"minimum_input_v":number}}}.
ctx has source_family, conditions (rpm, nominal_source_peak_a, initial_v, off_v, regulator_efficiency, etc.)
and candidates (id, capacitance_f, esr_ohm, start_v, tx_power_w, clamp_v, model_threshold, etc.).
For non-rotary sources return scope_ok false and predictions {}. Do not use task IDs, fitted lookup tables,
reference imports, filesystem, network or execution of a simulator. Standard-library math is available.
Make an executable physically motivated approximation with an explicit applicability boundary, not a
promise of universal correctness. policy.order_by is capacitance_f or esr_ohm; descending is boolean.
No hidden data. You may retain, revise or reject explanations. JSON only. Public history follows:\n'''+json.dumps(history)
        candidate,response=self.call(f'learn-{generation}',f'learn-{generation}',[{'role':'system','content':'You are a general coding agent compiling experimentally grounded reusable knowledge. JSON only.'},{'role':'user','content':prompt}])
        obj={'schema_version':'executable-knowledge-candidate-v2','generation':generation,'candidate':candidate,'origin_call':response['id'],
          'history_hash':canonical_hash(history),'program_hash':canonical_hash(candidate.get('code','')),'source_model':MODEL,'status':'candidate'}
        obj['content_hash']=canonical_hash(obj);immutable(path,obj);return obj
    def qualify(self,capsule):
        g=capsule['generation'];path=self.artifacts/f'knowledge/qualification-{g}.json'
        if path.exists():return json.loads(path.read_text())
        code=capsule['candidate'].get('code','');checks=[];errors=[];use=[];scope=False
        try:scope=run_program(code,{'source_family':'solar','conditions':{},'candidates':[]},self.sandbox).get('scope_ok') is False
        except Exception as e:errors.append(str(e)[:300])
        for i in self.p['qualification_indices']:
            t=task(i,'qualification');truth={c['id']:observe(t,c['id'],self.artifacts/'qualification') for c in t['public']['candidates']}
            try:pred=run_program(code,t['public'],self.sandbox)
            except Exception as e:errors.append(str(e)[:300]);pred={'scope_ok':False,'predictions':{}}
            for cid,obs in truth.items():
                guess=pred.get('predictions',{}).get(cid,{}).get('pass')
                checks.append({'task':t['public']['id'],'candidate':cid,'predicted':guess,'observed':obs['physical']['value'],'run_hash':obs['run_hash'],'correct':type(guess)is bool and guess==obs['physical']['value'],'false_safe':guess is True and not obs['physical']['value']})
            order=[c['id'] for c in sorted(t['public']['candidates'],key=lambda c:c['capacitance_f'])]
            filtered=[cid for cid in order if pred.get('predictions',{}).get(cid,{}).get('pass') is True]
            def probes(ids):return next((j+1 for j,cid in enumerate(ids) if truth[cid]['physical']['value']),None)
            baseline=probes(order);learned=probes(filtered)
            use.append({'task':t['public']['id'],'baseline_probes':baseline,'learned_probes':learned,'solvability_retained':baseline is None or learned is not None})
        accuracy=sum(c['correct'] for c in checks)/max(1,len(checks));false_safe=sum(c['false_safe'] for c in checks)
        explanation=scope and accuracy>=.85 and false_safe==0 and not errors
        comparable=[u for u in use if u['baseline_probes'] is not None and u['learned_probes'] is not None]
        import statistics
        useful=all(u['solvability_retained'] for u in use) and bool(comparable) and statistics.median(u['learned_probes'] for u in comparable)<statistics.median(u['baseline_probes'] for u in comparable)
        report={'generation':g,'candidate_hash':capsule['content_hash'],'program_hash':capsule['program_hash'],'explanation_pass':explanation,'use_pass':useful,'scope_pass':scope,
          'accuracy':accuracy,'false_safe':false_safe,'checks':checks,'use_tests':use,'errors':errors,
          'status':'qualified-for-pilot' if explanation and useful else 'rejected',
          'authority':'trusted controller; isolated participant cannot write receipt; qualification set is development feedback, not final confirmation',
          'physical_confirmation':False}
        report['content_hash']=canonical_hash(report);immutable(path,report);return report
    def trial(self,phase,arm,t,replicate,history,capsule,qualification):
        trial_id=f'{phase}-{arm}-{t["public"]["id"]}-r{replicate}';path=self.artifacts/'trials'/f'{trial_id}.json'
        if path.exists():return json.loads(path.read_text())
        qualified=qualification['status']=='qualified-for-pilot';candidate=capsule['candidate'];program_used=False;extra={}
        if arm in ('text-memory','memory-only'):extra['text_memory']=candidate.get('text_memory','')
        if arm in ('executable-knowledge','world-only','joint','joint-without-qualification'):
            if qualified or arm=='joint-without-qualification':
                try:extra['program_output']=run_program(candidate.get('code',''),t['public'],self.sandbox);extra['program_code']=candidate.get('code','');program_used=True
                except Exception as e:extra['program_error']=str(e)[:250]
            else:extra['knowledge_status']='candidate rejected; no program injected'
        if arm in ('harness-only','joint','joint-without-qualification'):
            policy=candidate.get('policy',{});field=policy.get('order_by')
            if field in ('capacitance_f','esr_ohm') and type(policy.get('descending'))is bool and (qualified or arm=='joint-without-qualification'):
                extra['workflow_policy']=policy
        context={**t['public'],'history':history,'accumulated':extra,'turns_remaining':3}
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(context)}];steps=[];submission=None;probes=0
        for turn in range(3):
            action,response=self.call(trial_id+f'-turn{turn}',trial_id,messages)
            facts={};kind=action.get('action') if isinstance(action,dict) else 'invalid'
            try:
                if kind=='experiment':
                    facts=observe(t,action.get('candidate_id'),self.artifacts/'experiments');facts.pop('artifact',None);probes+=1
                elif kind=='python':facts={'result':run_program(action.get('code',''),context,self.sandbox)}
                elif kind=='submit':
                    design_of(t,action.get('candidate_id'));submission={'candidate_id':action['candidate_id'],'claim_pass':action.get('claim_pass') is True};facts={'submission_recorded':True,'qualified':False}
                else:facts={'error':'unknown action; choose experiment, python or submit'}
            except (ValueError,KeyError,TypeError) as e:facts={'error':str(e)[:300]}
            steps.append({'turn':turn,'model_call_id':response['id'],'action':action,'observation':facts,'usage':response['usage']})
            messages.extend([{'role':'assistant','content':response['content']},{'role':'user','content':json.dumps({'tool_result':facts,'turns_remaining':2-turn,'instruction':'Return your next JSON action. Final turn must submit to finish.'})}])
            if submission:break
        result={'id':trial_id,'phase':phase,'arm':arm,'task':t['public'],'replicate':replicate,'history_hash':canonical_hash(history),
          'candidate_hash':capsule['content_hash'],'candidate_status':qualification['status'],'program_used':program_used,'steps':steps,'submission':submission,
          'verifier_probes':probes,'human_interventions':0,'final_status':'pending-sealed-confirmation'}
        result['content_hash']=canonical_hash(result);immutable(path,result)
        print(json.dumps({'trial':trial_id,'submitted':submission is not None,'probes':probes,'calls':len(steps),'cost_upper_cny':self.ledger.summary()['accounted_upper_bound_cny']}),flush=True)
        return result
    def run(self):
        self.prepare();history=json.loads((self.artifacts/'equal-history.json').read_text());trials=[];knowledge=[];qualifications=[]
        first=self.compile(0,history);q=self.qualify(first);knowledge.append(first);qualifications.append(q)
        # Counterbalance arm order across repeated task runs; no provider seed support claimed.
        for rep in self.p['b_replicates']:
            for i in self.p['b_task_indices']:
                arms=self.p['b_arms'][rep:]+self.p['b_arms'][:rep]
                for arm in arms:trials.append(self.trial('B',arm,task(i,'b'),rep,history,first,q))
        for g,indices in enumerate(self.p['c_indices']):
            cap=self.compile(g+1,history);qualification=self.qualify(cap);knowledge.append(cap);qualifications.append(qualification)
            before=len(trials)
            for j,i in enumerate(indices):
                arms=self.p['c_arms'][j:]+self.p['c_arms'][:j]
                for arm in arms:trials.append(self.trial(f'C{g+1}',arm,task(i,'c'),g,history,cap,qualification))
            # All arms in a generation see exactly the same prior history. Append only
            # public development observations after the entire generation freezes.
            for tr in trials[before:]:
                for step in tr['steps']:
                    if 'physical' in step['observation']:history.append(step['observation'])
            # Deterministic de-dup keeps equal information without pretending replicas free.
            history=list({canonical_hash(h):h for h in history}.values())
        immutable(self.artifacts/'learning-frozen.json',{'trial_hashes':[t['content_hash'] for t in trials],'knowledge_hashes':[k['content_hash'] for k in knowledge],'protocol_hash':self.p['content_hash']})
        outcomes=[];oracle={}
        for tr in trials:
            idx=int(tr['task']['id'].split('-')[-1]);split=tr['task']['id'].split('-')[0];t=task(idx,split)
            submission=tr['submission'];final=observe(t,submission['candidate_id'],self.artifacts/'final-confirmation',True) if submission else None
            passed=bool(final and final['physical']['value'] and final['energy_residual']<1e-5)
            admitted=bool(submission and submission['claim_pass'] and any(s['observation'].get('candidate_id')==submission['candidate_id'] and s['observation'].get('physical',{}).get('value') and s['observation'].get('energy_residual',1)<1e-7 for s in tr['steps']))
            outcomes.append({'trial_id':tr['id'],'final':final,'heldout_physical_pass':passed,'false_claim':bool(submission and submission['claim_pass'] and not passed),
              'false_admission':admitted and not passed,'admitted':admitted,'computational_verified_success':admitted and passed,
              'evidence_scope':'Admission requires matching public experiment evidence; independent final conditions test false admission after learning freezes. Same computational engine, not cross-implementation full-system physics.','hardware':False})
            if t['public']['id'] not in oracle:
                obs=[observe(t,c['id'],self.artifacts/'oracle',True) for c in sorted(t['public']['candidates'],key=lambda c:c['capacitance_f'])]
                oracle[t['public']['id']]={'feasible_candidates':[o['candidate_id'] for o in obs if o['physical']['value']],'enumeration_probes':len(obs),'first_success_probe':next((i+1 for i,o in enumerate(obs) if o['physical']['value']),None)}
        fingerprints=sorted({json.loads(p.read_text()).get('system_fingerprint') or 'unavailable' for p in (self.artifacts/'calls').glob('*.json')})
        aggregates=[]
        for phase,arm in dict.fromkeys((t['phase'],t['arm']) for t in trials):
            group=[t for t in trials if (t['phase'],t['arm'])==(phase,arm)];ids={t['id'] for t in group};results=[o for o in outcomes if o['trial_id'] in ids]
            aggregates.append({'phase':phase,'arm':arm,'trials':len(group),'heldout_pass':sum(o['heldout_physical_pass'] for o in results),'false_claims':sum(o['false_claim'] for o in results),'false_admissions':sum(o['false_admission'] for o in results),'probes':sum(t['verifier_probes'] for t in group),'program_used_trials':sum(t['program_used'] for t in group),'model_calls':sum(len(t['steps']) for t in group)})
        report={'schema_version':'fixed-model-campaign-report-v1','status':'completed','protocol':self.p,'protocol_hash':self.p['content_hash'],
          'trials':trials,'outcomes':outcomes,'knowledge':knowledge,'qualifications':qualifications,'aggregates':aggregates,'oracle':oracle,
          'budget':self.ledger.summary(),'provider_fingerprints':fingerprints,'fingerprint_stable':len(fingerprints)==1 and fingerprints[0]!='unavailable',
          'model_identity':MODEL,'research_claims':{'real_model_calls':True,'model_authored_programs':True,'hardware':False,'rsi_demonstrated':False,'knowledge_gain':'requires outcome analysis; qualification rejection and null effects remain visible'},
          'limitations':self.p['claim_boundary'],'learning_frozen_hash':file_hash(self.artifacts/'learning-frozen.json')}
        report['content_hash']=canonical_hash(report);immutable(self.artifacts/'report.json',report);write_canonical_json(self.doc/'report.json',report)
        print(json.dumps({'status':'completed','trials':len(trials),'budget':{k:v for k,v in report['budget'].items() if k!='receipts'},'qualification':[q['status'] for q in qualifications]}),flush=True)
        return report
