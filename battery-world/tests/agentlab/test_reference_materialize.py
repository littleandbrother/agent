import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from bfworld.agentlab.references import References
from bfworld.agentlab.eda_cli import validate_argv, command_line


class ReferenceMaterialize(unittest.TestCase):
    def test_raw_identity_idempotence_and_conflicting_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); blob=root/'blob'; raw=b'/* vendor header */\n#define FIELD_Pos 16UL\n';blob.write_bytes(raw)
            obj=object.__new__(References);obj.store=SimpleNamespace(root=root/'state')
            source={'kind':'source','raw_sha256':hashlib.sha256(raw).hexdigest(),'url':'https://example.org/a.h'}
            with patch.object(obj,'get',return_value=source),patch.object(obj,'blob',return_value=blob),patch.object(obj,'put',side_effect=lambda owner,kind,v:v):
                result=obj.materialize('owner','ref','vendor/a.h')
                self.assertEqual((root/'participants/owner/vendor/a.h').read_bytes(),raw)
                self.assertEqual(obj.materialize('owner','ref','vendor/a.h'),result)
                self.assertEqual(result['sha256'],source['raw_sha256'])
                (root/'participants/owner/vendor/a.h').write_bytes(b'own change')
                with self.assertRaisesRegex(ValueError,'DESTINATION_CONFLICT'):obj.materialize('owner','ref','vendor/a.h')
                for name in ['../foreign/header.h',str(root/'absolute.h')]:
                    with self.assertRaises(ValueError):obj.materialize('owner','ref',name)
                (root/'participants/owner/outside').symlink_to(root,target_is_directory=True)
                with self.assertRaises(ValueError):obj.materialize('owner','ref','outside/escape.h')

    def test_owner_and_blob_checks_cannot_be_bypassed(self):
        obj=object.__new__(References)
        with patch.object(obj,'get',side_effect=PermissionError('REFERENCE_NOT_FOUND')):
            with self.assertRaises(PermissionError):obj.materialize('foreign','ref','a.h')
        obj.store=SimpleNamespace(root=Path('/tmp/state'))
        with patch.object(obj,'get',return_value={'kind':'source','raw_sha256':'bad'}),patch.object(obj,'blob',side_effect=ValueError('REFERENCE_BLOB_TAMPER')):
            with self.assertRaisesRegex(ValueError,'BLOB_TAMPER'):obj.materialize('owner','ref','a.h')

    def test_router_is_operator_owned_and_help_does_not_need_engine(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);router=root/'router with spaces';router.write_text('engine')
            for flag in ['--router','--router=arbitrary-command']:
                with self.assertRaisesRegex(ValueError,'ROUTER_SERVER_OWNED'):
                    validate_argv(['pcb','autoroute',flag,'malicious'],root,'bound')
            with patch('bfworld.agentlab.runtime_config.configured',return_value=router):
                command=command_line(['pcb','autoroute','--doc','board'],'bound')
                self.assertEqual(command[-2:],['--project','bound'])
                self.assertIn("'"+str(router)+"' {in} {out}",command)
            with patch('bfworld.agentlab.runtime_config.configured',return_value=root/'missing'):
                self.assertNotIn('--router',command_line(['pcb','autoroute','--help'],'bound'))
                with self.assertRaisesRegex(ValueError,'ROUTER_UNAVAILABLE'):command_line(['pcb','autoroute'],'bound')

if __name__=='__main__':unittest.main()
