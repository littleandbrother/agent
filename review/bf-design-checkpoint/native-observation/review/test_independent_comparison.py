"""Synthetic report-integrity tests only. No simulation or physical evidence."""
import unittest,sys,json,copy,os
from pathlib import Path
KIT_ROOT=Path(os.environ.get('NATIVE_OBSERVATION_KIT_ROOT',str(Path(__file__).resolve().parents[1]/'native-observation-kit-v1-20261001')))
sys.path.insert(0,str(KIT_ROOT/'src'))
from compare_refinement import compare,compare_events
from retained_raw import EvidenceError
PLAN=json.loads((KIT_ROOT/'EXACT-PLAN.json').read_text())

def event():return {'direction':'rising','time_bracket_s':[.299999,.3],'signal_bracket':[0,3.3],'analysis_level':1.65,'vin_V_bracket':[5.05,5.06],'vout_V_bracket':[3.31,3.312]}
def report(resolution):
 ledger_keys=['drive_delivered_J','control_delivered_J','source_resistor_loss_J','switch_loss_J','load_loss_J','l_esr_loss_J','l_rpar_loss_J','cout_esr_loss_J','zero_sensor_absorption_J','macro_absorption_J','initial_external_stored_J','final_external_stored_J','max_abs_external_residual_J']
 return {'schema_version':'native-observation-retained-metrics-v1','case_id':'driven-down-'+resolution,'numerical_checks':[{'name':'SYNTHETIC_SCHEMA_FIXTURE_ONLY','max_abs_residual':0.0,'tolerance':1e-9,'passed':True}],'all_numerical_checks_passed':True,'initial_state':{'zero_screen_passed':True},'energy_ledger':dict.fromkeys(ledger_keys,0.0),'PGOOD':{'status':'OBSERVED_SIGNAL_BRACKETS','events':[event()]},'VIN_reference_crossings':{'5.05':[],'3.67':[]},'switch_control_crossings':[],'pre_uvlo_observation':{'rails':{k:{'voltage_start_V':0.0,'voltage_end_V':1.0,'delta_charge_C':1e-6,'delta_energy_J':1e-6} for k in ('Ccap','Cvin2')}}}

class ComparisonReview(unittest.TestCase):
 def not_pass(self,fn):
  try:r=fn()
  except (EvidenceError,ValueError,KeyError):return
  self.assertFalse(r.get('passed',r.get('all_resolved_numerical_gates_passed',True)))
 def test_complete_matching_synthetic_reports_pass(self):self.assertTrue(compare(report('coarse'),report('fine'),PLAN)['all_resolved_numerical_gates_passed'])
 def test_equal_brackets_pass(self):self.assertTrue(compare_events([event()],[event()],PLAN['analysis'],'PGOOD')['passed'])
 def test_missing_voltage_bracket_never_passes(self):
  a,b=event(),event();del b['vout_V_bracket'];self.not_pass(lambda:compare_events([a],[b],PLAN['analysis'],'PGOOD'))
 def test_missing_voltage_fields_in_both_never_passes(self):
  a=event();del a['vout_V_bracket'];self.not_pass(lambda:compare_events([a],[copy.deepcopy(a)],PLAN['analysis'],'PGOOD'))
 def test_unresolved_references_never_pass(self):self.not_pass(lambda:compare_events(None,None,PLAN['analysis'],'PGOOD'))
 def test_zero_screen_false_never_passes(self):
  a,b=report('coarse'),report('fine');b['initial_state']['zero_screen_passed']=False;self.not_pass(lambda:compare(a,b,PLAN))
 def test_zero_screen_string_never_passes(self):
  a,b=report('coarse'),report('fine');b['initial_state']['zero_screen_passed']='false';self.not_pass(lambda:compare(a,b,PLAN))
 def test_numerical_flag_string_never_passes(self):
  a,b=report('coarse'),report('fine');b['all_numerical_checks_passed']='false';self.not_pass(lambda:compare(a,b,PLAN))
 def test_missing_VIN_reference_keys_never_passes(self):
  a,b=report('coarse'),report('fine');a['VIN_reference_crossings']={};b['VIN_reference_crossings']={};self.not_pass(lambda:compare(a,b,PLAN))
 def test_nan_energy_never_passes(self):
  a,b=report('coarse'),report('fine');a['energy_ledger']['drive_delivered_J']=float('nan');self.not_pass(lambda:compare(a,b,PLAN))
 def test_event_order_mismatch_never_passes(self):
  a,b=event(),event();b['direction']='falling';self.not_pass(lambda:compare_events([a],[b],PLAN['analysis'],'PGOOD'))

if __name__=='__main__':unittest.main(verbosity=2)
