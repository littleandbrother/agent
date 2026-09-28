#!/usr/bin/env python3
"""Guided computational study; all curves and probe counts come from execution.

Not a hidden/blinded LLM campaign. No fabrication of Agent messages or reasoning.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict,replace
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.coupled.engine import Design,Reference,execute
from bfworld.coupled.artifacts import seal_run
from bfworld.knowledge.burst_program import predict
from bfworld.knowledge.registry import create_capsule,transition,verify_lifecycle
from bfworld.kernel.canonical import canonical_hash,write_canonical_json

def main():
    cost={'learning_experiments':0,'qualification_experiments':0,'solve_experiments':0,'external_model_calls':0,'predictor_steps':0}
    inventory=[]
    def experiment(label,design,ref,category):
        cost[category]+=1
        if sum(cost[k] for k in ('learning_experiments','qualification_experiments','solve_experiments'))>100:raise RuntimeError('local study cost cap exceeded')
        run=execute(design,ref);root=seal_run(REPO/'runs/learning',run)
        inventory.append({'id':label,'content_hash':run['content_hash'],'path':str(root.relative_to(REPO)),'category':category})
        return run
    initial=replace(Design(),capacitance_f=.00033,esr_ohm=18)
    interventions=[]
    for label,d in [('initial-failure',initial),('remove-series-resistance',replace(initial,esr_ohm=0)),
                    ('reduce-tx-demand',replace(initial,tx_power_w=.012)),('increase-storage',replace(initial,capacitance_f=.0022))]:
        run=experiment(label,d,Reference(),'learning_experiments')
        interventions.append({'id':label,'design':asdict(d),'run_hash':run['content_hash'],'outcome':run['physical_mission_pass'],
         'minimum_input_v':run['summary']['minimum_input_v'],'first_brownout_s':run['summary']['first_brownout_s'],
         'trace':[{'time_s':r['time_s'],'input_voltage_v':r['input_voltage_v'],'predicted_voltage_v':r['predicted_voltage_v']} for r in run['rows']],
         'events':run['events']})
    calibration=run
    ledger=calibration['energy_ledger'];load=sum(ledger[k] for k in ('boot','idle','sense','infer','tx'))
    params={'efficiency':load/(load+ledger['pmic_loss']),'sense_power_w':ledger['sense']/.08,
      'infer_power_w':ledger['infer']/.035,'boot_power_w':ledger['boot']/.012,'idle_power_w':.00005,
      'sense_duration_s':.08,'infer_duration_s':.035,'boot_duration_s':.012,'tx_duration_s':.04,'leakage_r_ohm':200000.}
    capsule=create_capsule(REPO/'runs/knowledge',params,[r['run_hash'] for r in interventions])
    manifest=capsule['manifest'];kid=manifest['content_hash']
    condition={'initial_v':2.65,'off_v':1.8,'harvest_during_burst':False,'signal_program':'difference-feature-int8-v1'}
    def prediction(d,cond,parameters=params):
        result=predict(parameters,asdict(d),cond);cost['predictor_steps']+=result.get('steps',0);return result
    # Fixed grid and thresholds precede evaluation. No tuning loop is provided.
    explanation=[]
    for i,(c,r,p) in enumerate([(.00047,6,.022),(.00068,14,.037),(.001,6,.058),(.0015,14,.058),(.0022,6,.037),(.0033,14,.065)]):
        d=replace(Design(),capacitance_f=c,esr_ohm=r,tx_power_w=p,release_s=.025)
        ref=replace(Reference(),rpm=0,source_peak_a=0,dt_s=.0002,initial_v=2.65)
        pred=prediction(d,condition)
        observed=experiment(f'explanation-{i}',d,ref,'qualification_experiments')
        # Guard covers the active burst, not post-mission idle discharge.
        active=[row['input_voltage_v'] for row in observed['rows'] if row['time_s']<=.181]
        actual=min(active)
        explanation.append({'id':f'explanation-{i}','design':asdict(d),'prediction':pred,'observed_minimum_v':actual,
            'absolute_error_v':abs(pred['minimum_terminal_v']-actual),'run_hash':observed['content_hash'],
            'false_admission':bool(pred['energy_feasible'] and not observed['physical_mission_pass']['electrical_safe'])})
    explanation_receipt={'candidate_hash':kid,'tolerance_v':.08,'maximum_error_v':max(x['absolute_error_v'] for x in explanation),
       'false_admissions':sum(x['false_admission'] for x in explanation),'tests':explanation,
       'independent_of_candidate':'reference engine does not import or call the capsule; fixed computational conditions, not real measurements'}
    explanation_receipt['passed']=explanation_receipt['maximum_error_v']<.08 and explanation_receipt['false_admissions']==0
    if not explanation_receipt['passed']:raise RuntimeError('explanation gate failed: '+json.dumps(explanation_receipt))
    # Future task driver has no original conversation; removal changes only the
    # admission/ranking module. Raw and text labels are explicitly non-LLM controls.
    candidates=[.00033,.00047,.00068,.001,.0015,.0022,.0033,.0047]
    future=[]
    for task,(p,r,v) in enumerate([(.022,6,2.65),(.037,14,2.65),(.058,6,2.9),(.058,14,2.65)]):
        ref=replace(Reference(),rpm=0,source_peak_a=0,dt_s=.0002,initial_v=v,device_session=f'synthetic-future-{task}')
        cond={**condition,'initial_v':v};arms=[]
        for arm in ('raw-search-removal','text-energy-rule','executable-capsule'):
            probes=[];predictions=[]
            for c in candidates:
                d=replace(Design(),capacitance_f=c,esr_ohm=r,tx_power_w=p,release_s=.025)
                if arm=='executable-capsule':
                    pred=prediction(d,cond);predictions.append({'capacitance_f':c,**pred})
                    if not pred.get('energy_feasible'):continue
                if arm=='text-energy-rule':
                    required=(ledger['sense']+ledger['infer']+ledger['boot']+p*.04)/params['efficiency']
                    if .5*c*(v*v-ref.off_v**2)<required:continue
                observed=experiment(f'future-{task}-{arm}-{len(probes)}',d,ref,'solve_experiments')
                probes.append({'capacitance_f':c,'run_hash':observed['content_hash'],'physical_mission_pass':observed['physical_mission_pass']['value'],
                    'minimum_input_v':observed['summary']['minimum_input_v']})
                if observed['physical_mission_pass']['value']:break
            arms.append({'arm':arm,'probes':probes,'probe_count':len(probes),'success':bool(probes and probes[-1]['physical_mission_pass']),
                         'candidate_predictions':predictions,'knowledge_hash':kid if arm=='executable-capsule' else None})
        future.append({'id':f'future-{task}','tx_power_w':p,'esr_ohm':r,'initial_v':v,'arms':arms})
    # Capsule transplantation into a standalone process in another directory.
    with tempfile.TemporaryDirectory(prefix='bfworld-transplant-') as tmp:
        for name in ('program.py','parameters.json','manifest.json'):shutil.copyfile(Path(capsule['path'])/name,Path(tmp)/name)
        detached_input={'design':asdict(replace(Design(),release_s=.025)),'condition':condition}
        completed=subprocess.run([sys.executable,'-I',str(Path(tmp)/'program.py')],input=json.dumps(detached_input),capture_output=True,text=True,cwd=tmp,timeout=30,check=True)
        detached=json.loads(completed.stdout)
        if detached!=predict(params,detached_input['design'],condition):raise RuntimeError('detached execution differs')
    oos=predict(params,asdict(Design()),{**condition,'harvest_during_burst':True})
    totals={arm:sum(next(a['probe_count'] for a in t['arms'] if a['arm']==arm) for t in future) for arm in ('raw-search-removal','text-energy-rule','executable-capsule')}
    use_receipt={'candidate_hash':kid,'passed':all(a['success'] for t in future for a in t['arms']) and totals['executable-capsule']<totals['raw-search-removal'],
                 'probe_totals':totals,'detached_result':detached,'out_of_scope_result':oos,'future_tasks':future,
                 'control_boundary':'deterministic reference search drivers; these are NOT equal-history LLM arms'}
    lifecycle=[]
    decisions=[('EXPLANATION_VALIDATED',explanation_receipt)]
    if use_receipt['passed']:
        decisions += [('USE_VALIDATED',use_receipt),('PROMOTED',{'candidate_hash':kid,'passed':True,'explanation_hash':canonical_hash(explanation_receipt),'use_hash':canonical_hash(use_receipt)})]
    else:
        decisions += [('REJECTED',{'candidate_hash':kid,'passed':False,'use_receipt_hash':canonical_hash(use_receipt),
           'reason':'Prespecified all-task use gate failed. Future-3 had no observed feasible design in the fixed candidate list. Gate and tasks were not changed after inspection.'})]
    for state,evidence in decisions:
        lifecycle=transition(lifecycle,kid,state,evidence,role='qualifier')
    # A deliberately unsupported candidate is retained as a rejected control.
    bad_hash=canonical_hash({'candidate':'average-energy-only','omits':'ESR and transient state'})
    lifecycle=transition(lifecycle,bad_hash,'REJECTED',{'candidate_hash':bad_hash,'reason':'Initial failure had an optimistic mean-energy prediction despite actual TX brownout. No dual-validation receipt.'},role='qualifier')
    verify_lifecycle(lifecycle)
    report={'schema_version':'reference-transfer-study-v1','status':'pass' if use_receipt['passed'] else 'qualification-failed','execution_status':'completed','actor':'guided developer-authored reference driver',
      'formal_agent_trial':False,'autonomous_discovery':False,'research_qualified_knowledge':0,'reference_qualified_knowledge':int(use_receipt['passed']),
      'interventions':interventions,'candidate':manifest,'candidate_path':str(Path(capsule['path']).relative_to(REPO)),
      'program_source':(Path(capsule['path'])/'program.py').read_text(),
      'explanation':explanation_receipt,'use':use_receipt,'lifecycle':lifecycle,'cost':cost,'run_inventory':inventory,
      'interpretation':{'direct_observation':'330 µF / 18 Ω design loses power during TX.',
         'structural_dependency':'source, storage, series resistance and action load share the electrical path; topology alone is not causal evidence.',
         'competing_explanations':['series resistance alone','insufficient stored energy for action burst','wrong diagnostic model'],
         'intervention_supported':'Removing ESR alone did not restore this design; lowering TX demand or increasing storage did. Storage/load interventions are effective here; this does not uniquely identify energy depletion versus transient mechanisms.',
         'knowledge_update':'Reusable empirical action-load model plus explicit electrical burst simulation; guarded no-harvest scope.'},
      'claim_boundary':'A reproducible, scoped computational transfer demonstration, not autonomous Agent efficacy, novel physics, real hardware or RSI.',
      'next_required_evidence':['fixed-model isolated participant pilot','equal-history LLM raw/text/executable arms','sealed final confirmation','multi-campaign model/workflow factorial','independent device or hardware']}
    report['content_hash']=canonical_hash(report)
    write_canonical_json(REPO/'docs/knowledge/reference-study.json',report)
    print(json.dumps({'status':report['status'],'execution_status':'completed','explanation_error_v':explanation_receipt['maximum_error_v'],'probe_totals':totals,'cost':cost,'formal_agent_trial':False}))
if __name__=='__main__':main()
