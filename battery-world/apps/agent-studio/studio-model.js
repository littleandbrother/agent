/* Pure presentation helpers. No metric thresholds or acceptance decisions. */
(function(root){
  const key=r=>r.case_id?'case:'+r.case_id+':'+r.case_version:'';
  function choices(snapshot){
    const cases=new Map();
    for(const r of snapshot.results||[])if(key(r)&&!cases.has(key(r)))cases.set(key(r),{id:key(r),label:(r.case_title||r.case_id)+' · '+r.case_version});
    return [...(snapshot.revision!=null?[{id:'assembly',label:'装配 v'+snapshot.revision+' · 适用成果'}]:[]),
      {id:'session',label:'全部记录 · 含历史与独立运行'},...cases.values()];
  }
  function scoped(snapshot,selection){
    if(!selection||selection==='session')return {...snapshot,selectedScope:'session'};
    const files=(snapshot.files||[]).filter(f=>selection==='assembly'?['current','reused'].includes(f.applicability?.state):key(f)===selection||snapshot.results.some(r=>key(r)===selection&&r.files.some(x=>x.id===f.id)));
    const ids=new Set(files.map(f=>f.id));
    const results=snapshot.results.filter(r=>selection==='assembly'?r.files.some(f=>ids.has(f.id)):key(r)===selection)
      .map(r=>({...r,files:r.files.filter(f=>ids.has(f.id)),presentations:(r.presentations||[]).filter(v=>ids.has(v.file_id))}));
    return {...snapshot,results,files,verdict:selection==='assembly'?snapshot.verdict:null,
      blockers:selection==='assembly'?snapshot.blockers:[],selectedScope:selection};
  }
  function preferredScope(snapshot){
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
  function verdict(r){if(r.reference_only)return '历史参考 · 待适配';return r.design_status==='FAIL'?'未通过':r.status==='FAILED'?'执行失败':r.applicability?.state==='stale'?'需要重验':r.predicted_design_status==='unsatisfied'?'模型内未达到目标':r.design_status==='insufficient_evidence'?'依据不足':r.design_status==='PASS'?'该项计算通过':['RUNNING','QUEUED'].includes(r.status)?'进行中':'查看验证范围'}
  function fileLabel(f){if(f.label)return f.label;const n=f.name.toLowerCase();return /^preview\./.test(n)?'整体外观':/^back\./.test(n)?'背部视图':/^side\./.test(n)?'侧面视图':/mechanism-door-open/.test(n)?'开门结构':/mechanism/.test(n)?'机构细节':/schematic/.test(n)?'电路原理图':/pcb-combined/.test(n)?'PCB 布线':/pcb-top/.test(n)?'顶层布线':/pcb-bottom/.test(n)?'底层布线':/exploded/.test(n)?'爆炸视图':/inside|internal/.test(n)?'内部结构':/installation/.test(n)?'安装视图':/\.mp4$/.test(n)?'动作演示':/\.glb$/.test(n)?'三维模型':/report|door-case/.test(n)&&/\.pdf$/.test(n)?'技术报告':f.name;}
  const api={choices,scoped,scopeLabel,preferredScope,previewLabels,findings,hero,verdict,fileLabel,key};
  if(typeof module!=='undefined')module.exports=api;else root.StudioModel=api;
})(typeof window!=='undefined'?window:this);
