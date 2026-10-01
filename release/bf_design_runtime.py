"""Assemble the current source overlay for a zero-provider Pi process probe."""
import json
from pathlib import Path
import shutil

from validate_bf_design import ROOT, sha, write


def prepare_runtime(output, sources, service):
    pi_source = ROOT / 'pi-bf-aiot'
    pi = service / 'pi-overlay'
    for name in ['package.json', 'package-lock.json']:
        shutil.copyfile(pi_source / name, pi / name)
    (pi / 'node_modules').symlink_to(pi_source / 'node_modules', target_is_directory=True)
    (pi / 'packages/ai').symlink_to(pi_source / 'packages/ai', target_is_directory=True)
    (service / 'reports').mkdir(exist_ok=True)
    paths = service / 'src/paths.py'
    original = paths.read_text()
    marker = '\ndef verify_inputs():\n'
    if original.count(marker) != 1:
        raise ValueError('INPUT_VERIFIER_PATCH_TARGET_DRIFT')
    paths.write_text(original[:original.index(marker)] + '\nfrom local_inputs import verify_inputs\n')
    shutil.copyfile(ROOT / 'release/bf_design_runtime_inputs.py', service / 'src/local_inputs.py')
    # Handoff remains the exact sealed implementation. Its default argument is
    # relocated at the importing adapter seam, not by changing the frozen core.
    adapter = service / 'src/service_adapter.py'
    text = adapter.read_text()
    old = "handoff.prepare_request(snapshot['candidate'], model, self.profile['native_tools'], task_name=body['task_id'])"
    new = "handoff.prepare_request(snapshot['candidate'], model, self.profile['native_tools'], pipeline_root=handoff_pipeline_root, task_name=body['task_id'])"
    if text.count(old) != 1:
        raise ValueError('HANDOFF_RELOCATION_PATCH_TARGET_DRIFT')
    text = text.replace(old, new)
    text = text.replace("FIXTURE_OWNER = 'trusted-probe'", "FIXTURE_OWNER = 'trusted-probe'\nhandoff_pipeline_root = Path(" + repr(str(ROOT / 'battery-world/packages/python/bfworld/src/bfworld/agentlab/simulation_chain')) + ")")
    adapter.write_text(text)
    # Readback negatives must consume this new probe, never an old archived run.
    test = service / 'tests/test_service.py'
    text = test.read_text()
    old = "run = ROOT / 'reports/probe-v3'\n        if not run.exists():\n            run = ROOT / 'reports/probe-v1'"
    if text.count(old) != 1:
        raise ValueError('TRACE_FIXTURE_RELOCATION_TARGET_DRIFT')
    text = text.replace(old, "run = ROOT / 'reports/local-probe'")
    start = text.index('    def test_prestart_source_modification_rejected_before_packet_or_journal(self):')
    end = text.index('    def test_local_caps_count_all_job_intents_and_snapshot_intents(self):', start)
    text = text[:start] + '''    def test_prestart_source_modification_rejected_before_packet_or_journal(self):
        source = ROOT / 'src/method_contract.py'
        original = source.read_bytes()
        try:
            source.write_bytes(original + b'\\n# synthetic local drift\\n')
            with self.assertRaisesRegex(ValueError, 'LOCAL_INTEGRATION_INPUT_DRIFT'):
                s.RegistryService(self.root / 'should-not-exist', self.settings, method_id='strong_generic')
            self.assertFalse((self.root / 'should-not-exist').exists())
        finally:
            source.write_bytes(original)

''' + text[end:]
    old = "            (workspace / '.pi').mkdir()\n"
    if text.count(old) != 1:
        raise ValueError('METHOD_CANDIDATE_FIXTURE_TARGET_DRIFT')
    text = text.replace(old, old + "            (workspace / 'candidate.json').write_text('{}')\n")
    test.write_text(text)
    return pi


def seal_runtime(output, sources, service):
    """Bind current imports and compiled artifacts after successful builds."""
    pi = service / 'pi-overlay'
    files = set()
    for directory in [service / 'src', service / 'tests',
                      ROOT / 'battery-world/packages/python/bfworld/src',
                      sources / 'development/evidence/authoritative-world-20261001',
                      sources / 'development/evidence/controlled-agent-protocol-20261001',
                      sources / 'development/evidence/causal-evaluator-repair-20261001']:
        files.update(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for base in [ROOT / 'pi-bf-aiot/packages', pi / 'packages']:
        files.update(p for p in base.rglob('*') if p.is_file() and 'node_modules' not in p.parts
                     and ('src' in p.parts or 'dist' in p.parts)
                     and p.suffix in {'.ts', '.js', '.json'})
    files.update([service / 'run_probe.py', pi / 'package-lock.json', pi / 'package.json',
                  ROOT / 'release/bf_design_runtime.py', ROOT / 'release/bf_design_runtime_inputs.py'])
    write(service / 'LOCAL-INPUT-LOCK.json', {
        'schema': 'bf-design-local-runtime-inputs-v1', 'scope': 'new trusted offline integration only',
        'historical_seal': False, 'execution_authorized': False,
        'dependencies': 'Pinned npm lock; third-party node_modules bytes are not individually attested.',
        'files': {str(p): sha(p) for p in sorted(files)},
    })
    write(service / 'reports/BUILD-RECEIPT.json', {
        'schema': 'bf-design-local-pi-build-v1', 'main_source': sha(pi / 'packages/bf-agent/src/main.ts'),
        'main_build': sha(pi / 'packages/bf-agent/dist/main.js'),
        'input_lock_sha256': sha(service / 'LOCAL-INPUT-LOCK.json'),
        'historical_receipt': False, 'provider_calls': 0,
    })
    write(output / 'RUNTIME-INTEGRATION.json', {
        'schema': 'bf-design-local-runtime-revision-v1',
        'input_lock_sha256': sha(service / 'LOCAL-INPUT-LOCK.json'),
        'files': [{'path': str(p.relative_to(service)), 'sha256': sha(p)}
                  for p in sorted(service.rglob('*')) if p.is_file() and not p.is_symlink()
                  and 'node_modules' not in p.parts and '__pycache__' not in p.parts],
        'qualification': False, 'historical_seals_changed': False,
    })
