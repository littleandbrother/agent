/* Lab reads immutable engineering records. Display helpers never award a verdict. */
export const gateNames = {source_domain:'源模型与工况',schematic_bom_pins:'原理图、BOM 与引脚',pcb_connectivity_drc:'PCB 连通与 DRC',geometry_fit:'机械与装配',board_firmware_interfaces:'板卡与固件接口',firmware_event_logic:'固件事件行为',power_load_chain:'供能与任务执行',delivery_version:'同版本交付'};
export function coreRecords(system) {
  return Object.entries(gateNames).map(([id,label])=>({...system.validations?.[id],id,label,target:system.id,status:system.validations?.[id]?.status||'NOT_CHECKED',kind:'core'}));
}
export function latestInterface(view,system) {
  return view.validations.filter(v=>v.target===system.id&&v.kind==='power-firmware-interface').at(-1);
}
export function contractVerdict(view,system,contract) {
  if(!Object.values(system.contracts||{}).includes(contract.id))return 'NOT_CHECKED';
  return latestInterface(view,system)?.status||'NOT_CHECKED';
}
export function changedFiles(system,parent) {
  if(!parent)return [];
  return [...new Set([...Object.keys(parent.files),...Object.keys(system.files)])].filter(p=>parent.files[p]?.sha256!==system.files[p]?.sha256).map(path=>({path,before:parent.files[path],after:system.files[path]}));
}
export function operationOutcome(op) {
  const r=op.result||{};
  return {execution:op.status,engineering:r.result?.status||r.current_qualification?.status||r.digital_status||r.status||null};
}
export function scopeRequests(requests,{owner,start,end}={}) {
  return requests.filter(r=>(!owner||r.owner===owner)&&(start==null||r.created>=start)&&(end==null||r.created<end));
}
export function usageTotals(requests) {
  return {requests:requests.length,ledger:requests.reduce((n,r)=>n+Number((r.status==='SETTLED'?r.charged:r.reserved)??0),0),estimate:requests.reduce((n,r)=>n+(r.cost_estimate?.cache_aware_estimate_usd??0),0),estimated:requests.filter(r=>r.cost_estimate?.cache_aware_estimate_usd!=null).length,unknown:requests.filter(r=>r.status==='UNKNOWN').length,tokens:requests.reduce((n,r)=>n+(r.usage?.total_tokens??0),0)};
}
export function publicSearchText(record) {
  return [record.id,record.label,record.name,record.title,record.path,record.description,record.rationale,record.question,record.conclusion,record.scope].filter(v=>typeof v==='string').join(' ').toLowerCase();
}
export function sourceOperation(view,key) {
  const matches=view.operations.filter(o=>o.result?.id===key||o.result?.system_commit===key);
  return matches.find(o=>o.request?.action==='repository_integrate')||matches.find(o=>o.result?.id===key)||matches.at(-1);
}
export function designDecision(view,key) {
  const record=view.decisions.filter(d=>d.to_design===key||d.snapshot===key||d.system_commit===key).at(-1);
  if(!record)return null;
  try{return {...record,...JSON.parse(record.rationale)};}catch{return record;}
}
export function roundScope(view,system) {
  const tasks=[...view.professional_task_history,...view.professional_tasks];
  const starts=tasks.filter(t=>t.base_system===system.parent&&t.created).map(t=>t.created);
  const parent=view.systems.find(s=>s.id===system.parent)||system;
  const start=starts.length?Math.min(...starts):sourceOperation(view,parent.id)?.created||0;
  const next=tasks.filter(t=>t.base_system===system.id&&t.created>start).map(t=>t.created);
  return {start,end:next.length?Math.min(...next):null};
}
export function jobArtifactSystem(view,preferred,job,path,sha256) {
  const matches=s=>{const ref=s?.jobs?.[job]?.artifacts?.[path];return ref&&(!sha256||ref.sha256===sha256);};
  return matches(preferred)?preferred:[...view.systems].reverse().find(matches);
}

if(typeof document!=='undefined') {
window.history.scrollRestoration='manual';
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short=s=>s?String(s).slice(0,11):'—';
const stamp=n=>n?new Date(n*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'冻结记录';
const readable=s=>String(s||'').replace(/(?:SC|DC|IC|RV|IR|PT|EX|DA|REL|pi-chat|eng)-[a-f0-9]{10,}/g,v=>short(v));
const brief=(s,n=96)=>{s=readable(s).replace(/\s+/g,' ').trim();return s.length>n?s.slice(0,n)+'…':s;};
const labels={PASS:'通过',FAIL:'未通过',UNEVALUABLE:'缺少验证条件',NOT_CHECKED:'未检查',RECHECK_REQUIRED:'需复查',QUEUED:'未启动',RUNNING:'执行中',SUBMITTED:'已提交',BLOCKED:'受阻',COMPLETED:'已结束',REVIEW_REQUIRED:'等待复查',REVIEW_PACKAGE:'审查交付',REPAIR_REQUIRED:'待修订',RETAIN_FOR_REVIEW:'保留审查',REVISE:'继续修订',REJECT:'拒绝候选',ADOPT_PASSED:'采用通过版',NOT_TESTED:'未进行',IDLE:'空闲',FAILED:'执行失败',SUCCEEDED:'调用完成',SETTLED:'已登记',UNKNOWN:'待核对',AVAILABLE:'可用',ACTIVE:'已激活',LOADED:'配置已加载',RECORDED:'已记录',PLANNED:'待运行',REVIEW_DELIVERED:'审查包已交付',OPEN:'待解决'};
const badge=s=>`<span class="badge ${esc(String(s).toLowerCase())}">${esc(labels[s]||s||'未检查')}</span>`;
const id=s=>`<span class="id" title="${esc(s)}">${esc(short(s))}</span>`;
const empty=s=>`<p class="empty">${esc(s)}</p>`;
const json=v=>`<pre class="source-box">${esc(JSON.stringify(v,null,2))}</pre>`;
const domains={mechanical:['机械与采能','结构、尺寸与源输入'],power:['电源与电路','转换、储能与负载'],firmware:['感知与固件','采样、无线与接收'],assembly:['装配与封装','板卡安装与几何接口']};
const headings={system:['系统设计','当前设计、实际变更与工程结论'],runs:['运行记录','按设计轮次查看任务、执行结果与公开决定'],validation:['验证','当前八项检查与接口检查，历史回执单独查看'],environment:['环境','固定软件、实际执行、权限和接口'],harness:['方法与技能','按 Agent 查看加载配置与技能使用'],experiments:['实验与改进','协议、比较结果与方法采用']};
const actionNames={commit:'提交专业修订',contract:'修订接口契约',integrate:'形成系统候选',validate:'运行工程检查',review:'独立工程审查',execute:'构建或求解',write:'修改工程文件',delegate:'分配专业任务',assign:'分配专业任务',import:'导入冻结工程',reopen:'恢复专业任务',rebase:'切换任务基准',finish:'提交阶段结论',decide:'作出设计决定',release:'生成同版交付',close:'结束本轮',extract:'提取工程事实',read:'读取工程',state:'读取任务状态',summary:'查看状态摘要',task:'读取任务要求'};
const icons={brand:'M2 12h4l2-7 4 14 3-9 2 2h5',menu:'M4 6h16 M4 12h16 M4 18h16',search:'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',refresh:'M20 7V3m0 4h-4 M4 17v4m0-4h4 M4 9a8 8 0 0 1 13-6l3 4 M20 15a8 8 0 0 1-13 6l-3-4',close:'m6 6 12 12 M6 18 18 6',system:'M6 5v14 M18 5v14 M6 9h12 M6 15h12 M3 3h6v4H3z M15 3h6v4h-6z M3 17h6v4H3z M15 17h6v4h-6z',runs:'M8 5v14l11-7z M3 5v14',validation:'m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6z m-4 9 3 3 5-6',environment:'m12 2 9 5v10l-9 5-9-5V7z M3 7l9 5 9-5 M12 12v10',harness:'M14 6a5 5 0 0 0-7 7L3 17v4h4l4-4a5 5 0 0 0 7-7l-4 4-4-4z',experiments:'M9 3h6 M10 3v7l-6 9c-.6 1 .1 2 1.4 2h13.2c1.3 0 2-1 1.4-2l-6-9V3 M7 16h10',power:'m13 2-9 12h7l-1 8 10-12h-7z',firmware:'M6 6h12v12H6z M9 9h6v6H9z M9 2v4 M15 2v4 M9 18v4 M15 18v4 M2 9h4 M2 15h4 M18 9h4 M18 15h4',mechanical:'m12 3 8 4v10l-8 4-8-4V7z M4 7l8 4 8-4 M12 11v10',assembly:'m12 3 9 5v9l-9 5-9-5V8z M3 8l9 5 9-5 M12 13v9',contract:'M10 7H7a5 5 0 0 0 0 10h3 M14 7h3a5 5 0 0 1 0 10h-3 M8 12h8',release:'M5 5h14v16H5z M8 2h8v6H8z M8 12h8 M8 16h5',arrow:'M5 12h14 m-5-5 5 5-5 5'};
const icon=k=>`<svg class="vector-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${icons[k]||icons.system}"/></svg>`;
const symbol=k=>`<span class="domain-symbol ${k}">${icon(k)}</span>`;
const item=(kind,key)=>`data-kind="${esc(kind)}" data-key="${esc(key)}"`;
const jump=(to,key,text)=>`<button data-jump="${to}" data-object="${esc(key||'')}">${esc(text)}</button>`;
const objectButton=(kind,key,text,extra='')=>`<button class="text-link" ${item(kind,key)} ${extra}>${esc(text)}</button>`;
const card=(title,subtitle,body,action='')=>`<section class="card"><header><div><h2>${esc(title)}</h2>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div>${action}</header>${body}</section>`;
const fact=(title,value)=>`<div><dt>${esc(title)}</dt><dd>${esc(value??'未记录')}</dd></div>`;
let data,project,systemId,page='system',selection=null,detailMode='details',query='',busy=false;
let historyFilter='system',historyAll=false,validationFilter='all',usageScope='round',usageOwner='',selectedMethodOwner='',related=null,traceCursor={},viewerState=null;
const shell=$('.shell'),viewStates=new Map(),methodFacts=new Map();
document.querySelectorAll('[data-icon]').forEach(n=>n.innerHTML=icon(n.dataset.icon));
const current=()=>data.systems.find(s=>s.id===systemId)||data.systems.at(-1);
const req=async url=>{const r=await fetch(url,{cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(d.error||r.statusText);return d;};
const baseQuery=()=>({project:project.id,owner:project.owner,system:current().id});
const fileURL=(path,extras={})=>'/api/design-repository/file?'+new URLSearchParams({...baseQuery(),path,...extras});
const archiveURL=r=>'/api/design-repository/archive?'+new URLSearchParams({project:project.id,owner:project.owner,release:r.id});
const sourcePreview=name=>data.previews.find(p=>p.name===name&&p.system_commit===current().id);
const previewURL=p=>fileURL(p.name,{preview:1});
const parentOf=s=>data.systems.find(p=>p.id===s.parent);
const latestRelease=s=>data.releases.filter(r=>r.target===s.id).at(-1);
const action=op=>op.request?.action?.replace('repository_','')||op.operation;
const actionLabel=op=>action(op)==='validate'?(op.result?.kind==='system-engineering'||op.request?.scope==='system'?'独立工程审查':'检查接口'):action(op)==='execute'?(op.result?.kind==='spice'||op.request?.path?.includes('chain')?'电源瞬态求解':'目标固件构建'):actionNames[action(op)]||action(op);
const opFor=key=>sourceOperation(data,key);
const timeOf=v=>v.created||opFor(v.id)?.created||data.events.find(e=>e.data?.system_commit===v.id)?.created||0;
const taskFor=owner=>data.professional_tasks.find(t=>t.owner===owner);
const roleName=owner=>domains[taskFor(owner)?.role]?.[0]||(owner===project.owner?'BF Lead':'专业会话');
const methodSkills=()=>[...new Map([...data.skills.skills,...data.methods.flatMap(m=>m.resource_manifest?.skills||[])].map(s=>[s.id,s])).values()];
const systemTitle=s=>{
 if(s.id===project.adopted)return '稳定参考';if(s.origin_design_id&&!s.parent)return '导入的 P01 工程';
 const paths=changedFiles(s,parentOf(s)).map(f=>f.path),fw=paths.some(p=>p.startsWith('project-fw')),power=paths.some(p=>p.startsWith('project-chain')||p.startsWith('project-spice'));
 return `${fw&&power?'固件与供能联合修订':fw?'固件修订':power?'供能修订':paths.length?'接口与集成修订':'系统集成'} · v${Math.max(1,data.systems.indexOf(s))}`;
};
const systemPurpose=s=>{
 const changes=changedFiles(s,parentOf(s)),fw=changes.filter(c=>c.path.startsWith('project-fw')).length,power=changes.filter(c=>c.path.startsWith('project-chain')||c.path.startsWith('project-spice')).length;
 return fw||power?[fw?`更新 ${fw} 件固件源文件`:'',power?`更新 ${power} 件供能与负载文件`:''].filter(Boolean).join('，')+'；查看下方检查结果与 BF 决定。':changes.length?`更新 ${changes.length} 件接口或集成文件；工程输入与证据绑定本版。`:'P01 无线传感节点 · 冻结工程与已有验证';
};
const domainTitle=d=>`${domains[d.domain]?.[0]||d.domain} · 修订 ${d.revision??data.domain_commits.filter(c=>c.domain===d.domain).indexOf(d)+1}`;
const selectionTitle=(kind,v)=>({system:()=>systemTitle(v),domain:()=>domainTitle(v),contract:()=>`电源与固件活动契约 · 第 ${v.revision} 版`,validation:()=>v.kind==='power-firmware-interface'?'电源与固件接口检查':'独立工程审查',gate:()=>v.label,run:()=>roleName(v.owner),decision:()=>`BF 设计决定 · ${labels[v.decision]||'公开理由'}`,operation:()=>actionLabel(v),method:()=>`${roleName(v.owner)} 执行配置`,execution:()=>v.kind==='spice'?'电源瞬态求解':'固件目标构建',release:()=>`同版工程审查包`,skill:()=>skillTitle(v),tool:()=>toolNames[v.id]||v.id,interface:()=>actionNames[v.id.replace('repository_','')]||v.id,assets:()=>domains[v.id]?.[0]||'工程文件',experiment:()=>v.title,request:()=>`${roleName(v.owner)} 模型请求`}[kind]?.()||v.label||v.title||'记录');
function notify(text){$('#notice').textContent=text;$('#notice').classList.add('visible');setTimeout(()=>$('#notice').classList.remove('visible'),3500);}
const translations={
 'netlist load differs from the declared load witness':'实际网表负载与声明的时序不一致','load charge differs from timeline':'负载积分电荷与时序表不一致','supply falls below the declared operating voltage':'供电低于声明的工作电压','manual admission produces a negative MCU rail':'人工接通模型出现负电压',
 'native PCB peripheral initialization and full pin/interface audit':'待核对原生 PCB、外设初始化及完整引脚接口','native component 3D heights':'缺少原生器件三维高度','PCB-to-CAD placement transform':'缺少 PCB 与 CAD 的装配坐标对应','mounting-hole correspondence':'待核对安装孔对应关系','supplier, footprint and vendor pin full audit':'待核对供应商、封装和厂商引脚','T1 winding parameter identification':'待确认 T1 绕组参数',
 'CS-TENG capacitance and its stroke dependence':'待确定 TENG 电容与行程关系','rectifier diode part number / Vf / recovery':'待确定整流二极管与动态参数','SECE switch part number and drive':'待确定 SECE 开关与驱动','storage capacitor ESR and leakage':'待补储能电容 ESR 和漏电','regulator part number, dropout and efficiency curve':'待补稳压器型号、压差与效率曲线','AD7156 conversion current and timing (declared only)':'AD7156 电流与转换时序待校准','nRF52832 radio TX/RX current profile (declared only)':'nRF52832 无线电流波形待校准','fast SECE switching instant and duty':'待补 SECE 开关时刻与占空比','switch on-resistance and gate/drive charge':'待补开关导通电阻与驱动电荷','transformer/inductor values and saturation':'待补变压器、电感与饱和参数','diode vs synchronous rectification in the extraction stage':'待确认提取级整流方式','series resistance of the real extraction path':'待补提取路径串联电阻',
 'source timing and declared load/power interface':'实际源码时序与声明的电源、负载接口','exact validated firmware input reuse':'精确复用已验证的固件输入','original independent native review on identical saved EDA/CAD inputs':'复用输入一致的原生 EDA / CAD 独立检查','original source calibration and SECE applicability':'源模型校准与 SECE 适用条件','native board and firmware interfaces':'原生板卡与固件接口','current source and selected worker inputs; immutable review manifest':'当前源码、选定作业输入及同版清单','fixed nominal/manual-admission load and actual native transient; source calibration pending':'名义工况、人工接通与实际瞬态输出；源参数待校准'};
Object.assign(translations,{'power rail and initial state':'供电电压与初始储能','actual radio and sampling timing':'实际无线与采样时序','source-bound load timing':'与源码对应的负载时序','manual admission boundary':'人工接通条件','current amplitude provenance':'电流幅值依据'});
const tr=s=>translations[s]||readable(s);
const publicNote=(text,label='完整公开说明')=>text?`<details class="public-note"><summary>${esc(label)}</summary><p class="public-text">${esc(readable(text))}</p></details>`:'';
function gateInfo(g) {
 const f=g.findings||{},n=f.findings&&!Array.isArray(f.findings)?f.findings:f;
 const notes=[...(Array.isArray(f.findings)?f.findings:[]),...(n.pending||f.pending||[])].map(tr);
 const metrics=[];
 if(f.minimum_supply_v!=null)metrics.push(['最低供电',Number(f.minimum_supply_v).toPrecision(6)+' V']);
 if(f.storage_v)metrics.push(['储能电压',f.storage_v.map(v=>Number(v).toPrecision(4)).join(' → ')+' V']);
 if(f.load_binding)metrics.push(['负载波形点数',`${f.load_binding.actual_points} 实际 / ${f.load_binding.expected_points} 声明重建`]);
 if(f.minimum_mcu_v!=null)metrics.push(['模型 MCU 最低电压',Number(f.minimum_mcu_v).toPrecision(5)+' V']);
 if(n.fresh_drc_counts)for(const [k,v]of Object.entries(n.fresh_drc_counts))metrics.push([k==='Clearance Error'?'间距错误':k==='Connection Error'?'连接错误':k,String(v)]);
 if(n.outline?.pcb_mm)metrics.push(['PCB / CAD 外形',n.outline.pcb_mm.join(' × ')+' / '+n.outline.cad_mm.join(' × ')+' mm']);
 if(n.part_pin_net_correspondence)metrics.push(['器件 / 引脚对应',`${n.part_pin_net_correspondence.components} 件 / ${n.part_pin_net_correspondence.pins} 脚`]);
 if(f.file_count!=null)metrics.push(['同版文件',f.file_count+' 件']);
 if(f.exact_reuse_validation)notes.push('复用相同源码的事件行为检查');
 if(!notes.length)notes.push(g.status==='PASS'?'当前输入对应的检查通过':g.status==='RECHECK_REQUIRED'?'受影响的工程输入已改变':g.status==='NOT_CHECKED'?'等待本版检查':'查看本版工程检查结果');
 return {notes,metrics,scope:tr(g.scope||'当前候选')};
}
const summaryText=g=>{const x=gateInfo(g);return x.metrics.length?x.metrics.map(([k,v])=>k+' '+v).slice(0,2).join(' · '):x.notes.slice(0,2).join('；');};
function gateCards(rows,compact=false){return rows.map(g=>`<button class="gate-row ${compact?'compact':''}" ${item('gate',g.id)}><span class="status-dot ${g.status.toLowerCase()}"></span><span><strong>${esc(g.label)}</strong><small>${esc(summaryText(g))}</small></span>${badge(g.status)}<span class="row-arrow">›</span></button>`).join('');}
function counts(system=current()) {const rows=coreRecords(system);return ['PASS','FAIL','UNEVALUABLE','RECHECK_REQUIRED','NOT_CHECKED'].map(status=>({status,count:rows.filter(g=>g.status===status).length}));}
function summaryStrip(){return `<div class="summary-strip" aria-label="当前八项检查汇总">${counts().filter(x=>x.count||['PASS','FAIL','UNEVALUABLE'].includes(x.status)).map(x=>`<button data-filter="${x.status}"><b>${x.count}</b><span>${labels[x.status]}</span></button>`).join('')}<div><b>8</b><span>当前核心检查</span></div></div>`;}
function domainChanges(domain,system=current()) {return changedFiles(system,parentOf(system)).filter(f=>domain==='firmware'?f.path.startsWith('project-fw'):domain==='power'?f.path.startsWith('project-chain')||f.path.startsWith('project-spice'):f.path.includes(domain==='mechanical'?'cad':'assembly'));}
function systemPage() {
 const s=current(),release=latestRelease(s),changes=changedFiles(s,parentOf(s)),contract=data.contracts.find(c=>c.id===s.contracts['power-firmware']),ci=latestInterface(data,s),preview=sourcePreview('cad-top.png');
 const parent=parentOf(s),decision=designDecision(data,s.id);
 const overview=`<div class="design-overview"><div><div class="eyebrow">${s.id===project.submitted?'当前工作候选':'历史候选'} · ${id(s.id)}</div><h2>${esc(systemTitle(s))}</h2><p class="design-purpose">${esc(systemPurpose(s))}</p><div class="context-links">${badge(s.digital_status)}<span>物理验证：${labels[s.physical]||s.physical}</span>${parent?objectButton('system',parent.id,'来自 '+systemTitle(parent)):''}</div><dl class="facts inline">${fact('本轮工程变更',changes.filter(c=>!c.path.startsWith('interfaces/')).length+' 个文件')}${fact('选定工程作业',Object.keys(s.jobs).length+' 个')}<div><dt>BF 决定</dt><dd>${decision?objectButton('decision',decision.id,labels[decision.decision]||'查看公开理由'):'尚无决定'}</dd></div></dl><div class="preview-actions"><button data-preview="schematic.svg">${icon('contract')}原理图</button><button data-preview="pcb-combined.svg">${icon('firmware')}PCB</button><button data-cad>${icon('assembly')}3D CAD</button>${release?`<a class="button-primary" href="${archiveURL(release)}" download>下载同版审查包</a>`:''}</div></div>${preview?`<button class="design-preview" data-cad><img src="${previewURL(preview)}" alt="本版机械模型预览"><span>查看三维模型 ↗</span></button>`:''}</div>`;
 const branches=Object.entries(domains).map(([domain,[title,desc]])=>{const dc=data.domain_commits.find(c=>c.id===s.domain_commits[domain]),diff=domainChanges(domain,s);return `<button class="branch" ${item(dc?'domain':'assets',dc?.id||domain)}>${symbol(domain)}<span><b>${title}</b><small>${dc?`${diff.length} 个工程文件相对父版变化`:'沿用冻结工程资产'} · ${desc}</small><small>${dc?esc(diff.map(f=>f.path.split('/').at(-1)).join('、')||'只更新接口声明，工程文件沿用'):'查看已绑定的文件与检查'}</small></span><span class="row-arrow">›</span></button>`;}).join('');
 const contractBody=contract?`<button class="contract-focus" ${item('contract',contract.id)}><span>${symbol('contract')}<b>电源 ↔ 固件活动</b></span>${badge(contractVerdict(data,s,contract))}<small>第 ${contract.revision} 版 · ${ci?.result?.checks?.length||0} 项源码与声明核对</small></button><p class="muted">${esc(tr(ci?.result?.scope||'等待实际接口检查'))}</p><div class="contract-parts"><div><b>电源提供</b><p>${esc(contract.provides?.map(tr).join('；'))}</p></div><div><b>固件要求</b><p>${esc(contract.requires?.map(tr).join('；'))}</p></div></div>`:empty('尚未建立电源与固件契约');
 const changeRows=changes.map(c=>`<div class="change-row"><button class="text-link" data-diff="${esc(c.path)}">${esc(c.path)}</button><small>${c.before&&c.after?'已修改':c.after?'新增':'已移除'}</small></div>`).join('');
 return `${card('本版设计','',overview)}${summaryStrip()}<div class="grid two">${card('当前工程问题','先看未通过项，再补验证条件',gateCards(coreRecords(s).filter(g=>g.status==='FAIL'),true)||empty('本版没有失败项'),jump('validation',s.id,'查看全部检查'))}${card('专业修订','相对于直接父版本的完整文件差异',branches)}</div><div class="grid two">${card('接口与依赖','',contractBody)}${card('这一版改了什么',parent?'与 '+systemTitle(parent)+' 比较':'冻结导入的完整工程',changeRows||empty('本版没有文件变更'),parent?objectButton('system',parent.id,'查看父版本'):'')}</div>${historyView()}`;
}
function historyView() {
 const tracks=[['system','系统修订',data.systems],['domain','专业提交',data.domain_commits],['validation','独立检查',data.validations],['release','交付',data.releases]];
 let nodes=tracks.flatMap(([kind,label,rows])=>rows.map(v=>({kind,label,v,time:timeOf(v)}))).filter(n=>historyFilter==='all'||n.kind===historyFilter).sort((a,b)=>a.time-b.time||data.systems.indexOf(a.v)-data.systems.indexOf(b.v));
 const total=nodes.length;if(!historyAll)nodes=nodes.slice(-8);
 const rows=tracks.filter(([kind])=>historyFilter==='all'||kind===historyFilter);
 const title=n=>n.kind==='system'?systemTitle(n.v):n.kind==='domain'?domainTitle(n.v):n.kind==='release'?'同版审查包':n.v.kind==='power-firmware-interface'?'接口核对':'整机工程检查';
 const body=`<div class="history-scroll" tabindex="0" aria-label="横向设计历史"><div class="history-grid" data-columns="${nodes.length}"><span class="history-heading">${nodes.length} / ${total} 项</span>${nodes.map(n=>`<span class="history-heading">${stamp(n.time)}</span>`).join('')}${rows.map(([kind,label])=>`<div class="history-label">${icon(kind==='domain'?'system':kind)}<span>${label}</span></div>${nodes.map(n=>`<div class="history-cell">${n.kind===kind?`<button class="history-node ${kind} ${esc(n.v.domain||'')} ${n.v.id===current().id?'selected':''}" ${item(kind,n.v.id)}><span class="node-mark"></span><strong>${esc(title(n))}</strong><small>${id(n.v.id)}</small>${n.v.parent?`<small>← ${esc(n.kind==='system'?systemTitle(data.systems.find(s=>s.id===n.v.parent)||n.v):short(n.v.parent))}</small>`:n.v.target?`<small>对应 ${esc(systemTitle(data.systems.find(s=>s.id===n.v.target)||n.v))}</small>`:''}</button>`:''}</div>`).join('')}`).join('')}</div></div>`;
 return card('设计历史','横向查看版本与父版本；切换节点查看对应工程',body,`<div class="tabs" aria-label="历史类型">${[['system','系统'],['domain','专业'],['validation','检查'],['release','交付'],['all','全部']].map(([k,t])=>`<button data-history="${k}" aria-pressed="${historyFilter===k}">${t}</button>`).join('')}<button data-history-more>${historyAll?'最近记录':'更早记录'}</button></div>`);
}
const roundBounds=(system=current())=>roundScope(data,system);
function activeUsageScope() {return {...(usageScope==='round'?roundBounds():{}),...(usageScope==='session'?{owner:usageOwner||project.owner}:{})};}
function episode(op){
 const o=operationOutcome(op),engineering=o.engineering&&o.engineering!==o.execution,result=op.result||{};
 const resultText=action(op)==='execute'?(result.status==='QUEUED'?'已入队':result.status==='SUCCEEDED'?(result.reused?'精确复用完成':'作业执行完成'):''):result.decision?labels[result.decision]:'';
 return `<button class="episode" ${item('operation',op.id)}><span class="episode-time">${stamp(op.created)}</span><span><strong>${esc(actionLabel(op))}</strong><small>${esc(brief(op.request.rationale||op.request.conclusion||op.request.path||op.request.question,125))}</small></span><span class="outcomes">${resultText?`<span class="outcome-text">${esc(resultText)}</span>`:engineering?badge(o.engineering):''}<small>${labels[o.execution]||o.execution}</small></span></button>`;
}
function runPage() {
 const scope=activeUsageScope(),requests=scopeRequests(data.model_requests,scope),t=usageTotals(requests);
 const ops=data.operations.filter(o=>(!scope.owner||o.owner===scope.owner)&&(scope.start==null||o.created>=scope.start)&&(scope.end==null||o.created<scope.end)&&(!related?.owner||o.owner===related.owner));
 const sessions=data.states.filter(r=>r.model_calls>0||r.status==='RUNNING'),unstarted=data.states.filter(r=>!r.model_calls&&r.status!=='RUNNING');
 const sessionCards=sessions.map(r=>`<button class="session" ${item('run',r.owner)}>${symbol(taskFor(r.owner)?.role||'system')}<span><b>${esc(roleName(r.owner))}</b><small>${r.model_calls} 次累计请求</small></span>${badge(r.status)}</button>`).join('');
 const major=new Set(['commit','integrate','contract','validate','review','execute','finish','decide','release','close','delegate','rebase']);
 const groups=sessions.map(r=>{const events=ops.filter(o=>o.owner===r.owner&&major.has(action(o))).sort((a,b)=>a.created-b.created);if(!events.length)return '';const task=taskFor(r.owner);return `<section class="task-group"><header><div><h3>${esc(roleName(r.owner))}</h3><p>${esc(brief(task?.question||'组织本轮集成、检查、设计决定和交付',150))}</p></div><button data-trace="${esc(r.owner)}">公开对话</button></header>${events.slice(-6).map(episode).join('')}${events.length>6?`<details class="earlier-actions"><summary>更早行动 · ${events.length-6} 项</summary>${events.slice(0,-6).map(episode).join('')}</details>`:''}</section>`;}).join('');
 return `${card('运行范围与费用','任务范围与费用范围共同切换',`<div class="run-controls"><label>查看范围 <select id="usage-scope" aria-label="查看范围"><option value="round" ${usageScope==='round'?'selected':''}>本轮</option><option value="session" ${usageScope==='session'?'selected':''}>本会话累计</option><option value="project" ${usageScope==='project'?'selected':''}>项目累计</option></select></label>${usageScope==='session'?`<label>Agent <select id="usage-owner" aria-label="选择 Agent 会话">${sessions.map(s=>`<option value="${s.owner}" ${s.owner===(usageOwner||project.owner)?'selected':''}>${esc(roleName(s.owner))}</option>`).join('')}</select></label>`:''}<small>${scope.start?stamp(scope.start)+' → '+(scope.end?stamp(scope.end):'最近一次读取'):'完整累计记录'}${related?.owner?' · 聚焦 '+roleName(related.owner):''}</small>${related?.owner?jump('runs','','取消任务聚焦'):''}</div><div class="metrics">${metric('模型请求',t.requests)}${metric('本地保守登记','$'+t.ledger.toFixed(4))}${metric('缓存费率估算',t.estimated?'$'+t.estimate.toFixed(4):'未记录')}${metric('UNKNOWN 预留',t.unknown)}</div>`)}<details class="section-details" open><summary>Agent 会话 · ${sessions.length} 个有运行记录</summary><div class="sessions">${sessionCards}</div>${unstarted.length?`<details><summary>${unstarted.length} 个未启动任务</summary>${unstarted.map(r=>objectButton('run',r.owner,roleName(r.owner)+' · 未启动')).join('')}</details>`:''}</details>${card('任务与工程行动','按 Agent 分组；每项展示实际结果与公开理由',groups||empty('所选范围没有工程行动'))}<details class="section-details"><summary>模型请求明细 · ${requests.length} 条</summary><div class="table-wrap"><table><thead><tr><th>时间</th><th>Agent</th><th>请求</th><th>状态</th><th>Token</th><th>本地费用</th></tr></thead><tbody>${[...requests].reverse().map(r=>`<tr><td>${stamp(r.created)}</td><td>${esc(roleName(r.owner))}</td><td>${objectButton('request',r.id,short(r.id))}</td><td>${badge(r.status)}</td><td>${r.usage?.total_tokens?.toLocaleString()||'待核对'}</td><td>$${Number((r.status==='SETTLED'?r.charged:r.reserved)??0).toFixed(5)}</td></tr>`).join('')}</tbody></table></div></details><details class="section-details"><summary>底层工具操作 · ${ops.length} 条可查</summary>${ops.map(o=>`<div class="log-row">${objectButton('operation',o.id,actionLabel(o)+' · '+stamp(o.created))}${badge(o.status)}</div>`).join('')}</details>`;
}
const metric=(title,value)=>`<div><small>${esc(title)}</small><b>${esc(value)}</b></div>`;
function validationPage() {
 const rows=coreRecords(current()),filtered=rows.filter(g=>validationFilter==='all'||g.status===validationFilter),ci=latestInterface(data,current()),history=data.validations.filter(v=>v.target===current().id);
 const links=`<div class="tabs" aria-label="筛选当前核心检查">${[['all','全部'],['FAIL','未通过'],['UNEVALUABLE','缺少条件'],['PASS','通过'],['RECHECK_REQUIRED','需复查']].map(([k,t])=>`<button data-filter="${k}" aria-pressed="${validationFilter===k}">${t}</button>`).join('')}</div>`;
 return `${summaryStrip()}${card('当前版本 · 八项核心检查','每项只显示本版当前有效结果',gateCards(filtered)||empty('这个筛选下没有检查'),links)}${card('电源与固件接口','实际源码与负载声明的对应关系',ci?`<div class="result-heading"><strong>${ci.result?.checks?.length||0} 项核对</strong>${badge(ci.status)}${objectButton('validation',ci.id,'查看对照与来源')}</div><p class="muted">${esc(tr(ci.result?.scope))}</p>`:empty('尚无本版接口检查'))}<details class="section-details" ${related?.history?'open':''}><summary>本版检查历史 · ${history.length} 条回执</summary><div class="table-wrap"><table><thead><tr><th>检查范围</th><th>结果</th><th>检查器</th><th>回执</th></tr></thead><tbody>${[...history].reverse().map(v=>`<tr><td>${v.kind==='power-firmware-interface'?'电源与固件接口':'独立工程审查'}</td><td>${badge(v.status)}</td><td>${esc(v.result?.checker||v.evaluator?.version||v.evaluator)}</td><td>${objectButton('validation',v.id,'查看回执 '+short(v.id))}</td></tr>`).join('')}</tbody></table></div></details>`;
}
const toolNames={CAD_PYTHON:'机械 CAD · Python / CadQuery',EDA_CLI:'立创 EDA · Connect',EDA_NATIVE_CLI:'立创桌面版',NGSPICE:'电路仿真 · ngspice',ARM_GCC:'目标固件 · ARM GCC',COMSOL:'多物理场 · COMSOL',BLENDER:'渲染 · Blender',NODE:'Agent 运行 · Node.js',GO:'Go 工具链',RENODE:'MCU 仿真 · Renode'};
function toolUsage(key) {
 const kinds=key==='NGSPICE'?['spice']:key==='ARM_GCC'?['firmware-nrf52832-s132']:[];
 const executions=data.executions.filter(e=>kinds.includes(e.kind)),jobs=Object.entries(current().jobs).filter(([,r])=>kinds.includes(r.kind));
 if(kinds.length)return {text:jobs.length?`${jobs.length} 个本版选定作业`:'本版未选择作业',executions,jobs};
 if(key==='CAD_PYTHON'){const cad=Object.entries(current().jobs).filter(([,r])=>Object.keys(r.artifacts).some(p=>p.includes('mesh')||p.endsWith('.step')));return {text:cad.length?`${cad.length} 个已绑定 CAD 作业`:'本版无 CAD 作业',executions:[],jobs:cad};}
 if(key.startsWith('EDA'))return {text:data.environment.native_project_count?`${data.environment.native_project_count} 个授权工程`:'本环境读取冻结工程',executions:[],jobs:[]};
 return {text:'本项目未记录调用',executions:[],jobs:[]};
}
function environmentPage() {
 const pins=Object.entries(data.environment.tool_pins.tools||{});
 return `${card('当前环境','软件资产与执行权限',`<div class="metrics">${metric('已固定软件',pins.filter(([,p])=>p.exists).length+' 项')}${metric('原生执行权限',data.environment.capabilities.native?'已开放':'未开放')}${metric('EDA 工程写入',data.environment.native_project_count?data.environment.native_project_count+' 个授权工程':'当前隔离环境未开放')}${metric('当前选定作业',Object.keys(current().jobs).length+' 个')}</div>`)}${card('工具与实际使用','点击查看固定路径、摘要和对应执行记录',`<div class="tool-list">${pins.map(([key,p])=>{const use=toolUsage(key);return `<button class="tool-row" ${item('tool',key)}>${symbol(key.includes('EDA')?'contract':key==='ARM_GCC'?'firmware':key==='NGSPICE'?'power':'environment')}<span><b>${esc(toolNames[key]||key)}</b><small>${esc(p.resolved?.split('/').slice(-3).join('/')||p.path)}</small></span><span>${p.exists?'已安装':'缺少软件'}<small>${esc(use.text)}</small></span><span class="row-arrow">›</span></button>`;}).join('')}</div>`)}${card('工具接口','Pi 实际工具入口与服务合同',`<div class="interface-list">${data.interfaces.map(i=>`<button class="row-card" ${item('interface',i.id)}><b>${esc(actionNames[i.id.replace('repository_','')]||i.id)}</b><small>${esc(i.pi_tool)} · ${esc(i.method)} ${esc(i.endpoint)}</small></button>`).join('')}</div>`)}<details class="section-details"><summary>环境身份与资源锁</summary><dl class="facts">${fact('环境',data.environment.profile_id)}${fact('运行端口',data.environment.port)}${fact('稳定 Demo',data.original_demo_port)}${fact('共享原生锁',data.environment.shared_native_lock)}${fact('环境摘要',data.environment.profile_sha256)}${fact('基线摘要',data.project.baseline.manifest_sha256)}</dl></details>`;
}
const skillNames={'bf-design-task-control-v1':'设计任务控制与恢复','bf-compiled-event-port-v1':'事件与程序接口','bf-native-coupling-v2':'原生联合执行'};
const skillTitle=s=>skillNames[s.id]||s.name||s.description||s.id;
function selectedMethod(){return data.methods.find(m=>m.owner===(selectedMethodOwner||project.owner))||data.methods[0];}
function harnessPage() {
 const m=selectedMethod();if(!m)return empty('本项目尚无方法加载记录');const owner=m.owner,facts=methodFacts.get(owner),active=new Set(data.skill_activations.filter(a=>a.owner===owner&&a.active).map(a=>a.skill_id)),loaded=new Set(m.resource_manifest?.skills?.map(s=>s.id)||[]),skills=methodSkills();
 const model=facts?.model?.id||facts?.model?.model||facts?.model||'查看实际请求';
 const skillRow=s=>`<button class="skill-row" ${item('skill',s.id)}><span><b>${esc(skillTitle(s))}</b><small>版本 ${esc(s.version||'冻结版本')}</small></span>${badge(active.has(s.id)?'ACTIVE':loaded.has(s.id)?'LOADED':'AVAILABLE')}</button>`;
 const currentSkills=skills.filter(s=>loaded.has(s.id)||active.has(s.id)),catalog=skills.filter(s=>!loaded.has(s.id)&&!active.has(s.id));
 return `${card(roleName(owner)+' · 执行配置','选定 Agent 的实际加载记录',`<div class="owner-tabs tabs">${data.methods.map(v=>`<button data-method-owner="${v.owner}" aria-pressed="${v.owner===owner}">${esc(roleName(v.owner))}</button>`).join('')}</div><dl class="facts inline">${fact('控制器',m.controller)}${fact('源码版本',short(m.source_commit))}${fact('模型',typeof model==='string'?model:'查看加载回执')}${fact('工具',(m.tools||[]).join('、'))}</dl><div class="context-links">${objectButton('method',m.owner,'配置详情')}<button data-trace="${owner}" data-trace-start="1">实际提示词与请求</button></div>`)}${card('本会话技能','已激活、配置加载和可用目录分别显示',`<div class="skill-list">${currentSkills.map(skillRow).join('')}</div>`)}<details class="section-details"><summary>其他可用技能 · ${catalog.length} 项</summary><div class="skill-list">${catalog.map(skillRow).join('')}</div></details><details class="section-details"><summary>配置身份 · ${new Set(data.methods.map(m=>m.harness_id)).size} 个版本</summary>${data.methods.map(v=>`<div class="config-row">${objectButton('method',v.owner,roleName(v.owner))}${id(v.harness_id)}<small>${esc(v.resource_manifest?.policy||'冻结配置')}</small></div>`).join('')}</details>`;
}
function experimentPage() {
 const studies=data.experiments;
 if(!studies.length)return card('准备方法比较','当前尚无注册实验',`<div class="experiment-empty">${symbol('experiments')}<h3>先固定比较条件，再记录方法收益</h3><p>在这里查看实验协议、相同条件下的结果与采用决定。</p><dl class="facts inline">${fact('注册实验','0 项')}${fact('已加载方法配置',new Set(data.methods.map(m=>m.harness_id)).size+' 个')}${fact('当前工程候选',systemTitle(current()))}${fact('方法比较结果','尚未执行')}</dl><div class="context-links">${jump('runs','','查看实际运行')}${jump('harness','','查看方法配置')}${jump('environment','','查看实验环境')}</div></div>`);
 return card('方法实验','固定方法、环境、评价器与输入',studies.map(s=>`<button class="study" ${item('experiment',s.id)}><strong>${esc(s.title)}</strong>${badge(s.status)}<p>${esc(s.hypothesis)}</p><small>${(s.results||[]).length} 条实际结果</small></button>`).join(''));
}
function objectNav(title,buttons){return `<section class="object-group"><h3>${esc(title)}</h3>${buttons}</section>`;}
function renderContext() {
 const s=current();let nav='',banner='';
 if(page==='system'){
  nav=objectNav('系统版本',objectButton('system',s.id,'当前查看 · '+systemTitle(s))+objectButton('system',project.adopted,'稳定参考'))+objectNav('专业工作',Object.entries(domains).map(([k,[t]])=>objectButton(s.domain_commits[k]?'domain':'assets',s.domain_commits[k]||k,t)).join(''))+objectNav('接口与交付',Object.values(s.contracts).map(k=>objectButton('contract',k,'电源 ↔ 固件活动')).join('')+(latestRelease(s)?objectButton('release',latestRelease(s).id,'同版审查包'):''));
  banner=`${coreRecords(s).filter(g=>g.status==='FAIL').map(g=>g.label).join('、')||'查看本版核心检查'} · ${coreRecords(s).filter(g=>g.status==='UNEVALUABLE').length} 项待补验证条件`;
 }else if(page==='runs'){
  nav=objectNav('设计轮次',data.systems.filter(v=>v.id===project.submitted||data.releases.some(r=>r.target===v.id)).slice().reverse().map(v=>`<button data-round="${v.id}" aria-pressed="${v.id===s.id}">${esc(systemTitle(v))}<small>${id(v.id)}</small></button>`).join(''))+objectNav('Agent 任务',data.states.filter(r=>r.model_calls||r.status==='RUNNING').map(r=>`<button data-session="${r.owner}">${esc(roleName(r.owner))}<small>${labels[r.status]||r.status}</small></button>`).join(''));
  const running=data.states.filter(r=>r.status==='RUNNING');banner=running.length?running.map(r=>roleName(r.owner)).join('、')+' 正在执行':'当前没有正在执行的 Agent 任务';
 }else if(page==='validation'){
  nav=objectNav('当前核心检查',coreRecords(s).map(g=>`<button ${item('gate',g.id)}><span class="status-dot ${g.status.toLowerCase()}"></span>${esc(g.label)}</button>`).join(''))+objectNav('其他记录',latestInterface(data,s)?objectButton('validation',latestInterface(data,s).id,'电源 ↔ 固件接口'):'');banner=`当前候选：${counts(s).filter(x=>x.count).map(x=>x.count+' 项'+labels[x.status]).join('，')}`;
 }else if(page==='environment'){
  nav=objectNav('软件与工具',Object.keys(data.environment.tool_pins.tools).map(k=>objectButton('tool',k,toolNames[k]||k)).join(''))+objectNav('实际接口',data.interfaces.map(i=>objectButton('interface',i.id,actionNames[i.id.replace('repository_','')]||i.id)).join(''));banner=`V2 环境 :${data.environment.port} · ${Object.keys(s.jobs).length} 个本版选定作业 · EDA ${data.environment.native_project_count?'授权工程可写':'读取冻结工程'}`;
 }else if(page==='harness'){
  nav=objectNav('Agent 方法',data.methods.map(m=>`<button data-method-owner="${m.owner}" aria-pressed="${m.owner===(selectedMethodOwner||project.owner)}">${esc(roleName(m.owner))}</button>`).join(''))+objectNav('已激活技能',data.skill_activations.filter(a=>a.owner===(selectedMethodOwner||project.owner)&&a.active).map(a=>objectButton('skill',a.skill_id,skillTitle(methodSkills().find(s=>s.id===a.skill_id)||{id:a.skill_id}))).join('')||'<p class="muted">此会话尚未激活技能</p>');banner=`${roleName(selectedMethodOwner||project.owner)} 的冻结配置与实际技能激活`;
 }else{nav=objectNav('实验协议',data.experiments.map(e=>objectButton('experiment',e.id,e.title)).join('')||'<p class="muted">尚未注册实验</p>')+objectNav('相关资料',jump('harness','','方法配置')+jump('environment','','环境')+jump('runs','','真实运行'));banner='方法比较与采用记录';}
 $('#design-objects').innerHTML=nav;$('#current-question').innerHTML=`<div class="page-summary"><span>${esc(banner)}</span><small>最新工程事件 ${stamp(Math.max(0,...data.events.map(e=>e.created)))}</small></div>`;
}
function searchPage() {
 const s=current(),objects=[...coreRecords(s).map(v=>({kind:'gate',v})),...data.systems.map(v=>({kind:'system',v,label:systemTitle(v)+' '+systemPurpose(v)})),...data.domain_commits.map(v=>({kind:'domain',v,label:domainTitle(v)})),...data.contracts.map(v=>({kind:'contract',v,label:'电源与固件活动契约'})),...methodSkills().map(v=>({kind:'skill',v}))];
 const q=query.trim().toLowerCase(),matches=objects.filter(o=>(publicSearchText(o.v)+' '+(o.label||'')+' '+(o.kind==='gate'?summaryText(o.v):'')).toLowerCase().includes(q));
 const files=Object.keys(s.files).filter(p=>p.toLowerCase().includes(q));const total=matches.length+files.length;
 return card('搜索结果',`${total} 项 · 本项目设计、问题与当前候选文件`,total?matches.map(o=>`<button class="search-result" ${item(o.kind,o.v.id)}><strong>${esc(selectionTitle(o.kind,o.v))}</strong><small>${esc(brief(o.v.rationale||o.v.description||o.v.scope||o.v.id,160))}</small></button>`).join('')+files.map(p=>`<button class="search-result" data-file="${esc(p)}"><strong>${esc(p)}</strong><small>当前候选工程文件</small></button>`).join(''):empty('没有找到相关设计、问题或文件'),'<button data-clear-search>清空搜索</button>');
}
function getSelection(kind,key) {
 const table={system:data.systems,domain:data.domain_commits,contract:data.contracts,validation:data.validations,integration:data.integration_requests,release:data.releases,method:data.methods,skill:methodSkills(),experiment:data.experiments,operation:data.operations,run:data.states,request:data.model_requests,execution:data.executions};
 if(kind==='gate')return coreRecords(current()).find(g=>g.id===key);
 if(kind==='decision'){const record=data.decisions.find(d=>d.id===key);return record?designDecision({decisions:[record]},record.to_design):null;}
 if(kind==='tool')return {id:key,...data.environment.tool_pins.tools[key]};
 if(kind==='interface')return data.interfaces.find(v=>v.id===key);
 if(kind==='assets')return {id:key,files:Object.entries(current().files).filter(([p])=>key==='mechanical'?p.includes('cad'):key==='assembly'?p.includes('assembly'):true).map(([path,r])=>({path,...r}))};
 return table[kind]?.find(v=>(kind==='method'?v.owner:v.id||v.owner)===key);
}
const valueText=v=>v==null?'—':typeof v==='boolean'?v?'是':'否':typeof v==='object'?Array.isArray(v)?v.map(valueText).join(' – '):JSON.stringify(v):String(v);
const fieldValue=(c,value)=>valueText(value)+(value!=null?(c.id.endsWith('_ms')||['connection_bound','model_interface_advertising'].includes(c.id)?' ms':c.id.endsWith('_v')?' V':''):'');
const fieldNames={advertising_ms:'实际广播间隔',connection_min_ms:'最小连接间隔',connection_max_ms:'最大连接间隔',sample_ms:'采样周期',connection_bound:'负载连接间隔',model_interface_advertising:'模型广播间隔',manual_admission_energy:'人工接通注入能量',power_declaration_rail_v:'工作电压',power_declaration_storage_initial_v:'初始储能电压',power_declaration_manual_admission:'人工接通',power_declaration_sece_resolved:'SECE 条件已确认',firmware_declaration_advertising_ms:'固件声明广播间隔',firmware_declaration_connection_min_ms:'固件声明最小连接间隔',firmware_declaration_connection_max_ms:'固件声明最大连接间隔',firmware_declaration_sample_ms:'固件声明采样周期',firmware_declaration_policy_advertising_ms:'策略广播周期'};
function checksTable(checks=[]) {
 const fields=checks.filter(c=>!String(c.id).includes('_source_'));
 return `<div class="table-wrap"><table class="comparison"><thead><tr><th>参数</th><th>实际值</th><th>声明 / 要求</th><th>结果</th></tr></thead><tbody>${fields.map(c=>`<tr><td>${esc(fieldNames[c.id]||c.id)}<small>${esc(brief(c.source,150))}</small></td><td>${esc(fieldValue(c,c.actual))}</td><td>${esc(fieldValue(c,c.expected))}</td><td>${badge(c.status)}</td></tr>`).join('')}</tbody></table></div>`;
}
function metricsList(metrics){return metrics.length?`<dl class="facts">${metrics.map(([k,v])=>fact(k,v)).join('')}</dl>`:'';}
function notesList(notes){return `<ul class="findings">${notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul>`;}
function filesList(files,extra=''){return Object.entries(files||{}).map(([p,r])=>`<button class="file-link" data-file="${esc(p)}" ${extra}><span>${esc(p)}</span><small>${Math.ceil((r.bytes||0)/1024)} KB</small></button>`).join('');}
function provenance(v,kind) {
 const key=v.id||v.harness_id||v.owner;
 return `<details class="provenance"><summary>版本与来源</summary><dl class="facts">${fact('记录身份',key)}${fact('系统候选',v.target||v.evidence_target||v.system_commit||v.base_system||(kind==='system'?v.id:current().id))}${v.parent?fact('父版本',v.parent):''}${v.owner?fact('原会话',v.owner):''}${v.input_fingerprint?fact('输入摘要',v.input_fingerprint):''}${v.evidence?.sha256?fact('证据摘要',v.evidence.sha256):''}${v.reused_from?fact('复用来源',v.reused_from):''}${v.scope?fact('检查范围',tr(v.scope)):''}</dl><button data-copy="${esc(key)}">复制完整身份</button></details>`;
}
function showDetail(kind,key) {
 const v=getSelection(kind,key);if(!v){$('#detail').innerHTML=empty('请选择要查看的对象');return;}
 $('#inspector-title').textContent=selectionTitle(kind,v);
 let status=kind==='contract'?contractVerdict(data,current(),v):kind==='system'?v.digital_status:kind==='operation'?operationOutcome(v).engineering||v.status:v.status;
 let html=`<div class="detail-heading"><small>${esc(kind==='gate'?'当前核心检查':kind==='contract'?'接口版本':'工程记录')}</small><h2>${esc(selectionTitle(kind,v))}</h2>${status?badge(status):''}</div><div class="tabs detail-tabs" aria-label="详情内容"><button data-detail="details" aria-pressed="${detailMode==='details'}">说明</button><button data-detail="evidence" aria-pressed="${detailMode==='evidence'}">证据与文件</button><button data-detail="raw" aria-pressed="${detailMode==='raw'}">原始记录</button></div>`;
 if(detailMode==='raw'){html+=json(v);$('#detail').innerHTML=html;return;}
 if(kind==='gate'){
  const g=gateInfo(v);html+=`<h3>检查结论</h3>${notesList(g.notes)}${metricsList(g.metrics)}<h3>条件与范围</h3><p>${esc(g.scope)}</p><div class="context-links"><button data-gate-report="${esc(key)}">打开检查报告</button>${v.validation_id?objectButton('validation',v.validation_id,'完整复查回执'):''}</div>`;
  if(key==='power_load_chain')html+=`<div class="context-links"><button data-file="project-chain/load-timeline.json">本版负载时序</button>${Object.entries(current().jobs).filter(([,j])=>j.kind==='spice').map(([job,j])=>j.artifacts['project-trace.raw']?`<a href="${fileURL('project-trace.raw',{job})}" download>下载本版 RAW</a>`:'').join('')}</div>`;
  if(key==='pcb_connectivity_drc')html+='<button data-preview="pcb-combined.svg">查看本版 PCB</button>';
 }else if(kind==='contract'){
  const check=latestInterface(data,current());html+=`<h3>本候选下的接口结果</h3><p>${esc(tr(check?.result?.scope||'本候选尚无检查'))}</p>${checksTable(check?.result?.checks)}<h3>保持开放的问题</h3>${notesList((check?.result?.issues||[]).map(i=>i.id==='sece-envelope'?'SECE 开关、器件动态和模型适用条件待补充':i.id==='policy-radio-duty'?'实际无线活动与策略周期需共同核对':i.id))}<h3>关联专业</h3>${Object.entries(v.domain_commits).map(([d,c])=>objectButton('domain',c,domains[d]?.[0]||d)).join('')}`;
 }else if(kind==='validation'){
  html+=`<p>${esc(tr(v.result?.scope||v.scope||v.kind))}</p>`;
  if(v.result?.gates)html+=Object.entries(v.result.gates).map(([g,r])=>`<div class="report-gate"><h3>${esc(gateNames[g])} ${badge(r.status)}</h3>${notesList(gateInfo(r).notes)}${metricsList(gateInfo(r).metrics)}</div>`).join('');
  else html+=checksTable(v.result?.checks||v.controls||[]);
  html+=`<h3>检查器</h3><p>${esc(v.result?.checker||v.evaluator?.version||v.evaluator)}</p><div class="context-links">${jump('system',v.target,'查看对应系统')}<button data-record-download="validation" data-record-key="${esc(key)}">下载检查回执</button></div>`;
 }else if(kind==='system'){
  html+=`<p>${esc(systemPurpose(v))}</p>${publicNote(opFor(v.id)?.request?.rationale,'BF 集成理由')}<h3>当前资格</h3>${gateCards(coreRecords(v),true)}<h3>专业提交</h3>${Object.entries(v.domain_commits).map(([d,c])=>objectButton('domain',c,domains[d]?.[0]||d)).join('')}<h3>本版文件</h3>${filesList(Object.fromEntries(Object.entries(v.files).slice(0,detailMode==='evidence'?undefined:6)),`data-system="${v.id}"`)}${latestRelease(v)?`<a class="button-primary" href="${archiveURL(latestRelease(v))}" download>下载同版审查包</a>`:''}`;
 }else if(kind==='domain'){
  const system=data.systems.find(s=>s.id===v.base_system),diff=changedFiles(v,system);html+=`<h3>本次提交</h3><p>${esc(brief(v.rationale,220))}</p>${publicNote(v.rationale)}<h3>完整源树与累计修改</h3><p>${Object.keys(v.files).length} 件冻结文件 · 相对系统基准 ${diff.length} 件变化</p>${diff.map(c=>`<button class="file-link" data-file="${esc(c.path)}" data-domain="${v.id}">${esc(c.path)}</button>`).join('')}<h3>实际执行</h3>${data.executions.filter(e=>e.domain_commit===v.id).map(e=>objectButton('execution',e.id,(e.kind==='spice'?'电源求解':'目标构建')+' · '+(e.reused?'精确复用':'新执行')+' · '+(labels[e.status]||e.status))).join('')||'<p>此提交没有单独执行记录</p>'}${detailMode==='evidence'?`<h3>完整文件清单</h3>${filesList(v.files,`data-domain="${v.id}"`)}`:''}`;
 }else if(kind==='operation'){
  const o=operationOutcome(v);html+=`<dl class="facts">${fact('调用执行',labels[o.execution]||o.execution)}${fact('工程结果',labels[o.engineering]||o.engineering||'此操作未产生工程判定')}${fact('执行者',roleName(v.owner))}${fact('时间',stamp(v.created))}</dl><h3>公开理由与结论</h3><p class="public-text">${esc(readable(v.request.rationale||v.request.conclusion||v.request.question||v.request.path||''))}</p>`;
  const resultKey=v.result?.id,kindMap={SC:'system',DC:'domain',RV:'validation',IC:'contract',EX:'execution',REL:'release'};if(resultKey&&kindMap[resultKey.split('-')[0]])html+=objectButton(kindMap[resultKey.split('-')[0]],resultKey,'查看实际产物与结果');
  html+=`<div class="context-links"><button data-trace="${v.owner}">公开会话与工具</button></div>`;
 }else if(kind==='decision'){
  html+=`<h3>BF 的选择</h3>${badge(v.decision)}<h3>对应候选的工程结论</h3>${gateCards(coreRecords(data.systems.find(s=>s.id===v.to_design)||current()).filter(g=>g.status==='FAIL'),true)}${publicNote(v.rationale,'BF 的完整公开理由')}<div class="context-links">${objectButton('system',v.to_design,'查看该候选')}<button data-trace="${v.owner}">查看对应公开对话</button></div>`;
 }else if(kind==='run'){
  html+=`<h3>任务</h3><p class="public-text">${esc(readable(v.task?.question||'系统候选集成、检查、设计决定和交付'))}</p><h3>完成条件</h3><p>${esc(readable(v.task?.completion||'形成同版工程审查交付与设计决定'))}</p><div class="metrics">${metric('会话累计请求',v.model_calls)}${metric('本地保守登记','$'+Number(v.cost_upper_bound_usd).toFixed(4))}</div>${v.error?`<h3>执行卡点</h3><p>${esc(v.error)}</p>`:''}<div class="context-links"><button data-trace="${v.owner}">公开对话</button><button data-session="${v.owner}">查看会话执行与费用</button></div>`;
 }else if(kind==='execution'){
  html+=`<dl class="facts">${fact('类型',v.kind)}${fact('作业',v.job_id)}${fact('结果',labels[v.status]||v.status)}${fact('本次操作',v.reused?'复用相同输入的成功作业':'新执行')}${fact('输入源文件',Object.keys(v.consumed_input?.sources||{}).join('、'))}</dl>${objectButton('domain',v.domain_commit,'查看冻结源树')}<h3>结果产物</h3>${Object.entries(v.artifacts||{}).map(([p,ref])=>{const bound=jobArtifactSystem(data,current(),v.job_id,p,ref.sha256);return bound?`<button class="file-link" data-job-file="${esc(p)}" data-job="${esc(v.job_id)}" data-system="${bound.id}">${esc(p)}</button>`:`<p class="file-link">${esc(p)} <small>尚未纳入系统候选</small></p>`;}).join('')}`;
 }else if(kind==='method'){
  html+=`<dl class="facts">${fact('Agent',roleName(v.owner))}${fact('控制器',v.controller)}${fact('工具',(v.tools||[]).join('、'))}${fact('源码版本',v.source_commit)}${fact('方法身份',v.harness_id)}</dl><h3>冻结的上下文组件</h3><p>${esc(Object.keys(v.context_bindings||{}).join('、'))}</p><h3>技能资源</h3>${(v.resource_manifest?.skills||[]).map(s=>objectButton('skill',s.id,s.description||s.id)).join('')}<button data-trace="${v.owner}" data-trace-start="1">实际提示词、模型与加载记录</button>`;
 }else if(kind==='skill'){
  const owner=selectedMethodOwner||project.owner,activations=data.skill_activations.filter(a=>a.skill_id===v.id);html+=`<h3>用途</h3><p>${esc(v.description||v.name)}</p><dl class="facts">${fact('版本',v.version)}${fact('来源',v.plugin_id||v.path)}${fact('当前 Agent',roleName(owner))}${fact('当前激活',activations.some(a=>a.owner===owner&&a.active)?'已激活':'未激活')}</dl><h3>实际使用记录</h3>${activations.map(a=>`<p>${esc(roleName(a.owner))} · ${stamp(a.updated)} · ${a.active?'激活':'已停用'}</p><button data-trace="${a.owner}">查看对应公开请求</button>`).join('')||'<p>本项目尚无激活记录</p>'}`;
 }else if(kind==='tool'){
  const use=toolUsage(v.id);html+=`<dl class="facts">${fact('安装记录',v.exists?'已安装并固定摘要':'未安装')}${fact('实际路径',v.resolved||v.path)}${fact('本版使用',use.text)}${fact('工具能力资格','当前投影未登记独立能力资格')}</dl><h3>真实执行记录</h3>${use.executions.map(e=>objectButton('execution',e.id,(e.kind==='spice'?'SPICE 求解':'S132 构建')+' · '+(labels[e.status]||e.status))).join('')||'<p>本环境没有此工具的新增执行回执</p>'}<h3>本版绑定产物</h3>${use.jobs.map(([j,r])=>`<p>${id(j)} · ${Object.keys(r.artifacts).length} 个产物</p>`).join('')||'<p>本版未选择对应作业</p>'}`;
 }else if(kind==='interface'){
  html+=`<dl class="facts">${fact('工具',v.pi_tool)}${fact('服务入口',v.method+' '+v.endpoint)}${fact('输入动作',v.input?.action)}${fact('参数',(v.input?.fields||[]).join('、'))}${fact('输出',v.output)}${fact('写入影响',v.side_effects)}${fact('恢复与校验',v.contract)}</dl><details><summary>实现位置与认证</summary><p>${esc(v.implementation)}</p><p>${esc(v.authentication)}</p></details>`;
 }else if(kind==='release'){
  html+=`<p class="public-text">${esc(readable(v.rationale))}</p><dl class="facts">${fact('文件',Object.keys(v.files||{}).length+' 件')}${fact('绑定检查记录',(v.validations||[]).length+' 条')}</dl>${objectButton('system',v.target,'查看对应系统候选')}<a class="button-primary" href="${archiveURL(v)}" download>下载同版审查包</a>`;
 }else if(kind==='assets')html+=v.files.map(f=>`<button class="file-link" data-file="${esc(f.path)}">${esc(f.path)}</button>`).join('')||empty('当前候选没有对应文件');
 else if(kind==='request')html+=`<dl class="facts">${fact('Agent',roleName(v.owner))}${fact('时间',stamp(v.created))}${fact('状态',labels[v.status])}${fact('输入 token',v.usage?.prompt_tokens)}${fact('缓存命中',v.usage?.prompt_cache_hit_tokens)}${fact('输出 token',v.usage?.completion_tokens)}${fact('本地保守登记',v.charged)}${fact('全额预留',v.reserved)}${fact('缓存费率估算',v.cost_estimate?.cache_aware_estimate_usd)}</dl>`;
 else if(kind==='experiment')html+=`<h3>假设</h3><p>${esc(v.hypothesis)}</p><h3>可推翻条件</h3><p>${esc(v.falsifier)}</p><h3>比较条件</h3>${(v.conditions||[]).map(c=>`<p>${esc(c.id)} · ${esc(c.method)}</p>`).join('')}<h3>结果</h3>${v.results?.length?json(v.results):empty('尚无实际结果')}`;
 else if(kind==='integration')html+=`<h3>集成目的</h3><p>${esc(readable(v.rationale))}</p>${Object.entries(v.domain_commits||{}).map(([d,c])=>objectButton('domain',c,domains[d]?.[0]||d)).join('')}${v.system_commit?objectButton('system',v.system_commit,'查看系统候选'):''}`;
 html+=provenance(v,kind);$('#detail').innerHTML=html;
}
function inspector(open,focus=false) {
 shell.classList.toggle('inspector-hidden',!open);$('#inspector').hidden=!open;$('#inspector-toggle').setAttribute('aria-expanded',String(open));
 sessionStorage.setItem('bf-lab-inspector-'+page,String(open));if(focus&&open)$('#inspector-close').focus();
}
function saveView(){viewStates.set(location.hash,{y:scrollY,nav:$('#navigation').scrollTop,history:$('.history-scroll')?.scrollLeft});window.history.replaceState({...window.history.state,labScroll:scrollY},'');}
function route(to=page,object=selection,push=true) {
 saveView();const params=new URLSearchParams({candidate:systemId});if(object){params.set('kind',object.kind);params.set('object',object.key);}const hash='#'+to+'?'+params;
 window.history[push?'pushState':'replaceState']({labScroll:push?0:scrollY},'',hash);render(!push);
}
function go(to,key) {
 related=null;if(['system','validation'].includes(to)&&data.systems.some(s=>s.id===key))systemId=key;
 if(to==='runs'&&key&&data.states.some(s=>s.owner===key)){usageScope='session';usageOwner=key;related={owner:key};}
 selection=null;route(to,null);
}
function selectObject(kind,key) {
 const v=getSelection(kind,key);if(!v)return;
 if(kind==='system')systemId=key;
 if(['validation','release'].includes(kind)&&data.systems.some(s=>s.id===v.target))systemId=v.target;
 if(kind==='domain'&&!Object.values(current().domain_commits).includes(key))systemId=[...data.systems].reverse().find(s=>Object.values(s.domain_commits).includes(key))?.id||v.base_system;
 if(kind==='contract'&&!Object.values(current().contracts).includes(key))systemId=[...data.systems].reverse().find(s=>Object.values(s.contracts).includes(key))?.id||v.base_system;
 selection={kind,key};detailMode='details';route(page,selection);inspector(true);showDetail(kind,key);persist();
}
function persist(){sessionStorage.setItem('bf-lab-context-'+project.id,JSON.stringify({systemId,selection,usageScope,usageOwner,selectedMethodOwner,historyFilter,historyAll,validationFilter}));}
function render(preserve=true) {
 if(!data)return;const prior=preserve?{y:scrollY,history:$('.history-scroll')?.scrollLeft,nav:$('#navigation').scrollTop}:null;
 const [mode,search]=location.hash.slice(1).split('?'),params=new URLSearchParams(search||'');page=headings[mode]?mode:'system';
 const candidate=params.get('candidate');if(candidate&&data.systems.some(s=>s.id===candidate))systemId=candidate;
 if(params.has('kind'))selection={kind:params.get('kind'),key:params.get('object')};
 $('#candidate-select').innerHTML=data.systems.slice().reverse().map(s=>`<option value="${s.id}" ${s.id===systemId?'selected':''}>${esc(systemTitle(s))}${s.id===project.submitted?' · 当前':''}</option>`).join('');
 $('#adopted').textContent='稳定参考';$('#adopted').title='查看采用版 '+project.adopted;
 $('#title').textContent=headings[page][0];$('#subtitle').textContent=headings[page][1];
 document.querySelectorAll('[data-page]').forEach(a=>{a.classList.toggle('active',a.dataset.page===page);if(a.dataset.page===page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
 $('#search').value=query;$('#search-clear').hidden=!query;renderContext();
 $('#content').innerHTML=query?searchPage():({system:systemPage,runs:runPage,validation:validationPage,environment:environmentPage,harness:harnessPage,experiments:experimentPage}[page])();
 const timeline=$('.history-grid');if(timeline)timeline.style.gridTemplateColumns=`112px repeat(${Number(timeline.dataset.columns)},178px)`;
 showDetail(selection?.kind||'system',selection?.key||current().id);
 inspector(sessionStorage.getItem('bf-lab-inspector-'+page)==='true');persist();
 requestAnimationFrame(()=>{const stored=viewStates.get(location.hash);if($('.history-scroll'))$('.history-scroll').scrollLeft=prior?.history??stored?.history??$('.history-scroll').scrollWidth;$('#navigation').scrollTop=prior?.nav??stored?.nav??0;const target=prior?.y??stored?.y??window.history.state?.labScroll??0;window.scrollTo({top:target,behavior:'instant'});document.documentElement.dataset.scrollDebug=JSON.stringify({target,y:scrollY,height:document.documentElement.scrollHeight,stored,prior});});
 if(page==='harness')loadMethodFacts(selectedMethodOwner||project.owner);
}
async function loadMethodFacts(owner){if(methodFacts.has(owner))return;methodFacts.set(owner,null);try{const v=await req('/api/design-repository/trace?'+new URLSearchParams({project:project.id,owner:project.owner,session:owner,limit:100}));const manifest=data.methods.find(m=>m.owner===owner);methodFacts.set(owner,v.records.filter(r=>r.type==='repository_controller_loaded'&&r.harness_id===manifest?.harness_id).at(-1)||{});if(page==='harness'&&(selectedMethodOwner||project.owner)===owner)render();}catch{methodFacts.set(owner,{});}}
function modal(title,html){$('#viewer-title').textContent=title;$('#viewer-body').innerHTML=html;if(!$('#viewer').open)$('#viewer').showModal();}
async function showTrace(owner,after=null) {
 const args={project:project.id,owner:project.owner,session:owner,limit:100};if(after!=null)args.after=after;
 const v=await req('/api/design-repository/trace?'+new URLSearchParams(args));traceCursor[owner]=v.cursor;
 const text=kind=>({repository_controller_loaded:'实际加载配置',user_message:'用户要求',tool_execution_end:'工具结果',message:'公开对话',conversation_status:'会话状态',repository_turn_finished:'运行结束'}[kind]||kind);
 modal(roleName(owner)+' · 公开对话',`<div class="trace-view"><div class="tabs"><button data-trace="${owner}" data-trace-start="1">从会话开头</button><button data-trace="${owner}">最近记录</button><button data-trace="${owner}" data-trace-after="${v.cursor}" ${v.records.length?'':'disabled'}>下一段</button></div><p class="muted">${v.records.length} 条公开记录</p>${v.records.map(r=>`<details class="trace-record" ${r.text&&r.role==='assistant'?'open':''}><summary>${stamp(r.time)} · ${esc(r.role||text(r.type))}${r.tool?' · '+esc(r.tool):''}${r.is_error?' · 执行错误':''}</summary>${r.text?`<p class="public-text">${esc(readable(r.text))}</p>`:''}${r.prompt?`<details><summary>实际系统提示词</summary><pre>${esc(r.prompt)}</pre></details>`:''}${r.harness_id?`<dl class="facts">${fact('方法',r.harness_id)}${fact('模型',typeof r.model==='string'?r.model:JSON.stringify(r.model))}</dl>`:''}${r.tool_calls?.length?`<details><summary>工具调用参数 · ${r.tool_calls.length} 项</summary>${json(r.tool_calls)}</details>`:''}${r.result?`<details><summary>工具返回</summary>${json(r.result)}</details>`:''}${r.error?`<p>${esc(valueText(r.error))}</p>`:''}</details>`).join('')||empty('这段没有更多公开记录')}</div>`);
}
function imageViewer(url,label){
 viewerState={scale:1,fit:1,x:0,y:0,url,label};modal(label,`<div class="image-controls"><button data-image="fit">适屏</button><button data-image="one">100%</button><button data-image="out" aria-label="缩小图纸">−</button><output id="image-scale">适屏</output><button data-image="in" aria-label="放大图纸">＋</button><label>定位 <input id="image-find" placeholder="器件或网络，如 U1、GND" aria-label="在图纸中定位器件或网络"></label><button data-image="find">查找</button><span id="image-location" role="status"></span><a href="${url}" target="_blank" rel="noopener">原图 ↗</a></div><div class="image-stage" tabindex="0" aria-label="图纸，可拖动和平移，方向键移动"><img id="engineering-image" src="${url}" alt="${esc(label)}" draggable="false"></div>`);
 const img=$('#engineering-image'),stage=$('.image-stage');const loaded=()=>{if(!viewerState||!img.naturalWidth)return;viewerState.width=img.naturalWidth;viewerState.height=img.naturalHeight;fitImage();};img.onload=loaded;if(img.complete)loaded();img.onerror=()=>{if($('#image-location'))$('#image-location').textContent='图纸读取失败，请重试';};
 let drag=null;stage.onpointerdown=e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,px:viewerState.x,py:viewerState.y};stage.setPointerCapture(e.pointerId);stage.classList.add('dragging');};stage.onpointermove=e=>{if(drag&&viewerState){viewerState.x=drag.px+e.clientX-drag.x;viewerState.y=drag.py+e.clientY-drag.y;updateImage();}};stage.onpointerup=()=>{drag=null;stage.classList.remove('dragging');};
 stage.onwheel=e=>{e.preventDefault();zoomImage(e.deltaY>0?.85:1.18,e.clientX-stage.getBoundingClientRect().left,e.clientY-stage.getBoundingClientRect().top);};
 stage.onkeydown=e=>{const moves={ArrowLeft:[32,0],ArrowRight:[-32,0],ArrowUp:[0,32],ArrowDown:[0,-32]};if(moves[e.key]){e.preventDefault();viewerState.x+=moves[e.key][0];viewerState.y+=moves[e.key][1];updateImage();}if(e.key==='+'||e.key==='=')zoomImage(1.25);if(e.key==='-')zoomImage(.8);};
}
function updateImage(){const s=viewerState;if(!s||!$('#engineering-image'))return;const img=$('#engineering-image');img.style.width=s.width+'px';img.style.height=s.height+'px';img.style.transform=`translate(${s.x}px,${s.y}px) scale(${s.scale})`;$('#image-scale').textContent=Math.round(s.scale*100)+'%';}
function fitImage(){const s=viewerState,stage=$('.image-stage');if(!s?.width||!stage)return;s.fit=Math.min((stage.clientWidth-32)/s.width,(stage.clientHeight-32)/s.height);s.scale=s.fit;s.x=(stage.clientWidth-s.width*s.scale)/2;s.y=(stage.clientHeight-s.height*s.scale)/2;updateImage();}
function zoomImage(factor,cx,cy){const s=viewerState,stage=$('.image-stage');if(!s?.width||!stage)return;cx??=stage.clientWidth/2;cy??=stage.clientHeight/2;const next=Math.max(.02,Math.min(12,s.scale*factor));s.x=cx-(cx-s.x)*next/s.scale;s.y=cy-(cy-s.y)*next/s.scale;s.scale=next;updateImage();}
async function locateInImage(){const s=viewerState,q=$('#image-find')?.value.trim();if(!s||!q)return;const status=$('#image-location');if(!/\.svg(?:\?|$)/.test(s.url)&&!s.url.includes('svg')){status.textContent='此预览没有文字索引';return;}if(!s.svg){const r=await fetch(s.url);if(!r.ok)throw Error('图纸读取失败');s.svg=new DOMParser().parseFromString(await r.text(),'image/svg+xml');}const match=[...s.svg.querySelectorAll('text')].find(n=>n.textContent.trim().toLowerCase()===q.toLowerCase());if(!match){status.textContent='图中未找到 '+q;return;}const x=parseFloat(match.getAttribute('x')),y=parseFloat(match.getAttribute('y'));if(!Number.isFinite(x)||!Number.isFinite(y)){status.textContent='已找到文字，当前图元没有定位坐标';return;}const vb=s.svg.documentElement.getAttribute('viewBox')?.split(/[ ,]+/).map(Number)||[0,0,s.width,s.height];const px=(x-vb[0])*s.width/vb[2],py=(y-vb[1])*s.height/vb[3];const stage=$('.image-stage');s.scale=Math.max(s.fit,1);s.x=stage.clientWidth/2-px*s.scale;s.y=stage.clientHeight/2-py*s.scale;updateImage();status.textContent='已定位 '+q;}
async function showPreview(name){const p=sourcePreview(name);if(!p){notify('此候选没有来源一致的预览');return;}imageViewer(previewURL(p),p.label||name);}
async function showFile(path,options={}) {
 const selected=options.domain?data.domain_commits.find(d=>d.id===options.domain):options.system?data.systems.find(s=>s.id===options.system):current(),ref=options.job?selected.jobs?.[options.job]?.artifacts?.[path]:selected?.files?.[path];
 if(!ref){notify('文件不在所选版本中');return;}const url=fileURL(path,{...(options.domain?{domain_commit:options.domain}:{}),...(options.system?{system:options.system}:{}),...(options.job?{job:options.job}:{})});
 if(/\.(png|svg|jpg|webp)$/i.test(path)){imageViewer(url,path);return;}
 if(/\.(zip|hex|bin|elf|step|stl|raw)$/i.test(path)){modal(path,`<div class="file-view"><h3>${esc(path)}</h3><p>${Number(ref.bytes).toLocaleString()} 字节</p><a class="button-primary" href="${url}" download>下载原生文件</a><details><summary>来源摘要</summary><p class="id">${esc(ref.sha256)}</p></details></div>`);return;}
 const response=await fetch(url);if(!response.ok)throw Error('文件完整性读取失败');modal(path,`<pre>${esc(await response.text())}</pre>`);
}
async function showDiff(path) {
 const s=current(),parent=parentOf(s);const read=async version=>{if(!version?.files[path])return '此版本没有该文件';const r=await fetch(fileURL(path,{system:version.id}));if(!r.ok)throw Error('版本文件读取失败');return r.text();};
 if(!/\.(c|h|json|py|cir|md|txt|csv)$/i.test(path)){await showFile(path);return;}
 const [before,after]=await Promise.all([read(parent),read(s)]);modal(path+' · 版本比较',`<div class="diff-view"><section><h3>${esc(parent?systemTitle(parent):'父版')}</h3><pre>${esc(before)}</pre></section><section><h3>${esc(systemTitle(s))}</h3><pre>${esc(after)}</pre></section></div>`);
}
function showCAD(){const job=Object.entries(current().jobs).find(([,j])=>j.artifacts?.['project-preview-mesh.json']);if(!job){notify('本版没有匹配的 STEP 派生网格');return;}const url='/model-viewer.html?'+new URLSearchParams({repository_project:project.id,repository_owner:project.owner,repository_system:current().id,repository_job:job[0],repository_path:'project-preview-mesh.json',mesh:'1'});modal('CAD · 本版三维模型',`<iframe title="原生 CAD 三维预览" src="${url}"></iframe>`);}
function downloadRecord(kind,key){const v=getSelection(kind,key);if(!v)return;const url=URL.createObjectURL(new Blob([JSON.stringify({system_commit:current().id,...v},null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=(v.id||key)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function showGateReport(key){const g=getSelection('gate',key),info=gateInfo(g);modal(g.label+' · 当前版本检查报告',`<article class="gate-report"><div class="result-heading"><h2>${esc(g.label)}</h2>${badge(g.status)}</div><p>${esc(info.scope)}</p>${notesList(info.notes)}${metricsList(info.metrics)}<dl class="facts">${fact('系统候选',current().id)}${fact('检查回执',g.validation_id||g.reused_from||'冻结基线')}${fact('输入摘要',g.input_fingerprint)}</dl><button data-record-download="gate" data-record-key="${key}">下载这项检查记录</button><details><summary>完整检查数据</summary>${json(g.findings||g)}</details></article>`);}
async function refresh() {
 if(busy||!project)return;busy=true;$('#refresh').disabled=true;
 try{const next=await req('/api/design-repository?'+new URLSearchParams({project:project.id,owner:project.owner}));data=next;project=data.project;if(!systemId||!data.systems.some(s=>s.id===systemId))systemId=project.submitted;
  const studio=location.port===String(data.environment.port)?'http://127.0.0.1:'+data.original_demo_port+'/':'/';$('#studio-home').href=studio;$('#studio-link').href=studio;
  $('#workspace-note').textContent='V2 :'+data.environment.port+' · 稳定 Demo :'+data.original_demo_port;$('#sync').textContent='读取于 '+new Date(data.updated*1000).toLocaleTimeString('zh-CN',{hour12:false});$('#sync').classList.remove('offline');$('#agent-count').textContent=data.states.filter(s=>s.status==='RUNNING').length+' 个 Agent 执行中';render();
 }catch(e){$('#sync').textContent='连接中断 · 保留上次视图';$('#sync').classList.add('offline');notify(e.message);if(!data)$('#content').innerHTML=empty('暂时无法读取项目，请刷新重试。');}finally{busy=false;$('#refresh').disabled=false;}
}
document.addEventListener('click',async event=>{
 const a=event.target.closest('[data-page]');if(a){event.preventDefault();go(a.dataset.page);return;}
 const n=event.target.closest('button,[data-cad]');if(!n)return;
 try{
  if(n.dataset.jump){go(n.dataset.jump,n.dataset.object);return;}
  if(n.dataset.kind){selectObject(n.dataset.kind,n.dataset.key);return;}
  if(n.dataset.preview){await showPreview(n.dataset.preview);return;}
  if('cad' in n.dataset){showCAD();return;}
  if(n.dataset.file){await showFile(n.dataset.file,{domain:n.dataset.domain,system:n.dataset.system});return;}
  if(n.dataset.jobFile){await showFile(n.dataset.jobFile,{job:n.dataset.job,system:n.dataset.system});return;}
  if(n.dataset.diff){await showDiff(n.dataset.diff);return;}
  if(n.dataset.gateReport){showGateReport(n.dataset.gateReport);return;}
  if(n.dataset.recordDownload){downloadRecord(n.dataset.recordDownload,n.dataset.recordKey);return;}
  if(n.dataset.copy){await navigator.clipboard.writeText(n.dataset.copy);notify('已复制完整身份');return;}
  if(n.dataset.trace){await showTrace(n.dataset.trace,n.dataset.traceStart==='1'?0:n.dataset.traceAfter!=null?Number(n.dataset.traceAfter):null);return;}
  if(n.dataset.detail){detailMode=n.dataset.detail;showDetail(selection?.kind||'system',selection?.key||current().id);return;}
  if(n.dataset.history){historyFilter=n.dataset.history;historyAll=false;render();return;}
  if('historyMore' in n.dataset){historyAll=!historyAll;render();return;}
  if(n.dataset.filter){validationFilter=n.dataset.filter;if(page!=='validation')go('validation',current().id);else render();return;}
  if(n.dataset.round){systemId=n.dataset.round;usageScope='round';related=null;route('runs',null);return;}
  if(n.dataset.session){usageScope='session';usageOwner=n.dataset.session;related=null;go('runs');return;}
  if(n.dataset.methodOwner){selectedMethodOwner=n.dataset.methodOwner;selection=null;render();return;}
  if('clearSearch' in n.dataset){query='';render();$('#search').focus();return;}
  if(n.dataset.image){if(n.dataset.image==='fit')fitImage();else if(n.dataset.image==='in')zoomImage(1.25);else if(n.dataset.image==='out')zoomImage(.8);else if(n.dataset.image==='one')zoomImage(1/viewerState.scale);else await locateInImage();}
 }catch(e){notify(e.message);}
});
document.addEventListener('change',event=>{const n=event.target;if(n.id==='usage-scope'){usageScope=n.value;related=null;render();}if(n.id==='usage-owner'){usageOwner=n.value;render();}});
$('#refresh').onclick=refresh;$('#adopted').onclick=()=>selectObject('system',project.adopted);
$('#inspector-close').onclick=()=>{inspector(false);$('#inspector-toggle').focus();};
$('#inspector-toggle').onclick=()=>inspector($('#inspector').hidden);
$('#viewer-close').onclick=()=>$('#viewer').close();$('#viewer').addEventListener('close',()=>{viewerState=null;$('#viewer-body').replaceChildren();});
$('#candidate-select').onchange=e=>{systemId=e.target.value;selection=null;query='';route(page,null);};
$('#search').oninput=e=>{query=e.target.value;render();};$('#search-clear').onclick=()=>{query='';render();$('#search').focus();};
$('#project').onchange=async e=>{const index=await req('/api/design-repository/projects');project=index.projects.find(p=>p.id===e.target.value);systemId=null;selection=null;query='';window.history.replaceState(null,'','#system');await refresh();};
function navigation(open){shell.classList.toggle('navigation-hidden',!open);$('#navigation').hidden=!open;$('#navigation-toggle').setAttribute('aria-expanded',String(open));$('#navigation-toggle').setAttribute('aria-label',open?'收起对象栏':'展开对象栏');localStorage.setItem('bf-lab-navigation',open?'open':'closed');}
$('#navigation-toggle').onclick=()=>navigation($('#navigation').hidden);
const resize=$('#navigation-resize');let resizing=false;
function navWidth(width){width=Math.max(184,Math.min(280,width));document.documentElement.style.setProperty('--nav',width+'px');resize.setAttribute('aria-valuenow',String(width));localStorage.setItem('bf-lab-nav-width',String(width));}
resize.onpointerdown=e=>{resizing=true;resize.setPointerCapture(e.pointerId);};resize.onpointermove=e=>{if(resizing)navWidth(e.clientX-12);};resize.onpointerup=()=>{resizing=false;};resize.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();navWidth(Number(resize.getAttribute('aria-valuenow'))+(e.key==='ArrowRight'?8:-8));}};
navWidth(Number(localStorage.getItem('bf-lab-nav-width'))||216);navigation(localStorage.getItem('bf-lab-navigation')!=='closed');
window.addEventListener('popstate',()=>{selection=null;render(false);});window.addEventListener('hashchange',()=>render(false));
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('#search').focus();}if(e.key==='Escape'&&!$('#viewer').open&&!$('#inspector').hidden)inspector(false);if(e.key==='Enter'&&e.target.id==='image-find')locateInImage();});
try{const index=await req('/api/design-repository/projects');project=index.projects[0];if(project){try{const saved=JSON.parse(sessionStorage.getItem('bf-lab-context-'+project.id)||'{}');({systemId,selection,usageScope='round',usageOwner='',selectedMethodOwner='',historyFilter='system',historyAll=false,validationFilter='all'}=saved);}catch{}$('#project').innerHTML=index.projects.map(p=>`<option value="${p.id}">${esc(p.title)}</option>`).join('');await refresh();}else $('#content').innerHTML=empty('尚未导入项目');}catch(e){$('#content').innerHTML=empty(e.message);$('#sync').textContent='连接中断';}
}
