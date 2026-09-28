#!/usr/bin/env python3
"""Persist one inspectable UNPAID scripted matrix on already-public tasks."""
import json
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'packages/python/bfworld/src'))
from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.campaign.trials import VERSION, ARMS, TOOLS, history_from_runs, run_matrix
from bfworld.campaign.repair import checked


class DemonstrationControl:
    decision_origin = 'scripted-unpaid-control'
    implementation_hash = file_hash(Path(__file__))
    configuration_hash = canonical_hash({'policy': 'explicit scripted scan; no LLM, no learned policy'})

    def __call__(self, request):
        context = json.loads(request['messages'][1]['content'])
        observations = [json.loads(m['content'])['tool_result'] for m in request['messages'][2:] if m['role'] == 'user']
        successful = next((r for r in observations if r.get('physical_pass')), None)
        if successful:
            return {'action': 'submit', 'candidate_id': successful['candidate_id'], 'claim_pass': True,
                    'evidence_hash': successful['content_hash'], 'decision_summary': 'Scripted submission of passing local evidence.'}
        if request['turn'] == 0:
            return {'action': 'python', 'code': "def plan(ctx): return {'design_count':len(ctx['task']['candidates'])}",
                    'decision_summary': 'Same Python tool available in every participant condition.'}
        tried = {o['candidate_id'] for o in observations if 'run_hash' in o}
        remaining = [c for c in context['task']['candidates'] if c['id'] not in tried]
        if not remaining:
            return {'action': 'abstain', 'reason': 'Exhausted public catalogue.'}
        # This policy intentionally does NOT claim it learned from text/code.
        # The installed code executes and its output is visible, but this fixed
        # controller merely scans. A treatment invocation is not a use benefit.
        return {'action': 'experiment', 'candidate_id': remaining[0]['id'], 'predicted_pass': True,
                'decision_summary': 'Optimistic scripted prediction; compare with actual observation.'}


def main():
    source = checked(json.loads((REPO/'docs/b2-development/profiled-report.json').read_text()))
    tasks = {t['task_id']: t for t in source['registry']['tasks']}
    past, task, final = [tasks[k] for k in ('public-long-tx', 'public-long-sense', 'public-shifted-source')]
    row = next(r for r in source['runs'] if r['task_id'] == past['task_id'] and r['candidate_id'] == 'small')
    run = json.loads((REPO/row['artifact']/'run.json').read_text())
    history = history_from_runs([(past, 'small', run)])
    candidate = {'schema_version': 'world-model-patch-v1', 'kind': 'world-model', 'scope': {'source_families': ['rotary']},
                 'code': "def plan(ctx):\n    if not isinstance(ctx,dict) or ctx.get('source_family')!='rotary' or not isinstance(ctx.get('conditions'),dict) or not ctx.get('candidates'):\n        return {'scope_ok':False,'predictions':{}}\n    return {'scope_ok':True,'predictions':{c['id']:{'verdict':'abstain','reason':'Engineer-authored plumbing control; no learned claim.'} for c in ctx['candidates']}}"}
    capsule = {'history_hash': history['content_hash'], 'candidate': candidate,
               'text_lesson': 'The small design failed under a 200 ms TX in a public computational run. This alone does not establish transfer to a longer sense window.',
               'engineering_activation': {'candidate_hash': canonical_hash(candidate), 'enabled': True, 'scope': 'engineering-interface-only'}}
    plan = {'schema_version': VERSION, 'purpose': 'engineering-controls', 'arms': ARMS, 'tools': TOOLS,
            'max_turns': 6, 'max_experiments': 3, 'candidate_order_rule': 'stable-capacitance-ascending',
            'session_namespace': 'public-unpaid-plumbing-control', 'history_hash': history['content_hash'],
            'task_hash': task['content_hash'], 'confirmation_hash': final['content_hash'], 'capsule_hash': canonical_hash(capsule)}
    identity = canonical_hash({'plan': plan, 'source_hash': source['content_hash'],
                               'builder_hash': file_hash(Path(__file__)),
                               'runner_hash': file_hash(REPO/'packages/python/bfworld/src/bfworld/campaign/trials.py')})
    root = REPO/'.bfworld/matched-trial-controls'/identity.split(':')[1]
    report = run_matrix(plan, task, final, history, capsule, DemonstrationControl(), root)
    projection = {'schema_version': 'inspectable-trial-control-v1', 'source_report_hash': source['content_hash'],
                  'artifact_root': str(root.relative_to(REPO)), 'report': report,
                  'claim_boundary': 'Already-public conditions, scripted scan, deliberately all-abstain knowledge. No Agent or transfer benefit.'}
    projection['content_hash'] = canonical_hash(projection)
    write_canonical_json(REPO/'docs/b2-development/matched-trial-control.json', projection)
    print(json.dumps({'artifact_root': str(root), 'report_hash': report['content_hash'], 'provider_calls': 0,
                      'arms': [t['arm'] for t in report['trials']], 'transfer_validated': False}))


if __name__ == '__main__': main()
