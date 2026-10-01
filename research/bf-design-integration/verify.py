"""One standard-library offline entrypoint; requires git for scratch patch tests."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
import method_adapter as adapter


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    baseline = adapter.verify_publication(ROOT.parents[1])
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    with (output / 'tests.log').open('w') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    files = [p for directory in ['src', 'tests', 'contracts', 'patches'] for p in (ROOT / directory).rglob('*')
             if p.is_file() and '__pycache__' not in p.parts]
    files.append(Path(__file__))
    report = {'schema': 'bf-design-nominal-adapter-check-v1', 'readiness': 'supplied-for-local-integration',
        'baseline': baseline, 'protocol_hash': adapter.load_protocol()['protocol_hash'],
        'python_version': platform.python_version(), 'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'passed': result.wasSuccessful() and not result.skipped,
        'transport': 'offline injected fixture using published task checker/evaluator/artifact_view',
        'model_calls': 0, 'native_solver_calls': 0, 'scientific_success': False,
        'production_files_modified': False,
        'files': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},
        'remaining_gates': ['local coordinator wiring to real bf_engineering and authorization',
            'local-owned native-model-interface sidecar', 'independent runtime/source identity alignment',
            'model budget ledger and live method delivery qualification; no inherited paid authority']}
    (output / 'VALIDATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
