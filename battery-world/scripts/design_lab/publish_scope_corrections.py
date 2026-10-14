#!/usr/bin/env python3
"""Reuse exact independent correction proofs without promoting core function."""
import json
from pathlib import Path
import sys
import time
APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.design_lab.contracts import sha,sealed
from bfworld.agentlab.store import identity
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT

root=DEFAULT_ROOT
path=root/'campaign/reviews/P08/funded-analysis-recheck-002/result.json'
review=json.loads(path.read_text());owner=review['owner']
if review['status']!='SCOPED_CORRECTIONS_VERIFIED' or not all(c['passed'] for c in review['checks']):
    raise ValueError('INDEPENDENT_CORRECTION_PROOF_REQUIRED')
workspace=root/'runtime/participants'/owner
for name,digest in review['current_files_sha256'].items():
    if sha(workspace/name)!=digest:raise ValueError('CORRECTION_REVIEW_INPUT_CHANGED:'+name)
source=review['source_result']
if sha(root/source['path'])!=source['sha256']:raise ValueError('CORRECTION_NATIVE_BINDING_CHANGED')
if sha(root/'runtime/engineering'/review['job_id']/'project-trace.raw')!=review['raw_sha256']:
    raise ValueError('CORRECTION_RAW_CHANGED')
if {r['id'] for r in review['findings'] if r['status']=='CORRECTED_SCOPE'}!={'F1','F2','F3','F4'}:
    raise ValueError('CORRECTION_FINDINGS_CHANGED')
artifacts=[]
for gate,ids in [('cold_start_domain',['F1']),('branch_energy',['F2','F3']),('efficiency_scope',['F4'])]:
    body={'schema_version':'bf-paper-digital-gate-review-v2','paper':'P08','owner':owner,
          'actor':'independent-checker','gate_id':gate,'status':'UNEVALUABLE','created':time.time(),
          'bindings':[{'job_id':review['job_id'],'project_sha256':review['project_sha256']}],
          'resolves':ids,'resolved_findings':[{'id':i,'status':'PASS','scope':'identified-defect-only'} for i in ids],
          'supporting_sources':[{'path':n,'sha256':s} for n,s in review['current_files_sha256'].items()],
          'source_review':{'path':str(path.relative_to(root)),'sha256':sha(path)},
          'scope':'Exact independent analysis defect correction only. Cold start, physical branch attribution and complete efficiency remain unevaluable.',
          'new_native_solves':0,'participant_source_edits':0}
    destination=root/'campaign/reviews/P08/digital-gates'/('scoped-correction-'+gate+'-'+identity(body)[:20]+'.json')
    sealed(destination,body);artifacts.append({'path':str(destination.relative_to(root)),'sha256':sha(destination)})
receipt={'schema_version':'bf-scoped-correction-projection-v1','artifacts':artifacts,
         'source_review_sha256':sha(path),'model_calls':0,'native_solves':0,
         'core_function_promoted':False,'physical_verified':False}
out=root/'deployment/executable-lab-20261012'/('correction-projection-'+str(time.time_ns())+'.json')
sealed(out,receipt);print(json.dumps({'receipt':str(out),'resolved_defects':['F1','F2','F3','F4'],'core_function':'UNEVALUABLE'}))
