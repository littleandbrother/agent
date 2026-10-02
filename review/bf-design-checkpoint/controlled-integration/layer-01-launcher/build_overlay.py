"""Build an instrumentation-only copy of the existing Pi entry point.

Never touches the restored tree. No network, install, provider, or model call.
"""
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from paths import ROOT, PI, PI_SOURCE, sha, source_paths, write_once, verify_sources

INSERT = '''
// Controlled activation evidence is emitted only after actual import/call.
// A trusted supervisor binds the fresh process, nonce, exit status and trace.
const binding = config.controlledActivation;
if (!binding || config.dryRun !== true || !["solve", "improve"].includes(config.mode))
    throw new Error("CONTROLLED_OVERLAY_TRUSTED_DRY_RUN_ONLY");
if (binding.harnessSourceHash !== config.sourceManifest.source_hash ||
    binding.appBuildHash !== sha(process.argv[1]) ||
    binding.loaded.solver !== sha(config.solverModule) ||
    binding.loaded.improver !== sha(config.improverModule))
    throw new Error("CONTROLLED_ACTIVATION_IDENTITY_MISMATCH");
const evidence = (phase: string, entrypoint: string, output: unknown = null) => {
    console.log(JSON.stringify({type: "controlled_activation", phase, entrypoint,
        nonce: binding.nonce, pid: process.pid, mode: config.mode,
        harness_source_hash: binding.harnessSourceHash, loaded: binding.loaded,
        app_build_hash: binding.appBuildHash, binding_hash: binding.bindingHash,
        output: phase === "invoked" ? output : null,
        output_hash: phase === "invoked"
            ? crypto.createHash("sha256").update(JSON.stringify(output)).digest("hex") : null}));
};
const invoke = <T>(entrypoint: string, call: () => T): T => {
    const result = call();
    evidence("invoked", entrypoint, result);
    return result;
};
'''

def build():
    if not (ROOT / 'INPUT-LOCK.json').exists():
        write_once(ROOT / 'INPUT-LOCK.json', {'schema': 'controlled-input-lock-v1',
            'files': {str(p): sha(p) for p in source_paths()}})
    verify_sources()
    PI.mkdir(exist_ok=True)
    for filename in ['package.json', 'package-lock.json']:
        shutil.copyfile(PI_SOURCE / filename, PI / filename)
    if not (PI / 'node_modules').exists():
        (PI / 'node_modules').symlink_to(PI_SOURCE / 'node_modules', target_is_directory=True)
    agent = PI / 'packages/bf-agent'
    (agent / 'src').mkdir(parents=True, exist_ok=True)
    for name in ['package.json', 'tsconfig.json']:
        shutil.copyfile(PI_SOURCE / 'packages/bf-agent' / name, agent / name)
    original = (PI_SOURCE / 'packages/bf-agent/src/main.ts').read_text()
    transformed = original.replace('const activation = {', INSERT + '\nconst activation = {', 1)
    for old, new in [
        ('const solver = await import(pathToFileURL(config.solverModule).href);',
         'const solver = await import(pathToFileURL(config.solverModule).href);\nevidence("post_import", "solver");'),
        ('const improver = await import(pathToFileURL(config.improverModule).href);',
         'const improver = await import(pathToFileURL(config.improverModule).href);\nevidence("post_import", "improver");'),
        (': solver.initialState();', ': invoke("solver.initialState", () => solver.initialState());'),
        ('? solver.solverPrompt(task, state) : improver.improvementPrompt(config.improvementContext);',
         '? invoke("solver.solverPrompt", () => solver.solverPrompt(task, state))\n'
         '    : invoke("improver.improvementPrompt", () => improver.improvementPrompt(config.improvementContext));'),
    ]:
        if transformed.count(old) != 1:
            raise ValueError('PATCH_TARGET_DRIFT:' + old)
        transformed = transformed.replace(old, new, 1)
    (agent / 'src/main.ts').write_text(transformed)
    (ROOT / 'patches/main.ts.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), transformed.splitlines(True),
        fromfile='upstream/packages/bf-agent/src/main.ts', tofile='overlay/packages/bf-agent/src/main.ts')))
    harness = PI / 'packages/bf-harness'
    (harness / 'src').mkdir(parents=True, exist_ok=True)
    for src in (PI_SOURCE / 'packages/bf-harness/src').glob('*.ts'):
        shutil.copyfile(src, harness / 'src' / src.name)
    for name in ['package.json', 'tsconfig.json']:
        shutil.copyfile(PI_SOURCE / 'packages/bf-harness' / name, harness / name)
    # Existing freeze binds the same pinned provider resources.
    if not (PI / 'packages/ai').exists():
        (PI / 'packages/ai').symlink_to(PI_SOURCE / 'packages/ai', target_is_directory=True)
    commands = []
    for package in [agent, harness]:
        command = [str(PI_SOURCE / 'node_modules/.bin/tsgo'), '-p', str(package / 'tsconfig.json')]
        run = subprocess.run(command, text=True, capture_output=True, timeout=60)
        commands.append({'argv': command, 'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr})
        if run.returncode:
            print(run.stdout + run.stderr)
            raise RuntimeError('OVERLAY_BUILD_FAILED')
    receipt = {'schema': 'controlled-overlay-build-v1', 'provider_calls': 0,
        'commands': commands, 'base_main_source': sha(PI_SOURCE / 'packages/bf-agent/src/main.ts'),
        'overlay_main_source': sha(agent / 'src/main.ts'), 'overlay_main_build': sha(agent / 'dist/main.js'),
        'pi_lock_hash': sha(PI_SOURCE / 'package-lock.json'), 'input_verification': verify_sources(),
        'scope': 'actual pinned Pi SDK and compiler, instrumented dry-run entrypoint only'}
    write_once(ROOT / 'reports/BUILD-RECEIPT.json', receipt)
    return receipt

if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
