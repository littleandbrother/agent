import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from bfworld.agentlab.literature_acceptance import evaluate


class DigitalAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'campaign/reviews/P01').mkdir(parents=True)
        for name in ('result.json', 'issue.json'):
            (self.root / name).write_text('{}')
        self.scope = {'paper': 'P01', 'owner': 'pi-original', 'scope': 'complete-digital-system',
                      'review_roots': ['campaign/reviews/P01'],
                      'required_gates': [{'id': 'interfaces'}, {'id': 'mission'}]}
        self.current = {'paper': 'P01', 'owner': 'pi-original', 'result_path': 'result.json',
                        'live_assembly_matches': True,
                        'result_sha256': self.hash('result.json'), 'delivery_integrity': {'status': 'PASS'},
                        'evaluation': {'status': 'PASS', 'native_checks': [{'job_id': 'eng-a', 'project_sha256': 'abc'}]}}
        self.binding = [{'job_id': 'eng-a', 'project_sha256': 'abc'}]
        self.evidence = [{'paper': 'P01', 'owner': 'pi-original', 'actor': 'independent-checker',
                          'gate_id': gate, 'status': 'PASS', 'created': 2, 'bindings': self.binding,
                          'artifact': None}
                         for gate in ('interfaces', 'mission')]
        self.write_evidence()
        self.issue = {'paper': 'P01', 'owner': 'pi-original', 'id': 'wrong-pin', 'gate_id': 'interfaces',
                      'created': 1, 'finding_status': 'FAIL', 'bindings': self.binding,
                      'artifact': {'path': 'issue.json', 'sha256': self.hash('issue.json')}}

    def hash(self, name):
        return hashlib.sha256((self.root / name).read_bytes()).hexdigest()

    def write_evidence(self):
        for i, row in enumerate(self.evidence):
            name = f'campaign/reviews/P01/gate-{i}.json'
            body = {k: v for k, v in row.items() if k != 'artifact'}
            body['schema_version'] = 'bf-paper-digital-gate-review-v1'
            (self.root / name).write_text(json.dumps(body))
            row['artifact'] = {'path': name, 'sha256': self.hash(name)}

    def run_gate(self, evidence=None, issues=()):
        return evaluate(self.root, self.scope, self.current, self.evidence if evidence is None else evidence, issues)

    def test_all_required_independent_gates_grant_digital_only(self):
        result = self.run_gate()
        self.assertTrue(result['full_product_passed'])
        self.assertFalse(result['physical_verified'])
        self.assertFalse(result['agent_improvement_proven'])

    def test_file_gate_alone_cannot_grant_product(self):
        r = self.run_gate([])
        self.assertTrue(r['stage_delivery_passed'])
        self.assertFalse(r['full_product_passed'])

    def test_unclosed_failure_overrides_file_pass(self):
        r = self.run_gate(issues=[self.issue])
        self.assertEqual(r['digital_engineering_status'], 'REPAIR_REQUIRED')

    def test_changed_job_requires_recheck_not_silent_closure(self):
        self.current['evaluation']['native_checks'][0]['project_sha256'] = 'changed'
        r = self.run_gate(issues=[self.issue])
        self.assertEqual(r['issues'][0]['state'], 'RECHECK_REQUIRED')
        self.assertFalse(r['full_product_passed'])

    def test_explicit_independent_same_scope_closure(self):
        self.evidence[0]['resolves'] = ['wrong-pin']
        self.write_evidence()
        self.assertTrue(self.run_gate(issues=[self.issue])['full_product_passed'])

    def test_new_version_can_close_old_issue_only_with_independent_recheck(self):
        self.current['evaluation']['native_checks'][0]['project_sha256'] = 'new'
        for e in self.evidence:
            e['bindings'] = [{'job_id': 'eng-a', 'project_sha256': 'new'}]
        self.evidence[0]['resolves'] = ['wrong-pin']
        self.write_evidence()
        self.assertEqual(self.run_gate(issues=[self.issue])['issues'][0]['state'], 'CLOSED')

    def test_wrong_owner_evidence_rejected(self):
        self.evidence[0]['owner'] = 'other'
        self.assertFalse(self.run_gate()['full_product_passed'])

    def test_participant_self_award_rejected(self):
        self.evidence[0]['actor'] = 'Pi report'
        self.assertFalse(self.run_gate()['full_product_passed'])

    def test_hash_change_rejected(self):
        (self.root / self.evidence[0]['artifact']['path']).write_text('{"changed":true}')
        self.assertFalse(self.run_gate()['full_product_passed'])

    def test_current_seal_tamper_rejected(self):
        (self.root / 'result.json').write_text('tamper')
        self.assertEqual(self.run_gate()['file_integrity'], 'STALE')

    def test_assembly_change_blocks_whole_product(self):
        self.current['live_assembly_matches'] = False
        self.assertFalse(self.run_gate()['full_product_passed'])

    def test_report_change_invalidates_functional_recheck(self):
        p = self.root / 'runtime/participants/pi-original/analysis.py'
        p.parent.mkdir(parents=True)
        p.write_text('old')
        self.evidence[0]['supporting_sources'] = [{'path': 'analysis.py', 'sha256': hashlib.sha256(b'old').hexdigest()}]
        self.write_evidence()
        p.write_text('new')
        self.assertFalse(self.run_gate()['full_product_passed'])

    def test_later_negative_check_reopens_gate(self):
        self.evidence.append({**self.evidence[0], 'status': 'FAIL', 'created': 3})
        self.write_evidence()
        self.assertEqual(self.run_gate()['digital_engineering_status'], 'REPAIR_REQUIRED')

    def test_unknown_status_cannot_be_pass(self):
        self.evidence[0]['status'] = 'COMPLETED'
        self.assertFalse(self.run_gate()['full_product_passed'])

    def test_malformed_but_hash_bound_review_cannot_grant_pass(self):
        p = self.root / self.evidence[0]['artifact']['path']
        p.write_text('{invalid-json')
        self.evidence[0]['artifact']['sha256'] = self.hash(str(p.relative_to(self.root)))
        result = self.run_gate()
        self.assertFalse(result['full_product_passed'])
        self.assertEqual(result['rejected_evidence'][0]['reason'], 'EVIDENCE_CONTENT_MISMATCH')

    def test_changed_underlying_review_cannot_survive_valid_wrapper(self):
        name = 'campaign/reviews/P01/raw-review.json'
        (self.root / name).write_text('{"status":"PASS"}')
        self.evidence[0]['source_review'] = {'path': name, 'sha256': self.hash(name)}
        self.write_evidence()
        (self.root / name).write_text('{"status":"FAIL"}')
        result = self.run_gate()
        self.assertFalse(result['full_product_passed'])
        self.assertEqual(result['rejected_evidence'][0]['reason'], 'SOURCE_REVIEW_HASH_MISMATCH')

    def test_later_failure_reopens_previously_closed_issue(self):
        self.evidence[0]['resolves'] = ['wrong-pin']
        self.evidence.append({**self.evidence[0], 'status': 'FAIL', 'created': 3})
        self.write_evidence()
        result = self.run_gate(issues=[self.issue])
        self.assertEqual(result['issues'][0]['state'], 'OPEN')
        self.assertEqual(result['digital_engineering_status'], 'REPAIR_REQUIRED')

    def test_report_wrapper_cannot_change_actual_review_status(self):
        self.evidence[0]['status'] = 'FAIL'
        self.write_evidence()
        self.evidence[0]['status'] = 'PASS'
        self.assertFalse(self.run_gate()['full_product_passed'])

    def test_participant_directory_cannot_supply_independent_review(self):
        p = self.root / 'runtime/participants/pi-original/review.json'
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({**self.evidence[0], 'schema_version': 'bf-paper-digital-gate-review-v1'}))
        self.evidence[0]['artifact'] = {'path': str(p.relative_to(self.root)), 'sha256': self.hash(str(p.relative_to(self.root)))}
        self.assertFalse(self.run_gate()['full_product_passed'])

    def test_cross_owner_issue_rejected(self):
        self.issue['owner'] = 'wrong'
        with self.assertRaises(ValueError):
            self.run_gate(issues=[self.issue])

    def test_live_input_change_invalidates_old_pass(self):
        p = self.root / 'runtime/participants/pi-original/source.c'
        p.parent.mkdir(parents=True)
        p.write_text('old')
        self.current['evaluation']['native_checks'][0]['project_source_sha256'] = {'source.c': hashlib.sha256(b'old').hexdigest()}
        p.write_text('new')
        self.assertFalse(self.run_gate()['full_product_passed'])


if __name__ == '__main__':
    unittest.main()
