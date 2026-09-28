#!/usr/bin/env python3
"""Run isolated transport/qualification controls; no real provider or credentials."""
import io
import json
import sys
import time
import unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'));sys.path.insert(0,str(REPO/'tests/campaign'))
from bfworld.kernel.canonical import canonical_hash,file_hash,write_canonical_json
from bfworld.campaign.splits import launch_readiness
from bfworld.campaign.repair import cpu_seconds,checked

class RecordedResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.cases=[]
    def addSuccess(self,test):super().addSuccess(test);self.cases.append({'id':test.id(),'passed':True})
    def addError(self,test,err):super().addError(test,err);self.cases.append({'id':test.id(),'passed':False})
    def addFailure(self,test,err):super().addFailure(test,err);self.cases.append({'id':test.id(),'passed':False})

def implementation_paths():
    targets=['test_b2_repair_bridge','test_b2_scientific','test_b2_trials','test_b2_proposal','test_b2_live_trials','test_b2_workflow_use'];paths=[]
    for module in targets:paths.append(REPO/'tests/campaign'/f'{module}.py')
    for name in ('repair_bridge.py','scientific.py','trials.py','proposal.py','live_trials.py','workflow_use.py','qualification.py','repair.py','compiler.py','provider.py','budget.py','task_context.py','splits.py','sandbox.py','semantic_development.py'):
        paths.append(REPO/'packages/python/bfworld/src/bfworld/campaign'/name)
    paths.extend([REPO/'packages/python/bfworld/src/bfworld/coupled'/n for n in ('profiled.py','profiled_artifacts.py','engine.py')])
    paths.extend([REPO/'scripts/run_b2_repair.py',REPO/'scripts/run_b2_trials.py',REPO/'scripts/build_b2_workflow_use.py',Path(__file__)])
    return {str(p.relative_to(REPO)):file_hash(p) for p in paths}

def validate_report(report):
    checked(report)
    if report['implementation']!=implementation_paths() or report['protocol_file_hash']!=file_hash(REPO/'studies/b2-003/protocol-draft.json'):
        raise ValueError('execution controls refer to stale implementation/protocol')
    if report['tests_run']!=len(report['cases']) or len({c['id'] for c in report['cases']})!=report['tests_run'] or not all(c['passed'] for c in report['cases']) or report['status']!='pass':
        raise ValueError('execution control suite did not completely pass')
    if report['actual_provider_calls']!=0 or report['actual_paid_cny']!=0 or report['credentials_loaded']:
        raise ValueError('fixture report cannot describe actual provider activity')
    return report

def ensure():
    path=REPO/'docs/b2-development/execution-controls.json'
    if path.exists():
        try:return validate_report(json.loads(path.read_text()))
        except ValueError:pass
    if main()!=0:raise ValueError('execution control validation failed')
    return validate_report(json.loads(path.read_text()))

def main():
    targets=['test_b2_repair_bridge','test_b2_scientific','test_b2_trials','test_b2_proposal','test_b2_live_trials','test_b2_workflow_use']
    implementation=implementation_paths()
    stream=io.StringIO();start=time.perf_counter();cpu=cpu_seconds()
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in targets)
    result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=RecordedResult).run(suite)
    report={'schema_version':'b2-execution-controls-v1','status':'pass' if result.wasSuccessful() else 'fail',
        'implementation':implementation,'protocol_file_hash':file_hash(REPO/'studies/b2-003/protocol-draft.json'),'cases':result.cases,'tests_run':result.testsRun,
        'control_transport':'in-process fake HTTP response with actual Provider.complete and isolated SQLite reservation/settlement; one actual subprocess exit',
        'actual_provider_calls':0,'actual_paid_cny':0,'credentials_loaded':False,
        'cost':{'wall_s':time.perf_counter()-start,'cpu_s':cpu_seconds()-cpu},
        'launch_readiness':launch_readiness(json.loads((REPO/'studies/b2-003/protocol-draft.json').read_text())),
        'claim_boundary':'Engineering recovery and qualification controls. No real G3/G4 generated, no formal candidate qualified, no Agent transfer or hardware result.'}
    report['content_hash']=canonical_hash(report)
    archive=REPO/'.bfworld/execution-controls'/report['content_hash'].split(':')[1]
    archive.mkdir(parents=True,exist_ok=False);write_canonical_json(archive/'report.json',report)
    (archive/'test-output.log').write_text(stream.getvalue())
    output=REPO/'docs/b2-development';write_canonical_json(output/'execution-controls.json',report)
    (output/'execution-controls.log').write_text(stream.getvalue())
    print(json.dumps({'status':report['status'],'tests_run':result.testsRun,'actual_provider_calls':0,'actual_paid_cny':0,'report_hash':report['content_hash']}))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':sys.exit(main())
