#!/usr/bin/env python3
"""Project verified computational artifacts into a portable Studio payload.

The build materializes deterministic no-provider development evidence; it never
launches paid trials or promotes knowledge. Original samples remain intact.
Derived values carry their expression and source binding; the browser renders.
"""
from __future__ import annotations
import json
import math
import sys
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'packages/python/bfworld/src'))
from bfworld.bundle.reader import RunBundleReader
from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.verification.verifier import verify_bundle


def build_payload(repo: Path = REPO) -> dict:
    root = repo / 'runs/a-rotary-v1'
    verified = verify_bundle(root)
    reader = RunBundleReader(root)
    world = reader.json('world.ir.json')
    mission = world['mission']
    manifest = reader.manifest
    samples = reader.channels()
    c = mission['storage']['capacitance_f']
    vmin = mission['storage']['min_operating_voltage_v']
    vmax = mission['storage']['max_safe_voltage_v']
    usable_max = .5*c*(vmax*vmax-vmin*vmin)
    source_files = {p.name: file_hash(p) for p in root.iterdir() if p.is_file()}
    channels = {}
    units = {'time_s':'s','rpm':'RPM','source_current_a':'A','harvest_current_a':'A',
             'load_current_a':'A','leak_current_a':'A','shunt_current_a':'A',
             'capacitor_voltage_v':'V','storage_energy_j':'J','inference_active':'boolean',
             'brownout':'boolean','overvoltage':'boolean'}
    for key, unit in units.items():
        channels[key] = {'file':'channels.parquet','field':key,'unit':unit,
                         'file_hash':source_files['channels.parquet'], 'source_kind':'simulated',
                         'producer':world['provider']['id'],'fidelity':world['provider']['fidelity'],
                         'timebase':'simulation seconds; sample-and-hold display'}
    for key, expression, unit in [
        ('shaft_angle_rad','time_s * rpm / 60 * 2*pi','rad'),
        ('usable_energy_j','max(0, storage_energy_j - 0.5*C*Vmin^2)','J'),
        ('energy_fill','clamp(usable_energy_j / (0.5*C*(Vmax^2-Vmin^2)), 0, 1)','ratio')]:
        channels[key] = {'file':'channels.parquet','field':key,'unit':unit,
                         'file_hash':source_files['channels.parquet'],'source_kind':'derived',
                         'expression':expression,'parameters':'world.ir.json#/mission/storage',
                         'fidelity':'F1-simplified','producer':'studio projection v1',
                         'timebase':'simulation seconds; sample-and-hold display'}
    for row in samples:
        row['shaft_angle_rad'] = row['time_s'] * row['rpm']/60*2*math.pi
        row['usable_energy_j'] = max(0, row['storage_energy_j'] - .5*c*vmin*vmin)
        row['energy_fill'] = max(0,min(1,row['usable_energy_j']/usable_max))
    phases = []
    titles = {'baseline':('01','Initial design','Unclamped storage'),
              'revised':('02','Protection added','3.45 V shunt clamp'),
              'fine_validation':('03','Resolution check','Same model · 1 ms time step')}
    for phase, (number,title,subtitle) in titles.items():
        rows = [r for r in samples if r['phase']==phase]
        first = next((r['time_s'] for r in rows if r['overvoltage'] or r['brownout']),None)
        phases.append({'id':phase,'number':number,'title':title,'subtitle':subtitle,
                       'summary':manifest['phases'][phase],'rows':rows,
                       'first_violation_s':first,
                       'summary_binding':f'run-manifest.json#/phases/{phase}',
                       'sample_binding':'channels.parquet'})
    specs = [
      ('rotary','Rotary-TENG','Load-dependent Norton source','implemented','world.ir.json#/provider'),
      ('rectifier','Rectification','Rectified source abstraction','simplified','world.ir.json#/provider/equations'),
      ('storage','Energy storage','1,000 µF capacitor','implemented','world.ir.json#/mission/storage'),
      ('protection','Protection','Revision: resistive shunt clamp','implemented','world.ir.json#/mission/revision'),
      ('load','Compute load','Aggregate load pulses; no inference execution','simplified','world.ir.json#/mission/load'),
      ('pmic','PMIC state machine','Not implemented in A-001','unimplemented',None),
      ('sensor','Sensing & INT8 inference','Not implemented in A-001','unimplemented',None),
      ('receiver','Receiver delivery','Not implemented in A-001','unimplemented',None)]
    components = [{'id':i,'title':t,'description':d,'status':s,'binding':b,
                   'fidelity':'F1-simplified' if b else None,'hardware':False} for i,t,d,s,b in specs]
    roadmap = yaml.safe_load((repo/'project/ROADMAP.yaml').read_text())
    features = [yaml.safe_load(p.read_text()) for p in sorted((repo/'project/features').glob('*/feature.yaml'))]
    golden_manifest = json.loads((repo/'fixtures/golden-episodes/manifest.json').read_text())
    golden = [json.loads((repo/'fixtures/golden-episodes'/e['path']).read_text()) for e in golden_manifest['files']]
    bindings = {
        'shaft.rotation':'shaft_angle_rad','storage.fill':'energy_fill','storage.energy':'usable_energy_j',
        'storage.voltage':'capacitor_voltage_v','load.pulse':'inference_active',
        'timeline.voltage':'capacitor_voltage_v','timeline.energy':'storage_energy_j',
        'timeline.harvester':'harvest_current_a','timeline.load':'load_current_a',
        'failure.overvoltage':'overvoltage','failure.brownout':'brownout',
    }
    payload = {'schema_version':'bfworld-studio-payload-v1','title':'Rotary-TENG laboratory',
       'run_id':manifest['run_id'],'bundle_hash':verified['bundle_hash'],'world':world,
       'manifest':manifest,'evidence':reader.evidence,'verification':verified,
       'events':reader.events(),'phases':phases,'channels':channels,'visual_bindings':bindings,
       'source_files':source_files,'components':components,'golden':golden,
       'roadmap':roadmap,'features':features,
       'coverage':{'agent':False,'knowledge':False,'measured':False,'hidden_qualification':False},
       'source_url':'../../../runs/a-rotary-v1/replay.html'}
    coupled_path=repo/'docs/coupled/validation.json'
    if coupled_path.exists():
        from bfworld.coupled.artifacts import verify_bundle as verify_coupled
        coupled=json.loads(coupled_path.read_text())
        for case in coupled['cases']:
            case_root=repo/case['path'];verify_coupled(case_root)
            case['run']=json.loads((case_root/'run.json').read_text())
            run=case['run'];d=run['design'];r=run['reference']
            for row in run['rows']:
                row['energy_fill']=max(0,min(1,(row['energy_j']-.5*d['capacitance_f']*r['off_v']**2)/(.5*d['capacitance_f']*(r['max_v']**2-r['off_v']**2))))
            case['visual_provenance']={'source':case['path']+'/run.json','source_hash':file_hash(case_root/'run.json'),
              'energy_fill':'clamp((energy_j-0.5*C*Voff^2)/(0.5*C*(Vmax^2-Voff^2)),0,1)',
              'voltage':'storage_voltage_v','load':'interval_load_state','time':'post-event state; interval quantities are labeled',
              'prediction':'average-energy-v0, created before observed run outcomes; not an independent observation'}
        payload['coupled']=coupled
    learning_path=repo/'docs/knowledge/reference-study.json'
    if learning_path.exists():
        from bfworld.knowledge.registry import verify_capsule,verify_lifecycle
        learning=json.loads(learning_path.read_text())
        if canonical_hash({k:v for k,v in learning.items() if k!='content_hash'})!=learning['content_hash']:raise ValueError('learning study tamper')
        verify_capsule(repo/learning['candidate_path']);verify_lifecycle(learning['lifecycle'])
        payload['learning']=learning
    deployment_path=repo/'docs/deployments/validation.json'
    if deployment_path.exists():
        from bfworld.deployments.artifacts import verify as verify_deployment
        deployments=json.loads(deployment_path.read_text())
        for scene in deployments['scenes']:
            for variant in scene['variants']:
                root=repo/variant['path'];verify_deployment(root)
                variant['run']=json.loads((root/'run.json').read_text())
        payload['deployments']=deployments
    campaign_path=repo/'docs/campaign/report.json'
    if campaign_path.exists():
        campaign=json.loads(campaign_path.read_text())
        if canonical_hash({k:v for k,v in campaign.items() if k!='content_hash'})!=campaign['content_hash']:raise ValueError('campaign report identity mismatch')
        payload['campaign']=campaign
        from bfworld.campaign.study import task,design_of
        from bfworld.coupled.engine import execute,Reference
        from dataclasses import replace
        traces={}
        for trial,outcome in zip(campaign['trials'],campaign['outcomes']):
            if trial['id']!=outcome['trial_id']:raise ValueError('campaign trial/outcome misbound')
            if not outcome['final']:continue
            expected=outcome['final']['run_hash']
            if expected in traces:continue
            split,index=trial['task']['id'].rsplit('-',1);t=task(int(index),split)
            ref=Reference(**t['reference']);ref=replace(ref,source_phase_rad=.73,source_peak_a=ref.source_peak_a*.95,device_session=ref.device_session+'-sealed-confirmation')
            run=execute(design_of(t,trial['submission']['candidate_id']),ref)
            if run['content_hash']!=expected:raise ValueError('campaign final replay identity drift')
            for row in run['rows']:
                row['energy_fill']=max(0,min(1,(row['energy_j']-.5*run['design']['capacitance_f']*ref.off_v**2)/(.5*run['design']['capacitance_f']*(ref.max_v**2-ref.off_v**2))))
            traces[expected]=run
        payload['campaign_traces']=traces
    development_path=repo/'docs/b2-development/report.json'
    if development_path.exists():
        from bfworld.campaign.repair import checked
        from bfworld.campaign.diagnostics import validate_dossier
        development=checked(json.loads(development_path.read_text()))
        if development['inputs']['pilot_file_hash']!=file_hash(campaign_path):raise ValueError('development source pilot drift')
        validate_dossier(development,campaign,repo)
        payload['b2_development']=development
    profiled_path=repo/'docs/b2-development/profiled-report.json'
    if profiled_path.exists():
        from build_b2_profiled import validate as validate_profiled
        profiled=json.loads(profiled_path.read_text());validate_profiled(profiled,repo)
        payload['b2_profiled']=profiled
    measured_path=repo/'docs/b2-development/measured-import.json'
    if measured_path.exists():
        from bfworld.campaign.measurements import restore_archive
        pointer=json.loads(measured_path.read_text())
        root,measured=restore_archive(repo/'docs/b2-development/measured-replay.zip',repo/'.bfworld/measured-imports')
        if measured!=pointer['report'] or str(root.relative_to(repo))!=pointer['artifact']:
            raise ValueError('measured replay pointer identity mismatch')
        payload['b2_measured']=measured
    execution_path=repo/'docs/b2-development/execution-controls.json'
    if execution_path.exists():
        from validate_b2_execution import validate_report
        payload['b2_execution_controls']=validate_report(json.loads(execution_path.read_text()))
    workflow_path=repo/'docs/b2-development/workflow-use-controls.json'
    if workflow_path.exists():
        from build_b2_workflow_use import validate as validate_workflow_use
        payload['b2_workflow_use']=validate_workflow_use(json.loads(workflow_path.read_text()),repo)
    # YAML dates are represented as ISO strings in the portable JSON view.
    payload = json.loads(json.dumps(payload,default=str))
    payload['content_hash'] = canonical_hash(payload)
    return payload


def main():
    # Included in the normal build so ignored raw B2 bundles can be recreated on
    # a new checkout before their public projection is verified. Cached inputs
    # reuse sealed receipts; changed implementation gets a new dossier identity.
    from build_b2_development import build as build_development
    build_development(REPO)
    from build_b2_profiled import build as build_profiled
    build_profiled(REPO)
    from build_b2_workflow_use import build as build_workflow_use
    build_workflow_use(REPO)
    from validate_b2_execution import ensure as ensure_execution_controls
    ensure_execution_controls()
    payload = build_payload()
    write_canonical_json(REPO/'apps/world-studio/generated/payload.json', payload)
    print(json.dumps({'status':'built','samples':sum(len(p['rows']) for p in payload['phases']),
                      'bundle_hash':payload['bundle_hash'],'payload_hash':payload['content_hash']}))

if __name__=='__main__':
    main()
