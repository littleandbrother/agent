"""D5 adds physical extraction/gating choices; D4 task/model remain sealed."""
import copy
import hashlib
from pathlib import Path
from ..door_system import contracts as d4

SCHEMA='bf-door-selfpower-design-v1'
SCHEMA_V2='bf-door-selfpower-design-v2'
SCHEMA_V3='bf-door-selfpower-design-v3'
SCHEMAS=(SCHEMA,SCHEMA_V2,SCHEMA_V3)
LOAD_SWITCHES=('BSS84','Si2333CDS')
SI2333_MODEL_HASH='229e45a704ecd62bb40ab5fc6ea81f071dcfa9a77755572146c5c632dfd6f0c6'
SI2333_DATASHEET_HASH='c3117561a13cb50bc56ddcf9b4439611d42edb55e1640363ff65407362974b20'
SCOPE=('D5 self-powered extraction and supply-qualified reserve gate, fixed D4 beam/task/load; '
       'native nominal-model simulation + shared C SIL + virtual receive. No hardware, RF, '
       'fabrication release, exact paper reproduction or autonomous-method claim.')
GATES={'off':None, 'reserve-5v5':{'high_V':5.5,'low_V':4.3},
       'reserve-5v5-3v0':{'high_V':5.5,'low_V':3.}, 'reserve-6v5':{'high_V':6.5,'low_V':4.3},
       'reserve-e96-6v1':{'high_V':1.24*2.978e6/604e3,'low_V':1.24*2.978e6/1.238e6,
                          'divider_ohm':(1.74e6,634e3,604e3)},
       'reserve-e96-6v3':{'high_V':1.24*2.989e6/590e3,'low_V':1.24*2.989e6/1.209e6,
                          'divider_ohm':(1.78e6,619e3,590e3)},
       'reserve-e96-6v3-2v96':{'high_V':1.24*2.995e6/590e3,'low_V':1.24*2.995e6/1.255e6,
                               'divider_ohm':(1.74e6,665e3,590e3)},
       'reserve-e96-5v43-2v98':{'high_V':1.24*2.983e6/681e3,'low_V':1.24*2.983e6/1.243e6,
                               'divider_ohm':(1.74e6,562e3,681e3)},
       'reserve-e96-5v16-2v98':{'high_V':1.24*2.978e6/715e3,'low_V':1.24*2.978e6/1.238e6,
                               'divider_ohm':(1.74e6,523e3,715e3)},
       'reserve-8v0':{'high_V':8.,'low_V':4.3}}
ENVELOPES=(68.,100.,220.,470.,680.,1000.,3000.)
BASE={'mechanical':{'gap_mm':48.,'closed_dz_mm':0.,'polarity':-1},
      'circuit':{'cin_uF':10.,'cout_uF':10.},'firmware':{'interval_ms':100.}}
PARTS={'coil':{'mpn':'7447471471','L_H':470e-6,'dcr_ohm_max':1.2,'Isat10_A_typ':.98,
               'rated_rms_A':.68,'operating_V':120.,'diameter_mm':11.5,'height_mm':11.},
       'detector':'MMBT5551','extractor':'2N5401',
       'monitor':'MIC841L powered push-pull behavioral model; 1.5uA typ, high output below low threshold',
       'load_switch':'BSS84 installed model','divider_total_ohm':3e6,
       'gate_pullup_ohm':None,
       'gate_output':'Supply-powered complementary push-pull; no open-drain pull-up resistor'}


def normalize(candidate=None):
    c={} if candidate is None else candidate
    if not isinstance(c,dict) or set(c)-{'mechanical','circuit','firmware','extraction','gate','application','gate_switch'}:
        raise ValueError('SELFPOWER_FROZEN_CONDITION_OR_UNKNOWN_FIELD')
    base=copy.deepcopy(BASE)
    for k in base:
        if k in c:
            if not isinstance(c[k],dict):raise ValueError('SELFPOWER_SECTION_OBJECT_REQUIRED')
            base[k].update(c[k])
    original=d4.normalize(base)
    e={'topology':'sece','envelope_pF':1000.,'diodes':'BAT46WJ'}
    if 'extraction' in c:
        if not isinstance(c['extraction'],dict) or set(c['extraction'])-set(e):
            raise ValueError('SELFPOWER_EXTRACTION_INVALID')
        e.update(c['extraction'])
    if e['topology'] not in ('direct','seh','psshi','sece'):
        raise ValueError('SELFPOWER_TOPOLOGY_INVALID')
    if isinstance(e['envelope_pF'],bool) or e['envelope_pF'] not in ENVELOPES:
        raise ValueError('SELFPOWER_ENVELOPE_PART_INVALID')
    if e['diodes'] not in ('BAT46WJ','BAS21HY','BAT46WJ-3P'):raise ValueError('SELFPOWER_DIODE_PART_INVALID')
    if e['diodes']=='BAT46WJ-3P' and e['topology']!='sece':
        raise ValueError('SELFPOWER_PARALLEL_BANK_REQUIRES_SECE')
    app={'packet_policy':'one-shot'}
    if 'application' in c:
        if not isinstance(c['application'],dict) or set(c['application'])-set(app):raise ValueError('SELFPOWER_APPLICATION_INVALID')
        app.update(c['application'])
    if app['packet_policy'] not in ('one-shot','beacon'):raise ValueError('SELFPOWER_PACKET_POLICY_INVALID')
    gate=c.get('gate','reserve-5v5-3v0')
    if not isinstance(gate,str) or gate not in GATES:raise ValueError('SELFPOWER_GATE_INVALID')
    switch=c.get('gate_switch','BSS84')
    if not isinstance(switch,str) or switch not in LOAD_SWITCHES:raise ValueError('SELFPOWER_LOAD_SWITCH_INVALID')
    v={'schema_version':SCHEMA,'revision':'D5','base_design':original,'extraction':e,
       'gate':gate,'application':app,'parts':copy.deepcopy(PARTS),'scope':SCOPE}
    # Preserve every existing v1/BSS84 identity. A sourced component change is
    # a prospective v2 design, never a reinterpretation of old native results.
    if switch!='BSS84':
        v.update(schema_version=SCHEMA_V2,gate_switch=switch)
        v['parts']['load_switch']='Si2333CDS original Vishay subcircuit'
        v['parts']['load_switch_model']={'mpn':switch,'sha256':SI2333_MODEL_HASH,
            'datasheet_sha256':SI2333_DATASHEET_HASH,'Vds_limit_V':12.,'Vgs_limit_V':8.,
            'Rds_on_max_ohm_at_Vgs_minus1v8':.059,'package':'SOT-23','pins':{'1':'G','2':'S','3':'D'}}
    if e['diodes']=='BAT46WJ-3P':
        v['schema_version']=SCHEMA_V3
        v['parts']['diode_bank']={'mpn':'BAT46WJ','parallel_per_power_position':3,
          'power_positions':['Dbr1','Dbr2','Dbr3','Dbr4','Dblock','Dtransfer'],
          'single_positions':['Denv','Dbase'],'ballast_ohm_each':.22,'diode_count':20,
          'scope':'Real separate branches, identical nominal model; mismatch/PCB/thermal qualification pending.'}
    v['parts']['diodes']=e['diodes']
    if GATES[gate] is not None:
        v['parts']['gate_thresholds_V']={k:GATES[gate][k] for k in ('high_V','low_V')}
        if 'divider_ohm' in GATES[gate]:
            v['parts']['divider_ohm']=list(GATES[gate]['divider_ohm'])
            v['parts']['divider_total_ohm']=sum(v['parts']['divider_ohm'])
    v['design_id']=d4.digest(v)
    return v


def verify_design(value):
    if not isinstance(value,dict):raise ValueError('SELFPOWER_DESIGN_REQUIRED')
    base=value.get('base_design',{})
    if not isinstance(base,dict) or set(BASE)-set(base):raise ValueError('SELFPOWER_BASE_DESIGN_REQUIRED')
    expected=normalize({**{k:base.get(k) for k in BASE},
                        'extraction':value.get('extraction'), 'gate':value.get('gate'),
                        'application':value.get('application'),
                        'gate_switch':value.get('gate_switch','BSS84')})
    if value != expected:raise ValueError('SELFPOWER_IDENTITY_OR_FROZEN_DRIFT')
    return expected


def template_hash():
    h=hashlib.sha256();here=Path(__file__).parent
    paths=sorted(here.glob('*.py'))+sorted(here.glob('*.c'))+sorted((here.parent/'door_system').glob('*.py'))
    paths += [here.parent/'simulation_chain'/n for n in ('contracts.py','native.py','program.c')]
    for p in paths:
        h.update(str(p.relative_to(here.parent)).encode());h.update(p.read_bytes())
    return h.hexdigest()
