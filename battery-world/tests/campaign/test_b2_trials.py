import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.coupled.engine import Design, Reference
from bfworld.coupled.profiled import LoadProfile
from bfworld.campaign.task_context import physics_for, execute_candidate
from bfworld.campaign.splits import task_record
from bfworld.campaign.trials import (VERSION, ARMS, TOOLS, run_matrix, audit_matrix,
                                     history_from_runs, proposal_request)

CODE = '''def plan(ctx):
    if not isinstance(ctx,dict) or ctx.get('source_family') != 'rotary' or not isinstance(ctx.get('conditions'),dict) or not ctx.get('candidates'):
        return {'scope_ok':False,'predictions':{}}
    return {'scope_ok':True,'predictions':{c['id']:{'verdict':'feasible' if c['capacitance_f']>=.0022 else 'infeasible'} for c in ctx['candidates']}}
'''


class Control:
    decision_origin = 'scripted-unpaid-control'
    implementation_hash = file_hash(Path(__file__))

    def __init__(self, mode='normal'):
        self.mode, self.requests = mode, []
        self.configuration_hash = canonical_hash({'mode': mode})

    def __call__(self, request):
        self.requests.append(copy.deepcopy(request))
        context = json.loads(request['messages'][1]['content'])
        if self.mode == 'crash':
            raise RuntimeError('injected decision interruption')
        if self.mode == 'false-claim':
            return {'action': 'submit', 'candidate_id': 'small', 'claim_pass': True, 'evidence_hash': 'sha256:missing'}
        if self.mode == 'unbound':
            return {'action': 'submit', 'candidate_id': 'large', 'claim_pass': True, 'evidence_hash': 'sha256:missing'}
        if self.mode == 'abstain':
            return {'action': 'abstain', 'reason': 'insufficient evidence'}
        if request['turn'] == 0:
            return {'action': 'python', 'code': "def plan(ctx): return {'available':len(ctx['task']['candidates'])}"}
        if request['turn'] == 1:
            choice = 'large'
            if context['knowledge']:
                choice = next(k for k, v in context['knowledge']['output']['predictions'].items() if v['verdict'] == 'feasible')
            return {'action': 'experiment', 'candidate_id': choice, 'predicted_pass': True}
        facts = json.loads(request['messages'][-1]['content'])['tool_result']
        return {'action': 'submit', 'candidate_id': facts['candidate_id'],
                'claim_pass': True, 'evidence_hash': facts['content_hash']}


class MatchedTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        designs = {'small': replace(Design(), capacitance_f=.00033, esr_ohm=18), 'large': Design()}
        def task(name, phase):
            return task_record(name, 'development', physics_for(designs, replace(Reference(), source_phase_rad=phase), LoadProfile()), prior_exposure='public')
        self.history_task, self.task, self.final = task('history', 0), task('new-use-control', .1), task('confirmation-control', .2)
        self.history = history_from_runs([(self.history_task, 'small', execute_candidate(self.history_task, 'small'))])
        candidate = {'schema_version': 'world-model-patch-v1', 'kind': 'world-model', 'scope': {'source_families': ['rotary']}, 'code': CODE}
        self.capsule = {'history_hash': self.history['content_hash'], 'text_lesson': 'One small-capacitor design browned out; source-phase generalization remains untested.',
                        'candidate': candidate, 'engineering_activation': {'scope': 'engineering-interface-only', 'enabled': True, 'candidate_hash': canonical_hash(candidate)}}
        self.plan = {'schema_version': VERSION, 'purpose': 'engineering-controls', 'arms': ARMS, 'tools': TOOLS,
                     'max_turns': 4, 'max_experiments': 2, 'candidate_order_rule': 'stable-capacitance-ascending',
                     'session_namespace': 'unpaid-test', 'history_hash': self.history['content_hash'],
                     'task_hash': self.task['content_hash'], 'confirmation_hash': self.final['content_hash'], 'capsule_hash': canonical_hash(self.capsule)}

    def tearDown(self):
        self.temp.cleanup()

    def run_control(self, control=None):
        return run_matrix(self.plan, self.task, self.final, self.history, self.capsule, control or Control(), self.root/'matrix')

    def test_five_arm_messages_treatments_tools_and_raw_python(self):
        control = Control()
        report = self.run_control(control)
        self.assertEqual([t['arm'] for t in report['trials']], ARMS)
        initial = [json.loads(t['initial_messages'][1]['content']) for t in report['trials']]
        self.assertTrue(all(c['task'] == initial[0]['task'] and c['raw_history'] == initial[0]['raw_history'] for c in initial))
        self.assertEqual(len({t['session_id'] for t in report['trials']}), 5)
        self.assertTrue(all(t['tools'] == TOOLS for t in report['trials']))
        self.assertEqual([t['treatment']['program_invocations'] for t in report['trials']], [0, 0, 1, 1, 0])
        self.assertTrue(initial[1]['lesson'].strip())
        self.assertEqual(initial[2]['knowledge']['output'], initial[3]['knowledge']['output'])
        self.assertEqual(report['trials'][0]['counters']['python_calls'], 1)
        self.assertTrue(all(o['admitted_computational_control'] for o in report['outcomes']))
        self.assertFalse(report['formal_agent_result'])
        self.assertFalse(report['transfer_validated'])
        self.assertEqual(report['cost']['actual_provider_calls'], 0)
        self.assertTrue(all('confirmation-control' not in json.dumps(r) for r in control.requests))
        self.assertTrue(all('"label"' not in json.dumps(c) and '"loss"' not in json.dumps(c) for c in initial))

    def test_final_execution_waits_until_all_trial_files_are_frozen(self):
        from bfworld.campaign import trials
        original = trials.execute_candidate
        def observed(task, candidate):
            if task['task_id'] == self.final['task_id']:
                self.assertTrue((self.root/'matrix/learning-frozen.json').exists())
                self.assertTrue(all((self.root/'matrix'/a/'trial.json').exists() for a in ARMS))
            return original(task, candidate)
        with patch.object(trials, 'execute_candidate', side_effect=observed):
            self.run_control()

    def test_complete_replay_uses_no_callback_or_reference(self):
        first = self.run_control()
        with patch('bfworld.campaign.trials.execute_candidate', side_effect=AssertionError('no rerun')), patch.object(Control, '__call__', side_effect=AssertionError('no callback')):
            second = self.run_control()
        self.assertEqual(first, second)

    def test_nonempty_text_and_exact_shared_history_are_required(self):
        self.capsule['text_lesson'] = ' '
        self.plan['capsule_hash'] = canonical_hash(self.capsule)
        with self.assertRaisesRegex(ValueError, 'empty'):
            self.run_control()
        self.capsule['text_lesson'] = 'evidence'
        self.plan['history_hash'] = 'sha256:changed'
        with self.assertRaisesRegex(ValueError, 'history'):
            self.run_control()

    def test_inactive_or_wrong_candidate_qualified_interface_stops(self):
        self.capsule['engineering_activation']['enabled'] = False
        self.plan['capsule_hash'] = canonical_hash(self.capsule)
        with self.assertRaisesRegex(ValueError, 'inactive'):
            self.run_control()

    def test_failing_claim_and_passing_but_unbound_claim_are_not_admitted(self):
        r = self.run_control(Control('false-claim'))
        self.assertTrue(all(x['false_claim'] and not x['admitted_computational_control'] for x in r['outcomes'][:4]))
        r = run_matrix(self.plan, self.task, self.final, self.history, self.capsule, Control('unbound'), self.root/'unbound')
        self.assertTrue(all(not x['false_claim'] and x['unbound_claim'] and not x['admitted_computational_control'] for x in r['outcomes'][:4]))

    def test_abstention_is_not_a_success(self):
        r = self.run_control(Control('abstain'))
        self.assertTrue(all(x['final'] is None and not x['admitted_computational_control'] for x in r['outcomes'][:4]))

    def test_interrupted_decision_does_not_get_retried(self):
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.run_control(Control('crash'))
        with self.assertRaisesRegex(RuntimeError, 'reconcile'):
            self.run_control(Control('crash'))

    def test_formal_mode_cannot_silently_use_scripted_controls(self):
        self.plan['purpose'] = 'formal-agent-trial'
        with self.assertRaisesRegex(ValueError, 'authorized'):
            self.run_control()

    def test_proposal_history_rejects_hidden_and_observation_mismatch(self):
        req = proposal_request(self.history, self.capsule['candidate'], generation='G3')
        self.assertEqual(req['history_hash'], self.history['content_hash'])
        blind = task_record('hidden', 'blind-transfer', self.history_task['physics'])
        with self.assertRaisesRegex(ValueError, 'blind'):
            history_from_runs([(blind, 'small', execute_candidate(blind, 'small'))])
        with self.assertRaisesRegex(ValueError, 'bind'):
            history_from_runs([(self.history_task, 'large', execute_candidate(self.history_task, 'small'))])

    def test_trial_or_confirmation_tampering_is_rejected(self):
        report = self.run_control()
        report['outcomes'][0]['final']['physical_pass'] = False
        report.pop('content_hash')
        report['content_hash'] = canonical_hash(report)
        write_canonical_json(self.root/'matrix/report.json', report)
        with self.assertRaisesRegex(ValueError, 'observation'):
            audit_matrix(self.root/'matrix')

    def test_rehashed_historical_truth_does_not_become_training_evidence(self):
        run = execute_candidate(self.history_task, 'small')
        run['physical_mission_pass']['value'] = True
        run.pop('content_hash'); run['content_hash'] = canonical_hash(run)
        with self.assertRaisesRegex(ValueError, 'reproduction'):
            history_from_runs([(self.history_task, 'small', run)])


if __name__ == '__main__':
    unittest.main()
