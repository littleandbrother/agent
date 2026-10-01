import sys,pathlib,unittest,json,time,os
repo=pathlib.Path(sys.argv[1]).resolve();out=pathlib.Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
os.chdir(repo);sys.path[:0]=[str(repo),str(repo/'packages/python/bfworld/src'),str(repo/'tests')]
class Result(unittest.TextTestResult):
 def __init__(self,*args,**kw): super().__init__(*args,**kw);self.records=[]
 def addSuccess(self,t): super().addSuccess(t);self.records.append({'id':t.id(),'status':'passed'})
 def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'id':t.id(),'status':'failed','traceback':self._exc_info_to_string(e,t)})
 def addError(self,t,e):super().addError(t,e);self.records.append({'id':t.id(),'status':'error','traceback':self._exc_info_to_string(e,t)})
 def addSkip(self,t,r):super().addSkip(t,r);self.records.append({'id':t.id(),'status':'skipped','reason':r})
start=time.monotonic()
with (out/'unittest.log').open('w') as stream:
 suite=unittest.defaultTestLoader.discover('tests');r=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
summary={'tests_run':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'passed':sum(x['status']=='passed' for x in r.records),'successful':r.wasSuccessful(),'elapsed_s':time.monotonic()-start,'python':sys.version,'repo':str(repo),'records':r.records}
(out/'result.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='records'}))
sys.exit(0 if r.wasSuccessful() else 1)
