import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from bfworld.agentlab.store import Store
from bfworld.agentlab.simulation_tasks import load_task
from bfworld.agentlab.simulation_chain.contracts import validate,write_json
from bfworld.agentlab.research_methods import record


class RevisionEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.binding=load_task();self.store=Store(self.root/'state')
        self.job={'status':'SUCCEEDED','task_binding':self.binding}
        self.spec=validate({'circuit':{'cin_uF':22}})
        write_json(self.root/'design-spec.json',self.spec)
        write_json(self.root/'result.json',{'task_evaluation':{'task_hash':self.binding['task_hash'],'nominal_task_status':'unsatisfied'}})
        def get(owner,key):
            if owner!='owner' or key!='job':raise PermissionError('ENGINEERING_JOB_NOT_FOUND')
            return self.job
        self.eng=SimpleNamespace(store=self.store,tasks=SimpleNamespace(binding=lambda owner:self.binding),
            get=get,artifact=lambda owner,key,name:self.root/name,event=lambda *args:None)
        self.body={'job_id':'job','requested_kind':'parameter_refinement','rationale':'Change capacitor','falsifier':'No energy reaches the load'}
    def tearDown(self):self.tmp.cleanup()

    def test_diff_comes_from_actual_artifact_and_no_op_is_not_revision(self):
        result=record(self.eng,'owner',{**self.body,'claimed_changed_fields':['mechanical.gap_mm']})
        self.assertEqual(['circuit.cin_uF'],result['actual_changed_fields'])
        self.assertFalse(result['scientific_success'])
        write_json(self.root/'design-spec.json',self.binding['task']['baseline'])
        self.assertEqual('no_op',record(self.eng,'owner',self.body)['implementation_status'])

    def test_architecture_proposal_never_counts_as_executed(self):
        body={**self.body,'job_id':None,'requested_kind':'architecture_recomposition'}
        value=record(self.eng,'owner',body)
        self.assertEqual('proposed_unsupported',value['implementation_status'])
        self.assertFalse(value['architecture_executed'])

    def test_cross_owner_and_old_task_are_rejected(self):
        with self.assertRaises(PermissionError):record(self.eng,'other',self.body)
        self.job['task_binding']={'task_hash':'different task'}
        with self.assertRaisesRegex(ValueError,'JOB_TASK_MISMATCH'):record(self.eng,'owner',self.body)

    def test_result_task_mismatch_and_protected_candidate_are_rejected(self):
        write_json(self.root/'result.json',{'task_evaluation':{'task_hash':'different task'}})
        with self.assertRaisesRegex(ValueError,'RESULT_TASK_MISMATCH'):record(self.eng,'owner',self.body)
        value=copy.deepcopy(self.spec);value['circuit']['initial_vin_V']=3
        write_json(self.root/'design-spec.json',value)
        with self.assertRaisesRegex(ValueError,'TASK_PROTECTED_FIELD'):record(self.eng,'owner',self.body)

if __name__=='__main__':unittest.main()
