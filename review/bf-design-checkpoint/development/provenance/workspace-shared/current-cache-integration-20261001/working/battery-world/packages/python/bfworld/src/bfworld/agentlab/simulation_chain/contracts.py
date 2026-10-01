"""Bounded engineering contracts; these do not modify the frozen research world."""
import hashlib
import json
import math
from pathlib import Path

VERSION = 'door-closed-simulation-v1'
DEFAULT = {
    'schema_version': 'closed-simulation-spec-v1',
    'mechanical': {'gap_mm': 48., 'opening_s': 2., 'angle_deg': 65.,
                   'remanence_T': 1.25, 'damping_ratio': .02},
    'circuit': {'cin_uF': 47., 'cout_uF': 100., 'initial_vin_V': 0.,
                'diagnostic_input_A': 0.},
    'firmware': {'interval_ms': 100., 'boot_ms': 53.8, 'init_ms': 13.,
                 'tx_ms': 5., 'boot_mA': .410, 'init_mA': 1.596,
                 'tx_mA': 3.659, 'sleep_uA': 2., 'reset_uA': .3},
    'link': {'loss_probability': 0., 'seed': 17, 'scan_duty': 1.},
    'solver': {'max_step_s': .00005, 'firmware_step_s': .0001,
               'reltol': .0001, 'max_coupling_iterations': 8},
    'presentation': {'camera_deg': 35.},
}
RANGES = {
 'mechanical': {'gap_mm':(28,70),'opening_s':(0,8),'angle_deg':(0,65),'remanence_T':(1,1.4),'damping_ratio':(.01,.08)},
 'circuit': {'cin_uF':(10,220),'cout_uF':(10,470),'initial_vin_V':(0,6),'diagnostic_input_A':(0,.003)},
 'firmware': {'interval_ms':(20,1000),'boot_ms':(1,100),'init_ms':(1,100),'tx_ms':(.5,20),'boot_mA':(.05,5),'init_mA':(.1,10),'tx_mA':(1,15),'sleep_uA':(.1,20),'reset_uA':(.01,5)},
 'link': {'loss_probability':(0,1),'seed':(0,2147483647),'scan_duty':(0,1)},
 'solver': {'max_step_s':(.000005,.0001),'firmware_step_s':(.00001,.0002),'reltol':(.000001,.001),'max_coupling_iterations':(2,12)},
 'presentation': {'camera_deg':(-180,180)},
}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

class ChainError(Exception):
    def __init__(self, status, reason):
        self.status=status
        super().__init__(reason)

def validate(spec):
    if not isinstance(spec,dict) or set(spec)-set(DEFAULT):
        raise ChainError('input_error','Unknown design fields')
    result=json.loads(json.dumps(DEFAULT))
    if spec.get('schema_version',DEFAULT['schema_version'])!=DEFAULT['schema_version']:
        raise ChainError('input_error','Unsupported design schema')
    for group,ranges in RANGES.items():
        supplied=spec.get(group,{})
        if not isinstance(supplied,dict) or set(supplied)-set(ranges):
            raise ChainError('input_error','Unknown fields: '+group)
        for name,value in supplied.items():
            lo,hi=ranges[name]
            if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
                raise ChainError('input_error','Invalid '+group+'.'+name)
            if name in ('seed','max_coupling_iterations') and int(value)!=value:
                raise ChainError('input_error','Integer required: '+name)
            result[group][name]=value
    if result['firmware']['interval_ms']<=result['firmware']['tx_ms']:
        raise ChainError('input_error','TX interval must exceed TX duration')
    return result

def physical_spec(spec):
    return {k:v for k,v in spec.items() if k!='presentation'}

def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
