"""Portable declarative scientific figure renderer (NumPy/Matplotlib/Pillow).

Only source CSV data and declared illustrations are drawn. There is no eval,
shell, network, or participant Python. PDF/SVG keep text and curves vector;
native render images remain explicitly raster images.
"""
import csv
import hashlib
import html
import json
import math
import os
import re
from pathlib import Path
import zipfile

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.ticker import LogFormatter, NullFormatter, ScalarFormatter
from matplotlib.textpath import TextToPath
from PIL import Image

PALETTE = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#4D5359']
LINESTYLES = ['-', '--', '-.', ':']
UNITS = {'m': ('length', 1), 'mm': ('length', 1e-3), 'um': ('length', 1e-6),
         's': ('time', 1), 'ms': ('time', 1e-3), 'V': ('voltage', 1), 'mV': ('voltage', 1e-3), 'uV': ('voltage', 1e-6),
         'A': ('current', 1), 'mA': ('current', 1e-3), 'uA': ('current', 1e-6), 'J': ('energy', 1), 'mJ': ('energy', 1e-3), 'uJ': ('energy', 1e-6),
         'W': ('power', 1), 'mW': ('power', 1e-3), 'uW': ('power', 1e-6), 'N': ('force', 1),
         'Pa': ('pressure', 1), 'MPa': ('pressure', 1e6), 'Hz': ('frequency', 1), 'kHz': ('frequency', 1e3),
         'rad': ('angle', 1), 'deg': ('angle', math.pi / 180), 'F': ('capacitance', 1), 'uF': ('capacitance', 1e-6),
         'ohm': ('resistance', 1), 'kohm': ('resistance', 1e3), 'Mohm': ('resistance', 1e6),
         '1': ('dimensionless', 1), '%': ('dimensionless', .01), 'm/s': ('velocity', 1),
         'N/m': ('stiffness', 1), 'T': ('flux', 1), 'kg': ('mass', 1), 'B': ('memory',1), 'KiB': ('memory',1024)}
LABELS = {'uJ': 'µJ', 'uW': 'µW', 'uV': 'µV', 'uA': 'µA', 'uF': 'µF', 'um': 'µm', 'ohm': 'Ω', 'Mohm': 'MΩ'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configure(size=9):
    # Prefer an embeddable TrueType face; CFF inside Hiragino TTC can be
    # rendered on this machine but produces a PDF font-type mismatch elsewhere.
    candidates = [os.environ.get('BF_FIGURE_FONT', ''), '/System/Library/Fonts/Supplemental/Arial Unicode.ttf', '/System/Library/Fonts/Hiragino Sans GB.ttc']
    family = 'DejaVu Sans'
    for name in candidates:
        if name and Path(name).is_file():
            font_manager.fontManager.addfont(name)
            family = font_manager.FontProperties(fname=name).get_name()
            break
    plt.rcParams.update({'font.family': [family, 'DejaVu Sans'], 'font.size': size, 'font.weight': 'light' if family.startswith('Hiragino') else 'normal', 'axes.labelsize': size,
        'xtick.labelsize': size, 'ytick.labelsize': size, 'legend.fontsize': size, 'axes.titlesize': size,
        'axes.linewidth': .7, 'axes.spines.top': False, 'axes.spines.right': False,
        'axes.unicode_minus': False, 'axes.edgecolor': '#626A72', 'text.color': '#20272D',
        'axes.labelcolor': '#20272D', 'xtick.color': '#424A51', 'ytick.color': '#424A51',
        'svg.fonttype': 'none', 'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.hashsalt': 'bf-scientific-figures-v1',
        'savefig.facecolor': 'white', 'figure.facecolor': 'white', 'axes.facecolor': 'white'})
    return family


class Sources:
    def __init__(self, plan, directory):
        self.directory = directory.resolve()
        self.items = {s['id']: s for s in plan['sources']}
        self.cache = {}
        for s in plan['sources']:
            p = directory / s['path']
            if Path(s['path']).is_absolute() or '..' in Path(s['path']).parts or p.is_symlink() or not p.resolve().is_relative_to(self.directory):
                raise ValueError('FIGURE_PATH_DENIED')
            if not p.is_file() or digest(p) != s['sha256']:
                raise ValueError('FIGURE_SOURCE_CHANGED:' + s['id'])

    def path(self, sid):
        return self.directory / self.items[sid]['path']

    def rows(self, sid):
        if sid not in self.cache:
            with self.path(sid).open(newline='', encoding='utf-8-sig') as stream:
                self.cache[sid] = list(csv.DictReader(stream))
            if not self.cache[sid] or len(self.cache[sid]) > 200_000:
                raise ValueError('FIGURE_CSV_EMPTY_OR_TOO_LARGE')
        return self.cache[sid]

    def column(self, sid, key, unit):
        declared = self.items[sid].get('columns', {}).get(key)
        if declared not in UNITS or unit not in UNITS or UNITS[declared][0] != UNITS[unit][0]:
            raise ValueError('FIGURE_UNIT_MISMATCH:' + str(key))
        values = np.asarray([float(r[key]) for r in self.rows(sid)])
        if not np.isfinite(values).all():
            raise ValueError('FIGURE_NONFINITE_DATA')
        return values * UNITS[declared][1] / UNITS[unit][1]


def unit_label(unit):
    return LABELS.get(unit, unit)


def title(ax, panel):
    ax.set_title(panel['label'] + '  ' + panel['title'], loc='left', pad=9, weight='semibold')


def wrapped(value, width_pt, font_pt):
    """Wrap both CJK and Latin strings within a declared physical width."""
    prop = font_manager.FontProperties(family=plt.rcParams['font.family'], size=font_pt,
                                       weight=plt.rcParams['font.weight'])
    metrics = TextToPath()
    lines, current = [], ''
    for char in str(value):
        if char == '\n':
            lines.append(current); current = ''
            continue
        size = metrics.get_text_width_height_descent(current + char, prop, ismath=False)[0]
        if size > width_pt and current:
            lines.append(current); current = ''
        current += char
    lines.append(current)
    return '\n'.join(lines)


def table_value(value):
    """Concise display precision only; original source CSV is never rewritten.

    Preserve identifiers with leading zeros and long integer identifiers. Native
    floating-point readbacks otherwise needlessly wrap16digits across cells.
    """
    text = str(value)
    if re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text):
        if re.fullmatch(r'0\d+|\d{9,}', text):
            return text
        number = float(text)
        if math.isfinite(number):
            return format(number, '.4g')
    return text


def diagram(ax, panel):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    nodes = {n['id']: n for n in panel['nodes']}
    for n in nodes.values():
        x, y, w, h = [float(n.get(k, v)) for k, v in [('x', 0), ('y', 0), ('width', .25), ('height', .15)]]
        if not all(math.isfinite(v) for v in (x, y, w, h)) or min(w, h) <= 0 or x < 0 or y < 0 or x + w > 1 or y + h > 1:
            raise ValueError('FIGURE_DIAGRAM_BOUNDS')
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.008', linewidth=.7,
                     edgecolor='#89949C', facecolor=n.get('color', '#F4F6F7')))
        width_pt = ax.get_position().width * ax.figure.get_figwidth() * 72 * w
        label = n['label'].replace(' / ', '\n')
        ax.text(x + w / 2, y + h / 2, wrapped(label, width_pt - 4, plt.rcParams['font.size']), ha='center', va='center')
    for edge in panel.get('edges', []):
        a, b = nodes[edge['from']], nodes[edge['to']]
        ac = np.array((a['x'] + a.get('width', .25) / 2, a['y'] + a.get('height', .15) / 2))
        bc = np.array((b['x'] + b.get('width', .25) / 2, b['y'] + b.get('height', .15) / 2))
        delta = bc - ac
        def extent(node):
            return min(node.get('width', .25) / (2 * abs(delta[0])) if delta[0] else math.inf,
                       node.get('height', .15) / (2 * abs(delta[1])) if delta[1] else math.inf)
        if np.linalg.norm(delta) == 0:
            raise ValueError('FIGURE_DIAGRAM_OVERLAPPING_NODES')
        start, end = ac + delta * extent(a), bc - delta * extent(b)
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=10, color='#637681', linewidth=.85,
                     shrinkA=2, shrinkB=2, connectionstyle='arc3,rad=' + str(edge.get('curve', 0))))
        if edge.get('label'):
            ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + .04, edge['label'], ha='center',
                    bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 1})


def draw(ax, panel, sources, *, compact=False):
    title(ax, panel)
    if panel['status'] != 'available':
        ax.axis('off')
        ax.text(.04, .7, '尚缺证据' if panel['status'] == 'missing' else '本任务不适用', transform=ax.transAxes,
                color='#69757E', weight='semibold')
        reason = panel['reason']
        if compact and len(reason) > 56:
            reason = reason[:56] + '…\n（完整说明见单图及图注）'
        width_pt = ax.get_position().width * ax.figure.get_figwidth() * 72
        ax.text(.04, .45, wrapped(reason, width_pt * .95, plt.rcParams['font.size']), transform=ax.transAxes, va='top', color='#69757E')
        return
    kind = panel['type']
    if kind in ('line', 'scatter'):
        units = {(s['x_unit'], s['y_unit']) for s in panel['series']}
        if len(units) != 1:
            raise ValueError('FIGURE_MIXED_AXIS_UNITS')
        for i, s in enumerate(panel['series']):
            x, y = [sources.column(s['source'], s[key], s[key + '_unit']) for key in ('x', 'y')]
            if len(x) != len(y):
                raise ValueError('FIGURE_LENGTH_MISMATCH')
            color = PALETTE[i % len(PALETTE)]
            if kind == 'scatter':
                ax.scatter(x, y, s=17, color=color, marker=s.get('marker', ['o', 's', '^', 'D'][i % 4]), label=s.get('label'))
            else:
                ax.plot(x, y, color=color, linewidth=1.15, linestyle=s.get('linestyle', LINESTYLES[i % 4]), drawstyle=panel.get('drawstyle', 'default'),
                        marker=s.get('marker'), markevery=max(1, len(x) // 12), markersize=3, label=s.get('label'))
        xu, yu = next(iter(units))
        ax.set_xlabel(panel.get('x_label', panel['series'][0]['x']) + ' (' + unit_label(xu) + ')')
        ax.set_ylabel(panel.get('y_label', panel['series'][0]['y']) + ' (' + unit_label(yu) + ')')
        if any(s.get('label') for s in panel['series']):
            ax.legend(frameon=False, loc=panel.get('legend_location', 'best'), handlelength=1.6)
    elif kind == 'bar':
        rows = sources.rows(panel['source'])
        x = [r[panel['x']] for r in rows]
        y = sources.column(panel['source'], panel['y'], panel['y_unit'])
        bars = ax.bar(range(len(x)), y, color=[PALETTE[i % 6] for i in range(len(x))], width=.6, edgecolor='#38434A', linewidth=.5)
        for i, bar in enumerate(bars):
            bar.set_hatch(['', '//', '..', '\\\\'][i % 4])
        ax.set_xticks(range(len(x)), x, rotation=panel.get('tick_rotation', 0))
        ax.set_ylabel(panel.get('y_label', panel['y']) + ' (' + unit_label(panel['y_unit']) + ')')
        ax.axhline(0, color='#5C6972', linewidth=.65)
        if np.all(y == 0) and 'ylim' not in panel:
            ax.set_ylim(0, 1)
            ax.set_yticks([0, 1])
            for i in range(len(x)):
                ax.text(i, .02, '0', ha='center', va='bottom')
    elif kind == 'heatmap':
        sid = panel['source']
        x, y, z = [sources.column(sid, panel[k], panel[k + '_unit']) for k in ('x', 'y', 'z')]
        xx, yy = np.unique(x), np.unique(y)
        zz = np.full((len(yy), len(xx)), np.nan)
        for a, b, c in zip(x, y, z):
            zz[np.searchsorted(yy, b), np.searchsorted(xx, a)] = c
        if not np.isfinite(zz).all():
            raise ValueError('FIGURE_HEATMAP_INCOMPLETE_GRID')
        image = ax.pcolormesh(xx, yy, zz, cmap='viridis', shading='auto', rasterized=False)
        ax.figure.colorbar(image, ax=ax, fraction=.046, pad=.04, label=panel.get('z_label', panel['z']) + ' (' + unit_label(panel['z_unit']) + ')')
        ax.set_xlabel(panel.get('x_label', panel['x']) + ' (' + unit_label(panel['x_unit']) + ')')
        ax.set_ylabel(panel.get('y_label', panel['y']) + ' (' + unit_label(panel['y_unit']) + ')')
    elif kind == 'image':
        p = sources.path(panel['source'])
        if p.suffix.lower() == '.svg':
            raise ValueError('FIGURE_IMAGE_REQUIRES_NATIVE_RASTER_EXPORT')
        native = Image.open(p).convert('RGBA')
        background = Image.new('RGBA', native.size, 'white')
        image = Image.alpha_composite(background, native).convert('RGB')
        ax.imshow(image)
        for label in panel.get('annotations', []):
            point=label['to'];location=[label['x'],label['y']]
            if not all(0<=float(v)<=1 for v in point+location):raise ValueError('FIGURE_ANNOTATION_BOUNDS')
            ax.annotate(label['label'],xy=(point[0],1-point[1]),xytext=(location[0],1-location[1]),
                        xycoords='axes fraction',textcoords='axes fraction',va='center',
                        ha='right' if location[0] > .6 else 'left',
                        arrowprops={'arrowstyle':'-','color':'#39444C','lw':.65},
                        bbox={'facecolor':'white','edgecolor':'none','pad':1.5})
        if panel.get('scale_bar'):
            bar = panel['scale_bar']
            length = float(bar['fraction'])
            if not 0 < length < .6:
                raise ValueError('FIGURE_SCALE_BAR_BOUNDS')
            ax.plot([.92 - length, .92], [.07, .07], transform=ax.transAxes, color='#29353E', lw=1.5)
            ax.text(.92 - length / 2, .11, bar['label'], transform=ax.transAxes, ha='center',
                    bbox={'facecolor':'white', 'edgecolor':'none', 'pad':1})
        ax.axis('off')
    elif kind == 'table':
        rows = sources.rows(panel['source'])
        columns = panel.get('compact', {}).get('columns', panel['columns']) if compact else panel['columns']
        cols = columns
        if len(rows) > 20 or len(cols) > 6:
            raise ValueError('FIGURE_TABLE_READABILITY_BOUNDS')
        ax.axis('off')
        all_count = len(rows)
        limit = panel.get('compact', {}).get('rows', 4) if compact else len(rows)
        rows = rows[:limit]
        size = 8.5 if compact else 10
        width_pt = ax.get_position().width * ax.figure.get_figwidth() * 72
        # Matplotlib table cells reserve PAD=0.1 on both sides.
        cell_width = width_pt / len(cols) * .78
        labels = panel.get('column_labels', {})
        headers = [labels.get(c, c) if isinstance(labels, dict) else c for c in cols]
        cells = [[wrapped(table_value(r[c]), cell_width, size) for c in cols] for r in rows]
        headers = [wrapped(c, cell_width, size) for c in headers]
        table = ax.table(cellText=cells, colLabels=headers, bbox=(0, .12, 1, .79), cellLoc='left')
        table.auto_set_font_size(False)
        table.set_fontsize(size)
        heights = [max(s.count('\n') + 1 for s in headers)] + [max(s.count('\n') + 1 for s in row) for row in cells]
        total = sum(h + .6 for h in heights)
        for (row, _), cell in table.get_celld().items():
            cell.set_height(.79 * (heights[row] + .6) / total)
            cell.set_edgecolor('#D4DCE1')
            cell.set_linewidth(.45)
            cell.set_facecolor('#F4F6F7' if row == 0 else 'white')
        if compact and (len(cols) < len(panel['columns']) or all_count > len(rows)):
            ax.text(0, .01, f'完整 {all_count} 行见单图 / CSV', transform=ax.transAxes, color='#626D75')
    elif kind == 'diagram':
        diagram(ax, panel)
    else:
        raise ValueError('FIGURE_TYPE_NOT_SUPPORTED')
    if kind in ('line', 'scatter', 'bar'):
        ax.grid(axis='y', color='#DEE3E6', linewidth=.4, alpha=.7)
        ax.set_axisbelow(True)
        if panel.get('xscale', panel.get('x_scale')) == 'log':
            ax.set_xscale('log')
            ax.xaxis.set_major_formatter(LogFormatter(labelOnlyBase=True))
            ax.xaxis.set_minor_formatter(NullFormatter())
        if panel.get('yscale', panel.get('y_scale')) == 'log':
            ax.set_yscale('log')
            ax.yaxis.set_major_formatter(LogFormatter(labelOnlyBase=True))
            ax.yaxis.set_minor_formatter(NullFormatter())
        else:
            formatter = ScalarFormatter(useMathText=False)
            formatter.set_powerlimits((-3, 3))
            ax.yaxis.set_major_formatter(formatter)
        for axis in ('x', 'y'):
            if axis + 'lim' in panel:
                bounds = panel[axis + 'lim']
                if len(bounds) != 2 or not all(math.isfinite(float(v)) for v in bounds) or bounds[1] <= bounds[0]:
                    raise ValueError('FIGURE_AXIS_BOUNDS')
                getattr(ax, 'set_' + axis + 'lim')(bounds)
        for threshold in panel.get('thresholds', []):
            ax.axhline(threshold['value'], color='#5A6066', linewidth=.8, linestyle=':')
            ax.text(.98, threshold['value'], threshold['label'], transform=ax.get_yaxis_transform(), ha='right', va='bottom')
        for t in panel.get('times', []):
            ax.axvline(t['value'], color='#7E868E', linewidth=.6, linestyle=':')
        if panel.get('yticks'):
            ax.set_yticks([t['value'] for t in panel['yticks']], [t['label'] for t in panel['yticks']])
    if panel.get('note'):
        ax.text(.02, .98, panel['note'], transform=ax.transAxes, va='top', color='#596770',
                bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .9, 'pad': 1.5})


def save(fig, output, stem):
    fig.savefig(output / (stem + '.pdf'), metadata={'CreationDate': None, 'ModDate': None}, facecolor='white')
    fig.savefig(output / (stem + '.svg'), metadata={'Date': None}, facecolor='white')
    fig.savefig(output / (stem + '.png'), dpi=300, facecolor='white')
    plt.close(fig)


def render(plan_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(plan_path).read_text())
    sources = Sources(plan, Path(plan_path).parent)
    font = configure(10.5)
    panel_records = []
    groups = []
    for group in plan['groups']:
        for panel in group['panels']:
            stem = 'panel-' + panel['id']
            width, height = 4.4, 3.45
            if panel.get('type') == 'table':
                width = 180 / 25.4
                rows = sources.rows(panel['source'])
                # Full tables have their own larger sheet; group panels show labelled excerpts.
                height = max(3.45, (len(rows) + 1) * .6 + 1.2)
            elif panel.get('type') == 'image' and sources.items.get(panel.get('source'), {}).get('origin') in ('schematic', 'native-simulation'):
                width, height = 180 / 25.4, 5.3
            fig, ax = plt.subplots(figsize=(width, height))
            fig.subplots_adjust(left=.17, right=.96, bottom=.19, top=.85)
            draw(ax, panel, sources)
            save(fig, output, stem)
            record = {**panel, 'schema_version': 'bf-scientific-panel-v1', 'figure': stem + '.png', 'vector': stem + '.svg', 'pdf': stem + '.pdf',
                      'source_identity': hashlib.sha256(json.dumps([sources.items[s] for s in panel['dependencies']], sort_keys=True).encode()).hexdigest(),
                      'provenance': stem + '-provenance.json',
                      'claim_boundary': 'Presentation of supplied source; no physical or autonomous certification.'}
            (output / (stem + '-provenance.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2))
            panel_records.append(record)
        # Exactly 180 mm wide. Labels are >=8.5pt at this printed size.
        configure(8.5)
        n = len(group['panels'])
        cols = group.get('columns', 3 if n >= 6 else 2)
        if cols not in (2, 3):
            raise ValueError('FIGURE_LAYOUT_COLUMNS')
        rows = math.ceil(n / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(180 / 25.4, (rows * 64 + 14) / 25.4), squeeze=False)
        fig.subplots_adjust(left=.13, right=.976, bottom=.062, top=.95, hspace=.62, wspace=.52)
        for ax, panel in zip(axes.flat, group['panels']):
            draw(ax, panel, sources, compact=True)
        for ax in list(axes.flat)[n:]:
            ax.axis('off')
        stem = 'figure-' + str(group['order'])
        save(fig, output, stem)
        members = [p for p in panel_records if p['id'].startswith(str(group['order']))]
        groups.append({**group, 'panels': members, 'figure': stem + '.png', 'vector': stem + '.svg', 'pdf': stem + '.pdf'})
        configure(10.5)
    counts = {status: sum(p['status'] == status for p in panel_records) for status in ('available', 'missing', 'not_applicable')}
    quality = {'schema_version': 'bf-scientific-figure-quality-v1', 'status': 'passed-for-source-rendering',
        'source_hashes_verified': True, 'units_and_finite_values': True, 'font': font, 'group_print_width_mm': 180,
        'minimum_declared_font_pt': 8.5, 'font_scope': 'New plot text, axes and annotations; embedded source-image labels require the full-size individual/source view.',
        'compact_tables': 'Labelled excerpts only; full rows and columns remain in individual sheets and source CSV.',
        'table_display_precision': 'Four significant digits; exact hashed source CSV values and identifiers retained.',
        'vector_text_and_curves': True, 'raster_images_are_native_renders_or_declared_sources': True,
        'palette': 'Okabe-Ito plus viridis; line style/hatch/marker dual encoding', 'error_bars': 'not generated without replicate contract',
        'visual_inspection': 'required', 'physical_qualification': False, 'counts': counts,
        'completion_scope': 'Availability against declared plan only, not scientific replication or autonomous success.'}
    result = {'schema_version': 'bf-scientific-figure-index-v1', 'title': plan['title'], 'version': plan['version'],
        'conclusion': plan['conclusion'], 'limitations': plan.get('limitations', []), 'groups': groups, 'panels': panel_records,
        'counts': counts, 'source_identity': hashlib.sha256(json.dumps(plan['sources'], sort_keys=True).encode()).hexdigest(),
        'plan_sha256': digest(plan_path), 'quality': quality}
    (output / 'figure-index.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (output / 'figure-quality.json').write_text(json.dumps(quality, ensure_ascii=False, indent=2))
    (output / 'figure-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    esc = html.escape
    blocks = []
    for group in groups:
        sub = ''.join(f'<details id="panel-{p["id"]}"><summary>{esc(p["id"]+" · "+p["title"])} · {esc(p["status"])}</summary>'
            f'<p>{esc(p["question"])}</p><img src="{esc(p["figure"])}" alt="{esc(p["caption"])}"><p>{esc(p["caption"])}</p>'
            f'<p>{esc(p.get("reason", ""))}</p><a href="panel-{p["id"]}.pdf">PDF</a> · <a href="panel-{p["id"]}.svg">SVG</a> · '
            f'<a href="panel-{p["id"]}-provenance.json">来源记录</a></details>' for p in group['panels'])
        blocks.append(f'<section id="figure-{group["order"]}"><h2>{esc(group["title"])}</h2><p>{esc(group["question"])}</p>'
            f'<img src="{esc(group["figure"])}" alt="{esc(group["question"])}"><p>{esc(group["conclusion"])}</p>{sub}</section>')
    (output / 'figure-atlas.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<style>body{font:16px/1.7 system-ui;max-width:1080px;margin:auto;padding:32px;color:#20272d;background:white}img{display:block;width:100%;height:auto}'
        'section{border-top:1px solid #d7dfe5;padding:24px 0}details{padding:12px;border:1px solid #dde2e7;margin:12px 0}summary{cursor:pointer}a{color:#375d70}</style>'
        f'<title>{esc(plan["title"])}</title><h1>{esc(plan["title"])}</h1><p>{esc(plan["conclusion"])}</p><p>已有 {counts["available"]} · 缺失 {counts["missing"]} · 不适用 {counts["not_applicable"]}。这是逐图证据供应情况。</p>'
        + ''.join(blocks) + '</html>')
    # Include the exact source bytes and declare paths for portable reconstruction.
    manifest = []
    for i, source in enumerate(plan['sources']):
        name = 'source-' + str(i + 1).zfill(2) + sources.path(source['id']).suffix
        (output / name).write_bytes(sources.path(source['id']).read_bytes())
        manifest.append({**source, 'archive_file': name})
    (output / 'figure-sources.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    portable = {**plan, 'sources': [{**s, 'path': s['archive_file']} for s in manifest]}
    (output / 'reproduce-plan.json').write_text(json.dumps(portable, ensure_ascii=False, indent=2))
    (output / 'REPRODUCE.md').write_text('Source-only scientific figures. Install NumPy, Matplotlib and Pillow, then run:\n\n'
        'python scientific_renderer.py reproduce-plan.json reproduced\n\n'
        'For Chinese labels configure BF_FIGURE_FONT to a local CJK font. Sources are hashed before drawing. '
        'This regenerates figures, not the original native simulations or hardware.\n')
    # Per-group archives avoid requiring a model to download the whole evidence package.
    for group in groups:
        names = {group[k] for k in ('figure', 'pdf', 'vector')}
        required = set()
        for p in group['panels']:
            names.update(p[k] for k in ('figure', 'pdf', 'vector', 'provenance'))
            required.update(p['dependencies'])
        names.update(s['archive_file'] for s in manifest if s['id'] in required)
        name = f'figure-{group["order"]}-sources.zip'
        with zipfile.ZipFile(output / name, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(names):
                archive.write(output / item, item)
    with zipfile.ZipFile(output / 'scientific-figures.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(output.glob('*')):
            if p.is_file() and p.suffix != '.zip':
                archive.write(p, p.name)
    return result


if __name__ == '__main__':
    import sys
    value = render(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps({'groups': len(value['groups']), 'counts': value['counts'], 'quality': value['quality']['status']}))
