import csv
import tempfile
import unittest
from pathlib import Path
from bfworld.agentlab.design_lab import finite_cases as f,method_study as m,physical
from bfworld.agentlab.store import identity


class MethodProtocolTests(unittest.TestCase):
    def test_stale_disconnect_does_not_cancel_new_request(self):
        seq=[(1,7,0),(3,7,2),(1,8,0),(3,8,2),(2,7,0),(5,8,2),(5,8,2)]
        self.assertEqual(m.expected(seq)[-3:],[ [1,8,2,0],[0,8,0,1],[0,8,0,1]])

    def test_zero_is_connected_identity_not_sentinel(self):
        self.assertEqual(m.expected([(1,0,0),(3,0,0),(5,0,0)])[-1],[0,0,0,1])

    def test_all_pass_no_gain_candidate_rejected(self):
        pairs=[{'parent':{'passed':True,'cost_usd':.1},'child':{'passed':True,'cost_usd':.1}}]
        self.assertFalse(m.decision(pairs,.01)['adopted'])

    def test_correctness_regression_overrides_cheaper_cost(self):
        pairs=[{'parent':{'passed':True,'cost_usd':1},'child':{'passed':False,'cost_usd':.001}}]
        self.assertFalse(m.decision(pairs,0)['adopted'])

    def test_acquisition_cost_counted(self):
        pairs=[{'parent':{'passed':True,'cost_usd':1},'child':{'passed':True,'cost_usd':.6}}]
        self.assertFalse(m.decision(pairs,.3)['adopted'])

    def test_candidate_cannot_rewrite_evaluator(self):
        body={'instruction':'x'*100,'hypothesis':'h','falsifier':'f','applicability':'a',
              'negative_scope':'n','evidence_episodes':['ep'],'threshold':0}
        with self.assertRaisesRegex(ValueError,'FIELDS'):m.candidate(body,'H0',['ep'])

    def test_candidate_cannot_use_unseen_episode(self):
        body={'instruction':'x'*100,'hypothesis':'h','falsifier':'f','applicability':'a',
              'negative_scope':'n','evidence_episodes':['hidden']}
        with self.assertRaisesRegex(ValueError,'EPISODE'):m.candidate(body,'H0',['ep'])


class PhysicalBoundaryTests(unittest.TestCase):
    def test_participant_measured_claim_does_not_admit_capture(self):
        with self.assertRaisesRegex(ValueError,'EXTERNALLY_APPROVED'):
            physical.inspect_capture('/no/file',{'origin':'instrument-measurement','acquisition_id':'fake'}, {})

    def test_simulation_not_hardware(self):
        with self.assertRaisesRegex(ValueError,'ORIGIN'):
            physical.inspect_capture('/no/file',{'origin':'simulation'}, {})

    def test_raw_units_are_checked_before_result(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'raw.csv';p.write_text(','.join(physical.CHANNELS)+'\n0,0,0,0,1,0\n1,1,1,0,1,1\n')
            md={'origin':'instrument-measurement','acquisition_id':'a','instrument_id':'i',
                'calibration_receipt':'r','design_id':'D','units':dict(zip(physical.CHANNELS,['s','V','V','mA','uint32','uint32']))}
            approved={'a':{'metadata_sha256':identity(md),'raw_sha256':physical.sha(p)}}
            with self.assertRaisesRegex(ValueError,'UNIT_MISMATCH'):physical.inspect_capture(p,md,approved)


class RealCompiledFeedbackTests(unittest.TestCase):
    def test_unrelated_numeric_pass_cannot_certify_this_execution(self):
        with tempfile.TemporaryDirectory() as d:
            env=f.manifest('B');source=f.reference_source('B');root=Path(d)/'build'
            b=f.build(env,source,root);x=f.execute(env,source,b,root)
            c=f.evaluate(env,b,x,native={'passed':True,'execution_id':'another-run','trace_sha256':'0'*64})
            self.assertEqual(c['gates']['numerical_balance'],'UNEVALUABLE')
            self.assertNotEqual(c['scoped_status'],'PASS')

    def test_host_only_file_writer_is_rejected_even_when_arm_has_no_io(self):
        with tempfile.TemporaryDirectory() as d:
            env=f.manifest('B');source=f.reference_source('B')
            source['program.c']='''#ifdef __APPLE__
#include <stdio.h>
void host_writer(void){FILE *p=fopen("forged.csv","w");fputs("fake",p);fclose(p);}
#endif
'''+source['program.c']
            with self.assertRaisesRegex(ValueError,'HOST_EXTERNAL_DENIED'):
                f.build(env,source,Path(d)/'build')

    def test_labels_must_follow_samples_after_independent_permutation(self):
        with tempfile.TemporaryDirectory() as d:
            env=f.manifest('A');source=f.reference_source('A');root=Path(d)/'build'
            b=f.build(env,source,root)
            normal=f.execute(env,source,b,root)
            shifted=f.execute(env,source,b,root,truth_shift=1,stem='shifted')
            self.assertEqual([v['class'] for v in normal['tx']],[0,1,0,1])
            self.assertEqual([v['class'] for v in shifted['tx']],[1,0,1,0])
            self.assertIn('sample_port?sample:0.',f.RUNNER)
            self.assertNotIn('step(dt,V,req,truth',f.RUNNER)

    def test_program_cannot_make_a_stage_cost_free(self):
        with tempfile.TemporaryDirectory() as d:
            env=f.manifest('B');source=f.reference_source('B')
            source['program.c']=source['program.c'].replace('return state==1?.00041:state==2?.001596:state==3?.003659:.0000003;','return 0;')
            root=Path(d)/'build';b=f.build(env,source,root)
            with self.assertRaises(Exception):f.execute(env,source,b,root)

    def test_program_changes_load_and_window_and_source_changes_execution(self):
        with tempfile.TemporaryDirectory() as d:
            env=f.manifest('B');source=f.reference_source('B');root=Path(d)/'normal'
            b=f.build(env,source,root);x=f.execute(env,source,b,root)
            self.assertEqual(len(x['tx']),1)
            dead=f.execute(env,source,b,root,source_scale=0,stem='no-source')
            self.assertEqual(dead['tx'],[])
            changed=f.reference_source('B',tx_s=1.);root2=Path(d)/'changed'
            b2=f.build(env,changed,root2);x2=f.execute(env,changed,b2,root2)
            self.assertNotEqual(x['integrated_load_J'],x2['integrated_load_J'])
            self.assertEqual(x2['tx'],[])
            self.assertGreater(x2['resets'],0)

    def test_changed_source_cannot_consume_old_binary(self):
        with tempfile.TemporaryDirectory() as d:
            env=f.manifest('B');source=f.reference_source('B');root=Path(d)/'build'
            b=f.build(env,source,root)
            with self.assertRaisesRegex(ValueError,'BINDING'):
                f.execute(env,f.reference_source('B',wrong_id=True),b,root)

    def test_source_domain_rejects_extra_energy(self):
        with tempfile.TemporaryDirectory() as d:
            env=f.manifest('B');source=f.reference_source('B');root=Path(d)/'build';b=f.build(env,source,root)
            with self.assertRaisesRegex(ValueError,'DOMAIN'):f.execute(env,source,b,root,source_scale=2)
