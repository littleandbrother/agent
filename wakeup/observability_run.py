"""36 fresh Legacy runs; original apparatus/loops, only feedback projection changes."""
import argparse
import concurrent.futures as cf
import copy
import http.server
import json
import math
import multiprocessing
import os
import random
import statistics
import threading
from pathlib import Path

import attribution_run as legacy
import attribution_physics as physics
import funnel_run as host

HERE = Path(__file__).resolve().parent
OUT = HERE / 'observability'
ORIGINAL_FEEDBACK = physics.feedback


def feedback(task, x, result):
    value = ORIGINAL_FEEDBACK(task, x, result)
    if task['feedback_level'] == 'gateway_only':
        value.pop('measurements')
        value['terminal'] = {k: value['terminal'][k] for k in ('faults', 'delivered_on_time', 'false_reports')}
        value['slack'] = {k: value['slack'][k] for k in ('stress', 'travel')}
    return value


def report():
    rows = [json.loads(p.read_text()) for p in sorted((OUT/'runs').glob('*/terminal.json'))]
    events = [json.loads(s) for p in sorted((OUT/'runs').glob('*/events.jsonl')) for s in p.read_text().splitlines()]
    replies = [e for e in events if e['kind'] == 'response']
    scientific = [e for e in events if e['kind'] == 'evaluation']
    cells = []
    for arm in ('L', 'A'):
        for level in ('gateway_only', 'original_p'):
            q = [r for r in rows if r['arm'] == arm and r['selection_id'].endswith(level)]
            steps = [r['first_pass'] for r in q if r['first_pass'] is not None]
            cells.append(dict(arm=arm, feedback_level=level, completed=len(q), found=len(steps),
                selected=sum(r['selected_pass'] for r in q), first_pass_median=statistics.median(steps) if steps else None,
                errors=sum(bool(r['error']) for r in q)))
    paired = []
    for arm in ('L', 'A'):
        by = {(r['task'], r['selection_id'].split('-', 2)[-1]): r for r in rows if r['arm'] == arm}
        pairs = [(by[t, 'gateway_only'], by[t, 'original_p']) for t in sorted({r['task'] for r in rows})
                 if (t, 'gateway_only') in by and (t, 'original_p') in by]
        for metric in ('found', 'selected'):
            values = [(g['first_pass'] is not None, p['first_pass'] is not None) if metric == 'found'
                      else (g['selected_pass'], p['selected_pass']) for g, p in pairs]
            gw_only = sum(g and not p for g, p in values)
            p_only = sum(p and not g for g, p in values)
            n = gw_only+p_only
            exact = min(1., 2*sum(math.comb(n, i) for i in range(min(gw_only,p_only)+1))/2**n) if n else 1.
            paired.append(dict(arm=arm,metric=metric,paired=len(pairs),both=sum(g and p for g,p in values),
                gateway_only=gw_only, original_p_only=p_only, neither=sum(not g and not p for g,p in values),
                exact_two_sided_p=exact))
    summary = dict(completed=len(rows), expected=len(json.loads((OUT/'tasks.json').read_text()))*2,
        cells=cells,paired=paired,rows=rows,accounting=dict(
            requests=sum(e['kind']=='request' for e in events), responses=len(replies),
            usage={k:sum(e['response']['usage'].get(k,0) for e in replies) for k in
                ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens')},
            estimated_usd=sum(e['estimated_usd'] for e in replies),
            unknown=[{k:e.get(k) for k in ('job','id','error','reservation_usd')} for e in events if e['kind']=='UNKNOWN']),
        science=dict(attempts=sum(e['kind']=='evaluation_request' for e in events), returned=len(scientific),
            new_full=sum(e['result']['cost']['full'] for e in scientific),reused=sum(e['result']['reused'] for e in scientific)))
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--report',action='store_true')
    parser.add_argument('--feedback_level',choices=['both','gateway_only','original_p'],default='both')
    args = parser.parse_args()
    if args.report:
        print(json.dumps(report()['cells'],ensure_ascii=False));return
    if not args.run:
        parser.error('Use --run or --report')
    if list((OUT/'runs').glob('*/events.jsonl')):
        raise SystemExit('This fresh experiment has already started; do not rerun its cells.')
    OUT.mkdir(exist_ok=True)
    levels = ('gateway_only','original_p') if args.feedback_level=='both' else (args.feedback_level,)
    selection=json.loads((HERE/'attribution'/'legacy-selection.json').read_text())['selected_pairs']
    unique={}
    for p in selection:
        unique.setdefault(p['instance_id'],p['selection_id'])
    initial=json.loads((HERE/'attribution'/'initial.json').read_text())
    tasks=[]
    for sid in unique.values():
        for level in levels:
            task=physics.make_task(sid,'direct','narrow')
            task.update(feedback_level=level,selection_id=sid+'-'+level)
            tasks.append(task)
    (OUT/'tasks.json').write_text(json.dumps(tasks,ensure_ascii=False,indent=2)+'\n')
    # One common saved result through the same projection used by all three public paths.
    t=tasks[0];r=initial[t['id']+'-direct-narrow'];original=ORIGINAL_FEEDBACK(t,t['initial'],r)
    g=feedback(t|dict(feedback_level='gateway_only'),t['initial'],r)
    assert 'measurements' not in g and set(g['slack'])=={'stress','travel'} and 'brownouts' not in g['terminal']
    assert feedback(t|dict(feedback_level='original_p'),t['initial'],r)==original
    free=os.statvfs(OUT).f_bavail*os.statvfs(OUT).f_frsize
    (OUT/'run-settings.json').write_text(json.dumps(dict(
        instances=list(unique),selection_ids=list(unique.values()),arms=['L','A'],feedback_levels=levels,
        model='deepseek-flash',thinking='high',design_evaluations=6,model_responses=64,
        output_tokens=262144,request_output=32768,episode_wall_s=1800,usd_cap=3,
        conversations=len(tasks)*2,physics_workers=8,full_attempt_cap=len(tasks)*12,
        available_bytes=free,peak_additional_bytes=500000000,retained_output_cap_bytes=100000000,
        initial_results='Reused unchanged saved direct/narrow initial results; zero new initials.',
        source_loop='attribution_run.Episode unchanged',projection_check='PASS; zero API/physics'),ensure_ascii=False,indent=2)+'\n')
    legacy.OUT=host.OUT=OUT
    host.SYSTEM,host.schemas,host.CAP=legacy.SYSTEM,legacy.schemas,3.
    host.KEY=(Path.home()/'.local/share/bf-campaign-20261019-s0/workbench/secrets/deepseek.key').read_text().strip()
    physics.feedback=feedback
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),host.Proxy);host.PORT=server.server_port
    threading.Thread(target=server.serve_forever,daemon=True).start()
    jobs=[(t,a) for t in tasks for a in ('L','A')]
    random.Random(20261112).shuffle(jobs)
    with cf.ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context('spawn')) as host.PHYSICS:
        with cf.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures=[pool.submit(lambda t=t,a=a:legacy.Episode(t,a,6,copy.deepcopy(initial[t['id']+'-direct-narrow'])).run()) for t,a in jobs]
            for future in cf.as_completed(futures):
                future.result();report()
    server.shutdown()
    print(json.dumps(report()['cells'],ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
