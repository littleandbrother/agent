"""Public development diagnostics over already observed, frozen G2 failures.

No new qualification or blind evaluation occurs here. Intervention outcomes
support local comparisons, not unique causal diagnoses or measured hardware.
"""
from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash
from bfworld.coupled.engine import Design, Reference, execute, reference_cases
from bfworld.coupled.artifacts import seal_run
from .audit import audit
from .study import task, design_of


def summarize(run, root, repo):
    bundle = seal_run(root, run)
    return {'run_hash':run['content_hash'],'artifact':str(bundle.relative_to(repo)),
            'design':run['design'],'reference':run['reference'],
            'physical':run['physical_mission_pass'],'summary':run['summary'],
            'energy_ledger':run['energy_ledger'], 'receive_s':run['request']['receive_s'],
            'transmit_s':run['request']['transmit_s'],'events':run['events']}


def g2_residuals(report, repo: Path, root: Path):
    audit(report)
    capsule, qualification = report['knowledge'][2], report['qualifications'][2]
    rows = []
    # Exact legacy tasks are reconstructed ONLY as explicitly observed development.
    for check in qualification['checks']:
        index = int(check['task'].rsplit('-',1)[1])
        t = task(index,'qualification')
        run = execute(design_of(t,check['candidate']),Reference(**t['reference']))
        if run['content_hash'] != check['run_hash'] or run['physical_mission_pass']['value'] is not check['observed']:
            raise ValueError('historical G2 observation identity drift')
        predicted = check['predicted']
        rows.append({'task_id':check['task'],'candidate_id':check['candidate'],
            'split':'development','prior_role':'observed-pilot-qualification',
            'predicted':predicted,'observed':check['observed'],
            'false_reject':predicted is False and check['observed'],
            'false_admit':predicted is True and not check['observed'],
            **summarize(run,root,repo)})
    def keys(row):
        return {k:row[k] for k in ('task_id','candidate_id','run_hash','design','reference','summary')}
    losses = []
    for use in qualification['use_tests']:
        matching = [r for r in rows if r['task_id']==use['task']]
        losses.append({**use,'wrongly_removed':[r['candidate_id'] for r in matching if r['false_reject']],
            'solvable_candidates':[r['candidate_id'] for r in matching if r['observed']],
            'probe_reduction':None if use['learned_probes'] is None or use['baseline_probes'] is None else use['baseline_probes']-use['learned_probes']})
    source = capsule['candidate']['code']
    lines = source.splitlines()
    semantic_sites = [{'line':i+1,'source':line.strip()} for i,line in enumerate(lines)
                      if 'load_energy = tx_power * cand.get(' in line]
    facts = {
        'false_reject_region':[keys(r) for r in rows if r['false_reject']],
        'false_admit_region':[keys(r) for r in rows if r['false_admit']],
        'lost_solvable_task':[u for u in losses if not u['solvability_retained']],
        'probe_reduction':losses,
        'scope_violation':{'observed_in_pilot':not qualification['scope_pass'],
            'scope_receipt_hash':qualification['content_hash'],
            'limitation':'one solar probe does not establish robust invalid-input abstention'},
        'missing_state_variable':[
            {'field':'tx_duration_s / complete load_profile','status':'absent-from-public-interface',
             'reference_fact':{'tx_duration_s':.04,'sense_duration_s':.08,'infer_duration_s':.035,'boot_duration_s':.012},
             'candidate_source_sites':semantic_sites,
             'interpretation':'release_s schedules task release; G2 multiplies it by TX power as if it were TX duration. This is a semantic mismatch, not proof that one repair alone will qualify.'},
            {'field':'source_phase_rad','status':'absent-from-public-interface','interpretation':'phase-sensitive risk cannot be identified from one scalar average source'},
            {'field':'deadline_s','status':'in-mission-prose-not-typed-conditions','interpretation':'candidate has no structured deadline input; energy sufficiency alone does not establish delivery before deadline'},
            {'field':'ESR and peak TX power','status':'present-and-read-by-G2','interpretation':'do not claim these were absent: the old code already includes an approximate I*R check'}],
    }
    obj = {'schema_version':'g2-development-residual-v1','source_report_hash':report['content_hash'],
           'candidate_hash':capsule['content_hash'],'program_hash':capsule['program_hash'],
           'historical_qualification_hash':qualification['content_hash'],'rows':rows,'residuals':facts,
           'status':'rejected-candidate-diagnosis','promotion':False,'new_blind_tasks':0,
           'claim_boundary':'24 already observed computational checks reclassified as development; no new transfer evidence'}
    obj['content_hash'] = canonical_hash(obj)
    return obj


def canonical_interventions(repo: Path, root: Path):
    design, ref = reference_cases()['brownout']
    # Declared before executing: retain unsuccessful interventions, no result search.
    specs = [
        ('baseline','No intervention',design,ref,[]),
        ('esr-only','ESR 18 → 4 Ω; same C and environment',replace(design,esr_ohm=4),ref,['design.esr_ohm']),
        ('capacity-only','C 330 → 2200 µF; same ESR and environment',replace(design,capacitance_f=.0022),ref,['design.capacitance_f']),
        ('tx-peak-only','TX load 36 → 9 mW; all durations unchanged',replace(design,tx_power_w=.009),ref,['design.tx_power_w']),
        ('phase-only','Source phase 0 → π/2; same design and source amplitude',design,replace(ref,source_phase_rad=1.5707963267948966),['reference.source_phase_rad'])]
    runs = []
    for identity,title,d,r,changed in specs:
        run = execute(d,r)
        runs.append({'id':identity,'title':title,'changed_fields':changed,
                     **summarize(run,root,repo),'trace':run['rows'],
                     'prediction_model':run['prediction_model'],'model_artifact':run['model_artifact']})
    base = runs[0]
    for run in runs:
        run['comparison'] = {'baseline_hash':base['run_hash'],
            'minimum_input_delta_v':run['summary']['minimum_input_v']-base['summary']['minimum_input_v'],
            'physical_pass_changed':run['physical']['value']!=base['physical']['value'],
            'certainty':'controlled computational difference, not unique mechanism identification'}
    obj = {'schema_version':'canonical-intervention-set-v1','runs':runs,
        'competing_explanations':[
            {'id':'storage','hypothesis':'insufficient usable storage for the complete action','status':'candidate-explanation'},
            {'id':'esr','hypothesis':'ESR-related terminal droop during peak load','status':'candidate-explanation'},
            {'id':'load','hypothesis':'average load omits peak or complete action schedule','status':'candidate-explanation'},
            {'id':'phase','hypothesis':'source phase conflicts with task scheduling','status':'candidate-explanation'}],
        'actor':'trusted deterministic development experiments, not a new Agent episode',
        'observation_source':'synthetic computational reference, not measured trace',
        'baseline_prediction':'average-energy-v0 voltage trace; no claim of information/receiver success',
        'remaining_uncertainty':['cross-factor interactions','source/PMIC calibration','load waveform realism','independent hardware confirmation']}
    obj['content_hash'] = canonical_hash(obj)
    return obj


def validate_dossier(dossier, pilot, repo):
    """Rebind rendered verdicts to raw runs and the immutable old checks."""
    from .repair import checked
    from bfworld.coupled.artifacts import verify_bundle
    checked(dossier);checked(dossier['g2']);checked(dossier['episode'])
    if dossier['g2']['source_report_hash'] != pilot['content_hash']:
        raise ValueError('G2 source report misbound')
    expected={(r['task'],r['candidate']):r for r in pilot['qualifications'][2]['checks']}
    rows=dossier['g2']['rows']
    if len(rows)!=len(expected) or len({(r['task_id'],r['candidate_id']) for r in rows})!=len(expected):
        raise ValueError('missing or duplicated counterexamples')
    for row in rows:
        original=expected.get((row['task_id'],row['candidate_id']))
        if original is None or any(row[k]!=original[v] for k,v in (('run_hash','run_hash'),('predicted','predicted'),('observed','observed'))):
            raise ValueError('G2 counterexample changed from historical evidence')
        if row['false_reject'] != (row['predicted'] is False and row['observed']) or row['false_admit'] != (row['predicted'] is True and not row['observed']):
            raise ValueError('G2 residual miscomputed')
    residual=dossier['g2']['residuals']
    for flag,region in [('false_reject','false_reject_region'),('false_admit','false_admit_region')]:
        if [(r['task_id'],r['candidate_id']) for r in residual[region]] != [(r['task_id'],r['candidate_id']) for r in rows if r[flag]]:
            raise ValueError('G2 residual region misbound')
    for rendered in rows+dossier['episode']['runs']:
        root=(repo/rendered['artifact']).resolve()
        if not root.is_relative_to((repo/'.bfworld/b2-development').resolve()) and not root.is_relative_to((repo/'.bfworld').resolve()):
            raise ValueError('development artifact outside local evidence root')
        verify_bundle(root)
        run=json.loads((root/'run.json').read_text())
        for field,source in [('run_hash','content_hash'),('summary','summary'),('physical','physical_mission_pass'),('design','design'),('reference','reference')]:
            if rendered[field]!=run[source]:raise ValueError('development source field misbound: '+field)
        if 'trace' in rendered and rendered['trace']!=run['rows']:
            raise ValueError('development trace sample changed')
    return {'status':'pass','counterexamples':len(rows),'runs':len(dossier['episode']['runs'])}
