"""Publish derived views beside a frozen candidate; never rewrite the design."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

from .candidate_results import CandidateResults, LABELS
from .store import canonical, identity


def publish(catalog, owner, design_id, views, *, renderer, channel_units=None):
    reader = CandidateResults(catalog); task = reader.task(owner)
    if not task or (task['intent'].get('working_design') or task['current_design']) != design_id:
        raise ValueError('PREVIEW_CURRENT_CANDIDATE_REQUIRED')
    design = reader.design(owner, design_id); sources = reader.sources(owner, design)
    items = []; data = {}
    for view in views:
        name = view['name']; rel = PurePosixPath(name)
        if not rel.parts or rel.is_absolute() or '..' in rel.parts or '\\' in name or name in data or name == 'manifest.json':
            raise ValueError('PREVIEW_FILE_NAME_INVALID')
        path = Path(view['path'])
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('PREVIEW_FILE_INVALID')
        if not view.get('sources') or not view.get('sections'):
            raise ValueError('PREVIEW_SOURCE_AND_SECTION_REQUIRED')
        if any(part not in LABELS for part in view['sections']):
            raise ValueError('PREVIEW_SECTION_INVALID')
        dependencies = []
        for key in view['sources']:
            if key not in sources: raise ValueError('PREVIEW_SOURCE_NOT_IN_CANDIDATE')
            original, meta = sources[key]
            valid, _ = catalog._integrity(original, meta['sha256'])
            if not valid: raise ValueError('PREVIEW_SOURCE_CHANGED')
            dependencies.append({'id': key, 'sha256': meta['sha256']})
        content = path.read_bytes(); data[name] = content
        items.append(dict(name=name, label=view.get('label', name), sections=view['sections'],
                          sha256=hashlib.sha256(content).hexdigest(), bytes=len(content), sources=dependencies))
    manifest = dict(schema_version='bf-candidate-previews-v1', owner=owner, design_id=design_id,
                    files=items, renderer=renderer, channel_units=channel_units or {})
    pid = identity(manifest); directory = reader.preview_root / owner / design_id / pid
    directory.mkdir(parents=True, exist_ok=True)
    data['manifest.json'] = canonical(manifest).encode()
    for name, content in data.items():
        dest = directory / name; dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if dest.is_symlink() or dest.read_bytes() != content: raise ValueError('PREVIEW_IMMUTABLE_CONFLICT')
        else:
            with dest.open('xb') as stream: stream.write(content)
    # Check the actual files again before making this publication visible.
    for key, (path, meta) in sources.items():
        if any(key == source['id'] for item in items for source in item['sources']):
            if not catalog._integrity(path, meta['sha256'])[0]: raise ValueError('PREVIEW_SOURCE_CHANGED')
    task = reader.task(owner)
    if not task or (task['intent'].get('working_design') or task['current_design']) != design_id:
        raise ValueError('PREVIEW_CANDIDATE_CHANGED')
    ref = canonical({'publication_id': pid, 'sha256': hashlib.sha256(data['manifest.json']).hexdigest()})
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory.parent, delete=False) as stream:
        temporary = Path(stream.name); stream.write(ref); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, directory.parent / 'current.json')
    reader.publication(owner, design_id, sources)
    return dict(design_id=design_id, publication_id=pid, files=len(items), manifest=str(directory / 'manifest.json'))
