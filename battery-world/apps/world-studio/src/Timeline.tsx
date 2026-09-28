import { useMemo, useRef } from 'react';
import { atTime, colors, data, Phase } from './types';

export function Timeline({time,onTime,phase,overlay,channel,range,onInspect}:{time:number;onTime:(v:number)=>void;phase:Phase;overlay:boolean;channel:string;range:[number,number];onInspect:(key:string)=>void}){
 const svg=useRef<SVGSVGElement>(null);
 const W=1100,H=245,L=54,R=24,T=24,B=34;
 const displayed=overlay?data.phases:[phase];
 const isVoltage=channel==='capacitor_voltage_v';
 const multiplier=channel.endsWith('_j')||channel.endsWith('_a')?1000:1;
 const unit=channel.endsWith('_j')?'mJ':channel.endsWith('_a')?'mA':'V';
 const max=useMemo(()=>Math.max(...displayed.flatMap(p=>p.rows.map(r=>Number(r[channel])*multiplier)),isVoltage?4:0)*1.06,[channel,overlay,phase.id]);
 const low=isVoltage?1.5:0;
 const x=(t:number)=>L+(t-range[0])/(range[1]-range[0])*(W-L-R);
 const y=(v:number)=>H-B-(v-low)/(max-low)*(H-T-B);
 const path=(p:Phase)=>p.rows.filter(r=>r.time_s>=range[0]&&r.time_s<=range[1]).map((r,i)=>`${i?'L':'M'}${x(r.time_s).toFixed(2)},${y(Number(r[channel])*multiplier).toFixed(2)}`).join(' ');
 const move=(e:React.PointerEvent<SVGSVGElement>)=>{const box=svg.current!.getBoundingClientRect();const v=range[0]+((e.clientX-box.left)/box.width*W-L)/(W-L-R)*(range[1]-range[0]);onTime(Math.min(range[1],Math.max(range[0],v)));};
 return <div className="timeline-chart">
 <div className="chart-meta"><button className="text-button" onClick={()=>onInspect(channel)}>{data.channels[channel].unit} → {unit} · source ↗</button><span>All {displayed.reduce((n,p)=>n+p.rows.length,0).toLocaleString()} samples · extrema preserved</span></div>
 <svg ref={svg} role="img" aria-label="Synchronized waveform timeline" viewBox={`0 0 ${W} ${H}`} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);move(e)}} onPointerMove={e=>{if(e.buttons===1)move(e)}}>
 <defs><clipPath id="chart-clip"><rect x={L} y={T} width={W-L-R} height={H-T-B}/></clipPath></defs>
 {Array.from({length:5},(_,i)=>{const v=low+(max-low)*i/4;return <g key={i}><line x1={L} x2={W-R} y1={y(v)} y2={y(v)} className="gridline"/><text x={L-12} y={y(v)+4} textAnchor="end">{v.toFixed(1)}</text></g>})}
 {Array.from({length:9},(_,i)=>{const t=range[0]+(range[1]-range[0])*i/8;return <g key={i}><line x1={x(t)} x2={x(t)} y1={T} y2={H-B} className="gridline vertical"/><text x={x(t)} y={H-9} textAnchor="middle">{t.toFixed(2)}s</text></g>})}
 <g clipPath="url(#chart-clip)">
 {isVoltage&&<><rect x={L} width={W-L-R} y={T} height={Math.max(0,y(3.6)-T)} fill="#d78763" opacity=".08"/><line x1={L} x2={W-R} y1={y(3.6)} y2={y(3.6)} stroke="#dca17c" strokeDasharray="5 5"/><text x={W-R-8} y={y(3.6)-7} fill="#dca17c" textAnchor="end">3.60 V · safety ceiling</text><line x1={L} x2={W-R} y1={y(1.8)} y2={y(1.8)} stroke="#779a8d" strokeDasharray="4 5"/></>}
 {data.world.mission.load.inference_times_s.map((t:number)=><rect key={t} x={x(t)} y={T} width={x(t+.02)-x(t)} height={H-T-B} fill="#c1d7b5" opacity=".035"/>)}
 {displayed.map(p=><path key={p.id} d={path(p)} stroke={colors[p.id]} fill="none" strokeWidth={p.id===phase.id?2.8:1.5} opacity={p.id===phase.id?1:.65} vectorEffect="non-scaling-stroke"/>)}
 <line x1={x(time)} x2={x(time)} y1={T} y2={H-B} stroke="#e9ecd9" strokeWidth="1"/>
 {displayed.map(p=><circle key={p.id} cx={x(time)} cy={y(Number(atTime(p.rows,time)[channel])*multiplier)} r={4} fill={colors[p.id]} stroke="#13231c" strokeWidth={2}/>)}
 </g>
 </svg>
 <div className="pulse-track"><span>Load windows</span><div>{data.world.mission.load.inference_times_s.map((t:number,i:number)=><button key={t} title={`Aggregate load pulse ${i+1}`} style={{left:`${t/2*100}%`}} onClick={()=>onTime(t)}>P{i+1}</button>)}<i style={{left:`${time/2*100}%`}}/></div></div>
 </div>
}
