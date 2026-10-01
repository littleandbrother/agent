/* Pure presentation helpers. No metric thresholds or acceptance decisions. */
(function(root){
  const key=r=>r.case_id?'case:'+r.case_id+':'+r.case_version:'';
  function choices(snapshot){
    const cases=new Map();
    for(const r of snapshot.results||[])if(key(r)&&!cases.has(key(r)))cases.set(key(r),{id:key(r),label:(r.case_title||r.case_id)+' · '+r.case_version});
    return [...cases.values(),{id:'session',label:'会话成果集合 · 含历史记录'}];
  }
  function scoped(snapshot,selection){
    if(!selection||selection==='session')return snapshot;
    const results=snapshot.results.filter(r=>key(r)===selection),ids=new Set(results.flatMap(r=>r.files.map(f=>f.id)));
    return {...snapshot,results,files:snapshot.files.filter(f=>ids.has(f.id)),verdict:null,blockers:[],selectedScope:selection};
  }
  function findings(snapshot){
    return snapshot.results.filter(r=>r.design_status==='FAIL'||r.status==='FAILED'||r.predicted_design_status==='unsatisfied').map(r=>({id:r.id,title:r.label||r.kind,text:r.scope||r.error||'检查未通过',state:'failed'}));
  }
  function hero(snapshot){
    const items=snapshot.results.flatMap(r=>(r.presentations||[]).filter(v=>['image','model','mesh','video'].includes(v.kind)).map(v=>({r,v,f:r.files.find(f=>f.id===v.file_id)}))).filter(x=>x.f?.integrity);
    const rank=x=>(x.r.kind==='blender'?0:x.r.kind==='product-model'?10:x.r.domain==='mechanical'?20:40)+({image:0,model:1,mesh:2,video:3}[x.v.kind])+(/installation|assembled|overview|preview|外观|安装/i.test(x.f.name)?-1:0);
    return items.sort((a,b)=>rank(a)-rank(b))[0]||null;
  }
  function verdict(r){return r.design_status==='FAIL'?'未通过':r.status==='FAILED'?'执行失败':r.applicability?.state==='stale'?'需要重验':r.predicted_design_status==='unsatisfied'?'模型内未达到目标':r.design_status==='insufficient_evidence'?'依据不足':r.design_status==='PASS'?'该项计算通过':['RUNNING','QUEUED'].includes(r.status)?'进行中':'查看验证范围'}
  function fileLabel(f){const n=f.name.toLowerCase();return /mechanism-door-open/.test(n)?'开门结构':/mechanism/.test(n)?'机构细节':/schematic/.test(n)?'电路原理图':/pcb-combined/.test(n)?'PCB 布线':/pcb-top/.test(n)?'顶层布线':/pcb-bottom/.test(n)?'底层布线':/exploded/.test(n)?'爆炸视图':/inside|internal/.test(n)?'内部结构':/installation/.test(n)?'安装视图':/\.mp4$/.test(n)?'动作演示':/\.glb$/.test(n)?'三维模型':/report|door-case/.test(n)&&/\.pdf$/.test(n)?'技术报告':f.name;}
  const api={choices,scoped,findings,hero,verdict,fileLabel,key};
  if(typeof module!=='undefined')module.exports=api;else root.StudioModel=api;
})(typeof window!=='undefined'?window:this);
