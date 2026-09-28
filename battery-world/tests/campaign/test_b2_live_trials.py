import copy
import json
import sys
import tempfile
import time
import unittest
import subprocess
import importlib.util
import io
import contextlib
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from bfworld.kernel.canonical import canonical_hash, write_canonical_json, file_hash
from bfworld.coupled.engine import Design, Reference
from bfworld.coupled.profiled import LoadProfile
from bfworld.campaign.task_context import physics_for, execute_candidate, public_context
from bfworld.campaign.splits import task_record
from bfworld.campaign.trials import ARMS, TOOLS, history_from_runs
from bfworld.campaign.compiler import compile_candidate
from bfworld.campaign.scientific import execute_qualification
from bfworld.campaign.budget import Ledger, BudgetStop
from bfworld.campaign.live_trials import VERSION, execution_pins, validate, run_matrix

sys.path.insert(0, str(Path(__file__).parent))
from test_b2_scientific import fixture
from test_b2_repair_bridge import FakeTransport, fixture_protocol


class DecisionTransport(FakeTransport):
    def __init__(self, ledger):
        super().__init__(ledger); self.bodies = []; self.mode = 'normal'

    def request(self, path, body=None):
        self.bodies.append(copy.deepcopy(body))
        results = []
        for m in body['messages']:
            if m['role'] == 'user':
                data = json.loads(m['content'])
                if 'tool_result' in data: results.append(data['tool_result'])
        if self.mode == 'unbound':
            action = {'action': 'submit', 'candidate_id': 'large', 'claim_pass': True, 'evidence_hash': 'sha256:invented'}
        elif not results:
            action = {'action': 'python', 'code': "def plan(ctx): return {'candidates':len(ctx['task']['candidates'])}"}
        elif results[-1].get('physical_pass'):
            r = results[-1]
            action = {'action': 'submit', 'candidate_id': r['candidate_id'], 'claim_pass': True, 'evidence_hash': r['content_hash']}
        else:
            action = {'action': 'experiment', 'candidate_id': 'large' if any('run_hash' in r for r in results) else 'small', 'predicted_pass': True}
        self.outputs = [json.dumps(action)]
        return super().request(path, body)


class LiveTrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.repo = Path(self.tmp.name)
        qt, qp, self.candidate = fixture()
        m = compile_candidate(self.candidate, [public_context(qt[0])], self.repo/'compile')
        self.q = execute_qualification(self.candidate, m, qt, qp, self.repo/'qualification', acquisition_cost_complete=True)
        self.history = history_from_runs([(qt[0], 'small', execute_candidate(qt[0], 'small'))])
        designs = {'small': replace(Design(), capacitance_f=.00033, esr_ohm=18), 'large': Design()}
        self.tasks = [task_record(n, 'development', physics_for(designs, replace(Reference(), source_phase_rad=p), LoadProfile()), prior_exposure='public')
                      for n, p in [('use-control', .1), ('confirmation-control', .2)]]
        self.cap = {'candidate': self.candidate, 'history_hash': self.history['content_hash'], 'text_lesson': 'Small capacitor failure is public; generalization is not proven.'}
        self.plan = {'schema_version': VERSION, 'purpose': 'provider-controls', 'arms': ARMS, 'tools': TOOLS,
                     'max_turns': 5, 'max_experiments': 2, 'session_namespace': 'provider-test',
                     'candidate_order_rule': 'stable-capacitance-ascending', 'task_id': self.tasks[0]['task_id'], 'confirmation_id': self.tasks[1]['task_id']}
        self.protocol = fixture_protocol()
        self.bind_protocol()
        self.ledger = Ledger(self.repo/'.bfworld/paid-campaign/cost.sqlite')
        self.transport = DecisionTransport(self.ledger)

    def bind_protocol(self):
        self.protocol['task_manifest_hash'] = canonical_hash(self.tasks)
        self.protocol['matched_trial_execution'] = {**execution_pins(self.plan, self.tasks, self.history, self.cap, self.q), 'model_fingerprint': 'fixture-fingerprint'}
        self.protocol['owner_approval'] = {'approval_id': 'TEST-ONLY', 'protocol_hash': canonical_hash({k: v for k, v in self.protocol.items() if k != 'owner_approval'})}

    def tearDown(self):
        self.ledger.db.close(); self.tmp.cleanup()

    def run_control(self, **kw):
        return run_matrix(self.plan, self.tasks, self.history, self.cap, self.q, self.protocol, self.repo, self.transport, self.repo/'matrix', **kw)

    def test_complete_provider_to_effect_to_submission_and_replay(self):
        r = self.run_control()
        self.assertEqual(r['cost']['provider_calls'], 16)
        self.assertEqual(r['cost']['actual_provider_calls'], 0)
        self.assertEqual(r['cost']['usage_tokens'], 2400)
        self.assertTrue(r['cost']['local_cost_complete'])
        self.assertFalse(r['cost']['total_campaign_cost_complete'])
        self.assertFalse(r['formal_agent_result']); self.assertFalse(r['transfer_validated'])
        self.assertTrue(all(o['evidence_bound_computational_success'] for o in r['outcomes']))
        contexts = [json.loads(t['initial_messages'][1]['content']) for t in r['trials']]
        self.assertTrue(all(c['raw_history'] == contexts[0]['raw_history'] and c['task'] == contexts[0]['task'] for c in contexts))
        self.assertEqual(r['trials'][0]['counters']['python_calls'], 1)
        self.assertTrue(all('confirmation-control' not in json.dumps(b) for b in self.transport.bodies))
        self.assertTrue(all('remaining_turns_including_this_one' in b['messages'][-1]['content'] for b in self.transport.bodies))
        before = self.ledger.summary()
        with patch.object(self.transport, 'request', side_effect=AssertionError('repeat paid effect')), patch('bfworld.coupled.profiled.execute', side_effect=AssertionError('repeat numerical solver')):
            self.assertEqual(self.run_control(reconcile_only=True), r)
        self.assertEqual(self.ledger.summary(), before)

    def test_settled_decision_recovered_with_unknown_local_interval(self):
        def fault(point):
            if point == 'decision-0-computed': raise RuntimeError('injected parent loss')
        with self.assertRaisesRegex(RuntimeError, 'parent loss'): self.run_control(fault=fault)
        self.assertEqual(self.transport.requests, 1)
        r = self.run_control()
        self.assertEqual(self.transport.requests, 16)
        self.assertFalse(r['cost']['local_cost_complete'])
        saved = json.loads((self.repo/'matrix/raw-history/decision-0.json').read_text())
        self.assertIsNone(saved['cost']['cpu_s'])

    def test_unknown_reserved_transport_never_retries(self):
        self.transport.failure = BudgetStop('unknown remote effect')
        with self.assertRaises(BudgetStop): self.run_control()
        with self.assertRaisesRegex(BudgetStop, 'uncertain'): self.run_control()
        self.assertEqual(self.transport.requests, 1)
        self.assertEqual(self.ledger.summary()['unsettled'], 1)

    def test_unknown_local_tool_effect_stops_instead_of_repeating(self):
        def fault(point):
            if point == 'effect-0-computed': raise RuntimeError('injected local loss')
        with self.assertRaises(RuntimeError): self.run_control(fault=fault)
        with self.assertRaisesRegex(BudgetStop, 'unresolved local effect'): self.run_control()
        self.assertEqual(self.transport.requests, 1)

    def test_draft_wrong_pins_and_empty_lesson_stop_before_transport(self):
        self.protocol['status'] = 'draft-not-authorized'
        with self.assertRaisesRegex(BudgetStop, 'owner-approved'): self.run_control()
        self.assertEqual(self.transport.requests, 0)
        self.protocol['status'] = 'owner-approved'; self.bind_protocol()
        self.cap['text_lesson'] = ''
        with self.assertRaisesRegex(BudgetStop, 'text lesson'): self.run_control()

    def test_engineering_qualification_cannot_enable_formal_agent_arm(self):
        self.plan['purpose'] = 'formal-agent-trial'
        self.tasks = [task_record(t['task_id'], 'blind-transfer', t['physics']) for t in self.tasks]
        self.bind_protocol()
        with self.assertRaisesRegex(BudgetStop, 'scientific qualification'): self.run_control()
        self.assertEqual(self.transport.requests, 0)

    def test_unbound_passing_design_never_admitted(self):
        self.transport.mode = 'unbound'
        r = self.run_control()
        self.assertTrue(all(not o['evidence_bound_computational_success'] for o in r['outcomes'][:4]))

    def test_barrier_precedes_all_confirmation(self):
        def fault(point):
            if point == 'all-trials-frozen':
                self.assertTrue(all((self.repo/'matrix'/a/'trial.json').exists() for a in ARMS))
                self.assertFalse((self.repo/'matrix/confirmation').exists())
                raise RuntimeError('barrier control')
        with self.assertRaisesRegex(RuntimeError, 'barrier'): self.run_control(fault=fault)
        before = self.transport.requests
        r = self.run_control(); self.assertEqual(self.transport.requests, before)
        self.assertTrue(r['outcomes'][0]['evidence_bound_computational_success'])

    def test_rehashed_submission_effect_cannot_self_certify_evidence(self):
        self.transport.mode = 'unbound'
        def fault(point):
            if point == 'all-trials-frozen': raise RuntimeError('pause before final')
        with self.assertRaises(RuntimeError): self.run_control(fault=fault)
        path = self.repo/'matrix/raw-history/effect-0.json'; obj = json.loads(path.read_text())
        obj['value']['submission']['evidence_admissible'] = True
        obj.pop('content_hash'); obj['content_hash'] = canonical_hash(obj); write_canonical_json(path, obj)
        with self.assertRaisesRegex(BudgetStop, 'submission evidence'): self.run_control()

    def test_model_fingerprint_drift_is_paid_but_not_admitted(self):
        self.transport.fingerprint = 'changed'
        with self.assertRaisesRegex(BudgetStop, 'fingerprint drift'): self.run_control()
        self.assertEqual(self.ledger.summary()['calls'], 1)
        self.assertEqual(self.ledger.summary()['unsettled'], 0)

    def test_unrelated_uncertain_call_stops_new_provider_trial(self):
        self.ledger.reserve('older-unknown-call', 'older-task', {'max_tokens': 10})
        with self.assertRaisesRegex(BudgetStop, 'uncertain prior call'):
            self.run_control()
        self.assertEqual(self.transport.requests, 0)

    def test_explicit_action_budget_stops_without_extra_provider_calls(self):
        self.plan['max_turns'] = 3; self.bind_protocol()
        result = self.run_control()
        self.assertEqual(self.transport.requests, 12)
        self.assertTrue(all(t['submission'] is None for t in result['trials'][:4]))
        self.assertTrue(all(not o['evidence_bound_computational_success'] for o in result['outcomes'][:4]))

    def test_real_process_exit_after_settled_decision_resumes_once(self):
        payload = {'plan': self.plan, 'tasks': self.tasks, 'history': self.history, 'capsule': self.cap,
                   'qualification': self.q, 'protocol': self.protocol}
        path = self.repo/'child-input.json'; write_canonical_json(path, payload)
        module_dir = Path(__file__).parent
        from bfworld.campaign import live_trials
        library = Path(live_trials.__file__).parents[2]
        code = f'''import sys,json,os
sys.path.insert(0,{str(library)!r});sys.path.insert(0,{str(module_dir)!r})
from pathlib import Path
from test_b2_live_trials import DecisionTransport
from bfworld.campaign.budget import Ledger
from bfworld.campaign.live_trials import run_matrix
repo=Path({str(self.repo)!r}); p=json.loads((repo/'child-input.json').read_text())
ledger=Ledger(repo/'.bfworld/paid-campaign/cost.sqlite')
def fault(point):
    if point=='decision-0-computed':os._exit(72)
run_matrix(**p,repo=repo,provider=DecisionTransport(ledger),root=repo/'matrix',fault=fault)
'''
        child = subprocess.run([sys.executable, '-c', code], capture_output=True, timeout=30,
                               env={'PATH': '/usr/bin:/bin', 'LANG': 'en_US.UTF-8'})
        self.assertEqual(child.returncode, 72, child.stderr.decode())
        self.assertEqual(self.ledger.summary()['calls'], 1)
        result = self.run_control()
        self.assertEqual(self.ledger.summary()['calls'], 16)
        self.assertEqual(self.transport.requests, 15)
        self.assertFalse(result['cost']['local_cost_complete'])

    def test_expired_window_replays_settled_matrix_but_blocks_new_effects(self):
        result = self.run_control()
        future = self.protocol['shared_budget']['new_campaign_execution_window']['ends_unix_s']+1
        with patch('bfworld.campaign.live_trials.time.time', return_value=future):
            self.assertEqual(self.run_control(reconcile_only=True), result)
            with self.assertRaisesRegex(BudgetStop, 'expired'):
                validate(self.plan, self.tasks, self.history, self.cap, self.q, self.protocol, dispatch=True)

    def test_saved_provider_slot_transcript_cannot_be_changed(self):
        self.run_control()
        path = self.repo/'matrix/raw-history/provider/slots/0.json'
        obj = json.loads(path.read_text()); obj['request']['messages'][1]['content'] = '{}'
        obj.pop('content_hash'); obj['content_hash'] = canonical_hash(obj); write_canonical_json(path, obj)
        with self.assertRaisesRegex(BudgetStop, 'transcript'):
            self.run_control(reconcile_only=True)

    def cli(self, argv):
        from bfworld.campaign import live_trials
        repo = Path(live_trials.__file__).parents[6]
        spec = importlib.util.spec_from_file_location('b2_live_cli_test', repo/'scripts/run_b2_trials.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module.REPO = self.repo
        stream = io.StringIO()
        with patch.object(sys, 'argv', ['run_b2_trials.py', *argv]), contextlib.redirect_stdout(stream):
            result = module.main()
        return result, json.loads(stream.getvalue().splitlines()[-1])

    def test_cli_draft_rejected_before_key_or_output_access(self):
        payload = {'plan': self.plan, 'tasks': self.tasks, 'history': self.history, 'capsule': self.cap, 'qualification': self.q}
        write_canonical_json(self.repo/'input.json', payload)
        self.protocol['status'] = 'draft-not-authorized'; write_canonical_json(self.repo/'draft.json', self.protocol)
        rc, out = self.cli(['--inputs', str(self.repo/'input.json'), '--protocol', str(self.repo/'draft.json'),
                            '--output', str(self.repo/'never-created'), '--execute', '--key-file', str(self.repo/'absent-key')])
        self.assertEqual(rc, 2); self.assertFalse(out['credentials_loaded'])
        self.assertFalse((self.repo/'never-created').exists())

    def test_cli_reconciliation_is_read_only_without_credentials(self):
        result = self.run_control(); path = self.repo/'.bfworld/paid-campaign/cost.sqlite'
        before = file_hash(path); write_canonical_json(self.repo/'protocol.json', self.protocol)
        rc, out = self.cli(['--inputs', str(self.repo/'matrix/inputs.json'), '--protocol', str(self.repo/'protocol.json'),
                            '--output', str(self.repo/'matrix'), '--reconcile-only'])
        self.assertEqual(rc, 0); self.assertEqual(out['report_hash'], result['content_hash'])
        self.assertEqual(before, file_hash(path)); self.assertEqual(self.transport.requests, 16)


if __name__ == '__main__': unittest.main()
