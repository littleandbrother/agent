import {useState} from 'react';
import {Scene} from './Scene';
import {data,Row,shortHash} from './types';
export function CampaignReplay({hash}:{hash:string}){
 const [time,setTime]=useState(.42),[selected,setSelected]=useState('storage');const run=data.campaign_traces?.[hash];
 if(!run)return null;
 const r=run.rows[Math.min(run.rows.length-1,Math.round(time/run.reference.dt_s))];
 const row={...r,coupled:true,phase:'final',step:Math.round(time/run.reference.dt_s),capacitor_voltage_v:r.storage_voltage_v,storage_energy_j:r.energy_j,inference_active:r.mcu_state==='infer'} as Row;
 const max=Math.max(4,...run.rows.map((r:any)=>r.storage_voltage_v))*1.05;
 const x=(t:number)=>35+t/run.reference.duration_s*690,y=(v:number)=>140-v/max*120;
 return <details className="campaign-replay"><summary>Replay this submitted system · {shortHash(hash)}</summary><div className="campaign-replay-scene"><Scene row={row} phase={run.design.clamp_v===null?'baseline':'final'} selected={selected} onSelect={setSelected}/></div><div className="transport"><span className="time-readout">{time.toFixed(3)} s</span><input type="range" aria-label="Agent run replay time" min="0" max={run.reference.duration_s} step={run.reference.dt_s} value={time} onChange={e=>setTime(+e.target.value)}/><small>{r.mcu_state} · {r.input_voltage_v.toFixed(3)} V</small></div><svg viewBox="0 0 750 160" aria-label="Agent submitted design voltage replay" role="img">{[1.8,3.6].map(v=><g key={v}><line x1="35" x2="725" y1={y(v)} y2={y(v)} stroke="#a78e60" strokeDasharray="4 5"/><text x="1" y={y(v)} fill="#a1b188" fontSize="9">{v} V</text></g>)}{['storage_voltage_v','input_voltage_v'].map((field,i)=><path key={field} d={run.rows.map((r:any,j:number)=>`${j?'L':'M'}${x(r.time_s).toFixed(2)},${y(r[field]).toFixed(2)}`).join(' ')} stroke={i?'#d7a87e':'#acd18e'} strokeWidth="1.5" fill="none"/>)}<line x1={x(time)} x2={x(time)} y1="10" y2="145" stroke="#d2dfb3"/></svg><p>Sealed final conditions · energy-bound fill · {run.rows.length} retained samples · receiver {r.receiver_delivered?'delivered':'not delivered at cursor'}. This replay belongs to the selected trial, not a separate demonstration.</p></details>
}
