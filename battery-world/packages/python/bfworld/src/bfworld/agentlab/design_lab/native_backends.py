"""Optional apparatus API probes, isolated from participant designs.

An API pass is never a vendor-model, MCU-current or physical qualification.
The pinned LTspice reference and all prior native artifacts remain unchanged.
"""
import ctypes as c
import json
from pathlib import Path
import subprocess
from .contracts import sha, sealed
from ..store import identity


class Vector(c.Structure):
    _fields_=[('name',c.c_char_p),('kind',c.c_int),('flags',c.c_short),
              ('real',c.POINTER(c.c_double)),('complex',c.c_void_p),('length',c.c_int)]


def shared_spice_probe(library):
    """Trusted RC control tests load/observe/alter; call in a dedicated process."""
    library=Path(library)
    lib=c.CDLL(str(library));messages=[]
    char=c.CFUNCTYPE(c.c_int,c.c_char_p,c.c_int,c.c_void_p)
    exit_callback=c.CFUNCTYPE(c.c_int,c.c_int,c.c_bool,c.c_bool,c.c_int,c.c_void_p)
    output=char(lambda text,_id,_data: messages.append(text.decode(errors='replace')) or 0)
    status=char(lambda *_:0)
    closed=[]
    on_exit=exit_callback(lambda code,*_:closed.append(code) or 0)
    lib.ngSpice_Init.argtypes=[c.c_void_p]*7;lib.ngSpice_Init.restype=c.c_int
    lib.ngSpice_Command.argtypes=[c.c_char_p];lib.ngSpice_Command.restype=c.c_int
    lib.ngSpice_Circ.argtypes=[c.POINTER(c.c_char_p)];lib.ngSpice_Circ.restype=c.c_int
    lib.ngGet_Vec_Info.argtypes=[c.c_char_p];lib.ngGet_Vec_Info.restype=c.POINTER(Vector)
    if lib.ngSpice_Init(output,status,on_exit,None,None,None,None):raise ValueError('NGSPICE_INIT_FAILED')
    lines=[b'BF isolated shared-library RC probe',b'V1 in 0 DC 1',b'R1 in out 1000',
           b'C1 out 0 1u IC=0',b'.tran 10u 10m uic',b'.end',None]
    if lib.ngSpice_Circ((c.c_char_p*len(lines))(*lines)):raise ValueError('NGSPICE_CIRCUIT_REJECTED')
    def command(value):
        if lib.ngSpice_Command(value.encode()) or closed:raise ValueError('NGSPICE_COMMAND_FAILED:'+value)
    def vector(name):
        p=lib.ngGet_Vec_Info(name.encode())
        if not p or not 0<p.contents.length<100000:raise ValueError('NGSPICE_VECTOR_UNAVAILABLE:'+name)
        v=p.contents
        return [v.real[i] for i in range(v.length)]
    command('run');time=vector('time');before=vector('v(out)')
    command('reset');command('alter R1 = 2000');command('run')
    after_t=vector('time');after=vector('v(out)')
    def nearest(t,y,target):return y[min(range(len(t)),key=lambda i:abs(t[i]-target))]
    fast=nearest(time,before,.001);slow=nearest(after_t,after,.001)
    checks={'initial_zero_charge':abs(before[0])<.02,
            'first_time_constant':.61<fast<.65,
            'alter_changes_response':.37<slow<.42 and fast-slow>.2,
            'near_steady_state':before[-1]>.999,
            'callbacks_observed':bool(messages)}
    return {'backend':'ngspice-shared','library':str(library),'library_sha256':sha(library),
            'checks':checks,'passed':all(checks.values()),
            'observations':{'voltage_at_1ms_1kohm_V':fast,'voltage_at_1ms_2kohm_V':slow,
                            'initial_V':before[0],'data_points':[len(time),len(after_t)]},
            'scope':'Trusted RC API load/run/observe/alter only; no migrated LTC/TENG/PMIC model or coupled product qualification.'}


def inventory():
    from .. import runtime_config as paths
    rt=paths.RUNTIME_ROOT
    values={'cadquery-python':paths.CAD,'comsol':paths.COMSOL,
            'ngspice-cli':paths.SPICE,'arm-gcc':paths.GCC,
            'ngspice-shared':paths.SPICE_SHARED,
            'renode':paths.RENODE}
    result={name:{'path':str(path),'installed':path.is_file(),
                  'sha256':sha(path) if path.is_file() else None} for name,path in values.items()}
    value={'schema_version':'bf-executable-lab-backend-inventory-v1','backends':result,
           'qualified_domains':{
               'native-C':'Fixed D5 COMSOL ROM, magnetic force and LTspice vendor circuit; changed candidate C/current requires converged qualification.',
               'finite-A-B':'Declared synthetic/finite source, sensor and program models only.',
               'target-builds':['nRF52832 bare-metal','nRF52832 SDK17/S132','STM32L031K6','STM32L432KCU6'],
               'Renode':'Installed optional ARM runtime; nRF52840 platform exists. nRF52832/S132 and STM32 paper applications NOT_QUALIFIED.',
               'shared-ngspice':'Optional RC API qualification does not replace native reference or calibrate vendor models.'},
           'physical_calibration':'NOT_TESTED','target_execution_current_calibration':'NOT_QUALIFIED',
           'TENG_new_geometry_calibration':'NOT_QUALIFIED','full_product_passed':False}
    return {**value,'inventory_id':'BACKENDS-'+identity(value)}


def probe_receipt(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    value=inventory();sealed(out/'inventory.json',value)
    shared=shared_spice_probe(value['backends']['ngspice-shared']['path'])
    renode=Path(value['backends']['renode']['path'])
    result=subprocess.run([str(renode),'--version'],capture_output=True,text=True,timeout=30)
    report={'schema_version':'bf-executable-lab-optional-backend-probes-v1','ngspice_shared':shared,
            'renode_startup':{'returncode':result.returncode,'version':result.stdout.strip(),
                             'passed':result.returncode==0 and '1.17.0' in result.stdout},
            'model_calls':0,'old_native_solves':0,'vendor_or_target_execution_qualified':False,
            'scope':'Optional API/startup capability; no participant geometry or simulation repeated.'}
    sealed(out/'backend-probes.json',report)
    return report
