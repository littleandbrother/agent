/* File placement is a view of explicit task/job bindings, never an acceptance verdict. */
(function(root){
  const G=typeof module!=='undefined'&&module.exports?require('./product-graph.js'):root.ProductGraph;
  const taskMap={
    mission:['requirements','references','interfaces'],
    energy:['magnetics','mapping','spice','joint'], sensing:['receiver','direction'], ml:[],
    mechanical:['cad','drawings','clearance','presentation','magnetics','fem','convergence','mapping'],
    circuit:['circuit-selection','schematic','spice','electrical-checks','pcb','pcb-checks','manufacturing'],
    firmware:['firmware','firmware-resources','flash-guide','receiver','direction','receiver-tests'],
    'energy-check':['spice','joint','matrix'], 'mechanical-check':['clearance','fem','convergence','mapping'],
    'circuit-check':['electrical-checks','spice','pcb-checks'],
    'firmware-check':['firmware-resources','receiver-tests'], 'service-check':['matrix','system-acceptance'],
  };
  const kinds={simulation:'仿真',image:'图片',native:'原生工程',code:'代码',document:'说明与报告',data:'数据与构建'};
  const deliveryNames={missing:'待补齐',partial:'部分文件',present:'文件已登记',invalid:'完整性失败',stale:'已失效'};
  const validationNames={not_run:'未验收',passed:'验收通过',failed:'验收未通过',stale:'需重验'};
  const refLink=p=>'/api/reference-case/artifact?name='+encodeURIComponent(p);
  const ext=f=>(f.name||f.path||'').split('.').at(-1).toLowerCase();
  const key=f=>f.url;
  function kind(f){
    const e=ext(f);
    if(['png','jpg','jpeg','webp','svg','gif'].includes(e))return 'image';
    if(['mph','cir','asc','raw','spice','net'].includes(e))return 'simulation';
    if(['blend','step','stp','stl','brep','glb','gltf','epro','eprj','schdoc','pcbdoc','prjpcb','sch','pcb','kicad_pcb','kicad_sch'].includes(e))return 'native';
    if(['py','c','h','cpp','hpp','js','ts','java','sh','ino','s','ld'].includes(e)||/(^|\/)makefile$/i.test(f.name||f.path))return 'code';
    if(['md','txt','pdf','html','json','yaml','yml'].includes(e))return 'document';
    return 'data';
  }
  const unique=files=>[...new Map(files.map(f=>[key(f),f])).values()];
  function tasksFor(node,tasks){return ['integrated','evidence','release'].includes(node)?tasks:tasks.filter(t=>(taskMap[node]||[]).includes(t.id))}
  const circuitSections=[{id:'schematic',title:'电路原理图',ids:['circuit-selection','schematic','electrical-checks'],hint:'原生原理图、审查图、BOM 与电气检查'},{id:'pcb',title:'PCB 板',ids:['pcb','pcb-checks','manufacturing'],hint:'布局布线、板图、DRC、Gerber 与钻孔文件'},{id:'simulation',title:'电路仿真',ids:['spice'],hint:'SPICE 网表、波形与校准对照'}];
  function sections(tasks,referenceAssets=[]){return circuitSections.map(s=>({...s,tasks:tasks.filter(t=>s.ids.includes(t.id)),assets:unique(tasks.filter(t=>s.ids.includes(t.id)).flatMap(t=>t.assets)),references:referenceAssets.filter(f=>s.id==='schematic'?ext(f)==='schdoc':s.id==='pcb'?ext(f)==='pcbdoc':false)}))}
  function reference(source){
    const d=source.delivery||{},graph=G.build(null), listed=new Map((source.artifacts||[]).map(f=>[f.path,f]));
    const mapFile=f=>{const a=listed.get(f.path);return a?{...a,...f,name:f.path.split('/').at(-1),url:refLink(f.path),integrity:source.artifact_integrity!==false,source:'参考辅助工程 · '+(d.version||'未建立快照')}:null};
    const tasks=(d.tasks||[]).map(t=>({...t,assets:(t.files||[]).map(mapFile).filter(Boolean)}));
    const extras=(source.artifacts||[]).filter(f=>['engineering-package','engineering-guide'].includes(f.kind)).map(mapFile);
    // Literature is explicitly kept as reference material, not a completed requirements task.
    const sources=(source.artifacts||[]).filter(f=>f.path.startsWith('sources/')).map(mapFile).map(f=>({...f,referenceOnly:true,source:'论文与器件参考资料'}));
    const circuitReferences=(source.artifacts||[]).filter(f=>f.path.startsWith('circuit-reference/')).map(mapFile).map(f=>({...f,referenceOnly:true,source:'原作者参考板 · 非本版设计'}));
    const all=unique([...tasks.flatMap(t=>t.assets),...extras,...sources,...circuitReferences]);
    const simulations=(d.native_simulations||[]).map(s=>({...s,assets:(s.files||[]).map(mapFile).filter(Boolean),figureFile:s.figure?mapFile({path:s.figure}):null}));
    const nodes=graph.nodes.map(n=>{
      const ts=tasksFor(n.id,tasks);let assets=unique(ts.flatMap(t=>t.assets));
      if(n.id==='mission')assets=unique([...assets,...sources]);
      if(['integrated','evidence','release'].includes(n.id))assets=all;
      const sims=simulations.filter(s=>s.assets.some(f=>assets.some(a=>key(a)===key(f))));
      assets=unique([...assets,...sims.map(s=>s.figureFile).filter(Boolean)]);
      const checks=ts.map(t=>({label:t.label,state:source.artifact_integrity===false?'failed':t.validation_status==='passed'?'passed':t.validation_status==='failed'?'failed':t.validation_status==='stale'?'stale':'pending',scope:validationNames[t.validation_status]||'未验收'}));
      const status=source.artifact_integrity===false?'failed':ts.some(t=>['invalid','stale'].includes(t.delivery_status))?'stale':assets.some(f=>!f.referenceOnly)?'recorded':'pending';
      return {...n,status,summary:assets.length?assets.filter(f=>!f.referenceOnly).length+' 件交付物'+(assets.some(f=>f.referenceOnly)?' / '+assets.filter(f=>f.referenceOnly).length+' 件参考':'')+' · '+(checks.some(c=>c.state==='failed')?'含未通过项':'验收另查'):'尚无该部分交付物',facts:[n.id==='ml'?'本参考工程尚未声明 TinyML 任务。':d.summary||source.summary],checks,version:d.version||'参考资料',deliveryTasks:ts,assets,simulations:sims,sections:n.id==='circuit'?sections(ts,circuitReferences):[]};
    });
    return {...graph,nodes,empty:false,title:source.title||'拨动式采能产品',reference:true,sourceLabel:'参考辅助工程',snapshot:d.version||'未建立交付快照',files:all,artifacts:[],tasks,checks:[],integrity:source.artifact_integrity,physicalVerified:source.hardware_verified===true};
  }
  function session(graph,snapshot,current){
    // A stale async response or latest-only delivery inventory must not contaminate a historical graph.
    const applies=snapshot?.owner===current?.id&&snapshot?.revision===graph.record?.revision&&graph.isCurrent;
    const tasks=applies?(snapshot.tasks||[]):[];
    const files=graph.files.map(f=>({...f,name:f.name||f.source?.split('/').at(-1)||f.id,source:'装配 v'+graph.record?.revision}));
    const artifacts=graph.artifacts.map(f=>({...f,source:'装配 v'+graph.record?.revision+' · '+(G.engines[f.engine]||f.engine)}));
    const normalized=tasks.map(t=>{
      const b=t.binding;const ok=b?.revision===graph.record?.revision&&b?.physical_hash===graph.record?.hashes?.physical_hash;
      const assets=ok?files.filter(f=>(b.files||[]).some(x=>x.id===f.id&&(x.digest||x.sha256)===(f.digest||f.sha256))):[];
      if(ok)assets.push(...artifacts.filter(f=>(b.jobs||[]).some(j=>j.id===f.job_id)));
      return {...t,assets:assets.map(f=>({...f,stale:f.stale||t.delivery_status==='stale',integrity:f.integrity!==false&&t.delivery_status!=='invalid'}))};
    });
    const nodes=graph.nodes.map(n=>{
      const ts=tasksFor(n.id,normalized);
      let assets=unique([...ts.flatMap(t=>t.assets),...artifacts.filter(f=>n.jobs.some(j=>j.id===f.job_id))]);
      if(['integrated','evidence','release'].includes(n.id))assets=unique([...files,...artifacts]);
      return {...n,assets,deliveryTasks:ts,simulations:[],sections:n.id==='circuit'?sections(ts):[]};
    });
    return {...graph,nodes,files,artifacts,tasks:normalized,sourceLabel:'当前任务',snapshot:graph.record?'装配 v'+graph.record.revision:'尚未建立装配',inventoryPending:!snapshot,unboundFiles:files.filter(f=>!normalized.some(t=>t.assets.some(a=>key(a)===key(f))))};
  }
  const api={reference,session,sections,tasksFor,kind,kinds,ext,unique,deliveryNames,validationNames};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ProductDeliverables=api;
})(typeof window==='undefined'?globalThis:window);
