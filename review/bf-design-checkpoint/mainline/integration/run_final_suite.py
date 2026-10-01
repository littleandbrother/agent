"""Final aggregate: inherited subprocess PYTHONPATH and explicitly scoped provider-unit isolation."""
import sys,pathlib,unittest,json,time,os,contextlib
from types import SimpleNamespace
from unittest.mock import patch
repo=pathlib.Path(sys.argv[1]).resolve();out=pathlib.Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['PYTHONPATH']=str(repo/'packages/python/bfworld/src')
os.chdir(repo);sys.path[:0]=[str(repo),str(repo/'packages/python/bfworld/src'),str(repo/'tests')]
class Result(unittest.TextTestResult):
 def __init__(self,*args,**kw): super().__init__(*args,**kw);self.records=[];self.provider_fixture_tests=0;self.transport_denials=0;self.fixture=None
 def startTest(self,t):
  if t.id().startswith('agentlab.test_provider.ProviderBudget.'):
   from bfworld.agentlab import provider
   self.provider_fixture_tests+=1;self.fixture=contextlib.ExitStack()
   self.fixture.enter_context(patch.object(provider,'KEY_PATH',SimpleNamespace(read_text=lambda:'inert-regression-only-not-an-api-key',exists=lambda:False)))
   def denied(*a,**kw):self.transport_denials+=1;raise AssertionError('PROVIDER_UNIT_FIXTURE_NETWORK_FORBIDDEN')
   for target in ['socket.socket.connect','socket.socket.connect_ex','socket.create_connection','urllib.request.OpenerDirector.open']:
    self.fixture.enter_context(patch(target,side_effect=denied))
  super().startTest(t)
 def stopTest(self,t):
  if self.fixture:self.fixture.close();self.fixture=None
  super().stopTest(t)
 def addSuccess(self,t):super().addSuccess(t);self.records.append({'id':t.id(),'status':'passed'})
 def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'id':t.id(),'status':'failed','traceback':self._exc_info_to_string(e,t)})
 def addError(self,t,e):super().addError(t,e);self.records.append({'id':t.id(),'status':'error','traceback':self._exc_info_to_string(e,t)})
 def addSkip(self,t,r):super().addSkip(t,r);self.records.append({'id':t.id(),'status':'skipped','reason':r})
start=time.monotonic();suite=unittest.defaultTestLoader.discover('tests');discovered=suite.countTestCases()
with (out/'unittest.log').open('w') as stream:r=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
summary={'discovered':discovered,'tests_run':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'passed':sum(x['status']=='passed' for x in r.records),'successful':r.wasSuccessful(),'elapsed_s':time.monotonic()-start,'python':sys.version,'repo':str(repo),'provider_fixture_tests':r.provider_fixture_tests,'provider_fixture_transport_denials':r.transport_denials,'provider_fixture_scope':'Only existing provider unit tests that already mock HTTP; inert in-memory key loader, no credential files, deny-all sockets/opener fallback, KEY_PATH.exists remains false. Other integration/readiness tests unchanged.','records':r.records}
(out/'result.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='records'}));sys.exit(0 if r.wasSuccessful() else 1)
