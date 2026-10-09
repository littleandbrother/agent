import json,sqlite3
from pathlib import Path
import tempfile
import unittest
from bfworld.agentlab.literature_campaign import (PAPERS,DISCIPLINES,register,projection,digest,display_digest,bound_file,owner_budget,evaluate_reconstruction)
from bfworld.agentlab.store import identity

class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'sources/P01/article-pages.json';self.source.parent.mkdir(parents=True)
        self.source.write_text(json.dumps([{'page':1,'text':'The node includes an nRF52832 microcontroller. The storage threshold is measured independently. No native PCB file is released.'}]))
        assets=[{'path':str(self.source.relative_to(self.root)),'sha256':digest(self.source)}]
        self.contract={'paper_id':'P01','source_identity':identity(assets),'assets':assets}
        self.report={'schema_version':'bf-paper-reconstruction-v1','paper_id':'P01','source_identity':identity(assets),'physical_verified':False,'full_product_passed':False,'dimensions':{k:{'status':'needs-information','available':'Documented experimental block','rebuild':'Reconstruct native implementation','independent_check':'Read native file using a separate checker'} for k in DISCIPLINES},'facts':[{'asset':assets[0]['path'],'locator':'page 1','quote':q,'claim':q} for q in ['The node includes an nRF52832 microcontroller.','The storage threshold is measured independently.','No native PCB file is released.']],'gaps':['Original board/module pin assignments unavailable.']}
    def test_ten_candidates_do_not_masquerade_as_ten_full_devices(self):
        self.assertEqual(len(PAPERS),10);self.assertEqual(sum(p['role']=='full-system-candidate' for p in PAPERS),5)
        packet=register(self.root);view=projection(self.root)
        self.assertEqual(view['accepted_full_products'],0);self.assertFalse(view['recursive_self_improvement_proven'])
        self.assertEqual(packet['budget']['scope'],'per-session/task')
    def test_source_snapshot_is_versioned(self):
        register(self.root);before=list((self.root/'campaign/versions').glob('*.json'))
        self.source.write_text(self.source.read_text()+' ');register(self.root)
        after=list((self.root/'campaign/versions').glob('*.json'));self.assertEqual(len(after),len(before)+1)
    def test_one_owners_cost_does_not_use_anothers_budget(self):
        rows=[{'id':'r1','owner':'a','status':'SETTLED','charged':29,'reserved':29},{'id':'r2','owner':'b','status':'SETTLED','charged':12,'reserved':12}]
        self.assertEqual(owner_budget(rows,'b')['remaining_usd'],18)
        self.assertFalse(owner_budget(rows,'b')['exhausted'])
        rows.append({'id':'r3','owner':'a','status':'UNKNOWN','reserved':1,'charged':0})
        self.assertTrue(owner_budget(rows,'a')['exhausted']);self.assertFalse(owner_budget(rows,'b')['exhausted'])
    def test_source_provenance_positive_and_negative_controls(self):
        self.assertEqual(evaluate_reconstruction(self.root,self.contract,self.root,self.report)['status'],'PASS')
        self.report['facts'][0]['quote']='An invented sensor value not in the source.'
        self.assertIn('QUOTE_NOT_IN_BOUND_SOURCE',evaluate_reconstruction(self.root,self.contract,self.root,self.report)['problems'])
    def test_self_awarded_acceptance_cannot_pass(self):
        self.report['full_product_passed']=True;self.report['physical_verified']=True
        r=evaluate_reconstruction(self.root,self.contract,self.root,self.report)
        self.assertIn('SELF_AWARDED_PRODUCT_PASS',r['problems']);self.assertIn('UNSUPPORTED_PHYSICAL_CLAIM',r['problems'])
    def test_missing_professional_dimension_fails(self):
        self.report['dimensions'].pop('pcb');self.assertIn('DISCIPLINE_COVERAGE',evaluate_reconstruction(self.root,self.contract,self.root,self.report)['problems'])
    def test_changed_source_or_escaped_path_rejected(self):
        self.source.write_text('changed')
        with self.assertRaises(ValueError):bound_file(self.root,'sources/P01/article-pages.json',self.contract['assets'][0]['sha256'])
        with self.assertRaises(ValueError):bound_file(self.root,'../other.json','0'*64)
    def test_projection_is_read_only(self):
        register(self.root);before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        projection(self.root);after={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()};self.assertEqual(before,after)
    def test_continuation_is_visible_without_overwriting_original_result(self):
        register(self.root);parent=self.root/'campaign/native-runs/P01-native'
        for folder,started,status in [(parent,1,'FAIL'),(parent/'continuations/turn-001',2,'PASS')]:
            folder.mkdir(parents=True);(folder/'attempt.json').write_text(json.dumps({'paper':'P01','owner':'pi-own','started':started}))
            (folder/'result.json').write_text(json.dumps({'paper':'P01','owner':'pi-own','evaluation':{'status':status},'artifacts':[]}))
        before=(parent/'result.json').read_bytes();view=projection(self.root)
        self.assertEqual(['FAIL','PASS'],[t['evaluation']['status'] for t in view['paper_tasks']])
        self.assertEqual(before,(parent/'result.json').read_bytes());self.assertEqual(0,view['accepted_full_products'])
    def test_metadata_cache_detects_changed_artifact(self):
        before=display_digest(self.source);self.source.write_text('changed source')
        self.assertNotEqual(before,display_digest(self.source))
    def test_running_native_task_is_visible_before_final_result(self):
        register(self.root);attempt=self.root/'campaign/native-runs/P01-native/attempt.json';attempt.parent.mkdir(parents=True)
        attempt.write_text(json.dumps({'paper':'P01','owner':'pi-own','started':123.,'task':'P01-native'}))
        dbpath=self.root/'runtime/state/workbench.sqlite';dbpath.parent.mkdir(parents=True)
        with sqlite3.connect(dbpath) as db:
            db.executescript('CREATE TABLE model_requests(id,owner,status,reserved,charged); CREATE TABLE conversations(id,status,error,updated); CREATE TABLE engineering_jobs(id,owner,status,created,ended,result,error);')
            db.execute('INSERT INTO conversations VALUES(?,?,?,?)',('pi-own','RUNNING',None,125.))
            db.execute('INSERT INTO model_requests VALUES(?,?,?,?,?)',('llm-own','pi-own','DISPATCHED',.05,0.))
            db.execute('INSERT INTO engineering_jobs VALUES(?,?,?,?,?,?,?)',('eng-own','pi-own','SUCCEEDED',124.,125.,json.dumps({'kind':'cadquery','readback_passed':True}),None))
        result=projection(self.root);live=result['paper_attempts'][0]
        self.assertFalse(live['result_available']);self.assertEqual('RUNNING',live['execution']['status'])
        self.assertEqual(.05,live['budget']['liability_usd']);self.assertTrue(live['jobs'][0]['readback_passed'])
        self.assertEqual(0,result['accepted_full_products'])
    def test_method_qualification_does_not_award_production_or_product_pass(self):
        register(self.root);revision=self.root/'learning/generation-test';revision.mkdir(parents=True)
        (revision/'prepared.json').write_text('{}')
        candidate=revision/'candidate-02.json';candidate.write_text(json.dumps({'child_method':'M2','adopted':False,'body':{'instruction':'bounded workflow'}}))
        comparison=revision/'comparison.json';comparison.write_text(json.dumps({'status':'LOCAL_QUALIFIED'}))
        (revision/'qualification-audit.json').write_text(json.dumps({'status':'PASS','candidate_sha256':digest(candidate),'comparison_sha256':digest(comparison),'allowed_experimental_use':['async-firmware-development']}))
        view=projection(self.root);c=view['candidates'][0]
        self.assertEqual('LOCAL_QUALIFIED',c['decision']);self.assertFalse(c['adopted'])
        self.assertEqual(['async-firmware-development'],c['allowed_experimental_use']);self.assertEqual(0,view['accepted_full_products'])
        candidate.write_text(candidate.read_text()+' ');c=projection(self.root)['candidates'][0]
        self.assertEqual('PENDING',c['decision']);self.assertEqual([],c['allowed_experimental_use'])
    def test_changed_job_output_is_not_listed_as_current_artifact(self):
        register(self.root);output=self.root/'runtime/engineering/eng-own/project-readback.json';output.parent.mkdir(parents=True);output.write_text('{}')
        dbpath=self.root/'runtime/state/workbench.sqlite';dbpath.parent.mkdir(parents=True)
        with sqlite3.connect(dbpath) as db:
            db.executescript('CREATE TABLE model_requests(id,owner,status,reserved,charged); CREATE TABLE conversations(id,status,error,updated); CREATE TABLE engineering_jobs(id,owner,status,created,ended,result,error);')
            db.execute('INSERT INTO engineering_jobs VALUES(?,?,?,?,?,?,?)',('eng-own','pi-own','SUCCEEDED',1,2,json.dumps({'outputs':[{'name':'project-readback.json','sha256':digest(output)}]}),None))
        self.assertEqual(1,len(projection(self.root)['live_native_jobs'][0]['artifacts']))
        output.write_text('changed');self.assertEqual([],projection(self.root)['live_native_jobs'][0]['artifacts'])
    def test_stage_review_is_bound_to_actual_selected_source(self):
        register(self.root)
        source=self.root/'runtime/participants/pi-own/spice/main.cir';source.parent.mkdir(parents=True);source.write_text('C1 out 0 1u')
        check={'job_id':'eng-own','project_sha256':'project','project_source_sha256':{'spice/main.cir':digest(source)}}
        task=self.root/'campaign/native-runs/P01-native';task.mkdir(parents=True)
        (task/'attempt.json').write_text(json.dumps({'paper':'P01','owner':'pi-own','started':1}))
        (task/'result.json').write_text(json.dumps({'paper':'P01','owner':'pi-own','evaluation':{'native_checks':[check]},'artifacts':[]}))
        review=self.root/'campaign/reviews/P01/stage-check-001/result.json';review.parent.mkdir(parents=True)
        row={'owner':'pi-own','job_id':'eng-own','project_sha256':'project','source_sha256':{'spice/main.cir':digest(source)},'status':'FAIL'}
        review.write_text(json.dumps(row))
        self.assertTrue(projection(self.root)['stage_reviews'][0]['matches_current_selected_sources'])
        source.write_text('changed circuit after review')
        self.assertFalse(projection(self.root)['stage_reviews'][0]['matches_current_selected_sources'])
        source.write_text('C1 out 0 1u');row['job_id']='different-job';review.write_text(json.dumps(row))
        self.assertFalse(projection(self.root)['stage_reviews'][0]['matches_current_selected_sources'])

    def test_legacy_source_recheck_requires_same_result_and_owner(self):
        register(self.root)
        source=self.root/'runtime/participants/pi-own/spice/main.cir';source.parent.mkdir(parents=True);source.write_text('C1 out 0 1u')
        check={'job_id':'eng-own','project_sha256':'project'}
        task=self.root/'campaign/native-runs/P01-native';task.mkdir(parents=True)
        (task/'attempt.json').write_text(json.dumps({'paper':'P01','owner':'pi-own','started':1}))
        result=task/'result.json';result.write_text(json.dumps({'paper':'P01','owner':'pi-own','evaluation':{'native_checks':[check]},'artifacts':[]}))
        review=self.root/'campaign/reviews/P01/stage-check-001/result.json';review.parent.mkdir(parents=True)
        review.write_text(json.dumps({'owner':'pi-own','job_id':'eng-own','project_sha256':'project','source_sha256':{'spice/main.cir':digest(source)},'status':'FAIL'}))
        recheck=review.parent.parent/'native-v2-binding-recheck.json'
        row={'owner':'pi-own','original_result':str(result.relative_to(self.root)),'original_result_sha256':digest(result),
             'native_readback':{'native_checks':[{**check,'project_source_sha256':{'spice/main.cir':digest(source)}}]}}
        recheck.write_text(json.dumps(row));self.assertTrue(projection(self.root)['stage_reviews'][0]['matches_current_selected_sources'])
        row['owner']='other-owner';recheck.write_text(json.dumps(row))
        self.assertFalse(projection(self.root)['stage_reviews'][0]['matches_current_selected_sources'])
        row['owner']='pi-own';recheck.write_text(json.dumps(row));result.write_text(result.read_text()+' ')
        self.assertFalse(projection(self.root)['stage_reviews'][0]['matches_current_selected_sources'])

    def test_review_bundle_requires_matching_bytes_and_paper_owner(self):
        register(self.root)
        task=self.root/'campaign/native-runs/P01-native';task.mkdir(parents=True)
        (task/'attempt.json').write_text(json.dumps({'paper':'P01','owner':'pi-own','started':1}))
        result=task/'result.json';result.write_text(json.dumps({'paper':'P01','owner':'pi-own','evaluation':{'status':'FAIL'},'artifacts':[]}))
        folder=self.root/'campaign/deliveries/P01/version';folder.mkdir(parents=True)
        archive=folder/'review.zip';archive.write_bytes(b'verified immutable archive')
        row={'paper_id':'P01','owner':'pi-own','created':2,'native_result_sha256':digest(result),
             'archive':{'path':str(archive.relative_to(self.root)),'sha256':digest(archive)}}
        receipt=folder/'receipt.json';receipt.write_text(json.dumps(row))
        self.assertTrue(projection(self.root)['deliveries'][0]['matches_current_result'])
        row['owner']='other-paper-owner';receipt.write_text(json.dumps(row))
        self.assertFalse(projection(self.root)['deliveries'][0]['matches_current_result'])
        archive.write_bytes(b'corrupted archive');self.assertEqual([],projection(self.root)['deliveries'])

    def test_method_candidate_survives_simultaneous_firmware_source_review(self):
        register(self.root);revision=self.root/'learning/generation-test';revision.mkdir(parents=True)
        (revision/'prepared.json').write_text('{}')
        candidate=revision/'candidate-02.json';candidate.write_text(json.dumps({'child_method':'M2','adopted':False,'body':{'instruction':'bounded workflow'}}))
        comparison=revision/'comparison.json';comparison.write_text(json.dumps({'status':'LOCAL_QUALIFIED'}))
        (revision/'qualification-audit.json').write_text(json.dumps({'status':'PASS','candidate_sha256':digest(candidate),'comparison_sha256':digest(comparison)}))
        source=self.root/'runtime/participants/pi-own/fw/main.c';source.parent.mkdir(parents=True);source.write_text('int main(void){return 0;}')
        task=self.root/'campaign/native-runs/P01-native';task.mkdir(parents=True)
        (task/'attempt.json').write_text(json.dumps({'paper':'P01','owner':'pi-own','started':1}))
        (task/'result.json').write_text(json.dumps({'paper':'P01','owner':'pi-own','evaluation':{'native_checks':[{'kind':'firmware-nrf52832','project_source_sha256':{'fw/main.c':digest(source)}}]},'artifacts':[]}))
        review=self.root/'campaign/reviews/P01/fault-check-001/result.json';review.parent.mkdir(parents=True)
        review.write_text(json.dumps({'source_owner':'pi-own','immutable_source_sha256':{'main.c':digest(source)},'checks':{'counterexample':False},'status':'FAIL'}))
        packet=projection(self.root)
        self.assertEqual(['M2'],[c['child_method'] for c in packet['candidates']])
        self.assertTrue(packet['functional_reviews'][0]['matches_current_selected_sources'])

    def test_legacy_method_body_requires_recorded_owner_and_exact_source(self):
        import hashlib
        register(self.root);revision=self.root/'revisions/legacy';revision.mkdir(parents=True)
        (revision/'prepared.json').write_text('{}')
        source=self.root/'runtime/participants/pi-improver/candidate.json';source.parent.mkdir(parents=True)
        body={'instruction':'original bounded method','hypothesis':'candidate hypothesis'};source.write_text(json.dumps(body))
        trial=revision/'trials/Pi-improver-01/result.json';trial.parent.mkdir(parents=True)
        row={'trial':'Pi-improver-01','kind':'improver','owner':'pi-improver','candidate_path':str(source),'model_calls':0}
        trial.write_text(json.dumps(row))
        candidate=revision/'candidate-01.json';candidate.write_text(json.dumps({'child_method':'M1','adopted':False,'improver_owner':'pi-improver','candidate_sha256':digest(source),'instruction_sha256':hashlib.sha256(body['instruction'].encode()).hexdigest()}))
        comparison=revision/'comparison.json';comparison.write_text(json.dumps({'status':'NO_MEASURED_BENEFIT'}))
        (revision/'qualification-audit.json').write_text(json.dumps({'status':'PASS','candidate_sha256':digest(candidate),'comparison_sha256':digest(comparison)}))
        c=projection(self.root)['candidates'][0]
        self.assertEqual('NO_MEASURED_BENEFIT',c['decision']);self.assertEqual(body['instruction'],c['instruction'])
        row['owner']='wrong-improver';trial.write_text(json.dumps(row));self.assertEqual('PENDING',projection(self.root)['candidates'][0]['decision'])
        row['owner']='pi-improver';trial.write_text(json.dumps(row));source.write_text(source.read_text()+' ')
        self.assertFalse(projection(self.root)['candidates'][0]['candidate_source_verified'])

if __name__=='__main__':unittest.main()
