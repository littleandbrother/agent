"""Independent operator checks of sealed D4 results; no participant promotion."""
import argparse,json
from pathlib import Path
import numpy as np
from bfworld.agentlab.door_system.model import field_energy
from bfworld.agentlab.simulation_chain.contracts import file_hash,write_json

def prepare(root):
    root=Path(root);out=root/'verification';out.mkdir(exist_ok=True)
    runs=[root/n for n in ('sealed-reference-v2','sealed-reference-v3')]
    a,b=[json.loads((p/'result.json').read_text()) for p in runs];ma,mb=[json.loads((p/'system-manifest.json').read_text()) for p in runs]
    same=all(a.get(k)==b.get(k) for k in ('design_id','run_status','source_stable')) and ma['executor_sha256']==mb['executor_sha256'] and ma['source_dependencies']==mb['source_dependencies']
    peaks={k:abs(a['metrics'][k]-b['metrics'][k])/max(abs(a['metrics'][k]),1e-12) for k in ('peak_tip_mm','peak_piezo_V','peak_storage_V','peak_supply_V')}
    counts=all(a['metrics'][k]==b['metrics'][k] for k in ('tx_completed','received_events'))
    repeat={'same_inputs_and_executor':same,'both_source_stable':a['source_stable'] and b['source_stable'],
        'peak_relative_differences':peaks,'counts_equal':counts,'target':.01,'passed':same and counts and max(peaks.values())<=.01,
        'result_files':[{'path':str(p/'result.json'),'sha256':file_hash(p/'result.json')} for p in runs],
        'scope':'Two independent native launches, no D4 successful stage cache; deterministic numeric repeat, not stochastic physical repeat.'}
    write_json(out/'cold-repeat.json',repeat)
    d=json.loads((runs[0]/'design-spec.json').read_text());rows=[]
    for polarity in (-1,1):
        mech={**d['mechanical'],'polarity':polarity}
        for angle,q in [(0,.003),(.06,-.001),(.8,.002)]:
            force=field_energy(angle,q,mech)[0][2];eps=1e-7
            derivative=-(field_energy(angle,q+eps,mech)[1]-field_energy(angle,q-eps,mech)[1])/(2*eps)
            rows.append({'angle_rad':angle,'tip_m':q,'polarity':polarity,'force_N':float(force),'potential_derivative_N':derivative,
                         'passed':bool(np.isclose(force,derivative,rtol=1e-5,atol=1e-8))})
    write_json(out/'reciprocity.json',{'checks':rows,'passed':all(r['passed'] for r in rows),'scope':'Independent central difference of same magnetic potential; implementation check, not physical calibration.'})
    original=json.loads((root/'trajectory-fem-v1/trajectory-anchors.json').read_text());corrected=[]
    for anchor in original['anchors']:
        angle=-1 if anchor['name']=='peak_q' else int(anchor['name'].removeprefix('angle_'))
        folder=root/('far-field-diagnostic-v1' if angle==35 else f'far-field-confirmation-{angle}-v1')
        path=folder/'driver-and-domain/result.json';result=json.loads(path.read_text());declaration=json.loads((folder/'declaration.json').read_text())
        if declaration['design_id']!=d['design_id'] or declaration['anchor']['tip_m']!=anchor['tip_m'] or result['status']!='completed':raise ValueError('FEM_CORRECTION_IDENTITY')
        corrected.append({'name':anchor['name'],'angle_deg':anchor['angle_deg'],'tip_m':anchor['tip_m'],
            'original_reference_error':anchor['result']['reference_error'],'reference_error':result['relative_reference_errors'][-1],
            'mesh_delta':result['mesh_delta'],'passed':result['reference_passed'] and result['mesh_passed'],
            'result_path':str(path),'result_sha256':file_hash(path),'source_sha256':result['source_sha256'],'model_sha256':result['model_sha256']})
    correction={'schema_version':'bf-fem-corrected-anchors-v1','design_id':d['design_id'],'anchors':corrected,
        'configuration':'Driver hmax2mm; air radius max(440mm,3*driver-distance+100mm); three unchanged local tip mesh sizes.',
        'preselected_anchors':True,'all_finite_anchors_passed':all(a['passed'] for a in corrected),'reference_target':.05,'mesh_target':.05,
        'maximum_reference_error':max(a['reference_error'] for a in corrected),'maximum_mesh_delta':max(a['mesh_delta'] for a in corrected),
        'full_rotating_domain_coverage':False,'formal_method_comparison':False,
        'scope':'Operator development correction of air-boundary truncation. Original failures retained. Seven finite anchors only; no strain/fatigue/contact/hardware validation or automatic design-ranking promotion.'}
    write_json(out/'corrected-fem-anchors.json',correction)
    return {'cold_repeat':repeat['passed'],'reciprocity':all(r['passed'] for r in rows),'finite_fem':correction['all_finite_anchors_passed'],'maximum_fem_error':correction['maximum_reference_error']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.root)))
