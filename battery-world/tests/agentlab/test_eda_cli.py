import tempfile
import unittest
import json
import sqlite3
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from bfworld.agentlab.eda_cli import EdaCLI, select_window, command_line, validate_argv, ready_window


def health(*windows):
    return {'found': {'raw': {'windows':list(windows)}}}


def window(wid, project='bound', host='desktop', mode='half-offline'):
    return {'windowId':wid,'context':{'projectUuid':project,'environment':{'host':host,'mode':mode,'version':'4.1.60'}}}


class DesktopRouteTests(unittest.TestCase):
    policy={'host':'desktop','modes':['half-offline','offline']}

    def test_call_help_is_an_exact_readonly_metadata_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            for argv in [['call','--help'],['call','-h']]:
                self.assertEqual(argv,validate_argv(argv,Path(tmp),'bound'))
            with self.assertRaisesRegex(ValueError,'TYPED_ACTION_DENIED'):
                validate_argv(['call','debug.exec_js','--help'],Path(tmp),'bound')

    def test_connector_update_selects_only_the_exact_reviewed_version(self):
        old=window('old');old['connectorVersion']='old'
        new=window('new');new['connectorVersion']='reviewed'
        policy={**self.policy,'connector_version':'reviewed'}
        self.assertEqual(select_window(health(old,new),'bound',policy),new)
        for value in [health(old),health(window('missing-version'))]:
            with self.assertRaisesRegex(ValueError,'CONNECTOR_VERSION_MISMATCH'):
                select_window(value,'bound',policy)
        duplicate={**new,'windowId':'duplicate'}
        with self.assertRaisesRegex(ValueError,'WINDOW_AMBIGUOUS'):
            select_window(health(old,new,duplicate),'bound',policy)

    def test_reviewed_connector_package_is_hash_bound_without_new_grants(self):
        from bfworld.agentlab import runtime_config
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/'connector.eext';path.write_bytes(b'original-reviewed-package')
            config={'eda':{'connector_version':'reviewed','connector_package':{
                'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}}
            with patch.object(runtime_config,'_CONFIG',config):
                policy=runtime_config.eda_policy()
                self.assertEqual(policy['connector_package'],config['eda']['connector_package'])
                path.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'CONNECTOR_PACKAGE_CHANGED'):runtime_config.eda_policy()
                path.unlink();path.symlink_to(Path(tmp).resolve()/'other')
                with self.assertRaisesRegex(ValueError,'CONNECTOR_PACKAGE_CHANGED'):runtime_config.eda_policy()

    def test_connector_policy_refuses_relative_unknown_or_unversioned_packages(self):
        from bfworld.agentlab import runtime_config
        cases=[{'connector_version':''}, {'connector_package':{'path':'relative','sha256':'0'*64}},
               {'connector_version':'v1','connector_package':{'path':'relative','sha256':'0'*64}},
               {'connector_version':'v1','connector_package':{'path':'/unknown','sha256':'bad'}}]
        for value in cases:
            with self.subTest(value=value),patch.object(runtime_config,'_CONFIG',{'eda':value}):
                with self.assertRaises(ValueError):runtime_config.eda_policy()

    def test_native_window_is_selected_without_web_fallback(self):
        desktop=window('desktop')
        self.assertEqual(select_window(health(window('web',host='web',mode='online'),desktop), 'bound',self.policy),desktop)
        for value in [health(window('web',host='web',mode='online')),health(window('cloud',mode='online'))]:
            with self.assertRaisesRegex(ValueError,'HOST_POLICY_MISMATCH'): select_window(value,'bound',self.policy)

    def test_unknown_ambiguous_and_foreign_projects_refuse(self):
        unknown=window('old');unknown['context'].pop('environment')
        for value,reason in [(health(),'NO_CONNECTED_WINDOW'),(health(window('foreign',project='other')),'BOUND_PROJECT_NOT_OPEN'),
                             (health(unknown),'HOST_IDENTITY_UNKNOWN'),(health(window('one'),window('two')),'WINDOW_AMBIGUOUS')]:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError,reason):select_window(value,'bound',self.policy)

    def test_native_cli_uses_real_sessions_and_never_falls_back_to_duplicate_connectors(self):
        policy={**self.policy,'transport':'native-cli-v1'}
        native=window('native-session');native['capabilities']=['native-cli.v1']
        self.assertEqual(select_window(health(window('ws-one'),window('ws-two'),native),'bound',policy),native)
        with self.assertRaisesRegex(ValueError,'HOST_POLICY_MISMATCH'):
            select_window(health(window('ws-one'),window('ws-two')),'bound',policy)
        other=window('another-native-session');other['capabilities']=['native-cli.v1']
        with self.assertRaisesRegex(ValueError,'WINDOW_AMBIGUOUS'):
            select_window(health(native,other),'bound',policy)

    def test_reconnect_uses_project_identity_but_never_a_retired_window(self):
        self.assertEqual(select_window(health(window('replacement')),'bound',self.policy)['windowId'],'replacement')
        argv=command_line(['sch','save'],'bound','replacement')
        self.assertEqual(argv[-4:],['--project','bound','--window','replacement'])

    def test_schematic_import_disables_library_backfill_in_effective_receipt_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=['pcb','import-changes','--schematic','original-sch','--doc','original-pcb']
            effective=validate_argv(raw,Path(tmp),'bound')
            self.assertEqual(raw[-1],'original-pcb')
            self.assertEqual(effective,raw+['--no-sync-attrs'])
            self.assertEqual(validate_argv(effective,Path(tmp),'bound'),effective)
            command=command_line(effective,'bound','original-window')
            self.assertIn('--no-sync-attrs',command)
            self.assertEqual(command[-4:],['--project','bound','--window','original-window'])

    def test_schematic_import_policy_preserves_reads_and_rejects_false_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            for raw in [['pcb','import-changes','--help'],['pcb','import-changes','-h'],
                        ['sch','read'],['pcb','list','--include-pads']]:
                self.assertEqual(validate_argv(raw,Path(tmp),'bound'),raw)
            with self.assertRaisesRegex(ValueError,'IMPORT_LIBRARY_BACKFILL_DENIED'):
                validate_argv(['pcb','import-changes','--no-sync-attrs=false'],Path(tmp),'bound')

    def test_local_metadata_works_without_a_window(self):
        self.assertEqual(command_line(['api','show','sys_Environment'],'bound'),
                         command_line(['api','show','sys_Environment'],'another'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(validate_argv(['call','system.environment'],root,'bound'),['call','system.environment'])
            for action in ['system.page_reload','debug.exec_js','project.open']:
                with self.assertRaises(ValueError):validate_argv(['call',action],root,'bound')

    def test_project_help_exposes_exports_without_enabling_project_switch_or_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for args in [['project','--help'],['project','-h'],['project','export-source','--help']]:
                self.assertEqual(validate_argv(args,root,'bound'),args)
            for args in [['project','create'],['project','open','--help'],['project','find']]:
                with self.assertRaisesRegex(ValueError,'PROJECT_OPERATION_DENIED'):
                    validate_argv(args,root,'bound')
            with self.assertRaisesRegex(ValueError,'PROJECT_IDENTITY_MISMATCH'):
                validate_argv(['project','export-source','--project','foreign'],root,'bound')

    def test_inspect_reports_selected_transport_separately_from_typed_adapter(self):
        tool=EdaCLI.__new__(EdaCLI)
        tool.workspace=lambda owner:Path('/unused')
        tool.binding=lambda owner:{'project':'bound','writable':1}
        target=window('native-session');target['connectorVersion']='1.9.0-bf-native.1'
        for transport in ['native-cli-v1','easyeda-typed-v1']:
            tool.policy={**self.policy,'transport':transport}
            with patch('bfworld.agentlab.eda_cli.ready_window',return_value=target):
                result=tool.action('test-owner',{'action':'inspect'},operator=True)
            self.assertEqual(result['transport'],transport)
            self.assertEqual(result['adapter'],'easyeda-typed-v1')
            self.assertTrue(result['readiness']['ready'])
            self.assertEqual(result['import_changes_policy']['effective_flags'],['--no-sync-attrs'])

    def test_wait_retries_only_absent_startup_and_has_a_deadline(self):
        with patch('bfworld.agentlab.eda_cli.read_health',side_effect=[health(),health(window('ready'))]) as read, \
             patch('bfworld.agentlab.eda_cli.time.sleep'):
            self.assertEqual(ready_window('bound',self.policy,1)['windowId'],'ready')
            self.assertEqual(read.call_count,2)
        with patch('bfworld.agentlab.eda_cli.read_health',return_value=health(window('web',host='web'))) as read:
            with self.assertRaisesRegex(ValueError,'HOST_POLICY_MISMATCH'):ready_window('bound',self.policy,1)
            self.assertEqual(read.call_count,1)
        with patch('bfworld.agentlab.eda_cli.read_health',return_value=health()) as read:
            with self.assertRaisesRegex(ValueError,'NO_CONNECTED_WINDOW'):ready_window('bound',self.policy,0)
            self.assertEqual(read.call_count,1)


class NativeAuthorityTests(unittest.TestCase):
    def test_expired_historical_grant_needs_explicit_owner_time_authority(self):
        import json, sqlite3
        from bfworld.agentlab.engineering import Engineering
        from bfworld.agentlab.budget_policy import install
        owner='pi-chat-desktop-test'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.sqlite'
            class ScopedStore:
                def connect(self):
                    db=sqlite3.connect(path);db.row_factory=sqlite3.Row;return db
            store=ScopedStore()
            with store.connect() as db:
                db.executescript('CREATE TABLE grants(owner PRIMARY KEY,expires); CREATE TABLE chat_contexts(owner PRIMARY KEY,config); CREATE TABLE settings(key PRIMARY KEY,value);')
                db.execute('INSERT INTO grants VALUES(?,?)',(owner,1))
                db.execute('INSERT INTO chat_contexts VALUES(?,?)',(owner,json.dumps({'tools':['bf_engineering']})))
            tool=Engineering.__new__(Engineering);tool.store=store
            with self.assertRaises(PermissionError):tool.authorize(owner)
            policy={'schema_version':'bf-model-unbounded-policy-v2','mode':'unbounded','scope':'owners','owners':[owner],
                'authorized_by':'direct-user','direct_user_authorization':'No cumulative fee, token or request caps',
                'cumulative_usd_cap':None,'cumulative_token_cap':None,'request_count_cap':None,'request_usd_cap':None,
                'fees_reset':False,'unknown_reservations_preserved':True,'wall_seconds':None,
                'wall_authorized_by':'direct-user','wall_authorization_text':'持续运行 不设置时间限制',
                'wall_unbounded':True,'wall_owners':[owner],'unknown_carryforward':{}}
            with store.connect() as db:install(db,policy)
            tool.authorize(owner)
            with store.connect() as db:
                self.assertEqual(db.execute('SELECT expires FROM grants WHERE owner=?',(owner,)).fetchone()[0],1)
                db.execute('UPDATE chat_contexts SET config=?',(json.dumps({'tools':[]}),))
            with self.assertRaises(PermissionError):tool.authorize(owner)
            with store.connect() as db:
                db.execute('UPDATE chat_contexts SET config=?',(json.dumps({'tools':['bf_engineering']}),))
                db.execute('DELETE FROM grants')
            with self.assertRaises(PermissionError):tool.authorize(owner)
            with self.assertRaises(PermissionError):tool.authorize('pi-chat-other')


class ProjectProbeRecoveryTests(unittest.TestCase):
    """Transport failure cannot authorize a write or masquerade as a foreign design."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);state=root/'state.sqlite'
        class ScopedStore:
            def connect(self):return sqlite3.connect(state)
        self.tool=EdaCLI.__new__(EdaCLI)
        self.tool.store=ScopedStore();self.tool.lock=threading.Lock()
        self.tool.policy={'host':'desktop','modes':['half-offline'],'wait_s':0}
        self.tool.root=root/'receipts';self.tool.root.mkdir()
        self.workspace=root/'participant';self.workspace.mkdir()
        self.tool.app=SimpleNamespace(conversations=SimpleNamespace(event=Mock()))
        with self.tool.store.connect() as db:
            db.execute('CREATE TABLE eda_cli_jobs(id PRIMARY KEY,status,result,ended)')
            db.execute('INSERT INTO eda_cli_jobs VALUES(?,?,?,?)',('test-job','RUNNING',None,None))
        self.selected=window('native-window')

    def response(self,project='bound',**extra):
        value={'ok':True,'result':{'uuid':project,'environment':self.selected['context']['environment']},
               'context':{'projectUuid':project,'environment':self.selected['context']['environment']}}
        value.update(extra)
        return subprocess.CompletedProcess(['fixed-read'],0,json.dumps(value),'')

    def run_receipt(self,argv,responses):
        with patch('bfworld.agentlab.eda_cli.ready_window',return_value=self.selected), \
             patch('bfworld.agentlab.eda_cli.subprocess.run',side_effect=responses) as run:
            self.tool.run('original-owner','test-job',argv,{'project':'bound'},self.workspace)
        receipt=json.loads((self.tool.root/'test-job.json').read_text())
        with self.tool.store.connect() as db:
            row=db.execute('SELECT status,result FROM eda_cli_jobs WHERE id=?',('test-job',)).fetchone()
        self.assertEqual(row[0],receipt['status'])
        return receipt,run

    def test_unavailable_probe_preserves_native_error_and_never_sends_design_command(self):
        wire={'ok':False,'error':{'code':'CONNECTOR_HEALTH_UNVERIFIED','message':'queued read unanswered'}}
        proc=subprocess.CompletedProcess(['project','info'],1,json.dumps(wire),'native refused')
        receipt,run=self.run_receipt(['sch','save'],[proc])
        self.assertEqual(receipt['status'],'FAILED');self.assertFalse(receipt['command_entered'])
        self.assertEqual(run.call_count,1)
        self.assertEqual(receipt['error'],'EDA_PROJECT_PROBE_FAILED:CONNECTOR_HEALTH_UNVERIFIED')
        self.assertEqual(json.loads(receipt['project_probe']['stdout']),wire)
        self.assertEqual(receipt['project_probe']['stderr'],'native refused')
        self.assertEqual(receipt['project_probe']['exit_code'],1)

    def test_probe_timeout_is_not_an_unknown_design_mutation(self):
        receipt,run=self.run_receipt(['sch','save'],[subprocess.TimeoutExpired(['project','info'],15)])
        self.assertEqual(receipt['status'],'FAILED');self.assertFalse(receipt['command_entered'])
        self.assertEqual(receipt['error'],'EDA_PROJECT_PROBE_TIMEOUT_ACTION_NOT_SENT')
        self.assertTrue(receipt['project_probe']['timed_out']);self.assertEqual(run.call_count,1)

    def test_entered_design_timeout_remains_unknown_and_is_not_replayed(self):
        receipt,run=self.run_receipt(['sch','save'],[self.response(),subprocess.TimeoutExpired(['sch','save'],540)])
        self.assertEqual(receipt['status'],'UNKNOWN');self.assertTrue(receipt['command_entered'])
        self.assertEqual(receipt['error'],'EDA_COMMAND_TIMEOUT_READ_BACK_BEFORE_RETRY')
        self.assertEqual(run.call_count,2)

    def test_actual_replace_dispatch_timeout_reply_is_unknown_and_never_replayed(self):
        value={'ok':False,'error':{'code':'DISPATCH_FAILED','message':'connector did not respond','detail':'context deadline exceeded'}}
        proc=subprocess.CompletedProcess(['sch','replace'],1,json.dumps(value),'')
        receipt,run=self.run_receipt(['sch','replace','--id','old','--lcsc','C123'],[self.response(),proc])
        self.assertEqual('UNKNOWN',receipt['status']);self.assertTrue(receipt['command_entered'])
        self.assertEqual(2,run.call_count)

    def test_known_replace_refusal_and_read_dispatch_failure_are_not_unknown_writes(self):
        value={'ok':False,'error':{'code':'INVALID_STATE','message':'target ambiguous before delete'}}
        proc=subprocess.CompletedProcess(['sch','replace'],1,json.dumps(value),'')
        receipt,_=self.run_receipt(['sch','replace','--id','old','--lcsc','C123'],[self.response(),proc])
        self.assertEqual('FAILED',receipt['status'])
        value['error'].update(code='DISPATCH_FAILED',message='connector did not respond',detail='context deadline exceeded')
        proc=subprocess.CompletedProcess(['sch','list'],1,json.dumps(value),'')
        receipt,_=self.run_receipt(['sch','list'],[self.response(),proc])
        self.assertEqual('FAILED',receipt['status'])

    def test_readonly_document_diagnostic_does_not_require_the_blocked_project_probe(self):
        argv=['call','document.current']
        self.assertEqual(validate_argv(argv,self.workspace,'bound'),argv)
        proc=self.response(result={'uuid':'sheet-one','parentProjectUuid':'bound'})
        receipt,run=self.run_receipt(argv,[proc])
        self.assertEqual(receipt['status'],'SUCCEEDED');self.assertEqual(run.call_count,1)
        self.assertNotIn('project_probe',receipt)
        self.assertEqual(run.call_args.args[0][1:3],argv)
        self.assertEqual(receipt['native_host']['project_uuid'],'bound')
        with self.assertRaisesRegex(ValueError,'TYPED_ACTION_DENIED'):
            validate_argv(['call','document.delete'],self.workspace,'bound')

    def test_fresh_foreign_project_prevents_design_command_despite_cached_health(self):
        receipt,run=self.run_receipt(['sch','save'],[self.response('foreign')])
        self.assertEqual(receipt['status'],'FAILED');self.assertFalse(receipt['command_entered'])
        self.assertEqual(receipt['error'],'EDA_FRESH_PROJECT_IDENTITY_MISMATCH')
        self.assertEqual(run.call_count,1)

    def test_diagnostic_still_rejects_a_foreign_project_and_retains_its_read_receipt(self):
        proc=self.response('foreign')
        receipt,run=self.run_receipt(['project','info'],[proc])
        self.assertEqual(receipt['status'],'FAILED');self.assertTrue(receipt['command_entered'])
        self.assertEqual(receipt['error'],'EDA_FRESH_PROJECT_IDENTITY_MISMATCH')
        self.assertEqual(receipt['stdout'],proc.stdout);self.assertEqual(run.call_count,1)

    def test_malformed_or_missing_identity_never_authorizes_a_design_command(self):
        for value,reason in [('[]','INVALID_RESPONSE'),('{"ok":true,"result":[]}','IDENTITY_UNKNOWN'),
                             ('{"ok":true,"result":{"uuid":"bound"},"context":"bad"}','INVALID_RESPONSE')]:
            with self.subTest(value=value):
                proc=subprocess.CompletedProcess(['project','info'],0,value,'')
                receipt,run=self.run_receipt(['sch','save'],[proc])
                self.assertEqual(receipt['status'],'FAILED');self.assertFalse(receipt['command_entered'])
                self.assertIn(reason,receipt['error']);self.assertEqual(run.call_count,1)


class HistoricalOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.sqlite'
        def connect():
            db = sqlite3.connect(self.path)
            db.row_factory = sqlite3.Row
            return db
        self.tool = EdaCLI.__new__(EdaCLI)
        self.tool.store = SimpleNamespace(connect=connect)
        self.tool.workspace = lambda owner: Path(self.temp.name)
        self.tool.binding = lambda owner: {'project': 'bound', 'writable': 1}
        self.tool.app = SimpleNamespace(engineering=SimpleNamespace(authorize=Mock()))
        from bfworld.agentlab.store import canonical
        with connect() as db:
            db.execute('CREATE TABLE eda_cli_jobs(id,owner,operation,request,status,result,created,ended)')
            for status in ['SUCCEEDED', 'FAILED', 'UNKNOWN']:
                db.execute('INSERT INTO eda_cli_jobs VALUES(?,?,?,?,?,?,?,?)', (
                    'eda-' + status, 'original', status, canonical({'argv': ['sch', 'save'], 'project': 'bound'}),
                    status, json.dumps({'original': status}), 1, 2))

    def test_completed_failed_and_unknown_operations_only_return_unchanged_history(self):
        with self.tool.store.connect() as db:
            before = [tuple(row) for row in db.execute('SELECT * FROM eda_cli_jobs')]
        with patch('bfworld.agentlab.eda_cli.threading.Thread') as worker, patch('bfworld.agentlab.eda_cli.subprocess.run') as run:
            for status in ['SUCCEEDED', 'FAILED', 'UNKNOWN']:
                result = self.tool.action('original', {'action': 'command', 'argv': ['sch', 'save'], 'operation_id': status})
                self.assertEqual(status, result['status'])
                self.assertEqual({'original': status}, result['result'])
                self.assertEqual('existing_operation', result['observation']['origin'])
                self.assertFalse(result['observation']['dispatch_requested_in_this_call'])
                self.assertFalse(result['observation']['current_design_revalidated'])
            worker.assert_not_called()
            run.assert_not_called()
        with self.tool.store.connect() as db:
            self.assertEqual(before, [tuple(row) for row in db.execute('SELECT * FROM eda_cli_jobs')])

    def test_job_query_is_historical_and_cannot_read_a_foreign_owner(self):
        result = self.tool.get('original', 'eda-UNKNOWN')
        self.assertEqual('job_lookup', result['observation']['origin'])
        self.assertFalse(result['observation']['dispatch_requested_in_this_call'])
        with self.assertRaisesRegex(ValueError, 'EDA_JOB_NOT_FOUND'):
            self.tool.get('foreign', 'eda-UNKNOWN')

    def test_conflicting_arguments_are_rejected_without_replacing_original_operation(self):
        with patch('bfworld.agentlab.eda_cli.threading.Thread') as worker, self.assertRaisesRegex(ValueError, 'OPERATION_CONFLICT'):
            self.tool.action('original', {'action': 'command', 'argv': ['sch', 'read'], 'operation_id': 'SUCCEEDED'})
        worker.assert_not_called()
        self.assertEqual(['sch', 'save'], self.tool.get('original', 'eda-SUCCEEDED')['request']['argv'])

    def insert_observation(self, jid, created, owner='original', project='bound', status='SUCCEEDED', argv=None):
        from bfworld.agentlab.store import canonical, identity
        argv=argv or ['sch','read']
        receipt={'job_id':jid,'owner':owner,'project':project,'status':status,'stdout':'x'*200000}
        folder=Path(self.temp.name)/'eda-receipts';folder.mkdir(exist_ok=True)
        path=folder/(jid+'.json');path.write_text(canonical(receipt))
        result={'receipt_path':'eda-receipts/'+jid+'.json','receipt_sha256':identity(receipt)}
        with self.tool.store.connect() as db:
            db.execute('INSERT INTO eda_cli_jobs VALUES(?,?,?,?,?,?,?,?)',
                       (jid,owner,jid,canonical({'argv':argv,'project':project}),status,canonical(result),created,created+1))
        return path

    def test_latest_eda_read_is_owner_project_and_hash_bound_without_frontloading_result(self):
        self.insert_observation('eda-read-old',10)
        path=self.insert_observation('eda-read-current',20)
        self.insert_observation('eda-foreign',30,owner='foreign')
        self.insert_observation('eda-other-project',40,project='another')
        with self.tool.store.connect() as db:before=[tuple(row) for row in db.execute('SELECT * FROM eda_cli_jobs')]
        with patch('bfworld.agentlab.eda_cli.subprocess.run') as run:
            history=self.tool.public_history('original','bound')
        run.assert_not_called()
        observation=history['latest_by_action']['sch.read']
        self.assertEqual('eda-read-current',observation['id'])
        self.assertEqual('HASH_BOUND',observation['receipt_status'])
        self.assertEqual('eda-receipts/'+path.name,observation['receipt']['path'])
        self.assertFalse(observation['current_design_revalidated'])
        self.assertLess(len(json.dumps(history)),12000)
        self.assertNotIn('stdout',json.dumps(history))
        self.assertNotIn('eda-foreign',json.dumps(history))
        self.assertNotIn('eda-other-project',json.dumps(history))
        with self.tool.store.connect() as db:self.assertEqual(before,[tuple(row) for row in db.execute('SELECT * FROM eda_cli_jobs')])

    def test_latest_failed_or_unknown_read_is_never_replaced_by_an_older_success(self):
        self.insert_observation('eda-read-old',10)
        for i,status in enumerate(['FAILED','UNKNOWN']):
            self.insert_observation('eda-read-'+status,20+i,status=status)
            history=self.tool.public_history('original','bound')
            observation=history['latest_by_action']['sch.read']
            self.assertEqual(status,observation['status'])
            self.assertEqual('eda-read-'+status,observation['id'])
            self.assertFalse(history['full_product_passed'])

    def test_missing_corrupt_and_symlink_receipts_do_not_produce_verified_pointers(self):
        path=self.insert_observation('eda-read-current',20)
        for mode in ['corrupt','missing','symlink']:
            with self.subTest(mode=mode):
                if path.exists() or path.is_symlink():path.unlink()
                if mode=='corrupt':path.write_text('changed')
                if mode=='symlink':path.symlink_to(self.path)
                observation=self.tool.public_history('original','bound')['latest_by_action']['sch.read']
                self.assertNotEqual('HASH_BOUND',observation['receipt_status'])
                self.assertNotIn('receipt',observation)

    def test_recent_operation_projection_is_bounded_and_does_not_replay(self):
        for i in range(12):self.insert_observation('eda-save-'+str(i),30+i,argv=['sch','save'])
        history=self.tool.public_history('original','bound')
        self.assertEqual(8,len(history['recent_operations']))
        self.assertEqual('eda-save-11',history['latest_by_action']['sch.save']['id'])
        self.assertEqual(0,history['new_native_calls'])
