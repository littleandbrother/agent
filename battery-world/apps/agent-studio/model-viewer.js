import * as THREE from '/vendor/three/build/three.module.js';
import {OrbitControls} from '/vendor/three/examples/jsm/controls/OrbitControls.js';
import {GLTFLoader} from '/vendor/three/examples/jsm/loaders/GLTFLoader.js';
const $=s=>document.querySelector(s),stage=$('#stage');
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,2));stage.append(renderer.domElement);
renderer.setClearColor(0xf3f4ef);renderer.outputColorSpace=THREE.SRGBColorSpace;
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(38,1,.001,20),controls=new OrbitControls(camera,renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff,0x52685e,2.4));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(.4,.8,.6);scene.add(light);
let partNames=new Map();
let object,meshes=[],center=new THREE.Vector3(),radius=.15,inside=false,exploded=false;
function reset(){controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(1.6,1.1,2).multiplyScalar(radius));controls.update()}
function update(){for(const [i,m] of meshes.entries()){m.visible=!(inside&&['housing','cover'].includes(m.userData.role));m.position.copy(m.userData.original);if(exploded)m.position.add(m.userData.offset)}$('#inside').setAttribute('aria-pressed',inside);$('#explode').setAttribute('aria-pressed',exploded);controls.update()}
$('#reset').onclick=()=>{inside=false;exploded=false;update();$('#part').value='';reset()};$('#inside').onclick=()=>{inside=!inside;update()};$('#explode').onclick=()=>{exploded=!exploded;update()};
$('#part').onchange=e=>{const item=meshes.find(m=>m.name===e.target.value);if(!item){reset();return}const box=new THREE.Box3().setFromObject(item);controls.target.copy(box.getCenter(new THREE.Vector3()));camera.position.copy(controls.target).add(new THREE.Vector3(.06,.045,.065));controls.update()};
const observer=new ResizeObserver(()=>{const w=stage.clientWidth,h=stage.clientHeight;if(w&&h){renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix()}});observer.observe(stage);
const parameters=new URL(location.href).searchParams;
const job=parameters.get('job'),reference=parameters.get('case')==='pluck-v1';
if(/^eng-[a-f0-9]+$/.test(job||''))fetch('/api/engineering/jobs/'+job).then(r=>{if(!r.ok)throw Error('MODEL_METADATA');return r.json()}).then(j=>{partNames=new Map((j.assembly?.payload?.parts||[]).map(p=>[p.id,p.name]));for(const o of $('#part').options)if(partNames.has(o.value))o.textContent=partNames.get(o.value)}).catch(()=>{});
if(!reference&&!/^eng-[a-f0-9]+$/.test(job||''))$('#notice').textContent='模型编号无效';
else new GLTFLoader().load(reference?'/api/reference-case/artifact?name='+encodeURIComponent(parameters.get('artifact')||'cad/model.glb'):'/api/engineering/jobs/'+job+'/artifact?name=model.glb',g=>{
 object=g.scene;scene.add(object);const box=new THREE.Box3().setFromObject(object);box.getCenter(center);const size=box.getSize(new THREE.Vector3());radius=Math.max(size.x,size.y,size.z);
 object.traverse(m=>{if(!m.isMesh)return;m.userData.original=m.position.clone();const p=new THREE.Box3().setFromObject(m).getCenter(new THREE.Vector3()).sub(center);m.userData.offset=p.length()>.001?p.normalize().multiplyScalar(.04):new THREE.Vector3(0,.04,0);meshes.push(m);const o=document.createElement('option');o.value=m.name;o.textContent=partNames.get(m.name)||m.name;$('#part').append(o)});
 reset();$('#notice').textContent=meshes.length+' 个零件';$('#dimensions').textContent='实际模型包络 '+[size.x,size.z,size.y].map(v=>(v*1000).toFixed(1)).join(' × ')+' mm · 拖动旋转 / 滚轮缩放';
},undefined,e=>{$('#notice').textContent='加载失败，请检查此版本的模型产物';console.error(e)});
renderer.setAnimationLoop(()=>renderer.render(scene,camera));window.addEventListener('pagehide',()=>{renderer.setAnimationLoop(null);observer.disconnect();controls.dispose();scene.traverse(o=>{o.geometry?.dispose();const ms=Array.isArray(o.material)?o.material:[o.material];ms.forEach(m=>m?.dispose())});renderer.dispose()},{once:true});
