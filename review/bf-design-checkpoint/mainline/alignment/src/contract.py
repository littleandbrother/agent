"""Executable semantic contract: quantity equality is scoped, never inferred."""
import copy,json,math,pathlib
import jsonschema
ROOT=pathlib.Path(__file__).resolve().parents[1]
AXES=('geometry','force','initial_energy','source_trajectory','circuit','firmware','packet','receiver','mission','units','version')
PURPOSE_AXES={
 'direct_force_kernel':('force',),
 'geometry_trajectory':('geometry','source_trajectory'),
 'imposed_firmware_replay':('firmware','packet','receiver','mission','units'),
 'closed_loop_mission':AXES,
}

def validate(value):
    jsonschema.validate(value,json.loads((ROOT/'contracts/semantic-contract.schema.json').read_text()))
    def finite(x):
        if isinstance(x,float) and not math.isfinite(x):raise ValueError('NONFINITE_CONTRACT_QUANTITY')
        if isinstance(x,dict):
            for v in x.values():finite(v)
        if isinstance(x,list):
            for v in x:finite(v)
    finite(value)
    if value['mission']['deadline_s']>value['mission']['duration_s']:raise ValueError('DEADLINE_AFTER_HORIZON')
    if value['initial_energy']['mechanical_J'] is not None and value['initial_energy']['mechanical_J']<0:raise ValueError('NEGATIVE_INITIAL_ENERGY')
    return value

def assess(left,right,purpose='closed_loop_mission'):
    validate(left);validate(right)
    if purpose not in PURPOSE_AXES:raise ValueError('UNKNOWN_COMPARISON_PURPOSE')
    rows=[]
    for axis in PURPOSE_AXES[purpose]:
        a=left[axis];b=right[axis]
        if axis=='version':
            # Distinct implementations are expected; the identity must be bound,
            # and missing native evidence still blocks mission interpretation.
            reasons=[] if a['source_bound'] and b['source_bound'] else ['SOURCE_IDENTITY_UNBOUND']
            if purpose=='closed_loop_mission' and (not a['native_evidence_available'] or not b['native_evidence_available']):reasons.append('NATIVE_REALIZATION_NOT_CROSS_VALIDATED')
        else:reasons=[] if a==b else ['SEMANTIC_CONTRACT_MISMATCH']
        rows.append({'axis':axis,'compatible':not reasons,'reasons':reasons})
    return {'purpose':purpose,'admitted':all(x['compatible'] for x in rows),'axes':rows,'claim':'Admission only establishes declared fixture comparability; never hardware or Agent qualification.'}

def fixture_copy(contract,**axes):
    """Explicit fixture override, new identity required, source defaults untouched."""
    out=copy.deepcopy(contract)
    out.update(copy.deepcopy(axes));out['contract_id']=contract['contract_id']+'-matched-fixture';out['scope']='synthetic-matched-fixture'
    return validate(out)
