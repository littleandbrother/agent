/* Pure presentation helpers. No metric thresholds or acceptance decisions. */
(function(root){
  const key=r=>r.case_id?'case:'+r.case_id+':'+r.case_version:'';
  function choices(snapshot){
    if(snapshot.scope_options)return snapshot.scope_options;
    const cases=new Map();
    for(const r of snapshot.results||[])if(key(r)&&!cases.has(key(r)))cases.set(key(r),{id:key(r),label:(r.case_title||r.case_id)+' · '+r.case_version});
    return [...(snapshot.candidate?[{id:'candidate',label:snapshot.candidate.label}]:[]),...(snapshot.revision!=null?[{id:'assembly',label:'装配 v'+snapshot.revision+' · 适用成果'}]:[]),
      {id:'session',label:'全部记录 · 含历史与独立运行'},...cases.values()];
  }
  function scoped(snapshot,selection){
    if(!selection||selection==='session')return {...snapshot,selectedScope:'session'};
    if(selection==='candidate'&&snapshot.candidate){
      const design=snapshot.candidate.design_id;
      return {...snapshot,selectedScope:selection,files:snapshot.files.filter(f=>f.candidate_id===design),
        results:snapshot.results.filter(r=>r.candidate_id===design),
        verdict:snapshot.candidate.verdict,blockers:[]};
    }
    if(selection==='latest'){
      const ids=new Set(snapshot.latest_file_ids||[]),rows=new Set(snapshot.latest_result_ids||[]);
      return {...snapshot,selectedScope:selection,files:snapshot.files.filter(f=>ids.has(f.id)),
        results:snapshot.results.filter(r=>rows.has(r.id)).map(r=>({...r,files:r.files.filter(f=>ids.has(f.id)),presentations:(r.presentations||[]).filter(v=>ids.has(v.file_id))})),
        verdict:null,blockers:[]};
    }
    const files=(snapshot.files||[]).filter(f=>selection==='assembly'?['current','reused'].includes(f.applicability?.state):key(f)===selection||snapshot.results.some(r=>key(r)===selection&&r.files.some(x=>x.id===f.id)));
    const ids=new Set(files.map(f=>f.id));
    const results=snapshot.results.filter(r=>selection==='assembly'?r.files.some(f=>ids.has(f.id)):key(r)===selection)
      .map(r=>({...r,files:r.files.filter(f=>ids.has(f.id)),presentations:(r.presentations||[]).filter(v=>ids.has(v.file_id))}));
    return {...snapshot,results,files,verdict:selection==='assembly'?snapshot.verdict:null,
      blockers:selection==='assembly'?snapshot.blockers:[],selectedScope:selection};
  }
  function preferredScope(snapshot){
    if(snapshot.preferred_scope&&choices(snapshot).some(x=>x.id===snapshot.preferred_scope))return snapshot.preferred_scope;
    if(snapshot.scope_options?.some(x=>x.id==='latest'))return 'latest';
    const dossier=typeof window!=='undefined'?window.ProductEvidence?.preferred(snapshot):'';
    if(dossier)return dossier;
    const current=(snapshot.files||[]).some(f=>f.integrity&&['current','reused'].includes(f.applicability?.state));
    const options=choices(snapshot);
    if(current&&options.some(x=>x.id==='assembly'))return 'assembly';
    // Explicitly published reference cases remain labelled as such. When an
    // assembly has no readable output, do not open an empty assembly by default.
    const latest=(snapshot.results||[]).filter(key).reduce((last,r)=>!last||(r.created||0)>(last.created||0)?r:last,null);
    return latest?key(latest):options[0].id;
  }
  function scopeLabel(snapshot){return choices(snapshot).find(c=>c.id===snapshot.selectedScope)?.label||'全部记录';}
  function previewLabels(files){
    const counts=new Map();for(const f of files)counts.set(fileLabel(f),(counts.get(fileLabel(f))||0)+1);
    return files.map(f=>({id:f.id,label:fileLabel(f)+(counts.get(fileLabel(f))>1?' · '+f.name:'')}));
  }
  function findings(snapshot){
    return snapshot.results.filter(r=>r.design_status==='FAIL'||r.status==='FAILED'||r.predicted_design_status==='unsatisfied').map(r=>({id:r.id,title:r.label||r.kind,text:r.scope||r.error||'检查未通过',state:'failed'}));
  }
  function hero(snapshot){
    const items=snapshot.results.flatMap(r=>(r.presentations||[]).filter(v=>['image','model','mesh','video'].includes(v.kind)).map(v=>({r,v,f:r.files.find(f=>f.id===v.file_id)}))).filter(x=>x.f?.integrity);
    const rank=x=>(x.r.kind==='blender'?0:x.r.kind==='product-model'?10:x.r.domain==='mechanical'?20:40)+({image:0,model:1,mesh:2,video:3}[x.v.kind])+(/installation|assembled|overview|preview|外观|安装/i.test(x.f.name)?-1:0);
    return items.sort((a,b)=>rank(a)-rank(b))[0]||null;
  }
  function verdict(r){if(r.reference_only)return '历史参考 · 待适配';return r.design_status==='FAIL'?'未通过':r.status==='FAILED'?'执行失败':r.applicability?.state==='stale'?'需要重验':r.predicted_design_status==='unsatisfied'?'模型内未达到目标':r.design_status==='insufficient_evidence'?'依据不足':r.design_status==='PASS'?(r.source_type==='eda'?'该项原生检查通过':'该项计算通过'):['RUNNING','QUEUED'].includes(r.status)?'进行中':'查看验证范围'}
  function fileLabel(f){if(f.label)return f.label;const n=f.name.toLowerCase();return n==='project-preview-mesh.json'?'CAD · 三维装配':/^preview\./.test(n)?'整体外观':/^back\./.test(n)?'背部视图':/^side\./.test(n)?'侧面视图':/mechanism-door-open/.test(n)?'开门结构':/mechanism/.test(n)?'机构细节':/schematic/.test(n)?'电路原理图':/pcb-combined/.test(n)?'PCB 布线':/pcb-top/.test(n)?'顶层布线':/pcb-bottom/.test(n)?'底层布线':/exploded/.test(n)?'爆炸视图':/inside|internal/.test(n)?'内部结构':/installation/.test(n)?'安装视图':/\.mp4$/.test(n)?'动作演示':/\.glb$/.test(n)?'三维模型':/report|door-case/.test(n)&&/\.pdf$/.test(n)?'技术报告':f.name;}
  const api={choices,scoped,scopeLabel,preferredScope,previewLabels,findings,hero,verdict,fileLabel,key};
  if(typeof module!=='undefined')module.exports=api;else root.StudioModel=api;
})(typeof window!=='undefined'?window:this);

/* Public task/check/version presentation. Acceptance remains a backend fact. */
(function(root){
  const states={PASS:{label:'已通过',icon:'✓',tone:'good'},FAIL:{label:'未通过',icon:'×',tone:'bad'},RUNNING:{label:'正在执行',icon:'◉',tone:'active'},WAITING_CHECK:{label:'待验收',icon:'◌',tone:'pending'},NOT_CHECKED:{label:'未检查',icon:'○',tone:'idle'},NOT_STARTED:{label:'未开始',icon:'○',tone:'idle'},UNEVALUABLE:{label:'无法评价',icon:'!',tone:'warn'},BLOCKED:{label:'受阻',icon:'!',tone:'warn'},STALE:{label:'修改后需复查',icon:'↻',tone:'warn'},RECHECK_REQUIRED:{label:'需复查',icon:'↻',tone:'warn'},UNKNOWN:{label:'状态待核对',icon:'?',tone:'warn'}};
  const causes=[['agent_judgment','Agent 判断错误'],['tool_execution','工具执行错误'],['model_domain','模型不适用'],['missing_information','资料不足'],['infeasible_task','任务本身不可实现'],['checker_judgment','检查器判断错误']];
  const sections=[['definition','需求与依据'],['circuit','电路与 PCB'],['firmware','固件与通信'],['power','供能与任务验证'],['mechanical','机械与装配'],['delivery','同版本交付']];
  function sectionFor(id){
    if(/delivery|package|manifest/.test(id))return 'delivery';
    if(/geometry|mechanic|dimension|layer|fit|dynamic/.test(id))return 'mechanical';
    if(/firmware|protocol|buffer|register|timing|event_logic|mcu|communication/.test(id))return 'firmware';
    if(/schematic|bom|pins|pcb|afe|interface/.test(id))return 'circuit';
    if(/source|power|energy|coupling|rectifier|load|readout|charge|cold|sensor/.test(id))return 'power';
    return 'definition';
  }
  function state(status){return states[status]||states.UNKNOWN;}
  function rollup(children){
    if(!children.length)return 'NOT_CHECKED';
    const s=children.map(c=>c.status);
    if(s.includes('RUNNING'))return 'RUNNING';
    if(s.includes('FAIL'))return 'FAIL';
    if(s.every(x=>x==='PASS'))return 'PASS';
    if(s.some(x=>['STALE','RECHECK_REQUIRED'].includes(x)))return 'RECHECK_REQUIRED';
    if(s.some(x=>['BLOCKED','UNEVALUABLE','UNKNOWN'].includes(x)))return 'BLOCKED';
    return 'WAITING_CHECK';
  }
  function diagnosis(issue){
    const c=issue.classification||issue.cause;
    const found=causes.find(([id,label])=>c===id||c===label);
    const confirmed=issue.classification_confirmed===true&&!!issue.artifact;
    return {label:found?found[1]:'原因尚未确认',confirmed,attribution:confirmed?'独立证据确认':found?'当前解释 · 待确认':'未归因',phenomenon:issue.summary||issue.error||'查看原始问题记录',evidence:issue.artifact||null};
  }
  function activeAction(events,execution,connected=true){
    if(!connected||!['RUNNING','STARTING'].includes(execution?.status))return null;
    const starts=new Map();
    for(const row of events||[]){const e=row.data||row;
      if(e.type==='tool_execution_start')starts.set(e.toolCallId||e.tool_call_id||e.tool_name||e.toolName,{...e,time:row.time});
      if(e.type==='tool_execution_end')starts.delete(e.toolCallId||e.tool_call_id||e.tool_name||e.toolName);
      if(['turn_complete','turn_failed'].includes(e.type))starts.clear();
    }
    const e=[...starts.values()].at(-1);if(!e)return {label:execution.status==='STARTING'?'准备原会话':'Agent 正在分析',task:null,section:null};
    const name=e.toolName||e.tool_name||e.name||'操作',arg=e.args||e.arguments||{};
    const explicit=e.task_id||arg.task_id||arg.gate_id||null;
    const text=name+' '+JSON.stringify(arg);
    // This is only a location hint for an actual running action, never a cause
    // diagnosis, fabricated permanent task or acceptance decision.
    const section=/firmware|nrf|stm32|\.c\b|s132|sdk/i.test(text)?'firmware':/pcb|schematic|eda/i.test(text)?'circuit':/cad|mechanic|step/i.test(text)?'mechanical':/spice|power|energy/i.test(text)?'power':/deliver|manifest|package/i.test(text)?'delivery':null;
    const names={bash:'执行命令',read:'读取资料',edit:'修改工程',write:'写入工程',bf_engineering:'工程操作',bf_eda:'本地 EDA 操作',bf_skills:'读取专业方法',bf_references:'核对参考资料'};
    return {label:names[name]||name,tool:name,task:explicit,section,time:e.time,location_inferred:!explicit};
  }
  function project(data,events=[],connected=true){
    const acceptance=data.acceptance,version=data.assembly_revision!=null?'装配 v'+data.assembly_revision:data.design_lab?.current_design?.slice(0,14)||'尚无冻结版本';
    const gates=acceptance?.functional_gates||[];
    const fresh=connected&&data.fresh!==false;
    const action=activeAction(events,data.execution,fresh);
    const issues=(acceptance?.issues||[]).filter(x=>x.state!=='CLOSED').map(x=>({...x,diagnosis:diagnosis(x)}));
    const leaves=gates.map(g=>({id:g.id,label:g.label,section:sectionFor(g.id),
      status:(!fresh&&g.status==='PASS')?'UNKNOWN':(acceptance.current_sources_valid!==true&&g.status==='PASS')?'STALE':g.status||'NOT_CHECKED',
      recorded_status:g.status,version,evidence:g.evidence,condition:'对应范围的独立检查通过，且输入与版本仍有效。',
      dependencies:g.dependencies||[],issues:issues.filter(i=>i.gate_id===g.id),required:true}));
    if(!gates.length&&data.design_lab){
      const contract=data.design_lab.contract||{},submission=data.design_lab.submission;
      const verdict=submission?.acceptance,checks=verdict?.gates||verdict?.checks||[];
      const rows=Array.isArray(checks)?checks:Object.entries(checks).map(([id,v])=>({id,...(typeof v==='object'?v:{status:v})}));
      for(const g of rows){const id=g.id||g.name;leaves.push({id,label:g.label||id,section:sectionFor(id),status:fresh&&verdict?.passed===true&&(g.status==='PASS'||g.passed===true)?'PASS':g.status==='FAIL'?'FAIL':'NOT_CHECKED',version,evidence:null,condition:'同设计快照的公开验收回执。',required:true,issues:[]})}
      if(!rows.length)leaves.push({id:'design-checks',label:contract.title||'当前设计的独立验收',section:'definition',status:'NOT_CHECKED',condition:'需要公开且与当前设计绑定的独立检查结果。',required:true,version,issues:[]});
    }
    if(!leaves.length)leaves.push({id:'define-scope',label:'明确任务和通过条件',section:'definition',status:'NOT_CHECKED',condition:'尚未找到结构化验收范围；不根据聊天文字判定完成。',required:true,version,issues:[]});
    const groups=sections.map(([id,label])=>({id,label,children:leaves.filter(l=>l.section===id)})).filter(g=>g.children.length);
    for(const g of groups){g.status=rollup(g.children);g.active=!!action&&(action.section===g.id||g.children.some(x=>x.id===action.task));}
    const activity=action?{id:'current-action',label:action.label,section:action.section||'definition',status:'RUNNING',condition:'实际活动；执行结束仍需验收。',version,action,issues:[],required:false}:null;
    const full=!!acceptance?.full_product_passed&&acceptance.current_sources_valid===true&&fresh&&leaves.every(x=>x.status==='PASS')&&issues.length===0;
    const counts={passed:leaves.filter(l=>l.status==='PASS').length,total:leaves.length,running:action?1:0,failed:leaves.filter(l=>l.status==='FAIL').length,pending:leaves.filter(l=>!['PASS','FAIL'].includes(l.status)).length};
    return {owner:data.owner,version,groups,leaves,activity,issues,counts,
      status:full?'PASS':action?'RUNNING':rollup(leaves)==='PASS'?'WAITING_CHECK':rollup(leaves),
      full_product_passed:full,physical:data.physical_validation||'NOT_TESTED',phase:data.phase,
      execution:data.execution,checked_at:data.checked_at,connected:fresh,
      versions:versionGraph(data.versions||[]),design_lab:data.design_lab};
  }
  function versionGraph(rows){
    const byId=new Map(rows.map(r=>[r.id,r]));const depth=new Map();
    function level(id,seen=new Set()){
      if(depth.has(id))return depth.get(id);if(seen.has(id))return 0;seen.add(id);
      const p=byId.get(id)?.parent_id;const n=p&&byId.has(p)?Math.min(8,1+level(p,seen)):0;depth.set(id,n);return n;
    }
    return rows.map(r=>({...r,depth:level(r.id),explicit_parent:r.parent_id&&byId.has(r.parent_id)?r.parent_id:null,
      missing_parent:!!r.parent_id&&!byId.has(r.parent_id),link_kind:r.parent_id?'ancestry':r.timeline_predecessor?'sequence':null,
      changes:r.parent_id&&byId.has(r.parent_id)?Object.keys({...byId.get(r.parent_id).hashes,...r.hashes}).filter(k=>byId.get(r.parent_id).hashes?.[k]!==r.hashes?.[k]):[],
      adoption:r.current?(r.kind==='assembly'?'当前装配':'当前采用'):'历史版本'}));
  }
  function expanded(node,manual){return Object.prototype.hasOwnProperty.call(manual||{},node.id)?manual[node.id]:node.active||['RUNNING','FAIL','BLOCKED','UNEVALUABLE','STALE','RECHECK_REQUIRED'].includes(node.status);}
  function rollbackEligibility(model,node){
    if(!node)return {allowed:false,reason:'选择一个历史设计。'};
    if(node.current)return {allowed:false,reason:'这已经是当前版本。'};
    if(node.kind!=='design'||!node.rollback_supported)return {allowed:false,reason:'此原生工程尚无经过验证的恢复接口；当前支持只读查看历史。'};
    if(!model.connected)return {allowed:false,reason:'需先重新核对当前状态。'};
    if(['RUNNING','STARTING','STOPPING','QUEUED'].includes(model.execution?.status))return {allowed:false,reason:'需在当前执行停止的安全边界恢复。'};
    if(model.design_lab?.status==='SUBMITTED')return {allowed:false,reason:'此阶段已封存；恢复需要新的授权阶段。'};
    return {allowed:true,reason:'将记录新的采用事件，原历史与费用保留。受影响检查需复查。'};
  }
  const api={states,causes,sectionFor,state,rollup,diagnosis,activeAction,project,versionGraph,expanded,rollbackEligibility};
  if(typeof module!=='undefined')module.exports.ExecutionProgressModel=api;else root.ExecutionProgressModel=api;
})(typeof window!=='undefined'?window:this);
