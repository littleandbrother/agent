#!/usr/bin/env python3
"""Read and verify the sealed engineering delivery; never dispatch work."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path,
                        default=Path.home()/'.local/share/bf-agent-architecture-v2')
    args = parser.parse_args()
    expected = json.loads(Path(__file__).with_name('RESULTS.json').read_text())
    repository = args.runtime/'workbench/design-lab/repository'
    root = repository/'node-realizations'/expected['realization_id']
    payload = (root/'manifest.json').read_bytes()
    assert sha(payload) == expected['manifest_sha256'], 'REALIZATION_MANIFEST_CHANGED'
    manifest = json.loads(payload)
    assert manifest['system_id'] == expected['system_id']
    assert manifest['execution_id'] == expected['execution_id']
    assert manifest['native'] and manifest['new_physics_solves'] == 0
    for name, entry in manifest['outputs'].items():
        data = (root/name).read_bytes()
        assert len(data) == entry['bytes'] and sha(data) == entry['sha256'], name
    with zipfile.ZipFile(root/'handoff.zip') as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts, name
        checksums = json.loads(archive.read('checksums.json'))
        for name, entry in checksums.items():
            data = archive.read(name)
            assert len(data) == entry['bytes'] and sha(data) == entry['sha256'], name
        assert archive.read('native/project.epro2') == (root/'native/project.epro2').read_bytes()
    assembly = json.loads((root/'assembly-readback.json').read_text())
    assert assembly['native_valid'] and assembly['solid_count'] == 32
    assert assembly['interferences'] == []
    assert assembly['beam_free_length_mm'] == 90 and assembly['beam_width_mm'] == 30
    target = json.loads((root/'target-status.json').read_text())
    assert target['status'] == 'BUILT' and target['memory_fit']
    summary = json.loads((root/'summary.json').read_text())
    assert summary['native_drc_passed'] and summary['digital_frames'] == 15
    assert summary['board_review']['warnings'] == 12
    assert (root/'index.html').read_text().count('NODE_BUNDLE') >= 2
    release = repository/'releases'/f"{expected['release_id']}.zip"
    seal = json.loads(release.with_suffix('.seal.json').read_text())
    data = release.read_bytes()
    assert seal['target'] == expected['system_id']
    assert seal['bytes'] == len(data) and seal['sha256'] == sha(data)
    with zipfile.ZipFile(release) as archive:
        assert archive.testzip() is None
    print(json.dumps({'status': 'PASS', 'system_id': expected['system_id'],
                      'verified_outputs': len(manifest['outputs']), 'step_solids': 32,
                      'native_drc': 'PASS', 'new_physics_solves': 0,
                      'model_calls': 0, 'native_dispatches': 0}))


if __name__ == '__main__':
    main()
