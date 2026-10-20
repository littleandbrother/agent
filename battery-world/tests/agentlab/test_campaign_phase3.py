"""Changed phase3 integration only; no provider calls or new simulations."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import binascii
import struct
from types import SimpleNamespace
import zlib
import unittest

from bfworld.agentlab.campaign20261019.phase3 import ComparisonStore,ProspectiveHost,qualify,ordered_state
from bfworld.agentlab.campaign20261019.phase3_interfaces import decode_packet

APP=Path(__file__).resolve().parents[2]
ROOT=APP.parents[2]
OUT=Path.home()/'.local/share/bf-phase3-20261020'
HIST=Path.home()/'.local/share/bf-agent-architecture-v2/parallel-campaign-20261019/a/reference-run-001'
spec=importlib.util.spec_from_file_location('phase3_test_runner',APP/'scripts/campaign_phase3.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
adapter=runner.load_module('phase3_test_adapter',ROOT/'docs/research/phase-plan-20261019/phase2/dispatch_adapter_v2.py')


class Phase3IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='bf-p3-tests-')
        self.root=Path(self.temp.name)
        self.store=ComparisonStore(APP,self.root,HIST,OUT/'initial-cache.json','one')

    def tearDown(self):
        self.temp.cleanup()

    def host(self,condition='complete-raw',kind='D',world='b-volatile-reset'):
        tool=runner.definition(kind,adapter,self.store.legal(world))
        return ProspectiveHost(self.root/condition,self.store,world,kind,adapter,condition=condition,tool=tool)

    def test_e4_real_host_packets_preserve_facts_and_permissions(self):
        left=self.host('rich-static').inspect();right=self.host('e4-rich-static-table').inspect()
        self.assertEqual(decode_packet(left['serialized_information'],'json'),decode_packet(right['serialized_information'],'table'))
        self.assertIn('model_law',decode_packet(left['serialized_information'],'json')['facts'])

    def test_average_projection_cannot_acquire_full_activity_but_e5_can(self):
        coarse=self.host('average-energy')({'action':'acquire','source_id':'saved_activity'})
        self.assertNotIn('activity',coarse['payload'])
        refined=self.host('live-e5','E5')({'action':'acquire','source_id':'saved_activity'})
        self.assertIn('activity',refined['payload'])

    def test_shared_physics_does_not_share_group_exposure_budget(self):
        d={'capacitance_f':10e-6,'tx_not_before_s':.045}
        first=self.store.execute('b-volatile-reset',d)
        self.store.execute('b-volatile-reset',{'capacitance_f':15e-6,'tx_not_before_s':.045})
        with self.assertRaisesRegex(ValueError,'SHARED_GROUP_TWO_D_LIMIT'):
            self.store.execute('b-volatile-reset',{'capacitance_f':22e-6,'tx_not_before_s':.045})
        other=ComparisonStore(APP,self.root,HIST,OUT/'initial-cache.json','two')
        second=other.execute('b-volatile-reset',d)
        self.assertTrue(first['job_accounting']['new_logical_D_evaluation'])
        self.assertTrue(second['job_accounting']['new_logical_D_evaluation'])
        self.assertTrue(second['job_accounting']['physical_exact_input_reused'])
        self.assertEqual(len(json.loads(other.job.read_text())['executed']),1)

    def test_h_host_excludes_D_without_consuming_H_and_allows_no_update(self):
        h=self.host('proposed_method','H')
        with self.assertRaisesRegex(ValueError,'V2_ACTION_TYPE_OR_SYNTAX_REJECTED'):
            h({'action':'check','candidate':{'capacitance_f':10e-6,'tx_not_before_s':0}})
        self.assertEqual(len(h.counter.used),0)
        self.assertEqual(h({'action':'submit','proposal':{'decision':'no-update','reason':'No supported procedural improvement'}})['method_decision'],'no-update')

    def test_source_binding_and_independent_units(self):
        source=self.store.source('component_record','b-volatile-reset')
        s={'hypothesis':'Read source voltage under the declared exact-source domain','mode':'selection','source_id':'component_record','field':'/ready_v','units':'V','domain':{'constraints':[]}}
        observed,qualified=qualify(s,source)
        self.assertEqual(observed['value'],2.8);self.assertTrue(qualified['prospective'])
        changed=copy.deepcopy(source);changed['payload']['ready_v']=3
        with self.assertRaisesRegex(ValueError,'SOURCE_PAYLOAD_BINDING_FAILED'):qualify(s,changed)

    def test_postdelivery_reset_is_not_pending_retention(self):
        task=self.store.task('b-volatile-reset')
        raw={'packets':[{'time_s':.0056,'event_id':1,'application_bytes':8}],
             'activity':[{'time_s':.003,'action':'capture','event_id':1},{'time_s':.0121,'action':'brownout','event_was_captured':False}]}
        reference={'verdicts':{'event_receive':'PASS','event_preserved_after_reset':'PASS'}}
        state=ordered_state(task,raw,reference)
        self.assertEqual(state['classification'],'DELIVERED_BEFORE_ANY_RESET')
        self.assertFalse(state['pending_event_retained_across_reset'])
        self.assertEqual(len(state['resets_after_delivery_before_deadline']),1)

    def test_derived_query_gate_overrides_misleading_legacy_receiver_pass(self):
        # Injected software frames, not physical simulation or experiment data.
        # In particular the old receiver's event+deadline=9 must not admit RX8
        # when this new contract has the absolute reply deadline 7.
        spec=json.loads((APP/'configs/studies/phase3-20261020/interfaces/derived-case.json').read_text())
        task=spec['bf_engine_input'];checker=self.store.base.checker
        rule=json.loads((APP/'configs/studies/phase3-20261020/shared/tasks.json').read_text())['tasks'][spec['id']]['query_protocol']
        for name,seq,rx,expected in [('valid',1,2.5,'PASS'),('wrong-query',2,2.5,'FAIL'),('late',1,8,'FAIL')]:
            body=struct.pack('>HHBBH',task['device']['id'],seq,1,1,0xB026)
            frame=body+binascii.crc_hqx(body,0xFFFF).to_bytes(2,'big')
            raw={'activity':[{'action':'capture','event_id':1,'time_s':2}],
                 'packets':[{'hex':frame.hex(),'event_id':1,'application_bytes':8,'time_s':rx}]}
            path=self.root/(name+'.json.zlib');path.write_bytes(zlib.compress(json.dumps(raw).encode()))
            result={'raw_path':str(path),'reference':{'verdicts':{'event_receive':'PASS','event_preserved_after_reset':'FAIL'}},
                    'execution_key':'injected-'+name,'design':spec['initial_design'],'complete_service':'PASS','reused':False}
            self.store.base=SimpleNamespace(task=lambda _:task,legal=lambda _:{'capacitance_f':(25e-6,100e-6),'tx_not_before_s':(2,7)},
                execute=lambda *_,r=result:copy.deepcopy(r),checker=checker,task_registry={'tasks':{spec['id']:{'query_protocol':rule}}})
            value=self.store.execute(spec['id'],spec['initial_design'])
            self.assertEqual(value['query_service']['status'],expected,name)
            self.assertEqual(value['complete_service'],expected,name)


if __name__=='__main__':unittest.main()
