"""D4 adapter binds the design to actual CAD, program source and native solver."""
import copy
import json
from pathlib import Path
from .contracts import verify_design
from ..simulation_chain import native as v1
from ..runtime_config import REPO, CAD

def solver_spec(design):
    verify_design(design); frozen = design['frozen']; model = frozen['model']; task = frozen['task']
    return {'system_design': design, 'mechanical': {'opening_s': task['opening_s'], 'angle_deg': task['angle_deg'], 'damping_ratio': model['damping_ratio']},
            'circuit': {**design['circuit'], 'initial_vin_V': 0., 'diagnostic_input_A': 0.},
            'firmware': {k: model[k] for k in ('boot_ms', 'init_ms', 'tx_ms', 'boot_mA', 'init_mA', 'tx_mA', 'sleep_uA', 'reset_uA')} | design['firmware'],
            'link': {'loss_probability': task['link_loss_probability'], 'scan_duty': task['scan_duty'], 'seed': task['seed']},
            'solver': {k: frozen['numerics'][k] for k in ('max_step_s', 'firmware_step_s', 'reltol', 'max_coupling_iterations')}}

def firmware(directory, design):
    # Actual C program is built on both hosts. New target identity must not be
    # inferred from an older full flash image; ARM object limitation is retained.
    value = v1.firmware(directory, solver_spec(design)['firmware'])
    value['design_id'] = design['design_id']; value['application_source_version'] = 'shared-C-v1-preserved'
    v1.write_json(directory/'build-receipt.json', value)
    return value

def cad(directory, design):
    verify_design(design); source=json.loads((REPO/'configs/reference_cases/door-magnetic-v1/design.json').read_text())
    mech=design['mechanical'];source['revision']='D4';source['magnets']['nominal_center_separation_x_mm']=mech['gap_mm']
    source['door']['driver_closed_world_mm']=[904-mech['gap_mm'],75.265+mech['closed_dz_mm'],2140]
    v1.write_json(directory/'source-design.json',source);v1.write_json(directory/'system-design.json',design)
    v1.command([CAD,REPO/'scripts/door_case/build_cad.py',directory,'--design',directory/'source-design.json','--system-design',directory/'system-design.json'],directory,'cad',300)
    payload=json.loads((directory/'input.json').read_text())['assembly']['payload']
    parts={p['id']:p for p in payload['parts']};tip=parts['tip_magnet']['geometry']['center_mm'];driver=parts['driver_magnet']['geometry']['center_mm']
    actual_world=[1004-driver[0],70+driver[2],2140+driver[1]]
    if any(abs(a-b)>1e-7 for a,b in zip(actual_world,source['door']['driver_closed_world_mm'])):raise ValueError('D4_CAD_FORCE_COORDINATES_DISAGREE')
    if abs(driver[0]-tip[0]-mech['gap_mm'])>1e-7:raise ValueError('D4_CAD_GAP_DISAGREES')
    read=json.loads((directory/'cad-readback.json').read_text())
    value={'design_id':design['design_id'],'parts':len(parts),'driver_closed_world_mm':actual_world,
           'polarity':mech['polarity'],'assembly_sha256':v1.file_hash(directory/'assembly.step'),
           'installation_sha256':v1.file_hash(directory/'installation.step'),'readback_sha256':v1.file_hash(directory/'cad-readback.json'),
           'collisions':read['collisions'],'scope':'Actual BREP readback and static pose; dynamic FEM, strain, fatigue, bracket strength and fabrication release not certified.'}
    v1.write_json(directory/'d4-cad-receipt.json',value);return value
