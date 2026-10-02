"""Read-only model adapters. Only host C and pure numerical functions are run.

Source trees are inputs. Native tools, main/native firmware builders and caches
are deliberately never called. A waveform replay is an imposed supply fixture,
not a closed-loop power simulation.
"""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
    os.environ[key]='1'
import sys
sys.dont_write_bytecode=True
import copy, ctypes, hashlib, importlib.util, json, pathlib, shutil, subprocess
from unittest.mock import patch
import numpy as np
from scipy.interpolate import RegularGridInterpolator
ROOT=pathlib.Path(__file__).resolve().parents[1]
UP=pathlib.Path(os.environ.get('BF_ALIGNMENT_UPSTREAM','/workspace/shared/current-source-reconciliation-20261001/checkout/battery-world'))
CLOUD=pathlib.Path(os.environ.get('BF_ALIGNMENT_CLOUD','/workspace/shared/bf-simulation-chain/battery-world'))
EVENT=pathlib.Path(os.environ.get('BF_ALIGNMENT_EVENT','/workspace/shared/bf-paper-campaigns/event-solver-qualification-20261001-v2'))
sys.path.insert(0,str(UP/'packages/python/bfworld/src'))
sys.path.insert(0,str(CLOUD/'scripts/door_case'))
from bfworld.agentlab.simulation_chain import native as upstream_native, solver as upstream_solver, contracts as upstream_contracts
from simchain import physics_power as cloud_power, firmware_receiver as cloud_firmware
import coupled as cloud_force

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(path,value):pathlib.Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')

def compile_host(directory,kind,config=None):
    """Compile unchanged upstream C or unchanged cloud common C; never ARM."""
    directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=False)
    cc=shutil.which('cc')
    if not cc:raise RuntimeError('HOST_C_COMPILER_REQUIRED')
    if kind=='upstream':
        config=config or upstream_contracts.DEFAULT['firmware']
        mapping={'INTERVAL_MS':'interval_ms','BOOT_MS':'boot_ms','INIT_MS':'init_ms','TX_MS':'tx_ms','BOOT_MA':'boot_mA','INIT_MA':'init_mA','TX_MA':'tx_mA'}
        header=''.join('#define '+k+' '+str(config[v])+'\n' for k,v in mapping.items())
        header+='#define SLEEP_MA '+str(config['sleep_uA']/1000)+'\n#define RESET_MA '+str(config['reset_uA']/1000)+'\n'
        (directory/'policy.h').write_text(header)
        source=pathlib.Path(upstream_native.__file__).with_name('program.c');shutil.copyfile(source,directory/'program.c')
        # Exactly the upstream builder's BFP1→BFD2 decoder derivation.
        (directory/'receiver.py').write_text((UP/'scripts/pluck_receiver.py').read_text().replace('BFP1','BFD2'))
        cmd=[cc,'-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','program.c','-o','program.dylib']
    elif kind=='cloud':
        config=cloud_firmware.config(config)
        for name in ('bf_event.c','bf_event.h'):shutil.copyfile(CLOUD/'scripts/door_case/simchain/common'/name,directory/name)
        (directory/'strategy.h').write_text(f'#define BF_ADV_INTERVAL_US {int(round(config["advertising_interval_s"]*1e6))}u\n#define BF_CONFIG_ID "{hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()}"\n')
        source=CLOUD/'scripts/door_case/simchain/common/bf_event.c'
        cmd=[cc,'-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-include','strategy.h','bf_event.c','-o','libbf_event.so']
    else:raise ValueError(kind)
    p=subprocess.run(cmd,cwd=directory,capture_output=True,text=True,timeout=30)
    (directory/'build.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise RuntimeError('HOST_BUILD_FAILED:'+p.stderr)
    receipt={'kind':kind,'config':config,'source_sha256':sha(source),'command':cmd,'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0], 'compiler_sha256':sha(cc),'host_C_compiled':True,'ARM_built':False,'target_binary_executed':False,'vendor_model_executed':False,'files':{f.name:sha(f) for f in sorted(directory.iterdir()) if f.is_file()}}
    receipt['build_identity']=digest(receipt);write(directory/'build-receipt.json',receipt)
    return receipt

class UpstreamPolicy:
    names=('RESET','BOOT','WAIT','INIT','TX','SLEEP')
    def __init__(self,directory):
        self.directory=pathlib.Path(directory);self.lib=ctypes.CDLL(str((self.directory/'program.dylib').resolve()))
        self.lib.bf_step.argtypes=[ctypes.c_double]*3;self.lib.bf_step.restype=ctypes.c_int
        self.lib.bf_current_mA.restype=ctypes.c_double;self.lib.bf_state.restype=ctypes.c_int
        self.lib.bf_reset();self.events=[];self.rows=[]
    def advance(self,t,dt,vdd,pgood):
        complete=self.lib.bf_step(dt*1000,float(vdd),float(pgood))
        state=self.names[self.lib.bf_state()]
        if complete:
            data=(ctypes.c_uint8*12)();self.lib.bf_payload(data)
            self.events.append({'time_s':float(t),'payload_hex':bytes(data).hex(),'capture_id':f'fixture-{len(self.events)}','tx_complete':True,'origin':'synthetic-imposed-waveform'})
        self.rows.append({'time_s':float(t),'state':state,'current_A':self.lib.bf_current_mA()/1000})
        return state

class CloudPolicy:
    def __init__(self,directory,config=None):
        directory=pathlib.Path(directory);receipt=json.loads((directory/'build-receipt.json').read_text())
        # Substitution concerns build orchestration only. Behavioral class and C
        # functions remain unchanged, using the exact host-compiled C above.
        with patch.object(cloud_firmware,'build_common',return_value=receipt):
            self.policy=cloud_firmware.FirmwareReceiver(config,build_dir=directory)
        self.events=self.policy.packet_events;self.rows=[]
    def advance(self,t,dt,vdd,pgood):
        state=self.policy.advance(t-dt,dt,float(vdd),bool(pgood>=2.5),min_vdd_v=float(vdd))['state']
        self.rows.append({'time_s':float(t),'state':state.upper(),'current_A':self.policy.load_current_a(float(vdd),bool(pgood>=2.5))})
        return state.upper()

def replay_pair(host_up,host_cloud,duration=.4,step=.0001,perturb=None,cloud_config=None):
    """Same grid and supply values; optional state-relative perturbation is labeled."""
    result={}
    for name,policy in [('upstream',UpstreamPolicy(host_up)),('cloud',CloudPolicy(host_cloud,cloud_config))]:
        first_tx=None;trigger=None
        if name=='upstream':policy.advance(0.,0.,3.3,3.3)
        for i in range(1,round(duration/step)+1):
            t=i*step;vdd=pgood=3.3
            if perturb and first_tx is not None and t>=first_tx+perturb.get('after_tx_s',.0004)-1e-12:
                trigger=trigger if trigger is not None else t
                vdd=perturb.get('supply_V',vdd);pgood=perturb.get('pgood_V',pgood)
            state=policy.advance(t,step,vdd,pgood)
            if first_tx is None and state=='TX':first_tx=t
        result[name]={'events':policy.events,'rows':policy.rows,'first_tx_start_s':first_tx,'perturbation_time_s':trigger}
    return result

def cloud_coordinates(angle,gap_mm):
    ref,_,_,_=cloud_power.normalize({'mechanics':{'installation_gap_mm':gap_mm}})
    origin=ref['door']['product_origin_world_mm'];driver=ref['door']['driver_closed_world_mm'];tip=ref['magnets']['tip_center_mm']
    return ((origin[0]-tip[0]-(driver[0]*np.cos(angle)-driver[1]*np.sin(angle)))/1000,
            (driver[0]*np.sin(angle)+driver[1]*np.cos(angle)-origin[1]-tip[2])/1000)

def force_at(side,angle,q,gap=48.,br=1.25,n=6):
    if side=='upstream':
        dx,dz=upstream_native.coordinates(angle,gap);return upstream_native.force(dx,dz-q,angle,br,n)[2]
    if br!=1.25:raise ValueError('CLOUD_FIXED_REMANENCE_1_25_T')
    dx,dz=cloud_coordinates(angle,gap);return cloud_force.force(dx,dz-q,angle,n)[2]

def interpolated_force(side,angle,q,gap=48.):
    """Exact local cells of original grids; no full-grid or FEM qualification."""
    if side=='upstream':
        aa=np.unique(np.r_[np.linspace(0,5,21),np.linspace(5,15,21),np.linspace(15,65,26)])*np.pi/180;qq=np.linspace(-.008,.008,17)
    else:aa=np.linspace(0,np.deg2rad(65),181);qq=np.linspace(-.008,.008,49)
    if not 0<=angle<=aa[-1] or not -.008<=q<=.008:raise ValueError('OUT_OF_DOMAIN')
    ai=min(max(np.searchsorted(aa,angle)-1,0),len(aa)-2);qi=min(max(np.searchsorted(qq,q)-1,0),len(qq)-2)
    a2=aa[ai:ai+2];q2=qq[qi:qi+2]
    values=np.array([[force_at(side,a,b,gap) for b in q2] for a in a2])
    return float(RegularGridInterpolator((a2,q2),values,bounds_error=True)([[angle,q]])[0])

def source_paths():
    return {'upstream_contracts':pathlib.Path(upstream_contracts.__file__),'upstream_native':pathlib.Path(upstream_native.__file__),'upstream_solver':pathlib.Path(upstream_solver.__file__),'upstream_program':pathlib.Path(upstream_native.__file__).with_name('program.c'),'upstream_receiver':UP/'scripts/pluck_receiver.py','upstream_pipeline':pathlib.Path(upstream_native.__file__).with_name('pipeline.py'),'cloud_power':pathlib.Path(cloud_power.__file__),'cloud_firmware':pathlib.Path(cloud_firmware.__file__),'cloud_force':pathlib.Path(cloud_force.__file__),'cloud_common_c':CLOUD/'scripts/door_case/simchain/common/bf_event.c','cloud_common_h':CLOUD/'scripts/door_case/simchain/common/bf_event.h','cloud_receiver':CLOUD/'scripts/door_case/simchain/pluck_receiver_d2.py','cloud_design':CLOUD/'scripts/door_case/simchain/baseline-design.json','cloud_reference':CLOUD/'configs/reference_cases/door-magnetic-v1/design.json','event_v2':EVENT/'event_power.py','event_receipt':EVENT/'qualification-report.json'}
