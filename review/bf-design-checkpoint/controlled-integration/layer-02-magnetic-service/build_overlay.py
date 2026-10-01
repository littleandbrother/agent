"""Narrow registry hooks in the existing service plus explicit Pi execution packet."""
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from paths import ROOT, FIRST, REPO, PI, PI_SOURCE, sha, read, write_once, verify_inputs

def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('PATCH_TARGET_DRIFT:' + old[:120])
    return source.replace(old, new, 1)

def diff(name, original, new):
    (ROOT / 'patches' / name).write_text(''.join(difflib.unified_diff(original.splitlines(True), new.splitlines(True), fromfile='pinned-upstream', tofile='isolated-protocol-overlay')))

def build():
    verify_inputs()
    server_path = REPO / 'packages/python/bfworld/src/bfworld/agentlab/server.py'
    original = server_path.read_text()
    server = replace(original, "REPO = Path(__file__).resolve().parents[6]", "from .runtime_config import REPO")
    server = replace(server, "                path = urlparse(self.path).path\n                static = {",
        "                path = urlparse(self.path).path\n                if getattr(workbench,'controlled',None) and path!='/api/budget' and not path.startswith('/api/tasks/'):\n                    return self.reply(403,{'error':'CONTROLLED_ROUTE_NOT_ALLOWED'})\n                static = {")
    server = replace(server, "                if path=='/api/budget':\n", "                if path=='/api/budget' and getattr(workbench,'controlled',None):\n                    return self.reply(200,workbench.controlled.budget(owner))\n                if path=='/api/budget':\n")
    server = replace(server, "                if path.startswith('/api/tasks/'):\n", "                if path.startswith('/api/tasks/') and getattr(workbench,'controlled',None):\n                    return self.reply(200,workbench.controlled.public_task(owner,path.removeprefix('/api/tasks/')))\n                if path.startswith('/api/tasks/'):\n")
    server = replace(server, "                body = json.loads(self.rfile.read(length))\n", """                body = json.loads(self.rfile.read(length))
                if getattr(workbench,'controlled',None):
                    if path=='/api/snapshots':return self.reply(201,workbench.controlled.snapshot(owner,body))
                    if path=='/api/jobs':return self.reply(200,workbench.controlled.job(owner,body))
                    if path in ('/api/solve','/v1/chat/completions','/api/submit'):
                        return self.reply(403,workbench.controlled.denied(owner,path,body))
                    return self.reply(403,{'error':'CONTROLLED_ROUTE_NOT_ALLOWED'})
""")
    server = replace(server, "                actor = self.principal(); owner = actor['owner']\n                if path in ('/api/reference-case'", "                actor = self.principal(); owner = actor['owner']\n                if getattr(workbench,'controlled',None) and path!='/api/budget' and not path.startswith('/api/tasks/'):\n                    return self.reply(403,{'error':'CONTROLLED_ROUTE_NOT_ALLOWED'})\n                if path in ('/api/reference-case'")
    (ROOT / 'src/server_overlay.py').write_text(server)
    diff('server.py.diff', original, server)
    PI.mkdir(exist_ok=True)
    for name in ['package.json', 'package-lock.json']:
        shutil.copyfile(PI_SOURCE / name, PI / name)
    if not (PI / 'node_modules').exists():
        (PI / 'node_modules').symlink_to(PI_SOURCE / 'node_modules', target_is_directory=True)
    (PI / 'packages').mkdir(exist_ok=True)
    if not (PI / 'packages/ai').exists():
        (PI / 'packages/ai').symlink_to(PI_SOURCE / 'packages/ai', target_is_directory=True)
    for package in ['bf-agent', 'bf-harness']:
        dest = PI / 'packages' / package
        (dest / 'src').mkdir(parents=True, exist_ok=True)
        for name in ['package.json', 'tsconfig.json']:
            shutil.copyfile(PI_SOURCE / 'packages' / package / name, dest / name)
    original_main = (FIRST / 'pi-overlay/packages/bf-agent/src/main.ts').read_text()
    main = replace(original_main, 'const cwd = path.resolve(config.workspace);', '''const cwd = path.resolve(config.workspace);
const packet = config.executionPacket;
if (!packet || packet.scope !== "trusted-offline-protocol-probe" || packet.execution_authorized !== false || config.dryRun !== true)
    throw new Error("EXPLICIT_OFFLINE_EXECUTION_PACKET_REQUIRED");
const ordered = (value: unknown): unknown => Array.isArray(value) ? value.map(ordered)
    : value && typeof value === "object"
        ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, ordered((value as Record<string, unknown>)[key])]))
        : value;
const packetBody = {...packet};
delete packetBody.packet_id;
if (crypto.createHash("sha256").update(JSON.stringify(ordered(packetBody))).digest("hex") !== packet.packet_id)
    throw new Error("EXECUTION_PACKET_CONTENT_HASH_MISMATCH");
const profile = packet.runtime_profile;
if (!profile || profile.provenance !== "fictional-offline-SDK-initialization-only" ||
    profile.budget.model_calls !== 0 || profile.budget.solver_calls !== 0 ||
    profile.budget.money !== 0 || packet.task_id !== config.taskId)
    throw new Error("OFFLINE_PACKET_CANNOT_AUTHORIZE_EXECUTION");
''')
    main = replace(main, 'model: "deepseek-flash",', 'model: profile.model.model_id,')
    main = replace(main, 'solver.initialState());', 'solver.initialState(profile.budget));')
    main = replace(main, 'body: JSON.stringify(body)', 'body: JSON.stringify({ ...(body as Record<string, unknown>), execution_packet_id: packet.packet_id })')
    main = replace(main, '["design.json", "policy.py"].map', '["candidate.json"].map')
    main = replace(main, 'Upload immutable current design.json and policy.py, then submit one async experiment. Persist and reuse operation_id after interruption.',
        'Upload immutable candidate.json under the registered canonical magnetic schema, then request preflight. Missing native identity or qualification returns BLOCKED, never a completed experiment. Reuse operation_id after interruption.')
    # Keep the existing bf_experiment body and call it from a labeled trusted
    # fixture driver. No model, agent decision or selected solution is fabricated.
    marker = '\t\tasync execute(_id, { operation_id }) {'
    start = main.index(marker)
    end = main.index('\n\t\t},\n\t}),', start)
    body = main[start + len(marker):end]
    main = main[:start] + '\t\tasync execute(_id, { operation_id }) { return experiment(operation_id);' + main[end:]
    main = replace(main, 'const tools = [', 'const experiment = async (operation_id: string) => {' + body + '\n};\nconst tools = [')
    main = replace(main, 'const tools = [\n\tdefineTool({\n\t\tname: "bf_experiment",', 'const experimentTool = defineTool({\n\t\tname: "bf_experiment",')
    main = replace(main, '\n\t}),\n\tdefineTool({\n\t\tname: "bf_job",', '\n\t});\nconst tools = [experimentTool,\n\tdefineTool({\n\t\tname: "bf_job",')
    main = replace(main, '\tstate.remainingExperiments = state.budget.remaining_experiments;\n\tsave();\n}',
        '\tif (state.budget.execution_packet_id !== packet.packet_id || JSON.stringify(ordered(state.budget.budget)) !== JSON.stringify(ordered(profile.budget))) throw new Error("SERVICE_BUDGET_PACKET_MISMATCH");\n\tstate.remainingExperiments = state.budget.remaining_experiments;\n\tsave();\n}')
    start = main.index('runtime.registerProvider("bf-deepseek", {')
    end = main.index('\nif (!model) throw new Error("EXPLICIT_MODEL_UNAVAILABLE");', start)
    main = main[:start] + '''console.log(JSON.stringify({type:"controlled_runtime_configuration", packet_id:packet.packet_id,
    model:profile.model, budget:profile.budget, autonomous_participant:false}));
runtime.registerProvider(profile.model.provider, {
    baseUrl: config.service + "/v1", api: "openai-completions", apiKey: config.token,
    models: [{ id: profile.model.model_id, name: profile.model.revision,
        reasoning: profile.model.reasoning, input: ["text"], cost: profile.model.cost,
        contextWindow: profile.model.context_tokens, maxTokens: profile.model.max_output_tokens,
        compat: {supportsDeveloperRole:false,supportsStore:false,supportsUsageInStreaming:true,maxTokensField:"max_tokens"} }],
});
const model = runtime.getModel(profile.model.provider, profile.model.model_id);''' + main[end:]
    main = replace(main, 'const task = config.mode === "solve" ? JSON.parse(fs.readFileSync(path.join(cwd, "task.json"), "utf8")) : null;', '''const task = config.mode === "solve" ? await api("/api/tasks/" + encodeURIComponent(config.taskId)) : null;
if (task && (task.execution_packet_id !== packet.packet_id || task.binding.task_contract_hash !== packet.task_contract_hash))
    throw new Error("SERVICE_TASK_PACKET_MISMATCH");
if (task && JSON.stringify(ordered(task.execution_contract.runtime_profile)) !== JSON.stringify(ordered(profile)))
    throw new Error("SERVICE_RUNTIME_PROFILE_MISMATCH");
if (task) {
    fs.writeFileSync(path.join(cwd,"task.json"), JSON.stringify(task,null,2));
    console.log(JSON.stringify({type:"controlled_task_bound", task_id:task.task_id, binding:task.binding,
        packet_id:packet.packet_id, source:"actual-registry-service-read"}));
}''')
    main = replace(main, '\tif (!config.dryRun)\n\t\tawait session.prompt(', '''\tif (config.trustedControllerProbe === true) {
        if (config.mode !== "solve") throw new Error("TRUSTED_PROBE_REQUIRES_SOLVE_MODE");
        const args = {operation_id:"trusted-controller-probe-1"};
        const registeredTool = session.getToolDefinition("bf_experiment");
        if (!registeredTool) throw new Error("REGISTERED_EXPERIMENT_TOOL_MISSING");
        const result = await registeredTool.execute("trusted-controller-probe", args, undefined, undefined, session.extensionRunner.createContext());
        console.log(JSON.stringify({type:"trusted_controller_probe", autonomous_participant:false,
            tool_name:registeredTool.name, arguments:args, packet_id:packet.packet_id, result}));
    }
\tif (!config.dryRun)\n\t\tawait session.prompt(''')
    (PI / 'packages/bf-agent/src/main.ts').write_text(main)
    diff('main.ts.diff', original_main, main)
    for src in (PI_SOURCE / 'packages/bf-harness/src').glob('*.ts'):
        value = src.read_text()
        if src.name == 'solver.ts':
            value = replace(value, 'initialState(): SolverState', 'initialState(budget: {solver_calls: number}): SolverState')
            value = replace(value, 'remainingExperiments: 6,', 'remainingExperiments: budget.solver_calls,')
            value = replace(value, 'Read task.json, design.json and policy.py. Edit actual design parameters and/or the Python plan(obs).',
                'Read task.json and candidate.json. Use the registered magnetic candidate contract. Unsupported architecture or model regions are insufficient evidence, never silently restricted or scored as design failure.')
            value = replace(value, 'The experiment limit is 6. Finish within 24 model requests and 10 minutes. No internet access.',
                'Use only the explicit execution packet limits. No internet access. A blocked native request is not a completed experiment.\nExecution contract: ${JSON.stringify(task.execution_contract)}')
        elif src.name == 'improver.ts':
            value = replace(value, 'You have 24 model requests and 10 minutes.', 'Use only the explicit execution packet limits: ${JSON.stringify(context.execution_contract)}.')
        (PI / 'packages/bf-harness/src' / src.name).write_text(value)
        if value != src.read_text():
            diff(src.name + '.diff', src.read_text(), value)
    original_launcher = (REPO / 'packages/python/bfworld/src/bfworld/agentlab/launcher.py').read_text()
    launcher = replace(original_launcher, 'from .runtime_config import PI, HOME_ROOT, NODE as NODE_PATH',
        'from .runtime_config import PI, HOME_ROOT, NODE as NODE_PATH, REPO')
    if launcher.count('base=Path(__file__).resolve().parent') != 2:
        raise ValueError('WORLD_BINDING_SOURCE_DRIFT')
    launcher = launcher.replace('base=Path(__file__).resolve().parent', "base=REPO/'packages/python/bfworld/src/bfworld/agentlab'")
    launcher = replace(launcher,
        "'session_caps':{'experiments':6,'model_requests':128 if app_entry=='chat-product.js' else 24,'wall_seconds':INTERACTIVE_WALL_SECONDS if app_entry in ('chat.js','chat-v2.js','chat-product.js') else 600},",
        "'session_caps':None,'session_cap_authority':'explicit-execution-packet',")
    launcher = replace(launcher, "'model':'deepseek-flash'", "'model':None,'model_authority':'explicit-execution-packet'")
    launcher = replace(launcher, "'world':'coupled-programmed-reference-v3'",
        "'world':None,'world_authority':'explicit-execution-packet','world_binding_scope':'legacy-controller-source-dependencies-only','legacy_source_world':'coupled-programmed-reference-v3'")
    # This staging module exposes the unchanged freeze implementation only to our
    # runner. Its legacy launch function is disabled before any grants or keys.
    launcher = replace(launcher, '    home_root=Path(home_root or HOME_ROOT)\n',
        "    raise RuntimeError('LEGACY_LAUNCH_DISABLED_USE_CONTROLLED_SERVICE_GATE')\n    home_root=Path(home_root or HOME_ROOT)\n")
    (ROOT / 'src/launcher_overlay.py').write_text(launcher)
    diff('launcher.py.diff', original_launcher, launcher)
    builds = []
    for name in ['bf-agent', 'bf-harness']:
        command = [str(PI_SOURCE / 'node_modules/.bin/tsgo'), '-p', str(PI / 'packages' / name / 'tsconfig.json')]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        builds.append({'argv': command, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            print(result.stdout + result.stderr)
            raise ValueError('OVERLAY_BUILD_FAILED')
    receipt = {'schema': 'magnetic-service-overlay-build-v1', 'builds': builds,
        'main_source': sha(PI / 'packages/bf-agent/src/main.ts'), 'main_build': sha(PI / 'packages/bf-agent/dist/main.js'),
        'server_source': sha(ROOT / 'src/server_overlay.py'), 'launcher_source': sha(ROOT / 'src/launcher_overlay.py'),
        'inputs': verify_inputs(), 'provider_calls': 0}
    write_once(ROOT / 'reports/BUILD-RECEIPT.json', receipt)
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    build()
