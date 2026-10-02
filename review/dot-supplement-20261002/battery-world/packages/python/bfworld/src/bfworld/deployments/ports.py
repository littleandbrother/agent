"""Raw electrical port -> fixed-ratio converter -> shared storage bus.

All source responses depend on bus voltage, not a precomputed power schedule.
Models are deliberately uncalibrated. Environmental traces are synthetic.
"""
from __future__ import annotations
import math
from dataclasses import dataclass,asdict

@dataclass(frozen=True)
class Source:
    id:str
    kind:str
    position:tuple[float,float,float]
    scale:float=1.
    ratio:float=1.
    efficiency:float=.86

def environment(scene:str,t:float)->dict:
    # Seconds are literal synthetic test seconds, not an implicit day timewarp.
    sun=.8*(.65+.35*math.cos(t*.9))
    shade=.12 if 1.4<t<2.3 else 1.
    return {'time_s':t,'irradiance_w_m2':max(0,800*sun*shade) if scene in ('solar-field','hybrid-station') else 35*(.7+.3*math.cos(t)) if scene=='indoor-office' else 0.,
      'rpm':120+25*math.sin(t*1.7) if scene in ('rotary-factory','hybrid-station') else 0.,
      'acceleration_g':.8+.55*math.sin(t*5)**8 if scene in ('vibration-bridge','hybrid-station') else 0.,
      'temperature_delta_k':26+6*math.sin(t*.6) if scene=='thermal-pipeline' else 0.,
      'ambient_temperature_c':25.,'synthetic':True}

def port(source:Source,bus_voltage:float,env:dict,t:float)->dict:
    if source.kind not in ('rotary','solar','piezo','thermal'):raise ValueError('unknown harvester kind')
    if not (0<=source.scale<=8 and source.ratio>0 and 0<source.efficiency<=1 and bus_voltage>=0):raise ValueError('invalid source/port domain')
    raw_v=bus_voltage/source.ratio
    if source.kind=='solar':
        illumination=env['irradiance_w_m2']/1000
        voc=max(0,5.2+.22*math.log(max(illumination,1e-12))) if illumination>0 else 0
        isc=.018*illumination*source.scale
        raw_i=max(0,isc*(1-math.exp(min(50,(raw_v-voc)/.28)))) if voc else 0
        mechanism='simplified exponential photovoltaic I-V; no calibrated diode parameters'
    elif source.kind=='rotary':
        rpm=env['rpm'];source_i=.0038*max(0,rpm)/120*abs(math.sin(2*math.pi*4*rpm/60*t))
        raw_i=source.scale*max(0,source_i-raw_v/3000);voc=source_i*3000
        mechanism='rectified Norton source with synthetic motion; no contact mechanics calibration'
    elif source.kind=='piezo':
        voc=7*max(0,env['acceleration_g'])*abs(math.sin(2*math.pi*18*t))
        raw_i=source.scale*max(0,(voc-raw_v)/950)
        mechanism='rectified voltage-source envelope and series impedance; no mechanical back-action model'
    else:
        voc=.065*max(0,env['temperature_delta_k'])
        raw_i=source.scale*max(0,(voc-raw_v)/70)
        mechanism='Seebeck voltage and internal resistance; no thermal-network feedback model'
    bus_i=raw_i*source.efficiency/source.ratio
    raw_power=raw_v*raw_i;bus_power=bus_voltage*bus_i
    return {'source_id':source.id,'kind':source.kind,'raw_voltage_v':raw_v,'raw_current_a':raw_i,
      'open_circuit_voltage_v':voc,'bus_voltage_v':bus_voltage,'bus_current_a':bus_i,
      'raw_power_w':raw_power,'bus_power_w':bus_power,'conversion_loss_w':raw_power-bus_power,
      'model':mechanism,'fidelity':'F1-uncalibrated','measured':False}

SCENES={
 'rotary-factory':{'title':'Rotary machine hall','subtitle':'Rotation → condition monitoring','category':'INDUSTRIAL MOTION','color':'#c4b581','sources':[Source('rotary-1','rotary',(-3,0,0))],'distance_m':12.,'description':'A rotary source mounted on a machine shaft supplies a condition-monitoring node.'},
 'solar-field':{'title':'Solar field station','subtitle':'Light → environmental sensing','category':'OUTDOOR SOLAR','color':'#97c69d','sources':[Source('pv-1','solar',(-3,0,0),.8)],'distance_m':28.,'description':'An outdoor photovoltaic panel experiences a synthetic cloud-shadow interval.'},
 'indoor-office':{'title':'Ambient office node','subtitle':'Indoor light → room monitoring','category':'INDOOR AMBIENT','color':'#c2bb9e','sources':[Source('pv-indoor','solar',(-2,0,0),3)],'distance_m':8.,'description':'Large-area low-light PV powers a precharged node; illumination may be insufficient for sustained service.'},
 'vibration-bridge':{'title':'Instrumented bridge','subtitle':'Structural vibration → inspection','category':'STRUCTURAL VIBRATION','color':'#9caec5','sources':[Source('piezo-1','piezo',(-2.5,0,0),2)],'distance_m':38.,'description':'A rectified piezoelectric source responds to a synthetic vibration envelope.'},
 'thermal-pipeline':{'title':'Thermal process line','subtitle':'Heat gradient → process diagnostics','category':'THERMAL GRADIENT','color':'#d2ab8b','sources':[Source('teg-1','thermal',(-2.7,0,0),1,3.2,.72)],'distance_m':18.,'description':'A fixed-ratio converter couples a thermoelectric element to the storage bus.'},
 'hybrid-station':{'title':'Hybrid micro-station','subtitle':'Light + motion + vibration → resilient sensing','category':'MULTI-SOURCE DEPLOYMENT','color':'#b4d792','sources':[Source('pv-1','solar',(-3,0,-1.5),.4),Source('rotary-1','rotary',(-3,0,1.6)),Source('piezo-1','piezo',(-.7,0,2.1))],'distance_m':30.,'description':'Three converter-isolated harvesting branches share one capacitor and an executed node workload.'}}

def scene_manifest(scene:str)->dict:
    if scene not in SCENES:raise ValueError('unknown deployment scene')
    obj=SCENES[scene]
    return {'id':scene,**{k:v for k,v in obj.items() if k!='sources'},'sources':[asdict(s) for s in obj['sources']],
      'geometry':'illustrative parametric deployment, not CAD; schematic and actual receiver distance distinguished',
      'environment_source':'synthetic deterministic conditions','hardware_confirmed':False}
