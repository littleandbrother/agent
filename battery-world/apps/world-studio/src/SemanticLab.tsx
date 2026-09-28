import {useState} from 'react';
import {data,shortHash} from './types';
import './semantic.css';

export function SemanticLab(){
 const d=data.b2_profiled;
 const [task,setTask]=useState('observed-qualification-6'),[program,setProgram]=useState('tx-duration-only'),[cid,setCid]=useState(''),[time,setTime]=useState(.39);
 if(!d)return null;
 const result=d.variants.find((v:any)=>v.id===program),test=result.tasks.find((t:any)=>t.task_id===task),runs=d.runs.filter((r:any)=>r.task_id===task);
 const run=runs.find((r:any)=>r.candidate_id===cid)||runs[0],p=run.load_profile;
 const current=run.trace.reduce((a:any,b:any)=>b.time_s<=time?b:a,run.trace[0]);
 const ymax=Math.max(3.8,...run.trace.map((r:any)=>r.storage_voltage_v))*1.06,x=(t:number)=>54+t/run.reference.duration_s*810,y=(v:number)=>220-v/ymax*180;
 const line=(key:string)=>run.trace.map((r:any,i:number)=>`${i?'L':'M'}${x(r.time_s).toFixed(2)},${y(r[key]).toFixed(2)}`).join(' ');
 return <section id="semantic-development">
  <div className="development-section-heading"><h3>04 / A fix is not yet knowledge</h3><span>{d.runs.length} reference runs · {d.registry.tasks.length} public conditions · {d.cost.provider_calls} new model calls</span></div>
  <p className="development-boundary">只修正时长，能够找回被错误剪枝的设计，却也放过更多失败设计。以下是工程师编写的诊断补丁；既不是 Agent 生成的 G3/G4，也没有获得科学资格。每个程序看到相同输入，按相同候选顺序检查。</p>
  <div className="semantic-variants">{d.variants.map((v:any)=><button aria-pressed={program===v.id} className={program===v.id?'active':''} key={v.id} onClick={()=>setProgram(v.id)}><small>{v.id}</small><b>{v.false_rejects}<em>错误剪枝</em></b><b className="semantic-risk">{v.false_feasible_predictions}<em>错误可行预测</em></b><span>{v.physical_successes} / {d.registry.tasks.length} deterministic task successes · {v.qualified?'QUALIFIED':'NOT QUALIFIED'}</span></button>)}</div>
  <div className="development-section-heading"><div><select aria-label="Explicit development task" value={task} onChange={e=>{setTask(e.target.value);setCid('')}}>{d.registry.tasks.map((t:any)=><option key={t.task_id}>{t.task_id}</option>)}</select><select aria-label="Profiled candidate" value={run.candidate_id} onChange={e=>setCid(e.target.value)}>{runs.map((r:any)=><option key={r.candidate_id}>{r.candidate_id}</option>)}</select></div><span>RELEASE {(run.design.release_s*1000).toFixed(0)} ms ≠ TX {(p.tx_duration_s*1000).toFixed(0)} ms</span></div>
  <div className="semantic-phases">{['boot','sense','infer','tx'].map(k=><div key={k}><small>{k.toUpperCase()}</small><b>{(p[k+'_duration_s']*1000).toFixed(0)} ms</b><span>{((k==='tx'?run.design.tx_power_w:p[k+'_power_w'])*1000).toFixed(1)} mW</span></div>)}</div>
  <div className="development-trace"><div className="development-trace-legend"><span>Storage — olive · terminal — mint</span><span>ALL {run.trace.length.toLocaleString()} SAMPLES · SYNTHETIC v2</span><code>{shortHash(run.run_hash)}</code></div>
   <svg viewBox="0 0 900 253" role="img" aria-label="Explicit load profile voltage replay"><rect x="54" y={y(run.reference.off_v)} width="810" height={220-y(run.reference.off_v)} fill="#784b32" opacity=".2"/>{[run.reference.off_v,run.reference.max_v].map(v=><g key={v}><line x1="54" x2="864" y1={y(v)} y2={y(v)} stroke="#a5ab7b" strokeDasharray="4 4"/><text x="5" y={y(v)}>{v} V</text></g>)}<path d={line('storage_voltage_v')} stroke="#bfcb97"/><path d={line('input_voltage_v')} stroke="#68c7b0"/><line x1={x(time)} x2={x(time)} y1="30" y2="221" stroke="#e4daba"/>{[0,.4,.8,1.2,1.6].map(v=><text x={x(v)} y="244" key={v}>{v} s</text>)}</svg>
   <div className="development-cursor"><b>{time.toFixed(3)} s</b><input aria-label="Profiled replay time" type="range" min="0" max={run.reference.duration_s} step=".001" value={time} onChange={e=>setTime(+e.target.value)}/><button onClick={()=>setTime(run.summary.first_brownout_s??.39)}>Jump to selected failure</button></div>
   <div className="development-sample semantic-sample" data-run-hash={run.run_hash}><div><small>INPUT</small><b>{current.input_voltage_v.toFixed(3)} V</b></div><div><small>PRECEDING LOAD</small><b>{current.interval_load_state}</b></div><div><small>POST-EVENT STATE</small><b>{current.mcu_state}</b></div><div><small>PHYSICAL MISSION</small><b>{run.physical.value?'PASS':'FAIL'}</b></div></div>
  </div>
  <div className="semantic-controls">{[['Raw',test.raw],['With diagnostic code',test.program],['Code removed',test.removed],['Detached process',test.detached]].map(([name,value]:any)=><div key={name}><small>{name}</small><b>{value.probes} probes</b><span>{value.success?'EVIDENCE-BOUND SUBMISSION':'NO SUCCESS'}</span></div>)}</div>
  <p className="development-boundary">“移除”和“移植”在这里仅测试确定性控制器的代码移除及独立进程可移植性，不是新 Agent 的能力提升。错误可行预测必须经过独立 reference 检查，不能直接形成准入。</p>
  <details className="semantic-details"><summary>Inspect exact code change, task physics and all decision errors</summary><pre>{result.diff_from_interface||'No semantic modification: interface adapter only.'}</pre><pre>{JSON.stringify({task_hash:test.task_hash,context_hash:test.context_hash,decisions:test.rows,candidate_hash:result.candidate_hash,authorship:result.authorship,qualified:result.qualified},null,2)}</pre></details>
 </section>
}

export function MeasuredReplay(){
 const d=data.b2_measured,[sample,setSample]=useState(0);
 if(!d)return null;
 const o=d.observations,c=o.current,points=c.trace,current=points[Math.min(sample,points.length-1)];
 const xmin=points[0].time_s,xmax=points[points.length-1].time_s,ymax=c.peak_a*1.1;
 const x=(t:number)=>54+(t-xmin)/(xmax-xmin)*810,y=(i:number)=>220-i/ymax*190;
 const path=points.map((p:any,i:number)=>`${i?'L':'M'}${x(p.time_s).toFixed(2)},${y(p.current_a).toFixed(2)}`).join(' ');
 return <section id="measured-replay">
  <div className="development-section-heading"><h3>05 / Real traces. Explicit limits.</h3><span>ARCHIVED MEASUREMENT · NOT ONE CLOSED HARDWARE EPISODE</span></div>
  <p className="development-boundary">已接入真实历史电流与接收端日志，但它们来自不同实验。电流保留原始秒／安培单位；没有同步电压，不计算实测能量。动作能量历史表的电压假设与启发式对齐方式一并保留。</p>
  <div className="semantic-controls"><div><small>RAW CURRENT</small><b>{c.raw_samples.toLocaleString()}</b><span>原始样本全部封存</span></div><div><small>MEASURED PEAK</small><b>{(c.peak_a*1000).toFixed(2)} mA</b><span>极值保留投影</span></div><div><small>RX MATCHED ROWS</small><b>{o.receiver.matched_rows} / {o.receiver.rows}</b><span>不是全链路 PDR 分母</span></div><div><small>MEASURED ENERGY</small><b>UNAVAILABLE</b><span>无同步电压；不猜测</span></div></div>
  <div className="development-trace"><div className="development-trace-legend"><span>20 kHz archived current capture · first/min/max/last projection</span><code>{shortHash(d.manifest_hash)}</code></div><svg viewBox="0 0 900 255" role="img" aria-label="Measured current extrema preserving replay"><path d={path} stroke="#dab988"/><line x1={x(current.time_s)} x2={x(current.time_s)} y1="25" y2="225" stroke="#d5e4bd"/>{[0,5,10,15,20].map(v=><text x="2" y={y(v/1000)} key={v}>{v} mA</text>)}{[0,1,2,3,4,5].map(v=><text x={x(v)} y="247" key={v}>{v} s</text>)}</svg><div className="development-cursor"><b>{current.time_s.toFixed(5)} s</b><input aria-label="Measured current sample" type="range" min="0" max={points.length-1} step="1" value={sample} onChange={e=>setSample(+e.target.value)}/><button onClick={()=>setSample(points.findIndex((p:any)=>p.current_a===c.peak_a))}>Jump to measured peak</button></div><div className="measured-sample" data-manifest-hash={d.manifest_hash}>Raw sample #{current.sample} · {(current.current_a*1000).toFixed(4)} mA · instrument-relative time</div></div>
  <div className="development-finding"><div><b>Missing alignment is a result, not a blank to fill.</b><p>另一个 PPK 缓存明确标注未与 UART 同步，不能用来推导动作能量。这里不把接收端回调时间当作空口时延，不把不同 session 拼成一次完整硬件成功。</p></div></div>
  <details className="semantic-details"><summary>Inspect measurement provenance, missing values and receiver statuses</summary><pre>{JSON.stringify({manifest_hash:d.manifest_hash,measurement_boundary:o.source_boundary,receiver:o.receiver,rejected_asset:o.rejected_asset,historical_phases:o.historical_phases},null,2)}</pre></details>
 </section>
}
