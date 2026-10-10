#!/usr/bin/env python3
"""Reproduce the bounded analysis's deterministic and fail-closed output tests.

Only synthetic temporary fixtures are modified. Original inputs are read-only.
The test receipt must also be a new path and is created exclusively.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(args):
    script = Path(__file__).with_name('analyze_passive.py')
    names = ['BF_Conditional_Passive_20261001_core.zip', 'BF_Conditional_Passive_20261001_raw47.tar.xz', 'BF_Conditional_Passive_20261001_raw10.tar.xz']
    files = [args.archive_dir / n for n in names]
    before = {p.name:sha(p) for p in files}
    tests = []
    with tempfile.TemporaryDirectory(prefix='passive-analysis-selftest-') as tmp:
        tmp = Path(tmp)

        def run(directory, output, recovery=None):
            cmd = [sys.executable, '-B', str(script), '--archive-dir', str(directory), '--out', str(output)]
            if recovery:
                cmd += ['--recovery-index', str(recovery)]
            return subprocess.run(cmd, capture_output=True, text=True)

        p = run(args.archive_dir, tmp/'rerun.json', args.recovery_index)
        tests.append({'test':'deterministic_readonly_replay', 'pass':p.returncode == 0 and (tmp/'rerun.json').read_bytes() == args.reference_result.read_bytes()})
        missing=tmp/'missing'; missing.mkdir()
        p=run(missing,tmp/'missing.json'); result=json.loads((tmp/'missing.json').read_text())
        tests.append({'test':'missing_archive_fail_closed','pass':p.returncode == 1 and result['status']=='BLOCKED_OR_FAILED','observed_error_type':result.get('error_type')})
        corrupt=tmp/'corrupt'; corrupt.mkdir()
        data=bytearray(files[0].read_bytes()); data[-1]^=1; (corrupt/files[0].name).write_bytes(data)
        p=run(corrupt,tmp/'corrupt.json'); result=json.loads((tmp/'corrupt.json').read_text())
        tests.append({'test':'one_byte_archive_corruption_fail_closed','pass':p.returncode == 1 and 'archive SHA mismatch' in result.get('error',''),'observed_error':result.get('error')})
        p=run(args.archive_dir,files[0])
        tests.append({'test':'immutable_archive_output_rejected','pass':p.returncode==2 and 'Output must be outside' in p.stderr})
        source=tmp/'synthetic-source.npz'; original=b'Synthetic protected source bytes; not scientific data.\n'; source.write_bytes(original)
        existing=tmp/'existing-output.json'; existing.write_bytes(b'Previous generated output\n')
        symlink=tmp/'symlink-output.json'; symlink.symlink_to(source)
        broken=tmp/'broken-output.json'; missing_target=tmp/'target-must-stay-missing.json'; broken.symlink_to(missing_target)
        hardlink=tmp/'hardlink-output.json'; os.link(source,hardlink)
        directory=tmp/'directory-output'; directory.mkdir()
        cases=[('existing_regular_output_rejected',existing),('existing_source_file_rejected',source),('symlink_to_source_rejected',symlink),('broken_symlink_rejected',broken),('hardlink_to_source_rejected',hardlink),('existing_directory_rejected',directory)]
        for label,target in cases:
            initial_link=os.readlink(target) if target.is_symlink() else None
            initial_bytes=target.read_bytes() if target.is_file() else None
            p=run(args.archive_dir,target)
            preserved=(os.readlink(target)==initial_link) if initial_link is not None else (target.read_bytes()==initial_bytes if initial_bytes is not None else target.is_dir())
            tests.append({'test':label,'pass':p.returncode==2 and 'Output must be a new path' in p.stderr and preserved})
        tests.append({'test':'synthetic_original_and_broken_target_preserved','pass':source.read_bytes()==original and not missing_target.exists() and os.path.lexists(broken)})
        if args.extracted_evidence_file:
            protected=args.extracted_evidence_file; digest=sha(protected)
            p=run(args.archive_dir,protected)
            tests.append({'test':'original_extracted_evidence_output_rejected','pass':p.returncode==2 and 'Output must be a new path' in p.stderr and sha(protected)==digest,'protected_member_basename':protected.name,'sha256_before_equals_after':sha(protected)})
        # Review the final-write safeguard itself, not only the early existence check.
        tests.append({'test':'final_write_is_exclusive_creation','pass':"args.out.open('x', encoding='utf-8')" in script.read_text() and 'args.out.write_text' not in script.read_text()})
    after={p.name:sha(p) for p in files}
    tests.append({'test':'all_original_archives_unchanged','pass':before==after})
    return {'schema':'bf-passive-analysis-selftest-v2','all_pass':all(t['pass'] for t in tests),'tests':tests,'script_sha256':sha(script),'self_test_script_sha256':sha(Path(__file__)),'results_sha256':sha(args.reference_result),'new_scientific_solves':0,'temporary_fixtures_removed':True,'original_archive_sha256_after':after}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive-dir',type=Path,required=True)
    p.add_argument('--recovery-index',type=Path)
    p.add_argument('--reference-result',type=Path,required=True)
    p.add_argument('--extracted-evidence-file',type=Path)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if os.path.lexists(args.out):
        p.error('Receipt output must be a new path')
    result=main(args)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    try:
        with args.out.open('x',encoding='utf-8') as out:
            out.write(json.dumps(result,indent=2)+'\n')
    except FileExistsError:
        p.error('Receipt output appeared during testing; refusing overwrite')
    print(json.dumps({'all_pass':result['all_pass'],'tests':len(result['tests']),'receipt':str(args.out)}))
    sys.exit(0 if result['all_pass'] else 1)
