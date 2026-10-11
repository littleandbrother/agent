"""Executable A/B model-domain apparatus, distinct from calibrated devices.

The actual participant core is compiled and executed. A trusted runner supplies
external requests/samples and feeds storage voltage back into that core every
tick. Its storage equation is independently replayed by native ngspice. The
source and peripheral assumptions are explicit synthetic F0 contracts; native
numerical agreement does not certify a mechanical harvester or a converter.
"""
import csv
import json
import math
import re
from pathlib import Path
import subprocess
from .case_c import command, CLANG, SDK, object_symbols
from .contracts import sha, sealed
from ..store import identity
from ..runtime_config import SPICE

VERSION = 'finite-source-program-power-service-v4'
GATES = ('compiled_input', 'source_initial_state', 'power_feedback',
         'request_identity', 'deadline_receive', 'information_valid', 'numerical_balance')

RUNNER = r'''#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <math.h>
void reset(void); int step(double,double,uint32_t,int,double,uint32_t*,int*);
double current_A(void); int phase(void);
int main(int argc,char**argv){
 if(argc!=12)return 10;
 FILE*f=fopen(argv[1],"w");if(!f)return 11;
 int ca=atoi(argv[2]);double dt=atof(argv[3]),duration=atof(argv[4]),cap=atof(argv[5]);
 double input=atof(argv[6]),initial=atof(argv[7]),leak=atof(argv[8]),delay=atof(argv[9]);
 int count=atoi(argv[10]),truthshift=atoi(argv[11]);
 double E=initial,last=0;int reset_count=0;reset();
 fputs("t,V,E_J,source_W,load_W,dump_W,state,request_id,tx_id,class,reset\n",f);
 for(int k=0;k<=(int)round(duration/dt);k++){
  double t=k*dt,V=sqrt(2*fmax(E,0)/cap),src=0;
  if(ca==1)src=input*fabs(sin(2*3.141592653589793*30*t));
  else if(t>=delay&&t<delay+.1)src=input/.1;
  uint32_t req=0;int truth=0;double sample=0;
  for(int j=0;j<count;j++){
   double rt=ca==1?2+3*j:0;
   if(t>=rt&&t<rt+(ca==1?.75:1.)){req=(uint32_t)(60001+65537*j);truth=(j+truthshift)%2;
    sample=sin(2*3.141592653589793*(truth?90:30)*(t-rt));}
  }
  if(V<1.8){reset();if(last>=1.8)reset_count++;}
  uint32_t tx=0;int cls=-1;
  int sample_port=phase()==2;
  if(V>=1.8)step(dt,V,req,sample_port,sample_port?sample:0.,&tx,&cls);
  double draw=current_A();
  int state=phase();double modeled=state==1?.00041:state==2?.001596:state==3?.003659:.0000003;
  if(state<0||state>3||!isfinite(draw)||fabs(draw-modeled)>1e-12)return 12;
  double load=V*(draw+leak),raw=E+(src-load)*dt,maximum=.5*cap*3.3*3.3;
  double dump=fmax(0,raw-maximum)/dt;
  fprintf(f,"%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%u,%u,%d,%d\n",
    t,V,E,src,load,dump,phase(),req,tx,cls,reset_count);
  E=fmin(maximum,fmax(0,raw));last=V;
 }
 fclose(f);return 0;
}'''


def manifest(case):
    if case not in ('A', 'B'): raise ValueError('FINITE_CASE_UNKNOWN')
    source = ({'type': 'prescribed-rectified-Norton-equivalent',
               'frequency_Hz': 30, 'power_amplitude_W': .003,
               'mechanical_calibration': 'NOT_CHECKED'} if case == 'A' else
              {'type': 'constant-surface-charge-Q-V-x-work-bound', 'Q_C': 4e-6,
               'C_contact_F': 100e-9, 'C_separated_F': 2e-9, 'transfer_efficiency': .65,
               'transfer_interval_s': [.1, .2], 'initial_surface_charge_C':4e-6,
               'initial_source_electrostatic_J':.5*(4e-6)**2/100e-9,
               'mechanical_calibration': 'NOT_CHECKED',
               'converter_topology': 'abstract-loss-fraction; not an executed SECE/buck circuit'})
    v = {'schema_version': VERSION, 'case': case,
         'case_id': 'vibration-diagnosis-v1' if case == 'A' else 'teng-single-event-v1',
         'scope': case+'-F0-synthetic-source-compiled-core-model-domain-v1',
         'source': source, 'initial_storage_J': 0., 'capacitance_F': 220e-6,
         'voltage_limits_V': [0, 3.3], 'reset_V': 1.8, 'start_V': 3.,
         'step_s': .0005, 'duration_s': 12 if case == 'A' else 1.5,
         'request_times_s': [2, 5, 8, 11] if case == 'A' else [0],
         'deadline_s': .75 if case == 'A' else 1., 'sample_rate_Hz': 256,
         'window_samples': 64 if case=='A' else 4, 'sensor': 'synthetic 30/90Hz sine at an external request; B is event notification, not diagnosis',
         'load': {'idle_A': .3e-6, 'boot_A': .41e-3, 'sample_A': 1.596e-3,
                  'tx_A': 3.659e-3, 'boot_s': .03, 'tx_s': .005},
         'supported_actions': ['application C logic', 'sample rate/window within declared synthetic domain',
                               'program stage timing; exact trusted current for each stage'],
         'sample_port': 'sample data only during sampling phase; no ground-truth label is supplied to participant',
         'unqualified': ['physical/calibrated source', 'converter switching losses', 'native sensor',
                         'SoC/ELF/HEX execution', 'PCB/BOM', 'physical RF', 'full product'],
         'power_model': 'C*d(V^2/2)/dt = source-load-leak-dump; voltage fed to actual C at each tick',
         'equation_domain': 'finite prescribed source, constant C, bounded current, ideal 3.3V clamp',
         'code_sha256': sha(__file__), 'runner_sha256': identity(RUNNER),
         'compiler_sha256': sha(CLANG), 'spice_sha256': sha(SPICE)}
    return {**v, 'environment_id': 'E-'+identity(v)}


def reference_source(case, *, fs=256, tx_s=.005, wrong_class=False, wrong_id=False):
    # Public no-Agent environment reference, not a scored Pi design.
    if case not in ('A','B'):raise ValueError('FINITE_CASE_UNKNOWN')
    text = r'''#include <stdint.h>
static int state,n,crossings;static double age,sample_clock,last;
static uint32_t pending,done;
void reset(void){state=n=crossings=0;age=sample_clock=last=0;pending=done=0;}
int phase(void){return state;}
double current_A(void){return state==1?.00041:state==2?.001596:state==3?.003659:.0000003;}
int step(double dt,double V,uint32_t req,int truth,double sample,uint32_t*out,int*cls){
 (void)truth;
 if(state==0){if(V>=3.&&req&&req!=done){pending=req;state=1;age=0;}}
 else if(state==1){age+=dt;if(age>=.03){state=2;n=crossings=0;sample_clock=0;last=0;}}
 else if(state==2){sample_clock+=dt;
  if(sample_clock>=1./FS){sample_clock-=1./FS;if(n&&((sample>=0)!=(last>=0)))crossings++;
   last=sample;n++;if(n>=64){state=3;age=0;}}}
 else if(state==3){age+=dt;if(age>=TX){*out=pending;*cls=crossings>28;done=pending;state=0;return 1;}}
 return 0;
}'''
    text = text.replace('FS',str(fs)).replace('TX',repr(tx_s))
    if case=='B':text=text.replace('*cls=crossings>28','*cls=0').replace('n>=64','n>=4')
    if wrong_class:text=text.replace('*cls=crossings>28','*cls=0')
    if wrong_id:text=text.replace('*out=pending','*out=1')
    return {'program.c': text}


def build(env, sources, directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    if set(sources)!= {'program.c'} or len(sources['program.c'])>64_000:raise ValueError('FINITE_SOURCE_BOUND')
    (directory/'program.c').write_text(sources['program.c'])
    (directory/'runner.c').write_text(RUNNER)
    if re.search(r'\b(?:__asm__|__asm|asm)\s*\(|constructor',sources['program.c']):
        raise ValueError('FINITE_ESCAPE_DENIED')
    command([CLANG,'-isysroot',SDK,'-O2','-std=c11','-Wall','-Werror','-c','program.c','-o','application-core.o'],
            directory,[CLANG.parent.parent.parent])
    # The host object is Mach-O on macOS; the existing ARM reader is ELF-only.
    listing=subprocess.run(['/usr/bin/nm','-u',str(directory/'application-core.o')],
                           check=True,capture_output=True,text=True,timeout=10)
    host_symbols={'undefined':[line.strip().split()[-1] for line in listing.stdout.splitlines() if line.strip()]}
    # ARM-only symbol inspection misses #ifdef __APPLE__ host file/process
    # calls. The actual host core must have no I/O capability in the trusted
    # runner's output directory. Only bounded memory/math helpers are allowed.
    allowed={'memset','memcpy','memmove','fabs','floor','ceil','sqrt','sin','cos','fmod','stack_chk_fail','stack_chk_guard'}
    if any(s.lstrip('_') not in allowed for s in host_symbols['undefined']):
        raise ValueError('FINITE_HOST_EXTERNAL_DENIED')
    command([CLANG,'-isysroot',SDK,'-O2','-std=c11','-Wall','-Werror','program.c','runner.c','-o','application'],
            directory,[CLANG.parent.parent.parent])
    command([CLANG,'--target=arm-none-eabi','-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft',
             '-O2','-ffreestanding','-std=c11','-Wall','-Werror','-c','program.c','-o','application.o'],
            directory,[CLANG.parent.parent])
    symbols=object_symbols(directory/'application.o')
    if any(not s.startswith('__aeabi_') for s in symbols['undefined']):raise ValueError('FINITE_EXTERNAL_DENIED')
    v={'environment_id':env['environment_id'],'sources_sha256':identity(sources),
       'files':{n:sha(directory/n) for n in ('program.c','runner.c','application-core.o','application','application.o')},
       'host_external_symbols':host_symbols['undefined'],
       'execution_level':'F0 host-core; ARM object only', 'compiler_sha256':sha(CLANG)}
    return {**v,'build_id':'B-'+identity(v)}


def input_energy(env):
    s=env['source']
    return (s['power_amplitude_W'] if env['case']=='A' else
            .5*s['Q_C']**2*(1/s['C_separated_F']-1/s['C_contact_F'])*s['transfer_efficiency'])


def execute(env, sources, receipt, directory, *, source_scale=1., initial_J=None,
            delay_s=None, leak_A=0., dt=None, truth_shift=0, stem='trace'):
    directory=Path(directory)
    if receipt['sources_sha256']!=identity(sources) or receipt['environment_id']!=env['environment_id']:
        raise ValueError('FINITE_BUILD_BINDING')
    for n,d in receipt['files'].items():
        if sha(directory/n)!=d:raise ValueError('FINITE_BINARY_TAMPER')
    if not 0<=source_scale<=1 or not 0<=leak_A<=.01:raise ValueError('FINITE_MODEL_DOMAIN')
    dt=dt or env['step_s'];initial=env['initial_storage_J'] if initial_J is None else initial_J
    if not 0<=initial<=.5*env['capacitance_F']*3.3**2 or dt not in (.0005,.00025):
        raise ValueError('FINITE_MODEL_DOMAIN')
    delay=.1 if delay_s is None else delay_s
    trace=directory/(stem+'.csv')
    command([directory/'application',trace,1 if env['case']=='A' else 2,dt,env['duration_s'],
             env['capacitance_F'],input_energy(env)*source_scale,initial,leak_A,delay,
             len(env['request_times_s']),truth_shift],directory,[])
    with trace.open() as stream:rows=[{k:float(v) for k,v in r.items()} for r in csv.DictReader(stream)]
    if len(rows)!=round(env['duration_s']/dt)+1:raise ValueError('FINITE_TRACE_INCOMPLETE')
    if any(abs(r['t']-i*dt)>1e-9 for i,r in enumerate(rows)):raise ValueError('FINITE_CLOCK_INVALID')
    tx=[{'time_s':r['t'],'request_id':int(r['tx_id']),'class':int(r['class'])} for r in rows if r['tx_id']]
    # The same-clock discrete energy residual is explicit. Grid sensitivity is
    # evaluated in a separate run; this check alone does not establish accuracy.
    residual=max(abs(b['E_J']-max(0,a['E_J']+(a['source_W']-a['load_W']-a['dump_W'])*dt))
                 for a,b in zip(rows,rows[1:]))
    sample_times={}
    for r in rows:
        if int(r['state'])==2 and int(r['request_id']):
            key=str(int(r['request_id']));sample_times[key]=sample_times.get(key,0)+dt
    v={'environment_id':env['environment_id'],'build_id':receipt['build_id'],
       'source_scale':source_scale,'initial_storage_J':initial,'transfer_delay_s':delay,
       'leak_A':leak_A,'dt_s':dt,'truth_shift':truth_shift,'samples':len(rows),'tx':tx,
       'integrated_source_J':sum(r['source_W']*dt for r in rows[:-1]),
       'integrated_load_J':sum(r['load_W']*dt for r in rows[:-1]),
       'initial_J':rows[0]['E_J'],'final_J':rows[-1]['E_J'],
       'energy_residual_J':residual,'resets':int(rows[-1]['reset']),
       'max_supply_V':max(r['V'] for r in rows),
       'sample_stage_s_by_request':sample_times,
       'observations':{trace.name:sha(trace)},'trace_name':trace.name}
    return {**v,'execution_id':'X-'+identity(v)}


def native_energy_check(execution, directory):
    """Native numerical replay of the storage ledger, not a converter model."""
    directory=Path(directory)
    if sha(directory/execution['trace_name'])!=execution['observations'][execution['trace_name']]:
        raise ValueError('FINITE_NUMERIC_INPUT_CHANGED')
    with (directory/execution['trace_name']).open() as stream:rows=list(csv.DictReader(stream))
    intervals=[]
    for i,r in enumerate(rows[:-1]):
        net=float(r['source_W'])-float(r['load_W'])-float(r['dump_W'])
        # Account for explicitly rejected negative energy at the zero boundary.
        if float(r['E_J'])+net*execution['dt_s']<0:
            net=-float(r['E_J'])/execution['dt_s']
        intervals.append(net)
    # Block-integral replay preserves total net energy while avoiding tiny
    # artificial breakpoints at every firmware tick. It validates the energy
    # ledger only, never voltage or individual MCU timing at this coarser grid.
    points=[]
    block=20
    for start in range(0,len(intervals),block):
        segment=intervals[start:start+block];mean=sum(segment)/len(segment)
        t=start*execution['dt_s'];end=(start+len(segment))*execution['dt_s']
        points.extend([(t,mean),(end-1e-6,mean)])
    points.append((float(rows[-1]['t']),0.))
    net=directory/'energy.pwl';net.write_text('\n'.join(f'{t:.12g} {p:.12g}' for t,p in points))
    deck=directory/'energy.cir'
    deck.write_text('Storage energy-coordinate numerical replay\nCenergy e 0 1 IC='+str(execution['initial_J'])+
        '\nIenergy 0 e PWL('+ ' '.join(f'{t:.12g} {p:.12g}' for t,p in points)+')\n'+
        '.options reltol=1e-6 abstol=1e-12\n.control\ntran '+str(execution['dt_s']*10)+' '+str(rows[-1]['t'])+
        ' uic\nset wr_vecnames\nset wr_singlescale\nwrdata energy-native.txt v(e)\nquit\n.endc\n.end\n')
    p=subprocess.run([str(SPICE),'-b',str(deck)],cwd=directory,capture_output=True,text=True,timeout=60)
    (directory/'ngspice.log').write_text(p.stdout+p.stderr)
    if p.returncode or not (directory/'energy-native.txt').is_file():raise ValueError('FINITE_NATIVE_SOLVE_FAILED')
    data=[line.split() for line in (directory/'energy-native.txt').read_text().splitlines()[1:]]
    native_final=float(data[-1][1]);error=abs(native_final-execution['final_J'])
    v={'execution_id':execution['execution_id'],'trace_sha256':execution['observations'][execution['trace_name']],
       'solver':str(SPICE),'solver_sha256':sha(SPICE),'deck_sha256':sha(deck),
       'raw_text_sha256':sha(directory/'energy-native.txt'),'final_storage_J':native_final,
       'reference_final_J':execution['final_J'],'absolute_error_J':error,
       'passed':error<=2e-6,'scope':'Independent native integrator replay, not native source/rectifier/converter qualification'}
    sealed(directory/'native-energy-check.json',v)
    return v


def evaluate(env, receipt, execution, *, link_loss=False, native=None):
    if receipt['build_id']!=execution['build_id'] or env['environment_id']!=execution['environment_id']:
        raise ValueError('FINITE_EXECUTION_BINDING')
    requests=[{'id':60001+65537*i,'t':t,'truth':(i+execution['truth_shift'])%2 if env['case']=='A' else 0}
              for i,t in enumerate(env['request_times_s'])]
    received=[] if link_loss else execution['tx']
    identities={r['id'] for r in requests}
    identity_ok=all(t['request_id'] in identities for t in received)
    outcomes=[]
    for r in requests:
        matches=[t for t in received if t['request_id']==r['id']]
        timely=[t for t in matches if r['t']<=t['time_s']<=r['t']+env['deadline_s']]
        covered=execution['sample_stage_s_by_request'].get(str(r['id']),0)>=env['window_samples']/env['sample_rate_Hz']-2*execution['dt_s']
        outcomes.append({'request_id':r['id'],'request_time_s':r['t'],'received':len(matches),
                         'timely':len(timely)==1,'correct':len(timely)==1 and timely[0]['class']==r['truth'],
                         'sample_window_covered':covered,
                         'latency_s':timely[0]['time_s']-r['t'] if timely else None})
    gates={'compiled_input':'PASS','source_initial_state':'PASS' if execution['initial_J']==0 else 'FAIL',
           'power_feedback':'PASS' if execution['energy_residual_J']<1e-9 else 'UNEVALUABLE',
           'request_identity':'PASS' if identity_ok and len(received)==len(requests) else 'FAIL',
           'deadline_receive':'PASS' if all(r['timely'] for r in outcomes) else 'FAIL',
           'information_valid':'PASS' if all(r['correct'] and r['sample_window_covered'] for r in outcomes) else 'FAIL',
           'numerical_balance':'PASS' if native and native.get('passed') and
                native.get('execution_id')==execution['execution_id'] and
                native.get('trace_sha256')==execution['observations'][execution['trace_name']]
                else 'UNEVALUABLE' if native else 'NOT_CHECKED'}
    v={'environment_id':env['environment_id'],'execution_id':execution['execution_id'],'scope':env['scope'],
       'gates':gates,'requests':outcomes,'scoped_status':'PASS' if all(v=='PASS' for v in gates.values()) else
       'FAIL' if 'FAIL' in gates.values() else 'UNEVALUABLE',
       'full_case_qualified':False,'full_product_passed':False,'physical':'NOT_TESTED',
       'model_scope':'Synthetic source and shared compiled core; calibrated mechanics, switching electronics and target/RF remain unqualified'}
    return {**v,'check_id':'V-'+identity(v)}
