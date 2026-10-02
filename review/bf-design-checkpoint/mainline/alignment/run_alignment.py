#!/usr/bin/env python3
"""Create a NEW alignment receipt. Never overwrites a run or source input."""
import argparse,datetime,hashlib,importlib.util,json,os,pathlib,platform,sys,time,unittest
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'src'))
import adapters as a
p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);args=p.parse_args();out=args.output.resolve()
# Prevent any accidental write into source trees or sealed campaigns.
for source in (a.UP,a.CLOUD,a.EVENT):
    if out==source or source in out.parents:raise SystemExit('REFUSE_OUTPUT_INSIDE_SOURCE_TREE')
out.mkdir(parents=True,exist_ok=False)
lock=json.loads((ROOT/'contracts/source-lock.json').read_text());before={k:a.sha(v['path']) for k,v in lock['sources'].items()}
if any(before[k]!=v['sha256'] for k,v in lock['sources'].items()):raise SystemExit('SOURCE_LOCK_MISMATCH')
module=a.load_module('alignment_tests',ROOT/'tests/test_alignment.py');module.OUT=out
class Results(unittest.TextTestResult):
    def startTest(self,test):self.started=time.monotonic();super().startTest(test)
    def stopTest(self,test):records.append({'test':str(test),'wall_s':time.monotonic()-self.started,'passed':not any(t==test for t,_ in self.failures+self.errors)});super().stopTest(test)
records=[];start=time.monotonic()
with (out/'tests.log').open('w') as f:r=unittest.TextTestRunner(stream=f,verbosity=2,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(module.Alignment))
after={k:a.sha(v['path']) for k,v in lock['sources'].items()}
receipt={'schema_version':'simulation-alignment-receipt-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':sys.argv,'tests_run':r.testsRun,'passed':r.testsRun-len(r.failures)-len(r.errors),'failures':[(str(t),s) for t,s in r.failures],'errors':[(str(t),s) for t,s in r.errors],'test_records':records,'source_inputs_unchanged':before==after,'input_lock_sha256':a.sha(ROOT/'contracts/source-lock.json'),'test_plan_sha256':a.sha(ROOT/'fixtures/predeclared-tests.json'),'supplement_source_receipt':json.loads((ROOT/'source-supplement/fetch-receipt.json').read_text()),'harness_files':{str(f.relative_to(ROOT)):a.sha(f) for f in sorted(ROOT.rglob('*.py')) if out not in f.parents},'runtime':{'python':platform.python_version(),'numpy':a.np.__version__,'scipy':__import__('scipy').__version__,'jsonschema':__import__('importlib.metadata',fromlist=['version']).version('jsonschema'),'blas':a.cloud_power.solver_blas_providers()},'wall_s':time.monotonic()-start,'claim':'Portable semantic/differential checks only. Passing expected-difference tests is evidence of incompatibility, not whole-model equivalence.','native_tools_executed':[],'paid_calls':0,'full_closed_loop_comparison_admitted':False,'preserved_sources':lock['sources']}
a.write(out/'run-receipt.json',receipt)
a.write(out/'artifact-manifest.json',{'files':[{'path':str(f.relative_to(out)),'sha256':a.sha(f),'bytes':f.stat().st_size} for f in sorted(out.rglob('*')) if f.is_file()]})
print(json.dumps({k:receipt[k] for k in ('tests_run','passed','source_inputs_unchanged','wall_s','full_closed_loop_comparison_admitted')}))
if not r.wasSuccessful():print((out/'tests.log').read_text())
sys.exit(0 if r.wasSuccessful() and before==after else 1)
