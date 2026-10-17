#!/usr/bin/env python3
"""Offline receipt checks. Reads saved answers/results; invokes no external service."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    p.add_argument('directory',type=Path,help='Report or extracted bundle directory containing data/')
    args=p.parse_args();root=args.directory.resolve()
    def read(name):return json.loads((root/'data'/name).read_text())
    checks=[]
    def check(name,value):
        if not value:raise ValueError(name)
        checks.append(name)
    manifest=root/'MANIFEST.json'
    if manifest.exists():
        for row in json.loads(manifest.read_text())['files']:
            f=root/row['path']
            check('hash:'+row['path'],f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest()==row['sha256'])
    questions=read('question-bank/requests.json')
    check('48 unique requests',len(questions)==len({r['id'] for r in questions})==48)
    first=read('intake-results.json');second=read('intake-results-v2.json')
    check('initial valid',sum(x['schema_valid'] for x in first['results'])==10)
    check('flat example valid',sum(x['schema_valid'] for x in second['results'])==44)
    check('intent agreement',sum(x['metrics']['intent'] for x in second['results'])==45)
    edge=read('edge-checks/result.json');check('edge validity',sum(x['valid'] for x in edge['results'])==13)
    m=read('mechanisms/result.json')
    check('90 alias pairs',m['aliasing_pairs']==90)
    check('static false accepts',m['tables']['test']['static-budget']['false_accept']==36)
    check('strong baseline tied',m['tables']['test']['fixed-event-contract']==m['tables']['test']['counterexample-refinement'])
    check('30 reversed rankings',len(m['replay'])==30 and all(x['child_frozen']>x['parent_packets']>x['child_full'] for x in m['replay']))
    check('scope matches',all(x['child_scoped']==x['child_full'] and x['scoped_energy_error']<1e-8 for x in m['replay']))
    check('work saving',sum(x['scoped_work'] for x in m['replay'])==.75*sum(x['full_work'] for x in m['replay']))
    controls=read('mechanisms-controls/result.json')
    check('native anchors',len(controls['native_anchors'])==6 and all(x['same_judgment'] for x in controls['native_anchors']))
    check('negative controls',controls['controls']=={'zero':False,'ample':True,'invalid_information':False})
    method=read('method-pilot-v2/result.json')
    check('six method configurations',len(method['candidates'])==6)
    check('method tied',method['test']['selected']==method['test']['fixed-rich-causal'])
    probe=read('default/vendor-probe/result.json')
    check('native cold startup failure',not probe['service_passed'] and len(probe['valid_sequences'])==0 and 18.20<probe['startup_2p3v_s']<18.22)
    p08=read('p08/readback.json')
    check('P08 no dispatch',p08['new_native_runs']==0)
    errors=[abs(100*(x['native_us']/x['paper_us']-1)) for x in p08['rows']]
    check('P08 error',len(errors)==6 and abs(max(errors)-.5264707728292795)<1e-8)
    usage=read('usage.json')
    check('167 settled requests',usage['total_new_model_requests']==167 and usage['requests']==usage['settled']==121)
    check('preservation',read('preservation.json')['passed'])
    print(json.dumps({'status':'PASS','checks':len(checks),'model_requests_added':0,'native_jobs_dispatched':0,
                      'reports':str(root)},ensure_ascii=False))


if __name__=='__main__':main()
