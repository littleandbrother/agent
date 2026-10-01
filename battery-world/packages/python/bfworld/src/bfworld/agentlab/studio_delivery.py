"""Studio delivery is a projection, never an acceptance or adoption authority."""
import hashlib
import html
import json
import os
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
        options = [{'id': 'session', 'label': '会话成果集合 · 含历史记录'}]
        seen = set()
        for r in rows:
            if r.get('case_id'):
                key = 'case:' + r['case_id'] + ':' + r['case_version']
                if key not in seen:
                    options.insert(0, {'id': key, 'label': r['case_title'] + ' · ' + r['case_version']})
                    seen.add(key)
        if catalog['revision'] is not None:
            options.append({'id': 'assembly', 'label': '装配 v' + str(catalog['revision']) + ' · 适用文件'})
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
            verdict = catalog['verdict']
        else:
            files = catalog['files']
            verdict = catalog['verdict']
        payload = dict(schema_version='bf-studio-delivery-v1', owner=owner, title=catalog['title'],
                       selection=selection, selection_label=next(o['label'] for o in options if o['id'] == selection),
                       revision=catalog['revision'], options=options, results=rows, files=files, verdict=verdict,
                       scope='所选记录的可交付资料；文件完整性与产品验收分别记录。未记录采用关系，不自动标为当前采用版。')
        payload['snapshot_sha256'] = identity({k: v for k, v in payload.items() if k != 'options'})
        return payload

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

    def package(self, owner, body):
        snap = self.inspect(owner, body.get('selection', 'session'), body.get('revision'))
        if snap['snapshot_sha256'] != body.get('snapshot_sha256'):
            raise ValueError('STUDIO_SNAPSHOT_CHANGED')
        purpose = body.get('purpose', 'engineering')
        if purpose not in ('summary', 'report', 'engineering'):
            raise ValueError('STUDIO_EXPORT_PURPOSE_INVALID')
        if purpose == 'report' and not any(f['integrity'] and f['name'].lower().endswith('.pdf') and ('report' in (f.get('source_path','') + f['name']).lower() or '报告' in f['name']) for f in snap['files']):
            raise ValueError('STUDIO_REPORT_NOT_AVAILABLE')
        missing = [f for f in snap['files'] if not f['integrity']]
        if purpose != 'summary' and missing and body.get('allow_partial') is not True:
            raise ValueError('STUDIO_FILES_MISSING')
        files = [] if purpose == 'summary' else [dict(f, export_path=self.entry_path(f)) for f in snap['files'] if f['integrity']]
        paths = {}
        for f in files:
            if f['export_path'] in paths and paths[f['export_path']] != f['sha256']:
                raise ValueError('STUDIO_EXPORT_PATH_COLLISION')
            paths[f['export_path']] = f['sha256']
        files = list({f['export_path']: f for f in files}.values())
        manifest = dict(schema_version='bf-studio-package-v1', purpose=purpose, snapshot=snap, files=files, omitted=missing)
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
