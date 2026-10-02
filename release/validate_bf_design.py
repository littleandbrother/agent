"""Rebuild and test the reviewed BF sources without models or vendor execution.

The immutable checkpoint and historical receipts are never written to. Output is
a new local integration revision, not a repaired historical seal or live runtime.
"""
import argparse
import ast
import hashlib
import io
import json
import os
import platform
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tokenize

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / 'review/bf-design-checkpoint'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def relocate_python(source, mapping):
    """Replace string values, never inject a filesystem path as Python syntax."""
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    edits = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.STRING:
            continue
        try:
            value = ast.literal_eval(token.string)
        except (SyntaxError, ValueError):
            continue
        if not isinstance(value, str):
            continue
        changed = value
        for old, new in mapping.items():
            changed = changed.replace(old, new)
        if changed != value:
            begin = offsets[token.start[0] - 1] + token.start[1]
            end = offsets[token.end[0] - 1] + token.end[1]
            edits.append((begin, end, repr(changed)))
    for begin, end, replacement in reversed(edits):
        source = source[:begin] + replacement + source[end:]
    ast.parse(source)
    return source


def test_coverage(text, code):
    """unittest returns zero even when required coverage is skipped."""
    skipped = re.search(r'OK \(skipped=(\d+)\)', text)
    count = re.search(r'Ran (\d+) tests? in ', text)
    return {'tests_run': int(count[1]) if count else None,
            'skipped_count': int(skipped[1]) if skipped else 0,
            'status': 'blocked' if code == 0 and skipped else ('passed' if code == 0 else 'failed')}


def validation_environment(source=None):
    """Pass the explicit current-source seal, without leaking runtime secrets."""
    source = os.environ if source is None else source
    allowed = ('PATH', 'HOME', 'SYSTEMROOT', 'TEMP', 'TMP', 'LANG',
               'BF_INTEGRATION_SOURCE_MANIFEST')
    return {k: v for k, v in source.items() if k in allowed}


def verify_checkpoint():
    manifest = json.loads((CHECKPOINT / 'SOURCE-MANIFEST.json').read_text())
    for row in manifest['files']:
        path = (ROOT / row['path']).resolve()
        if not path.is_relative_to(CHECKPOINT) or not path.is_file():
            raise ValueError('CHECKPOINT_FILE_MISSING: ' + row['path'])
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('CHECKPOINT_FILE_CHANGED: ' + row['path'])
    return len(manifest['files'])


def verify_repository_sources():
    """Keep the published baseline immutable; bind intentional revisions separately."""
    current = os.environ.get('BF_INTEGRATION_SOURCE_MANIFEST')
    if current:
        path = Path(current)
        manifest = json.loads(path.read_text())
        if manifest.get('schema_version') != 'integration-source-manifest-v1':
            raise ValueError('INTEGRATION_SOURCE_MANIFEST_SCHEMA')
        for row in manifest['files']:
            source = (ROOT/row['path']).resolve()
            if not source.is_relative_to(ROOT) or sha(source) != row['sha256']:
                raise ValueError('INTEGRATION_CURRENT_SOURCE_DRIFT:'+row['path'])
        return {'mode':'explicit_new_integration_manifest','files':len(manifest['files']),
                'manifest_sha256':sha(path),'historical_seal_reissued':False,'scientific_qualified':False}

    baseline = json.loads((ROOT / 'release/source-manifest.json').read_text())
    revision = json.loads((ROOT / 'release/bf-design-source-revision.json').read_text())
    changed = {row['path']: row for row in revision['files']}
    baseline_paths = {row['path'] for row in baseline['files']}
    if not set(changed).issubset(baseline_paths):
        raise ValueError('REVISION_PATH_NOT_IN_BASELINE')
    for row in baseline['files']:
        target = ROOT / row['path']
        update = changed.get(row['path'])
        if update and update['baseline_sha256'] != row['sha256']:
            raise ValueError('REVISION_BASELINE_DRIFT: ' + row['path'])
        expected = update['sha256'] if update else row['sha256']
        if sha(target) != expected:
            raise ValueError('REPOSITORY_SOURCE_DRIFT: ' + row['path'])
    return {'baseline_files': len(baseline['files']), 'revised_files': len(changed)}


def prepare(output):
    count = verify_checkpoint()
    repository = verify_repository_sources()
    output.mkdir(parents=True, exist_ok=False)
    sources = output / 'sources'
    shutil.copytree(CHECKPOINT, sources)
    control = sources / 'controlled-integration'
    service = output / 'service'
    shutil.copytree(control / 'layer-02-magnetic-service', service)
    patch = sources / 'method-patch/patch-work'
    manifest = json.loads((patch / 'PATCH-SOURCE-MANIFEST.json').read_text())
    for row in manifest['files']:
        target = service / row['path']
        before = sha(target) if target.exists() else None
        if before != row['before_sha256']:
            raise ValueError('METHOD_PATCH_BASE_DRIFT: ' + row['path'])
        source = patch / 'changed' / row['path']
        if sha(source) != row['after_sha256']:
            raise ValueError('METHOD_PATCH_SOURCE_DRIFT: ' + row['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    # Relocate executable Python only. Historical JSON locks and receipts keep
    # their exact bytes and must NOT be relabelled as current successful checks.
    mapping = {
        '/workspace/shared/current-cache-integration-20261001/working': str(ROOT),
        '/workspace/shared/controlled-launcher-integration-20261001': str(control / 'layer-01-launcher'),
        '/workspace/shared/authoritative-world-20261001': str(sources / 'development/evidence/authoritative-world-20261001'),
        '/workspace/shared/controlled-agent-protocol-20261001': str(sources / 'development/evidence/controlled-agent-protocol-20261001'),
        '/workspace/shared/causal-evaluator-repair-20261001': str(sources / 'development/evidence/causal-evaluator-repair-20261001'),
    }
    relocations = []
    for path in sorted(service.rglob('*.py')):
        original = path.read_text()
        text = relocate_python(original, mapping)
        if text != original:
            before = sha(path)
            path.write_text(text)
            relocations.append({'path': str(path.relative_to(output)), 'before_sha256': before, 'after_sha256': sha(path)})

    # The old generator copies the pre-method H0 over final reviewed sources.
    # Keep it in the checkpoint, but fail closed at BOTH generated entrypoints.
    guard = 'raise SystemExit("LEGACY_GENERATOR_DISABLED: rerun release/validate_bf_design.py with a new --output; never regenerate over the final method patch")\n'
    for directory in [service, control / 'layer-01-launcher', control / 'layer-02-magnetic-service']:
        (directory / 'build_overlay.py').write_text(guard)

    # Existing independent tests now import the actually merged service files.
    # Copies avoid symlinks and work on Windows as well as POSIX.
    shutil.rmtree(patch / 'changed')
    shutil.copytree(service, patch / 'changed')
    (patch / 'reports').mkdir(exist_ok=True)
    rows = [{'path': str(p.relative_to(output)), 'sha256': sha(p)}
            for p in sorted(service.rglob('*')) if p.is_file()]
    write(output / 'INTEGRATION.json', {
        'schema': 'bf-design-local-integration-v1', 'checkpoint_files_verified': count,
        'repository_source_verification': repository,
        'checkpoint_manifest_sha256': sha(CHECKPOINT / 'SOURCE-MANIFEST.json'),
        'method_patch_files': len(manifest['files']), 'relocation_map': mapping,
        'relocated_sources': relocations, 'service_files': rows,
        'historical_seals_reissued': False, 'live_execution_authorized': False,
        'root_cache_source_sha256': sha(ROOT / 'battery-world/packages/python/bfworld/src/bfworld/agentlab/simulation_chain/cache.py'),
    })
    return sources, service, patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New, nonexistent local output directory')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(CHECKPOINT):
        parser.error('Output cannot be inside the immutable checkpoint')
    sources, service, patch = prepare(output)
    logs = output / 'logs'
    logs.mkdir()
    # Do not inherit credentials, endpoint switches or vendor/model configuration.
    env = validation_environment()
    env.update(PYTHONDONTWRITEBYTECODE='1', BF_HOME=str(output / 'isolated-home'))
    checks = []

    def run(name, command, cwd, extra=None):
        coverage = {}
        try:
            result = subprocess.run(command, cwd=cwd, env={**env, **(extra or {})},
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
            text, code = result.stdout, result.returncode
            coverage = test_coverage(text, code)
            status = coverage['status']
        except (OSError, subprocess.TimeoutExpired) as exc:
            text, code, status = str(exc), None, 'blocked'
        (logs / (name + '.log')).write_text(text)
        checks.append({'name': name, 'status': status, 'exit_code': code,
                       **coverage,
                       'command': command, 'cwd': str(cwd), 'log': 'logs/' + name + '.log'})
        print(name + ': ' + status, flush=True)
        return status == 'passed'

    run('integration-regression', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'release', '-p', 'test_bf_design_validation.py', '-v'], ROOT)
    run('cache-contracts', [sys.executable, '-B', '-m', 'unittest',
        'test_simulation_chain.ContractsAndRecovery', 'test_simulation_chain.CacheConsistencyTests', '-v'],
        ROOT / 'battery-world/tests/agentlab', {'PYTHONPATH': str(ROOT / 'battery-world/packages/python/bfworld/src')})
    run('method-node', ['node', '--experimental-strip-types', '--test',
        *map(str, sorted((patch / 'tests/independent').glob('*.test.mjs')))], patch)
    run('method-python', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/independent', '-p', 'test_*.py', '-v'], patch)
    run('method-syntax', ['node', 'tests/build_offline.mjs'], patch)
    evaluator = sources / 'development/evidence/causal-evaluator-repair-20261001'
    run('causal-contracts', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_causal_evaluator.py', '-v'], evaluator)
    requirements = {
        'beam-rom': ('static-rom/beam', ['sources/piezo-material-20261001.html']),
        'magnetic-interface': ('static-rom/magnetic', ['outputs/STATIC-RESULTS.json', 'evidence-completion-replay/RAW-REPLAY-RESULTS.json']),
        'native-kit-contracts': ('native-observation', []),
    }
    for name, (component, required) in requirements.items():
        missing = [str(Path(component) / p) for p in required if not (sources / component / p).is_file()]
        if missing:
            checks.append({'name': name, 'status': 'blocked', 'missing_prerequisites': missing,
                           'reason': 'Excluded from the source checkpoint; do not fabricate provenance or retained results.'})
            print(name + ': blocked (missing checkpoint prerequisites)', flush=True)
        else:
            run(name, [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], sources / component)
    # Guard regression: rebuilding must stop without changing final method bytes.
    before = {str(p.relative_to(service)): sha(p) for p in service.rglob('*') if p.is_file()}
    stopped = subprocess.run([sys.executable, '-B', 'build_overlay.py'], cwd=service,
                             env=env, capture_output=True, text=True)
    after = {str(p.relative_to(service)): sha(p) for p in service.rglob('*') if p.is_file()}
    checks.append({'name': 'generator-preserves-method', 'status': 'passed' if stopped.returncode != 0 and 'LEGACY_GENERATOR_DISABLED' in stopped.stderr and before == after else 'failed'})
    verify_checkpoint()
    from bf_design_runtime import prepare_runtime, seal_runtime
    compiler = ROOT / 'pi-bf-aiot/node_modules/.bin/tsgo'
    if not compiler.is_file():
        checks.append({'name': 'full-pi-build-and-service-probe', 'status': 'blocked',
                       'reason': 'Pinned compiler missing. Restore pi-bf-aiot dependencies with npm ci --ignore-scripts --no-audit --no-fund; no install is performed by this entrypoint.'})
    else:
        built = run('pi-offline-build', ['npm', 'run', 'bf:build'], ROOT / 'pi-bf-aiot')
        typed = run('pi-project-typecheck', [str(compiler), '--noEmit'], ROOT / 'pi-bf-aiot')
        if built and typed:
            pi = prepare_runtime(output, sources, service)
            compiled = True
            for package in ['bf-harness', 'bf-agent']:
                compiled = run('overlay-' + package, [str(compiler), '-p', str(pi / 'packages' / package / 'tsconfig.json')], pi) and compiled
            if compiled:
                seal_runtime(output, sources, service)
                probe = run('controlled-service-probe', [sys.executable, '-B', 'run_probe.py', '--method', 'bf_design', '--output', str(service / 'reports/local-probe')], service)
                if probe:
                    run('controlled-service-tests', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], service)
                run('runtime-lock-after-tests', [sys.executable, '-B', '-c',
                    'import json; from local_inputs import verify_inputs; print(json.dumps(verify_inputs()))'], service / 'src')
    run('source-preservation-after-tests', [sys.executable, '-B', '-c',
        'from validate_bf_design import verify_checkpoint, verify_repository_sources; print(verify_checkpoint(), verify_repository_sources())'], ROOT / 'release')
    checks += [
        {'name': 'passive-and-authoritative-world-full-replay', 'status': 'unrun', 'reason': 'Separate modules retained; original source provenance, transitive paths and new execution receipts still required.'},
        {'name': 'historical-raw-replay', 'status': 'blocked', 'reason': 'Checkpoint excludes raw traces, vendor payloads, auth fixtures and runtime files; original sealed archives required.'},
        {'name': 'native-agent-method-experiments', 'status': 'unrun', 'reason': 'No vendor/model execution authorized; task qualification, model/budget authorization and participant isolation remain open.'},
        {'name': 'repository-init', 'status': 'unrun', 'reason': 'This entrypoint is a bounded offline suite, not full repository health verification.'},
    ]
    failed = any(c['status'] == 'failed' for c in checks)
    blocked = any(c['status'] == 'blocked' for c in checks)
    report = {'schema': 'bf-design-local-validation-v1', 'scope': 'offline software contracts only',
              'entrypoint_sha256': sha(Path(__file__)), 'python_version': platform.python_version(),
              'all_checks_passed': not failed and not blocked and not any(c['status'] == 'unrun' for c in checks),
              'executed_checks_passed': not failed and not any(c.get('skipped_count', 0) for c in checks), 'scientific_success': False,
              'native_execution': False, 'model_calls': 0, 'checks': checks}
    write(output / 'VALIDATION.json', report)
    print('Report: ' + str(output / 'VALIDATION.json'))
    return 1 if failed else (2 if blocked else 0)


if __name__ == '__main__':
    raise SystemExit(main())
