import * as THREE from '/vendor/three/build/three.module.js';
import {OrbitControls} from '/vendor/three/examples/jsm/controls/OrbitControls.js';
import {GLTFLoader} from '/vendor/three/examples/jsm/loaders/GLTFLoader.js';
const $=s=>document.querySelector(s),stage=$('#stage');
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,2));stage.append(renderer.domElement);
renderer.setClearColor(0xf7f8f9);renderer.outputColorSpace=THREE.SRGBColorSpace;
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(38,1,.001,20),controls=new OrbitControls(camera,renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff,0x52685e,2.4));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(.4,.8,.6);scene.add(light);
let partNames=new Map();
let object,meshes=[],center=new THREE.Vector3(),inside=false,exploded=false;
function fit(box){
 const target=box.getCenter(new THREE.Vector3()),direction=new THREE.Vector3(1.6,1.1,2).normalize(),right=new THREE.Vector3(0,1,0).cross(direction).normalize(),up=direction.clone().cross(right),tanV=Math.tan(THREE.MathUtils.degToRad(camera.fov/2)),tanH=tanV*camera.aspect;
 let distance=0;
 for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){
  const p=new THREE.Vector3(x,y,z).sub(target),depth=p.dot(direction);
  distance=Math.max(distance,depth+Math.abs(p.dot(up))/tanV,depth+Math.abs(p.dot(right))/tanH);
 }
 distance=Math.max(distance*1.15,.001);controls.target.copy(target);camera.position.copy(target).addScaledVector(direction,distance);camera.near=Math.max(distance/1000,.000001);camera.far=Math.max(distance*100,20);camera.updateProjectionMatrix();controls.update();
}
function reset(){if(object)fit(new THREE.Box3().setFromObject(object))}
function update(){for(const [i,m] of meshes.entries()){m.visible=!(inside&&['housing','cover'].includes(m.userData.role));m.position.copy(m.userData.original);if(exploded)m.position.add(m.userData.offset)}$('#inside').setAttribute('aria-pressed',inside);$('#explode').setAttribute('aria-pressed',exploded);controls.update()}
$('#reset').onclick=()=>{inside=false;exploded=false;update();$('#part').value='';reset()};$('#inside').onclick=()=>{inside=!inside;update()};$('#explode').onclick=()=>{exploded=!exploded;update();reset()};
$('#part').onchange=e=>{const item=meshes.find(m=>m.name===e.target.value);if(!item){reset();return}fit(new THREE.Box3().setFromObject(item))};
const observer=new ResizeObserver(()=>{const w=stage.clientWidth,h=stage.clientHeight;if(w&&h){renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix()}});observer.observe(stage);
const parameters=new URL(location.href).searchParams;
const resultFile=parameters.get('result_file'),resultSession=parameters.get('session'),resultUrl=resultFile&&resultSession?'/api/results/file?'+new URLSearchParams({session:resultSession,id:resultFile}):null;
const job=parameters.get('job')||(resultFile?.startsWith('eng-')?resultFile.split('/')[0]:null),reference=parameters.get('case')==='pluck-v1',meshPreview=parameters.get('mesh')==='1';
if(/^eng-[a-f0-9]+$/.test(job||''))fetch('/api/engineering/jobs/'+job).then(r=>{if(!r.ok)throw Error('MODEL_METADATA');return r.json()}).then(j=>{partNames=new Map((j.assembly?.payload?.parts||[]).map(p=>[p.id,p.name]));for(const o of $('#part').options)if(partNames.has(o.value))o.textContent=partNames.get(o.value)}).catch(()=>{});
if(!reference&&!resultUrl&&!/^eng-[a-f0-9]+$/.test(job||''))$('#notice').textContent='模型编号无效';
else if(meshPreview){
 fetch(resultUrl||'/api/engineering/jobs/'+job+'/artifact?name=project-preview-mesh.json').then(r=>{if(!r.ok)throw Error('MESH_MISSING');return r.json()}).then(m=>{
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(m.vertices.flat().map(x=>x/1000),3));geometry.setIndex(m.triangles.flat());geometry.computeVertexNormals();
 const solid=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:0xb6c6d5,roughness:.6,side:THREE.DoubleSide}));solid.name='STEP 原生实体';const group=new THREE.Group();group.add(solid);group.rotation.x=-Math.PI/2;loaded({scene:group});$('#notice').textContent='精确 STEP 的派生预览 · 非整机验收';$('#inside').disabled=true;$('#explode').disabled=true;
 }).catch(()=>{$('#notice').textContent='该结果还没有 STEP 派生预览，请下载原生工程'});
}
else new GLTFLoader().load(resultUrl||(reference?'/api/reference-case/artifact?name='+encodeURIComponent(parameters.get('artifact')||'cad/model.glb'):'/api/engineering/jobs/'+job+'/artifact?name=model.glb'),loaded,undefined,e=>{$('#notice').textContent='加载失败，请检查此版本的模型产物';console.error(e)});
function loaded(g){
 object=g.scene;scene.add(object);const box=new THREE.Box3().setFromObject(object);box.getCenter(center);const size=box.getSize(new THREE.Vector3());
 object.traverse(m=>{if(!m.isMesh)return;m.userData.original=m.position.clone();const p=new THREE.Box3().setFromObject(m).getCenter(new THREE.Vector3()).sub(center);m.userData.offset=Array.isArray(m.userData.explosionOffsetM)?new THREE.Vector3(...m.userData.explosionOffsetM):(p.length()>.001?p.normalize().multiplyScalar(.04):new THREE.Vector3(0,.04,0));meshes.push(m);if(['pad','copper'].includes(m.userData.role))return;const o=document.createElement('option');o.value=m.name;o.textContent=partNames.get(m.name)||m.userData.label||m.name;$('#part').append(o)});
 const parts=meshes.filter(m=>!['pad','copper'].includes(m.userData.role));
 $('#inside').disabled=!meshes.some(m=>['housing','cover'].includes(m.userData.role));
 $('#explode').disabled=meshes.every(m=>m.userData.offset.length()===0);
 reset();$('#notice').textContent=parts.length+' 个零件';$('#dimensions').textContent='模型包络 '+[size.x,size.z,size.y].map(v=>(v*1000).toFixed(1)).join(' × ')+' mm · '+(object.userData.scope||'拖动旋转 / 滚轮缩放');
}
renderer.setAnimationLoop(()=>renderer.render(scene,camera));window.addEventListener('pagehide',()=>{renderer.setAnimationLoop(null);observer.disconnect();controls.dispose();scene.traverse(o=>{o.geometry?.dispose();const ms=Array.isArray(o.material)?o.material:[o.material];ms.forEach(m=>m?.dispose())});renderer.dispose()},{once:true});
