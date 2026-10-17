import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [runtimeRoot, owner] = process.argv.slice(2);
const profile = JSON.parse(fs.readFileSync(path.join(runtimeRoot, 'profile.json'), 'utf8'));
const agentDir = path.join(profile.home, 'pi-config');
if (process.env.PI_CODING_AGENT_DIR !== agentDir) throw Error('V2_PI_STATE_SCOPE');
if (profile.protected_owners.includes(owner)) throw Error('V2_ORIGINAL_OWNER');
globalThis.fetch = () => {throw Error('V2_SDK_UNEXPECTED_NETWORK');};
const sdkPackage = fs.realpathSync(path.join(profile.pi_root, 'node_modules/@earendil-works/pi-coding-agent'));
const sdkMetadata = JSON.parse(fs.readFileSync(path.join(sdkPackage, 'package.json'), 'utf8'));
const sdkFile = path.resolve(sdkPackage, sdkMetadata.exports['.'].import);
if (!sdkFile.startsWith(profile.pi_root + path.sep)) throw Error('V2_SDK_SOURCE_SCOPE');
const {createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager} = await import(pathToFileURL(sdkFile));
const cwd = path.join(profile.home, 'participants', owner);
fs.mkdirSync(path.join(cwd, '.pi'), {recursive: true});
const settings = SettingsManager.create(cwd, agentDir);
const loader = new DefaultResourceLoader({cwd, agentDir, settingsManager: settings,
  noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true,
  noContextFiles: true, systemPrompt: 'Environment validation; do not perform inference.'});
await loader.reload();
const modelRuntime = await ModelRuntime.create({authPath: path.join(cwd, '.pi/auth.json'), modelsPath: path.join(cwd, '.pi/models.json')});
modelRuntime.registerProvider('bf-deepseek', {baseUrl: `http://127.0.0.1:${profile.port}/v1`, api: 'openai-completions', apiKey: 'development-disabled',
  models: [{id: 'deepseek-flash', name: 'DeepSeek Flash environment fixture', reasoning: true, input: ['text'],
    cost: {input: .3, output: 1.2, cacheRead: .006, cacheWrite: .3}, contextWindow: 1048576, maxTokens: 8000}]});
const model = modelRuntime.getModel('bf-deepseek', 'deepseek-flash');
if (!model) throw Error('V2_SDK_MODEL_CONFIGURATION');
const manager = SessionManager.create(cwd, path.join(cwd, '.pi/design-sessions'));
manager.appendMessage({role: 'user', content: 'A/B environment session recovery test; no inference.', timestamp: Date.now()});
manager.appendMessage({role: 'assistant', content: [{type: 'text', text: 'Synthetic SDK persistence fixture; not a model response.'}],
  api: 'openai-completions', provider: 'environment-fixture', model: 'synthetic', stopReason: 'stop', timestamp: Date.now(),
  usage: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
    cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0}}});
const options = {cwd, agentDir, model, modelRuntime, thinkingLevel: 'high', resourceLoader: loader, tools: [], settingsManager: settings};
const first = await createAgentSession({...options, sessionManager: manager});
const sessionFile = manager.getSessionFile();
if (!sessionFile || !sessionFile.startsWith(cwd + path.sep)) throw Error('V2_SDK_SESSION_SCOPE');
first.session.dispose();
const reopened = SessionManager.open(sessionFile);
const restored = await createAgentSession({...options, sessionManager: reopened});
if (restored.modelFallbackMessage || restored.session.getActiveToolNames().length || reopened.buildSessionContext().messages.length !== 2)
  throw Error('V2_SDK_RECOVERY_MISMATCH');
restored.session.dispose();
console.log(JSON.stringify({status: 'PASS', sdk_file: sdkFile, node: process.version, owner, agent_dir: agentDir,
  session_file: sessionFile, restored_messages: 2, message_origin: 'synthetic persistence fixtures',
  model_id: model.id, thinking: 'high', model_requests: 0, network_requests: 0}));
