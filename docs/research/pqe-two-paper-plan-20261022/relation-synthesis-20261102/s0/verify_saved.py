"""Repeatable metadata integrity check; never launches science or a provider."""
from common import *


def checked_ref(value):
    path=Path(value['path'])
    if not path.is_absolute():
        path=ROOT/path
    assert ref(path)['sha256']==value['sha256'],str(path)


def run():
    verified=load(HERE/'verification.json')
    result=load(HERE/'result.json')
    costs=load(HERE/'cost-closeout.json')
    assert verified['status']=='PASS'
    assert verified['resources']==result['resources']==costs['resources']
    count=0
    for key in ('stage1','stage2','component_closure_implementation','comparison','cost_closeout'):
        checked_ref(result[key]);count+=1
    plots=load(OUT/'figures/plot-data.json')
    for item in plots['sources']+[plots['script']]:
        checked_ref(item);count+=1
    checked_ref(plots['metadata_interpretation']);count+=1
    totals=HERE/'resource-total.json'
    if totals.exists():
        total=load(totals)
        final_resources=total['resources']
        for key,value in result['resources'].items():
            expected=value+total['additional_exit_checks'] if key in {'software_checks','software_S0'} else value
            assert final_resources[key]==expected
        assert final_resources['software_checks']<=24
        checked_ref(result['final_resource_total']);count+=1
    final=HERE/'final-readback.json'
    if final.exists():
        close=load(final)
        for item in close['reviewed_refs']:
            checked_ref(item);count+=1
        assert close['new_science']==close['new_provider']==0
    print(json.dumps(dict(status='PASS',checked_artifact_refs=count,
        new_science=0,new_provider=0,scope='Saved result, figure and final review metadata integrity; no live billing or scientific rerun.')))


if __name__=='__main__':
    run()
