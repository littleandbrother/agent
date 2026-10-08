"""Verify and link an existing immutable engineering case to a named task.

Reading archived bytes also materializes macOS cloud placeholders. A linked
case remains operator-assisted evidence, never an Agent assembly acceptance.
The original design directory and publication are not rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

from bfworld.agentlab.product_results import ProductResults
from bfworld.agentlab.store import Store, identity


def restore(catalog, source_owner, owner, case_id, version):
    catalog.sources.require(source_owner)
    catalog.sources.require(owner)
    with catalog.store.connect() as db:
        row = db.execute(
            'SELECT payload FROM engineering_case_releases WHERE owner=? AND id=? AND version=?',
            (source_owner, case_id, version),
        ).fetchone()
    if row is None:
        raise ValueError('CASE_RELEASE_NOT_FOUND')
    manifest = json.loads(row['payload'])
    with tempfile.TemporaryDirectory(prefix='bf-case-readback-') as folder:
        stage = Path(folder)
        for group in manifest['groups']:
            for file in group['files']:
                rel = Path(file['path'])
                if rel.is_absolute() or '..' in rel.parts or any(p.startswith('.') for p in rel.parts):
                    raise PermissionError('CASE_PATH_DENIED')
                archive = catalog.cases.archive_path(source_owner, file['sha256'], file['name'])
                roots=(catalog.cases.root.resolve(),catalog.cases.legacy_root.resolve())
                if archive.is_symlink() or not any(archive.resolve().is_relative_to(root) for root in roots):
                    raise PermissionError('CASE_PATH_DENIED')
                data = archive.read_bytes()
                if hashlib.sha256(data).hexdigest() != file['sha256'] or len(data) != file['bytes']:
                    raise ValueError('CASE_ARCHIVE_CORRUPT')
                dest = stage / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        saved = catalog.cases.publish(owner, stage, manifest)
    _, files, _ = catalog.cases.collect(owner)
    selected = [f for f in files if f['case_id'] == case_id and f['case_version'] == version]
    return dict(owner=owner, case_id=case_id, version=version, files=len(selected),
                integrity=all(f['integrity'] for f in selected),
                manifest_sha256=identity(saved), autonomous_agent_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--from-owner', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    catalog = ProductResults(SimpleNamespace(store=Store(args.state)))
    print(json.dumps(restore(catalog, args.from_owner, args.owner, args.case, args.version)))


if __name__ == '__main__':
    main()
