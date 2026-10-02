"""Host-executed common C application + explicit behavioral peripheral load SIL.
Not nRF52832/S132 binary execution, calibrated power, radio, or hardware evidence.
"""
from __future__ import annotations
import ctypes, hashlib, importlib.util, json, math, pathlib, shutil, subprocess, tempfile, sys, platform
HERE=pathlib.Path(__file__).resolve().parent
VERSION='firmware-receiver-sil-v1'
DEFAULTS={'brownout_v':1.7,'startup_v':1.8,'device_id':[0x12345678,0x90abcdef],
 'advertising_interval_s':0.1,'random_delay_s':0.005,
 'durations_s':{'reset':.001,'clock':.001,'boot':.003,'init':.002,'read':.001,'payload':.0002,'tx':.0012},
 'currents_a':{'off':1e-6,'reset':.003,'clock':.003,'boot':.003,'init':.003,'read':.003,'payload':.003,'tx':.0053,'sleep':5e-6},
 'silence_s':.35}
LIMITS=['Host common C encoding and gating execute; CPU/SoftDevice/radio are behavioral state models.',
 'All default durations and currents are explicit engineering assumptions, not measured firmware profiles.',
 'Current sensitivity ranges: CPU 1–8 mA, TX 3–15 mA, off/sleep 0.1–20 uA; no calibrated confidence interval.',
 'Ideal virtual link has no RF loss/collision/channel/antenna model; no real radio reception.',
 'PGOOD is GPIO, not a power gate: reset/boot and off leakage load remain.',
 'No persistent event counter; existing decoder silence grouping cannot establish true event or direction.']
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def config(value=None):
    c=json.loads(json.dumps(DEFAULTS));value=value or {}
    for k,v in value.items():
        if k not in c: raise ValueError('UNKNOWN_PROGRAM_KEY:'+k)
        if k in ('durations_s','currents_a'): c[k].update(v)
        else:c[k]=v
    for category in ('durations_s','currents_a'):
        if set(c[category])!=set(DEFAULTS[category]):raise ValueError('UNKNOWN_STATE')
        for v in c[category].values():
            if type(v) not in (float,int) or not math.isfinite(v) or v<=0:raise ValueError('INVALID_STATE_PARAMETER')
    for k in ('brownout_v','startup_v','advertising_interval_s','random_delay_s','silence_s'):
        if type(c[k]) not in (float,int) or not math.isfinite(c[k]) or c[k]<0:raise ValueError('INVALID_PROGRAM_PARAMETER')
    if c['startup_v']<=c['brownout_v'] or c['silence_s']<=0:raise ValueError('INVALID_THRESHOLDS')
    if abs(c['advertising_interval_s']/0.000625-round(c['advertising_interval_s']/0.000625))>1e-8:raise ValueError('BLE_INTERVAL_NOT_625US_MULTIPLE')
    if not .02<=c['advertising_interval_s']<=10.24:raise ValueError('BLE_INTERVAL_OUT_OF_DOMAIN')
    if c['durations_s']['tx']>=c['advertising_interval_s']:raise ValueError('TX_EXCEEDS_INTERVAL')
    if not 0<=c['random_delay_s']<=.01:raise ValueError('BLE_DELAY_OUT_OF_DOMAIN')
    if len(c['device_id'])!=2 or any(type(v)!=int or not 0<=v<=0xffffffff for v in c['device_id']):raise ValueError('INVALID_DEVICE_ID')
    return c

def build_common(program, output):
    c=config(program);out=pathlib.Path(output);out.mkdir(parents=True,exist_ok=True)
    for name in ('bf_event.c','bf_event.h'):shutil.copyfile(HERE/'common'/name,out/name)
    interval=int(round(c['advertising_interval_s']*1e6))
    generated=f'#define BF_ADV_INTERVAL_US {interval}u\n#define BF_CONFIG_ID "{hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()}"\n'
    (out/'strategy.h').write_text(generated)
    cc=shutil.which('cc')
    if not cc:raise RuntimeError('HOST_C_COMPILER_UNAVAILABLE')
    cmd=[cc,'-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-include','strategy.h','bf_event.c','-o','libbf_event.so']
    r=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=30)
    (out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('HOST_BUILD_FAILED')
    # Target adapter is a new derivative, leaving sealed original source intact.
    target=(HERE/'target_main_original.c').read_text()
    target=target.replace('#include <stdint.h>','#include <stdint.h>\n#include "bf_event.h"')
    target=target.replace('if (!nrf_gpio_pin_read(11))','if (!bf_should_start(nrf_gpio_pin_read(11)))')
    target=target.replace('memcpy(payload+4, id, sizeof id);','bf_encode_event(id[0], id[1], payload);')
    target=target.replace('advertising.interval = 160;', 'advertising.interval = bf_advertising_interval_us() / 625;')
    (out/'target_main_common.c').write_text(target)
    target_cc=shutil.which('arm-none-eabi-gcc');target_status='unavailable-no-arm-compiler'
    if target_cc:
        tr=subprocess.run([target_cc,'-mcpu=cortex-m4','-mthumb','-std=c99','-O2','-include','strategy.h','-c','bf_event.c','-o','bf_event_arm.o'],cwd=out,capture_output=True,text=True,timeout=30)
        (out/'target-common-build.log').write_text(tr.stdout+tr.stderr)
        target_status='common-object-compiled' if tr.returncode==0 else 'common-object-build-failed'
    receipt={'version':VERSION,'config':c,'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],
      'command':cmd,'files':{name:digest(out/name) for name in ('bf_event.c','bf_event.h','strategy.h','libbf_event.so','target_main_common.c')},
      'target_common_build':target_status,'full_target_build':'not_run-sdk-not-configured','target_binary_executed':False,
      'host_common_compiled':True,'host_common_executed':False,'current_and_timing_origin':'explicit-assumed-engineering-ranges','limitations':LIMITS}
    receipt['build_identity']=hashlib.sha256(json.dumps(receipt,sort_keys=True).encode()).hexdigest()
    (out/'program-build.json').write_text(json.dumps(receipt,indent=2))
    return receipt

class FirmwareReceiver:
    def __init__(self,program_config=None,build_dir=None):
        self.config=config(program_config)
        if build_dir is None:build_dir=tempfile.mkdtemp(prefix='bf-firmware-sil-')
        self.build_dir=pathlib.Path(build_dir)
        # Rebuild from bound current sources, never trust a foreign shared object.
        self.receipt=build_common(self.config,self.build_dir)
        self.lib=ctypes.CDLL(str((self.build_dir/'libbf_event.so').resolve()))
        self.lib.bf_encode_event.argtypes=[ctypes.c_uint32,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint8)]
        self.lib.bf_should_start.argtypes=[ctypes.c_int];self.lib.bf_should_start.restype=ctypes.c_int
        self.lib.bf_advertising_interval_us.restype=ctypes.c_uint32
        self.state='off';self.elapsed=0.;self.packet_events=[];self.transitions=[];self.brownouts=0;self.interrupted_tx=0;self.boots=0;self._last_end=None;self._payload=None;self._wait_pgood=False;self.common_executed=False
    def _should_start(self,pgood):
        self.common_executed=True
        return self.lib.bf_should_start(bool(pgood))
    def next_transition_s(self):
        """Pure remaining state duration for event-aligned causal integration."""
        if self.state=='off':return None
        duration=(self.config['advertising_interval_s']+self.config['random_delay_s']-self.config['durations_s']['tx']) if self.state=='sleep' else self.config['durations_s'][self.state]
        return max(1e-15,duration-self.elapsed)
    def load_current_a(self,vdd,pgood):
        if not math.isfinite(vdd) or vdd<0:raise ValueError('INVALID_SUPPLY')
        # Even PGOOD-low/reset has current. Supply below brownout leaves leakage.
        state='off' if vdd<self.config['brownout_v'] else self.state
        return self.config['currents_a'][state]
    def _state(self,new,t):
        if new!=self.state:self.transitions.append({'time_s':t,'from':self.state,'to':new})
        self.state=new;self.elapsed=0.
    def advance(self,t_s,dt_s,vdd_v,pgood,min_vdd_v=None):
        if not all(math.isfinite(x) for x in (t_s,dt_s,vdd_v)) or t_s<0 or dt_s<=0 or vdd_v<0:raise ValueError('INVALID_TICK')
        if self._last_end is not None and abs(t_s-self._last_end)>1e-8:raise ValueError('NONCONTIGUOUS_TICK')
        self._last_end=t_s+dt_s;end=t_s+dt_s;before=len(self.packet_events)
        minimum=vdd_v if min_vdd_v is None else min_vdd_v
        if not math.isfinite(minimum) or minimum<0 or minimum>vdd_v+1e-10:raise ValueError('INVALID_MINIMUM_SUPPLY')
        if minimum<self.config['brownout_v']:
            if self.state!='off':
                self.brownouts+=1
                if self.state=='tx':self.interrupted_tx+=1
            self._state('off',end);self._payload=None;self._wait_pgood=False
            return {'state':self.state,'packet_events':[]}
        if self.state=='off':
            if vdd_v>=self.config['startup_v'] and (not self._wait_pgood or pgood):
                self.boots+=1;self._state('reset',end)
            return {'state':self.state,'packet_events':[]}
        # PGOOD checked by application only after boot; does not erase boot energy.
        if self.state=='sleep' and not self._should_start(pgood):
            if self.state=='tx':self.interrupted_tx+=1
            self._state('off',end);self._wait_pgood=True;return {'state':self.state,'packet_events':[]}
        self.elapsed+=dt_s
        duration=(self.lib.bf_advertising_interval_us()/1e6+self.config['random_delay_s']-self.config['durations_s']['tx']) if self.state=='sleep' else self.config['durations_s'][self.state]
        # Quantize transitions to accepted macro ticks. No unaccounted multiple
        # transitions within an interval charged at a single state's current.
        if self.elapsed+1e-12>=duration:
            sequence={'reset':'clock','clock':'boot','boot':'init','init':'read','read':'payload','payload':'tx','tx':'sleep','sleep':'tx'}
            if self.state=='boot' and not self._should_start(pgood):
                self._state('off',end);self._wait_pgood=True
            else:
                if self.state=='payload':
                    self.common_executed=True;data=(ctypes.c_uint8*12)();self.lib.bf_encode_event(*self.config['device_id'],data);self._payload=bytes(data)
                if self.state=='tx':
                    self.packet_events.append({'time_s':end,'payload_hex':self._payload.hex(),'capture_id':f'sil-{len(self.packet_events)}','origin':'simulated-host-common-logic-ideal-virtual-link','protocol':'BFD2','tx_complete':True})
                self._state(sequence[self.state],end)
        return {'state':self.state,'packet_events':self.packet_events[before:]}
    def summary(self):
        return {'version':VERSION,'state':self.state,'packet_events':self.packet_events,'transitions':self.transitions,'boots':self.boots,'brownouts':self.brownouts,'interrupted_tx':self.interrupted_tx,'build_identity':self.receipt['build_identity'],'config':self.config,'limitations':LIMITS,'target_binary_executed':False,'host_common_executed':self.common_executed,'hardware_verified':False}

def _decoder(name):
    spec=importlib.util.spec_from_file_location('_simchain_'+name,HERE/name)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def receive(records,silence_s=.35):
    """Explicit BFP1/BFD2 dispatch; use preserved original decode/group/dedup."""
    groups=[];invalid=0;seen={}
    for row in records:
        if row.get('tx_complete') is False:raise ValueError('INCOMPLETE_TX_NOT_RECEIVABLE')
        rid=row.get('capture_id')
        signature=(row.get('time_s'),row.get('payload_hex'))
        if rid is not None and rid in seen and seen[rid]!=signature:raise ValueError('CAPTURE_ID_CONFLICT')
        if rid is not None:seen[rid]=signature
    for protocol,filename in (('BFP1','pluck_receiver_bfp1.py'),('BFD2','pluck_receiver_d2.py')):
        decoder=_decoder(filename);selected=[]
        for row in records:
            try:data=bytes.fromhex(row['payload_hex'])
            except (ValueError,KeyError,TypeError):continue
            if data[:4]==protocol.encode():selected.append(row)
        groups.extend(decoder.group(selected,silence_s=silence_s))
    for row in records:
        try:data=bytes.fromhex(row['payload_hex']);valid=len(data)==12 and data[:4] in (b'BFP1',b'BFD2')
        except (ValueError,KeyError,TypeError):valid=False
        if not valid:invalid+=1
    return {'events':sorted(groups,key=lambda e:e['first_packet_s']),'invalid_packets':invalid,'origin':'simulated-virtual-link','limitations':LIMITS}

def result(metrics,artifacts=(),status='satisfied',reasons=()):
    return {'run_status':'completed','design_status':status,'metrics':metrics,'applicability':{'status':'in_domain','limits':LIMITS,'checks':{'behavioral_only':True,'hardware_verified':False}},'reasons':list(reasons),'artifacts':list(artifacts)}

def program_build_stage(context):
    out=pathlib.Path(context['output_dir']);out.mkdir(parents=True,exist_ok=True)
    receipt=build_common(context['design'].get('program',{}),out)
    return result({'build_identity':receipt['build_identity'],'host_common_compiled':True,'target_common_build':receipt['target_common_build'],'full_target_build':receipt['full_target_build'],'target_binary_executed':False},[{'kind':'program-build-file','path':p.name} for p in sorted(out.iterdir()) if p.is_file()])

def receiver_stage(context):
    out=pathlib.Path(context['output_dir']);out.mkdir(parents=True,exist_ok=True)
    upstream=context['inputs']['coupled_power'];metrics=upstream['result'].get('metrics',{})
    firmware=metrics.get('firmware',{});records=firmware.get('packet_events',metrics.get('packet_events'))
    if records is None:return result({},status='insufficient_evidence',reasons=['CAUSAL_FIRMWARE_PACKET_EVENTS_MISSING'])
    mission=context['design'].get('mission',{})
    needed=mission.get('minimum_radio_events');deadline=mission.get('receiver_deadline_s');duration=mission.get('duration_s')
    if type(needed)!=int or needed<1 or type(deadline) not in (int,float) or not math.isfinite(deadline) or deadline<=0 or type(duration) not in (int,float) or not math.isfinite(duration) or not 0<deadline<=duration:
        return result({},status='insufficient_evidence',reasons=['MISSING_OR_INVALID_FROZEN_RECEIVER_MISSION'])
    if any(r.get('tx_complete') is not True for r in records):
        return result({},status='insufficient_evidence',reasons=['INCOMPLETE_OR_UNATTESTED_TX_PACKET'])
    timely=[r for r in records if r['time_s']<=deadline]
    data=receive(timely,config(context['design'].get('program',{}))['silence_s'])
    data['late_packets']=len(records)-len(timely);data['mission']={'minimum_radio_events':needed,'receiver_deadline_s':deadline}
    (out/'receiver.json').write_text(json.dumps(data,indent=2))
    count=sum(e['packets'] for e in data['events'])
    return result({'received_packets':count,'grouped_events':len(data['events']),'late_packets':data['late_packets'],'minimum_radio_events':needed,'event_criterion':'silence-group-estimate-not-physical-event','receiver_deadline_s':deadline,'direction':'unknown','radio_model':'ideal-virtual-link','hardware_verified':False},[{'kind':'receiver-events','path':'receiver.json'}],status='satisfied' if len(data['events'])>=needed else 'unsatisfied',reasons=[] if len(data['events'])>=needed else ['INSUFFICIENT_GROUPED_EVENTS_BEFORE_DEADLINE'])

def model_versions():
    sources={str(p.resolve()):digest(p) for p in [HERE/'firmware_receiver.py',HERE/'common/bf_event.c',HERE/'common/bf_event.h',HERE/'target_main_original.c',HERE/'pluck_receiver_d2.py',HERE/'pluck_receiver_bfp1.py']}
    return {stage:{'version':VERSION,'semantics':'host-common-application-plus-behavioral-load-ideal-link; python '+platform.python_version(),'source_hashes':sources,'dependency_hashes':{str(pathlib.Path(sys.executable).resolve()):digest(sys.executable),str(pathlib.Path(shutil.which('cc')).resolve()):digest(shutil.which('cc'))},'applicability':LIMITS} for stage in ('program_build','receiver')}
