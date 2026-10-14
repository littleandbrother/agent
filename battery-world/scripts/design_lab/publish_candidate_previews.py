#!/usr/bin/env python3
"""Render frozen native artifacts and publish views without running engineering jobs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace
import warnings

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / 'packages/python/bfworld/src'))
from bfworld.agentlab.candidate_results import CandidateResults
from bfworld.agentlab.engineering import Engineering
from bfworld.agentlab.paper_sessions import ReadOnlyStore, reader
from bfworld.agentlab.preview_publication import publish
from bfworld.agentlab.product_results import ProductResults


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def catalog(runtime):
    app = SimpleNamespace(store=ReadOnlyStore(runtime / 'state'))
    app.engineering = reader(Engineering, app, root=runtime / 'engineering')
    return reader(ProductResults, app, _checked={})


def cad_drawings(mesh_path, step_sha, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    import numpy as np
    mesh = json.loads(mesh_path.read_text())
    if mesh.get('units') != 'mm' or mesh.get('source_sha256') != step_sha:
        raise ValueError('CAD_MESH_SOURCE_MISMATCH')
    vertices = np.asarray(mesh['vertices'], dtype=float)
    triangles = np.asarray(mesh['triangles'], dtype=int)
    if not np.isfinite(vertices).all() or triangles.min() < 0 or triangles.max() >= len(vertices):
        raise ValueError('CAD_MESH_INVALID')
    dims = np.ptp(vertices, axis=0)
    produced = []
    for name, axes, depth in [('top', (0, 1), 2), ('front', (0, 2), 1), ('side', (1, 2), 0)]:
        faces = vertices[triangles]
        order = np.argsort(faces[:, :, depth].mean(axis=1))
        normal = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
        light = np.abs(normal[:, depth]) / np.maximum(np.linalg.norm(normal, axis=1), 1e-12)
        colors = np.column_stack((.27+.18*light, .46+.19*light, .62+.22*light, np.ones(len(light))))
        fig, ax = plt.subplots(figsize=(7, 6), layout='constrained')
        ax.add_collection(PolyCollection(faces[order][:, :, axes], facecolors=colors[order], edgecolors='#3b5874', linewidths=.12))
        ax.autoscale(); ax.margins(.07); ax.set_aspect('equal')
        ax.set_xlabel('XYZ'[axes[0]] + ' (mm)'); ax.set_ylabel('XYZ'[axes[1]] + ' (mm)')
        ax.set_title(f'{name.title()} view · {dims[axes[0]]:g} × {dims[axes[1]]:g} mm', fontsize=12)
        for spine in ax.spines.values(): spine.set_color('#b4bec8')
        dest = out / ('cad-' + name + '.png')
        fig.savefig(dest, dpi=220, facecolor='white'); plt.close(fig)
        produced.append(dest)
    return produced, {'bounds_mm': dims.tolist(), 'vertices': len(vertices), 'triangles': len(triangles), 'matplotlib': matplotlib.__version__}


def gerber_drawings(path, library, out):
    sys.path.insert(0, str(library))
    import gerbonara
    from gerbonara import LayerStack
    from importlib.metadata import version
    mapping = {r'.*\.GTL': 'top copper', r'.*\.GBL': 'bottom copper', r'.*\.GTO': 'top silk',
               r'.*\.GBO': 'bottom silk', r'.*\.GTS': 'top mask', r'.*\.GBS': 'bottom mask',
               r'.*\.GTP': 'top paste', r'.*\.GKO': 'mechanical outline', r'.*\.DRL': 'drill plated'}
    with warnings.catch_warnings(record=True) as notes:
        warnings.simplefilter('always')
        stack = LayerStack.open(path, overrides=mapping, autoguess=False)
        expected = {tuple(s.split()) for s in mapping.values() if not s.startswith('drill')}
        if set(stack.graphic_layers) != expected: raise ValueError('GERBER_LAYER_MAPPING_INCOMPLETE')
        views = []
        for side in ('top', 'bottom'):
            dest = out / ('pcb-' + side + '.svg')
            dest.write_text(str(stack.to_pretty_svg(side=side, margin=1)), encoding='utf-8')
            views.append(dest)
        dest = out / 'pcb-combined.svg'
        colors = {'top copper': '#b9493d', 'bottom copper': '#4478b2', 'top silk': '#7a858d',
                  'mechanical outline': '#172631', 'drill pth': '#f4f6f8', 'drill unknown': '#f4f6f8'}
        dest.write_text(str(stack.to_svg(margin=1, colors=colors)), encoding='utf-8'); views.insert(0, dest)
    return views, {'gerbonara': version('gerbonara'), 'library': str(Path(gerbonara.__file__).parent),
                   'layer_mapping': mapping, 'bounds_mm': stack.board_bounds(), 'warnings': [str(x.message) for x in notes]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, required=True); p.add_argument('--owner', required=True)
    p.add_argument('--out', type=Path, required=True); p.add_argument('--gerbonara', type=Path, required=True)
    p.add_argument('--schematic-svg', type=Path); p.add_argument('--export-receipt', type=Path)
    p.add_argument('--native-project', type=Path)
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    cat = catalog(args.runtime); reader_ = CandidateResults(cat); task = reader_.task(args.owner)
    if not task: raise ValueError('CANDIDATE_TASK_REQUIRED')
    design_id = task['intent'].get('working_design') or task['current_design']
    design = reader_.design(args.owner, design_id); sources = reader_.sources(args.owner, design)
    for key, (path, meta) in sources.items():
        if not cat._integrity(path, meta['sha256'])[0]: raise ValueError('SOURCE_CHANGED: ' + key)
    def unique(predicate):
        matched = [(key, path, meta) for key, (path, meta) in sources.items() if predicate(key, path)]
        # Duplicate native files may be retained as history inside the same candidate.
        if len({m['sha256'] for _, _, m in matched}) != 1: raise ValueError('PREVIEW_SOURCE_AMBIGUOUS')
        return matched[-1]
    views = []; info = {'script_sha256': sha(__file__), 'actor': 'Codex', 'owner': args.owner, 'design_id': design_id}
    if args.schematic_svg:
        if not args.native_project or not args.export_receipt: raise ValueError('NATIVE_EXPORT_PROOF_REQUIRED')
        key, source, meta = unique(lambda k, p: p.suffix == '.esch2')
        # Native image export is admitted only while persisted native inputs match this frozen candidate.
        native = []
        for k, (path, m) in sources.items():
            if '/native-project/' not in k: continue
            rel = k.split('/native-project/', 1)[1]; live = args.native_project / rel
            if not live.is_file() or live.is_symlink() or sha(live) != m['sha256']:
                raise ValueError('NATIVE_PROJECT_CANDIDATE_CHANGED: ' + rel)
            native.append({'name': rel, 'sha256': m['sha256']})
        receipt = json.loads(args.export_receipt.read_text())
        _, readback, _ = unique(lambda k, p: p.name == 'schematic-readback.json')
        context = json.loads(readback.read_text())['context']
        if (not native or receipt.get('svg_sha256') != sha(args.schematic_svg) or
                receipt.get('project_uuid') != context['projectUuid'] or receipt.get('document_uuid') != context['documentUuid']):
            raise ValueError('SCHEMATIC_EXPORT_IDENTITY_MISMATCH')
        dest = args.out / 'schematic.svg'; shutil.copyfile(args.schematic_svg, dest) if dest.resolve() != args.schematic_svg.resolve() else None
        views.append(dict(path=dest, name=dest.name, sections=['schematic'], label='原理图 · 原生矢量图', sources=[key]))
        info['schematic'] = {'receipt_sha256': sha(args.export_receipt), **receipt, 'persisted_native_files': native}
    gerber_key, gerber, _ = unique(lambda k, p: p.suffix == '.zip' and 'gerber' in p.name.lower())
    board_key, _, _ = unique(lambda k, p: p.suffix == '.epcb2')
    images, info['pcb'] = gerber_drawings(gerber, args.gerbonara, args.out)
    labels = {'pcb-combined.svg': 'PCB · 双层走线', 'pcb-top.svg': 'PCB · 正面', 'pcb-bottom.svg': 'PCB · 背面'}
    views += [dict(path=x, name=x.name, sections=['pcb'], label=labels[x.name], sources=[gerber_key, board_key]) for x in images]
    mesh_key, mesh, _ = unique(lambda k, p: p.name == 'project-preview-mesh.json')
    step_key, _, step = unique(lambda k, p: p.name == 'project-assembly.step')
    images, info['cad'] = cad_drawings(mesh, step['sha256'], args.out)
    labels = {'cad-top.png': 'CAD · 俯视尺寸图', 'cad-front.png': 'CAD · 正视尺寸图', 'cad-side.png': 'CAD · 侧视尺寸图'}
    views += [dict(path=x, name=x.name, sections=['mechanical'], label=labels[x.name], sources=[mesh_key, step_key]) for x in images]
    result = publish(cat, args.owner, design_id, views, renderer=info)
    (args.out / 'publication.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
