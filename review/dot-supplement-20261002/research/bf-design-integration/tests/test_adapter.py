"""Offline transport fixtures using actual published task validation/evaluation.

No HTTP server, provider, native solver, paid study or production database.
"""
import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(REPO / 'battery-world/packages/python/bfworld/src'))
import method_adapter as m
from analyze_ledger import analyze
from bfworld.agentlab.simulation_tasks import load_task, check_candidate, evaluate, NUMERICAL, SimulationTasks


class ToolFixture:
    def __init__(self, owner, directory):
        self.owner = owner
        self.directory = Path(directory)
        self.binding = {**load_task(), 'owner': owner, 'max_candidates': 3, 'created': 0}
        self.jobs, self.calls, self.submission = {}, [], None
        self.fail_run_once = False
        self.fail_submit_once = False
        self.wrap = False
        self.production_summary = False
        self.mutate = lambda action, value: value

    def artifact(self, owner, job_id, name):
        if owner != self.owner:
            raise PermissionError('OWNER')
        job = next(j for j in self.jobs.values() if j['id'] == job_id)
        entry = next(a for a in job['result']['artifacts'] if a['name'] == name)
        path = self.directory / job_id / name
        if m.file_hash(path) != entry['sha256']:
            raise ValueError('ARTIFACT_HASH_MISMATCH')
        return path

    def complete(self, operation, *, status='SUCCEEDED', padding=''):
        job = self.jobs[operation]
        path = self.directory / job['id']
        path.mkdir(exist_ok=True)
        spec = job['parameters']['candidate']
        result = {'run_status': 'completed', 'checks': {key: True for key in NUMERICAL},
                  'metrics': {'cold_start_reached': False}, 'applicability': {}, 'note': padding}
        receiver = {'transmitted': [], 'delivered': [], 'events': []}
        result['task_evaluation'] = evaluate(self.binding, spec, result, receiver)
        for name, value in [('result.json', result), ('design-spec.json', spec), ('receiver.json', receiver)]:
            (path / name).write_text(json.dumps(value, ensure_ascii=False) + '\n')
        job['result'] = {**result, 'artifacts': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': m.file_hash(p)} for p in sorted(path.iterdir())]}
        job['status'] = status

    def __call__(self, args):
        self.calls.append(copy.deepcopy(args))
        action = args['action']
        if action == 'inspect':
            value = {'task_binding': self.binding, 'jobs': list(self.jobs.values())}
        elif action == 'skill':
            content = 'Synthetic skill; no runtime execution.'
            value = {'content': content, 'sha256': m.file_bytes_hash(content.encode())}
        elif action == 'run':
            op = args['operation_id']
            spec = check_candidate(self.binding, args['parameters'])
            if op not in self.jobs:
                if self.submission or len(self.jobs) >= 3:
                    raise ValueError('BACKEND_QUOTA_OR_SUBMITTED')
                self.jobs[op] = {'id': 'eng-' + m.digest(op)[:12], 'owner': self.owner, 'operation': op,
                    'status': 'QUEUED', 'engine': 'closed-simulation', 'parameters': {'candidate': spec, 'confirmation': True},
                    'task_binding': self.binding, 'result': None}
            elif self.jobs[op]['parameters'] != args['parameters']:
                raise ValueError('BACKEND_OPERATION_CONFLICT')
            if self.fail_run_once:
                self.fail_run_once = False
                raise TimeoutError('Synthetic unknown effect after reservation')
            value = self.jobs[op]
        elif action == 'job':
            value = next(j for j in self.jobs.values() if j['id'] == args['job_id'])
        elif action == 'artifact_view':
            value = SimulationTasks.artifact_view(None, self, self.owner, args)
        elif action == 'submit':
            job = next(j for j in self.jobs.values() if j['id'] == args['job_id'])
            result_path = self.artifact(self.owner, job['id'], 'result.json')
            result = json.loads(result_path.read_text())
            spec = json.loads(self.artifact(self.owner, job['id'], 'design-spec.json').read_text())
            receiver = json.loads(self.artifact(self.owner, job['id'], 'receiver.json').read_text())
            if evaluate(self.binding, spec, result, receiver) != result['task_evaluation']:
                raise ValueError('BACKEND_EVALUATION_MISMATCH')
            receipt = {'owner': self.owner, 'job_id': job['id'], 'task_hash': self.binding['task_hash'],
                       'result_sha256': m.file_hash(result_path), 'evaluation': result['task_evaluation'],
                       'rationale': args['rationale'], 'claim': 'participant selection; not product acceptance'}
            if self.submission and self.submission != receipt:
                raise ValueError('BACKEND_SUBMISSION_IMMUTABLE')
            self.submission = receipt
            if self.fail_submit_once:
                self.fail_submit_once = False
                raise TimeoutError('Synthetic committed submission; response lost')
            value = receipt
        else:
            raise AssertionError('Unexpected action')
        value = self.mutate(action, copy.deepcopy(value))
        text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        if self.production_summary and len(text.encode()) > 24000:
            sha = m.file_bytes_hash(text.encode())
            summary = {'record_file': 'tool-records/' + sha + '.json', 'sha256': sha,
                       'bytes': len(text.encode()), 'id': value.get('id'), 'status': value.get('status')}
            return {'content': [{'type': 'text', 'text': json.dumps(summary)}], 'details': {}}
        return {'content': [{'type': 'text', 'text': json.dumps(value)}], 'details': {}} if self.wrap else value


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.tool = ToolFixture('owner-A', self.path)
        self.adapter = m.Adapter('owner-A', 'bf_design', self.tool, self.path / 'ledger')

    def tearDown(self):
        self.adapter.close()
        self.tmp.cleanup()

    def run_one(self, op='a', candidate=None):
        return self.adapter.run_candidate(op, candidate or {}, rationale='Synthetic numeric revision', falsifier='No predicted nominal response')

    def finish(self, op='a', **kwargs):
        self.tool.complete(op, **kwargs)
        return self.adapter.poll(op)

    def test_published_task_hash_and_numeric_checker_agree(self):
        self.assertEqual(m.load_protocol()['normalized_task_hash'], load_task()['task_hash'])
        for c in [{}, {'mechanical': {'gap_mm': 28}}, {'circuit': {'cin_uF': 10, 'cout_uF': 22}, 'firmware': {'interval_ms': 200}}]:
            self.assertEqual(m.normalize_candidate(c, self.adapter.task), check_candidate(self.tool.binding, {'candidate': c, 'confirmation': True}))

    def test_protected_unknown_nonfinite_and_architecture_denied(self):
        for c in [{'mechanical': {'opening_s': 1}}, {'circuit': {'initial_vin_V': 3}}, {'link': {'seed': 2}},
                  {'mechanical': {'gap_mm': True}}, {'mechanical': {'gap_mm': float('nan')}},
                  {'circuit': {'cin_uF': 23}}, {'firmware': {'source': 'new.c'}}, {'architecture': 'new'}]:
            with self.subTest(c=c), self.assertRaises(m.Rejected):
                self.run_one(candidate=c)
        with self.assertRaisesRegex(m.Rejected, 'ARCHITECTURE'):
            self.adapter.run_candidate('a', {}, rationale='x', falsifier='y', revision_kind='architecture')
        self.assertFalse(self.tool.jobs)

    def test_profile_conditions_share_facts_and_freedoms(self):
        values = [m.method_prompt(self.adapter.protocol, p['id'], self.adapter.task, []) for p in self.adapter.protocol['profiles']]
        self.assertEqual(len({v['shared_hash'] for v in values}), 1)
        self.assertEqual(len({v['text'] for v in values}), 4)
        self.assertTrue(all(v['shared']['max_new_candidates'] == 3 and not v['shared']['architecture_changes'] for v in values))

    def test_actual_activation_and_action_provenance(self):
        self.run_one()
        activation = next(r['data'] for r in self.adapter.ledger.events if r['kind'] == 'method_activation')
        self.assertEqual(activation['output_hash'], m.digest(m.method_prompt(self.adapter.protocol, 'bf_design', self.adapter.task, [])))
        intents = {r['hash'] for r in self.adapter.ledger.events if r['kind'] == 'action_intent'}
        results = [r['data'] for r in self.adapter.ledger.events if r['kind'] == 'action_result']
        self.assertTrue(all(r['intent_hash'] in intents and r['response_hash'] == m.digest(r['response']) for r in results))
        self.assertEqual(self.tool.calls[-1]['action'], 'run')

    def test_pending_poll_is_read_only_and_blocks_another_candidate(self):
        self.run_one(); self.adapter.poll('a')
        with self.assertRaisesRegex(m.Rejected, 'PENDING'):
            self.run_one('b')
        self.assertEqual(sum(c['action'] == 'run' for c in self.tool.calls), 1)

    def test_idempotent_retry_and_conflict(self):
        first = self.run_one(); second = self.run_one()
        self.assertEqual(first, second)
        with self.assertRaisesRegex(m.Rejected, 'OPERATION_CONFLICT'):
            self.run_one(candidate={'mechanical': {'gap_mm': 40}})
        self.assertEqual(len(self.adapter.operations), 1)

    def test_timeout_after_effect_reconciles_same_operation(self):
        self.tool.fail_run_once = True
        with self.assertRaises(TimeoutError): self.run_one()
        with self.assertRaisesRegex(m.Rejected, 'PENDING'): self.run_one('b')
        self.assertEqual(self.run_one()['id'], self.tool.jobs['a']['id'])
        self.assertEqual(len(self.tool.jobs), 1)

    def test_three_candidate_quota_survives_reopen(self):
        for op in ['a', 'b', 'c']:
            self.run_one(op); self.finish(op)
        self.adapter.close()
        self.adapter = m.Adapter('owner-A', 'bf_design', self.tool, self.path / 'ledger')
        with self.assertRaisesRegex(m.Rejected, 'QUOTA'): self.run_one('d')
        self.assertEqual(len(self.tool.jobs), 3)

    def test_unknown_job_requires_reconciliation(self):
        self.run_one(); self.tool.jobs['a']['status'] = 'UNKNOWN'; self.adapter.poll('a')
        with self.assertRaisesRegex(m.Rejected, 'PENDING'): self.run_one('b')

    def test_owner_and_profile_ledger_isolation(self):
        self.adapter.close()
        for owner, profile in [('other', 'bf_design'), ('owner-A', 'strong_generic')]:
            with self.assertRaisesRegex(m.Rejected, 'LEDGER_IDENTITY'):
                m.Adapter(owner, profile, self.tool, self.path / 'ledger')

    def test_exclusive_writer(self):
        with self.assertRaises(FileExistsError):
            m.Adapter('owner-A', 'bf_design', self.tool, self.path / 'ledger')

    def test_ledger_tamper_rejected(self):
        self.adapter.close()
        path = self.path / 'ledger/events.jsonl'
        rows = path.read_text().splitlines(); row = json.loads(rows[0]); row['data']['owner'] = 'forged'; rows[0] = json.dumps(row)
        path.write_text('\n'.join(rows) + '\n')
        with self.assertRaisesRegex(m.Rejected, 'LEDGER_HASH'):
            m.Adapter('owner-A', 'bf_design', self.tool, self.path / 'ledger')

    def test_task_owner_hash_and_quota_admission(self):
        for field, value in [('owner', 'foreign'), ('task_hash', 'f'*64), ('max_candidates', 2)]:
            tool = ToolFixture('owner-A', self.path); tool.binding[field] = value
            with self.subTest(field=field), self.assertRaises(m.Rejected):
                m.Adapter('owner-A', 'bf_design', tool, self.path / ('bad-' + field))

    def test_unaccounted_backend_jobs_refuse_fresh_ledger(self):
        self.run_one()
        with self.assertRaisesRegex(m.Rejected, 'UNACCOUNTED'):
            m.Adapter('owner-A', 'bf_design', self.tool, self.path / 'fresh-ledger')

    def test_wrong_job_owner_and_candidate_rejected(self):
        for field, value in [('owner', 'foreign'), ('parameters', {}), ('id', '../bad')]:
            self.tool.mutate = lambda action, v, f=field, x=value: {**v, f: x} if action == 'run' else v
            with self.subTest(field=field), self.assertRaises(m.Rejected): self.run_one()
        self.assertEqual(len(self.tool.jobs), 1)

    def test_artifact_pagination_unicode_and_manifest_hash(self):
        self.run_one(); self.finish(padding='中文' * 14000)
        result, sha = self.adapter.read_artifact('a', 'result.json')
        self.assertEqual(len(result['note']), 28000)
        self.assertEqual(sha, m.file_hash(self.path / self.tool.jobs['a']['id'] / 'result.json'))
        self.assertGreater(sum(c['action'] == 'artifact_view' for c in self.tool.calls), 1)

    def test_artifact_bytes_tamper_rejected(self):
        self.run_one(); self.finish()
        (self.path / self.tool.jobs['a']['id'] / 'result.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH'):
            self.adapter.read_artifact('a', 'result.json')

    def test_wrong_page_hash_and_nonadvancing_offset_rejected(self):
        self.run_one(); self.finish(padding='x' * 30000)
        for update in [{'sha256': 'f'*64}, {'next_offset': 0}, {'truncated': False}]:
            self.tool.mutate = lambda action, v, u=update: {**v, **u} if action == 'artifact_view' else v
            with self.subTest(update=update), self.assertRaises(m.Rejected):
                self.adapter.read_artifact('a', 'result.json')

    def test_final_failed_candidate_submission_is_not_scientific_success(self):
        self.run_one(); self.finish(status='FAILED')
        proof = self.adapter.submit('a', 'Retain synthetic failure')
        self.assertFalse(proof['scientific_success'])
        self.assertEqual(proof['receipt']['evaluation']['nominal_task_status'], 'unsatisfied')
        self.assertFalse(proof['receipt']['evaluation']['design_ranking_eligible'])
        calls = len(self.tool.calls)
        self.assertEqual(self.adapter.submit('a', 'Retain synthetic failure'), proof)
        self.assertEqual(len(self.tool.calls), calls)
        with self.assertRaisesRegex(m.Rejected, 'IMMUTABLE'): self.adapter.submit('a', 'Different reason')
        with self.assertRaisesRegex(m.Rejected, 'SUBMITTED'): self.run_one('b')

    def test_pending_submission_refused(self):
        self.run_one()
        with self.assertRaisesRegex(m.Rejected, 'JOB_NOT_FINAL'): self.adapter.submit('a', 'Not finished')

    def test_lost_submission_response_is_immutable_and_recoverable(self):
        self.run_one(); self.finish(); self.tool.fail_submit_once = True
        with self.assertRaises(TimeoutError): self.adapter.submit('a', 'Keep failure')
        with self.assertRaisesRegex(m.Rejected, 'SUBMITTED'): self.run_one('b')
        with self.assertRaisesRegex(m.Rejected, 'IMMUTABLE'): self.adapter.submit('a', 'Different reason')
        self.adapter.close()
        self.adapter = m.Adapter('owner-A', 'bf_design', self.tool, self.path / 'ledger')
        self.assertEqual(self.adapter.submit('a', 'Keep failure')['receipt'], self.tool.submission)

    def test_forged_submission_proof_rejected(self):
        self.run_one(); self.finish()
        self.tool.mutate = lambda action, v: {**v, 'result_sha256': 'f'*64} if action == 'submit' else v
        with self.assertRaisesRegex(m.Rejected, 'SUBMISSION_PROOF'): self.adapter.submit('a', 'Keep failure')

    def test_actual_tool_reply_envelope_and_skill_hash(self):
        self.tool.wrap = True
        self.assertEqual(self.adapter.read_skill()['content'], 'Synthetic skill; no runtime execution.')
        self.run_one(); self.finish(); self.adapter.submit('a', 'Keep failure')

    def test_terminal_result_mutation_is_rejected(self):
        self.run_one(); self.finish()
        self.tool.jobs['a']['status'] = 'RUNNING'
        with self.assertRaisesRegex(m.Rejected, 'TERMINAL_JOB_CHANGED'): self.adapter.poll('a')

    def test_read_only_analysis_retains_failures_without_cost_or_success_inference(self):
        self.tool.fail_run_once = True
        with self.assertRaises(TimeoutError): self.run_one()
        before = self.adapter.ledger.path.read_bytes()
        report = analyze(self.adapter.ledger.path)
        self.assertEqual(report['reserved_candidates'], 1)
        self.assertEqual(report['action_intents']['run'], 1)
        self.assertIsNone(report['costs'])
        self.assertFalse(report['scientific_success'])
        self.assertEqual(before, self.adapter.ledger.path.read_bytes())

    def test_production_large_job_summary_blocks_without_record_file_read(self):
        self.run_one()
        self.tool.complete('a', padding='x' * 25000)
        self.tool.production_summary = True
        with self.assertRaisesRegex(m.Rejected, 'LOCAL_TRANSPORT_BRIDGE'):
            self.adapter.poll('a')
        with self.assertRaisesRegex(m.Rejected, 'PENDING'):
            self.run_one('b')
        summary = next(r['data'] for r in self.adapter.ledger.events if r['kind'] == 'transport_summary')
        self.assertFalse(summary['record_file_read'])
        self.assertFalse((self.path / summary['summary']['record_file']).exists())

    def test_large_inspect_summary_has_explicit_boundary_error(self):
        tool = ToolFixture('owner-A', self.path)
        tool.production_summary = True
        tool.mutate = lambda action, value: {**value, 'padding': 'x' * 25000}
        with self.assertRaisesRegex(m.Rejected, 'LOCAL_TRANSPORT_BRIDGE'):
            m.Adapter('owner-A', 'bf_design', tool, self.path / 'summary-ledger')

    def test_error_envelope_and_malformed_json_are_not_success(self):
        for value in [{'error': 'synthetic'}, {'isError': True, 'content': [{'type': 'text', 'text': '{}'}]},
                      {'content': [{'type': 'text', 'text': '{bad-json'}]}]:
            self.adapter.tool = lambda args, v=value: v
            with self.subTest(value=value), self.assertRaises((m.Rejected, json.JSONDecodeError)):
                self.adapter.read_skill()

    def node_reply(self, value):
        source = (REPO / 'pi-bf-aiot/packages/bf-agent/src/chat-product.ts').read_text()
        reply = source[source.index('const reply ='):source.index('const files =')]
        reply = reply.replace(': any', '').replace(' as const', '')
        script = ("const fs=require('fs'),path=require('path'),crypto=require('crypto');"
                  "const cwd=process.argv[1]; const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');"
                  + reply + "process.stdout.write(JSON.stringify(reply(JSON.parse(fs.readFileSync(0,'utf8')))));" )
        return json.loads(subprocess.run(['node', '-e', script, str(self.path)],
            input=json.dumps(value), text=True, capture_output=True, check=True).stdout)

    def test_real_node_reply_full_lifecycle_and_numeric_identity(self):
        self.adapter.close()
        self.adapter = m.Adapter('owner-A', 'bf_design', lambda args: self.node_reply(self.tool(args)), self.path / 'node-ledger')
        self.assertEqual(m.digest(self.adapter.task), self.tool.binding['task_hash'])
        self.run_one()
        self.finish()
        proof = self.adapter.submit('a', 'fixture selection')
        self.assertFalse(proof['scientific_success'])

    def test_real_node_reply_summary_is_explicitly_unsupported(self):
        self.adapter.tool = lambda args: self.node_reply(self.tool(args))
        self.run_one()
        self.tool.complete('a', padding='x' * 25000)
        with self.assertRaisesRegex(m.Rejected, 'LOCAL_TRANSPORT_BRIDGE'):
            self.adapter.poll('a')
        self.assertTrue(list((self.path / 'tool-records').glob('*.json')))
        self.assertFalse(next(e for e in self.adapter.ledger.events if e['kind'] == 'transport_summary')['data']['record_file_read'])

    def test_wire_numeric_equivalence_does_not_admit_boolean_or_changed_task(self):
        for replacement in [True, 49, '48']:
            binding = copy.deepcopy(self.tool.binding)
            binding['task']['baseline']['mechanical']['gap_mm'] = replacement
            with self.assertRaisesRegex(m.Rejected, 'TASK_IDENTITY'):
                self.adapter._binding(binding)

    def test_returned_prompt_task_and_job_cannot_mutate_state_or_budget(self):
        self.adapter.activate()['shared']['task']['baseline']['mechanical']['opening_s'] = 999
        self.adapter.task['baseline']['mechanical']['opening_s'] = 888
        job = self.run_one()
        job['parameters']['candidate']['mechanical']['opening_s'] = 777
        self.assertEqual(self.adapter.task['baseline']['mechanical']['opening_s'], 2)
        self.assertEqual(self.adapter.operations['a']['candidate']['mechanical']['opening_s'], 2)
        self.assertEqual(len(self.adapter.operations), 1)
        self.finish()

    def test_returned_submission_cannot_rewrite_disk_or_idempotent_selection(self):
        self.run_one()
        self.finish()
        proof = self.adapter.submit('a', 'original')
        original = (self.path / 'ledger/events.jsonl').read_bytes()
        proof['receipt']['rationale'] = 'changed'
        proof['scientific_success'] = True
        with self.assertRaisesRegex(m.Rejected, 'SUBMISSION_IMMUTABLE'):
            self.adapter.submit('a', 'changed')
        self.assertFalse(self.adapter.submit('a', 'original')['scientific_success'])
        self.assertEqual(self.tool.submission['rationale'], 'original')
        self.assertEqual((self.path / 'ledger/events.jsonl').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
