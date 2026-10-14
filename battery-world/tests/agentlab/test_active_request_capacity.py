import copy
import unittest
from bfworld.agentlab.context import project_interactive
from bfworld.agentlab.model_profile import ACTIVE, ENGINEERING, OUTPUT64, qualified_owner


class ActiveRequestCapacityTests(unittest.TestCase):
    def test_complete_active_tool_exchange_fits_without_truncating_user_or_protocol(self):
        # Synthetic opaque reasoning bytes; no private model content is inspected.
        payload={'model':'deepseek-flash','messages':[
            {'role':'system','content':'fixed instruction '*2600},
            {'role':'user','content':'current requirement '*4600},
            {'role':'assistant','content':'','reasoning_content':'opaque '*22000,
             'tool_calls':[{'id':'active-call','type':'function','function':{'name':'read','arguments':'{"path":"current.json"}'}}]},
            {'role':'tool','tool_call_id':'active-call','content':'current verified facts'}]}
        original=copy.deepcopy(payload)
        _,old=project_interactive(payload,request_bytes=OUTPUT64['request_bytes'],target_bytes=OUTPUT64['target_bytes'])
        current,audit=project_interactive(payload,request_bytes=ACTIVE['request_bytes'],target_bytes=ACTIVE['target_bytes'])
        self.assertFalse(old['fits'])
        self.assertTrue(audit['fits'])
        self.assertEqual(old['projected_bytes'],audit['projected_bytes'])
        self.assertEqual(payload,current)
        self.assertEqual(original,payload)
        self.assertEqual(ENGINEERING['target_bytes'],ACTIVE['target_bytes'])

    def test_capacity_override_is_only_for_the_explicit_original_owner(self):
        qualification={'original_owner_output_profiles':{'original-p01':ACTIVE['version']}}
        self.assertEqual(ACTIVE,qualified_owner(OUTPUT64,qualification,'original-p01'))
        self.assertEqual(ENGINEERING,qualified_owner(ENGINEERING,qualification,'another-paper'))
        for key in ('thinking','reasoning_effort','max_output_tokens','target_bytes'):
            self.assertEqual(OUTPUT64[key],ACTIVE[key])


if __name__=='__main__':unittest.main()
