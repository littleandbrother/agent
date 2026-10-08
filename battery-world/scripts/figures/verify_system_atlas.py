"""Independent D4/E3 source, numeric-display and fresh-process redraw check."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify(root, redraw, presentation=None):
    root, redraw = Path(root).resolve(), Path(redraw).resolve()
    presentation = Path(presentation).resolve() if presentation else root / 'presentation'
    output = presentation / 'report'
    index = json.loads((output / 'figure-index.json').read_text())
    plan = json.loads((output / 'figure-plan.json').read_text())
    sources = json.loads((output / 'figure-sources.json').read_text())
    lookup = {s['id']: {k: v for k, v in s.items() if k != 'archive_file'} for s in sources}
    if [len(g['panels']) for g in index['groups']] != [12, 12, 12, 12, 12, 10]:
        raise ValueError('E3_PANEL_DENOMINATOR_DRIFT')
    counts = {s: sum(p['status'] == s for p in index['panels']) for s in ('available', 'missing', 'not_applicable')}
    if counts != {'available': 66, 'missing': 4, 'not_applicable': 0} or counts != index['counts']:
        raise ValueError('E3_GAP_PROMOTED')
    if hashlib.sha256(json.dumps(plan['sources'], sort_keys=True).encode()).hexdigest() != index['source_identity']:
        raise ValueError('E3_INPUT_IDENTITY')
    for source in sources:
        if sha(output / source['archive_file']) != source['sha256']:
            raise ValueError('E3_SOURCE_CHANGED:' + source['id'])
    for panel in index['panels']:
        if json.loads((output / panel['provenance']).read_text()) != panel:
            raise ValueError('E3_PROVENANCE_CHANGED:' + panel['id'])
        sid = hashlib.sha256(json.dumps([lookup[s] for s in panel['dependencies']], sort_keys=True).encode()).hexdigest()
        if sid != panel['source_identity']:
            raise ValueError('E3_PANEL_SOURCE_IDENTITY')
    ref = root / 'sealed-reference-v2'
    result = json.loads((ref / 'result.json').read_text())
    with (ref / 'waveform.csv').open() as f:
        values = list(csv.DictReader(f))
    peak = max(float(row['storage_V']) for row in values)
    if abs(peak-result['metrics']['peak_storage_V']) / result['metrics']['peak_storage_V'] > .01:
        raise ValueError('E3_RAW_SAMPLE_DISAGREEMENT')
    if result['metrics']['tx_completed'] != 0 or result['metrics']['received_events'] != 0:
        raise ValueError('E3_FAILED_REFERENCE_CHANGED')
    renderer = Path(__file__).parents[2] / 'packages/python/bfworld/src/bfworld/agentlab/scientific_renderer.py'
    shutil.copy2(renderer, output / 'scientific_renderer.py')
    if redraw.exists():
        raise ValueError('E3_REDRAW_DIRECTORY_MUST_BE_FRESH')
    # A new standalone process consumes only hashed, relocated source copies.
    proc = subprocess.run([sys.executable, str(output / 'scientific_renderer.py'),
                           str(output / 'reproduce-plan.json'), str(redraw)],
                          capture_output=True, text=True, timeout=240)
    if proc.returncode:
        raise ValueError('E3_REDRAW_FAILED:' + proc.stderr[-3000:])
    graphics = {g[k] for g in index['groups'] for k in ('figure', 'pdf', 'vector')}
    graphics.update(p[k] for p in index['panels'] for k in ('figure', 'pdf', 'vector'))
    differences = [name for name in sorted(graphics) if sha(output / name) != sha(redraw / name)]
    if differences:
        raise ValueError('E3_REDRAW_NOT_IDENTICAL:' + ','.join(differences))
    receipt = {'schema_version': 'bf-system-atlas-verification-v1', 'status': 'passed',
               'groups': 6, 'planned_panels': 70, 'counts': counts, 'sources': len(sources),
               'graphics_byte_identical': len(graphics), 'redraw_identical': True,
               'source_identity': index['source_identity'], 'renderer_sha256': sha(renderer),
               'sampling_peak_storage_V': peak, 'raw_peak_storage_V': result['metrics']['peak_storage_V'],
               'sampling_peak_tolerance_relative': .01,
               'physical_qualification': False, 'autonomous_80_percent_reproduction': False,
               'scope': 'Relocated sources, numeric units and exact fresh-process graphics replay in this declared font/library environment; not native solver/physical replay.',
               'visual_inspection': 'All six groups and full-size native/individual numerical panels reviewed; historical conditions and four gaps retained.'}
    (presentation / 'verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--redraw', type=Path, required=True); p.add_argument('--presentation', type=Path); a = p.parse_args()
    print(json.dumps(verify(a.root, a.redraw, a.presentation)))
