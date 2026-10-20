"""Generate manuscript numbers solely from sealed campaign data and its audit."""
from pathlib import Path
import csv
import json

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1]/'docs/research/parallel-20261019/methods'
q = json.loads((DATA/'f1a-controls.json').read_text())
rows = q['rows']
bad = sum(not r['fixed_matches_full'] for r in rows)
text = (f'\nIn the executed deterministic controls, fixed-trajectory replay disagrees '
        f'with the full response on {bad} of {len(rows)} inputs. The conservative '
        f'dependency, boundary, and exact-cache results agree on all {len(rows)}. '
        'Only the unchanged input is an initial exact-cache hit. These are synthetic '
        'correctness controls; execution counts do not measure wall-time speedup.\n')
text += '\\begin{center}\n\\begin{tabular}{lrrr}\n\\toprule\nInput & Replay packets & Full packets & Replay valid\\\\\n\\midrule\n'
for r in rows:
    text += f"{r['case']} & {r['fixed_trajectory']['packets']} & {r['full']['packets']} & {r['fixed_trajectory']['admissible']}\\\\\n"
text += '\\bottomrule\n\\end{tabular}\n\\end{center}\n'
(HERE/'results.tex').write_text(text)

audit = json.loads((DATA/'paid-audit.json').read_text())
paid = audit['rows']
assert len(paid)==4 and audit['same_harness'] and audit['normalized_core_match']
calls = sum(r['requests'] for r in paid)
upper = sum(r['cost_upper_bound_usd'] for r in paid)
estimate = sum(r['cache_aware_estimate_usd'] for r in paid)
completed = sum(r['delivered'] and r['task_passed'] for r in paid)
native = sum(r['native_dispatches'] for r in paid)
candidates = sum(r['candidate_evaluations'] for r in paid)
censored = [r for r in paid if r['resource_censored']]
assert len(censored)==1 and censored[0]['attempt']=='H0-r2'
paid_text = ('\n\\paragraph{Observed attempts and resource stop.} '
             f'All {len(paid)} fresh controllers consumed their assigned goal, started with '
             'zero prior trajectory messages, and changed the initial firmware. '
             'After administrative identifiers are normalized, the base prompts match; '
             'the harness, task, initial device, and physical cache start are identical. '
             f'{completed} attempts completed all six computational qualification gates and delivery. '
             'The last attempt, $H_0$-r2, completed its native numerical execution but hit the '
             'frozen 5 GB free-space gate before validation and release. It stopped after '
             f"{censored[0]['decision_wall_s']:.3f} seconds and was not resampled. "
             'Its pending qualification is not converted into a device failure or a pass.\n')
paid_text += '\\begin{center}\n{\\small\\begin{tabular}{lrrrrrl}\n\\toprule\nAttempt & Requests & USD upper & Executions & Native & Frames & Outcome\\\\\n\\midrule\n'
for r in paid:
    frames = '--' if r['received_frames'] is None else str(r['received_frames'])
    outcome = 'STOP' if r['resource_censored'] else 'PASS' if r['delivered'] and r['task_passed'] else 'FAIL'
    paid_text += f"{r['attempt']} & {r['requests']} & {r['cost_upper_bound_usd']:.6f} & {r['candidate_evaluations']} & {r['native_dispatches']} & {frames} & {outcome}\\\\\n"
paid_text += '\\bottomrule\n\\end{tabular}}\n\\end{center}\n'
paid_text += (f'Across all attempted owners, including the stop, {calls} requests settled '
              f'with no missing provider usage or unresolved reservation. Their conservative '
              f'charge upper bound is USD {upper:.6f}; the rate-based cache-aware estimate '
              f'is USD {estimate:.6f}, not an invoice. The {candidates} candidate executions '
              f'used {native} new native dispatches. Each newly solved input is disjoint '
              'from earlier successful native inputs; applicable exact inputs were reused. '
              'The sixteen-entry initial cache was copied without new solves. Its historical '
              'construction bill is unknown, not zero. Operator proposal and Codex supervision, '
              'executor-chat, and writing costs are outside the BF ledger; these attempt '
              'charges cannot establish end-to-end improvement efficiency.\n\n'
              'Both $H_1$ confirmations delivered, using twenty requests each; the completed '
              '$H_0$-r1 used thirteen. The interrupted second $H_0$ prevents a completed '
              'arm comparison. We preserve $H_1$ as an experimental artifact, keep the default '
              'method unchanged, and make no success-rate, cost, speedup, transfer, or recursive '
              'improvement claim. Provider and OS caches were uncontrolled; setup and subsequent '
              'wall times remain separate in the audit.\n')
(HERE/'paid-results.tex').write_text(paid_text)
with (HERE/'results.csv').open('w',newline='') as out:
    w=csv.writer(out);w.writerow(['case','replay_packets','full_packets','replay_admissible','matches_full'])
    for r in rows:
        w.writerow([r['case'],r['fixed_trajectory']['packets'],r['full']['packets'],r['fixed_trajectory']['admissible'],r['fixed_matches_full']])
(HERE/'claim-index.json').write_text(json.dumps({'schema_version':'campaign-paper-claims-v1','claims':[
    {'claim':'Fixed replay can fail after a feedback-dependent D intervention','status':'SUPPORTED_PUBLIC_CONTROL',
     'data':str(DATA/'f1a-controls.json'),'code':'reexecution.py','section':'F1a'},
    {'claim':'Assigned H was consumed in fresh design decisions','status':'AUDITED_FOUR_STARTS_THREE_DELIVERIES_ONE_RESOURCE_STOP',
     'data':str(DATA/'paid-audit.json'),'section':'F1b and early F4'},
    {'claim':'H1 improves design quality or cost','status':'NOT_ESTABLISHED_RESOURCE_CENSORED',
     'data':str(DATA/'paid-audit.json'),'decision':audit['retention'],'section':'F1b and early F4'},
    {'claim':'Recursive improvement and transfer','status':'NOT_TESTED','section':'Remaining experiments'}]},indent=2)+'\n')
print(json.dumps({'deterministic_inputs':len(rows),'fixed_replay_disagreements':bad,
                  'paid_attempts':len(paid),'delivered':completed,'resource_censored':len(censored),
                  'requests':calls,'cost_upper_bound_usd':upper}))
