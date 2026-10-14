from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from bfworld.agentlab.store import Store
from bfworld.agentlab.eda_cli import EdaCLI
from bfworld.agentlab.literature_eda import local_destination,open_local_destination,persisted_window,verify_native_documents
from bfworld.agentlab.literature_native import native_route_allowed
from unittest.mock import patch
import json


class LocalEdaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state')
        with self.store.connect() as db:
            db.execute('CREATE TABLE model_requests(id TEXT,status TEXT,reserved REAL,charged REAL)')
            db.execute('INSERT INTO model_requests VALUES("original","UNKNOWN",.8,0)')
        self.cli=EdaCLI(SimpleNamespace(store=self.store))
        self.original=self.cli.bind('original-owner','cloud-container-001','original authority',True)

    def test_append_migration_retains_exact_original_and_owner(self):
        with self.store.connect() as db:
            original=dict(db.execute('SELECT * FROM eda_cli_bindings').fetchone())
        result=self.cli.migrate_binding('original-owner','cloud-container-001','local-project-001','a'*64,'local authority',operator=True)
        self.assertEqual('local-project-001',result['project'])
        self.assertEqual('original-owner',result['owner'])
        self.assertEqual(result,self.cli.migrate_binding('original-owner','cloud-container-001','local-project-001','a'*64,'local authority',operator=True))
        with self.store.connect() as db:
            self.assertEqual(original,dict(db.execute('SELECT * FROM eda_cli_bindings').fetchone()))
            self.assertEqual(1,db.execute('SELECT COUNT(*) FROM eda_cli_binding_revisions').fetchone()[0])
            self.assertEqual(('original','UNKNOWN',.8,0),tuple(db.execute('SELECT * FROM model_requests').fetchone()))

    def test_participant_wrong_parent_and_foreign_project_are_rejected(self):
        with self.assertRaisesRegex(PermissionError,'OPERATOR_REQUIRED'):
            self.cli.migrate_binding('original-owner','cloud-container-001','local-project-001','a'*64,'fake')
        with self.assertRaisesRegex(ValueError,'PREVIOUS_BINDING'):
            self.cli.migrate_binding('original-owner','wrong-cloud-001','local-project-001','a'*64,'fake',operator=True)
        self.cli.bind('other-owner','local-project-001','other authority',True)
        with self.assertRaisesRegex(ValueError,'FOREIGN_PROJECT'):
            self.cli.migrate_binding('original-owner','cloud-container-001','local-project-001','a'*64,'fake',operator=True)

    def test_native_local_path_identity_symlinks_and_foreign_scope(self):
        root=Path(self.tmp.name).resolve()/'local';root.mkdir()
        path=root/'paper.eprj3';path.write_text(json.dumps({'name':'paper'}))
        record={'local_project':str(path)};creation={'name':'paper'}
        with patch('bfworld.agentlab.runtime_config.configured',return_value=root):
            self.assertEqual(path,local_destination(record,creation))
            with self.assertRaisesRegex(ValueError,'LOCAL_PROJECT_NAME'):
                local_destination(record,{'name':'foreign'})
            link=root/'alias.eprj3';link.symlink_to(path)
            with self.assertRaisesRegex(ValueError,'LOCAL_PROJECT_SCOPE'):
                local_destination({'local_project':str(link)},creation)
            outside=Path(self.tmp.name)/'other.eprj3';outside.write_text('{}')
            with self.assertRaisesRegex(ValueError,'LOCAL_PROJECT_SCOPE'):
                local_destination({'local_project':str(outside)},creation)

    def test_open_exact_file_only_when_absent_and_no_other_window_fallback(self):
        policy={'host':'desktop','transport':'native-cli-v1','wait_s':30}
        window={'windowId':'native-cli-expected'}
        with patch('bfworld.agentlab.literature_eda.local_destination',return_value=Path('/paper.eprj3')),patch('bfworld.agentlab.eda_cli.ready_window',return_value=window),patch('bfworld.agentlab.literature_eda.subprocess.run') as run:
            self.assertEqual((window,None),open_local_destination({}, {}, 'paper',policy));run.assert_not_called()
        with patch('bfworld.agentlab.literature_eda.local_destination',return_value=Path('/paper.eprj3')),patch('bfworld.agentlab.eda_cli.ready_window',side_effect=ValueError('EDA_WINDOW_AMBIGUOUS')),patch('bfworld.agentlab.literature_eda.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):open_local_destination({}, {}, 'paper',policy)
            run.assert_not_called()
        cli=Path(self.tmp.name)/'official-cli';cli.touch()
        result=SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'value':{'sessionId':'owned'}}))
        window,health=self.native_health('owned')
        listed=SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'value':[]}))
        with patch('bfworld.agentlab.literature_eda.local_destination',return_value=Path('/paper.eprj3')),patch('bfworld.agentlab.runtime_config.configured',return_value=cli),patch('bfworld.agentlab.eda_cli.ready_window',side_effect=ValueError('EDA_BOUND_PROJECT_NOT_OPEN')),patch('bfworld.agentlab.eda_cli.read_health',return_value=health),patch('bfworld.agentlab.literature_eda.subprocess.run',side_effect=[listed,result]) as run:
            opened=open_local_destination({'local_project':'/paper.eprj3'}, {'name':'paper'}, 'creation-project',policy)
            self.assertEqual(window,opened[0]);self.assertEqual('owned',opened[1]['value']['sessionId'])
            self.assertEqual([str(cli),'open','--path','/paper.eprj3','--headless'],run.call_args.args[0])

    def test_only_bound_paper_can_access_eda_in_a_non_eda_stage(self):
        self.assertFalse(native_route_allowed('/api/eda-cli','engineering-review'))
        self.assertTrue(native_route_allowed('/api/eda-cli','engineering-review',eda_bound=True))
        self.assertFalse(native_route_allowed('/api/conversations/x/message','engineering-review',eda_bound=True))
        self.assertFalse(native_route_allowed('/api/eda-cli-migration','eda',eda_bound=True))

    def native_health(self,session='opened'):
        window={'windowId':'native-cli-'+session,'capabilities':['native-cli.v1'],
                'context':{'projectUuid':'persisted-runtime-uuid','projectName':'paper','environment':{'host':'desktop','mode':'half-offline'}}}
        return window,{'found':{'raw':{'windows':[window]}}}

    def test_native_reopen_alias_requires_exact_official_file_session(self):
        window,health=self.native_health();record={'local_project':'/expected/paper.eprj3'}
        sessions={'ok':True,'value':[{'sessionId':'opened','status':'alive','origin':'cli','path':record['local_project']}]}
        policy={'host':'desktop','modes':['half-offline'],'transport':'native-cli-v1'}
        self.assertEqual(window,persisted_window(record,{'name':'paper'},policy,sessions,health))
        for key,value in [('path','/foreign/paper.eprj3'),('origin','user'),('status','closed')]:
            with self.subTest(key=key):
                wrong={'ok':True,'value':[{**sessions['value'][0],key:value}]}
                with self.assertRaisesRegex(ValueError,'FILE_NOT_OPEN'):persisted_window(record,{'name':'paper'},policy,wrong,health)
        duplicate={'ok':True,'value':sessions['value']*2}
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):persisted_window(record,{'name':'paper'},policy,duplicate,health)

    def test_same_title_cannot_hide_foreign_documents_or_host(self):
        window,health=self.native_health();record={'local_project':'/expected/paper.eprj3'}
        sessions={'ok':True,'value':[{'sessionId':'opened','status':'alive','origin':'cli','path':record['local_project']}]}
        window['context']['environment']['host']='web'
        with self.assertRaisesRegex(ValueError,'HOST_POLICY'):persisted_window(record,{'name':'paper'},{'host':'desktop','transport':'native-cli-v1'},sessions,health)
        path=Path(self.tmp.name)/'paper.eprj3';path.write_text(json.dumps({'profile':{'schematics':{'sch-one':{}},'pcbs':{'pcb-one':{}}}}))
        response={'ok':True,'result':{'boards':[{'schematicUuid':'sch-one','pcbUuid':'pcb-one'}]}}
        verify_native_documents(path,response)
        response['result']['boards'][0]['pcbUuid']='foreign-same-name'
        with self.assertRaisesRegex(ValueError,'DOCUMENT_MISMATCH'):verify_native_documents(path,response)


    def test_missing_identity_is_readiness_wrong_identity_is_hard_failure(self):
        window,health=self.native_health();record={'local_project':'/expected/paper.eprj3'}
        sessions={'ok':True,'value':[{'sessionId':'opened','status':'alive','origin':'cli','path':record['local_project']}]}
        window['context'].pop('projectUuid')
        with self.assertRaisesRegex(ValueError,'NOT_READY'):
            persisted_window(record,{'name':'paper'},{'host':'desktop','transport':'native-cli-v1'},sessions,health)
        window['context']['projectUuid']='runtime-owned'
        window['context']['projectName']='another-paper'
        with self.assertRaisesRegex(ValueError,'WINDOW_IDENTITY'):
            persisted_window(record,{'name':'paper'},{'host':'desktop','transport':'native-cli-v1'},sessions,health)

    def test_open_waits_for_bound_context_without_relaxing_document_identity(self):
        cli=Path(self.tmp.name)/'official-cli';cli.touch()
        listed=SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'value':[]}))
        opened=SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'value':{'sessionId':'owned'}}))
        window,healthy=self.native_health('owned')
        pending={'found':{'raw':{'windows':[{**window,'context':{}}]}}}
        with patch('bfworld.agentlab.literature_eda.local_destination',return_value=Path('/paper.eprj3')),patch('bfworld.agentlab.runtime_config.configured',return_value=cli),patch('bfworld.agentlab.eda_cli.ready_window',side_effect=ValueError('EDA_BOUND_PROJECT_NOT_OPEN')),patch('bfworld.agentlab.eda_cli.read_health',side_effect=[{'found':{'raw':{'windows':[]}}},pending,healthy]),patch('bfworld.agentlab.literature_eda.subprocess.run',side_effect=[listed,opened]),patch('time.sleep') as sleep:
            result=open_local_destination({'local_project':'/paper.eprj3'},{'name':'paper'},'creation-project',{'host':'desktop','transport':'native-cli-v1','wait_s':1})
            self.assertEqual(window,result[0]);sleep.assert_called_once_with(.25)


if __name__=='__main__':unittest.main()
