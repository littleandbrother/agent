"""Execute only pinned pure CAD input-definition statements, never CAD kernels.

The build function is cut at the first input.json write, after all part-center
edits. IO/bootstrap statements are replaced by supplied design/definition. The
retained AST-derived statements are exact upstream source. This checks declared
geometry, not OCCT readback/clearance/installation mesh correctness.
"""
import ast,copy,json,pathlib,types
ROOT=pathlib.Path(__file__).resolve().parents[1]

def declared_centers(gap):
    source=ROOT/'source-supplement/build_pluck_product.py';tree=ast.parse(source.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='definition')
    namespace={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace);spec=namespace['definition']()
    design={'title':'Synthetic declared-coordinate audit','assumptions':[],'magnets':{'nominal_center_separation_x_mm':gap}}
    source=ROOT/'source-supplement/build_cad.py';tree=ast.parse(source.read_text());build=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build')
    # Source first constructs and edits spec after mod.definition, until writing.
    body=[];started=False
    for node in build.body:
        text=ast.get_source_segment(source.read_text(),node) or ''
        if text.startswith("spec=mod.definition()"):started=True;continue
        if not started:continue
        if text.startswith("(out/'input.json').write_text"):break
        body.append(node)
    if not body:raise ValueError('CAD_SOURCE_STRUCTURE_CHANGED')
    ns={'spec':spec,'design':design};exec(compile(ast.Module(body=body,type_ignores=[]),str(source),'exec'),ns)
    centers={p['id']:p['geometry']['center_mm'] for p in ns['spec']['parts']}
    # The exact installation transform in source is a 180 degree rotation
    # around (0,1,1), then translate(1004,70,2140): (x,y,z)->(-x,z,y)+origin.
    expected="s=s.rotate((0,0,0),(0,1,1),180).translate((1004,70,2140))"
    if expected not in source.read_text():raise ValueError('CAD_TRANSFORM_STRUCTURE_CHANGED')
    world={name:[1004-v[0],70+v[2],2140+v[1]] for name,v in centers.items() if name in ('driver_magnet','tip_magnet')}
    return {'gap_mm':gap,'local_mm':{k:centers[k] for k in world},'world_mm':world,'scope':'Pinned source geometry construction + declared rigid transform; no OCCT execution or native STEP verification'}
