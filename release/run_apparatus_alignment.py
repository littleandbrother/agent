"""Re-execute preserved semantic checks against current, explicitly pinned inputs.

The archived lock is copied and relocated to a NEW output, never rewritten. A
successful expected-difference test establishes a difference, not equivalence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'review/bf-design-checkpoint/mainline'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    source = ARCHIVE/'alignment'
    working = output/'harness'
    shutil.copytree(source, working, ignore=shutil.ignore_patterns('__pycache__'))
    # Only the NEW adapter changes BLAS discovery. Preserve equations and old
    # source bytes; unresolved binary ownership remains a hard failure.
    shutil.copyfile(ROOT/'release/alignment_blas.py',working/'src/alignment_blas.py')
    adapter=working/'src/adapters.py'
    original_adapter=adapter.read_text()
    adapter.write_text(original_adapter.replace('import coupled as cloud_force',
        'import coupled as cloud_force\nfrom alignment_blas import providers\ncloud_power.solver_blas_providers = providers'))
    original = json.loads((source/'contracts/source-lock.json').read_text())
    mappings = {
        '/workspace/shared/current-source-reconciliation-20261001/checkout/battery-world': ROOT/'battery-world',
        '/workspace/shared/bf-simulation-chain/battery-world': ARCHIVE/'alignment-inputs/cloud',
        '/workspace/shared/bf-paper-campaigns/event-solver-qualification-20261001-v2': ARCHIVE/'alignment-inputs/event',
    }
    relocated = json.loads(json.dumps(original))
    for row in relocated['sources'].values():
        for prefix, replacement in mappings.items():
            if row['path'].startswith(prefix+'/'):
                row['path'] = str(replacement/row['path'][len(prefix)+1:])
                break
        actual = Path(row['path'])
        if not actual.is_file() or sha(actual) != row['sha256']:
            raise ValueError('ALIGNMENT_SOURCE_DIFFERENT:'+row['path'])
    relocated.update(authority='New current-input alignment; original source lock retained separately',
                     upstream_commit='87e7d75b4c5cd13c96560b8aaa4168a292ddc3c9',
                     archived_lock_sha256=sha(source/'contracts/source-lock.json'))
    (working/'contracts/source-lock.json').write_text(json.dumps(relocated, indent=2)+'\n')
    env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','TEMP','TMP')}
    env.update(BF_ALIGNMENT_UPSTREAM=str(ROOT/'battery-world'),
               BF_ALIGNMENT_CLOUD=str(ARCHIVE/'alignment-inputs/cloud'),
               BF_ALIGNMENT_EVENT=str(ARCHIVE/'alignment-inputs/event'),
               PYTHONDONTWRITEBYTECODE='1')
    command = [sys.executable, str(working/'run_alignment.py'), '--output', str(output/'results')]
    process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
    (output/'runner.log').write_text(process.stdout+process.stderr)
    identity = {'schema_version':'integration-apparatus-alignment-v1',
        'command':command,'exit_code':process.returncode,
        'original_lock_sha256':sha(source/'contracts/source-lock.json'),
        'current_lock_sha256':sha(working/'contracts/source-lock.json'),
        'sources_byte_identical_to_archived_inputs':True,
        'portable_metadata_adapter':{'path':'src/alignment_blas.py',
            'sha256':sha(working/'src/alignment_blas.py'),
            'change':'Recognize package-owned macOS .dylibs; still require both NumPy/SciPy binary hashes',
            'physical_or_numerical_semantics_changed':False},
        'original_lock_unchanged':sha(source/'contracts/source-lock.json')==relocated['archived_lock_sha256'],
        'mainline_selected_for_live_execution':True,
        'full_model_equivalence':False,'physical_qualification':False,
        'scope':'Geometry/kernel, C replay and receiver semantics. No new vendor or paid execution.'}
    (output/'identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    print(process.stdout, end='')
    if process.returncode:
        print(process.stderr)
        raise SystemExit(process.returncode)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
