import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bfworld.agentlab import runtime_config, launcher


class ReadonlyRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.receiver=self.root/'receiver-runtime-20261013'
        self.python=self.root/'.cache/codex-runtimes/fixture/dependencies/python'
        self.receiver.mkdir();self.python.mkdir(parents=True)
        (self.python/'python3').write_text('pinned public interpreter')
        (self.receiver/'python').symlink_to(self.python/'python3')
        self.workspace=self.root/'participants/pi-chat-original';self.workspace.mkdir(parents=True)
        self.qualification=self.root/'qualification.json';self.qualification.write_text('{"status":"PASS"}')
        self.manifest=self.root/'capability.json'
        self.value={'schema_version':'bf-participant-readonly-runtime-v1','purpose':'receiver-software',
            'owner':self.workspace.name,'workspace':str(self.workspace),
            'interpreter':str(self.receiver/'python'),
            'roots':[{'path':str(p),'tree_sha256':runtime_config.readonly_tree_hash(p,[self.receiver,self.python])}
                     for p in [self.receiver,self.python]],
            'qualification':{'path':str(self.qualification),'sha256':hashlib.sha256(self.qualification.read_bytes()).hexdigest()}}
        self.publish()

    def publish(self):
        self.manifest.write_text(json.dumps(self.value))
        self.reference={'path':str(self.manifest),'sha256':hashlib.sha256(self.manifest.read_bytes()).hexdigest()}

    def validate(self):
        return runtime_config.validate_readonly_runtime(self.reference,self.receiver,self.python)

    def test_exact_owner_and_runtime_pins_are_preserved(self):
        self.assertEqual(self.validate()['owner'],'pi-chat-original')
        self.assertEqual(self.validate()['manifest_sha256'],self.reference['sha256'])

    def test_changed_manifest_cannot_relabel_grant(self):
        self.manifest.write_text(self.manifest.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'MANIFEST_CHANGED'):self.validate()

    def test_changed_dependency_cannot_keep_old_qualification(self):
        (self.python/'python3').write_text('changed executable')
        with self.assertRaisesRegex(ValueError,'CONTENT_CHANGED'):self.validate()

    def test_symlink_cannot_escape_runtime_scope(self):
        outside=self.root/'private';outside.write_text('never exposed')
        (self.receiver/'escape').symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'LINK_ESCAPE'):self.validate()

    def test_broad_root_cannot_replace_exact_runtime(self):
        self.value['roots'][0]['path']=str(self.root);self.publish()
        with self.assertRaisesRegex(ValueError,'ROOT_SCOPE'):self.validate()

    def test_dangling_build_link_grants_no_materialized_external_target(self):
        outside=self.root/'absent-build-metadata';(self.python/'metadata').symlink_to(outside)
        self.value['roots'][1]['tree_sha256']=runtime_config.readonly_tree_hash(self.python,[self.receiver,self.python]);self.publish()
        self.validate()
        outside.write_text('external target now exists')
        with self.assertRaisesRegex(ValueError,'LINK_ESCAPE'):self.validate()

    def test_workspace_symlink_cannot_claim_original_owner(self):
        linked=self.root/'linked/participants/pi-chat-original';linked.parent.mkdir(parents=True)
        linked.symlink_to(self.workspace,target_is_directory=True)
        self.value['workspace']=str(linked);self.publish()
        with self.assertRaisesRegex(ValueError,'OWNER_SCOPE'):self.validate()

    def test_failed_receipt_does_not_qualify_runtime(self):
        self.qualification.write_text('{"status":"FAIL"}')
        self.value['qualification']['sha256']=hashlib.sha256(self.qualification.read_bytes()).hexdigest();self.publish()
        with self.assertRaisesRegex(ValueError,'QUALIFICATION_REQUIRED'):self.validate()

    def test_foreign_owner_same_basename_and_default_do_not_inherit_grant(self):
        foreign=self.root/'elsewhere/participants'/self.workspace.name;foreign.mkdir(parents=True)
        with patch.object(runtime_config,'_CONFIG',{'participant_readonly_runtime':self.reference}), \
             patch.object(runtime_config,'configured',side_effect=[self.receiver,self.python,self.receiver,self.python]), \
             patch.object(runtime_config,'RUNTIME_ROOT',self.receiver.parent), \
             patch.object(Path,'home',return_value=self.root):
            self.assertIsNone(runtime_config.readonly_runtime(foreign))
            self.assertEqual(runtime_config.readonly_runtime(self.workspace)['owner'],self.workspace.name)
        with patch.object(runtime_config,'_CONFIG',{}):self.assertIsNone(runtime_config.readonly_runtime(self.workspace))


@unittest.skipUnless(sys.platform=='darwin' and runtime_config._CONFIG.get('participant_readonly_runtime'),
                     'Actual operator capability required; fixture tests cannot grant live qualification')
class ActualReceiverCallerTests(unittest.TestCase):
    def test_original_production_sandbox_imports_and_security_boundaries(self):
        value=runtime_config.readonly_runtime();workspace=Path(value['workspace'])
        # The recorded original harness is already readable; no new owner or WB.
        session=workspace.parent.parent/'sessions'/value['owner']/'receipt.json'
        harness=Path(json.loads(session.read_text())['harness_path'])
        self.assertTrue(launcher.preflight(workspace,harness)['receiver_runtime'])
        foreign=workspace.parent/'pi-chat-103e79405f0e0c6d'/'project-cad'/'project.json'
        if not foreign.is_file():
            foreign=next(p for p in (workspace.parent/'pi-chat-103e79405f0e0c6d').rglob('project.json') if '.pi' not in p.parts)
        code="const fs=require('fs');const checks={};for(const [k,p] of Object.entries("+json.dumps({
            'provider':str(runtime_config.KEY_PATH),'evaluator':str(Path(launcher.__file__).with_name('experiments.py')),
            'foreign':str(foreign)})+")){try{fs.readFileSync(p);checks[k]=false}catch(e){checks[k]=['EPERM','EACCES'].includes(e.code)}};try{fs.writeFileSync("+json.dumps(str(Path(value['roots'][0]['path'])/'denied-write-canary'))+",'x');checks.write=false}catch(e){checks.write=['EPERM','EACCES'].includes(e.code)};console.log(JSON.stringify(checks));"
        p=subprocess.run(['/usr/bin/sandbox-exec','-p',launcher.seatbelt(workspace,harness),launcher.NODE,'-e',code],
            cwd=workspace,env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','TMPDIR':str(workspace/'.tmp')},
            capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout),{'provider':True,'evaluator':True,'foreign':True,'write':True})

