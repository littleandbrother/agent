#!/usr/bin/env python3
"""Prospective orientation intervention, outside the sealed v1 trial namespace.

Reuses verified beam/firmware/CAD sources, rotates the driver magnet by 180 deg,
rebuilds actual STEP and uses the corresponding signed uniform-magnet force
table in native LTspice/SIL. No physical qualification or old-task score change.
"""
import argparse
import json
from pathlib import Path
import shutil
import time
import numpy as np
from bfworld.agentlab.mechanical_review import ForceTable,control
from bfworld.agentlab.simulation_chain.contracts import file_hash,write_json,ChainError
from bfworld.agentlab.simulation_chain.native import command,CAD
from bfworld.agentlab.simulation_chain.solver import solve


def magnet_orientation():
    """Magnetization is +x in the part frame; assembly rotation reverses it."""
    return {'driver_rotation_local_deg':[0,0,180],
        'tip_magnetization_local':[1,0,0],'driver_magnetization_local':[1,0,0],
        'driver_magnetization_in_unrotated_reference_frame':[-1,0,0],
        'uniform_force_multiplier':-1}


def run(source,cache,output,native=False):
    source,cache,output=map(Path,(source,cache,output))
    if output.exists():raise ValueError('PRESERVE_EXISTING_ORIENTATION_RUN')
    result=json.loads((source/'result.json').read_text());provenance={}
    def verified(stage,name):
        key=result['stages'][stage]['key'];root=cache/stage/key
        checkpoint=json.loads((root/'checkpoint.json').read_text())
        if checkpoint['key']!=key or checkpoint['stage']!=stage:raise ValueError('CHECKPOINT_IDENTITY')
        h=next(f['sha256'] for f in checkpoint['files'] if f['path']==name)
        path=root/name
        if file_hash(path)!=h:raise ValueError('CHECKPOINT_FILE_CHANGED:'+name)
        provenance[str(path)]=h
        return path
    spec=json.loads((source/'design-spec.json').read_text())
    expected=next(a['sha256'] for a in result['artifacts'] if a['name']=='design-spec.json')
    if file_hash(source/'design-spec.json')!=expected:raise ValueError('SPEC_CHANGED')
    rom=json.loads(verified('beam','rom.json').read_text());force_path=verified('force','force-table.npz')
    f=np.load(force_path)
    output.mkdir(parents=True);started=time.time()
    controls=[]
    for label,sign in [('same-polarization',1),('reversed-driver',-1)]:
        table=ForceTable(f['angles'],f['qs'],f['values']*sign)
        for kind in ('rotary_path','close_hold_open'):
            try:
                value,wave=control(rom,table,spec,kind)
                np.savetxt(output/(label+'-'+kind+'.csv'),wave,delimiter=',',
                    header='time_s,tip_m,velocity_m_s,piezo_V,resistor_J,damping_J,magnetic_work_J,stored_J',comments='')
            except ValueError as exc:value={'status':'not_evaluable','error':str(exc)}
            controls.append({**value,'orientation':label,'force_multiplier':sign})
    write_json(output/'screen.json',{'results':controls,'scope':'Exploratory ROM/resistor only; loading-cycle is not the frozen 4s mission.'})
    architecture={'schema':'magnetic-orientation-intervention-v1','change':'rotate driver magnet 180deg about local z',
        **magnet_orientation(),
        'units':'mm','fixed_inputs':spec,'operator_chosen_after_review':True,
        'agent_autonomous_design':False,'sealed_trial_modified':False,
        'applicability':'Uniform hard magnetization and recoil permeability=1 only. Magnetic FEM qualification unresolved.',
        'manufacturing_note':'Cube BREP is invariant under this rotation. Pole orientation and assembly instructions are required material attributes; STEP shape alone cannot prove magnetization.'}
    write_json(output/'candidate.json',architecture)
    outcome={'status':'not_requested'}
    if native:
        cad=output/'cad';cad.mkdir()
        cad_input=json.loads(verified('cad','input.json').read_text())
        driver=next(p for p in cad_input['assembly']['payload']['parts'] if p['id']=='driver_magnet')
        driver['geometry']['rotation_deg']=[0,0,180]
        driver['material']='NdFeB nominal Br=1.25T; part-local magnetization +x; assembly rotation maps it to reference -x; polarity reversal under review'
        cad_input['assembly']['payload']['design_revision']='D2-orientation-exploratory'
        write_json(cad/'input.json',cad_input)
        shutil.copy2(verified('cad','native_builder.py'),cad/'native_builder.py')
        command([CAD,cad/'native_builder.py',cad],cad,'cad-build',300)
        read=json.loads((cad/'cad-readback.json').read_text())
        part=next(p for p in read['parts'] if p['id']=='driver_magnet')
        if not part['native_valid']:raise ValueError('DRIVER_NATIVE_SHAPE_INVALID')
        write_json(cad/'magnetization.json',architecture)
        firmware=output/'firmware';firmware.mkdir()
        for name in ('program.dylib','program.c','program-arm.o','policy.h','receiver.py','build-receipt.json'):
            shutil.copy2(verified('firmware',name),firmware/name)
        np.savez(output/'force-reversed.npz',angles=f['angles'],qs=f['qs'],values=-f['values'])
        joint=output/'joint';joint.mkdir()
        try:
            value=solve(joint,spec,rom,output/'force-reversed.npz',firmware)
            outcome={'status':'completed','metrics':value,'physical_qualification':False,'design_status':'insufficient_evidence'}
        except ChainError as exc:outcome={'status':exc.status,'error':str(exc),'physical_qualification':False}
        write_json(output/'native-result.json',outcome)
    receipt={'schema':'magnetic-orientation-review-v1','started':started,'elapsed_s':time.time()-started,
        'source_result_sha256':file_hash(source/'result.json'),'source_files':provenance,
        'script_sha256':file_hash(Path(__file__)),'control_source_sha256':file_hash(Path(__file__).parents[1]/'packages/python/bfworld/src/bfworld/agentlab/mechanical_review.py'),
        'native_requested':native,'native_result':outcome,'new_external_model_calls':0,
        'scope':'Operator exploratory structural intervention, not a Pi candidate or a scored old pilot trial.'}
    write_json(output/'receipt.json',receipt)
    print(json.dumps({'output':str(output),'elapsed_s':receipt['elapsed_s'],'native_status':outcome['status']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--cache',required=True)
    p.add_argument('--output',required=True);p.add_argument('--native',action='store_true');a=p.parse_args()
    run(a.source,a.cache,a.output,a.native)
