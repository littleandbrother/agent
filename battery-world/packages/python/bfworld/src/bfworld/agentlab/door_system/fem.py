"""Rotated FEM anchoring; no replacement of the field by fitted success values."""
import json
import numpy as np
from pathlib import Path
from .model import coordinates, field_energy
from ..simulation_chain.native import command
from ..simulation_chain.contracts import write_json, file_hash
from ..runtime_config import COMSOL

def anchor(directory, design, angle_deg, tip_m, readback_only=False):
    directory.mkdir(parents=True, exist_ok=True); angle = np.deg2rad(angle_deg)
    dx, dz = coordinates(angle, design['mechanical']); dz -= tip_m
    expected = field_energy(angle, tip_m, design['mechanical'], n=12)[0][[0, 2]]
    source = Path(__file__).with_name('RotatedField.java').read_text()
    for key, value in {'DX': dx, 'DZ': dz, 'ANGLE': angle, 'RAIR': max(220.,np.hypot(dx,dz)*1000+100), 'POLARITY': design['mechanical']['polarity'], 'OUTPUT': directory}.items():
        source = source.replace('__'+key+'__', str(value))
    java = directory/'RotatedField.java'
    if readback_only:
        import hashlib
        if file_hash(java) != hashlib.sha256(source.encode()).hexdigest(): raise ValueError('FEM_READBACK_SOURCE_CHANGED')
    else:
        if java.exists(): raise ValueError('FEM_DIRECTORY_EXISTS; use readback or a new directory')
        java.write_text(source)
        write_json(directory/'anchor-input.json', {'design_id': design['design_id'], 'angle_deg': angle_deg,
                   'tip_m': tip_m, 'dx_m': dx, 'dz_m': dz, 'source_sha256': file_hash(java), 'reference_N': expected.tolist()})
        command([COMSOL, 'compile', java], directory, 'compile', 120)
        command([COMSOL, '-np', '2', 'batch', '-inputfile', java.with_suffix('.class'),
                 '-outputfile', directory/'model.mph', '-batchlog', directory/'solver.log'], directory, 'solve', 1200)
    log = '\n'.join((directory/n).read_text(errors='replace') for n in ('solve.log', 'solver.log') if (directory/n).exists())
    models = list(directory.glob('model*.mph'))
    if len(models) != 1: raise ValueError('FEM_NATIVE_MODEL_IDENTITY_AMBIGUOUS')
    import mph
    client = mph.start(cores=2); solved = client.load(models[0]); j = solved.java
    try:
        if j.param().evaluate('BF_complete') != 1: raise ValueError('FEM_ANCHOR_INCOMPLETE')
        rows = []
        for i, mesh in enumerate((1.5, 1., .7)):
            computed = np.array([j.param().evaluate('BF_fx'+str(i)), j.param().evaluate('BF_fz'+str(i))])
            rows.append({'local_tip_hmax_mm': mesh, 'force_N': computed.tolist(),
                         'relative_reference_error': float(np.linalg.norm(computed-expected)/max(np.linalg.norm(expected), 1e-9))})
        j.result().export().create('delivery', 'field', 'Image'); e = j.result().export('delivery')
        e.set('imagetype', 'png'); e.set('pngfilename', str(directory/'magnetic-flux.png'))
        e.set('size', 'manualweb'); e.set('unit', 'px'); e.set('width', '1600'); e.set('height', '1000'); e.set('zoomextents', 'on'); e.run()
    finally: client.remove(solved)
    if len(rows) != 3: raise ValueError('FEM_ANCHOR_MISSING_MESH_RESULTS')
    delta = np.linalg.norm(np.array(rows[-1]['force_N'])-rows[-2]['force_N'])/max(np.linalg.norm(rows[-1]['force_N']), 1e-9)
    result = {'design_id': design['design_id'], 'angle_deg': angle_deg, 'tip_m': tip_m, 'rows': rows,
              'mesh_delta': float(delta), 'mesh_target': design['frozen']['numerics']['mesh_target'],
              'reference_error': rows[-1]['relative_reference_error'],
              'mesh_passed': bool(delta <= .05), 'reference_passed': rows[-1]['relative_reference_error'] <= .05,
              'coverage_complete': False, 'source_sha256': file_hash(java), 'model_sha256': file_hash(models[0]),
              'model_file': models[0].name,
              'scope': 'Independent rotated driver FEM under same mu_r=1 hard-magnet assumptions; individual anchor, not whole-trajectory qualification.'}
    write_json(directory/'anchor-result.json', result); return result

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--design',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--angle-deg',type=float,required=True);p.add_argument('--tip-m',type=float,default=0.);p.add_argument('--readback',action='store_true')
    a=p.parse_args();print(json.dumps(anchor(a.out, json.loads(a.design.read_text()), a.angle_deg, a.tip_m, a.readback), indent=2))
