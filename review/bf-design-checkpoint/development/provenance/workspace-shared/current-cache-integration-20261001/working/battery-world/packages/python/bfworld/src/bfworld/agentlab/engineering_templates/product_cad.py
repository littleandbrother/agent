"""Bounded declarative solid modelling with CadQuery/OCCT. Units: millimetres.

Input JSON and this source are the editable parametric CAD definition. STEP,
individual STL and BREP outputs derive from the same native solids.
"""
import json
import sys
from pathlib import Path
import cadquery as cq

root = Path(sys.argv[1])
spec = json.loads((root / 'input.json').read_text())['assembly']['payload']


def primitive(g):
    x, y, z = g['size_mm']
    if g['kind'] == 'cylinder':
        shape = cq.Workplane('XY').cylinder(z, x / 2).val()
    elif g['kind'] == 'sphere':
        shape = cq.Workplane('XY').sphere(x / 2).val()
    else:
        wp = cq.Workplane('XY').box(x, y, z)
        radius = g.get('fillet_mm', 0)
        if radius:
            wp = wp.edges().fillet(radius)
        if g['kind'] == 'shell':
            wall = g['wall_mm']
            inner = cq.Workplane('XY').box(x-2*wall, y-2*wall, z-2*wall)
            if radius > wall: inner = inner.edges().fillet(radius-wall)
            opening = cq.Workplane('XY').box(x-2*wall,y,z-2*wall)
            if radius > wall: opening = opening.edges('|Y').fillet(radius-wall)
            wp = wp.cut(inner).cut(opening.translate((0,y/2+wall/2,0)))
        shape = wp.val()
    for cut in g.get('cutouts', []):
        shape = shape.cut(transform(primitive(cut), cut))
    return shape


def transform(shape, g):
    for axis, angle in zip(((1, 0, 0), (0, 1, 0), (0, 0, 1)), g.get('rotation_deg', [0, 0, 0])):
        if angle:
            shape = shape.rotate((0, 0, 0), axis, angle)
    return shape.translate(g.get('center_mm', [0, 0, 0]))


def bounds(shape):
    b = shape.BoundingBox()
    return {'min_mm': [b.xmin, b.ymin, b.zmin], 'max_mm': [b.xmax, b.ymax, b.zmax],
            'size_mm': [b.xlen, b.ylen, b.zlen]}


assembly = cq.Assembly(name='product')
solids = {}
records = []
for part in spec['parts']:
    shape = transform(primitive(part['geometry']), part['geometry'])
    if not shape.isValid() or shape.Volume() <= 0 or len(shape.Solids()) != 1:
        raise RuntimeError('INVALID_NATIVE_SOLID:' + part['id'])
    solids[part['id']] = shape
    cq.exporters.export(shape, str(root / (part['id'] + '.stl')), tolerance=.08, angularTolerance=.1)
    cq.exporters.export(shape, str(root / (part['id'] + '.brep')))
    assembly.add(shape, name=part['id'], color=cq.Color(*part.get('color', [.65, .65, .65])))
    records.append({'id': part['id'], 'native_valid': True, 'volume_mm3': shape.Volume(), 'solid_count': len(shape.Solids()), **bounds(shape)})
assembly.save(str(root / 'assembly.step'))
reopened = cq.importers.importStep(str(root / 'assembly.step'))
reopened_shape = reopened.val()
if not all(s.isValid() for s in reopened.solids().vals()):
    raise RuntimeError('STEP_READBACK_INVALID')
compound = cq.Compound.makeCompound(list(solids.values()))
allowed = {frozenset(pair) for pair in spec.get('allowed_contacts', [])}
collisions = []
for i, a in enumerate(spec['parts']):
    for b in spec['parts'][i + 1:]:
        if frozenset((a['id'], b['id'])) in allowed:
            continue
        # Bounding boxes first; precise solid intersection only for close pairs.
        ba, bb = solids[a['id']].BoundingBox(), solids[b['id']].BoundingBox()
        if any(getattr(ba, v+'max') <= getattr(bb, v+'min')+.001 or getattr(bb, v+'max') <= getattr(ba, v+'min')+.001 for v in 'xyz'):
            continue
        volume = solids[a['id']].intersect(solids[b['id']]).Volume()
        if volume > .1:
            collisions.append({'parts': [a['id'], b['id']], 'intersection_mm3': volume})
report = {'engine': 'CadQuery/OCCT', 'version': cq.__version__, 'units': 'mm', 'parts': records,
          'assembly_bounds': bounds(compound), 'step_solid_count': len(reopened.solids().vals()),
          'step_reopened_valid': True, 'collisions': collisions, 'allowed_contacts': spec.get('allowed_contacts', []),
          'scope': 'Native solid validity and geometric interference; component envelopes and declared contacts are not manufacturing or fit qualification.'}
(root / 'cad-readback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
# Orthographic SVG derived from the actual solid geometry.
for name, direction in [('front', (0, -1, 0)), ('side', (1, 0, 0)), ('top', (0, 0, 1))]:
    cq.exporters.export(compound, str(root / (name + '.svg')), opt={'projectionDir': direction, 'width': 960, 'height': 720, 'showHidden': False})
print(json.dumps({'native_parts': len(records), 'collisions': len(collisions), 'step_reopened': True}))
