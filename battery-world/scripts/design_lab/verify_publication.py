#!/usr/bin/env python3
"""Verify the published source/evidence bytes without model or solver calls."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('PUBLIC_ARCHIVE_CRC_FAILED:' + str(path))
        manifest = json.loads(archive.read('MANIFEST.json'))
        entries = manifest.get('files')
        if entries is None:
            entries = [{'path': name, **entry} for name, entry in manifest['members'].items()]
        expected = {entry['path'] for entry in entries} | {'MANIFEST.json'}
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
            raise ValueError('PUBLIC_ARCHIVE_MEMBERS_MISMATCH:' + str(path))
        for entry in entries:
            data = archive.read(entry['path'])
            if len(data) != entry['bytes'] or digest(data) != entry['sha256']:
                raise ValueError('PUBLIC_ARCHIVE_HASH_FAILED:' + entry['path'])
        return len(entries)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkout', type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    root = args.checkout.resolve()
    publication = root / 'battery-world/docs/agentlab/refactor-r3-r5-20261012/github-publication'
    manifest = json.loads((publication / 'SOURCE-PUBLICATION-MANIFEST.json').read_text())
    checked = 0
    for entry in manifest['files']:
        path = root / entry['path']
        if not path.is_file() or path.is_symlink() or root not in path.resolve().parents:
            raise ValueError('PUBLIC_SOURCE_NOT_REGULAR:' + entry['path'])
        data = path.read_bytes()
        if len(data) != entry['bytes'] or digest(data) != entry['sha256']:
            raise ValueError('PUBLIC_SOURCE_HASH_FAILED:' + entry['path'])
        checked += 1
    members = sum(verify_archive(publication / name) for name in manifest['archives'])
    print(json.dumps({'schema_version': 'bf-github-checkout-verification-v1',
        'source_and_evidence_files_verified': checked, 'archive_members_verified': members,
        'model_calls': 0, 'native_solver_calls': 0, 'passed': True,
        'claim': 'Published bytes and public archive members only; no new engineering or physical acceptance.'}))


if __name__ == '__main__':
    main()
