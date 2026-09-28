import { Suspense, useEffect, useMemo, useRef, Component, ReactNode } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Row } from './types';

function Controls({reset}:{reset:number}){
 const {camera,gl,invalidate}=useThree();
 useEffect(()=>{camera.position.set(8,7,10);camera.lookAt(0,0,0);const c=new OrbitControls(camera,gl.domElement);c.target.set(0,.3,0);c.enableDamping=true;c.enablePan=false;c.minZoom=28;c.maxZoom=110;c.maxPolarAngle=Math.PI/2.2;c.addEventListener('change',()=>invalidate());c.update();(gl.domElement as any).__controls=c;return()=>{c.dispose();delete (gl.domElement as any).__controls};},[camera,gl,reset]);
 useFrame(()=>{(gl.domElement as any).__controls?.update()});return null;
}
function Wire({points,color='#60c5a7',radius=.027}:{points:number[][];color?:string;radius?:number}){
 const geom=useMemo(()=>new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p))),48,radius,6,false),[JSON.stringify(points),radius]);
 useEffect(()=>()=>geom.dispose(),[geom]);
 return <mesh geometry={geom}><meshStandardMaterial color={color} metalness={.55} roughness={.36}/></mesh>;
}
function Box({p,s,c='#243b36',...props}:{p:number[];s:number[];c?:string;[key:string]:any}){return <mesh position={p as any} castShadow receiveShadow {...props}><boxGeometry args={s as any}/><meshStandardMaterial color={c} metalness={.35} roughness={.48}/></mesh>}
function Cylinder({p,r,h,c='#607b73',...props}:{p:number[];r:number;h:number;c?:string;[key:string]:any}){return <mesh position={p as any} castShadow receiveShadow {...props}><cylinderGeometry args={[r,r,h,64]}/><meshStandardMaterial color={c} metalness={.7} roughness={.3}/></mesh>}
function Rotor({angle,selected,onSelect}:{angle:number;selected:boolean;onSelect:()=>void}){
 const ring=useMemo(()=>Array.from({length:16},(_,i)=>new THREE.Shape().absarc(0,0,1.04,i*Math.PI/8+.015,(i+1)*Math.PI/8-.015,false).absarc(0,0,.44,(i+1)*Math.PI/8-.015,i*Math.PI/8+.015,true)),[]);
 return <group position={[-3,0,0]} onClick={e=>{e.stopPropagation();onSelect()}}>
   <Box p={[0,-.35,0]} s={[2.65,.16,2.65]} c={selected?'#467c69':'#263e36'}/>
   {[-.85,.85].flatMap(x=>[-.85,.85].map(z=><Cylinder key={`${x}${z}`} p={[x,-.03,z]} r={.075} h={.55} c='#9aa79b'/>))}
   <Cylinder p={[0,.11,0]} r={1.16} h={.18} c='#c4cabb'/>
   <Cylinder p={[0,.24,0]} r={1.08} h={.07} c='#164a3c'/>
   <group rotation={[0,angle,0]}>
    <Cylinder p={[0,.48,0]} r={1.13} h={.13} c='#d8d8c7'/>
    {ring.map((shape,i)=><mesh key={i} position={[0,.55,0]} rotation={[-Math.PI/2,0,0]}><shapeGeometry args={[shape]}/><meshStandardMaterial color={i%2?'#d99e51':'#233e35'} side={THREE.DoubleSide} metalness={.72} roughness={.28}/></mesh>)}
    <Cylinder p={[0,.58,0]} r={.33} h={.18} c='#c8cdbf'/>
    <Cylinder p={[0,.91,0]} r={.14} h={.58} c='#899c97'/>
    <Box p={[.34,1.2,0]} s={[.8,.09,.12]} c='#8b9c93'/>
   </group>
   <mesh rotation={[-Math.PI/2,0,0]} position={[0,-.25,0]}><ringGeometry args={[1.35,1.37,80]}/><meshBasicMaterial color={selected?'#bfee97':'#3f7660'} transparent opacity={.7}/></mesh>
 </group>
}
function Capacitor({fill,selected,onSelect}:{fill:number;selected:boolean;onSelect:()=>void}){
 return <group position={[.3,0,.25]} onClick={e=>{e.stopPropagation();onSelect()}}>
 <Box p={[0,-.35,0]} s={[1.65,.16,1.7]} c={selected?'#467c69':'#263e36'}/>
 <Cylinder p={[0,.41,0]} r={.49} h={1.22} c='#263e37'/>
 <mesh position={[0,.48,0]}><cylinderGeometry args={[.58,.58,1.36,64,1,true]}/><meshPhysicalMaterial color='#b1d1bc' transparent opacity={.15} roughness={.12} metalness={.12} side={THREE.DoubleSide} depthWrite={false}/></mesh>
 <mesh position={[0,-.12+.6*fill,0]}><cylinderGeometry args={[.54,.54,Math.max(.01,1.2*fill),64]}/><meshStandardMaterial color='#79d6ac' emissive='#3fb585' emissiveIntensity={.35} metalness={.22} roughness={.34}/></mesh>
 <Cylinder p={[0,1.18,0]} r={.58} h={.09} c='#ccd5c5'/>
 <Cylinder p={[0,-.15,0]} r={.58} h={.08} c='#9da99c'/>
 <Box p={[0,1.23,0]} s={[.48,.018,.032]} c='#6d7f73'/><Box p={[0,1.23,0]} s={[.032,.018,.48]} c='#6d7f73'/>
 {[.2,.5,.8].map(h=><mesh key={h} position={[0,h,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.59,.01,6,64]}/><meshStandardMaterial color='#9db8a0'/></mesh>)}
 </group>
}
function Circuit({active,clamp,selected,onSelect}:{active:boolean;clamp:boolean;selected:boolean;onSelect:()=>void}){
 return <group position={[2.8,0,.2]} onClick={e=>{e.stopPropagation();onSelect()}}>
 <Box p={[0,-.28,0]} s={[2.25,.12,1.9]} c={selected?'#296250':'#193e32'}/>
 {[-.8,.8].flatMap(x=>[-.65,.65].map(z=><Cylinder key={`${x}${z}`} p={[x,-.18,z]} r={.07} h={.06} c='#cfb873'/>))}
 <Box p={[0,-.03,0]} s={[.68,.3,.7]} c='#16201e'/>
 {Array.from({length:6},(_,i)=>[-1,1].map(s=><Box key={`${i}${s}`} p={[s*.43,-.07,(i-2.5)*.1]} s={[.19,.055,.045]} c='#a9b2a0'/>))}
 <Box p={[-.66,-.11,.42]} s={[.3,.14,.15]} c='#b7a269'/>
 <Box p={[.68,-.1,.42]} s={[.3,.16,.18]} c={clamp?'#d8c5a1':'#3e5247'}/>
 <mesh position={[.73,-.04,-.52]}><sphereGeometry args={[.07,12,8]}/><meshStandardMaterial color={active?'#a2ee88':'#4c5d43'} emissive='#a2ee88' emissiveIntensity={active?2:0}/></mesh>
 {[.5,-.5].map(z=><Wire key={z} points={[[-.97,-.205,z],[-.48,-.205,z],[-.3,-.205,z*.5]]} color='#8fa36a' radius={.012}/>)}
 <Wire points={[[.55,-.2,-.65],[.55,-.2,-.35],[.83,-.2,-.35],[.83,-.2,-.1],[1,-.2,-.1]]} color='#a5bc85' radius={.018}/>
 </group>
}
function Assembly({row,phase,selected,onSelect}:{row:Row;phase:string;selected:string;onSelect:(id:string)=>void}){
 return <>
 <ambientLight intensity={1.8}/><hemisphereLight args={['#e3e7d4','#1c3930',2]}/>
 <directionalLight position={[-4,8,6]} intensity={4} castShadow shadow-mapSize={[1024,1024]}/>
 <directionalLight position={[5,4,-5]} intensity={3} color='#89bcab'/>
 <Rotor angle={row.shaft_angle_rad} selected={selected==='rotary'} onSelect={()=>onSelect('rotary')}/>
 <Capacitor fill={row.energy_fill} selected={selected==='storage'} onSelect={()=>onSelect('storage')}/>
 <Circuit active={row.inference_active} clamp={phase!=='baseline'} selected={selected==='load'} onSelect={()=>onSelect('load')}/>
 {row.coupled&&<><group position={[2.8,0,-2.4]} onClick={e=>{e.stopPropagation();onSelect('receiver')}}><Box p={[0,-.3,0]} s={[1.7,.16,1.15]} c='#365345'/><Box p={[0,-.12,0]} s={[.45,.22,.4]} c='#192b25'/><Cylinder p={[.6,.4,0]} r={.028} h={1.4} c='#afbb9b'/><mesh position={[-.5,-.11,.3]}><sphereGeometry args={[.085,12,8]}/><meshStandardMaterial color={row.receiver_delivered?'#bbec88':'#5c6950'} emissive='#bbec88' emissiveIntensity={row.receiver_delivered?1.5:0}/></mesh></group><group position={[1.2,0,1.75]} onClick={e=>{e.stopPropagation();onSelect('sensor')}}><Box p={[0,-.29,0]} s={[.8,.1,.6]} c='#486454'/><Box p={[0,-.14,0]} s={[.28,.24,.28]} c={row.mcu_state==='sense'?'#76cec0':'#7f9185'}/></group><Wire points={[[1.2,-.2,1.75],[2,-.16,1.5],[2.4,-.16,.8]]} color='#7bba9d'/></>}
 <group position={[-1.3,0,.2]} onClick={e=>{e.stopPropagation();onSelect('rectifier')}}><Box p={[0,-.25,0]} s={[.75,.1,.8]}/><Box p={[0,-.1,0]} s={[.3,.2,.3]} c='#1c2722'/></group>
 <Wire points={[[-2.2,-.2,.92],[-1.6,-.16,.92],[-1.4,-.12,.45],[-1.3,-.12,.35]]}/>
 <Wire points={[[-1.2,-.12,.35],[-.7,-.13,.8],[.03,-.12,.75]]}/>
 <Wire points={[[.55,-.12,.68],[1.45,-.12,.9],[1.9,-.12,.7]]}/>
 <Wire points={[[3.7,-.18,-.5],[3.9,-.18,-1.15],[-3.9,-.18,-1.5],[-3.9,-.12,-.6]]} color='#597067' radius={.021}/>
 <mesh rotation={[-Math.PI/2,0,0]} position={[0,-.48,0]} receiveShadow><planeGeometry args={[200,200]}/><shadowMaterial transparent opacity={.28}/></mesh>
 <gridHelper args={[20,40,'#364c40','#283c32']} position={[0,-.46,0]}/>
 </>
}
class SceneBoundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true}}render(){return this.state.failed?<div className="scene-fallback">3D unavailable on this device. Use the component topology below; all traces remain available.</div>:this.props.children;}}
export function Scene({row,phase,selected,onSelect,reset=0}:{row:Row;phase:string;selected:string;onSelect:(id:string)=>void;reset?:number}){
 return <SceneBoundary><Suspense fallback={<div className="scene-fallback">Preparing the laboratory…</div>}><Canvas shadows orthographic camera={{position:[8,7,10],zoom:55,near:.1,far:100}} dpr={[1,1.5]} gl={{antialias:true,alpha:true}}><Controls reset={reset}/><Assembly row={row} phase={phase} selected={selected} onSelect={onSelect}/></Canvas></Suspense></SceneBoundary>;
}
