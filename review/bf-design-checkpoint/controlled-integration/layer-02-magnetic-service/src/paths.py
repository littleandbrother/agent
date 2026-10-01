from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sys
ROOT = Path(__file__).resolve().parents[1]
FIRST = Path('/workspace/shared/controlled-launcher-integration-20261001')
WORKING = Path('/workspace/shared/current-cache-integration-20261001/working')
REPO = WORKING / 'battery-world'
PI_SOURCE = WORKING / 'pi-bf-aiot'
PI = ROOT / 'pi-overlay'
WORLD = Path('/workspace/shared/authoritative-world-20261001')
PROTOCOL = Path('/workspace/shared/controlled-agent-protocol-20261001')
EVALUATOR = Path('/workspace/shared/causal-evaluator-repair-20261001/src/causal_evaluator_v2.py')
sys.path.insert(0, str(REPO / 'packages/python/bfworld/src'))
sys.dont_write_bytecode = True
os.environ['BF_PI_ROOT'] = str(PI)
os.environ['BF_HOME'] = str(ROOT / 'fixture-runtime')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def verify_inputs():
    original = read(FIRST / 'INPUT-LOCK.json')['files']
    sealed = read(FIRST / 'FILE-MANIFEST.json')['files']
    bad = [p for p, value in original.items() if sha(p) != value]
    bad += [str(FIRST / p) for p, value in sealed.items() if sha(FIRST / p) != value['sha256']]
    if bad:
        raise ValueError('SEALED_INPUT_CHANGED:' + ','.join(bad))
    return {'original_files': len(original), 'first_layer_files': len(sealed), 'unchanged': True}
