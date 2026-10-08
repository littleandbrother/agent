"""Independent trajectory-selected rotated FEM anchors; preserves failed solves."""
import argparse, json
from pathlib import Path
import numpy as np
from bfworld.agentlab.door_system.fem import anchor
from bfworld.agentlab.door_system.model import angle_path
from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json

def run(reference, output):
    reference,output=Path(reference),Path(output);output.mkdir(parents=True,exist_ok=True)
    design=json.loads((reference/'design-spec.json').read_text())
    wave=np.genfromtxt(reference/'waveform.csv',delimiter=',',names=True)
    angle=np.rad2deg(angle_path(wave['time_s'],design['frozen']))
    # Peak deflection and both sides of the high-gradient interval, then two
    # weak-field poses. Selection is outcome-blind to the independent FEM.
    targets=[('peak_q',int(np.argmax(np.abs(wave['tip_m']))))]
    for degree in (0,2,5,15,35,65):
        idx=int(np.argmin(abs(angle[:len(angle)//3]-degree)))
        targets.append(('angle_'+str(degree),idx))
    inputs=[{'name':name,'sample':idx,'time_s':float(wave['time_s'][idx]),
             'angle_deg':float(angle[idx]),'tip_m':float(wave['tip_m'][idx])} for name,idx in targets]
    write_json(output/'selection.json',{'design_id':design['design_id'],'waveform_sha256':file_hash(reference/'waveform.csv'),
        'selection':'Peak absolute q plus predeclared 0,2,5,15,35,65-degree closing-trajectory points; no FEM result used in selection.', 'anchors':inputs})
    rows=[]
    for item in inputs:
        d=output/item['name']
        try:
            receipt=anchor(d,design,item['angle_deg'],item['tip_m'],readback_only=(d/'RotatedField.java').exists())
            rows.append({**item,'status':'completed','result':receipt,'result_sha256':file_hash(d/'anchor-result.json')})
        except Exception as exc:
            rows.append({**item,'status':'failed','error':str(exc)})
        write_json(output/'trajectory-anchors.json',{'design_id':design['design_id'],'anchors':rows,'full_rotated_domain_qualified':False,
            'scope':'Finite independent trajectory anchors, not a continuous FEM error bound, manufacturing check or physical calibration.'})
        print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
    return rows

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.reference,a.output)
