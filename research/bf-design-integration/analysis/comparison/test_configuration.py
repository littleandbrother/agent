"""All declarations below are synthetic; no participant results."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
import contextlib
import io
from unittest.mock import patch
import check_configuration as c


def pair():
    rules=json.loads(c.RULE_PATH.read_text());protocol=json.loads((c.ROOT/'contracts/PROTOCOL.json').read_text())
    rows=[]
    for i,profile in enumerate(('strong_generic','bf_design')):
        ids={k:c.digest({'synthetic':k}) for k in rules['equal_identity_fields']}
        ids.update(task_hash=protocol['normalized_task_hash'],initial_candidate_hash=c.digest(protocol['common_facts_and_freedoms']['baseline']))
        r={'run_id':'synthetic-run-'+str(i),'owner':'synthetic-owner-'+str(i),'profile':profile,
           'protocol_hash':protocol['protocol_hash'],'rules_sha256':hashlib.sha256(c.RULE_PATH.read_bytes()).hexdigest(),
           'method_policy_sha256':c.expected_method_hash(protocol,profile),'max_candidates':3,'identities':ids,
           'budgets':{k:0 for k in rules['equal_budget_fields']}}
        rows.append({'source_id':'synthetic-source-'+str(i),'sha256':c.digest(r),'record':r})
    return rows


def seal(rows):
    for e in rows:e['sha256']=c.digest(e['record'])
    return rows


class ConfigurationTests(unittest.TestCase):
    def test_matching_synthetic_declarations_not_scientific_admission(self):
        r=c.check(pair());self.assertEqual(r['status'],'MATCHED_DECLARATIONS_ONLY')
        self.assertEqual(r['changed_factors'],['R','Q'])
        for k in ('actual_delivery_verified','actual_budget_enforcement_verified','pre_run_seal_timing_verified','execution_authorized','formal_method_comparison'):self.assertFalse(r[k])

    def test_missing_every_identity_is_unknown(self):
        for field in json.loads(c.RULE_PATH.read_text())['equal_identity_fields']:
            p=pair();del p[1]['record']['identities'][field]
            with self.subTest(field=field):self.assertEqual(c.check(seal(p))['status'],'UNKNOWN')

    def test_unknown_budget_is_not_zero(self):
        p=pair();p[1]['record']['budgets']['model_cost_microusd']=None
        self.assertEqual(c.check(seal(p))['status'],'UNKNOWN')

    def test_unequal_budget_or_information_incomparable(self):
        for group,key,value in [('budgets','model_tokens',1),('identities','initial_information_sha256','0'*64),('identities','cache_policy_sha256','1'*64)]:
            p=pair();p[1]['record'][group][key]=value
            with self.subTest(field=key):self.assertEqual(c.check(seal(p))['status'],'INCOMPARABLE')

    def test_same_profile_is_not_rq_comparison(self):
        p=pair();p[1]['record']['profile']=p[0]['record']['profile'];p[1]['record']['method_policy_sha256']=p[0]['record']['method_policy_sha256']
        self.assertEqual(c.check(seal(p))['status'],'INCOMPARABLE')

    def test_quota_increase_and_negative_budget_blocked(self):
        p=pair();p[1]['record']['max_candidates']=4
        self.assertEqual(c.check(seal(p))['status'],'BLOCKED')
        p=pair();p[1]['record']['budgets']['native_wall_s']=-1
        self.assertEqual(c.check(seal(p))['status'],'BLOCKED')

    def test_same_owner_and_run_alias_blocked(self):
        for field in ('owner','run_id'):
            p=pair();p[1]['record'][field]=p[0]['record'][field]
            self.assertEqual(c.check(seal(p))['status'],'BLOCKED')

    def test_task_method_or_rule_drift_blocked(self):
        for key in ('method_policy_sha256','rules_sha256','protocol_hash'):
            p=pair();p[1]['record'][key]='0'*64
            self.assertEqual(c.check(seal(p))['status'],'BLOCKED')
        p=pair();p[1]['record']['identities']['task_hash']='0'*64
        self.assertEqual(c.check(seal(p))['status'],'BLOCKED')

    def test_results_or_architecture_fields_blocked(self):
        for key in ('result','architecture','scientific_score'):
            p=pair();p[1]['record'][key]='SYNTHETIC PRIVATE MARKER'
            r=c.check(seal(p));self.assertEqual(r['status'],'BLOCKED');self.assertNotIn('PRIVATE',json.dumps(r))

    def test_tamper_and_bad_shapes_fail_closed(self):
        p=pair();p[1]['sha256']='0'*64
        for value in (p,None,{},['PRIVATE',[]]):
            self.assertEqual(c.check(value)['status'],'BLOCKED')

    def test_inputs_and_existing_contracts_unchanged(self):
        p=pair();before=copy.deepcopy(p)
        paths=[c.RULE_PATH,c.ROOT/'contracts/PROTOCOL.json',c.ROOT/'contracts/OWNERSHIP.json',c.ROOT/'analysis/trajectory/INPUT-CONTRACT.json']
        raw=[x.read_bytes() for x in paths];c.check(p)
        self.assertEqual(p,before);self.assertEqual(raw,[x.read_bytes() for x in paths])

    def assert_rules_failure_private(self, path, error=None):
        marker='SYNTHETIC_PRIVATE_RULES_MARKER'
        stdout,stderr=io.StringIO(),io.StringIO()
        with patch.object(c,'RULE_PATH',path), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            if error is None:
                result=c.check([])
            else:
                with patch.object(Path,'read_bytes',side_effect=error):
                    result=c.check([])
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['issues'],['INVALID_OR_UNBOUND_DECLARATION'])
        self.assertIsNone(result['rules_sha256'])
        self.assertNotIn(marker,json.dumps(result)+stdout.getvalue()+stderr.getvalue())
        self.assertEqual(stdout.getvalue()+stderr.getvalue(),'')

    def test_missing_rules_fail_closed_without_path(self):
        with tempfile.TemporaryDirectory() as d:
            self.assert_rules_failure_private(Path(d)/'SYNTHETIC_PRIVATE_RULES_MARKER.json')

    def test_unreadable_rules_fail_closed_without_path(self):
        # Inject PermissionError: chmod alone is unreliable under privileged CI.
        path=Path('/SYNTHETIC_PRIVATE_RULES_MARKER.json')
        self.assert_rules_failure_private(path,PermissionError(13,'permission denied',str(path)))

    def test_symlink_loop_rules_fail_closed_without_path(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'SYNTHETIC_PRIVATE_RULES_MARKER.json';path.symlink_to(path)
            self.assert_rules_failure_private(path)

if __name__=='__main__':unittest.main()
