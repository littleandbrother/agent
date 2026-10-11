import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

interface Config { workspace:string;service:string;token:string;owner:string;goal:string;instruction:string;toolService:string;toolToken:string;methodId:string; }
const input=readline.createInterface({input:process.stdin});
const config=await new Promise<Config>((resolve,reject)=>input.once("line",line=>{try{resolve(JSON.parse(line) as Config);}catch(e){reject(e);}}));
const emit=(v:Record<string,unknown>)=>console.log(JSON.stringify({...v,time:Date.now()/1000}));
const settings=SettingsManager.inMemory({compaction:{enabled:false},retry:{enabled:false}});
const core=`你是 BF Pi。自行理解合同、检查实际源码、选择验证和修订。只用 bf_method 工具在声明范围内工作；E/V、原始回执、费用与独立采用裁决不可修改。工程修复与方法补丁分别记录；不自称物理验证或 RSI。简短中文公开理由。\n${config.instruction}`;
const loader=new DefaultResourceLoader({cwd:config.workspace,agentDir:path.join(config.workspace,".pi"),settingsManager:settings,
 noExtensions:true,noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,systemPrompt:core,
 extensionFactories:[{name:"bf-method-study-v1",hidden:false,factory:pi=>{
  pi.registerTool({name:"bf_method",label:"BF method study",description:"Read frozen task and public episode; inspect/replace your program.c and run the public compiled-core checks. Improver submits a versioned conditional method candidate. Solver submits its final program for separate independent evaluation. All evaluation and adoption remain external.",executionMode:"sequential",
   parameters:Type.Object({action:Type.Union(["inspect","check","submit"].map(v=>Type.Literal(v))),source:Type.Optional(Type.String()),candidate:Type.Optional(Type.Record(Type.String(),Type.Unknown())),rationale:Type.Optional(Type.String())}),
   async execute(_id,args){const response=await fetch(config.toolService,{method:"POST",headers:{Authorization:`Bearer ${config.toolToken}`,"Content-Type":"application/json"},body:JSON.stringify(args)});
    const value=await response.json() as Record<string,unknown>;if(!response.ok)throw Error(String(value.error));
    emit({type:"method_tool_fact",action:args.action,input:args,result:value});return {content:[{type:"text",text:JSON.stringify(value)}],details:{}};}
  });
 }}]});
await loader.reload();
const runtime=await ModelRuntime.create({authPath:path.join(config.workspace,".pi/auth.json"),modelsPath:path.join(config.workspace,".pi/models.json")});
runtime.registerProvider("bf-deepseek",{baseUrl:`${config.service}/v1`,api:"openai-completions",apiKey:config.token,
 models:[{id:"deepseek-flash",name:"DeepSeek V4.1 Flash",reasoning:true,input:["text"],cost:{input:.3,output:1.2,cacheRead:.006,cacheWrite:.3},contextWindow:1048576,maxTokens:32768,
 compat:{supportsDeveloperRole:false,supportsStore:false,supportsUsageInStreaming:true,maxTokensField:"max_tokens",supportsReasoningEffort:true,thinkingFormat:"deepseek",requiresReasoningContentOnAssistantMessages:true}}]});
const model=runtime.getModel("bf-deepseek","deepseek-flash");if(!model)throw Error("MODEL_ID_UNAVAILABLE");
const pointer=path.join(config.workspace,".pi/method-session-path");fs.mkdirSync(path.dirname(pointer),{recursive:true});
const manager=fs.existsSync(pointer)?SessionManager.open(fs.readFileSync(pointer,"utf8")):SessionManager.create(config.workspace,path.join(config.workspace,".pi/method-sessions"));
fs.writeFileSync(pointer,manager.getSessionFile()!);
const {session,modelFallbackMessage}=await createAgentSession({cwd:config.workspace,agentDir:path.join(config.workspace,".pi"),model,modelRuntime:runtime,thinkingLevel:"high",resourceLoader:loader,tools:["bf_method"],sessionManager:manager,settingsManager:settings});
if(modelFallbackMessage)throw Error("MODEL_FALLBACK_DENIED");
emit({type:"method_loaded",method_id:config.methodId,owner:config.owner,core,model:model.id,thinking:"high",tools:session.getActiveToolNames(),resume_messages:session.messages.length});
let error:string|undefined;
session.subscribe(event=>{
 if(event.type==="message_end"&&event.message.role==="assistant"){
  emit({type:"assistant_public",content:event.message.content.filter(c=>c.type==="text"||c.type==="toolCall")});
  if(event.message.stopReason==="error")error=event.message.errorMessage??"MODEL_RESPONSE_ERROR";
 }
});
process.on("SIGTERM",()=>void session.abort());
await session.prompt(config.goal);if(error)throw Error(error);
emit({type:"method_run_complete",method_id:config.methodId});input.close();
