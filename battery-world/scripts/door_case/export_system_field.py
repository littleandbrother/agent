"""Export an already solved corrected FEM anchor into a new presentation folder.

No solver run, source-model mutation, or COMSOL preference modification.
Setting imagetype last avoids COMSOL's size-setting export-type reset.
"""
import argparse
import json
import shutil
from pathlib import Path
import mph
from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json


def export(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    before = file_hash(source)
    for suffix in ('png', 'glb'):
        old = output / ('magnetic-flux.' + suffix)
        global_view = output / ('magnetic-flux-global.' + suffix)
        if old.exists() and not global_view.exists():
            shutil.copy2(old, global_view)
    client = mph.start(cores=2)
    model = client.load(source)
    try:
        j = model.java
        j.component('c').view().create('presentation_local', 3)
        camera = j.component('c').view('presentation_local').camera()
        camera.set('viewscaletype', 'manual'); camera.set('autoupdate', False)
        camera.set('projection', 'orthographic')
        camera.set('position', [0.14, -0.16, 0.12])
        camera.set('target', [0.024, 0., 0.004])
        camera.set('up', [0., 0., 1.]); camera.set('zoomanglefull', 30.)
        j.result('field').set('view', 'presentation_local')
        exports = []
        for kind, suffix in [('png', 'png'), ('gltf', 'glb')]:
            tag = 'presentation_' + kind
            if tag in list(j.result().export().tags()):
                j.result().export().remove(tag)
            j.result().export().create(tag, 'field', 'Image')
            e = j.result().export(tag)
            dst = output / ('magnetic-flux.' + suffix)
            e.set('pngfilename' if kind == 'png' else 'gltffilename', str(dst))
            e.set('size', 'manualweb'); e.set('unit', 'px')
            e.set('width', '1600'); e.set('height', '1000')
            e.set('zoomextents', 'off'); e.set('options3d', 'on')
            e.set('legend3d', 'on'); e.set('title3d', 'on')
            e.set('imagetype', kind)
            e.run()
            if not dst.is_file() or dst.stat().st_size < 100:
                raise ValueError('NATIVE_FIELD_EXPORT_MISSING:' + str(dst))
            exports.append({'file': dst.name, 'sha256': file_hash(dst), 'bytes': dst.stat().st_size})
        model.save(output / 'field-presentation.mph')
        exports.append({'file': 'field-presentation.mph', 'sha256': file_hash(output / 'field-presentation.mph'),
                        'bytes': (output / 'field-presentation.mph').stat().st_size})
    finally:
        client.remove(model)
    if before != file_hash(source):
        raise ValueError('SOLVED_MODEL_CHANGED_DURING_PRESENTATION')
    receipt = {'source_model': str(source), 'source_mph_sha256': before,
               'exports': exports, 'solver_rerun': False, 'native_export': True,
               'presentation_transform': 'Local orthographic camera only; full-air view retained separately. Physics and solved field not changed.',
               'scope': 'Corrected finite-air rotated driver field at one trajectory anchor; neutral tip probe, no full assembly/strain/physical calibration.'}
    write_json(output / 'field-export-receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    print(json.dumps(export(a.source, a.output)))
