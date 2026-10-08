"""Verify an actual Studio download against the original delivery seal.

Replays only the fixed figure renderer in a new directory. Native physics and
Agent credit are not inferred from a portable presentation export.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(archive, expected, output, python):
    archive, expected, output, python = map(Path, (archive, expected, output, python))
    if output.exists():
        raise ValueError('DELIVERY_VERIFICATION_NEEDS_FRESH_DIRECTORY')
    output.mkdir(parents=True)
    seal = json.loads(expected.read_text())
    folder = output / 'extracted'
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        seals = [n for n in names if Path(n).name == 'seal.json']
        if len(seals) != 1 or z.read(seals[0]) != expected.read_bytes():
            raise ValueError('DELIVERY_SEAL_NOT_EXPECTED')
        if z.testzip(): raise ValueError('DELIVERY_CRC')
        base = seals[0][:-len('seal.json')]
        for name in names:
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('DELIVERY_ZIP_PATH')
        for record in seal['files']:
            data = z.read(base + record['path'])
            if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('DELIVERY_SOURCE_CHANGED:' + record['path'])
            dest = folder / record['path']; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        (folder / 'seal.json').write_bytes(expected.read_bytes())
    report = folder / 'report'
    index = json.loads((report / 'figure-index.json').read_text())
    if index['counts'] != {'available': 66, 'missing': 4, 'not_applicable': 0}:
        raise ValueError('DELIVERY_GAP_COUNT_CHANGED')
    if index['source_identity'] != seal['source_identity']:
        raise ValueError('DELIVERY_IDENTITY')
    progress = json.loads((folder / 'paper/final-progress.json').read_text())
    if (progress['predeclared_denominator'], progress['all_actors_independent_passed'],
        progress['agent_independent_passed'], progress['target_80_percent_reached']) != (20, 14, 1, False):
        raise ValueError('DELIVERY_TASK_CREDIT_DRIFT')
    # Absolute original receipt locators can be resolved by content hash in the
    # portable seal; do not pretend the native runtime/path configuration moved.
    byhash = {}
    for f in seal['files']: byhash.setdefault(f['sha256'], []).append(f['path'])
    unresolved = [(task['id'], e['path']) for task in progress['tasks']
                  for e in task.get('record', {}).get('evidence', []) if e['sha256'] not in byhash]
    if unresolved: raise ValueError('DELIVERY_TASK_EVIDENCE_ABSENT:' + str(unresolved))
    fem = json.loads((folder / 'verification/corrected-fem-anchors.json').read_text())
    for a in fem['anchors']:
        local = folder / 'native/fem-corrected' / a['name']
        if sha(local / 'RotatedField.java') != a['source_sha256']:
            raise ValueError('DELIVERY_FEM_SOURCE_CHANGED')
        models = list(local.glob('*.mph'))
        if len(models) != 1 or sha(models[0]) != a['model_sha256']:
            raise ValueError('DELIVERY_FEM_MODEL_CHANGED')
    if sha(report / 'door-evidence-report.pdf') != seal['report']['sha256']:
        raise ValueError('DELIVERY_PDF_CHANGED')
    redraw = output / 'redraw'
    renderer = report / 'scientific_renderer.py'
    proc = subprocess.run([str(python), str(renderer), str(report / 'reproduce-plan.json'), str(redraw)],
                          capture_output=True, text=True, timeout=240)
    (output / 'redraw.stdout').write_text(proc.stdout)
    (output / 'redraw.stderr').write_text(proc.stderr)
    if proc.returncode: raise ValueError('DELIVERY_REDRAW_FAILED:' + proc.stderr[-1500:])
    graphics = {g[k] for g in index['groups'] for k in ('figure', 'pdf', 'vector')}
    graphics.update(p[k] for p in index['panels'] for k in ('figure', 'pdf', 'vector'))
    if any(sha(report / path) != sha(redraw / path) for path in graphics):
        raise ValueError('DELIVERY_GRAPHICS_NOT_IDENTICAL')
    corrupted = output / 'tampered-figure-inputs'
    shutil.copytree(report, corrupted)
    plan = json.loads((corrupted / 'reproduce-plan.json').read_text())
    source = corrupted / plan['sources'][0]['path']
    source.write_bytes(source.read_bytes() + b'changed')
    control = subprocess.run([str(python), str(corrupted / 'scientific_renderer.py'),
                              str(corrupted / 'reproduce-plan.json'), str(output / 'must-reject')],
                             capture_output=True, text=True, timeout=60)
    if control.returncode == 0 or 'FIGURE_SOURCE_CHANGED' not in control.stderr:
        raise ValueError('DELIVERY_TAMPER_NOT_REJECTED')
    (output / 'tamper.stderr').write_text(control.stderr)
    receipt = {'schema_version': 'bf-system-delivery-verification-v1', 'archive': str(archive),
               'archive_sha256': sha(archive), 'archive_entries': len(names), 'version': seal.get('version', 'E3'),
               'verified_sealed_files': len(seal['files']), 'crc_and_hashes': True,
               'fem_native_models_verified': len(fem['anchors']), 'task_evidence_resolvable_by_hash': True,
               'graphics_byte_identical': len(graphics), 'redraw_identical': True,
               'tamper_rejected': True, 'source_identity': index['source_identity'],
               'report': seal['report'], 'physical_qualification': False,
               'autonomous_80_percent_reproduction': False,
               'scope': 'Actual browser download; original seal, native model identities, portable numeric graphics, and corruption control. Not a reexecution of native solvers or physical experiment.'}
    (output / 'verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('archive', 'expected', 'output', 'python'): p.add_argument('--' + name, type=Path, required=True)
    print(json.dumps(verify(**vars(p.parse_args())), ensure_ascii=False))
