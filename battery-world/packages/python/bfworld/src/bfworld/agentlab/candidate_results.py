"""Read-only artifact projection of the existing frozen design lifecycle.

Preview publications are derived files. Their dependencies must match the exact
candidate inputs or selected native outputs before they can be served.
"""
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlencode

from .store import identity


DESIGN = re.compile(r'D-[0-9a-f]{64}')
PUBLICATION = re.compile(r'[0-9a-f]{64}')
LABELS = {'schematic': '原理图', 'pcb': 'PCB', 'mechanical': '机械与结构',
          'simulation': '联合仿真', 'firmware': '目标固件', 'bom': 'BOM', 'documents': '报告与交付'}


def safe(root, name):
    rel = PurePosixPath(name)
    if rel.is_absolute() or not rel.parts or '..' in rel.parts or '\\' in name:
        raise PermissionError('CANDIDATE_FILE_PATH_INVALID')
    path = Path(root) / rel
    if any((Path(root) / Path(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)):
        raise PermissionError('CANDIDATE_FILE_SYMLINK')
    if not path.is_file():
        raise ValueError('CANDIDATE_FILE_MISSING: ' + name)
    return path


def sections(name, kind=None):
    ext = Path(name).suffix.lower(); text = name.lower()
    if ext == '.esch2': return ['schematic']
    if ext == '.epcb2': return ['pcb']
    if ext == '.eprj3': return ['schematic', 'pcb']
    if 'bom' in text or 'native-parts-readback' in text: return ['bom']
    if 'schematic' in text: return ['schematic']
    if 'manufacturing/' in text or 'pcb' in text or 'drc' in text: return ['pcb']
    if kind == 'cadquery' or ext in ('.step', '.stp', '.stl', '.brep', '.glb') or 'project-cad/' in text:
        return ['mechanical']
    if (kind or '').startswith('firmware-') or 'project-fw' in text or 'receiver/' in text or ext in ('.c', '.h', '.elf', '.hex', '.bin', '.map', '.ld'):
        return ['firmware']
    if kind == 'spice' or 'project-chain/' in text or ext in ('.cir', '.raw'):
        return ['simulation']
    return ['documents']


def display_verdict(acceptance):
    if not acceptance: return None
    return dict(passed=acceptance.get('full_product_passed', False),
                target_stage='complete-digital-system', scope=acceptance.get('digital_engineering_status', ''),
                stages=[dict(g, passed=g['status'] == 'PASS') for g in acceptance.get('functional_gates', [])],
                functional_gates=acceptance.get('functional_gates', []), physical=acceptance.get('physical_validation'))


class CandidateResults:
    def __init__(self, catalog):
        self.catalog = catalog; self.store = catalog.store
        self.root = self.store.root.parent / 'design-lab'
        self.preview_root = self.store.root.parent / 'design-previews'

    def task(self, owner):
        with self.store.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='design_tasks'").fetchone(): return None
            row = db.execute('SELECT * FROM design_tasks WHERE owner=?', (owner,)).fetchone()
        if not row: return None
        task = dict(row)
        for field in ('environment', 'intent', 'submission'):
            task[field] = json.loads(task[field]) if task.get(field) else {}
        if not task['environment'].get('mode', '').startswith('paper-native-'): return None
        return task

    def design(self, owner, design_id):
        if not DESIGN.fullmatch(design_id): raise PermissionError('CANDIDATE_ID_INVALID')
        with self.store.connect() as db:
            row = db.execute('SELECT value FROM design_snapshots WHERE owner=? AND design_id=?', (owner, design_id)).fetchone()
        if not row: raise PermissionError('CANDIDATE_NOT_FOUND')
        value = json.loads(row[0])
        if value.get('design_id') != design_id or 'D-' + identity({k: v for k, v in value.items() if k != 'design_id'}) != design_id:
            raise ValueError('CANDIDATE_SNAPSHOT_HASH_CHANGED')
        path = safe(self.root / owner / 'designs' / design_id, 'snapshot.json')
        if json.loads(path.read_text()) != value: raise ValueError('CANDIDATE_SNAPSHOT_CHANGED')
        return value

    def sources(self, owner, design):
        """Only the original selected jobs and frozen files are current inputs."""
        base = self.root / owner / 'designs' / design['design_id'] / 'inputs'
        found = {}
        for name, meta in design['files'].items():
            key = 'candidate/' + design['design_id'] + '/input/' + name
            try: path = safe(base, name)
            except ValueError: path = base / name
            kind = next((p['kind'] for n, p in design['projects'].items()
                         if name == n or name.startswith(str(PurePosixPath(n).parent) + '/')), None)
            found[key] = (path, dict(meta, source_path='candidate/' + name, sections=sections(name, kind), kind=kind))
        for jid, binding in design.get('selected_jobs', {}).items():
            job = self.catalog.app.engineering.get(owner, jid)
            if (job['status'] != 'SUCCEEDED' or job.get('project_sha256') != binding.get('project_sha256') or
                    identity(job.get('result')) != binding.get('result_sha256')):
                raise ValueError('CANDIDATE_SELECTED_JOB_CHANGED: ' + jid)
            project = job.get('parameters', {}).get('project_path')
            if project not in design['projects'] or design['projects'][project]['project_sha256'] != job.get('project_sha256'):
                raise ValueError('CANDIDATE_JOB_SOURCE_MISMATCH: ' + jid)
            kind = design['projects'][project]['kind']
            for item in (job.get('result') or {}).get('outputs', (job.get('result') or {}).get('artifacts', [])):
                name = item['name']; key = 'candidate/' + design['design_id'] + '/job/' + jid + '/' + name
                path = self.catalog.app.engineering.root / jid / name
                if Path(name).name != name: raise ValueError('CANDIDATE_JOB_OUTPUT_PATH')
                found[key] = (path, dict(item, source_path='jobs/' + jid + '/outputs/' + name,
                                        sections=sections(name, kind), kind=kind, job_id=jid))
        return found

    def publication(self, owner, design_id, sources, publication_id=None):
        directory = self.preview_root / owner / design_id
        pointer = directory / 'current.json'
        if publication_id is None:
            if not pointer.is_file(): return None
            if pointer.is_symlink(): raise ValueError('PREVIEW_POINTER_INVALID')
            ref = json.loads(pointer.read_text()); pid = ref.get('publication_id', '')
        else:
            pid = publication_id; ref = None
        if not PUBLICATION.fullmatch(pid): raise ValueError('PREVIEW_PUBLICATION_ID_INVALID')
        path = safe(directory / pid, 'manifest.json')
        if ref:
            good, _ = self.catalog._integrity(path, ref.get('sha256'))
            if not good: raise ValueError('PREVIEW_MANIFEST_CHANGED')
        manifest = json.loads(path.read_text())
        if (manifest.get('owner') != owner or manifest.get('design_id') != design_id or
                identity(manifest) != pid or manifest.get('schema_version') != 'bf-candidate-previews-v1'):
            raise ValueError('PREVIEW_CANDIDATE_MISMATCH')
        for item in manifest['files']:
            if not item.get('sources'): raise ValueError('PREVIEW_SOURCE_REQUIRED')
            for source in item['sources']:
                origin = sources.get(source['id'])
                if not origin or origin[1]['sha256'] != source['sha256']:
                    raise ValueError('PREVIEW_SOURCE_CANDIDATE_MISMATCH')
                good, _ = self.catalog._integrity(origin[0], source['sha256'])
                if not good: raise ValueError('PREVIEW_SOURCE_CHANGED')
        return pid, manifest

    def collect(self, owner):
        task = self.task(owner)
        if not task: return [], [], None
        design_id = task['intent'].get('working_design') or task['current_design']
        design = self.design(owner, design_id); sources = self.sources(owner, design)
        submission = task['submission']; submitted = submission.get('design_id') == design_id
        meta = dict(design_id=design_id, task_id=task['task_id'], adopted_design_id=task['current_design'],
                    working_design_id=design_id, submitted_design_id=submission.get('design_id'),
                    submission_id=submission.get('submission_id') if submitted else None,
                    state='submitted' if submitted else 'working', selected_jobs=list(design.get('selected_jobs', {})),
                    label=('已提交候选' if submitted else '工作候选') + ' · ' + design_id[:10],
                    acceptance=submission.get('acceptance') if submitted else None,
                    preview_errors=[])
        meta['verdict']=display_verdict(meta['acceptance'])
        found = dict(sources)
        try:
            published = self.publication(owner, design_id, sources)
            if published:
                pid, manifest = published; meta['publication_id'] = pid
                for item in manifest['files']:
                    key = 'preview/' + design_id + '/' + pid + '/' + item['name']
                    path = self.preview_root / owner / design_id / pid / item['name']
                    found[key] = (path, dict(item, source_path='previews/' + item['name'], role='preview'))
                meta['channel_units'] = manifest.get('channel_units', {})
        except (ValueError, OSError, PermissionError) as exc:
            meta['preview_errors'].append(str(exc))
        files = []; groups = {}
        from .product_results import role
        for key, (path, item) in found.items():
            valid, error = self.catalog._integrity(path, item['sha256'])
            primary = item['sections'][0]; rid = 'candidate:' + design_id + ':' + primary
            area={'mechanical':'mechanical','firmware':'firmware','simulation':'circuit','schematic':'circuit','pcb':'circuit','bom':'circuit','documents':'system'}[primary]
            f = dict(item, id=key, name=path.name, result_id=rid, domain=area,
                     role=item.get('role', role(path.name)), bytes=item.get('bytes', path.stat().st_size if path.is_file() else 0),
                     candidate_id=design_id, created_revision=None, applies_to_revision=None,
                     applicability={'state': 'candidate', 'reason': meta['label'], 'changed_inputs': []},
                     integrity=valid, error=error, status='PUBLISHED',
                     url='/api/results/file?' + urlencode({'session': owner, 'id': key}))
            files.append(f); groups.setdefault(primary, []).append(f)
        with self.store.connect() as db:
            created = db.execute('SELECT COALESCE(MAX(created),0) FROM design_events WHERE owner=?', (owner,)).fetchone()[0]
        rows = []
        gate_for = {'schematic': ['schematic_bom_pins'], 'pcb': ['pcb_connectivity_drc'], 'mechanical': ['geometry_fit'],
                    'simulation': ['source_domain', 'power_load_chain'], 'firmware': ['firmware_event_logic', 'board_firmware_interfaces'],
                    'bom': ['schematic_bom_pins'], 'documents': ['delivery_version']}
        for part, items in groups.items():
            gates = [g for g in (meta.get('acceptance') or {}).get('functional_gates', []) if g['id'] in gate_for[part]]
            checks = {g['label']: True if g['status'] == 'PASS' else False if g['status'] == 'FAIL' else g['status'] for g in gates}
            rows.append(dict(id='candidate:' + design_id + ':' + part, kind='candidate-' + part,
                domain=items[0]['domain'], label=LABELS[part], created=created, status='PUBLISHED', error=None,
                source_type='candidate', candidate_id=design_id, applicability=items[0]['applicability'],
                created_revision=None, metrics=[], inputs={'design_id': design_id, 'selected_jobs': meta['selected_jobs']},
                conditions={}, checks=checks, scope=meta['label'], files=items, source_sha256=identity(items),
                design_status='FAIL' if any(g['status'] == 'FAIL' for g in gates) else None,
                source_files=[], interfaces={}, design_inputs={}, readback_passed=False, hardware_verified=False))
        return rows, files, meta

    def file(self, owner, key):
        bits = key.split('/'); design_id = bits[1] if len(bits) > 1 else ''
        design = self.design(owner, design_id); sources = self.sources(owner, design)
        if bits[0] == 'candidate':
            if key not in sources: raise PermissionError('CANDIDATE_FILE_NOT_FOUND')
            path, item = sources[key]
        elif bits[0] == 'preview' and len(bits) > 3:
            published = self.publication(owner, design_id, sources, bits[2])
            if not published or bits[2] != published[0]: raise PermissionError('PREVIEW_NOT_PUBLISHED')
            name = '/'.join(bits[3:]); item = next((f for f in published[1]['files'] if f['name'] == name), None)
            if not item: raise PermissionError('PREVIEW_FILE_NOT_FOUND')
            path = safe(self.preview_root / owner / design_id / bits[2], name)
        else: raise PermissionError('CANDIDATE_FILE_NOT_FOUND')
        good, error = self.catalog._integrity(path, item['sha256'])
        if not good: raise ValueError('CANDIDATE_FILE_INVALID: ' + error)
        return path, path.name

    def version(self, owner):
        task = self.task(owner)
        if not task: return None
        design_id = task['intent'].get('working_design') or task['current_design']
        pointer = self.preview_root / owner / design_id / 'current.json'
        return {'task': task, 'publication': pointer.read_text() if pointer.is_file() and not pointer.is_symlink() else None}
