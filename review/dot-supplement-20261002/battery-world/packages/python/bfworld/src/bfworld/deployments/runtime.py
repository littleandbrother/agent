"""Multi-source, repeated-request world v2 with exact checkpoint continuation."""
from __future__ import annotations
import json
import math
from dataclasses import asdict,dataclass,replace
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash,file_hash,write_canonical_json
from bfworld.coupled.engine import classify,signal_window,Reference,input_current
from .ports import SCENES,Source,environment,port,scene_manifest

@dataclass(frozen=True)
class DeploymentDesign:
    capacitance_f:float=.0022
    esr_ohm:float=6.
    start_v:float=2.4
    tx_power_w:float=.036
    source_scale:float=1.
    model_threshold:int=25
    receiver_distance_m:float|None=None
    disabled_sources:tuple[str,...]=()

def source_identity():
    root=Path(__file__).parent
    return canonical_hash({p.name:file_hash(p) for p in (root/'runtime.py',root/'ports.py',root.parent/'coupled/engine.py')})

class Session:
    def __init__(self,scene:str,design:DeploymentDesign=DeploymentDesign(),*,dt_s:float=.002,duration_s:float=4.):
        if scene not in SCENES:raise ValueError('unknown scene')
        if not (.0001<=design.capacitance_f<=.01 and 0<=design.esr_ohm<=100 and .001<=design.tx_power_w<=.1 and 0<=design.source_scale<=3 and 1.81<=design.start_v<=3.4):raise ValueError('invalid design domain')
        if not(0<dt_s<=.002 and 0<duration_s<=8):raise ValueError('invalid time domain')
        if design.receiver_distance_m is not None and not 0<=design.receiver_distance_m<=1000:raise ValueError('invalid receiver distance')
        source_ids={s.id for s in SCENES[scene]['sources']}
        if set(design.disabled_sources)-source_ids:raise ValueError('unknown disabled source')
        self.config={'scene':scene,'design':json.loads(json.dumps(asdict(design))),'dt_s':dt_s,'duration_s':duration_s,'source_identity':source_identity()}
        self.design=design;self.sources=[replace(s,scale=s.scale*design.source_scale) for s in SCENES[scene]['sources'] if s.id not in design.disabled_sources]
        self.state={'step':0,'shaft_angle':0.,'voltage':2.65,'pmic':'off','mcu':'off','until':0.,'current_request':None,
          'receiver_queue':[],'brownouts':0,'overvoltage':False,'rows':[],'events':[],
          'requests':[{'id':f'request-{i}','release_s':t,'deadline_s':t+.9,'state':'pending','prediction':None,'samples':[], 'transmit_s':None,'receive_s':None,'correct':False} for i,t in enumerate((.3,1.5,2.7)) if t<duration_s],
          'ledger':{k:0. for k in ('raw_harvest','harvest','source_conversion_loss','load','regulator_loss','esr_loss','leakage','clamp')},
          'source_energy':{s.id:0. for s in self.sources}}
    def emit(self,t,priority,kind,**facts):
        events=self.state['events'];events.append({'seq':len(events),'time_s':t,'priority':priority,'type':kind,'facts':facts})
    def advance(self,steps:int|None=None):
        s=self.state;d=self.design;dt=self.config['dt_s'];total=round(self.config['duration_s']/dt)
        final=total if steps is None else min(total,s['step']+steps-1)
        powers={'off':0.,'cold-start':0.,'boot':.002,'sleep':.00005,'sense':.003,'infer':.009,'tx':d.tx_power_w}
        while s['step']<=final:
            step=s['step'];t=round(step*dt,9);v=s['voltage'];interval=s['mcu'];power=powers[interval];raw_ports=[];current=0.
            env=environment(self.config['scene'],t)
            if step:
                env_mid=environment(self.config['scene'],t-dt/2)
                s['shaft_angle']+=2*math.pi*env_mid['rpm']/60*dt
                previous_ports=[port(h,v,env_mid,t-dt/2) for h in self.sources]
                i0=input_current(v,power,d.esr_ohm,.82);h0=sum(h['bus_current_a'] for h in previous_ports)
                vm=max(.01,v+.5*dt*(h0-i0-v/200000)/d.capacitance_f)
                raw_ports=[port(h,vm,env_mid,t-dt/2) for h in self.sources]
                current=input_current(vm,power,d.esr_ohm,.82);hi=sum(h['bus_current_a'] for h in raw_ports);leak=vm/200000
                raw=max(.001,v+dt*(hi-current-leak)/d.capacitance_f);new=min(3.45,raw);work_v=(v+raw)/2
                e_h=work_v*hi*dt;e_esr=current**2*d.esr_ohm*dt;e_regin=work_v*current*dt-e_esr
                s['ledger']['harvest']+=e_h;s['ledger']['esr_loss']+=e_esr;s['ledger']['regulator_loss']+=e_regin*.18
                s['ledger']['load']+=e_regin*.82;s['ledger']['leakage']+=work_v*leak*dt;s['ledger']['clamp']+=.5*d.capacitance_f*(raw**2-new**2)
                for h,source in zip(raw_ports,self.sources):
                    bus_energy=work_v*h['bus_current_a']*dt;s['source_energy'][source.id]+=bus_energy
                    s['ledger']['raw_harvest']+=bus_energy/source.efficiency
                    s['ledger']['source_conversion_loss']+=bus_energy*(1/source.efficiency-1)
                v=new;s['voltage']=v
            else:raw_ports=[port(h,v,env,t) for h in self.sources]
            terminal=v-current*d.esr_ohm
            req=s['requests'][s['current_request']] if s['current_request'] is not None else None
            if terminal<1.8 and s['pmic']!='off':
                self.emit(t,10,'undervoltage',voltage_v=terminal)
                s['pmic']='off';self.emit(t,20,'pmic_transition',state='off')
                if req is not None:
                    s['brownouts']+=1;req['state']='aborted';self.emit(t,30,'mcu_transition',state='off');self.emit(t,40,'request_aborted',request_id=req['id'])
                    s['current_request']=None;req=None
                s['mcu']='off'
            elif s['pmic']=='off' and v>=d.start_v:
                s['pmic']='cold-start';s['until']=t+.004;self.emit(t,20,'pmic_transition',state='cold-start')
            elif s['pmic']=='cold-start' and t>=s['until']-1e-9:
                s['pmic']='regulated';s['mcu']='boot';s['until']=t+.012;self.emit(t,20,'pmic_transition',state='regulated');self.emit(t,30,'mcu_transition',state='boot')
            elif s['mcu']=='boot' and t>=s['until']-1e-9:s['mcu']='sleep';self.emit(t,30,'mcu_transition',state='sleep')
            if s['mcu']=='sleep' and s['current_request'] is None:
                pending=next((i for i,r in enumerate(s['requests']) if r['state']=='pending' and r['release_s']<=t),None)
                if pending is not None:
                    s['current_request']=pending;req=s['requests'][pending];req['state']='acquiring';req['sense_start_s']=t;s['mcu']='sense';s['until']=t+.08
                    self.emit(t,30,'mcu_transition',state='sense');self.emit(t,40,'acquisition_started',request_id=req['id'])
            elif s['mcu']=='sense':
                samples=signal_window(Reference());n=min(128,round((t-req['sense_start_s'])/.08*128));req['samples']=samples[:max(0,n)]
                if t>=s['until']-1e-9:
                    req['samples']=samples;s['mcu']='infer';s['until']=t+.035;req['state']='inferring'
                    self.emit(t,30,'mcu_transition',state='infer');self.emit(t,40,'acquisition_completed',request_id=req['id'],sample_hash=canonical_hash(samples))
            elif s['mcu']=='infer' and t>=s['until']-1e-9:
                req['prediction']=classify(req['samples'],d.model_threshold);req['correct']=req['prediction']['predicted_label']=='bearing-fault';req['state']='transmitting';req['transmit_s']=t
                s['mcu']='tx';s['until']=t+.04;self.emit(t,30,'mcu_transition',state='tx');self.emit(t,40,'inference_completed',request_id=req['id'],**req['prediction'])
            elif s['mcu']=='tx' and t>=s['until']-1e-9:
                req['state']='transmitted';s['receiver_queue'].append({'request':s['current_request'],'at':t+.008});s['current_request']=None
                s['mcu']='sleep';self.emit(t,30,'mcu_transition',state='sleep');self.emit(t,40,'transmission_completed',request_id=req['id'])
            for entry in s['receiver_queue'][:]:
                if t>=entry['at']-1e-9:
                    r=s['requests'][entry['request']];distance=d.receiver_distance_m if d.receiver_distance_m is not None else SCENES[self.config['scene']]['distance_m']
                    delivered=distance<=45
                    r['state']='received' if delivered else 'receiver-lost';r['receive_s']=t if delivered else None
                    self.emit(t,40,'receiver_delivered' if delivered else 'receiver_no_delivery',request_id=r['id'],distance_m=distance,model='deterministic 45 m range threshold, not validated RF propagation')
                    s['receiver_queue'].remove(entry)
            for r in s['requests']:
                if r['state']=='pending' and t>r['deadline_s']:r['state']='expired';self.emit(t,40,'deadline_expired',request_id=r['id'])
            energy=.5*d.capacitance_f*v*v
            s['rows'].append({'time_s':t,'environment':env,'storage_voltage_v':round(v,9),'terminal_voltage_v':round(terminal,9),
               'stored_energy_j':round(energy,12),'energy_fill':max(0,min(1,(v*v-1.8**2)/(3.6**2-1.8**2))),
               'ports':raw_ports,'harvest_power_w':sum(p['bus_power_w'] for p in raw_ports),'load_power_w':power,'interval_state':interval,
               'pmic_state':s['pmic'],'mcu_state':s['mcu'],'brownouts':s['brownouts'],'delivered_requests':sum(r['state']=='received' for r in s['requests']),
               'source_energy_j':dict(s['source_energy']),'rotary_angle_rad':s['shaft_angle'],
               'piezo_displacement_mm':env['acceleration_g']*math.sin(2*math.pi*18*t)*.4,
               'sample_count':len(req['samples']) if req else 0})
            s['step']+=1
        return self
    def checkpoint(self,path:Path):
        obj={'schema_version':'deployment-checkpoint-v2','config':self.config,'state':self.state};obj['content_hash']=canonical_hash(obj);write_canonical_json(path,obj)
    @classmethod
    def restore(cls,path:Path):
        obj=json.loads(path.read_text());claimed=obj.pop('content_hash')
        if canonical_hash(obj)!=claimed or obj['config']['source_identity']!=source_identity():raise ValueError('checkpoint identity/source drift')
        config=obj['config'];instance=cls(config['scene'],DeploymentDesign(**config['design']),dt_s=config['dt_s'],duration_s=config['duration_s']);instance.state=obj['state'];return instance
    def result(self):
        s=self.state;d=self.design
        if s['step']<=round(self.config['duration_s']/self.config['dt_s']):raise ValueError('unfinished session')
        requests=[]
        for r in s['requests']:
            requests.append({**r,'passed':r['correct'] and r['receive_s'] is not None and r['receive_s']<=r['deadline_s']})
        delta=.5*d.capacitance_f*(s['voltage']**2-2.65**2);ledger=s['ledger']
        losses=sum(ledger[k] for k in ('load','regulator_loss','esr_loss','leakage','clamp'))
        residual=ledger['harvest']-losses-delta
        result={'schema_version':'deployment-run-v2','config':self.config,'scene':scene_manifest(self.config['scene']),
          'rows':s['rows'],'events':s['events'],'requests':requests,
          'ledger':{**ledger,'storage_delta_j':delta,'residual_j':residual,'relative_residual':abs(residual)/max(losses,ledger['harvest'],.5*d.capacitance_f*2.65**2)},
          'summary':{'request_count':len(requests),'delivered_count':sum(r['receive_s'] is not None for r in requests),
            'correct_count':sum(r['correct'] for r in requests),'successful_requests':sum(r['passed'] for r in requests),
            'brownouts':s['brownouts'],'physical_mission_pass':bool(requests) and all(r['passed'] for r in requests) and s['brownouts']==0,
            'minimum_terminal_v':min(r['terminal_voltage_v'] for r in s['rows']),'energy_by_source_j':s['source_energy'],
            'evidence_admissible':False,'verified_mission_success':False},
          'fidelity':{'source':'analytic voltage-dependent electrical port; no mechanical/thermal back-action','converter':'fixed ratio/efficiency, no MPPT claim',
            'storage':'midpoint capacitor + ESR + leakage + ideal clamp','information':'executed integer classifier on synthetic window',
            'receiver':'separate delivery event with illustrative range threshold'},
          'visual_bindings':{'capacitor.fill':'rows[].energy_fill = clamp((V²-Voff²)/(Vmax²-Voff²))','source.activity':'rows[].ports[].bus_power_w',
            'shaft.rotation':'rows[].rotary_angle_rad','piezo.deflection':'rows[].piezo_displacement_mm (schematic amplified geometry)','node.state':'rows[].mcu_state','receiver.status':'rows[].delivered_requests'},
          'claim_boundary':'Computational scenario, precharged initial storage, synthetic forcing and data. Not a calibrated deployment or physical confirmation.'}
        result['content_hash']=canonical_hash(result);return result

def execute(scene:str,design:DeploymentDesign=DeploymentDesign(),**kwargs):return Session(scene,design,**kwargs).advance().result()
