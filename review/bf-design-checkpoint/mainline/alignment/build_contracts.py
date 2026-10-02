import sys,json,pathlib,copy
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'src'))
import adapters as a
from contract import AXES

def obj(required,properties):return {'type':'object','required':required,'properties':properties,'additionalProperties':False}
num={'type':'number'};nullable={'type':['number','null']};string={'type':'string'};boo={'type':'boolean'};positive={'type':'number','exclusiveMinimum':0};nonnegative={'type':'number','minimum':0};vec={'type':'array','items':num,'minItems':3,'maxItems':3}
props={
 'contract_id':string,'schema_version':{'const':'simulation-semantic-contract-v1'},'scope':{'enum':['source-defaults','synthetic-matched-fixture']},
 'geometry':obj(['tip_magnet_m','driver_magnet_m','gap_m','gap_actuation','rom_limit_m','beam_source'],{'tip_magnet_m':vec,'driver_magnet_m':vec,'gap_m':positive,'gap_actuation':string,'rom_limit_m':positive,'beam_source':string}),
 'force':obj(['model','remanence_T','recoil_permeability','quadrature_order'],{'model':string,'remanence_T':positive,'recoil_permeability':positive,'quadrature_order':{'type':'integer','minimum':1}}),
 'initial_energy':obj(['mechanical_J','piezo_V','vin_V','vout_V','auxiliary_J','mechanical_state_rule'],{'mechanical_J':nullable,'piezo_V':num,'vin_V':num,'vout_V':num,'auxiliary_J':nullable,'mechanical_state_rule':string}),
 'source_trajectory':obj(['opening_s','angle_rad','duration_s','coordinate_rule','electrical_input'],{'opening_s':nonnegative,'angle_rad':nonnegative,'duration_s':positive,'coordinate_rule':string,'electrical_input':string}),
 'circuit':obj(['model','cin_F','cout_F','cp_rule','energy_boundary','load_taper_voltage_V'],{'model':string,'cin_F':positive,'cout_F':positive,'cp_rule':string,'energy_boundary':string,'load_taper_voltage_V':positive}),
 'firmware':obj(['policy','brownout_V','startup_V','pgood_low_inflight','parameters'],{'policy':string,'brownout_V':positive,'startup_V':positive,'pgood_low_inflight':string,'parameters':{'type':'object'}}),
 'packet':obj(['protocol','bytes','device_id_hex','sequence','byte_order'],{'protocol':{'const':'BFD2'},'bytes':{'const':12},'device_id_hex':{'type':'string','pattern':'^[0-9a-f]{16}$'},'sequence':{'const':False},'byte_order':string}),
 'receiver':obj(['silence_s','loss_probability','scan_duty','scan_period_s','seed','capture_dedup','direction'],{'silence_s':positive,'loss_probability':{'type':'number','minimum':0,'maximum':1},'scan_duty':{'type':'number','minimum':0,'maximum':1},'scan_period_s':nullable,'seed':{'type':['integer','null']},'capture_dedup':boo,'direction':{'const':'unknown'}}),
 'mission':obj(['duration_s','deadline_s','minimum_groups','cold_start_gate','diagnostic_excluded'],{'duration_s':positive,'deadline_s':positive,'minimum_groups':{'type':'integer','minimum':1},'cold_start_gate':string,'diagnostic_excluded':boo}),
 'units':{'const':{'length':'m','angle':'rad','time':'s','voltage':'V','current':'A','energy':'J','force':'N','capacitance':'F','firmware_input_conversion':'upstream dt milliseconds, current milliamps; adapters convert explicitly'}},
 'version':obj(['model','source_bound','native_evidence_available','physics_hash','numerical_semantics'],{'model':string,'source_bound':boo,'native_evidence_available':boo,'physics_hash':{'type':'string','pattern':'^[0-9a-f]{64}$'},'numerical_semantics':string})}
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:bf:simulation-semantic-contract:v1',**obj(list(props),props)}
a.write(ROOT/'contracts/semantic-contract.schema.json',schema)
sources={name:{'path':str(path),'sha256':a.sha(path),'bytes':path.stat().st_size} for name,path in a.source_paths().items()}
a.write(ROOT/'contracts/source-lock.json',{'upstream_commit':'338d60384d5805abf1e02252a4513860066a2c39','sources':sources,'authority':'pinned source + preserved cloud input; no native receipt inferred'})
base={'schema_version':'simulation-semantic-contract-v1','scope':'source-defaults',
 'geometry':{'tip_magnet_m':[.01]*3,'driver_magnet_m':[.02]*3,'gap_m':.048,'gap_actuation':'move rotating driver at fixed stationary tip','rom_limit_m':.008,'beam_source':'fresh native extraction; rom.json absent'},
 'force':{'model':'finite-uniform-cuboid-surface-charge-mur1','remanence_T':1.25,'recoil_permeability':1.,'quadrature_order':6},
 'initial_energy':{'mechanical_J':None,'piezo_V':0.,'vin_V':0.,'vout_V':0.,'auxiliary_J':None,'mechanical_state_rule':'k*q0 = interpolated F(angle=0,q0); qdot=0; equilibrium preload energy counted'},
 'source_trajectory':{'opening_s':2.,'angle_rad':float(a.np.deg2rad(65)),'duration_s':4.,'coordinate_rule':'fixed tip at x=.904; driver x=(.904-gap)*cos(a)-.045*sin(a), z=(.904-gap)*sin(a)+.045*cos(a)-.075265','electrical_input':'none at baseline; configurable continuous diagnostic current into Vin'},
 'circuit':{'model':'native-LTC3588-1-encrypted-macro','cin_F':47e-6,'cout_F':100e-6,'cp_rule':'blocked capacitance counted exactly once; reciprocal theta signs','energy_boundary':'mechanical+piezo+PMIC input port; encrypted internal losses unqualified','load_taper_voltage_V':1.8},
 'firmware':{'policy':'shared-C-RESET-BOOT-WAIT-INIT-TX-SLEEP','brownout_V':1.8,'startup_V':1.8,'pgood_low_inflight':'abort INIT/TX/SLEEP to WAIT if PGOOD<2.5V','parameters':a.upstream_contracts.DEFAULT['firmware']},
 'packet':{'protocol':'BFD2','bytes':12,'device_id_hex':'0102030405060708','sequence':False,'byte_order':'raw bytes in C; cloud can match with two little-endian uint32 IDs'},
 'receiver':{'silence_s':.35,'loss_probability':0.,'scan_duty':1.,'scan_period_s':.1,'seed':17,'capture_dedup':True,'direction':'unknown'},
 'mission':{'duration_s':4.,'deadline_s':4.,'minimum_groups':1,'cold_start_gate':'max(Vout)>=3.2V and >=1 receiver group; result still insufficient_evidence','diagnostic_excluded':True},
 'units':props['units']['const']}
u=copy.deepcopy(base);u['contract_id']='upstream-338d603-default-v1';u['version']={'model':a.upstream_contracts.VERSION,'source_bound':True,'native_evidence_available':False,'physics_hash':a.digest({k:v for k,v in sources.items() if k.startswith('upstream_')}),'numerical_semantics':'LTspice waveform fixed point; maxstep 50us; firmware bin minimum 100us; reltol1e-4'}
c=copy.deepcopy(base);c['contract_id']='cloud-behavioral-default-v1';c['geometry'].update(gap_actuation='move stationary product; rotating driver x=.856m fixed',beam_source='inherited COMSOL-derived constants; not newly recomputed')
c['source_trajectory'].update(coordinate_rule='stationary tip x=.856+gap; driver x=.856*cos(a)-.045*sin(a), z=.856*sin(a)+.045*cos(a)-.075265',electrical_input='none at baseline; controlled input replaces door with F=0, Vin source 6V/20ohm for .3s')
c['initial_energy']['auxiliary_J']=0.
c['circuit'].update(model=a.cloud_power.VERSION,energy_boundary='full declared behavioral stores and assumed losses; not encrypted PMIC internals',load_taper_voltage_V=.1)
c['firmware']={'policy':'Python-off-reset-clock-boot-init-read-payload-tx-sleep + common C gate/encoding','brownout_V':1.7,'startup_V':1.8,'pgood_low_inflight':'finish current TX; gate at boot exit or sleep','parameters':a.cloud_firmware.DEFAULTS}
c['packet']['device_id_hex']='78563412efcdab90';c['receiver'].update(scan_period_s=None,seed=None)
c['mission']['cold_start_gate']='receiver stage counts completed timely packets grouped by silence; separate source cold-start mission contract'
c['version']={'model':a.cloud_power.VERSION,'source_bound':True,'native_evidence_available':False,'physics_hash':a.digest({k:v for k,v in sources.items() if k.startswith('cloud_')}),'numerical_semantics':'Radau2e-8/1e-13; accepted macro/event ticks; PMIC latches at macro boundaries'}
e=copy.deepcopy(c);e['contract_id']='cloud-event-v2-experimental';e['version']={'model':'reciprocal-behavioral-power-v1.3.1-experimental-terminal-events-tight','source_bound':True,'native_evidence_available':False,'physics_hash':a.digest(sources['event_v2']),'numerical_semantics':'directional terminal UVLO/aux/PGOOD roots; Radau2e-10/1e-14; firmware remains sampled; finite tested scope only'}
for name,contract in [('upstream-default',u),('cloud-default',c),('event-v2',e)]:a.write(ROOT/'contracts'/f'{name}.json',contract)
a.write(ROOT/'fixtures/predeclared-tests.json',{'schema_version':'alignment-test-plan-v1','scope':'portable source semantics, common host-C and matched synthetic analytic tests only','source_lock_sha256':a.sha(ROOT/'contracts/source-lock.json'),'defaults_never_rewritten':True,'fixture_parameters':{'force_direct_gaps_mm':[48], 'trajectory_gaps_mm':[40,48,60], 'angles_deg':[0,5,30,65],'displacements_m':[-.004,0,.004],'waveform_step_s':.0001,'waveform_duration_s':.4,'inflight_perturbation_delay_s':.0004,'analytic_duration_s':.004,'analytic_dt_s':.0005,'analytic_Cin_F':1e-7,'analytic_source_V':6.,'analytic_source_R_ohm':10000.,'analytic_startup_current_A':.001},'gates':{'force_direct_abs_N':1e-12,'geometry_nominal_abs_m':1e-14,'analytic_event_time_abs_s':2e-9,'analytic_final_v_abs_V':2e-7,'passive_energy_relative':1e-7},'forbidden_claims':['native vendor execution','hardware calibration','matched closed-loop mission','formal Agent superiority','event-v2 promotion']})
print('Bound',len(sources),'inputs; created three explicit semantic contracts')
