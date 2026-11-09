/** A real Pi SDK callback with no model-accessible tools or resource discovery. */
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { pathToFileURL } from 'node:url';

const lines = readline.createInterface({input: process.stdin});
const config = await new Promise((resolve, reject) => lines.once('line', line => {
  try { resolve(JSON.parse(line)); } catch (e) { reject(e); }
}));
const outputCap=config.max_output_tokens ?? 4096;
if(!Number.isInteger(outputCap)||outputCap<1||outputCap>32768) throw Error('OUTPUT_GRANT_INVALID');
const emit = value => console.log(JSON.stringify(value));
const {createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager,
       SettingsManager, VERSION} = await import(pathToFileURL(config.sdk_entry).href);
const settings = SettingsManager.inMemory({compaction:{enabled:false},retry:{enabled:false}});
const loader = new DefaultResourceLoader({cwd:config.workspace,
  agentDir:path.join(config.workspace,'.pi'),settingsManager:settings,
  noExtensions:true,noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,
  systemPrompt:config.instruction});
await loader.reload();
const runtime = await ModelRuntime.create({authPath:path.join(config.workspace,'.pi/auth.json'),
  modelsPath:path.join(config.workspace,'.pi/models.json')});
runtime.registerProvider('bf-deepseek', {baseUrl:config.service+'/v1',api:'openai-completions',
  apiKey:config.token,models:[{id:'deepseek-flash',name:'BF pinned DeepSeek Flash',
    reasoning:true,input:['text'],cost:{input:.3,output:1.2,cacheRead:.006,cacheWrite:.3},
    contextWindow:1048576,maxTokens:outputCap,compat:{supportsDeveloperRole:false,
      supportsStore:false,supportsUsageInStreaming:true,maxTokensField:'max_tokens',
      supportsReasoningEffort:true,thinkingFormat:'deepseek',requiresReasoningContentOnAssistantMessages:true}}]});
const model=runtime.getModel('bf-deepseek','deepseek-flash');
if(!model) throw Error('MODEL_UNAVAILABLE');
fs.mkdirSync(config.workspace,{recursive:true});
const manager=SessionManager.create(config.workspace,path.join(config.workspace,'.pi/sessions'));
const {session,modelFallbackMessage}=await createAgentSession({cwd:config.workspace,
  agentDir:path.join(config.workspace,'.pi'),model,modelRuntime:runtime,thinkingLevel:'high',
  resourceLoader:loader,tools:[],noTools:'all',sessionManager:manager,settingsManager:settings});
if(modelFallbackMessage || session.messages.length || session.getActiveToolNames().length)
  throw Error('FRESH_TOOL_FREE_PI_REQUIRED');
emit({type:'pqe_pi_loaded',sdk_version:VERSION,model:model.id,tools:session.getActiveToolNames(),
  history_messages:session.messages.length,reasoning:'high',max_output_tokens:outputCap});
let failed;
session.subscribe(event=>{
  if(event.type==='message_end' && event.message.role==='assistant'){
    emit({type:'assistant_public',content:event.message.content.filter(c=>c.type==='text'||c.type==='toolCall'),
      stopReason:event.message.stopReason,error:event.message.errorMessage});
    if(event.message.stopReason==='error') failed=event.message.errorMessage||'MODEL_ERROR';
  }
});
process.on('SIGTERM',()=>void session.abort());
await session.prompt(JSON.stringify(config.request));
lines.close();
if(failed) throw Error(failed);
emit({type:'callback_complete'});
