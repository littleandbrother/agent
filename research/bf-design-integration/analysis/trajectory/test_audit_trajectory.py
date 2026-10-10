"""Synthetic records only; no model, service or native runtime."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import audit_trajectory as a

HERE=Path(__file__).resolve().parent

def fixture():
    p=json.loads((a.ROOT/'contracts/PROTOCOL.json').read_text())
    t={'schema':'bf-method-behavior-input-v1','owner':'synthetic-owner','protocol_hash':p['protocol_hash'],
       'task_hash':p['normalized_task_hash'],'evidence_kind':'synthetic','sources':[]}
    def add(id,kind,data):
        r={'seq':len(t['sources']),'owner':t['owner'],'kind':kind,'data':data}
        t['sources'].append({'id':id,'sha256':a.digest(r),'record':r})
    spec=copy.deepcopy(p['common_facts_and_freedoms']['baseline']);ih=a.digest('synthetic instruction, not a delivered real prompt')
    add('config','configuration',{'profile':'bf_design','instruction_sha256':ih,'loaded':True})
    add('delivery1','instruction_delivery',{'config_id':'config','request_id':'request1','instruction_sha256':ih,'delivered':True,'receipt_id':'synthetic-delivery1'})
    add('action1','candidate_action',{'operation_id':'op1','request_id':'request1','candidate':spec,'candidate_hash':a.digest(spec),'job_id':'eng-a','dispatch':'acknowledged','revision_id':None})
    result={'job_id':'eng-a','operation_id':'op1','owner':t['owner'],'task_hash':t['task_hash'],'candidate_hash':a.digest(spec),'status':'FAILED','artifact_sha256':a.digest('synthetic missing external artifact')}
    add('terminal1','terminal_result',{'action_id':'action1','job_id':'eng-a','result':result,'result_sha256':a.digest(result)})
    add('feedback1','feedback_available',{'terminal_id':'terminal1','request_id':'request2','delivery_receipt_id':'synthetic-feedback1','available':True})
    add('delivery2','instruction_delivery',{'config_id':'config','request_id':'request2','instruction_sha256':ih,'delivered':True,'receipt_id':'synthetic-delivery2'})
    spec2=copy.deepcopy(spec);spec2['circuit']['cin_uF']=22
    add('revision2','revision',{'previous_action_id':'action1','feedback_id':'feedback1','request_id':'request2','next_operation_id':'op2','candidate_hash':a.digest(spec2),'kind':'numeric'})
    add('action2','candidate_action',{'operation_id':'op2','request_id':'request2','candidate':spec2,'candidate_hash':a.digest(spec2),'job_id':'eng-b','dispatch':'unknown','revision_id':'revision2'})
    add('developer-patch','h_change',{'authorship':'developer','artifact_sha256':a.digest('synthetic patch'),'generation_request_id':None,'execution_receipt_id':None})
    return t

def seal(t):
    for i,s in enumerate(t['sources']):
        s['record']['seq']=i;s['sha256']=a.digest(s['record'])
    return t

class AuditTests(unittest.TestCase):
    def test_synthetic_levels_and_unknowns(self):
        report=a.audit(fixture())
        self.assertEqual(report['distinct_operations'],2)
        self.assertEqual(report['levels']['feedback_linked_numeric_revision']['records'][0]['changes'],{'circuit.cin_uF':{'before':47.,'after':22}})
        self.assertEqual(report['cost']['status'],'unknown')
        self.assertEqual(report['manual_intervention']['status'],'unknown')
        self.assertFalse(report['h_changes'][0]['executable_H1_verified'])
        self.assertEqual(report['method_benefit'],'not established')
        self.assertFalse(report['levels']['terminal_result_bound']['records'][0]['external_artifact_hash_verified'])

    def test_configuration_alone_is_not_delivery(self):
        t=fixture();t['sources']=t['sources'][:1]
        r=a.audit(t)
        self.assertEqual(r['levels']['configuration_loaded']['status'],'recorded')
        self.assertEqual(r['levels']['instruction_delivered']['status'],'unknown')
        self.assertEqual(r['levels']['candidate_action_recorded']['status'],'unknown')

    def test_feedback_availability_not_revision(self):
        t=fixture();t['sources']=t['sources'][:5]
        r=a.audit(t)
        self.assertEqual(r['levels']['feedback_available']['status'],'recorded')
        self.assertEqual(r['levels']['feedback_linked_numeric_revision']['status'],'unknown')

    def test_tampered_source_hash(self):
        t=fixture();t['sources'][0]['record']['data']['loaded']=False
        with self.assertRaisesRegex(ValueError,'SOURCE_ID_HASH'):a.audit(t)

    def test_future_reference_and_owner_drift(self):
        t=fixture();t['sources'][1]['record']['data']['config_id']='later'
        with self.assertRaisesRegex(ValueError,'FUTURE_REFERENCE'):a.audit(seal(t))
        t=fixture();t['sources'][1]['record']['owner']='other'
        with self.assertRaisesRegex(ValueError,'CHRONOLOGY_OWNER'):a.audit(seal(t))

    def test_unlinked_request_rejected(self):
        t=fixture();t['sources'][7]['record']['data']['request_id']='other'
        with self.assertRaisesRegex(ValueError,'REVISION_ACTION_BINDING'):a.audit(seal(t))

    def test_protected_change_and_architecture_rejected(self):
        t=fixture();d=t['sources'][7]['record']['data'];d['candidate']['solver']['reltol']=.1;d['candidate_hash']=a.digest(d['candidate'])
        with self.assertRaisesRegex(ValueError,'PROTECTED_FIELD'):a.audit(seal(t))
        t=fixture();t['sources'][6]['record']['data']['kind']='architecture'
        with self.assertRaisesRegex(ValueError,'ARCHITECTURE_UNSUPPORTED'):a.audit(seal(t))

    def test_retry_keeps_quota_and_conflicting_candidate_rejected(self):
        t=fixture();retry=copy.deepcopy(t['sources'][2]);retry['id']='retry';t['sources'].insert(3,retry)
        self.assertEqual(a.audit(seal(t))['distinct_operations'],2)
        retry['record']['data']['candidate']['circuit']['cin_uF']=10
        retry['record']['data']['candidate_hash']=a.digest(retry['record']['data']['candidate'])
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):a.audit(seal(t))

    def test_fourth_operation_and_job_alias_rejected(self):
        t=fixture()
        for n in (3,4):
            x=copy.deepcopy(t['sources'][2]);x['id']='extra'+str(n);x['record']['data'].update(operation_id='op'+str(n),job_id='eng-'+str(n));t['sources'].append(x)
        with self.assertRaisesRegex(ValueError,'CANDIDATE_QUOTA'):a.audit(seal(t))
        t=fixture();t['sources'][7]['record']['data']['job_id']='eng-a'
        with self.assertRaisesRegex(ValueError,'JOB_OPERATION_CONFLICT'):a.audit(seal(t))

    def test_terminal_wrong_candidate_rejected(self):
        t=fixture();d=t['sources'][3]['record']['data'];d['result']['candidate_hash']='0'*64;d['result_sha256']=a.digest(d['result'])
        with self.assertRaisesRegex(ValueError,'TERMINAL_BINDING'):a.audit(seal(t))

    def test_unavailable_feedback_cannot_prove_linkage(self):
        t=fixture();t['sources'][4]['record']['data'].update(available=False,delivery_receipt_id=None)
        self.assertEqual(a.audit(seal(t))['levels']['feedback_linked_numeric_revision']['status'],'unknown')

    def test_participant_claim_is_not_executable_h1(self):
        t=fixture();t['sources'][-1]['record']['data'].update(authorship='participant',generation_request_id='request2',execution_receipt_id='unverified-execution')
        self.assertFalse(a.audit(seal(t))['h_changes'][0]['executable_H1_verified'])

    def test_output_preservation_and_input_immutability(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'input.json';out=Path(d)/'new.json';src.write_text(json.dumps(fixture()));before=src.read_bytes()
            cmd=[sys.executable,'-B',a.__file__,'--input',str(src),'--out',str(out)]
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            output=out.read_bytes()
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
            self.assertEqual(out.read_bytes(),output);self.assertEqual(src.read_bytes(),before)
            out.unlink();out.symlink_to(src)
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
            self.assertEqual(src.read_bytes(),before)

    def test_pre_feedback_candidate_retry_cannot_gain_revision_credit(self):
        t=fixture();early=copy.deepcopy(t['sources'][7]);early['id']='early-op2'
        early['record']['data'].update(revision_id=None,request_id='request1')
        t['sources'].insert(3,early)  # before delayed op1 result and feedback
        with self.assertRaisesRegex(a.AuditError,'RETRY_PROVENANCE_CHANGED'):
            a.audit(seal(t))

    def test_retry_same_revision_has_no_additional_linkage(self):
        t=fixture();retry=copy.deepcopy(t['sources'][7]);retry['id']='retry-op2';t['sources'].append(retry)
        report=a.audit(seal(t))
        self.assertEqual(len(report['levels']['feedback_linked_numeric_revision']['records']),1)
        self.assertEqual(report['actions'][-1]['first_source'],'action2')
        self.assertTrue(report['actions'][-1]['retry'])

    def test_changed_revision_label_or_removed_label_is_blocked(self):
        for relabel in (None,'revision3'):
            t=fixture();revision=copy.deepcopy(t['sources'][6]);revision['id']='revision3';t['sources'].append(revision)
            retry=copy.deepcopy(t['sources'][7]);retry['id']='retry-op2';retry['record']['data']['revision_id']=relabel;t['sources'].append(retry)
            with self.subTest(relabel=relabel),self.assertRaisesRegex(a.AuditError,'RETRY_PROVENANCE_CHANGED'):
                a.audit(seal(t))

    def test_delayed_terminal_cannot_be_backdated_into_revision(self):
        t=fixture();terminal=t['sources'].pop(3);t['sources'].append(terminal)
        with self.assertRaisesRegex(a.AuditError,'MISSING_OR_FUTURE_REFERENCE'):
            a.audit(seal(t))

    def run_private_input(self, raw, marker):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'input.json';out=Path(d)/'out.json';src.write_bytes(raw)
            result=subprocess.run([sys.executable,'-B',a.__file__,'--input',str(src),'--out',str(out)],capture_output=True,text=True)
            combined=result.stdout+result.stderr+(out.read_text() if out.exists() else '')
            self.assertNotIn(marker,combined)
            self.assertEqual(result.returncode,1)
            report=json.loads(out.read_text());self.assertEqual(report['status'],'BLOCKED')
            self.assertRegex(report['error_code'],r'^[A-Z_]+$')

    def test_all_reference_fields_never_echo_private_marker(self):
        fields=[(1,'config_id'),(7,'revision_id'),(3,'action_id'),(4,'terminal_id'),
                (6,'previous_action_id'),(6,'feedback_id')]
        for seq,key in fields:
            for marker in ('SYNTHETIC PRIVATE TRANSCRIPT MARKER','PRIVATE_TRANSCRIPT_MARKER'):
                t=fixture();t['sources'][seq]['record']['data'][key]=marker
                with self.subTest(field=key,marker_type='spaces' if ' ' in marker else 'identifier'):
                    self.run_private_input(json.dumps(seal(t)).encode(),marker)

    def test_malformed_and_wrong_shape_inputs_do_not_echo_values(self):
        marker='SYNTHETIC PRIVATE MALFORMED MARKER'
        malformed=[('not-json '+marker).encode(),json.dumps({marker:'x'}).encode(),
                   json.dumps([marker]).encode(), ('"'+marker+'" trailing').encode(),b'\xff'+marker.encode()]
        t=fixture();t['sources'][1]['record']['data']['config_id']={marker:'x'}
        malformed.append(json.dumps(seal(t)).encode())
        t=fixture();t['sources'][0]['record']['kind']={marker:'x'}
        malformed.append(json.dumps(seal(t)).encode())
        for raw in malformed:
            with self.subTest(case=len(raw)):self.run_private_input(raw,marker)

    def test_cli_argument_and_path_errors_do_not_echo_private_values(self):
        marker='SYNTHETIC_PRIVATE_PATH_MARKER'
        r=subprocess.run([sys.executable,'-B',a.__file__,'--'+marker],capture_output=True,text=True)
        self.assertEqual(r.returncode,2);self.assertNotIn(marker,r.stdout+r.stderr)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out.json'
            r=subprocess.run([sys.executable,'-B',a.__file__,'--input',str(Path(d)/marker),'--out',str(out)],capture_output=True,text=True)
            self.assertEqual(r.returncode,1)
            self.assertNotIn(marker,r.stdout+r.stderr+out.read_text())

    def test_input_and_output_symlink_loops_do_not_echo_paths(self):
        marker='SYNTHETIC_PRIVATE_LOOP_MARKER'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);loop=root/marker;loop.symlink_to(loop)
            source=root/'input.json';source.write_text(json.dumps(fixture()))
            for input_path,output_path in [(loop,root/'new.json'),(source,loop/'new.json')]:
                with self.subTest(direction='input' if input_path==loop else 'output'):
                    r=subprocess.run([sys.executable,'-B',a.__file__,'--input',str(input_path),'--out',str(output_path)],capture_output=True,text=True)
                    self.assertEqual(r.returncode,2)
                    self.assertEqual(r.stderr,'CLI_ARGUMENT_ERROR\n')
                    self.assertNotIn(marker,r.stdout+r.stderr)
                    self.assertNotIn('Traceback',r.stdout+r.stderr)
            self.assertFalse((root/'new.json').exists())

    def test_missing_output_ancestors_still_allow_exclusive_creation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input.json';source.write_text(json.dumps(fixture()))
            out=root/'new'/'nested'/'report.json'
            r=subprocess.run([sys.executable,'-B',a.__file__,'--input',str(source),'--out',str(out)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0)
            self.assertEqual(json.loads(out.read_text())['status'],'RECORDED_EVIDENCE_ONLY')

    def test_committed_synthetic_fixture(self):
        self.assertEqual(fixture(),json.loads((HERE/'SYNTHETIC-INPUT.json').read_text()))
        self.assertEqual(a.audit(fixture()),json.loads((HERE/'SYNTHETIC-AUDIT.json').read_text()))

if __name__=='__main__':unittest.main()
