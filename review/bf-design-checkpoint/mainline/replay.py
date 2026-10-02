#!/usr/bin/env python3
"""Read-only package checks and bounded replay in a NEW directory.
No downloads, vendor tools, credentials, full application build or participant calls.
"""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def package_check():
 manifest=ROOT/'FILE-MANIFEST.json'
 if not manifest.is_file():raise SystemExit('PACKAGE_MANIFEST_MISSING')
 entries=json.loads(manifest.read_text())['files'];errors=[]
 expected={x['path'] for x in entries}|{'FILE-MANIFEST.json'}
 actual={str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()}
 if actual!=expected:errors.append({'unexpected_or_missing':sorted(actual^expected)})
 for e in entries:
  p=ROOT/e['path']
  if p.is_symlink() or not p.is_file() or p.stat().st_size!=e['bytes'] or sha(p)!=e['sha256']:errors.append({'integrity':e['path']})
 if errors:raise SystemExit(json.dumps({'package_integrity':False,'errors':errors}))
 return {'package_integrity':True,'files_checked':len(entries)}
def source_map_arg(path):
 data=json.loads(pathlib.Path(path).read_text()) if path else {}
 if not isinstance(data,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in data.items()):raise SystemExit('SOURCE_MAP_MUST_MAP_ORIGINAL_PATH_TO_LOCAL_PATH')
 return data

def gate_preflight(mapping):
 m=json.loads((ROOT/'task-gates/SOURCE-MANIFEST.json').read_text());missing=[]
 for name,e in m['sources'].items():
  p=pathlib.Path(mapping.get(e['path'],e['path']))
  if not p.is_file():missing.append({'source':name,'original_path':e['path'],'status':'missing','expected_sha256':e['sha256']})
  elif p.stat().st_size!=e['bytes'] or sha(p)!=e['sha256']:missing.append({'source':name,'original_path':e['path'],'status':'hash_mismatch','expected_sha256':e['sha256']})
 return m,missing

def run(command,cwd,env,log):
 with log.open('w') as stream:r=subprocess.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
 return {'command':command,'exit_code':r.returncode,'log':str(log),'log_sha256':sha(log)}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['verify','preflight','alignment','gates']);p.add_argument('--output',type=pathlib.Path);p.add_argument('--source-map',help='JSON original absolute path -> locally restored path; byte identity remains mandatory');args=p.parse_args()
 integrity=package_check();mapping=source_map_arg(args.source_map)
 if args.mode=='verify':print(json.dumps(integrity,indent=2));return 0
 if args.mode=='preflight':
  _,missing=gate_preflight(mapping)
  print(json.dumps({**integrity,'portable_alignment_sources_included':True,'gate_sources_complete':not missing,'gate_missing_or_changed_sources':missing,'third_party_PDF_and_prior_raw_study_not_redistributed':True},indent=2));return 0 if not missing else 2
 if args.output is None:raise SystemExit('--output NEW_DIRECTORY_REQUIRED')
 out=args.output.resolve()
 if out==ROOT or ROOT in out.parents:raise SystemExit('OUTPUT_MUST_BE_OUTSIDE_PACKAGE')
 out.mkdir(parents=True,exist_ok=False)
 env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','BF_HOME':str(out/'isolated-home')}
 results=[]
 if args.mode=='alignment':
  work=out/'alignment-work';shutil.copytree(ROOT/'alignment',work,ignore=shutil.ignore_patterns('runs','__pycache__'))
  original_lock=work/'contracts/source-lock.json';old_bytes=original_lock.read_bytes();lock=json.loads(old_bytes);input_map=json.loads((ROOT/'ALIGNMENT-INPUT-MAP.json').read_text())
  for k,e in lock['sources'].items():
   item=input_map[k];src=ROOT/item['package_path']
   if sha(src)!=e['sha256'] or src.stat().st_size!=e['bytes']:raise SystemExit('PACKAGED_SOURCE_IDENTITY_MISMATCH:'+k)
   e['path']=str(src)
  (out/'original-source-lock.json').write_bytes(old_bytes);original_lock.write_text(json.dumps(lock,indent=2)+'\n')
  env.update({k:str(ROOT/'alignment-inputs'/v) for k,v in [('BF_ALIGNMENT_UPSTREAM','upstream'),('BF_ALIGNMENT_CLOUD','cloud'),('BF_ALIGNMENT_EVENT','event')]})
  results.append(run([sys.executable,'-B','run_alignment.py','--output',str(out/'alignment-run')],work,env,out/'alignment-replay.log'))
  if results[-1]['exit_code']==0:
   results.append(run([sys.executable,'-B','src/canonical_geometry.py'],work,env,out/'canonical-replay.log'))
   results.append(run([sys.executable,'-B','tests/check_settling_recipe.py'],work,env,out/'settling-replay.log'))
  success=all(x['exit_code']==0 for x in results)
  scope='30 differential tests, 72 canonical coordinates, 4 synthetic settling tests. Location-only source-lock derivative; scientific source bytes unchanged. Not full-model equivalence or native execution.'
 else:
  manifest,missing=gate_preflight(mapping)
  if missing:
   (out/'preflight.json').write_text(json.dumps({'missing_or_changed_sources':missing},indent=2)+'\n');print('GATE_SOURCE_PREFLIGHT_BLOCKED; see '+str(out/'preflight.json'));return 2
  work=out/'task-gates-work';shutil.copytree(ROOT/'task-gates',work)
  for e in manifest['sources'].values():e['path']=mapping.get(e['path'],e['path'])
  (work/'SOURCE-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
  results.append(run([sys.executable,'-B','-m','unittest','test_admission','-v'],work,env,out/'gates-tests.log'))
  results.append(run([sys.executable,'-B','admission.py','--output',str(out/'admission.json')],work,env,out/'admission.log'))
  admission=json.loads((out/'admission.json').read_text())
  success=results[0]['exit_code']==0 and results[1]['exit_code']==2 and admission['admitted_task_count']==0
  scope='38 deterministic checks plus source-bound admission. Expected exit2 and 0/2 admitted remain a blocked readiness result.'
 receipt={'schema':'mainline-transition-package-replay-v1','success':success,'scope':scope,'results':results,'package_integrity_after':package_check(),'paid_calls':0,'vendor_tools':[],'formal_Agent_calls':0}
 (out/'replay-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2));return 0 if success else 1
if __name__=='__main__':raise SystemExit(main())
