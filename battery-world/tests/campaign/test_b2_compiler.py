import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from bfworld.kernel.canonical import canonical_hash
from bfworld.campaign.compiler import compile_candidate, context_errors, static_errors
from bfworld.campaign.repair import run_repair
from bfworld.campaign.qualification import qualify_world, qualify_workflow, activated_components, receipt

CTX = {'source_family':'rotary','conditions':{'initial_v':2.6,'off_v':1.8,'duration_s':1.6},
       'candidates':[{'id':'a','capacitance_f':.0022,'esr_ohm':4.,'tx_power_w':.036,'start_v':2.35}]}
CODE = '''def plan(ctx):
    if not isinstance(ctx, dict) or ctx.get('source_family') != 'rotary' or not isinstance(ctx.get('conditions'), dict) or not ctx.get('candidates'):
        return {'scope_ok': False, 'predictions': {}}
    return {'scope_ok': True, 'predictions': {c['id']: {'verdict': 'abstain', 'reason': 'unqualified mechanical fixture'} for c in ctx['candidates']}}
'''


def candidate(code=CODE):
    return {'schema_version':'world-model-patch-v1','kind':'world-model',
            'scope':{'source_families':['rotary']},'code':code}


class CompilerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def test_real_sandbox_and_abstention(self):
        r = compile_candidate(candidate(),[CTX],self.root)
        self.assertTrue(r['passed'],r); self.assertEqual(len(r['checks']),5)
        self.assertEqual(r['scientific_probes'],0)
    def test_ast_dangers_do_not_execute(self):
        for code in ['def plan(ctx): return open("secret")',
                     'import os\ndef plan(ctx): return os.environ',
                     'def plan(ctx): return getattr(ctx,"x")',
                     'def plan(ctx): return ctx.__class__',
                     'print("side effect")\ndef plan(ctx): return {}',
                     'def plan(ctx):\n pass = True', 'def not_plan(ctx): return {}',
                     'def plan(ctx, extra): return {}']:
            with self.subTest(code=code):
                self.assertTrue(static_errors(code))
                r=compile_candidate(candidate(code),[CTX],self.root)
                self.assertFalse(r['passed']);self.assertEqual(r['checks'],[])
    def test_output_domain_and_fixture_failures(self):
        for code in ['def plan(ctx): return {}',
                     "def plan(ctx): return {'scope_ok': True, 'predictions': {}}",
                     CODE.replace("'verdict': 'abstain'", "'pass': True"),
                     CODE.replace("'reason': 'unqualified mechanical fixture'", "'minimum_input_v': float('nan')")]:
            self.assertFalse(compile_candidate(candidate(code),[CTX],self.root)['passed'])
        self.assertFalse(compile_candidate(candidate(),[],self.root)['passed'])
        self.assertTrue(context_errors({}))
    def test_compilation_gates_scientific_callback(self):
        bad=candidate('invalid Python !!!'); mechanical=compile_candidate(bad,[CTX],self.root)
        evaluator=Mock(side_effect=AssertionError('science must not run'))
        r=qualify_world(bad,mechanical,evaluator)
        evaluator.assert_not_called();self.assertFalse(r['passed'])
        with self.assertRaises(ValueError):qualify_world(candidate(),mechanical,evaluator)
    def test_repair_is_bounded_and_cached(self):
        calls=[]
        def proposer(feedback):
            calls.append(feedback)
            return {'candidate':candidate(),'cost_receipt':{'wall_s':0.,'cpu_s':0.,'provider_calls':0,'paid_cny':0}}
        initial=candidate('def plan(ctx) return {}')
        result=run_repair(initial,[CTX],self.root,proposer)
        self.assertEqual(result['status'],'mechanically-ready');self.assertEqual(len(result['attempts']),2)
        self.assertEqual(len(calls),1);self.assertEqual(result['scientific_probes'],0)
        self.assertEqual(run_repair(initial,[CTX],self.root,Mock(side_effect=AssertionError('no retry'))),result)
        self.assertIsNone(calls[0]['scientific_feedback'])
    def test_duplicate_stops_and_limit_is_not_extended(self):
        initial=candidate('broken')
        def proposer(feedback):
            return {'candidate':initial,'cost_receipt':{'wall_s':0,'cpu_s':0,'provider_calls':0,'paid_cny':0}}
        result=run_repair(initial,[CTX],self.root,proposer)
        self.assertEqual(result['status'],'duplicate-candidate');self.assertEqual(len(result['attempts']),1)
        with self.assertRaises(ValueError):run_repair(initial,[CTX],self.root,proposer,max_repairs=3)
    def test_unknown_callback_is_not_repeated(self):
        initial=candidate('broken')
        with self.assertRaises(RuntimeError):
            run_repair(initial,[CTX],self.root,Mock(side_effect=RuntimeError('interrupted dispatch')))
        second=Mock(side_effect=AssertionError('duplicate callback'))
        with self.assertRaisesRegex(RuntimeError,'unsettled'):
            run_repair(initial,[CTX],self.root,second)
        second.assert_not_called()
    def test_three_different_invalid_candidates_stop_at_limit(self):
        calls=[]
        def proposer(feedback):
            calls.append(feedback)
            return {'candidate':candidate('broken '+str(len(calls))),'cost_receipt':{'wall_s':0,'cpu_s':0,'provider_calls':0,'paid_cny':0}}
        result=run_repair(candidate('broken'),[CTX],self.root,proposer)
        self.assertEqual(result['status'],'repair-limit');self.assertEqual(len(result['attempts']),3);self.assertEqual(len(calls),2)
    def test_invalid_cost_stops_without_retry(self):
        def proposer(feedback):
            return {'candidate':candidate(),'cost_receipt':{'wall_s':0,'cpu_s':0,'provider_calls':0,'paid_cny':float('nan')}}
        with self.assertRaises(ValueError):run_repair(candidate('broken'),[CTX],self.root,proposer)
        with self.assertRaisesRegex(RuntimeError,'unsettled'):run_repair(candidate('broken'),[CTX],self.root,proposer)
    def test_stale_compiler_cannot_open_scientific_gate(self):
        c=candidate();r=compile_candidate(c,[CTX],self.root)
        r['compiler_hash']='sha256:stale';r.pop('content_hash');r['content_hash']=canonical_hash(r)
        callback=Mock(side_effect=AssertionError('science must not run'))
        with self.assertRaisesRegex(ValueError,'stale'):qualify_world(c,r,callback)
        callback.assert_not_called()
    def test_world_and_workflow_qualifications_are_independent(self):
        world=candidate(); workflow={'schema_version':'harness-patch-v1','kind':'workflow',
            'policy':{'order_by':'esr_ohm','descending':False,'require_transient_before_submit':True,'stop_after_verified':True}}
        w=receipt('world-model',world,False,{'negative_control':True});h=qualify_workflow(workflow)
        self.assertTrue(h['passed'])
        enabled=activated_components(world,w,workflow,h)
        self.assertIsNone(enabled['world-model']);self.assertEqual(enabled['workflow'],workflow)
        bad=copy.deepcopy(workflow);bad['policy']['reference']='edit truth'
        self.assertFalse(qualify_workflow(bad)['passed'])
        with self.assertRaises(ValueError):activated_components(world,h,workflow,w)


if __name__=='__main__': unittest.main()
