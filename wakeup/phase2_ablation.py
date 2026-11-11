"""Fourteen D-field ablations; reuse the Phase-2 model loop and physical cache."""
import json
import random
import sys
from pathlib import Path

import phase2 as runner
import phase2_physics as physics

OUT = Path(__file__).with_name('phase2_ablation')
FIELDS = dict(PA=['main_background_response', 'aux_target_response'], EW=['event_windows'])
original_view = physics.view


def view(task, design, result, condition):
    public = original_view(task, design, result, 'P')
    public['diagnostic'] = {key: result['diagnostic'][key] for key in FIELDS[condition]}
    return public


def prepare():
    OUT.mkdir(exist_ok=True)
    manifest = OUT / 'jobs.json'
    if not manifest.exists():
        old = [json.loads(line) for line in runner.JOURNAL.read_text().splitlines()]
        terminals = {(r['task'], r['rep'], r['condition']): r for r in old
                     if r['kind'] == 'terminal' and r['stage'] == 'A1'}
        tasks = {j['task']['id']: j['task'] for j in json.loads((runner.OUT / 'jobs.json').read_text())
                 if j['stage'] == 'A1'}
        jobs = []
        for (task, rep, arm), p in sorted(terminals.items()):
            d = terminals.get((task, rep, 'D'))
            if arm != 'P' or p['error'] or p['pass_'] or not d or d['error'] or not d['pass_']:
                continue
            for condition in FIELDS:
                jobs.append(dict(stage='B', round=1, task=tasks[task], condition=condition, rep=rep,
                                 historical_pair=dict(P=p['job'], D=d['job'])))
        random.Random(20261111).shuffle(jobs)
        manifest.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + '\n')
    original_keys = set(physics.STATE['cache'])
    delta = OUT / 'physics.json'
    if delta.exists():
        physics.STATE['cache'].update(json.loads(delta.read_text()))

    def save_new():
        delta.write_text(json.dumps({k: v for k, v in physics.STATE['cache'].items()
                                    if k not in original_keys}) + '\n')

    physics._save = save_new
    physics.view = view
    runner.OUT, runner.JOURNAL = OUT, OUT / 'results.jsonl'
    runner.CAPS = dict(B=4.)
    return json.loads(manifest.read_text())


if __name__ == '__main__':
    jobs = prepare()
    print(f'{len(jobs)} frozen conversations; PA=amplitude/phase, EW=event windows', flush=True)
    if '--run' in sys.argv:
        runner.run(1)
