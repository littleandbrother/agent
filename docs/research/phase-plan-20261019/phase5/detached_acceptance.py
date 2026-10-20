"""One focused independent-directory acceptance; no source-path fallback."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DELIVERY = ROOT / 'deliveries/BF_FINAL_20261020'


def run():
    assert not (HERE / 'detached-acceptance.json').exists(), 'ACCEPTANCE_ALREADY_RECORDED'
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='bf-final-detached-') as tmp:
        temporary = Path(tmp)
        bundle = temporary / 'portable'
        shutil.copytree(DELIVERY, bundle)
        scratch_bytes = sum(p.stat().st_size for p in bundle.rglob('*') if p.is_file())
        guard = temporary / 'guard'
        guard.mkdir()
        # sitecustomize also guards each Python paper subprocess. Dependencies
        # under the configured runtime remain readable, original research/data
        # roots and all Python network connections do not.
        blocked = [str(ROOT), str(Path.home() / '.local/share/bf-')]
        (guard / 'sitecustomize.py').write_text(
            'import os,sys\n'
            f'BLOCKED={blocked!r}\n'
            'def audit(event,args):\n'
            ' if event=="socket.connect": raise RuntimeError("NETWORK_FORBIDDEN")\n'
            ' if event=="open" and isinstance(args[0],(str,bytes)):\n'
            '  p=os.path.realpath(os.fsdecode(args[0]))\n'
            '  if any(p.startswith(x) for x in BLOCKED): raise RuntimeError("ORIGINAL_SOURCE_READ_FORBIDDEN")\n'
            'sys.addaudithook(audit)\n')
        env = {k: v for k, v in os.environ.items() if not k.startswith(('BF_', 'BFWORLD_', 'PI_'))}
        env.update(PYTHONPATH=str(guard), PYTHONDONTWRITEBYTECODE='1')
        # Falsifier: one changed real native BOM must be refused before any
        # generated figure/statistic is accepted. Original remains untouched.
        bom = bundle / 'engineering/piezo-node/native/bom.csv'
        original_bom = bom.read_bytes()
        bom.write_bytes(original_bom + b'\n')
        negative = subprocess.run([sys.executable, '-B', '-c',
            'import runpy,pathlib; m=runpy.run_path("reproduce.py"); m["verify_manifest"](pathlib.Path.cwd())'],
            cwd=bundle, env=env, capture_output=True, text=True, timeout=30)
        assert negative.returncode and 'FILE_DIGEST_MISMATCH' in negative.stderr, 'TAMPER_NOT_REJECTED'
        bom.write_bytes(original_bom)
        (HERE / 'detached-negative-control.log').write_text(negative.stderr)
        result_dir = temporary / 'rebuilt'
        command = [sys.executable, '-B', 'reproduce.py', '--output', str(result_dir)]
        result = subprocess.run(command, cwd=bundle, env=env, capture_output=True, text=True, timeout=240)
        (HERE / 'detached-acceptance.stdout.log').write_text(result.stdout)
        (HERE / 'detached-acceptance.stderr.log').write_text(result.stderr)
        if result.returncode:
            (HERE / 'detached-attempt-failed.json').write_text(json.dumps({'exit_code': result.returncode, 'stdout_log': 'detached-acceptance.stdout.log', 'stderr_log': 'detached-acceptance.stderr.log'}, indent=2))
            raise RuntimeError('DETACHED_ACCEPTANCE_FAILED; exact logs retained')
        payload = json.loads((result_dir / 'result.json').read_text())
        assert payload['status'] == 'PASS'
        saved = HERE / 'detached-results'
        shutil.copytree(result_dir, saved)
        receipt = {'schema_version': 'bf-final-detached-acceptance-v1', 'status': 'PASS',
                   'method': 'Fresh temporary directory, all original research/runtime source reads and Python network blocked; same-process and Python subprocess guard.',
                   'manifest_sha256': hashlib.sha256((bundle / 'MANIFEST.json').read_bytes()).hexdigest(),
                   'result': payload, 'negative_control': 'Actual BOM byte tamper rejected as FILE_DIGEST_MISMATCH',
                   'new_models': 0, 'new_scientific_executions': 0, 'new_native_dispatches': 0,
                   'prior_unchanged343test_CI': 'Reused phase4 final-integration.json; not repeated',
                   'prior_native_and_target_rebuild': 'Same inputs; saved native/40-command identical-HEX receipts reused',
                   'temporary_copy_logical_bytes': scratch_bytes,
                   'temporary_outputs_logical_bytes': sum(p.stat().st_size for p in result_dir.rglob('*') if p.is_file()),
                   'temporary_directory_removed': True, 'elapsed_s': time.monotonic() - started}
    (HERE / 'detached-acceptance.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'scratch_removed_bytes': scratch_bytes, 'elapsed_s': receipt['elapsed_s']}))


if __name__ == '__main__':
    run()
