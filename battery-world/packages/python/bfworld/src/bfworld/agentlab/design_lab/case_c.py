"""Actual application execution with independent load/receiver checks.

Participant C is never dlopened into the service. A sandboxed process consumes
the new executable and exact frozen waveform. This is F0, not a SoC/RF model.
"""
import csv
import json
import math
import os
from pathlib import Path
import resource
import signal
import struct
import subprocess
import time
from .contracts import sha, sealed, GATES
from ..store import canonical, identity
from ..engineering_projects import sandbox
CLANG = Path('/Library/Developer/CommandLineTools/usr/bin/clang')
SDK = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk')

VALIDATOR_VERSION = 'c-event-independent-v1'
CURRENT = (0.0000003, 0.00041, 0.000002, 0.001596, 0.003659, 0.000002)

# The executor supplies only time, supply, PGOOD and a modeled sensor port.
# Frames are obtained at TX completion, not sampled before the application ran.
RUNNER = r'''#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <math.h>
void bf_reset(void); int bf_state(void);
int bf_step(double,double,double); double bf_current_mA(void);
void bf_event(uint32_t,uint8_t); void bf_payload(uint8_t*);
int main(int argc,char**argv){
 if(argc!=7)return 10;
 FILE*in=fopen(argv[1],"r"),*out=fopen(argv[2],"w"),*tx=fopen(argv[3],"w");
 if(!in||!out||!tx)return 11;
 double event_time=strtod(argv[4],0),time_s,v,g,current,prev=0,oldstate;int state;
 uint32_t id=(uint32_t)strtoul(argv[5],0,10);uint8_t kind=(uint8_t)strtoul(argv[6],0,10);
 char line[512];if(!fgets(line,sizeof line,in))return 12;
 bf_reset(); fputs("time_s,supply_V,pgood_V,state,current_A\n",out);
 fputs("time_s,payload_hex\n",tx);
 while(fgets(line,sizeof line,in)){
  if(sscanf(line,"%lf,%lf,%lf,%lf,%lf",&time_s,&v,&g,&oldstate,&current)!=5)return 13;
  if(time_s>=event_time)bf_event(id,kind);
  int complete=bf_step((time_s-prev)*1000.0,v,g);state=bf_state();
  double draw=bf_current_mA()/1000.;
  if(state<0||state>5||!isfinite(draw)||draw<0||draw>.02)return 14;
  fprintf(out,"%.17g,%.17g,%.17g,%d,%.17g\n",time_s,v,g,state,draw);
  if(complete){uint8_t p[12]={0};bf_payload(p);fprintf(tx,"%.17g,",time_s);
   for(int j=0;j<12;j++)fprintf(tx,"%02x",p[j]);fputc('\n',tx);}
  prev=time_s;
 }
 fclose(in);fclose(out);fclose(tx);return 0;
}'''


def command(argv, directory, reads, seconds=60):
    """Contain each operation; this is not a cumulative user time limit."""
    profile = sandbox([directory, *reads], directory)
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(directory), 'TMPDIR': str(directory), 'LANG': 'C'}
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32*2**20, 32*2**20))
        resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
    with (directory/'process.log').open('ab') as log:
        p = subprocess.Popen(['/usr/bin/sandbox-exec', '-p', profile, *map(str, argv)],
                             cwd=directory, env=env, stdout=log, stderr=log,
                             start_new_session=True, preexec_fn=limits)
        try:
            result = p.wait(timeout=seconds+5)
        finally:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            p.wait()
    if result:
        raise ValueError('C_EXECUTION_FAILED:'+str(result)+': '+(directory/'process.log').read_text(errors='replace')[-2000:])


def build(design, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    for name, source in design['sources'].items():
        (directory/name).write_text(source)
    (directory/'trusted-runner.c').write_text(RUNNER)
    inputs = [directory/name for name in sorted(design['sources']) if name.endswith('.c')]
    if not CLANG.is_file():raise ValueError('C_NATIVE_CLANG_MISSING')
    command([CLANG, '-isysroot',SDK,'-std=c11', '-O2', '-Wall', '-Werror', *inputs,
             directory/'trusted-runner.c', '-o', directory/'application'], directory,
            [Path('/Library/Developer/CommandLineTools'), Path('/Applications/Xcode.app')])
    objects=[]
    for i, source in enumerate(inputs):
        command([CLANG, '--target=arm-none-eabi', '-mcpu=cortex-m4', '-mthumb', '-mfloat-abi=soft', '-O2',
                 '-std=c11', '-ffreestanding', '-Wall', '-Werror', '-I'+str(directory),
                 '-c', source, '-o', directory/f'application-{i}.o'], directory,
                [CLANG.parent.parent])
        # The finite F0 ABI admits pure C logic plus compiler arithmetic helpers,
        # not participant file/process/network operations in the runner process.
        objects.append(object_symbols(directory/f'application-{i}.o'))
        if any(token in source.read_text() for token in ('__asm','asm(','asm (','__attribute__((constructor')):
            raise ValueError('C_UNSUPPORTED_NATIVE_ESCAPE')
    defined=set().union(*(o['defined'] for o in objects))
    for name in set().union(*(o['undefined'] for o in objects)):
        if name not in defined and not name.startswith('__aeabi_'):raise ValueError('C_UNSUPPORTED_EXTERNAL:'+name)
    files = {p.name: sha(p) for p in directory.iterdir() if p.suffix in ('.c', '.h', '.o') or p.name == 'application'}
    value = {'schema_version': 'bf-c-build-v1', 'design_id': design['design_id'],
             'environment_id': design['environment_id'], 'source_hash': identity(design['sources']),
             'runner_sha256': sha(directory/'trusted-runner.c'), 'files': files,
             'compiler': {'host': str(CLANG), 'arm': str(CLANG), 'compiler_sha256': sha(CLANG),
                          'host_sdk':str(SDK.resolve()),'host_sdk_settings_sha256':sha(SDK/'SDKSettings.json'),
                          'target':'arm-none-eabi/cortex-m4/soft-float','object_machine':'ARM ELF32 checked independently'},
             'levels': {'F0': 'compiled-host-core', 'F1': 'Cortex-M4-object-only',
                        'F2': 'NOT_CHECKED', 'F3': 'NOT_CHECKED', 'F4': 'NOT_CHECKED'}}
    return {**value, 'build_id': 'B-'+identity(value)}


def object_symbols(path):
    data=Path(path).read_bytes()
    if data[:6]!=b'\x7fELF\x01\x01':raise ValueError('C_ARM_OBJECT_FORMAT')
    h=struct.unpack_from('<HHIIIIIHHHHHH',data,16)
    if h[0]!=1 or h[1]!=40:raise ValueError('C_ARM_OBJECT_MACHINE')
    sections=[struct.unpack_from('<10I',data,h[5]+i*h[10]) for i in range(h[11])]
    defined,undefined=set(),set()
    for section in sections:
        if section[1]!=2:continue
        table=sections[section[6]];strings=data[table[4]:table[4]+table[5]]
        for offset in range(section[4],section[4]+section[5],section[9]):
            name,_,_,info,_,index=struct.unpack_from('<IIIBBH',data,offset)
            if info>>4 not in (1,2) or not name:continue
            symbol=strings[name:strings.index(b'\x00',name)].decode()
            (defined if index else undefined).add(symbol)
    return {'defined':defined,'undefined':undefined}


def verify_build(design, receipt, directory):
    if receipt['design_id'] != design['design_id'] or receipt['source_hash'] != identity(design['sources']):
        raise ValueError('C_BUILD_SOURCE_MISMATCH')
    for name, digest in receipt['files'].items():
        if sha(Path(directory)/name) != digest:
            raise ValueError('C_BUILD_ARTIFACT_TAMPER')
    for name, text in design['sources'].items():
        if (Path(directory)/name).read_text() != text:
            raise ValueError('C_BUILD_SOURCE_MISMATCH')


def execute(task, design, receipt, directory, baseline, *, event=None, supply_override=None, stem='execution'):
    verify_build(design, receipt, directory)
    event = event or task['event']
    waveform = Path(baseline['root'])/'program.csv'
    if sha(waveform) != baseline['files']['program.csv']:
        raise ValueError('C_REFERENCE_WAVEFORM_TAMPER')
    # Keep participant code unable to read the trusted reference/evaluator.
    source = directory/'input.csv'
    source.write_bytes(waveform.read_bytes())
    if supply_override is not None:
        with source.open() as stream:rows = list(csv.DictReader(stream))
        for row in rows:
            row['supply_V']=row.get('supply_V',row.get('mcu_supply_V'))
            if supply_override(float(row['time_s'])):
                row['mcu_supply_V'] = row['supply_V'] = '0'
                row['pgood_V'] = '0'
        names = ['time_s','supply_V','pgood_V','state','current_A']
        with source.open('w') as stream:
            writer = csv.writer(stream);writer.writerow(names)
            for row in rows:writer.writerow([row[k] for k in names])
    if stem not in ('execution','port-id','port-kind'):raise ValueError('C_OBSERVATION_STEM_DENIED')
    trace=directory/(stem+'.csv');packets=directory/(stem+'-tx.csv')
    command([directory/'application',source,trace,packets,
             str(event['time_s']),str(event['event_id']),str(event['kind'])], directory, [])
    with trace.open() as stream:rows = list(csv.DictReader(stream))
    with packets.open() as stream:tx = list(csv.DictReader(stream))
    with waveform.open() as stream:original = list(csv.DictReader(stream))
    if len(rows) != len(original) or len(rows) < 2:
        raise ValueError('C_EXECUTION_INCOMPLETE')
    expected_t = [float(r['time_s']) for r in original]
    ticks = [float(r['time_s']) for r in rows]
    if ticks != expected_t or any(b<=a for a,b in zip(ticks,ticks[1:])):
        raise ValueError('C_EXECUTION_TIME_MISMATCH')
    envelope_ok = all(math.isclose(float(r['current_A']), CURRENT[int(r['state'])], abs_tol=1e-14, rel_tol=0)
                      for r in rows)
    reset_ok = all(int(r['state']) == 0 and float(r['current_A']) == CURRENT[0]
                   for r in rows if float(r['supply_V']) < 1.8)
    identical = supply_override is None and all(
        int(a['state']) == int(float(b['state'])) and math.isclose(float(a['current_A']),float(b['current_A']),abs_tol=1e-14,rel_tol=0)
        for a,b in zip(rows, original))
    events = [{'time_s': float(r['time_s']), 'payload_hex': r['payload_hex']} for r in tx]
    value = {'schema_version': 'bf-c-execution-v1', 'task_id': task['task_id'],
             'design_id': design['design_id'], 'build_id': receipt['build_id'],
             'environment_id': task['environment_id'], 'event_input': event,
             'executor_sha256': sha(__file__), 'samples': len(rows), 'transmitted': events,
             'workload_envelope_valid': envelope_ok, 'brownout_reset_valid': reset_ok,
             'power_fixed_point': identical and envelope_ok and reset_ok,
             'native_solve': 'REUSED_EXACT_LOAD_WITNESS' if identical else 'RECHECK_REQUIRED',
             'new_native_solver_calls': 0, 'input_sha256': sha(source),
             'observations': {trace.name:sha(trace),packets.name:sha(packets)},
             'physical_reference': baseline['environment_id'],
             'scope': task['scope'], 'level': 'F0', 'supply_fault_injected': supply_override is not None}
    return {**value, 'execution_id': 'X-'+identity(value)}


def decode(hexadecimal):
    try: data = bytes.fromhex(hexadecimal)
    except ValueError: return None
    if len(data) != 12 or data[:4] != b'BFMC' or data[4] != 1 or data[5] not in (1,2) or data[10] != 0:
        return None
    checksum = 0
    for byte in data[:11]: checksum ^= byte
    if data[11] != checksum: return None
    return {'event_id': int.from_bytes(data[6:10], 'little'), 'kind': data[5]}


def evaluate(task, design, build_receipt, execution, baseline, *, link_loss=False, event_truth=None):
    if any(execution[k] != v for k,v in [('task_id', task['task_id']), ('design_id', design['design_id']),
                                        ('build_id', build_receipt['build_id']), ('environment_id',task['environment_id'])]):
        raise ValueError('C_EXECUTION_BINDING_MISMATCH')
    event = event_truth or task['event']
    if execution['event_input']!=event:raise ValueError('C_EVENT_INPUT_BINDING_MISMATCH')
    decoded = [(e, decode(e['payload_hex'])) for e in execution['transmitted']]
    correct = bool(decoded) and all(d is not None and d['event_id']==event['event_id'] and d['kind']==event['kind']
                                   and e['time_s']>=event['time_s'] for e,d in decoded)
    delivered = [] if link_loss else [(e,d) for e,d in decoded if d is not None and
                   event['time_s'] <= e['time_s'] <= min(task['event']['deadline_s'], event['time_s']+.5)]
    # Receiver uses event identity, not frame capture ID or arrival time.
    unique = {(d['event_id'],d['kind']) for _,d in delivered}
    reference_ok = all(sha(Path(baseline['root'])/name)==digest for name,digest in baseline['files'].items())
    gates = {'source_build_binding':'PASS', 'power_fixed_point':'PASS' if execution['power_fixed_point'] else 'UNEVALUABLE',
             'event_identity':'PASS' if correct else 'FAIL',
             'deadline_receive':'PASS' if correct and delivered else 'FAIL',
             'application_dedup':'PASS' if correct and len(unique)==1 else 'FAIL',
             'reference_integrity':'PASS' if reference_ok else 'UNEVALUABLE'}
    value = {'schema_version':'bf-design-check-v1', 'issuer':'trusted-design-service',
             'task_id': task['task_id'], 'design_id':design['design_id'],
             'environment_id':task['environment_id'], 'validation_id':task['validation_id'],
             'scope':task['scope'], 'execution_id':execution['execution_id'],
             'gates':gates, 'receiver':{'decoded':decoded,'delivered_count':len(delivered),
                 'application_events':len(unique), 'latency_s':min((e['time_s']-event['time_s'] for e,_ in delivered),default=None),
                 'physical_rf':'NOT_CHECKED'},
             'evidence':execution['observations'], 'public_reason':
                 'Actual compiled source, event protocol/identity, receive deadline, and exact native-load witness checked independently.',
             'core_product':'NOT_CHECKED'}
    return {**value, 'check_id':'V-'+identity(value)}

