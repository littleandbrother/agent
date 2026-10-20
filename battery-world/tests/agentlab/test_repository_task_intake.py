import copy
import json
import unittest

import test_design_repository as fixtures
from test_design_repository import OWNER
from bfworld.agentlab.design_lab.repository_task_intake import example, prompt, schema, validate


def proposal():
    value = example()
    value['requirements'] = [{'text': '检查电源', 'source_quote': '检查电源'}]
    value['plan'] = [dict(value['plan'][0], action=step) for step in ('读取', '分析', '核对')]
    return value


class TaskIntakeTests(unittest.TestCase):
    setUp = fixtures.RepositoryCase.setUp

    def test_assessment_before_project_creation_has_no_write_side_effect(self):
        self.assertIsNone(self.repo.bound(OWNER))
        result = self.repo.handle(OWNER, {'action': 'repository_task_assess',
            'request': '帮我检查电源', 'assessment': json.dumps(proposal())})
        self.assertEqual('INPUT_REQUIRED', result['state'])
        self.assertFalse(result['requirements_frozen'])
        self.assertIsNone(self.repo.bound(OWNER))

    def test_invalid_claim_source_cannot_be_frozen_as_requirement(self):
        value = proposal(); value['requirements'][0]['source_quote'] = '必须使用 nRF52832'
        with self.assertRaisesRegex(ValueError, 'SOURCE_MISMATCH'):
            validate('帮我检查电源', value)

    def test_nested_schema_wrapper_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ASSESSMENT_FIELDS'):
            validate('检查电源', {'fields': proposal()})

    def test_schema_and_model_instructions_share_example(self):
        contract = self.repo.handle(OWNER, {'action': 'repository_task_assessment_schema'})
        self.assertEqual(prompt(), contract['prompt'])
        self.assertIn(json.dumps(contract['example'], ensure_ascii=False), prompt())
        self.assertEqual(set(contract['fields']), set(contract['example']))

    def test_malformed_scope_or_plan_is_rejected(self):
        changes = [('domains', [{}]), ('scope', 'P01'), ('plan', []), ('feasibility', 'proven')]
        for field, value in changes:
            p = proposal(); p[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate('检查电源', p)

    def test_conflict_and_ready_are_distinct_without_mutating_input(self):
        p = proposal(); p['missing_inputs'] = []
        before = copy.deepcopy(p)
        self.assertEqual('READY_FOR_CAPABILITY_MATCH', validate('检查电源', p)['state'])
        self.assertEqual(before, p)
        p['feasibility'] = 'conflict'
        self.assertEqual('REQUIREMENTS_CONFLICT', validate('检查电源', p)['state'])

    def test_missing_source_can_defer_domain_assignment(self):
        p = proposal(); p.update(domains=[], scope='unspecified')
        self.assertEqual('INPUT_REQUIRED', validate('检查电源', p)['state'])
        p['missing_inputs'] = []
        with self.assertRaisesRegex(ValueError, 'UNSPECIFIED_SCOPE_REQUIRES_INPUT'):
            validate('检查电源', p)


if __name__ == '__main__': unittest.main()
