"""Studio delivery is a projection, never an acceptance or adoption authority."""
import hashlib
import html
import json
import os
import posixpath
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import quote, urlencode
import zipfile

from .store import canonical, identity


class StudioDelivery:
    def __init__(self, results):
        self.results = results
        self.root = results.store.root / 'studio-deliveries'

    def inspect(self, owner, selection='session', revision=None):
        catalog = self.results.inspect(owner, revision)
        rows = catalog['results']
        options = [{'id': 'session', 'label': '全部记录 · 含历史与独立运行'}]
        seen = set()
        for r in rows:
            if r.get('case_id'):
                key = 'case:' + r['case_id'] + ':' + r['case_version']
                if key not in seen:
                    options.append({'id': key, 'label': r['case_title'] + ' · ' + r['case_version']})
                    seen.add(key)
        if catalog['revision'] is not None:
            options.insert(0, {'id': 'assembly', 'label': '装配 v' + str(catalog['revision']) + ' · 适用成果'})
        if selection not in {o['id'] for o in options}:
            raise ValueError('STUDIO_SELECTION_NOT_FOUND')
        if selection.startswith('case:'):
            _, cid, version = selection.split(':')
            rows = [r for r in rows if r.get('case_id') == cid and r.get('case_version') == version]
            ids = {f['id'] for r in rows for f in r['files']}
            files = [f for f in catalog['files'] if f['id'] in ids]
            verdict = None
        elif selection == 'assembly':
            files = [f for f in catalog['files'] if f['applicability']['state'] in ('current', 'reused')]
            ids = {f['result_id'] for f in files}
            rows = [r for r in rows if r['id'] in ids]
            file_ids = {f['id'] for f in files}
            rows = [dict(r, files=[f for f in r['files'] if f['id'] in file_ids],
                         presentations=[p for p in r.get('presentations', []) if p.get('file_id') in file_ids]) for r in rows]
            verdict = catalog['verdict']
        else:
            files = catalog['files']
            verdict = catalog['verdict']
        payload = dict(schema_version='bf-studio-delivery-v1', owner=owner, title=catalog['title'],
                       selection=selection, selection_label=next(o['label'] for o in options if o['id'] == selection),
                       revision=catalog['revision'], options=options, results=rows, files=files, verdict=verdict,
                       scope='所选记录的可交付资料；文件完整性与产品验收分别记录。未记录采用关系，不自动标为当前采用版。')
        payload['purposes'] = self.purposes(owner, files)
        payload['snapshot_sha256'] = identity({k: v for k, v in payload.items() if k != 'options'})
        return payload

    def purposes(self, owner, files):
        """Build a bounded report dependency closure from registered files only.

        Never execute TeX or follow arbitrary local paths. Include the report
        directory (custom figure macros live there), plus literal out-of-folder
        imports and their recursive sources. Unresolved imports remain visible.
        """
        report_pdfs = [f for f in files if f['name'].lower().endswith('.pdf') and
                       re.search(r'report|报告|door-case', (f.get('source_path', '') + f['name']), re.I)]
        def group(f):
            return (f.get('case_id'), f.get('case_version')) if f.get('case_id') else (f['result_id'],)
        def rel(f):
            return posixpath.normpath(f.get('source_path') or f['name'])
        selected = {f['id'] for f in report_pdfs}
        lookup = {(group(f), rel(f)): f for f in files}
        for pdf in report_pdfs:
            parent = posixpath.dirname(rel(pdf))
            for f in files:
                # Do not accidentally sweep the complete engineering root.
                same_tree = bool(parent) and (rel(f).startswith(parent + '/'))
                sibling = posixpath.splitext(rel(f))[0] == posixpath.splitext(rel(pdf))[0]
                if group(f) == group(pdf) and (same_tree or sibling): selected.add(f['id'])
        queue = [f for f in files if f['id'] in selected and f['name'].lower().endswith(('.tex', '.sty', '.cls'))]
        visited = set(); warnings = []
        pattern = re.compile(r'\\(?:input|include|includegraphics|includepdf|addbibresource|bibliography)\*?(?:\[[^\]]*\])?\{([^{}]+)\}')
        while queue:
            f = queue.pop()
            if f['id'] in visited: continue
            visited.add(f['id'])
            if not f['integrity']: continue
            path, _ = self.results.file(owner, f['id'])
            if path.stat().st_size > 2_000_000:
                warnings.append(f['name'] + '：源文件过大，未自动解析依赖'); continue
            text = re.sub(r'(?<!\\)%[^\n]*', '', path.read_text(errors='replace'))
            for target in pattern.findall(text):
                if '#' in target or '\\' in target:
                    warnings.append(f['name'] + '：动态引用仅包含已归档报告目录，需本地复编核对'); continue
                for target in target.split(','):
                    base = posixpath.normpath(posixpath.join(posixpath.dirname(rel(f)), target.strip()))
                    match = next((lookup.get((group(f), base + ext)) for ext in ('', '.tex', '.pdf', '.png', '.jpg', '.jpeg', '.svg', '.bib') if lookup.get((group(f), base + ext))), None)
                    if match:
                        selected.add(match['id'])
                        if match['name'].lower().endswith(('.tex', '.sty', '.cls')): queue.append(match)
                    else: warnings.append(f['name'] + '：未归档引用 ' + target.strip())
        report = [f for f in files if f['id'] in selected]
        def plan(items, available=True, notes=()):
            return dict(file_ids=[f['id'] for f in items], files=len(items),
                        readable=sum(bool(f['integrity']) for f in items),
                        bytes=sum(f.get('bytes', 0) for f in items if f['integrity']),
                        missing=[f['id'] for f in items if not f['integrity']],
                        available=available, warnings=sorted(set(notes)))
        return dict(summary=plan([]), report=plan(report, any(f['integrity'] for f in report_pdfs), warnings), engineering=plan(files))

    @staticmethod
    def entry_path(file):
        # Case source paths preserve TeX figure and drawing relationships.
        rel = PurePosixPath(file.get('source_path') or file['id'])
        if rel.is_absolute() or '..' in rel.parts or '\\' in str(rel):
            raise ValueError('STUDIO_EXPORT_PATH_INVALID')
        base = ('工程/' + file['case_id'] + '/' + file['case_version'] + '/') if file.get('case_id') else '成果/'
        return base + str(rel)

    @staticmethod
    def index(manifest):
        if manifest['schema_version'] == 'bf-studio-package-v2':
            return StudioDelivery.index_v2(manifest)
        esc = html.escape
        snap = manifest['snapshot']
        sections = []
        for r in snap['results']:
            status = '未通过' if r.get('design_status') == 'FAIL' else '该项计算通过' if r.get('design_status') == 'PASS' else '未给出独立验收结论'
            sections.append('<section><h2>' + esc(r.get('label') or r['kind']) + '</h2><b>' + status + '</b><p>' + esc(r.get('scope', '')) + '</p></section>')
        links = ''.join('<li><a href="' + quote(f['export_path']) + '">' + esc(f['name']) + '</a></li>' for f in manifest['files'])
        missing = ''.join('<li>' + esc(f['name']) + '：' + esc(f.get('error') or '文件不可读取') + '</li>' for f in manifest['omitted'])
        return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                '<title>产品交付说明</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:960px;margin:48px auto;padding:0 24px;color:#1d1d1f}a{color:#0066cc}section{border-top:1px solid #ddd;padding:18px 0}small{color:#555}</style>'
                '<h1>' + esc(snap['title']) + '</h1><p>' + esc(snap['selection_label']) + '</p><p>' + esc(snap['scope']) + '</p>'
                '<p>资料用途：' + esc(manifest['purpose']) + '。请先查看各部分的结论与限制，再打开原生工程继续修改或复算。仿真记录不等于实物验证。</p>'
                '<small>快照 ' + snap['snapshot_sha256'] + '</small>' + ''.join(sections) + '<h2>文件入口</h2><ul>' + links + '</ul>'
                + ('<h2>未包含的缺失文件</h2><ul>' + missing + '</ul>' if missing else '') + '</html>')

    @staticmethod
    def index_v2(manifest):
        esc = html.escape; snap = manifest['snapshot']
        purpose = {'summary': '结果概要', 'report': '技术报告', 'engineering': '工程资料包'}[manifest['purpose']]
        parts = []
        for r in snap['results']:
            status = ('模型内未达到目标' if r.get('predicted_design_status') == 'unsatisfied' else
                      '执行失败' if r.get('status') == 'FAILED' else
                      '未通过' if r.get('design_status') == 'FAIL' else
                      '该项计算通过' if r.get('design_status') == 'PASS' else '尚无独立通过结论')
            metrics = ''.join('<li>' + esc(str(m['name'])) + '：' + esc(str(m.get('value'))) + '</li>' for m in r.get('metrics', []))
            parts.append('<section><h2>' + esc(r.get('label') or r['kind']) + '</h2><b>' + status + '</b><p>' + esc(r.get('scope') or '') + '</p><ul>' + metrics + '</ul></section>')
        exported = {f['id']: f for f in manifest['files']}
        entries = []
        for f in snap['files']:
            item = exported.get(f['id'])
            label = '<a href="' + quote(item['export_path']) + '">' + esc(f['name']) + '</a>' if item else esc(f['name'])
            state = '已包含' if item else '未附原文件' if f['integrity'] else (f.get('error') or '不可读取')
            entries.append('<li>' + label + ' · ' + esc(state) + '</li>')
        notes = snap['purposes'][manifest['purpose']]['warnings']
        return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                '<title>' + esc(purpose) + '</title><style>body{font:16px/1.75 system-ui,sans-serif;color:#202124;max-width:880px;margin:48px auto;padding:0 24px}h1{line-height:1.4}h2{font-size:20px}section{border-top:1px solid #ddd;padding:20px 0}a{color:#0066cc}small,code{overflow-wrap:anywhere;color:#555}li{overflow-wrap:anywhere;margin:6px 0}</style>'
                '<small>BF Agent Studio · ' + purpose + '</small><h1>' + esc(snap['title']) + '</h1><p>' + esc(snap['selection_label']) + '</p><p>' + esc(snap['scope']) + '</p>'
                '<p>仿真与数字工程记录不等于实物验证。以下保留原有结论；未通过的条件不会因导出而改变。</p>' + ''.join(parts)
                + ('<section><h2>报告依赖提示</h2><ul>' + ''.join('<li>' + esc(n) + '</li>' for n in notes) + '</ul></section>' if notes else '')
                + '<section><h2>文件清单</h2><ul>' + ''.join(entries) + '</ul></section><small>快照 ' + snap['snapshot_sha256'] + '</small></html>')

    def package(self, owner, body):
        snap = self.inspect(owner, body.get('selection', 'session'), body.get('revision'))
        if snap['snapshot_sha256'] != body.get('snapshot_sha256'):
            raise ValueError('STUDIO_SNAPSHOT_CHANGED')
        purpose = body.get('purpose', 'engineering')
        if purpose not in ('summary', 'report', 'engineering'):
            raise ValueError('STUDIO_EXPORT_PURPOSE_INVALID')
        plan = snap['purposes'][purpose]
        if not plan['available']:
            raise ValueError('STUDIO_REPORT_NOT_AVAILABLE')
        selected = [f for f in snap['files'] if f['id'] in plan['file_ids']]
        missing = [f for f in (snap['files'] if purpose == 'summary' else selected) if not f['integrity']]
        if purpose != 'summary' and missing and body.get('allow_partial') is not True:
            raise ValueError('STUDIO_FILES_MISSING')
        files = [dict(f, export_path=self.entry_path(f)) for f in selected if f['integrity']]
        paths = {}
        for f in files:
            if f['export_path'] in paths and paths[f['export_path']] != f['sha256']:
                raise ValueError('STUDIO_EXPORT_PATH_COLLISION')
            paths[f['export_path']] = f['sha256']
        files = list({f['export_path']: f for f in files}.values())
        manifest = dict(schema_version='bf-studio-package-v2', purpose=purpose, snapshot=snap, files=files, omitted=missing)
        key = identity(manifest)
        folder = self.root / identity(owner)
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / (key + '.zip')
        if not dest.exists():
            fd, tmp = tempfile.mkstemp(dir=folder, suffix='.zip'); os.close(fd)
            try:
                with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.writestr('交付清单.json', canonical(manifest))
                    z.writestr('打开我.html', self.index(manifest))
                    for f in files:
                        source, _ = self.results.file(owner, f['id'])
                        z.write(source, f['export_path'])
                if self.inspect(owner, snap['selection'], snap['revision'])['snapshot_sha256'] != snap['snapshot_sha256']:
                    raise ValueError('STUDIO_SNAPSHOT_CHANGED')
                os.replace(tmp, dest)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
        self.archive(owner, key)
        return dict(id=key, files=len(files), omitted=len(missing), bytes=dest.stat().st_size,
                    url='/api/studio/archive?' + urlencode({'session': owner, 'id': key}))

    def archive(self, owner, key):
        self.results.sources.require(owner)
        if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
            raise PermissionError('STUDIO_ARCHIVE_NOT_FOUND')
        path = self.root / identity(owner) / (key + '.zip')
        if not path.is_file() or path.is_symlink(): raise PermissionError('STUDIO_ARCHIVE_NOT_FOUND')
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read('交付清单.json'))
            if identity(m) != key or m['snapshot']['owner'] != owner: raise ValueError('STUDIO_ARCHIVE_INVALID')
            if z.read('打开我.html') != self.index(m).encode(): raise ValueError('STUDIO_ARCHIVE_INDEX_INVALID')
            expected = {'交付清单.json', '打开我.html'} | {f['export_path'] for f in m['files']}
            if set(z.namelist()) != expected or len(z.namelist()) != len(expected): raise ValueError('STUDIO_ARCHIVE_INVENTORY_INVALID')
            for f in m['files']:
                with z.open(f['export_path']) as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != f['sha256']: raise ValueError('STUDIO_ARCHIVE_HASH_INVALID')
        return path
