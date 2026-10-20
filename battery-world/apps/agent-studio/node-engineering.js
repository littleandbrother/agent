/* One source-bound object; views only select presentation and time windows. */
(async()=>{
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const query=new URLSearchParams(location.search);
let bundle=window.NODE_BUNDLE;
const url=path=>bundle?.portable?path:'/api/design-repository/file?'+new URLSearchParams({project:query.get('project'),owner:query.get('owner'),system:query.get('system'),path,realization:'1'});
try{
if(bundle)bundle.portable=true;else{const r=await fetch(url('viewer-data.json'));if(!r.ok)throw Error('当前候选尚未生成工程视图');bundle=await r.json();}
const {summary,engineering,cad,wave}=bundle;
if(!bundle.portable)document.querySelector('header a[href="/lab#system"]').href='/lab?'+new URLSearchParams({project:query.get('project')})+'#system?candidate='+summary.system_id;
$('#identity').textContent=summary.system_id.slice(0,18)+' · '+summary.execution_id.slice(0,18);
$('#conclusion').textContent=summary.judgment;
$('#metrics').innerHTML=[['有效数字帧',summary.digital_frames],['首次供电',summary.first_powered_s.toFixed(4)+' s'],['新仿真',summary.new_physics_solves]].map(([k,v])=>`<div><strong>${esc(v)}</strong><span>${esc(k)}</span></div>`).join('');
$('#cad-image').src=url('cad-isometric.svg');$('#cad-view').addEventListener('change',e=>$('#cad-image').src=url('cad-'+e.target.value+'.svg'));
$('#cad-facts').innerHTML=[`自由梁 ${cad.beam_free_length_mm} × ${cad.beam_width_mm} mm`,`PCB ${cad.board_size_mm.join(' × ')} mm`,`运动峰值 ${cad.measured_peak_motion_mm.toPrecision(4)} mm`,`额外间隙 ${cad.minimum_motion_clearance_mm} mm`].map(v=>`<span>${esc(v)}</span>`).join('');
for(const key of ['schematic','pcb','pcb-bottom']){const name='native/'+key+'.svg';const exists=bundle.native_assets.includes(name);$('#'+key).src=exists?url(name):'';if(exists){$('#'+key).style.cursor='zoom-in';$('#'+key).onclick=()=>window.open(url(name),'_blank','noopener');}$('#'+key+'-note').textContent=exists?'来自本候选原生工程的保存读回。':'当前候选待补原生'+(key==='pcb'?'PCB':'原理图')+'输出。';}
$('#sequence').src=url('firmware-sequence.svg');
$('#mapping').innerHTML='<table><thead><tr><th>功能</th><th>目标实现</th><th>对应条件</th></tr></thead><tbody>'+bundle.mapping.map(row=>'<tr>'+row.map(c=>'<td>'+esc(c)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
$('#judgment').textContent=summary.judgment;$('#issues').innerHTML=engineering.issues.map(v=>'<li>'+esc(v)+'</li>').join('');
$('#downloads').innerHTML=[['八页简报','brief.pdf'],['工程详报','detailed.pdf'],['机械 STEP','assembly.step'],['目标映射','target-mapping.json'],...bundle.native_assets.filter(p=>/\.(epro2|zip)$/.test(p)).map(p=>['原生工程',p]),...(bundle.portable?[]:[['完整工程包','handoff.zip']])].map(([label,path])=>`<a href="${esc(url(path))}" download>${esc(label)}</a>`).join('');
$('#provenance').textContent=JSON.stringify({system_id:summary.system_id,execution_id:summary.execution_id,execution_origin:wave.execution_origin,source_hashes:wave.sources,assumptions:engineering.assumptions},null,2);
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>{document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-selected',String(b===button)));for(const id of ['device','operation','design'])$('#'+id).hidden=id!==button.dataset.view;});
const txs=wave.events.filter(e=>e.state==='tx'&&e.completed&&wave.received_sequences.includes(e.seq));for(const e of txs){const option=document.createElement('option');option.value=String(e.seq);option.textContent=`发送 ${e.seq} · ${e.t_s.toFixed(4)} s`;$('#event').append(option);}
function draw(){const selected=$('#event').value;let lo=0,hi=wave.duration_s;if(selected==='startup'){hi=summary.first_powered_s+.3;$('#event-detail').textContent='积能与首次供电';}else if(selected!=='all'){const e=txs.find(e=>String(e.seq)===selected);lo=e.t_s-.025;hi=e.t_s+.025;$('#event-detail').textContent=`序号 ${e.seq} · 数值 ${e.value} · CRC ${e.crc} · ${e.completed?'数字帧有效':'未完成'}`;}else $('#event-detail').textContent='保存的收敛结果 · 同一时间轴';
let pts=wave.points.filter(p=>p.t_s>=lo&&p.t_s<=hi);if(pts.length<2)return;
let svg='<svg viewBox="0 0 1100 650" role="img" aria-label="机械、供电、程序与接收的统一时间轴">';const X=t=>85+960*(t-lo)/(hi-lo);
const tracks=[['位移 · mm',['displacement_mm']],['供电 · V',['vin_v','vout_v','pgood_v']],['负载 · mA',['current_a']]];
tracks.forEach(([label,keys],row)=>{const top=25+row*160;let min=0,max=0;for(const p of pts)for(const k of keys){min=Math.min(min,p[k]);max=Math.max(max,p[k]);}const span=Math.max(1e-9,max-min);svg+=`<text x="85" y="${top+14}" class="wave-label">${label}</text>`;
for(let n=0;n<5;n++){const t=lo+(hi-lo)*n/4;svg+=`<path d="M${X(t)} ${top+26}v108" stroke="#e0e7ec"/><text x="${X(t)-17}" y="${top+151}" class="axis-label">${t.toFixed(3)}</text>`;}
keys.forEach((k,i)=>{const poly=pts.map(p=>`${X(p.t_s).toFixed(2)},${(top+129-93*(p[k]-min)/span).toFixed(2)}`).join(' ');svg+=`<polyline fill="none" stroke="${['#287ba6','#328d77','#be9144'][i]}" stroke-width="1.4" points="${poly}"/>`;});const mult=row===2?1000:1;svg+=`<text x="8" y="${top+47}" class="axis-label">${(max*mult).toPrecision(3)}</text><text x="8" y="${top+127}" class="axis-label">${(min*mult).toPrecision(3)}</text>`;});
svg+='<text x="85" y="520" class="wave-label">采样 / 发送 / 有效数字接收</text>';
for(const e of wave.events){if(e.t_s<lo||e.t_s>hi)continue;const y=e.state==='sample'?540:565;svg+=`<rect x="${X(e.t_s)}" y="${y}" width="${Math.max(3,960*e.duration_s/(hi-lo))}" height="12" fill="${e.state==='sample'?'#328d77':'#287ba6'}"/>`;if(e.state==='tx'&&e.completed&&wave.received_sequences.includes(e.seq))svg+=`<circle cx="${X(e.t_s+e.duration_s)}" cy="607" r="3" fill="#173e58"/>`;}
svg+='<text x="85" y="644" class="axis-label">VIN 蓝 / VOUT 绿 / PGOOD 金；参考负载为声明电流；原始波形与完整事件保存在工程包。</text></svg>';$('#waveform').innerHTML=svg;}
$('#event').onchange=draw;draw();
}catch(error){$('#error').textContent=error.message;}
})();
