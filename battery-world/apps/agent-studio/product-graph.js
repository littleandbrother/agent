/* Read-only projection of recorded product facts. No scientific verdicts here. */
(function (root) {
  const labels = {pending:'待验证',recorded:'已记录',passed:'检查通过',failed:'未通过',stale:'已失效',active:'执行中'};
  const engines = {'product-model':'产品模型',blender:'三维展示',comsol:'结构仿真',jlceda:'原理图与 PCB','event-transient':'机电瞬态','mcu-firmware':'固件构建','tinyml-nas':'TinyML / NAS'};
  const definitions = [
    ['mission','需求约定','requirements',24,256],
    ['energy','能源架构','energy',244,20], ['sensing','感知与服务','sensing',244,116],
    ['ml','TinyML 模型','ml',244,212], ['circuit','电路与通信','circuit',244,308],
    ['mechanical','机械装配','mechanical',244,404], ['firmware','固件程序','firmware',244,500],
    ['integrated','集成设计','integration',464,256],
    ['energy-check','能源可行性','verification',684,68], ['mechanical-check','模型与尺寸','verification',684,164],
    ['circuit-check','电路与接口','verification',684,260], ['firmware-check','目标固件','verification',684,356],
    ['service-check','服务与实测','verification',684,452],
    ['evidence','证据汇总','release',904,208], ['release','交付候选','release',904,352],
  ];
  const checkNames = {'required-parts':'必需部件','current-native-model':'原生模型与尺寸读回','energy-budget-screen':'日能量与储能初筛','normal-service-screen':'条件轨迹至少一次回应','native-electrical-rules':'原生电路规则','cross-domain-interfaces':'跨域接口一致性','product-electrical-verification':'真实电路功能','target-firmware-verification':'目标固件验证','hardware-measurements':'硬件测量'};
  const checkGroups = {'energy-check':['energy-budget-screen'], 'mechanical-check':['required-parts','current-native-model'], 'circuit-check':['native-electrical-rules','cross-domain-interfaces','product-electrical-verification'], 'firmware-check':['target-firmware-verification'], 'service-check':['normal-service-screen','hardware-measurements']};
  const engineNode = {'product-model':'mechanical-check',blender:'mechanical',comsol:'mechanical-check',jlceda:'circuit-check','event-transient':'energy-check','mcu-firmware':'firmware-check','tinyml-nas':'ml'};
  const nodeEngines = {energy:['event-transient'],mechanical:['product-model','blender','comsol'],circuit:['jlceda'],firmware:['mcu-firmware'],ml:['tinyml-nas'],'energy-check':['event-transient'],'mechanical-check':['product-model','comsol'],'circuit-check':['jlceda'],'firmware-check':['mcu-firmware'],'service-check':['event-transient']};
  const text = v => typeof v==='string'?v:JSON.stringify(v);
  const time = v => Number.isFinite(Number(v))?Number(v):0;
  function checkState(c) {
    if(c.stale)return 'stale';
    if(c.status==='NOT_EVALUATED'||c.passed===undefined||c.passed===null)return 'pending';
    if(c.passed===true)return 'passed';
    if(c.id==='current-native-model'&&!c.job_id)return 'pending';
    return 'failed';
  }
  function jobState(j) {
    if(j.stale)return 'stale';
    if(j.status==='FAILED'||[j.result?.computational_checks_passed,j.result?.digital_checks_passed,j.result?.numerical_checks_passed].includes(false))return 'failed';
    if(['RUNNING','QUEUED'].includes(j.status))return 'active';
    return j.status==='SUCCEEDED'?'recorded':'pending';
  }
  function matches(job,record) {
    if(!record||record.source_valid===false||job.stale)return false;
    const bound=job.assembly;
    return bound?.revision===record.revision && !!record.hashes?.physical_hash && bound.hashes?.physical_hash===record.hashes.physical_hash;
  }
  function build(current, revision) {
    const product=current?.product||{}, assembly=product.assembly||{}, versions=assembly.revisions||[];
    const record=revision?versions.find(r=>r.revision===Number(revision)):assembly.current;
    const isCurrent=!!record&&record.revision===assembly.current?.revision&&record.hashes?.physical_hash===assembly.current?.hashes?.physical_hash;
    const valid=record?.source_valid!==false;
    const proposal=isCurrent||!record?product.proposal:(product.records||[]).filter(r=>r.kind==='proposal'&&time(r.created)<=time(record.created)).at(-1);
    const p=proposal?.payload||{}, a=record?.payload||{}, jobs=product.engineering||[];
    const bound=jobs.filter(j=>matches(j,record));
    const checks=isCurrent&&valid?(assembly.checks||[]).map(c=>({...c,label:checkNames[c.id]||c.id,state:checkState(c)})):[];
    const nodes=definitions.map(([id,title,group,x,y])=>({id,title,group,x,y,status:'pending',summary:'尚无记录',facts:[],checks:[],jobs:[],version:record?'装配 v'+record.revision:'未建立装配'}));
    const get=id=>nodes.find(n=>n.id===id);
    function put(id,facts,summary){const n=get(id);n.facts=facts.filter(Boolean).map(text);if(n.facts.length){n.status=valid?'recorded':'stale';n.summary=summary||n.facts[0]}}
    put('mission',[p.purpose,...(a.requirements||[])],p.service||p.purpose);
    get('mission').version=proposal?'方案 v'+proposal.revision:'未形成方案';
    if(proposal?.stale)get('mission').status='stale';
    put('energy',[p.energy,a.energy&&JSON.stringify(a.energy,null,2)],a.energy?.capacitance_f!==undefined?'储能 '+a.energy.capacitance_f+' F · 参数已记录':p.energy);
    put('sensing',[p.service],p.service);
    put('circuit',a.interfaces||[],a.interfaces?.length+' 项接口约定');
    put('mechanical',(a.parts||[]).map(part=>part.name+' · '+(part.geometry?.size_mm||[]).join(' × ')+' mm'),a.parts?.length+' 个部件 · 尺寸以 mm 记录');
    put('integrated',[a.title,...(a.assumptions||[])],a.title);
    for(const n of nodes){
      n.jobs=bound.filter(j=>(nodeEngines[n.id]||[]).includes(j.engine));
      if(n.jobs.length&&!n.facts.length){n.status='recorded';n.summary=n.jobs.length+' 项绑定工程记录'}
      n.checks=checks.filter(c=>(checkGroups[n.id]||[]).includes(c.id));
      if(n.checks.length){
        n.status=n.checks.some(c=>c.state==='failed')?'failed':n.checks.every(c=>c.state==='passed')?'passed':'pending';
        n.summary=n.checks.filter(c=>c.state==='passed').length+' / '+n.checks.length+' 项检查通过';
      }
      if(!valid)n.status='stale';
    }
    const ml=bound.find(j=>j.engine==='tinyml-nas'&&j.result?.architecture);
    if(ml){put('ml',[JSON.stringify(ml.result.architecture,null,2),ml.result.scope], '已有模型与 NAS 记录 · 实测另查');}
    const fw=bound.find(j=>j.engine==='mcu-firmware'&&j.result?.build);
    if(fw){put('firmware',[JSON.stringify(fw.result.build,null,2),fw.result.scope],fw.result.build.target||'目标构建产物已记录');}
    put('evidence',checks.map(c=>c.label+' · '+labels[c.state]),checks.length?checks.filter(c=>c.state==='passed').length+' / '+checks.length+' 项检查通过':'尚无本版检查汇总');
    get('evidence').checks=checks;
    // Digital delivery and physical acceptance stay separate. No inferred green release.
    const delivery=isCurrent&&valid?assembly.delivery:null;
    get('release').summary=delivery?(delivery.passed?'声明的数字交付条件满足':'数字交付仍有缺项'):'尚无交付回执';
    get('release').status=delivery?.passed?'recorded':'pending';
    get('release').facts=delivery?[JSON.stringify(delivery,null,2)]:[];
    get('release').facts.push('实物验收：'+(isCurrent&&valid&&assembly.hardware_verified===true?'后端已有验证记录':'尚未验证'));
    const decisions=['energy','sensing','ml','circuit','mechanical','firmware'], validators=Object.keys(checkGroups);
    const edges=[...decisions.flatMap(id=>[{source:'mission',target:id},{source:id,target:'integrated'}]),...validators.flatMap(id=>[{source:'integrated',target:id},{source:id,target:'evidence'}]),{source:'evidence',target:'release'}];
    // Fixed lanes are explanatory workflow relationships, never inferred causal evidence.
    const events=[...(product.records||[]).filter(r=>r.kind==='proposal').map(r=>({id:'proposal-'+r.revision,time:time(r.created),title:'方案 v'+r.revision,node:'mission',state:r.stale?'stale':'recorded',detail:r.payload.title,record:r})),...versions.map(r=>({id:'assembly-'+r.revision,time:time(r.created),title:'装配 v'+r.revision,node:'integrated',state:r.source_valid===false?'stale':'recorded',revision:r.revision,detail:r.payload.title,record:r})),...jobs.map(j=>({id:j.id,time:time(j.ended||j.created),title:engines[j.engine]||j.engine,node:engineNode[j.engine]||'evidence',state:jobState(j),detail:j.status+' · '+j.id,job:j})),...(assembly.verifications||[]).map(v=>({id:'verification-'+v.id,time:time(v.created),title:'装配验证 v'+v.revision,node:'evidence',state:v.stale?'stale':v.integrity===false?'failed':'recorded',revision:v.revision,detail:v.scope||'独立验证记录',verification:v}))].filter(e=>e.time>0).sort((x,y)=>x.time-y.time||x.id.localeCompare(y.id));
    const files=(assembly.files||[]).filter(f=>f.revision===record?.revision).map(f=>({...f,url:'/api/assembly/file?session='+encodeURIComponent(current.id)+'&id='+encodeURIComponent(f.id)}));
    const artifacts=bound.flatMap(j=>(j.result?.artifacts||[]).map(f=>({...f,job_id:j.id,engine:j.engine,url:'/api/engineering/jobs/'+encodeURIComponent(j.id)+'/artifact?name='+encodeURIComponent(f.name)})));
    const previous=versions.filter(r=>r.revision<record?.revision).at(-1);
    const changes=previous?Object.keys(record.hashes||{}).filter(k=>record.hashes[k]!==previous.hashes?.[k]):[];
    return {nodes,edges,events,files,artifacts,bound,record,proposal,versions,previous,changes,isCurrent,checks,empty:!proposal&&!record,title:a.title||p.title||current?.title||'产品设计',physicalVerified:isCurrent&&valid&&assembly.hardware_verified===true};
  }
  const api={build,matches,checkState,jobState,labels,engines,checkNames,width:1116,height:606};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ProductGraph=api;
})(typeof window==='undefined'?globalThis:window);
