"""Run existing provider unit tests with scoped key-loader and deny-all transport fixtures."""
import sys,os,pathlib,unittest,json,socket
from types import SimpleNamespace
from unittest.mock import patch
repo=pathlib.Path(sys.argv[1]).resolve();out=pathlib.Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
os.chdir(repo);sys.path[:0]=[str(repo),str(repo/'packages/python/bfworld/src')]
from bfworld.agentlab import provider
suite=unittest.defaultTestLoader.loadTestsFromName('tests.agentlab.test_provider')
inert=SimpleNamespace(read_text=lambda:'inert-regression-only-not-an-api-key',exists=lambda:False)
guards={'unexpected_transport_calls':0}
def denied(*a,**k):guards['unexpected_transport_calls']+=1;raise AssertionError('PROVIDER_FIXTURE_NETWORK_FORBIDDEN')
with patch.object(provider,'KEY_PATH',inert),patch('socket.socket.connect',side_effect=denied),patch('socket.socket.connect_ex',side_effect=denied),patch('socket.create_connection',side_effect=denied),patch('urllib.request.OpenerDirector.open',side_effect=denied):
 # Existing tests override OpenerDirector.open only inside their explicit mock scopes.
 with (out/'unittest.log').open('w') as stream:r=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
 assert guards['unexpected_transport_calls']==0,guards
assert provider.KEY_PATH is not inert
result={'tests_run':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skips':len(r.skipped),'passed':r.wasSuccessful(),'repo':str(repo),'unexpected_transport_calls':guards['unexpected_transport_calls'],'real_credentials_loaded':False,'credential_files_created':False,'fixture_scope':'Only tests.agentlab.test_provider, whose tests explicitly mock OpenerDirector.open; nested deny-all socket and opener guards; exists() remains False so provider readiness is not asserted.','new_model_calls':0,'fixture_restored_after_suite':True}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
sys.exit(0 if r.wasSuccessful() else 1)
