import json
from pathlib import Path
import tempfile
import unittest
from bfworld.agentlab.responsibility_review import inspect, digest, bind_contract, submit
from bfworld.agentlab.eda_cli import validate_argv
from bfworld.agentlab.recovery import open_before_send, RequestNotSent
from unittest.mock import Mock


class ReviewTests(unittest.TestCase):
    def test_cli_playbook_steps_remain_typed_and_workspace_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);plan=p/'plan.json'
            def check(step):
                plan.write_text(json.dumps({'version':1,'steps':[step]}))
                return validate_argv(['apply','plan.json'],p,'bound')
            check({'run':'sch list','flags':{'include-pins':True,'out':'pins.json'}})
            for step in [{'run':'debug exec-js'},{'run':'sch list','flags':{'out':'../escape'}},{'run':'sch list','flags':{'window':'foreign'}},{'run':'sch apply','args':['plan.json']},{'run':'sch list','flags':{'out':'${path}'}}]:
                with self.subTest(step=step),self.assertRaises(ValueError):check(step)

    def test_staged_workspace_preserves_inputs_and_rejects_initialized_reuse(self):
        from bfworld.agentlab.launcher import prepare_workspace
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'participant';p.mkdir();(p/'TASK.md').write_text('immutable inputs')
            with self.assertRaisesRegex(ValueError,'ALREADY_INITIALIZED'):prepare_workspace(p)
            prepare_workspace(p,staged=True)
            self.assertEqual((p/'TASK.md').read_text(),'immutable inputs')
            with self.assertRaisesRegex(ValueError,'ALREADY_INITIALIZED'):prepare_workspace(p,staged=True)
            prepare_workspace(p,resume=True)
            link=Path(tmp)/'link';link.symlink_to(p)
            with self.assertRaisesRegex(ValueError,'SYMLINK'):prepare_workspace(link,staged=True)

    def test_stage_product_before_any_model_dispatch(self):
        from bfworld.agentlab.server import Workbench
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            app=Workbench(Path(tmp)/'state')
            try:
                with patch.object(app.conversations,'start') as start:
                    owner=app.conversations.create('complete engineering flow',None,'staged-run',defer_dispatch=True)['id']
                    start.assert_not_called()
                    with app.store.connect() as db:
                        row=db.execute('SELECT status FROM chat_messages WHERE conversation=?',(owner,)).fetchone()
                        self.assertEqual(row['status'],'QUEUED')
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0],0)
                    app.conversations.retry(owner)
                    start.assert_called_once_with(owner)
            finally:
                app.stop.set();app.thread.join(3);app.lock.close()

    def test_apply_step_selector_and_offline_paths_have_distinct_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'apply.json').write_text('{"steps":[{"action":"schematic.save"}]}')
            result=validate_argv(['sch','apply','apply.json','--from','wire-2','--journal','journal.jsonl'],p)
            self.assertEqual(result[4],'wire-2')
            self.assertEqual(result[6],str((p/'journal.jsonl').resolve()))
            result=validate_argv(['sch','materialize','connectivity.json','--out','apply.json'],p)
            self.assertEqual(result[2],str((p/'connectivity.json').resolve()))
            result=validate_argv(['sch','compose','--from','input.json','--before','before.json','--playbook','apply.json','--out','result.json'],p)
            self.assertEqual(result[5],str((p/'before.json').resolve()))
            for args in [['sch','materialize','../secret.json'],['sch','compose','--before','../secret.json'],['apply','apply.json','--journal','../log']]:
                with self.subTest(args=args),self.assertRaises(ValueError):validate_argv(args,p)

    def test_redundant_exact_project_route_is_accepted_but_foreign_is_denied(self):
        p=Path('/tmp')
        self.assertEqual(validate_argv(['sch','list','--project','bound'],p,'bound'),['sch','list'])
        self.assertEqual(validate_argv(['project','export','--project-uuid=bound','--out','board.epro2'],p,'bound'),['project','export','--out',str((p/'board.epro2').resolve())])
        for argv in [['sch','list','--project','foreign'],['sch','list','--window','another'],['sch','list','--project']]:
            with self.subTest(argv=argv),self.assertRaises(ValueError):validate_argv(argv,p,'bound')

    def test_pcb_review_rejects_omitted_parallel_branch_and_reversed_polarity(self):
        import runpy
        review=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/door_case/review_pcb_source.py'))['review']
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.cir';source.write_text('D1 a b BAT46WJ\nD2 c b BAT46WJ\nRbal_D2 a c 0.22\n')
            physical={'instances':{'D1':{'mpn':'BAT46WJ','roles':{'A':'a','K':'b'}},'D2':{'mpn':'BAT46WJ','roles':{'A':'c','K':'b'}}}}
            bom={'lines':[{'refs':['D1','D2','Rbal_D2']}]}
            good=review(source,physical,bom)
            self.assertTrue(good['covered_checks_passed']);self.assertFalse(good['engineering_passed'])
            physical['instances']['D1']['roles']={'A':'b','K':'a'}
            bom['lines'][0]['refs']=['D1']
            bad=review(source,physical,bom)
            kinds={x['kind'] for x in bad['findings']}
            self.assertIn('electrical_role_mismatch',kinds);self.assertIn('missing_bom_instance',kinds);self.assertIn('missing_bom_ballast',kinds)

    def test_connect_retry_only_before_transmission_and_is_bounded(self):
        opener=Mock();response=object();events=[]
        opener.open.side_effect=[RequestNotSent('connect timed out'),response]
        self.assertIs(response,open_before_send(opener,object(),timeout=90,retry_record=events.append,before_retry=lambda:None))
        self.assertEqual(len(events),1);self.assertEqual(events[0]['transmission'],'not_sent')
        opener.open.reset_mock();opener.open.side_effect=TimeoutError('could have sent')
        with self.assertRaises(TimeoutError):open_before_send(opener,object(),timeout=90,retry_record=events.append,before_retry=lambda:None)
        self.assertEqual(opener.open.call_count,1)
        opener.open.reset_mock();opener.open.side_effect=RequestNotSent('still offline')
        with self.assertRaises(RequestNotSent):open_before_send(opener,object(),timeout=90,retry_record=events.append,before_retry=lambda:None)
        self.assertEqual(opener.open.call_count,3)

    def test_pcb_csv_counts_do_not_replace_native_pin_evidence(self):
        import runpy
        module=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/door_case/review_pcb_source.py'))
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=p/'source.cir';source.write_text('D1 a b BAT46WJ\n')
            csv=p/'bom.csv';csv.write_text('Qty,Refdes,MPN,Package,LCSC\n2,D1,BAT46WJ,SOD323F,PENDING\n')
            native={'result':{'components':[{'componentType':'part','designator':'D1','manufacturerId':'BAT54S','pins':[{'pinName':'A','net':''},{'pinName':'K','net':''}]}]}}
            result=module['review'](source,{'instances':{'D1':{'mpn':'BAT46WJ','roles':{'A':'a','K':'b'}}}},module['load_bom'](csv),native=native)
            kinds={x['kind'] for x in result['findings']}
            self.assertIn('bom_quantity_mismatch',kinds)
            self.assertIn('native_pin_role_unverified',kinds)
            self.assertIn('native_model_requires_equivalence',kinds)
            self.assertFalse(result['covered_checks_passed'])

    def test_eleven_pin_device_cannot_be_serialized_as_five_pin_netlist(self):
        import runpy
        audit=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/door_case/review_pcb_source.py'))['review_csv_netlist']
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'netlist.csv';p.write_text('ref,nodes,net1,net2,net3,net4,net5\nU1,11,0,0,cap,vin,sw\n')
            self.assertEqual(audit(p),[{'ref':'U1','kind':'netlist_terminal_loss','declared':11,'retained':5}])
            p.write_text('ref,nodes,net1,net2\nC1,2,vin,0\n')
            self.assertEqual(audit(p),[])

    def test_bounded_observer_continues_work_but_never_certifies_inventory(self):
        from bfworld.agentlab.server import Workbench
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'paid-window-closed.json').write_text('{}')
            app=Workbench(base/'state')
            try:
                owner=app.conversations.create('新板工程',None,'review-test')['id']
                p=base/'participants'/owner;p.mkdir(parents=True,exist_ok=True)
                (p/'source.cir').write_text('frozen')
                body={'source_revision':'D5','required_ids':['pcb'],'max_continuations':2,'reason':'User requested complete board',
                      'sources':[{'path':'source.cir','sha256':digest(p/'source.cir')}]}
                bind_contract(app,owner,body)
                self.assertTrue(app.deliverables.inspect(owner)['verdict']['auto_continue'])
                data={'source_revision':'D5','sources':body['sources'],'responsibilities':[{'id':'pcb','requirement':'pcb','status':'blocked','artifacts':[]}],
                      'assumptions':[],'decisions':[],'issues':[{'id':'account','text':'not connected'}]}
                (p/'analysis.json').write_text(json.dumps(data))
                v=app.deliverables.inspect(owner)['verdict'];self.assertFalse(v['auto_continue']);self.assertFalse(v['passed'])
                (p/'board.json').write_text('{}');data['responsibilities'][0].update(status='evidence_ready',artifacts=[{'path':'board.json','source_revision':'D5','reference_only':False}])
                (p/'analysis.json').write_text(json.dumps(data))
                v=app.deliverables.inspect(owner)['verdict'];self.assertFalse(v['auto_continue']);self.assertFalse(v['full_engineering_passed'])
                with self.assertRaisesRegex(ValueError,'ALREADY_FROZEN'):bind_contract(app,owner,{**body,'required_ids':['something-easier']})
            finally:
                app.stop.set();app.thread.join(3);app.lock.close()

    def test_submission_needs_real_blocker_evidence_and_never_passes_engineering(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);state=p/'state';state.mkdir();w=p/'participants'/'owner';w.mkdir(parents=True)
            app=SimpleNamespace(store=SimpleNamespace(root=state),conversations=Mock(),eda_cli=SimpleNamespace(workspace=lambda _:w))
            app.results=Mock();app.results.cases.publish.side_effect=lambda owner,root,manifest:manifest
            (w/'source.cir').write_text('D5');(w/'report.md').write_text('Blocked: native host did not persist the board. This is not a passing result.')
            sources=[{'path':'source.cir','sha256':digest(w/'source.cir')}]
            bind_contract(app,'owner',{'source_revision':'D5','sources':sources,'required_ids':['pcb'],'max_continuations':2,'reason':'new board'})
            row={'id':'pcb','requirement':'PCB','status':'working','artifacts':[]}
            data={'source_revision':'D5','sources':sources,'responsibilities':[row],'assumptions':[],'decisions':[],'issues':[]}
            def check():
                (w/'analysis.json').write_text(json.dumps(data))
                return submit(app,'owner',{'file_path':'report.md'})
            self.assertFalse(check()['submitted'])
            row.update(status='blocked',blocker_reason='Native host unavailable',artifacts=[{'path':'missing.json','source_revision':'D5','reference_only':False}])
            self.assertFalse(check()['submitted'])
            (w/'failure.json').write_text('{"ok":false,"error":"host unavailable"}')
            row['artifacts'][0]['path']='failure.json'
            result=check();self.assertTrue(result['submitted']);self.assertEqual(result['status'],'submitted_with_gaps')
            self.assertFalse(result['engineering_passed']);self.assertEqual(len(list((state/'responsibility-submissions/owner').glob('*.json'))),1)
            manifest=app.results.cases.publish.call_args.args[2]
            self.assertFalse(manifest['hardware_verified']);self.assertFalse(manifest['autonomous_agent_verified'])
            self.assertEqual(manifest['groups'][0]['design_status'],'insufficient_evidence')
            self.assertEqual(result['publication']['groups'],2)

    def test_old_board_and_source_drift_remain_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'source.cir').write_text('D5');(p/'old.pcb').write_text('D3')
            data={'source_revision':'D5','sources':[{'path':'source.cir','sha256':digest(p/'source.cir')}],
              'responsibilities':[{'id':'board','requirement':'Implement current circuit','status':'evidence_ready','artifacts':[{'path':'old.pcb','source_revision':'D3','reference_only':True}]}],
              'assumptions':[],'decisions':[],'issues':[]}
            (p/'analysis.json').write_text(json.dumps(data));self.assertEqual(inspect(p)['status'],'incomplete')
            self.assertFalse(inspect(p)['engineering_passed'])
            (p/'source.cir').write_text('changed');self.assertTrue(any(x.startswith('source_changed') for x in inspect(p)['errors']))

    def test_missing_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.assertEqual(inspect(p)['status'],'missing')
            (p/'escape').symlink_to('/tmp')
            for argv in [['pcb','dump','--out','../outside'],['pcb','dump','--out','escape/secret'],['debug','exec-js'],['call','project.create'],['call','debug.exec_js'],['pcb','dump','--host=evil'],['project','open']]:
                with self.subTest(argv=argv),self.assertRaises(ValueError):validate_argv(argv,p)

    def test_playbook_debug_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'bad.json').write_text(json.dumps({'steps':[{'action':'debug.exec_js','payload':{'code':'anything'}}]}))
            with self.assertRaises(ValueError):validate_argv(['apply','--from','bad.json'],p)
            self.assertEqual(validate_argv(['pcb','dump','--out','board.json'],p)[-1],str((p/'board.json').resolve()))

    def test_both_apply_entrypoints_validate_typed_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);plan=p/'plan.json'
            plan.write_text(json.dumps({'steps':[{'action':'schematic.component.place','payload':{'x':100,'y':100,'uuid':'device'}}]}))
            for argv in (['apply','plan.json'],['sch','apply','plan.json']):
                self.assertEqual(validate_argv(argv,p)[-1],str(plan.resolve()))
            plan.write_text(json.dumps({'steps':[{'action':'debug.exec_js','payload':{'code':'anything'}}]}))
            for argv in (['apply','plan.json'],['sch','apply','plan.json']):
                with self.assertRaises(ValueError): validate_argv(argv,p)

    def test_invalid_command_is_distinct_from_account_or_busy_failure(self):
        self.assertEqual(validate_argv(['--help'],Path('/tmp')),['--help'])
        self.assertEqual(validate_argv(['actions'],Path('/tmp')),['actions'])
        with self.assertRaisesRegex(ValueError,'not a busy project or login failure'):
            validate_argv(['resolve','--bom','candidate.csv'],Path('/tmp'))

    def test_batch_identity_and_native_export_remain_project_bound(self):
        from bfworld.agentlab.eda_cli import command_line, export_window
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);plan=p/'plan.json'
            plan.write_text(json.dumps({'projectId':'new-project','steps':[{'action':'schematic.save'}]}))
            validate_argv(['sch','apply','plan.json'],p,'new-project')
            with self.assertRaises(ValueError):validate_argv(['sch','apply','plan.json'],p,'old-project')
            health={'found':{'raw':{'windows':[{'windowId':'new-window','context':{'projectUuid':'new-project'}},{'windowId':'old-window','context':{'projectUuid':'old-project'}}]}}}
            window=export_window(health,'new-project')
            cmd=command_line(['project','export','--out','candidate.epro2'],'new-project',window)
            self.assertEqual(cmd[-6:],['--project','new-project','--project-uuid','new-project','--window','new-window'])
            with self.assertRaises(ValueError):export_window(health,'missing-project')
            with self.assertRaises(ValueError): validate_argv(['project','export','--project-uuid','old-project'],p,'new-project')

    def test_completed_inventory_is_not_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'source.cir').write_text('source');(p/'new.pcb').write_text('board')
            (p/'analysis.json').write_text(json.dumps({'source_revision':'D5','sources':[{'path':'source.cir','sha256':digest(p/'source.cir')}],
              'responsibilities':[{'id':'pcb','requirement':'pcb','status':'evidence_ready','artifacts':[{'path':'new.pcb','source_revision':'D5','reference_only':False}]}],
              'assumptions':[],'decisions':[],'issues':[]}))
            result=inspect(p);self.assertEqual(result['status'],'inventory_ready');self.assertFalse(result['engineering_passed'])

    def test_frozen_contract_detects_removed_responsibility_and_rewritten_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'source.cir').write_text('original D5')
            expected={'source_revision':'D5','required_ids':['pcb','native'],'sources':[{'path':'source.cir','sha256':digest(p/'source.cir')}]}
            (p/'source.cir').write_text('participant rewrite')
            (p/'analysis.json').write_text(json.dumps({'source_revision':'D5','sources':[{'path':'source.cir','sha256':digest(p/'source.cir')}],
              'responsibilities':[{'id':'pcb','requirement':'board','status':'blocked','artifacts':[]}],
              'assumptions':[],'decisions':[],'issues':[]}))
            result=inspect(p,expected)
            self.assertIn('native',result['actionable'])
            self.assertIn('frozen_source_changed:source.cir',result['errors'])
            self.assertEqual(result['blocked'],['pcb'])
            self.assertFalse(result['engineering_passed'])

    def test_payload_cannot_redirect_or_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for argv in [
                ['call','system.exec','--payload','{}'],
                ['call','sch.components','--payload','{"projectUuid":"old-project"}'],
                ['call','pcb.export','--payload','{"path":"../outside"}'],
                ['pcb','dump','--project-uuid=old-project']]:
                with self.subTest(argv=argv),self.assertRaises(ValueError):validate_argv(argv,p)
