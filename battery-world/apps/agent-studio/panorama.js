/* A source-bound map. Navigation observes; it never launches agents or tools. */
(() => {
  const {api,esc}=window.BF, q=s=>document.querySelector(s);
  let data=null, selected=localStorage.getItem('bf-map-node')||'ui', version='', baseline='', view='architecture', search='', timer=null, busy=false, generation=0;
  let zoom=.8, positions={}, dragging=false, pending=false, routeCache=null, edgeFrame=0;
  try{positions=JSON.parse(localStorage.getItem('bf-map-layout-v1')||'{}')}catch{}
  const short=s=>(s||'').slice(0,10), date=t=>new Date(t*1000).toLocaleString('zh-CN',{hour12:false});
  const active=()=>document.body.dataset.studioMode==='panorama';
  const loc=n=>positions[n.id]||{x:n.x,y:n.y};
  const status=c=>c.freshness==='stale'?'历史结果 · 当前版本需复核':c.result==='passed'?'检查通过':'检查失败';
  function options(rows,chosen){return rows.map(s=>`<option value="${s.id}" ${s.id===chosen?'selected':''}>${date(s.created)} · ${short(s.id)}</option>`).join('')}
  function notify(s){const p=q('#map-notice');if(p)p.textContent=s}
  async function load(scan=true){
    if(busy){pending=true;return}busy=true;const gen=++generation, requestedVersion=version, requestedBaseline=baseline;
    try{
      if(scan)await api('/api/developer/panorama/scan',{});
      const params=new URLSearchParams();if(requestedVersion)params.set('snapshot',requestedVersion);if(requestedBaseline)params.set('baseline',requestedBaseline);
      const next=await api('/api/developer/panorama?'+params);
      const owner=window.BF.getSelection();
      if(!requestedVersion&&owner?.startsWith('pi-chat-'))try{next.progress=await api('/api/progress?session='+encodeURIComponent(owner))}catch{}
      if(gen!==generation||!active())return;
      if(version!==requestedVersion||baseline!==requestedBaseline){pending=true;return}
      const changed=!data||data.snapshot!==next.snapshot||data.checks?.length!==next.checks?.length||data.baseline!==next.baseline||JSON.stringify(data.progress)!==JSON.stringify(next.progress);
      data=next;
      if(!q('#map-stage'))build();else if(changed){selectors();draw();inspect()}
      q('#map-updated').textContent=(version?'历史快照 · ':'工作区观测 · ')+date(data.observed_at);
      const cloudSources=data.skipped?.filter(x=>x.reason==='cloud_placeholder').length||0;
      const cloudHistory=data.unavailable_snapshots?.length||0;
      notify(cloudSources||cloudHistory?`本机云端占位文件暂不可读：${cloudSources} 个源文件、${cloudHistory} 个历史快照。下载到本机后可恢复；未将缺失数据视为通过或删除。`:'');
    }catch(e){notify('观测暂不可用：'+e.message);if(!q('#map-stage'))q('#panorama-view').innerHTML=`<div class="map-empty"><p>${esc(e.message)}</p><button id="map-retry">重新读取</button></div>`;const retry=q('#map-retry');if(retry)retry.onclick=()=>open()}
    finally{busy=false;if(pending&&active()){pending=false;load(false)}}
  }
  function selectors(){
    q('#map-version').innerHTML='<option value="">当前工作区</option>'+options(data.snapshots,version);
    q('#map-version').value=version;
    q('#map-baseline').innerHTML=options(data.snapshots,data.baseline);
    q('#map-baseline-wrap').hidden=view!=='compare';
    q('#map-scope').textContent=`${data.files?Object.keys(data.files).length:0} 个源文件 · ${data.modules.length} 个模块 · ${data.changes?.length||0} 处文件变化`;
  }
  function build(){
    const root=q('#panorama-view');
    root.innerHTML=`<div class="panorama-heading"><div><h2>全景</h2><p id="map-scope"></p></div><span id="map-updated"></span></div>
      <div class="map-controls"><div class="map-views" aria-label="地图视图">${[['architecture','当前架构'],['development','开发变化'],['compare','版本对比']].map(([id,title])=>`<button data-map-view="${id}" aria-pressed="${view===id}">${title}</button>`).join('')}</div><input id="map-search" type="search" placeholder="查找模块或文件…" aria-label="查找模块或文件" value="${esc(search)}"><button id="map-refresh" class="quiet">刷新</button></div>
      <div class="map-version-bar"><label>查看 <select id="map-version" aria-label="地图版本"></select></label><label id="map-baseline-wrap">对比基线 <select id="map-baseline" aria-label="对比基线"></select></label><span>连线：架构声明 · 变更：源文件观测</span></div><p id="map-notice" role="status"></p>
      <div class="panorama-body"><div class="map-canvas-area"><div id="map-stage" tabindex="0" aria-label="架构画布，可拖动空白区域平移"><div id="map-size"><div id="map-board"><svg id="map-edges" viewBox="0 0 1310 755" aria-label="模块间的声明关系"></svg><div id="map-nodes"></div></div></div></div><div class="map-bottom"><span id="map-routing-hint">拖动节点自动排线 · 选中模块突出关联</span><div><button id="map-minus" aria-label="缩小">−</button><span id="map-zoom"></span><button id="map-plus" aria-label="放大">＋</button><button id="map-fit">全图</button><button id="map-reset" class="quiet">重置布局</button></div></div></div><aside id="map-inspector" aria-label="模块详情"></aside></div>`;
    selectors();draw();inspect();fit();window.BFPanelSizing?.refresh();
    root.querySelectorAll('[data-map-view]').forEach(b=>b.onclick=()=>{view=b.dataset.mapView;root.querySelectorAll('[data-map-view]').forEach(x=>x.setAttribute('aria-pressed',x===b));selectors();draw();inspect()});
    q('#map-search').oninput=e=>{search=e.target.value;draw()};q('#map-refresh').onclick=()=>load(true);
    q('#map-version').onchange=e=>{version=e.target.value;load(false)};
    q('#map-baseline').onchange=e=>{baseline=e.target.value;load(false)};
    q('#map-minus').onclick=()=>scale(zoom-.1);q('#map-plus').onclick=()=>scale(zoom+.1);q('#map-fit').onclick=fit;
    q('#map-reset').onclick=()=>{positions={};localStorage.removeItem('bf-map-layout-v1');draw();fit()};
    q('#map-stage').addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();scale(zoom+(e.deltaY<0?.06:-.06))}},{passive:false});
    q('#map-stage').addEventListener('pointerdown',pointerDown);
  }
  const boardHeight=()=>Math.max(755,...(data?.modules||[]).map(n=>loc(n).y+220));
  function scale(value){zoom=Math.max(.3,Math.min(1.6,value));q('#map-board').style.transform=`scale(${zoom})`;q('#map-size').style.width=1310*zoom+'px';q('#map-size').style.height=boardHeight()*zoom+'px';q('#map-board').style.height=boardHeight()+'px';q('#map-zoom').textContent=Math.round(zoom*100)+'%'}
  function fit(){if(!q('#map-stage'))return;scale(Math.min((q('#map-stage').clientWidth-24)/1310,(q('#map-stage').clientHeight-24)/boardHeight(),1));q('#map-stage').scrollTo(0,0)}
  function draw(){
    if(!data||data.empty)return;
    const needle=search.trim().toLowerCase(), changed=new Set(data.changes.flatMap(c=>c.modules));
    q('#map-nodes').innerHTML=data.modules.map(n=>{
      const files=Object.entries(data.files).filter(([,f])=>f.modules.includes(n.id));
      const match=!needle||[n.title,n.description,...files.map(([k])=>k)].some(s=>s.toLowerCase().includes(needle));
      const count=data.changes.filter(c=>c.modules.includes(n.id)).length;
      return `<button class="map-node ${selected===n.id?'selected':''} ${view!=='architecture'&&changed.has(n.id)?'changed':''} ${!match?'dimmed':''}" data-node="${n.id}" aria-pressed="${selected===n.id}"><span class="map-layer">${esc(n.layer)}</span><strong>${esc(n.title)}</strong><p>${esc(n.description)}</p><span class="map-node-meta">${files.length} 个文件${!version&&data.progress?.stages?.some(s=>s.module===n.id)?`<span>任务 ${data.progress.stages.filter(s=>s.module===n.id&&s.state==='passed').length}/${data.progress.stages.filter(s=>s.module===n.id).length} 项有证据</span>`:''}${count?`<b>${count} 处变化</b>`:'<span>无对比差异</span>'}</span></button>`;
    }).join('');
    q('#map-nodes').querySelectorAll('[data-node]').forEach(b=>{const p=loc(data.modules.find(n=>n.id===b.dataset.node));b.style.left=p.x+'px';b.style.top=p.y+'px';b.onclick=()=>{if(dragging)return;selected=b.dataset.node;localStorage.setItem('bf-map-node',selected);draw();inspect()}});
    edges();
  }
  // Route in board coordinates. A shared visibility grid keeps connections in
  // card gutters; bend and occupied-track costs discourage zigzags and overlap.
  function routeEdges(){
    const width=1310,height=boardHeight(),pad=14,rects=data.modules.map(n=>({id:n.id,...loc(n),w:252,h:170}));
    const key=JSON.stringify([rects,data.edges]);if(routeCache?.key===key)return routeCache.routes;
    const byId=new Map(rects.map(r=>[r.id,r])),groups=new Map();
    const links=data.edges.filter(e=>byId.has(e.source)&&byId.has(e.target)).map(e=>{
      const a=byId.get(e.source),b=byId.get(e.target),dx=b.x-a.x,dy=b.y-a.y;
      const horizontal=Math.abs(dx)>Math.abs(dy),from=horizontal?(dx>0?'E':'W'):(dy>0?'S':'N');
      const to={E:'W',W:'E',N:'S',S:'N'}[from],link={edge:e};
      for(const [name,r,side,other] of [['start',a,from,b],['end',b,to,a]]){
        const group=r.id+side;if(!groups.has(group))groups.set(group,[]);
        groups.get(group).push({link,name,r,side,order:side==='E'||side==='W'?other.y:other.x});
      }
      return link;
    });
    // Each relation gets its own port, including incoming and outgoing links.
    for(const group of groups.values()){
      group.sort((a,b)=>a.order-b.order||a.link.edge.id.localeCompare(b.link.edge.id));
      group.forEach(({link,name,r,side},i)=>{
        const vertical=side==='E'||side==='W',length=vertical?r.h:r.w;
        const offset=length/2+(i-(group.length-1)/2)*Math.min(24,(length-48)/Math.max(1,group.length-1));
        const p=vertical?{x:r.x+(side==='E'?r.w:0),y:r.y+offset}:{x:r.x+offset,y:r.y+(side==='S'?r.h:0)};
        const v={E:[1,0],W:[-1,0],N:[0,-1],S:[0,1]}[side];
        link[name]={point:p,exit:{x:p.x+v[0]*pad,y:p.y+v[1]*pad},axis:vertical?1:2};
      });
    }
    const xs=new Set([12,width-12]),ys=new Set([12,height-12]);
    rects.forEach(r=>{xs.add(r.x-pad);xs.add(r.x+r.w+pad);ys.add(r.y-pad);ys.add(r.y+r.h+pad)});
    links.forEach(l=>{for(const p of [l.start.exit,l.end.exit]){xs.add(p.x);ys.add(p.y)}});
    const axis=(values,limit)=>{
      const sorted=[...values].filter(v=>v>=4&&v<=limit-4).sort((a,b)=>a-b),extra=[];
      for(let i=1;i<sorted.length;i++)if(sorted[i]-sorted[i-1]>22)extra.push((sorted[i]+sorted[i-1])/2);
      return [...sorted,...extra].sort((a,b)=>a-b);
    };
    const X=axis(xs,width),Y=axis(ys,height),cols=X.length;
    const boxes=rects.map(r=>({left:r.x-pad,right:r.x+r.w+pad,top:r.y-pad,bottom:r.y+r.h+pad}));
    const inside=(p,r)=>p.x>r.left+.01&&p.x<r.right-.01&&p.y>r.top+.01&&p.y<r.bottom-.01;
    const blocked=(a,b)=>boxes.some(r=>a.y===b.y?
      a.y>r.top+.01&&a.y<r.bottom-.01&&Math.max(a.x,b.x)>r.left+.01&&Math.min(a.x,b.x)<r.right-.01:
      a.x>r.left+.01&&a.x<r.right-.01&&Math.max(a.y,b.y)>r.top+.01&&Math.min(a.y,b.y)<r.bottom-.01);
    const nodes=Y.flatMap((y,j)=>X.map((x,i)=>({x,y,i,j,free:!boxes.some(r=>inside({x,y},r)),next:[]})));
    for(const [id,p] of nodes.entries())if(p.free){
      for(const [i,j] of [[p.i-1,p.j],[p.i+1,p.j],[p.i,p.j-1],[p.i,p.j+1]]){
        const t=nodes[j*cols+i];if(i<0||i>=cols||j<0||j>=Y.length||!t?.free||blocked(p,t))continue;
        p.next.push({id:j*cols+i,axis:p.y===t.y?1:2,length:Math.abs(p.x-t.x)+Math.abs(p.y-t.y),key:[id,j*cols+i].sort((a,b)=>a-b).join(':')});
      }
    }
    const occupied=new Map(),traffic=new Map(),routes=[];
    const nodeId=p=>Y.indexOf(p.y)*cols+X.indexOf(p.x);
    const distance=(a,b)=>Math.abs(a.x-b.x)+Math.abs(a.y-b.y);
    // Nearby links establish the short routes first. Selection never reroutes.
    links.sort((a,b)=>distance(a.start.exit,a.end.exit)-distance(b.start.exit,b.end.exit)||a.edge.id.localeCompare(b.edge.id));
    for(const l of links){
      const first=nodeId(l.start.exit),last=nodeId(l.end.exit),queue=[],cost=new Map(),previous=new Map();
      const push=item=>{queue.push(item);let i=queue.length-1;while(i){const p=(i-1)>>1;if(queue[p].f<=item.f)break;queue[i]=queue[p];i=p}queue[i]=item};
      const pop=()=>{const result=queue[0],tail=queue.pop();if(queue.length){let i=0;while(i*2+1<queue.length){let c=i*2+1;if(c+1<queue.length&&queue[c+1].f<queue[c].f)c++;if(queue[c].f>=tail.f)break;queue[i]=queue[c];i=c}queue[i]=tail}return result};
      const initial=first*3+l.start.axis;cost.set(initial,0);push({state:initial,g:0,f:distance(l.start.exit,l.end.exit)});
      let final=null;
      while(queue.length){
        const current=pop();if(current.g!==cost.get(current.state))continue;
        const id=Math.floor(current.state/3),direction=current.state%3;
        if(id===last&&direction===l.end.axis){final=current.state;break}
        for(const step of nodes[id]?.next||[]){
          const state=step.id*3+step.axis;
          const crossing=(traffic.get(step.id)||0)&(step.axis===1?2:1);
          const g=current.g+step.length+(direction!==step.axis?32:0)+(occupied.get(step.key)||0)*(step.length*5+28)+(crossing?44:0);
          if(g>=(cost.get(state)??Infinity))continue;
          cost.set(state,g);previous.set(state,{state:current.state,step});push({state,g,f:g+distance(nodes[step.id],l.end.exit)});
        }
      }
      if(final===null){routes.push({edge:l.edge,points:[]});continue}
      const middle=[];
      for(let state=final;state!==initial;){
        const p=nodes[Math.floor(state/3)],prev=previous.get(state);middle.push({x:p.x,y:p.y});
        occupied.set(prev.step.key,(occupied.get(prev.step.key)||0)+1);
        traffic.set(Math.floor(state/3),(traffic.get(Math.floor(state/3))||0)|prev.step.axis);state=prev.state;
      }
      const points=[l.start.point,l.start.exit,...middle.reverse(),l.end.point],clean=[];
      for(const p of points){
        if(clean.length&&distance(clean.at(-1),p)<.01)continue;
        while(clean.length>1){const a=clean.at(-2),b=clean.at(-1);if((a.x===b.x&&b.x===p.x)||(a.y===b.y&&b.y===p.y))clean.pop();else break}
        clean.push(p);
      }
      routes.push({edge:l.edge,points:clean});
    }
    routeCache={key,routes};return routes;
  }
  function routePath(points){
    if(!points.length)return '';
    let path=`M${points[0].x} ${points[0].y}`;
    for(let i=1;i<points.length-1;i++){
      const a=points[i-1],b=points[i],c=points[i+1],ab=Math.hypot(b.x-a.x,b.y-a.y),bc=Math.hypot(c.x-b.x,c.y-b.y),r=Math.min(8,ab/2,bc/2);
      path+=` L${b.x+(a.x-b.x)*r/ab} ${b.y+(a.y-b.y)*r/ab} Q${b.x} ${b.y} ${b.x+(c.x-b.x)*r/bc} ${b.y+(c.y-b.y)*r/bc}`;
    }
    return path+` L${points.at(-1).x} ${points.at(-1).y}`;
  }
  function edges(){
    const svg=q('#map-edges');if(!svg)return;
    svg.setAttribute('viewBox',`0 0 1310 ${boardHeight()}`);
    const routes=routeEdges(),connected=e=>e.source===selected||e.target===selected;
    svg.innerHTML='<defs>'+['normal','selected'].map(s=>`<marker id="map-arrow-${s}" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6"/></marker>`).join('')+'</defs>'+[...routes].sort((a,b)=>Number(connected(a.edge))-Number(connected(b.edge))).map(({edge:e,points})=>{
      const d=routePath(points),state=connected(e)?'selected':'normal';
      return `<g class="map-edge ${state}" data-edge="${esc(e.id)}" data-source="${esc(e.source)}" data-target="${esc(e.target)}"><title>${esc(e.relation)} · 架构声明</title><path class="map-edge-halo" d="${d}"/><path class="map-edge-line" d="${d}" marker-end="url(#map-arrow-${state})"/></g>`;
    }).join('');
    svg.setAttribute('aria-label',`模块间的 ${routes.length} 条声明关系；选中模块可突出相关连线`);
    q('#map-routing-hint').textContent=routes.some(r=>!r.points.length)?'部分卡片过近，拖开卡片或重置布局可恢复连线':'拖动节点自动排线 · 选中模块突出关联';
  }
  function pointerDown(e){
    if(e.button!==0)return;
    const node=e.target.closest('[data-node]'),stage=q('#map-stage'),start={x:e.clientX,y:e.clientY,left:stage.scrollLeft,top:stage.scrollTop}, n=node&&data.modules.find(n=>n.id===node.dataset.node), origin=n?{...loc(n)}:null;
    dragging=false;stage.setPointerCapture(e.pointerId);
    const move=ev=>{const dx=ev.clientX-start.x,dy=ev.clientY-start.y;if(Math.abs(dx)+Math.abs(dy)<5&&!dragging)return;dragging=true;
      if(n){positions[n.id]={x:Math.max(24,Math.min(1034,origin.x+dx/zoom)),y:Math.max(24,Math.min(boardHeight()-194,origin.y+dy/zoom))};node.style.left=positions[n.id].x+'px';node.style.top=positions[n.id].y+'px';if(!edgeFrame)edgeFrame=requestAnimationFrame(()=>{edgeFrame=0;edges()})}
      else{stage.scrollLeft=start.left-dx;stage.scrollTop=start.top-dy}};
    const up=()=>{stage.removeEventListener('pointermove',move);stage.removeEventListener('pointerup',up);stage.removeEventListener('pointercancel',up);if(n&&dragging){localStorage.setItem('bf-map-layout-v1',JSON.stringify(positions));scale(zoom)}else if(n){selected=n.id;localStorage.setItem('bf-map-node',selected);draw();inspect()}setTimeout(()=>dragging=false,0)};
    stage.addEventListener('pointermove',move);stage.addEventListener('pointerup',up);stage.addEventListener('pointercancel',up);
  }
  function inspect(){
    if(!data||data.empty)return;
    const node=data.modules.find(n=>n.id===selected)||data.modules[0];selected=node.id;
    const files=Object.entries(data.files).filter(([,f])=>f.modules.includes(node.id));
    const changes=data.changes.filter(c=>c.modules.includes(node.id));
    const list=view==='architecture'?files.map(([key])=>({key,kind:data.changes.find(c=>c.key===key)?.kind})):changes;
    const checks=data.checks.filter(c=>c.freshness==='current');
    q('#map-inspector').innerHTML=`<span class="map-layer">${esc(node.layer)}</span><h3>${esc(node.title)}</h3><p>${esc(node.description)}</p><div class="map-detail-status"><span>${changes.length?'已观测到文件变化':'无对比差异'}</span><span>${checks.length?'有版本绑定检查，查看覆盖范围':'所选版本尚无绑定检查'}</span></div><p class="dev-hint">执行者：未归因<br>快照 ${short(data.snapshot)} · ${date(data.created)}</p><button id="map-console">在控制台查看 ↗</button>${!version&&data.progress?`<details open class="dev-record"><summary>当前任务 · 装配 v${data.progress.revision??'—'} 的进展</summary>${data.progress.stages.filter(s=>s.module===node.id).map(s=>`<p>${s.state==='passed'?'✓':'○'} ${esc(s.title)} · ${esc(s.detail)}</p>`).join('')||'<p>本模块没有对应的产品交付项。</p>'}<p class="dev-hint">任务状态与代码版本检查分别记录，不能互相替代。</p><button data-map-delivery>查看交付与问题定位 →</button></details>`:''}<h4>${view==='architecture'?'关联文件':'相对基线的变更'} <small>${list.length}</small></h4><div class="map-file-list">${list.map(f=>`<button data-map-file="${esc(f.key)}"><span>${esc(f.key.split(':')[1])}</span>${f.kind?`<small class="file-${f.kind}">${{added:'新增',modified:'修改',deleted:'删除'}[f.kind]}</small>`:''}</button>`).join('')||'<p class="dev-hint">这个模块没有对比变化。</p>'}</div><h4>声明的关系</h4><ul class="map-relations">${data.edges.filter(e=>e.source===node.id||e.target===node.id).map(e=>`<li>${esc(data.modules.find(n=>n.id===e.source)?.title)} → ${esc(data.modules.find(n=>n.id===e.target)?.title)}<small>${esc(e.relation)}</small></li>`).join('')}</ul><details class="dev-record"><summary>范围与来源</summary><p>${esc(data.scope)}</p><p>${esc(data.boundary)}</p>${data.skipped.length?`<pre>${esc(JSON.stringify(data.skipped,null,2))}</pre>`:''}</details>`;
    q('[data-map-delivery]')?.addEventListener('click',()=>window.BFDeveloper.openModule('delivery'));
    q('#map-console').onclick=()=>window.BFDeveloper.openModule(node.console);
    q('#map-inspector').querySelectorAll('[data-map-file]').forEach(b=>b.onclick=()=>file(b.dataset.mapFile));
  }
  async function file(key){
    const snapshot=data.snapshot,base=data.baseline;
    try{const r=await api('/api/developer/panorama/file?'+new URLSearchParams({snapshot,file:key,baseline:base}));
      show(`${key} · ${short(snapshot)}`,`<p class="dev-hint">历史内容按快照读取 · ${r.exists?'文件 SHA-256 '+esc(r.sha256):'所选版本已删除此文件'}</p><details open><summary>与基线差异</summary><pre>${esc(r.diff||'没有差异')}</pre></details><details><summary>所选版本完整内容</summary><pre>${esc(r.content)}</pre></details>`);
    }catch(e){notify(e.message)}
  }
  function show(title,html){let d=q('#panorama-detail');if(!d){d=document.createElement('dialog');d.id='panorama-detail';document.body.append(d)}d.innerHTML=`<form method="dialog" class="dialog-top"><h2>${esc(title)}</h2><button aria-label="关闭详情">×</button></form>${html}`;d.showModal()}
  async function fetchProjection(){await api('/api/developer/panorama/scan',{});return api('/api/developer/panorama')}
  async function history(root){
    root.innerHTML='<p class="dev-hint">正在读取平台版本…</p>';
    try{const d=await fetchProjection();if(!root.isConnected)return;
      root.innerHTML=`<div class="dev-heading"><h3>平台工作区版本</h3><button data-open-map>在全景对比 ↗</button></div><p class="dev-hint">源文件内容快照包含未提交改动；独立于下方 Harness 试验。相同内容复用同一身份。</p><div class="platform-versions">${d.snapshots.slice(0,16).map(s=>`<button data-map-snapshot="${s.id}"><b>${short(s.id)}</b><span>${date(s.created)}</span><small>${s.files} 个源文件${s.id===d.latest?' · 当前观测':''}</small></button>`).join('')}</div>`;
      root.querySelector('[data-open-map]').onclick=()=>focus('validation');root.querySelectorAll('[data-map-snapshot]').forEach(b=>b.onclick=()=>{version=b.dataset.mapSnapshot;view='compare';focus('validation')});
    }catch(e){if(root.isConnected)root.textContent=e.message}
  }
  async function checks(root){
    root.innerHTML='<p class="dev-hint">正在读取代码检查…</p>';
    try{const d=await fetchProjection();if(!root.isConnected)return;
      root.innerHTML=`<div class="dev-heading"><h3>平台代码检查</h3><button data-check-map>在全景定位 ↗</button></div><p class="dev-hint">绑定快照 ${short(d.snapshot)}。通过仅对应命令覆盖范围；代码变化后显示需复核。</p>${d.checks.length?d.checks.map(c=>`<article class="check-record"><div><b>${esc(c.label)}</b><p>${esc(status(c))} · ${date(c.ended)}</p><code>${short(c.snapshot)} · exit ${c.exit_code}</code></div><button data-check-log="${c.id}">查看记录</button></article>`).join(''):'<p class="dev-hint">尚无版本绑定检查。未导入的既有测试不推断为通过。</p>'}`;
      root.querySelector('[data-check-map]').onclick=()=>focus('validation');root.querySelectorAll('[data-check-log]').forEach(b=>b.onclick=async()=>{try{const r=await api('/api/developer/panorama/check?id='+b.dataset.checkLog);show(r.record.label,`<p>${esc(r.record.command.join(' '))}</p><p class="dev-hint">${esc(r.record.scope)}</p><pre>${esc(r.text)}</pre>`)}catch(e){show('记录不可用',`<p>${esc(e.message)}</p>`)}});
    }catch(e){if(root.isConnected)root.textContent=e.message}
  }
  async function open(){clearInterval(timer);await load(true);timer=setInterval(()=>{if(active()&&!document.hidden)load(true)},8000)}
  function focus(id){selected=id||selected;localStorage.setItem('bf-map-node',selected);window.BFDeveloper.setMode('panorama');if(data&&q('#map-stage')){draw();inspect()}}
  window.addEventListener('bf-mode',e=>{if(e.detail.mode!=='panorama')clearInterval(timer)});
  window.Panorama={open,focus,history,checks};
})();
