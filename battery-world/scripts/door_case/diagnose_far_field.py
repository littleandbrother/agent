"""Predeclared far-field source-mesh/domain diagnostic; never replaces a gate.

The original seven-anchor receipts remain immutable. Two explicit numerical
variants at the same 35-degree trajectory state test whether refining only the
probe was insufficient. This is operator model investigation, not Agent data.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
from bfworld.agentlab.door_system.model import coordinates,field_energy
from bfworld.agentlab.simulation_chain.native import command
from bfworld.agentlab.simulation_chain.contracts import file_hash,write_json
from bfworld.agentlab.runtime_config import COMSOL

def run(root,angle_deg=35):
    if angle_deg not in (-1,0,2,5,15,35,65):raise ValueError('PREDECLARED_ANCHOR_REQUIRED')
    root=Path(root);out=root/('far-field-diagnostic-v1' if angle_deg==35 else f'far-field-confirmation-{angle_deg}-v1')
    if out.exists():raise ValueError('DIAGNOSTIC_IMMUTABLE_USE_NEW_VERSION')
    out.mkdir();a=next(a for a in json.loads((root/'trajectory-fem-v1/trajectory-anchors.json').read_text())['anchors'] if a['name']==('peak_q' if angle_deg==-1 else f'angle_{angle_deg}'))
    d=json.loads((root/'sealed-reference-v2/design-spec.json').read_text());angle=np.deg2rad(a['angle_deg']);q=a['tip_m']
    dx,dz=coordinates(angle,d['mechanical']);dz-=q;distance=np.hypot(dx,dz)*1000
    expected=field_energy(angle,q,d['mechanical'],n=12)[0][[0,2]]
    from bfworld.agentlab import door_system
    template=Path(door_system.__file__).with_name('RotatedField.java')
    declaration={'schema_version':'bf-fem-diagnostic-v1','created':time.time(),'design_id':d['design_id'],
        'anchor':{k:a[k] for k in ('name','angle_deg','tip_m','time_s')},'original_receipt_sha256':file_hash(root/'trajectory-fem-v1/trajectory-anchors.json'),
        'template_sha256':file_hash(template),'hypothesis':'Probe-only refinement can converge around an inaccurate source field or truncated domain.',
        'falsifier':'Both variants remain above the unchanged5% relative reference target; then this diagnostic does not resolve the far-field mismatch.',
        'variants':([{'id':'driver-refined','driver_hmax_mm':2.,'air_radius_mm':max(220.,distance+100)}] if angle_deg==35 else [])+
                    [{'id':'driver-and-domain','driver_hmax_mm':2.,'air_radius_mm':max(440.,3*distance+100)}],
        'target':.05,'automatic_gate_promotion':False,'model_calls':0,
        'scope':'One fixed actual trajectory anchor, operator numerical investigation; not complete rotating-domain calibration.'}
    if angle_deg!=35:
        declaration['configuration_chosen_from']=file_hash(root/'far-field-diagnostic-v1/summary.json')
        declaration['hypothesis']='The explicitly selected larger-air-domain configuration resolves the original discrepancy at an additional trajectory angle.'
        declaration['falsifier']='This additional anchor remains above the unchanged5% reference or mesh target; do not tune this declared run.'
    write_json(out/'declaration.json',declaration);rows=[]
    for v in declaration['variants']:
        folder=out/v['id'];folder.mkdir();started=time.time()
        text=template.read_text()
        extra='''m.component("c").mesh("mesh").create("driverSize","Size");
  m.component("c").mesh("mesh").feature("driverSize").selection().named("g_turn_dom");
  m.component("c").mesh("mesh").feature("driverSize").set("custom","on");
  m.component("c").mesh("mesh").feature("driverSize").set("hmax","2[mm]");
  m.component("c").mesh("mesh").feature("driverSize").set("hmin","0.5[mm]");
  m.component("c").mesh("mesh").feature("driverSize").set("hgrad",1.3);
  '''
        text=text.replace('m.component("c").mesh("mesh").create("tet","FreeTet");',extra+'m.component("c").mesh("mesh").create("tet","FreeTet");')
        for k,value in {'DX':dx,'DZ':dz,'ANGLE':angle,'RAIR':v['air_radius_mm'],'POLARITY':d['mechanical']['polarity']}.items():text=text.replace('__'+k+'__',str(value))
        source=folder/'RotatedField.java';source.write_text(text)
        write_json(folder/'input.json',{**v,'dx_m':dx,'dz_m':dz,'angle_rad':float(angle),'tip_m':q,'reference_N':expected.tolist(),'source_sha256':file_hash(source)})
        try:
            command([COMSOL,'compile',source],folder,'compile',120)
            command([COMSOL,'-np','2','batch','-inputfile',source.with_suffix('.class'),'-outputfile',folder/'model.mph','-batchlog',folder/'solver.log'],folder,'solve',1200)
            import mph
            models=list(folder.glob('model*.mph'))
            if len(models)!=1:raise ValueError('NATIVE_MODEL_IDENTITY')
            client=mph.start(cores=2);model=client.load(models[0]);j=model.java
            try:
                if j.param().evaluate('BF_complete')!=1:raise ValueError('NATIVE_MODEL_INCOMPLETE')
                forces=[np.array([j.param().evaluate('BF_fx'+str(i)),j.param().evaluate('BF_fz'+str(i))]) for i in range(3)]
            finally:client.remove(model)
            errors=[float(np.linalg.norm(f-expected)/max(np.linalg.norm(expected),1e-9)) for f in forces]
            delta=float(np.linalg.norm(forces[-1]-forces[-2])/max(np.linalg.norm(forces[-1]),1e-9))
            result={'variant':v['id'],'status':'completed','force_N':[f.tolist() for f in forces],
                'relative_reference_errors':errors,'mesh_delta':delta,'reference_passed':errors[-1]<=.05,
                'mesh_passed':delta<=.05,'source_sha256':file_hash(source),'model_sha256':file_hash(models[0]),'elapsed_s':time.time()-started}
        except Exception as e:result={'variant':v['id'],'status':'failed','error':str(e),'source_sha256':file_hash(source),'elapsed_s':time.time()-started}
        write_json(folder/'result.json',result);rows.append(result);print(json.dumps(result),flush=True)
    write_json(out/'summary.json',{'declaration_sha256':file_hash(out/'declaration.json'),'original_reference_error':a['result']['reference_error'],'results':rows,'full_domain_qualified':False})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();run(a.root)
