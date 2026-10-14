"""Source-bound apparatus catalogue: installation, models and scope are separate.

This observes existing assets. It neither calibrates a missing model nor starts
a solver. Participants cannot turn a catalogue entry into a qualification.
"""
import json
from pathlib import Path
from .contracts import sha
from .builder import verify_asset
from ..store import identity

VERSION='bf-executable-lab-model-catalogue-v1'


def catalogue(reference, qualification=None, backend_probes=None, *, expected_environment=None, expected_validation=None):
    root=Path(reference).resolve()
    manifest=json.loads((root/'system-manifest.json').read_text())
    result=json.loads((root/'result.json').read_text())
    domain=json.loads((root/'force/force-domain.json').read_text())
    rom=json.loads((root/'rom.json').read_text())
    eligible=(result.get('run_status')=='completed' and
              manifest['qualification']['nominal_prediction_eligible'] is True and
              domain['interpolation_passed'] is True)
    if not eligible:raise ValueError('CATALOGUE_REQUIRES_VALID_EXISTING_REFERENCE')
    common={'version':manifest['revision'],
        'calibration':{'status':'NATIVE_MODEL_ONLY','hardware':'NOT_TESTED',
            'source':'Existing COMSOL ROM and nominal vendor circuit; fixed model/task.'},
        'qualification':{'status':'PASS','scope':'Frozen reference nominal model only',
            'receipt':str(root/'result.json'),'sha256':sha(root/'result.json')},
        'initial_state':{'electrical':'cold, zero stored electric energy',
                         'mechanical':'original frozen static equilibrium'},
        'supported_actions':['inspect','reuse_exact_reference']}
    assets=[]
    for item in [
        {**common,'id':'D5-piezo-first-mode-ROM',
         'files':{'rom.json':sha(root/'rom.json'),'design-spec.json':sha(root/'design-spec.json')},
         'interface':{'coordinate':'first-mode tip displacement','electrical':'reciprocal piezo terminal'},
         'units':{'coordinate':'m','force':'N','voltage':'V','capacitance':'F'},
         'domain':{'tip_m':domain['tip_m'],'restriction':rom['scope']},
         'parameters':rom,'unsupported':['new geometry/material','contact','fatigue','hardware prediction']},
        {**common,'id':'D5-rotating-magnetic-force',
         'files':{n:sha(root/n) for n in ('force/force-table.npz','force/force-domain.json','design-spec.json')},
         'interface':{'inputs':['tip_m','angle_deg'],'outputs':['force_N','potential_J']},
         'units':{'tip':'m','angle':'degree','force':'N','potential':'J'},
         'domain':{'tip_m':domain['tip_m'],'angle_deg':domain['angle_deg'],
                   'restriction':'Frozen 46mm gap, magnet dimensions, remanence and mounting'},
         'unsupported':['changed magnets/gap/mounting','physical magnet calibration']},
    ]:
        verification=verify_asset(root,item,require_qualified=True)
        assets.append({'root':str(root),'descriptor':item,'verification':verification})
    dependencies=[]
    for path,digest in manifest['source_dependencies'].items():
        source=Path(path)
        if source.is_symlink() or not source.is_file() or sha(source)!=digest:
            raise ValueError('CATALOGUE_VENDOR_DEPENDENCY_DRIFT:'+path)
        dependencies.append({'path':path,'sha256':digest})
    native={'status':'NOT_QUALIFIED','scope':'changed candidate C/native circuit coupling'}
    if qualification is not None:
        path=Path(qualification)
        q=json.loads(path.read_text())
        if ((expected_environment is not None and q['environment_id']!=expected_environment) or
            (expected_validation is not None and q['validation_id']!=expected_validation)):
            raise ValueError('CATALOGUE_QUALIFICATION_BINDING')
        native={'status':'PASS' if q['passed'] else 'FAIL',
            'scope':q['scope'],'environment_id':q['environment_id'],
            'validation_id':q['validation_id'],'receipt':str(path),'sha256':sha(path)}
    optional=None
    if backend_probes is not None:
        path=Path(backend_probes);optional={'receipt':str(path),'sha256':sha(path),
            'facts':json.loads(path.read_text()),'scope':'API/startup only, not product physics'}
    value={'schema_version':VERSION,'assets':assets,'vendor_dependencies':dependencies,
        'native_C':native,'optional_backends':optional,
        'finite_A_B':{'status':'FINITE_SCOPE_ONLY','physical_source_calibration':'NOT_QUALIFIED'},
        'unavailable_models':['calibrated new TENG geometry/contact/charge model',
            'target firmware execution with calibrated activity current',
            'physical RF/link/antenna model','biochemical AFE calibration',
            'implant coupling/variation-tolerance calibration'],
        'model_calls':0,'native_solves':0,'physical_verified':False,
        'scope':'Read-only source-bound capability inventory, not an additional model acceptance.'}
    return {**value,'catalogue_id':'CAT-'+identity(value)}
