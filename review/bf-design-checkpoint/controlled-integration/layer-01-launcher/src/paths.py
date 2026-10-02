"""Explicit read-only inputs; all runtime writes stay in the additive overlay."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKING = Path('/workspace/shared/current-cache-integration-20261001/working')
REPO = WORKING / 'battery-world'
PI_SOURCE = WORKING / 'pi-bf-aiot'
PI = ROOT / 'pi-overlay'
WORLD = Path('/workspace/shared/authoritative-world-20261001')
PROTOCOL = Path('/workspace/shared/controlled-agent-protocol-20261001')
EVALUATOR = Path('/workspace/shared/causal-evaluator-repair-20261001/src/causal_evaluator_v2.py')
PYTHON_ROOT = REPO / 'packages/python/bfworld/src'
sys.path.insert(0, str(PYTHON_ROOT))
os.environ['BF_PI_ROOT'] = str(PI)
os.environ['BF_HOME'] = str(ROOT / 'fixture-runtime')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def source_paths():
    # All repository Python inputs, restored Pi source/build files, lock, and
    # sealed contracts are read, not copied back into their original packages.
    files = list(PYTHON_ROOT.rglob('*.py'))
    for p in (PI_SOURCE / 'packages').rglob('*'):
        if p.is_file() and not p.is_symlink() and 'node_modules' not in p.parts and (
            'src' in p.parts or 'dist' in p.parts
        ) and p.suffix in {'.ts', '.js', '.json'}:
            files.append(p)
    files += [PI_SOURCE / 'package-lock.json', PI_SOURCE / 'package.json',
              PROTOCOL / 'preflight.py', PROTOCOL / 'protocol-world-bound-draft.json',
              PROTOCOL / 'SOURCE-MANIFEST.json', WORLD / 'FREEZE-RECEIPT.json',
              WORLD / 'FILE-MANIFEST.json', WORLD / 'contracts/tasks-v2.json', EVALUATOR]
    files += list((WORLD / 'pipeline-handoff-v2').glob('*.py'))
    files += list((WORLD / 'pipeline-handoff-v2').glob('*.json'))
    files += list((WORLD / 'src').glob('*.py'))
    return sorted(set(files))

def verify_sources():
    expected = read(ROOT / 'INPUT-LOCK.json')['files']
    changed = [p for p, value in expected.items() if not Path(p).is_file() or sha(p) != value]
    if changed:
        raise ValueError('PINNED_INPUT_DRIFT:' + ','.join(changed))
    return {'files': len(expected), 'input_lock_hash': sha(ROOT / 'INPUT-LOCK.json'), 'unchanged': True}

