import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { Reflector } from 'three/addons/objects/Reflector.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';
import { FontLoader } from 'three/addons/loaders/FontLoader.js';
import titleTypeface from './fonts/inter-titles.json';
import { createStudioDetails } from './details.js';
import { createStudioScreens } from './screens.js';

export const AGENTS = Object.freeze([
  {id:'mechanical', name:'Mechanical', zh:'机械设计', color:'#efa043', short:'M', glyph:'⚙', subtitle:'From form to function.', x:-5.15, z:-3.45, yawDeg:35},
  {id:'circuit', name:'Circuit', zh:'电路设计', color:'#28bbc3', short:'C', glyph:'▥', subtitle:'Ideas into reliable electronics.', x:5.15, z:-3.45, yawDeg:-35},
  {id:'pcb', name:'PCB', zh:'PCB 布局', color:'#78b867', short:'P', glyph:'▦', subtitle:'Routes for a connected world.', x:-6.0, z:1.85, yawDeg:70},
  {id:'power', name:'Power', zh:'能量与功耗', color:'#eac14d', short:'E', glyph:'☀', subtitle:'Harvests energy from the environment.', x:6.0, z:1.85, yawDeg:-70},
  {id:'firmware', name:'Firmware', zh:'单片机代码', color:'#9c7bdd', short:'F', glyph:'</>', subtitle:'Brings intelligence to life.', x:0, z:6.3, yawDeg:0},
]);
export const DEMO_DURATION = 96;
export const DEMO_STAGES = Object.freeze([
  {at:0, label:'各专业独立工作', labelEn:'INDEPENDENT WORK', members:[], topic:'五个专业，朝着同一个目标。', statuses:['work','work','work','work','work']},
  {at:15, label:'机械 × 电路 · 接口讨论', labelEn:'MECHANICAL × CIRCUIT', members:['mechanical','circuit'], topic:'机械间隙与前端灵敏度需要一起检查。'},
  {at:30, label:'返回工位 · 修改方案', labelEn:'BACK TO WORK', members:[], topic:'结论带回各自的工作间，继续设计。'},
  {at:40, label:'PCB × 功耗 × 固件 · 联合讨论', labelEn:'LAYOUT × ENERGY × CODE', members:['pcb','power','firmware'], topic:'布局、能量预算和执行时序一起对齐。'},
  {at:58, label:'返回工位 · 专业验证', labelEn:'SPECIALIST VALIDATION', members:[], topic:'各专业根据讨论结果完成自己的工作。'},
  {at:68, label:'全体会合 · Dot 总体评审', labelEn:'INTEGRATION REVIEW', members:['mechanical','circuit','pcb','power','firmware'], topic:'Dot 汇总五个专业，检查系统是否可以协同工作。'},
  {at:84, label:'集成成果 · 装配展示', labelEn:'IDEAS TO IMPACT', members:['mechanical','circuit','pcb','power','firmware'], topic:'演示装配完成。一起把想法变成作品。', assembled:true},
  {at:91, label:'返回工位 · 下一轮工作', labelEn:'A NEW ITERATION', members:[], topic:'讨论结束，回到自己的位置。'},
]);

const TAU = Math.PI * 2;
const clamp = THREE.MathUtils.clamp;
const ease = t => t*t*(3-2*t);
const ink = '#152c43';
const PALETTE = {white:0xf5f7fb, chrome:0xced9e3, dark:0x142639, blue:0x85cbff};
let areaLightsInitialized=false;

/**
 * Presentation-only Three.js scene. All runtime state lives inside this instance.
 * The host keeps execution/evidence authority; dispatch() only changes this view.
 */
export function createAgentStudio(container, options={}) {
  if (!(container instanceof HTMLElement)) throw new TypeError('A DOM container is required.');
  const hadHostClass = container.classList.contains('agent-studio');
  container.classList.add('agent-studio');
  const assetBase = options.assetBase || new URL('../assets/', import.meta.url).href;
  const quality = options.quality || 'auto';
  const reduced = options.reducedMotion ?? window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let mode = options.mode || 'demo';
  if (!['demo','live'].includes(mode)) throw new TypeError('mode must be demo or live');
  let paused = !!options.paused || reduced, speed = 1, disposed = false, demoTime = 0, visualTime = 0, stageIndex = -1;
  let meeting = null, liveTime = 0, animationFrame = 0, dotMessage = '';
  let currentCamera = 'overview';
  let cameraTransition = null;
  let lastFrame = performance.now(), needsRender = true;
  const eventIds = new Set();
  const acceptedEvents = [], labels = [], connectors = [], holo = [], installations = [], stations = [];
  const textures = new Set(), materials = new Set(), geometries = new Set();
  const agents = new Map();
  const listeners = new Set();
  const errors = [];

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xcbd9e9);
  scene.fog = new THREE.Fog(0xd6e2ef, 46, 100);
  const camera = new THREE.PerspectiveCamera(35, 1, .1, 120);
  const renderer = new THREE.WebGLRenderer({antialias:true, alpha:false, powerPreference:'high-performance'});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality === 'low' ? 1 : 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = .86;
  renderer.transmissionResolutionScale = .65;
  renderer.info.autoReset = false;
  renderer.shadowMap.enabled = quality !== 'low';
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.domElement.className = 'studio-canvas';
  renderer.domElement.setAttribute('aria-label','可旋转的三维 Agent 工作室：机械、电路、PCB、功耗、固件和 Dot');
  renderer.domElement.setAttribute('role','img');
  renderer.domElement.tabIndex = 0;
  container.appendChild(renderer.domElement);
  const overlay = document.createElement('div');
  overlay.className = 'studio-label-layer';
  container.appendChild(overlay);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = .065;
  controls.minDistance = 5; controls.maxDistance = 85;
  controls.minPolarAngle = .3; controls.maxPolarAngle = Math.PI*.49;
  controls.maxTargetRadius = 15; controls.enablePan = true;
  const onControlStart = () => {cameraTransition = null; currentCamera = 'free'; notify();};
  controls.addEventListener('start', onControlStart);
  const onControlsChange=()=>{needsRender=true;};controls.addEventListener('change',onControlsChange);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const roomEnv = new RoomEnvironment();
  const envTarget = pmrem.fromScene(roomEnv, .025, .1, 100, {size:128});
  scene.environment = envTarget.texture;
  scene.environmentIntensity = .55;
  roomEnv.dispose(); pmrem.dispose();

  function mat(color, extra={}) {
    const m = new THREE.MeshPhysicalMaterial({color, roughness:.19, metalness:.08, clearcoat:1, clearcoatRoughness:.08, ...extra});
    materials.add(m); return m;
  }
  const white = mat(0xeaf0f7,{roughness:.21,metalness:.12}), chrome = mat(0xbdcddd,{metalness:1,roughness:.17});
  const pale = mat(0x92a9bf,{metalness:.85,roughness:.22});
  const black = mat(0x07111f,{metalness:.15,roughness:.18,clearcoat:.9});
  const glass = mat(0xe5f5ff,{transmission:quality==='low'?0:.90, thickness:.13, ior:1.46, transparent:quality==='low', opacity:quality==='low'?.16:1, roughness:.025, metalness:0, depthWrite:false, side:THREE.DoubleSide,attenuationColor:0xa9d5ff,attenuationDistance:4});
  const softGlass = mat(0xb7deff,{transparent:true,opacity:.20,roughness:.055,metalness:.32,depthWrite:false,side:THREE.DoubleSide});
  // Thin partitions stay clear, so a turned workstation never blurs its robot.
  // Thick tabletops and device windows retain the transmissive glass material.
  const partitionGlass=mat(0xd9edff,{transparent:true,opacity:.105,roughness:.035,metalness:.12,clearcoat:1,depthWrite:false,side:THREE.DoubleSide});
  const blueGlow = mat(0x1385ed,{emissive:0x1385ff,emissiveIntensity:2.8,roughness:.08});
  const goldMetal = mat(0xd6ae55,{metalness:.82,roughness:.23});
  const boardMat = mat(0x155640,{roughness:.42,metalness:.15});
  const loader = new THREE.TextureLoader();
  function asset(name) {
    const tex = loader.load(options.assetUrls?.[name] || new URL(name+'.webp', assetBase).href, () => {needsRender=true;}, undefined, () => {errors.push('Asset missing: '+name); notify();});
    tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = Math.min(8,renderer.capabilities.getMaxAnisotropy());
    textures.add(tex); return tex;
  }
  const refTextures = {
    skyline:asset('skyline'),
  };
  function mesh(geom, material, parent, x=0,y=0,z=0) {
    geometries.add(geom);
    const m = new THREE.Mesh(geom, material); m.position.set(x,y,z);
    m.castShadow = material !== glass && material !== softGlass;
    m.receiveShadow = true;
    parent.add(m); return m;
  }
  function box(parent,w,h,d,material,x=0,y=0,z=0,r=.05) {return mesh(r<=.018?new THREE.BoxGeometry(w,h,d):new RoundedBoxGeometry(w,h,d,2,Math.min(r,w/2,h/2,d/2)),material,parent,x,y,z);}
  function cyl(parent,r,h,material,x=0,y=0,z=0,segments=64,rTop=r) {return mesh(new THREE.CylinderGeometry(rTop,r,h,segments),material,parent,x,y,z);}
  function sphere(parent,r,material,x=0,y=0,z=0,sx=1,sy=1,sz=1) {const m=mesh(new THREE.SphereGeometry(r,r>=.4?40:20,r>=.4?28:14),material,parent,x,y,z); m.scale.set(sx,sy,sz); return m;}
  function torus(parent,r,t,material,x=0,y=0,z=0,horizontal=true) {const m=mesh(new THREE.TorusGeometry(r,t,8,r>1?96:r>.25?64:32),material,parent,x,y,z); if(horizontal)m.rotation.x=Math.PI/2; return m;}
  function line(parent,points,material,r=.012) {return mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p))),Math.max(8,Math.min(256,points.length*3)),r,6,false),material,parent);}
  function plane(parent,w,h,material,x=0,y=0,z=0) {return mesh(new THREE.PlaneGeometry(w,h),material,parent,x,y,z);}
  function canvasTex(w,h,draw) {
    const c=document.createElement('canvas'); c.width=w;c.height=h;
    const ctx=c.getContext('2d'); draw(ctx,c);
    const tex=new THREE.CanvasTexture(c); tex.colorSpace=THREE.SRGBColorSpace;
    tex.anisotropy=Math.min(16,renderer.capabilities.getMaxAnisotropy());textures.add(tex);return tex;
  }
  const screens=createStudioScreens(canvasTex);
  const titleFont=new FontLoader().parse(titleTypeface);
  function workstationTitle(parent,config) {
    // Letter outlines are geometry, not a reduced raster texture. Keep the
    // board opaque, with no tiny subtitle or light spilling across the ink.
    box(parent,3.86,.81,.095,white,0,3.25,-.83,.08);
    const paper=new THREE.MeshBasicMaterial({color:0xfafcfe,toneMapped:false,fog:false});materials.add(paper);
    const board=plane(parent,3.75,.78,paper,0,3.25,-.77);board.castShadow=false;board.receiveShadow=false;
    iconPlate(parent,config.color,config.glyph,-1.52,3.25,-.735,.135);
  const geometry=new THREE.ShapeGeometry(titleFont.generateShapes(config.name,.28),12);
    geometry.computeBoundingBox();const bounds=geometry.boundingBox;
    const scale=Math.min(1,2.82/(bounds.max.x-bounds.min.x));
    const inkMaterial=new THREE.MeshBasicMaterial({color:0x2b4156,toneMapped:false,fog:false});materials.add(inkMaterial);
    const title=mesh(geometry,inkMaterial,parent,-1.23-bounds.min.x*scale,3.25-(bounds.max.y+bounds.min.y)*scale/2,-.73);
    title.scale.setScalar(scale);title.castShadow=false;title.receiveShadow=false;
  }
  function textPanel(parent,text,w,h,color=ink,background='rgba(249,251,255,.85)') {
    const tex=canvasTex(768,180,(c)=>{c.fillStyle=background;c.fillRect(0,0,768,180);c.fillStyle=color;c.font='500 36px Arial';c.textAlign='center';c.fillText(text,384,105);});
    const m=new THREE.MeshBasicMaterial({map:tex,transparent:true,side:THREE.DoubleSide});materials.add(m);
    return plane(parent,w,h,m);
  }
  function iconPlate(parent,color,glyph,x,y,z,r=.16) {
    const tex=canvasTex(128,128,c=>{c.fillStyle=color;c.beginPath();c.arc(64,64,61,0,TAU);c.fill();c.fillStyle='white';c.textAlign='center';c.textBaseline='middle';c.font=glyph.length>1?'bold 38px Arial':'bold 65px Arial';c.fillText(glyph,64,65);});
    const m=new THREE.MeshBasicMaterial({map:tex,transparent:true});materials.add(m);return plane(parent,r*2,r*2,m,x,y,z);
  }
  function glowMaterial(color, intensity=1) {return mat(color,{emissive:color,emissiveIntensity:intensity,roughness:.25,metalness:.2});}
  const details=createStudioDetails({box,cyl,torus,line,plane,mesh,mat,canvasTex,textPanel,pcb,
    white,chrome,pale,black,glass,softGlass,goldMetal,blueGlow,glowMaterial,quality});
  chrome.roughnessMap=details.brushing;

  // Bake immobile parts together, keeping articulated joints and moving exhibits
  // separate. Polished glass and bloom stay affordable without thousands of draws.
  function batchStaticMeshes(group, excluded=[]) {
    group.updateWorldMatrix(true,true);
    const inverse=group.matrixWorld.clone().invert(), batches=new Map();
    group.traverse(obj=>{
      if(!obj.isMesh||Array.isArray(obj.material))return;
      for(let p=obj;p&&p!==group;p=p.parent)if(excluded.includes(p))return;
      const key=obj.material.uuid+':'+obj.castShadow+':'+obj.receiveShadow;
      if(!batches.has(key))batches.set(key,[]);batches.get(key).push(obj);
    });
    for(const objects of batches.values()){
      if(objects.length<2)continue;
      const parts=objects.map(obj=>{
        let geometry=obj.geometry.clone();
        if(geometry.index){const flat=geometry.toNonIndexed();geometry.dispose();geometry=flat;}
        geometry.applyMatrix4(inverse.clone().multiply(obj.matrixWorld));return geometry;
      });
      const merged=mergeGeometries(parts,false);parts.forEach(g=>g.dispose());
      if(!merged)continue;
      merged.computeBoundingSphere();geometries.add(merged);
      const obj=new THREE.Mesh(merged,objects[0].material);obj.castShadow=objects[0].castShadow;obj.receiveShadow=objects[0].receiveShadow;
      objects.forEach(o=>o.removeFromParent());group.add(obj);
    }
  }

  // A warm directional key, cooler fill and rear rim preserve shape in the
  // white atrium. Large soft sources create readable glass/metal highlights.
  scene.add(new THREE.HemisphereLight(0xdfeeff,0x4b617c,.38));
  const sun=new THREE.DirectionalLight(0xffefdb,2.55);sun.position.set(-8,14,7);sun.castShadow=quality!=='low';
  sun.shadow.mapSize.set(2048,2048);sun.shadow.camera.left=-17;sun.shadow.camera.right=17;sun.shadow.camera.top=16;sun.shadow.camera.bottom=-16;sun.shadow.camera.near=1;sun.shadow.camera.far=46;sun.shadow.bias=-.00025;sun.shadow.normalBias=.022;sun.shadow.radius=2.5;scene.add(sun);
  const fill=new THREE.DirectionalLight(0xb4d1f5,.82);fill.position.set(12,9,4);scene.add(fill);
  const rim=new THREE.DirectionalLight(0xc5e4ff,1.1);rim.position.set(2,10,-10);scene.add(rim);
  const front=new THREE.DirectionalLight(0xffffff,.28);front.position.set(0,8,20);scene.add(front);
  if(quality!=='low'){
    if(!areaLightsInitialized){RectAreaLightUniformsLib.init();areaLightsInitialized=true;}
    const windowLight=new THREE.RectAreaLight(0xfff0df,1.0,9,6);windowLight.position.set(-9,7,4);windowLight.lookAt(0,1,0);scene.add(windowLight);
    const softbox=new THREE.RectAreaLight(0xc9e2ff,.75,7,4);softbox.position.set(9,6,-5);softbox.lookAt(0,1,0);scene.add(softbox);
  }
  const coreLight=new THREE.PointLight(0x2789ff,6.5,7.5,2);coreLight.position.set(0,2.1,0);scene.add(coreLight);
  const floorGroup=new THREE.Group();scene.add(floorGroup);
  const floor=mesh(new THREE.PlaneGeometry(80,80),mat(0xb8c9df,{metalness:.38,roughness:.12}),floorGroup,0,-.055,0);floor.rotation.x=-Math.PI/2;
  let mirror;
  if(quality!=='low') {
    mirror=new Reflector(new THREE.PlaneGeometry(58,58),{textureWidth:768,textureHeight:768,color:0xb7c5d6,multisample:0});
    mirror.rotation.x=-Math.PI/2;mirror.position.y=-.044;scene.add(mirror);
    const veil=plane(floorGroup,58,58,mat(0xa5b9d2,{transparent:true,opacity:.33,roughness:.08,metalness:.35,depthWrite:false}),0,-.030,0);veil.rotation.x=-Math.PI/2;veil.castShadow=false;
    const groundShadow=new THREE.ShadowMaterial({color:0x10233a,opacity:.22,depthWrite:false});materials.add(groundShadow);
    const shadowCatcher=plane(floorGroup,58,58,groundShadow,0,-.018,0);shadowCatcher.rotation.x=-Math.PI/2;shadowCatcher.castShadow=false;
  }
  const seamMat=mat(0xc4d1df,{roughness:.4,metalness:.2});
  for(let v=-32;v<=32;v+=4){box(floorGroup,64,.012,.018,seamMat,0,-.023,v,.003);box(floorGroup,.018,.012,64,seamMat,v,-.023,0,.003);}
  for(let v=-14;v<=14;v+=7){box(floorGroup,26,.012,.024,glowMaterial(0xffe6b3,.8),0,-.01,v,.004);}

  const beaconGlass=mat(0x8acbff,{transparent:true,opacity:.28,roughness:.04,metalness:.3,depthWrite:false});
  const beaconLight=glowMaterial(0x6acaff,1.8);
  function techBeacon(parent,x,y,z,scale=1,seed=0) {
    const p=new THREE.Group();p.position.set(x,y,z);p.scale.setScalar(scale);parent.add(p);
    p.name='technology-beacon';
    cyl(p,.22,.10,chrome,0,.05,0,32);cyl(p,.18,.025,black,0,.114,0,32);
    torus(p,.19,.013,beaconLight,0,.126,0);
    box(p,.23,.81,.23,beaconGlass,0,.56,0,.035);
    for(const side of [-1,1]){
      box(p,.015,.78,.017,chrome,side*.128,.56,0,.004);
      box(p,.006,.62,.013,beaconLight,side*.128,.56,.124,.002);
    }
    const core=mesh(new THREE.OctahedronGeometry(.112),blueGlow,p,0,.65,0);core.rotation.y=seed;
    holo.push({obj:core,kind:'beacon',base:.65,seed});
    torus(p,.18,.009,beaconLight,0,.88,0);
    installations.push(p);return p;
  }
  const room=new THREE.Group();scene.add(room);
  const skylineMaterial=new THREE.MeshBasicMaterial({map:refTextures.skyline,color:0xeef3ff});materials.add(skylineMaterial);
  plane(room,52,11,skylineMaterial,0,6.8,-18);
  const windowGlass=mat(0xe7f3ff,{transparent:true,opacity:.10,depthWrite:false,roughness:.04});
  for(let x=-23;x<=23;x+=3.2){box(room,.12,11,.18,white,x,5.5,-15.7);box(room,.035,11,.03,chrome,x+.12,5.5,-15.59);}
  box(room,52,.13,.24,white,0,10.3,-15.7);box(room,52,.12,.24,white,0,2.15,-15.7);
  plane(room,52,10.5,windowGlass,0,5.3,-15.66);
  for(const side of [-1,1]) {
    // Open side boundaries allow an orbit or wide pullback without wall occlusion.
    // Low exhibits also keep the former perimeter columns out of the camera path.
    for(let z=-14;z<12;z+=6.2)techBeacon(room,side*16.8,0,z,1.7,z);
  }
  for(const x of [-11.4,11.4]) {
    const shelf=new THREE.Group();shelf.position.set(x,0,-12.5);room.add(shelf);
    for(const xx of [-1.7,1.7])box(shelf,.11,7,.13,chrome,xx,3.5,0);
    for(let y=.65;y<7;y+=1.35){box(shelf,3.5,.09,1.3,glass,0,y,0);for(let n=0;n<3;n++)techBeacon(shelf,-1.1+n*1.05,y,0,.75,n+y);}
  }
  for(const x of [-6,-1,3,7])techBeacon(room,x,0,-13,1.9,x);
  // A quiet glass atrium with suspended blue technology exhibits.
  box(room,3.5,.48,1.5,white,0,.4,-11,.22);box(room,3.5,.9,.25,white,0,.95,-11.6,.1);
  cyl(room,.85,.12,glass,0,.6,-9.3);cyl(room,.08,.5,chrome,0,.3,-9.3);techBeacon(room,0,.66,-9.3,.55);
  details.room(room);

  function monitor(parent,w,h,x,y,z,texture,color) {
    const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);
    box(g,w+.1,h+.1,.13,black,0,0,0,.07);box(g,w+.14,h+.14,.09,chrome,0,0,-.04,.055);
    const m=new THREE.MeshBasicMaterial({map:texture,toneMapped:false});materials.add(m);
    plane(g,w,h,m,0,0,.074);
    box(g,.085,y-.67,.085,chrome,0,-(y-.67)/2-h/2,0,.01);box(g,.48,.045,.36,chrome,0,-y+.59,.08);
    box(g,w-.04,.012,.019,glowMaterial(color,.4),0,-h/2-.03,.075,.004);
    return g;
  }
  function pcb(parent,x,y,z,size=1) {
    const g=new THREE.Group();g.position.set(x,y,z);g.scale.setScalar(size);parent.add(g);
    box(g,1.05,.045,.7,boardMat,0,0,0,.028);
    details.board(g);return g;
  }
  function books(parent,x,y,z,color,words) {
    const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);
    words.forEach((s,i)=>{
      box(g,.6,.115,.36,white,0,i*.13,0,.014);box(g,.61,.012,.37,pale,0,i*.13+.064,0,.005);
      const p=textPanel(g,s,.55,.092,'#556477','rgba(246,249,255,1)');p.position.set(0,i*.13,.186);
    });return g;
  }
  function mug(parent,x,y,z,color=0xffffff) {
    const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);
    cyl(g,.12,.24,mat(color),0,.12,0,32);cyl(g,.1,.008,black,0,.243,0,24);const handle=torus(g,.088,.018,white,.135,.125,0,false);handle.rotation.y=Math.PI/2;return g;
  }
  function laptop(parent,x,y,z,color) {
    const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);
    box(g,.66,.035,.43,pale,0,0,0,.025);
    const lid=new THREE.Group();lid.position.set(0,.018,-.19);lid.rotation.x=-.21;g.add(lid);
    box(lid,.66,.42,.029,chrome,0,.21,0,.02);
    const tex=canvasTex(512,300,c=>{c.fillStyle='#1e2c40';c.fillRect(0,0,512,300);c.fillStyle=color;c.font='18px monospace';for(let i=0;i<11;i++)c.fillText(['// agent workspace','const model = compile();','await tool.run(task);','validate(result);'][i%4],18,35+i*23);});
    const m=new THREE.MeshBasicMaterial({map:tex,toneMapped:false});materials.add(m);plane(lid,.6,.36,m,0,.21,.018);
    for(let r=0;r<4;r++)for(let c=0;c<10;c++)box(g,.039,.009,.025,black,-.232+c*.051,.024,-.096+r*.040,.004);
    box(g,.18,.004,.087,chrome,0,.023,.117,.008);return g;
  }

  const contactTexture=canvasTex(128,128,c=>{const g=c.createRadialGradient(64,64,25,64,64,64);g.addColorStop(0,'rgba(44,66,88,.35)');g.addColorStop(.55,'rgba(44,66,88,.14)');g.addColorStop(1,'rgba(44,66,88,0)');c.fillStyle=g;c.fillRect(0,0,128,128);});
  const contactMaterial=new THREE.MeshBasicMaterial({map:contactTexture,transparent:true,depthWrite:false,toneMapped:false});materials.add(contactMaterial);
  function makeStation(config) {
    const g=new THREE.Group();g.position.set(config.x,0,config.z);scene.add(g);
    g.userData.agent=config.id;
    const contact=plane(g,5.6,5.6,contactMaterial,0,.014,0);contact.rotation.x=-Math.PI/2;
    g.rotation.y=THREE.MathUtils.degToRad(config.yawDeg);
    g.userData.home=g.position.clone();
    const outward=new THREE.Vector3(config.x,0,config.z).normalize();
    g.userData.expanded=g.position.clone().add(outward.multiplyScalar(config.id==='firmware'?4.9:2.35));
    g.userData.spread=0;
    g.userData.spreadFrom=0;g.userData.spreadTarget=0;g.userData.spreadStart=0;g.userData.spreadDuration=2.8;
    const colorMat=mat(config.color,{metalness:.45,roughness:.2});
    const lightMat=glowMaterial(config.color,.7);
    cyl(g,2.35,.32,white,0,.22,0);cyl(g,2.4,.055,chrome,0,.41,0);cyl(g,2.29,.065,glass,0,.49,0);torus(g,2.34,.018,lightMat,0,.48,0);
    cyl(g,2.36,.028,chrome,0,.066,0);torus(g,2.23,.027,white,0,.043,0);
    const arc=new THREE.CylinderGeometry(2.3,2.3,1.96,80,1,true,Math.PI*.18,Math.PI*1.64);
    const partition=mesh(arc,partitionGlass,g,0,1.43,0);partition.castShadow=false;partition.receiveShadow=false;geometries.add(arc);
    for(const yy of [.49,2.42]){
      const pts=[];for(let a=.18*Math.PI;a<1.83*Math.PI;a+=.04)pts.push([Math.sin(a)*2.3,yy,Math.cos(a)*2.3]);
      line(g,pts,chrome,yy>1?.018:.031);line(g,pts.map(([x,y,z])=>[x,y+.021,z]),lightMat,yy>1?.005:.008);
    }
    for(const a of [.18*Math.PI,.65*Math.PI,1.35*Math.PI,1.82*Math.PI]){
      const xx=Math.sin(a)*2.3,zz=Math.cos(a)*2.3;
      box(g,.05,1.95,.05,chrome,xx,1.45,zz,.012);box(g,.085,.18,.09,pale,xx,.61,zz,.016);
    }
    workstationTitle(g,config);
    if(config.id==='circuit') {
      monitor(g,2.45,1.23,-.55,1.89,-.84,screens.circuit,config.color);
      monitor(g,1.13,1.18,1.3,1.85,-.70,screens.signal,config.color);
      const scope=new THREE.Group();scope.position.set(1.24,.79,.23);g.add(scope);box(scope,.82,.44,.38,white);const scopeMat=new THREE.MeshBasicMaterial({map:screens.signal,toneMapped:false});materials.add(scopeMat);plane(scope,.55,.28,scopeMat,-.06,0,.2);
      for(let i=0;i<3;i++)cyl(scope,.029,.025,chrome,.30,-.11+i*.105,.20,16).rotation.x=Math.PI/2;
      pcb(g,.38,.54,1.25,.72);
      for(let i=0;i<3;i++){cyl(g,.055,.43,chrome,-1.56+i*.16,.75,-.35,24);cyl(g,.065,.12,black,-1.56+i*.16,.55,-.35,24);}
    } else if(config.id==='mechanical') {
      monitor(g,3.37,1.57,0,1.9,-.82,screens.mechanical,config.color);
      for(let i=0;i<4;i++){torus(g,.29-i*.033,.043,chrome,-1.15+i*.34,.57,.92+(i%2)*.47);cyl(g,.10,.11,chrome,-1.24+i*.68,.56,.24,32);}
      box(g,.83,.018,.58,white,.8,.505,1.28,.008);
      box(g,.54,.045,.035,chrome,1.20,.54,.82,.008);box(g,.08,.12,.25,black,1.32,.58,.80,.012);
      for(let i=0;i<3;i++){box(g,.10,.93,.11,chrome,-1.6+i*.21,1.0,-.48,.02);box(g,.16,.19,.21,black,-1.6+i*.21,.96,-.48,.025);}
    } else if(config.id==='pcb') {
      monitor(g,3.16,1.58,-.16,1.93,-.80,screens.pcb,config.color);
      for(let i=0;i<3;i++){const p=pcb(g,1.35,.69+i*.38,-.30,.68);p.rotation.z=.07;}
      pcb(g,.54,.56,1.13,.94);
      const sample=new THREE.Group();sample.position.set(-1.36,.79,.97);g.add(sample);box(sample,.58,.48,.13,glass);const b=pcb(sample,0,0,.1,.48);b.rotation.x=Math.PI/2;
    } else if(config.id==='power') {
      monitor(g,3.49,1.38,0,1.89,-.83,screens.power,config.color);
      const cap=new THREE.Group();cap.position.set(.97,.51,.67);g.add(cap);
      cyl(cap,.20,.73,chrome,0,.43,0,48);cyl(cap,.125,.055,chrome,0,.85,0,32);cyl(cap,.105,.07,black,0,.92,0,32);
      const charge=cyl(cap,.204,.48,lightMat,0,.34,0,48);charge.material=mat(config.color,{transparent:true,opacity:.4,emissive:config.color,emissiveIntensity:1});holo.push({obj:charge,kind:'charge',base:.48});
      torus(cap,.32,.018,lightMat,0,.02,0);torus(cap,.28,.013,lightMat,0,.20,0);
      pcb(g,1.37,.55,1.25,.68);cyl(g,.10,.27,black,1.23,.69,1.22,24);
      for(let i=0;i<9;i++)torus(g,.10,.009,goldMetal,1.23,.57+i*.023,1.22);
      box(g,.52,.36,.25,chrome,-1.44,.70,-.13,.03);for(let i=0;i<8;i++)box(g,.025,.30,.27,chrome,-1.66+i*.06,.71,-.13,.004);
    } else {
      monitor(g,3.58,1.37,0,1.93,-.80,screens.firmware,config.color);
      monitor(g,.83,.77,1.77,1.13,.15,screens.runtime,config.color).rotation.y=-.28;
      pcb(g,.85,.54,1.16,.85);
      box(g,.57,.05,.20,white,-1.55,.55,.9,.018);for(let i=0;i<10;i++)box(g,.02,.008,.14,black,-1.77+i*.047,.58,.9,.002);
    }
    books(g,-1.12,.57,1.20,config.color,config.id==='firmware'?['EMBEDDED C','LOW POWER','PROTOCOLS']:config.id==='power'?['HARVEST','CONVERT','STORE']:config.id==='mechanical'?['DESIGN','PROTOTYPE','TEST']:['DESIGN RULES','VALIDATION','REAL IMPACT']);
    techBeacon(g,-1.81,.52,-.20,.65,config.x);
    mug(g,1.43,.50,1.43);
    // The console sits between the specialist and the big screen, facing +Z.
    box(g,1.42,.065,.70,glass,0,1.04,.10,.035);box(g,1.43,.018,.71,chrome,0,1.0,.10,.012);
    for(const x of [-.58,.58])box(g,.034,.47,.034,chrome,x,.77,.05,.007);
    laptop(g,0,1.09,.08,config.color);
    details.workstation(g,config);
    const footer=textPanel(g,config.id==='firmware'?'SENSE · CONNECT · THINK · ACT · THRIVE':'DIFFERENT EXPERTISES · A BRIGHTER TOMORROW',3.2,.2,'#7b8b9b');footer.position.set(0,.23,2.348);
    stations.push(g);return g;
  }
  AGENTS.forEach(makeStation);

  function makeRobot(config) {
    const root=new THREE.Group(), body=new THREE.Group();root.add(body);scene.add(root);
    const accent=mat(config.color,{metalness:.46,roughness:.12});
    const glow=glowMaterial(config.color,2.2);
    const visor=mat(0x030a16,{metalness:.05,roughness:.11,clearcoat:1,clearcoatRoughness:.09,envMapIntensity:.22});
    // Small pear-shaped body, large round head, slim joints and tiny soft hands.
    sphere(body,.236,white,0,.48,0,1,1.15,.85);
    sphere(body,.185,accent,0,.355,-.025,1,.40,.87);
    cyl(body,.10,.07,pale,0,.75,0,32);
    const head=new THREE.Group();head.position.set(0,1.035,0);body.add(head);
    sphere(head,.48,white,0,0,0,1.08,.97,1);
    const cap=mesh(new THREE.SphereGeometry(.484,40,20,0,TAU,0,.48),accent,head);cap.scale.set(1.08,.97,1);
    sphere(head,.50,accent,0,-.016,.27,.855,.473,.477);
    sphere(head,.50,visor,0,-.016,.310,.840,.456,.470);
    const eyes=new THREE.Group();head.add(eyes);
    for(const x of [-.16,.16]){
      const points=[];for(let j=0;j<=16;j++){
        const a=Math.PI-j/16*Math.PI,xx=x+Math.cos(a)*.060,yy=-.020+Math.sin(a)*.064;
        const zz=.310+.235*Math.sqrt(Math.max(.1,1-(xx/.420)**2-((yy+.016)/.228)**2))+.009;
        points.push([xx,yy,zz]);
      }
      line(eyes,points,glow,.013);
    }
    // Restrained ear discs keep the silhouette compact.
    for(const side of [-1,1]){
      const outer=cyl(head,.128,.066,chrome,side*.494,-.018,-.025,40);outer.rotation.z=Math.PI/2;
      const ear=cyl(head,.104,.075,accent,side*.512,-.018,-.025,40);ear.rotation.z=Math.PI/2;
      const inner=cyl(head,.070,.082,pale,side*.529,-.018,-.025,32);inner.rotation.z=Math.PI/2;
      torus(head,.077,.008,glow,side*.574,-.018,-.025,false).rotation.y=Math.PI/2;
    }
    sphere(head,.021,glow,0,.485,-.045);
    const arms=[];
    for(const side of [-1,1]){
      const arm=new THREE.Group();arm.position.set(side*.232,.635,0);body.add(arm);
      sphere(arm,.085,accent,side*.02,0,0);
      const upper=cyl(arm,.049,.16,white,side*.047,-.092,.015,24);upper.rotation.z=side*.15;
      sphere(arm,.051,pale,side*.063,-.16,.041);
      const fore=cyl(arm,.056,.17,white,side*.07,-.213,.103,24);fore.rotation.x=-.64;
      sphere(arm,.067,white,side*.076,-.258,.177,1,.68,1.10);
      for(let f=0;f<3;f++)sphere(arm,.019,accent,side*.075+(f-1)*.027,-.258,.233,1,.72,1.5);
      batchStaticMeshes(arm);arms.push(arm);
    }
    const legs=[];
    for(const side of [-1,1]){
      const leg=new THREE.Group();leg.position.set(side*.118,.295,0);body.add(leg);
      sphere(leg,.067,pale,0,-.031,0);
      cyl(leg,.059,.13,white,0,-.108,.007,24);
      box(leg,.19,.11,.245,white,0,-.215,.045,.052);
      box(leg,.19,.023,.248,accent,0,-.266,.045,.010);
      batchStaticMeshes(leg);legs.push(leg);
    }
    iconPlate(body,config.color,config.glyph,0,.51,.20,.061);
    box(body,.102,.012,.015,glow,0,.685,.125,.005);
    batchStaticMeshes(head,[eyes]);batchStaticMeshes(body,[head,...arms,...legs]);
    const station=stations.find(g=>g.userData.agent===config.id);
    const localHome=new THREE.Vector3(0,.52,.67).applyAxisAngle(new THREE.Vector3(0,1,0),station.rotation.y);
    const home=station.userData.home.clone().add(localHome);
    root.position.copy(home);root.rotation.y=Math.PI+station.rotation.y;
    const feetShadow=plane(scene,.55,.43,contactMaterial,home.x,home.y+.002,home.z);feetShadow.rotation.x=-Math.PI/2;feetShadow.castShadow=false;
    const talk=document.createElement('div');talk.className='agent-talk';talk.style.setProperty('--agent-color',config.color);overlay.appendChild(talk);
    const robot={id:config.id,config,root,body,head,eyes,arms,legs,station,workYaw:Math.PI+station.rotation.y,home,from:home.clone(),target:home.clone(),motionStart:0,motionDuration:3.4,moving:false,status:'work',message:'',talk,feetShadow,meet:false};
    labels.push({el:talk,obj:root,offset:new THREE.Vector3(0,2.12,.1),speech:true});
    agents.set(config.id,robot);
    return robot;
  }
  AGENTS.forEach(makeRobot);

  // A floating, illuminated exploded assembly inside a glass projection chamber.
  const central=new THREE.Group();central.position.y=.22;scene.add(central);
  cyl(central,2.50,.23,white,0,.19,0);cyl(central,2.56,.058,chrome,0,.34,0);
  cyl(central,2.45,.10,glass,0,.43,0);cyl(central,1.43,.07,black,0,.47,0);
  const discTex=canvasTex(512,512,c=>{
    const grad=c.createRadialGradient(256,256,12,256,256,250);
    grad.addColorStop(0,'rgba(65,173,255,.5)');grad.addColorStop(.5,'rgba(72,170,255,.16)');grad.addColorStop(.85,'rgba(59,169,255,.36)');grad.addColorStop(1,'rgba(42,155,255,0)');
    c.fillStyle=grad;c.fillRect(0,0,512,512);c.strokeStyle='rgba(113,217,255,.8)';c.lineWidth=2;
    for(let r=48;r<240;r+=32){c.beginPath();c.arc(256,256,r,0,TAU);c.stroke();}
    for(let i=0;i<12;i++){const a=i/12*TAU;c.beginPath();c.moveTo(256+Math.cos(a)*80,256+Math.sin(a)*80);c.lineTo(256+Math.cos(a)*225,256+Math.sin(a)*225);c.stroke();}
  });
  const discMaterial=new THREE.MeshBasicMaterial({map:discTex,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});materials.add(discMaterial);
  const lightDisc=plane(central,4.9,4.9,discMaterial,0,.501,0);lightDisc.rotation.x=-Math.PI/2;lightDisc.castShadow=false;
  for(const r of [2.49,2.19,1.80,1.41,.95])torus(central,r,.014,blueGlow,0,.501,0);
  for(let i=0;i<72;i++){
    const a=i/72*TAU;const tick=box(central,.009,.007,i%6===0?.14:.05,blueGlow,Math.sin(a)*2.13,.507,Math.cos(a)*2.13,.002);tick.rotation.y=a;
  }
  const chamberMat=mat(0x96d2ff,{transparent:true,opacity:.085,roughness:.04,metalness:.28,depthWrite:false,side:THREE.DoubleSide});
  mesh(new THREE.CylinderGeometry(1.18,1.18,3.15,80,1,true,Math.PI*.19,Math.PI*1.62),chamberMat,central,0,2.09,0).castShadow=false;
  for(const yy of [.53,3.66])torus(central,1.18,.014,blueGlow,0,yy,0);
  const volumeTex=canvasTex(64,512,c=>{
    const gradient=c.createLinearGradient(0,0,0,512);gradient.addColorStop(0,'rgba(56,157,255,0)');gradient.addColorStop(.4,'rgba(56,169,255,.08)');gradient.addColorStop(1,'rgba(73,182,255,.30)');c.fillStyle=gradient;c.fillRect(0,0,64,512);
    for(let y=0;y<512;y+=26){c.fillStyle='rgba(87,184,255,.10)';c.fillRect(0,y,64,1);}
  });
  const volumeMat=new THREE.MeshBasicMaterial({map:volumeTex,transparent:true,side:THREE.DoubleSide,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false});materials.add(volumeMat);
  mesh(new THREE.CylinderGeometry(.93,1.42,3.15,64,1,true),volumeMat,central,0,2.07,0).castShadow=false;
  const scanRing=torus(central,1.10,.008,blueGlow,0,2.1,0);holo.push({obj:scanRing,kind:'scan'});
  const heroOrbits=[];
  for(let i=0;i<2;i++){
    const ring=torus(central,1.37+i*.18,.009,blueGlow,0,2.0+i*.30,0);ring.rotation.x=Math.PI/2+(i?-.20:.22);ring.rotation.z=i?-.25:.25;heroOrbits.push(ring);
  }
  const device=new THREE.Group();device.position.set(0,.94,0);device.scale.setScalar(1.34);central.add(device);
  const deviceLayers=[];
  function deviceLayer(open,closed,seed=0){const group=new THREE.Group();group.position.y=open;device.add(group);deviceLayers.push({obj:group,open,closed,seed});return group;}
  const bottom=deviceLayer(0,0);
  cyl(bottom,.64,.115,chrome);cyl(bottom,.57,.075,black,0,.085,0);torus(bottom,.625,.013,blueGlow,0,.057,0);
  cyl(bottom,.49,.028,glass,0,.138,0);torus(bottom,.49,.010,blueGlow,0,.155,0);
  for(let i=0;i<12;i++){const a=i/12*TAU;box(bottom,.045,.018,.076,pale,Math.sin(a)*.51,.14,Math.cos(a)*.51,.006).rotation.y=a;}
  const coil=deviceLayer(.55,.19,1);
  for(let i=0;i<11;i++)torus(coil,.26+i*.018,.012,goldMetal,0,i*.006,0);
  torus(coil,.51,.009,blueGlow,0,.026,0);cyl(coil,.14,.04,chrome,0,.025,0);
  const boardLayer=deviceLayer(1.10,.295,2);const b=pcb(boardLayer,0,0,0,1.10);
  box(b,.23,.10,.20,chrome,-.28,.09,-.13,.017);box(b,.15,.12,.11,pale,.32,.1,.17,.015);
  for(const zz of [-.38,.38])line(boardLayer,[[-.54,.01,zz],[.54,.01,zz]],blueGlow,.008);
  for(const xx of [-.54,.54])line(boardLayer,[[xx,.01,-.38],[xx,.01,.38]],blueGlow,.008);
  const housing=deviceLayer(1.63,.39,3);
  const shellProfile=[new THREE.Vector2(.48,-.064),new THREE.Vector2(.675,-.064),new THREE.Vector2(.709,-.04),new THREE.Vector2(.715,.034),new THREE.Vector2(.68,.068),new THREE.Vector2(.48,.068),new THREE.Vector2(.48,-.064)];
  mesh(new THREE.LatheGeometry(shellProfile,64),white,housing);
  torus(housing,.703,.018,chrome,0,0,0);torus(housing,.488,.010,blueGlow,0,.071,0);
  const lid=deviceLayer(2.08,.535,4);
  const lidProfile=[new THREE.Vector2(.34,-.036),new THREE.Vector2(.69,-.036),new THREE.Vector2(.69,.005),new THREE.Vector2(.64,.037),new THREE.Vector2(.34,.037),new THREE.Vector2(.34,-.036)];
  mesh(new THREE.LatheGeometry(lidProfile,64),chrome,lid);cyl(lid,.338,.027,glass,0,.050,0);
  torus(lid,.591,.017,white,0,.049,0);torus(lid,.618,.010,blueGlow,0,.064,0);
  cyl(lid,.094,.022,blueGlow,0,.075,0,32);torus(lid,.17,.007,blueGlow,0,.076,0);
  for(let n=0;n<6;n++){
    const a=n/6*TAU,screw=deviceLayer(.76,.32,n+5);
    cyl(screw,.018,.15,chrome,Math.sin(a)*.59,0,Math.cos(a)*.59,12);
    cyl(screw,.036,.024,pale,Math.sin(a)*.59,.085,Math.cos(a)*.59,16);
  }
  details.product({central,bottom,coil,board:boardLayer,housing,lid});
  for(let n=0;n<6;n++){
    const a=n/6*TAU,xx=Math.sin(a)*.96,zz=Math.cos(a)*.96;
    line(central,[[xx,.53,zz],[xx,3.67,zz]],glowMaterial(0x72cfff,1.5),.0035);
  }
  const floorTitle=textPanel(central,'SENSE · CONNECT · THINK · ACT · THRIVE',3.7,.17,'#55789c');floorTitle.position.set(0,.21,2.51);
  const title=textPanel(central,'Battery-Free Intelligent Node',2.68,.29,'#e1f5ff','rgba(15,70,122,.78)');title.position.set(0,.72,1.73);title.rotation.x=-.18;
  const heroHud=new THREE.Group();heroHud.position.set(-1.67,2.17,.18);central.add(heroHud);
  box(heroHud,.82,1.14,.027,softGlass);
  const heroTex=canvasTex(480,620,c=>{
    c.fillStyle='rgba(19,54,89,.68)';c.fillRect(0,0,480,620);c.fillStyle='#9bdfff';c.font='18px Arial';c.fillText('SYSTEM ASSEMBLY',28,53);
    ['01  ENCLOSURE','02  SENSING','03  PCB LAYOUT','04  ENERGY PATH','05  FIRMWARE'].forEach((text,i)=>{c.fillStyle='#cfecff';c.font='22px Arial';c.fillText(text,28,128+i*80);c.fillStyle='#58c7ff';c.fillRect(28,144+i*80,360-i*37,3);});
    c.fillStyle='#74cbff';c.font='17px Arial';c.fillText('DEMO · EXPLODED VIEW',28,570);
  });
  const hudMaterial=new THREE.MeshBasicMaterial({map:heroTex,transparent:true,side:THREE.DoubleSide,toneMapped:false});materials.add(hudMaterial);plane(heroHud,.80,1.1,hudMaterial,0,0,.019).castShadow=false;
  function setArtifactPose(assembled,instant=false){
    if(instant){for(const layer of deviceLayers)layer.obj.position.y=assembled?layer.closed:layer.open;device.position.y=assembled?1.95:.94;device.scale.setScalar(assembled?1.55:1.34);}
  }
  const dotRoot=new THREE.Group();dotRoot.position.set(0,5.36,-.13);dotRoot.scale.setScalar(1.2);scene.add(dotRoot);
  const dotShell=mat(0xe6f5ff,{metalness:.20,roughness:.1,transmission:0,thickness:.3});
  sphere(dotRoot,.64,dotShell);sphere(dotRoot,.74,softGlass);
  sphere(dotRoot,.60,mat(0x041329,{roughness:.10,metalness:.06,envMapIntensity:.24}),0,-.03,.38,.76,.51,.58);
  const dotEyes=new THREE.Group();dotRoot.add(dotEyes);
  for(const x of [-.18,.18]){const p=[];for(let j=0;j<=16;j++){const a=Math.PI-j/16*Math.PI,xx=x+Math.cos(a)*.075,yy=-.018+Math.sin(a)*.075;p.push([xx,yy,.38+.348*Math.sqrt(1-(xx/.456)**2-((yy+.03)/.306)**2)+.009]);}line(dotEyes,p,blueGlow,.018);}
  torus(dotRoot,.743,.018,blueGlow,0,0,0,false);
  const halo=torus(dotRoot,.89,.015,blueGlow,0,0,-.1,false);halo.rotation.y=.22;
  const glowTex=canvasTex(256,256,c=>{const grad=c.createRadialGradient(128,128,0,128,128,128);grad.addColorStop(0,'rgba(127,197,255,0)');grad.addColorStop(.45,'rgba(127,197,255,0)');grad.addColorStop(.58,'rgba(140,220,255,.36)');grad.addColorStop(.70,'rgba(96,181,255,.11)');grad.addColorStop(1,'rgba(96,181,255,0)');c.fillStyle=grad;c.fillRect(0,0,256,256);});
  const haloMat=new THREE.SpriteMaterial({map:glowTex,transparent:true,depthWrite:false,depthTest:false,blending:THREE.AdditiveBlending,toneMapped:false});materials.add(haloMat);
  const haloSprite=new THREE.Sprite(haloMat);haloSprite.scale.set(2.08,2.08,1);dotRoot.add(haloSprite);
  for(const a of AGENTS) {
    const p0=new THREE.Vector3(a.x,.50,a.z),p1=new THREE.Vector3(a.x*.6,.55,a.z*.65),p2=new THREE.Vector3(a.x*.23,.47,a.z*.25),p3=new THREE.Vector3(0,.47,0);
    const curve=new THREE.CubicBezierCurve3(p0,p1,p2,p3);
    const tube=mesh(new THREE.TubeGeometry(curve,48,.010,5,false),glowMaterial(0x53baff,1.6),scene);tube.castShadow=false;
    const packet=sphere(scene,.055,glowMaterial(a.color,2.1));connectors.push({curve,tube,packet,station:stations.find(g=>g.userData.agent===a.id),offset:AGENTS.indexOf(a)/5,spread:-1});
  }
  const meetingRing=torus(central,3.2,.015,blueGlow,0,.025,0);meetingRing.visible=false;
  const collaborationCard=document.createElement('div');collaborationCard.className='collaboration-card';overlay.appendChild(collaborationCard);labels.push({el:collaborationCard,obj:central,offset:new THREE.Vector3(0,4.0,.23)});
  const laserMat=glowMaterial(0xc1e9ff,.6);const meetingLines=[];
  for(let i=0;i<5;i++){const l=mesh(new THREE.CylinderGeometry(.008,.008,1,8),laserMat,scene);l.visible=false;meetingLines.push(l);}

  const movingExhibits=holo.map(h=>h.obj);
  batchStaticMeshes(room,movingExhibits);batchStaticMeshes(floorGroup);
  stations.forEach(g=>batchStaticMeshes(g,movingExhibits));
  deviceLayers.forEach(layer=>batchStaticMeshes(layer.obj));
  batchStaticMeshes(central,[device,scanRing,...heroOrbits]);
  let composer, bloomComposer, bloomPass, outputPass, compositePass;
  const darkMask=new THREE.MeshBasicMaterial({color:0x000000,side:THREE.DoubleSide});materials.add(darkMask);
  const glowMeshes=[], glowMaterials=new Map(), glowHidden=[];
  if(quality!=='low'){
    // Bloom sees only emitted light, rather than every white reflection in the room.
    scene.traverse(o=>{if(o.isMesh)glowMeshes.push(o);});
    bloomComposer=new EffectComposer(renderer);bloomComposer.renderToScreen=false;
    bloomComposer.addPass(new RenderPass(scene,camera));
    bloomPass=new UnrealBloomPass(new THREE.Vector2(512,512),.38,.42,.92);bloomComposer.addPass(bloomPass);
    composer=new EffectComposer(renderer);composer.renderTarget1.samples=4;composer.renderTarget2.samples=4;composer.addPass(new RenderPass(scene,camera));
    compositePass=new ShaderPass(new THREE.ShaderMaterial({
      uniforms:{baseTexture:{value:null},glowTexture:{value:bloomComposer.renderTarget2.texture}},
      vertexShader:'varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
      fragmentShader:'uniform sampler2D baseTexture; uniform sampler2D glowTexture; varying vec2 vUv; void main(){gl_FragColor=texture2D(baseTexture,vUv)+texture2D(glowTexture,vUv)*0.20;}',
      depthWrite:false,depthTest:false,
    }),'baseTexture');composer.addPass(compositePass);
    outputPass=new OutputPass();composer.addPass(outputPass);
    if(mirror){const mirrorRender=mirror.onBeforeRender.bind(mirror);mirror.onBeforeRender=(...args)=>{if(args[0].getRenderTarget()===composer.readBuffer)mirrorRender(...args);};}
  }
  function renderFrame(delta){
    renderer.info.reset();
    if(!composer){renderer.render(scene,camera);return;}
    const background=scene.background,fog=scene.fog,shadowUpdate=renderer.shadowMap.autoUpdate;
    scene.background=new THREE.Color(0);scene.fog=null;renderer.shadowMap.autoUpdate=false;
    if(mirror)mirror.visible=false;
    for(const mesh of glowMeshes){
      const material=mesh.material;
      if(material.blending===THREE.AdditiveBlending||material.emissiveIntensity>=1.4)continue;
      if(material.transmission>0||material.transparent){if(mesh.visible){glowHidden.push(mesh);mesh.visible=false;}continue;}
      glowMaterials.set(mesh,material);mesh.material=darkMask;
    }
    bloomComposer.render(delta);
    for(const [mesh,material] of glowMaterials)mesh.material=material;glowMaterials.clear();
    for(const mesh of glowHidden)mesh.visible=true;glowHidden.length=0;
    if(mirror)mirror.visible=true;
    scene.background=background;scene.fog=fog;renderer.shadowMap.needsUpdate=true;
    composer.render(delta);renderer.shadowMap.autoUpdate=shadowUpdate;
  }

  const cameraPresets={
    overview:{position:[12.8,14.2,23.5],target:[0,1.8,.6]},
    front:{position:[0,10.8,21.8],target:[0,1.7,.7]},
    meeting:{position:[0,8.9,16.5],target:[0,2.25,0]},
    product:{position:[4.3,4.5,6.4],target:[0,2.6,0]},
    ...Object.fromEntries(AGENTS.map(a=>[a.id,stationCamera(a)])),
    top:{position:[.1,25,.1],target:[0,0,0]},
  };
  function stationCamera(config){
    const angle=THREE.MathUtils.degToRad(config.yawDeg),axis=new THREE.Vector3(0,1,0);
    // Mirror side views inward so the adjacent room's sign cannot sit between
    // this camera and its specialist. Leave room for the tabletop and UI.
    const side=config.x>0?-1:1;
    const offset=new THREE.Vector3(side*4.9,5.35,4.25).applyAxisAngle(axis,angle);
    const target=new THREE.Vector3(0,1.15,.10).applyAxisAngle(axis,angle).add(new THREE.Vector3(config.x,0,config.z));
    return {position:offset.add(new THREE.Vector3(config.x,0,config.z)).toArray(),target:target.toArray()};
  }
  function fittedPosition(name){const p=cameraPresets[name],pos=new THREE.Vector3(...p.position),target=new THREE.Vector3(...p.target);const minAspect=['front','overview','top'].includes(name)?1.3:name==='meeting'?1.05:.90;const factor=Math.min(3.6,Math.max(1,minAspect/camera.aspect));return pos.sub(target).multiplyScalar(factor).add(target);}
  function setCamera(name, immediate=false) {
    if(!cameraPresets[name])throw new RangeError('Unknown camera: '+name);
    const p=cameraPresets[name];currentCamera=name;
    if(immediate||reduced){camera.position.copy(fittedPosition(name));controls.target.fromArray(p.target);cameraTransition=null;controls.update();}
    else cameraTransition={start:performance.now()/1000,from:camera.position.clone(),to:fittedPosition(name),targetFrom:controls.target.clone(),targetTo:new THREE.Vector3(...p.target)};
    notify();return api;
  }
  function meetingTargets(members) {
    const result=new Map();
    const slots=members.length===2?[-1.70,1.70]:members.length===3?[-1.85,2.59,1.70]:members.length===4?[-1.83,-2.37,2.44,1.71]:[-1.83,-2.37,2.59,2.13,1.61];
    members.forEach((id,i)=>{const a=slots[i];result.set(id,new THREE.Vector3(Math.sin(a)*3.34,.035,Math.cos(a)*3.34));});return result;
  }
  function moveTo(robot,target, instant=false) {
    if(robot.target.distanceTo(target)<.01&&!instant)return;
    robot.from.copy(robot.root.position);robot.target.copy(target);robot.motionStart=visualTime;
    robot.motionDuration=clamp(robot.from.distanceTo(target)/2.5,1.2,4);
    robot.motionCurve=null;
    const startFlat=robot.from.clone().setY(0),endFlat=target.clone().setY(0);
    const nearest=new THREE.Line3(startFlat,endFlat).closestPointToPoint(new THREE.Vector3(),true,new THREE.Vector3());
    if(nearest.length()<3.15){
      const first=Math.atan2(startFlat.x,startFlat.z),last=Math.atan2(endFlat.x,endFlat.z);
      const turn=Math.atan2(Math.sin(last-first),Math.cos(last-first)),points=[robot.from.clone()];
      for(let i=0;i<=5;i++){const t=i/5,a=first+turn*t;points.push(new THREE.Vector3(Math.sin(a)*3.95,THREE.MathUtils.lerp(robot.from.y,target.y,t),Math.cos(a)*3.95));}
      points.push(target.clone());robot.motionCurve=new THREE.CatmullRomCurve3(points);
      robot.motionDuration=clamp(robot.motionCurve.getLength()/2.6,2.2,4.2);
    }
    robot.moving=!instant && !reduced;
    if(!robot.moving)robot.root.position.copy(target);
  }
  function workPosition(robot,expanded=robot.station.userData.spread){
    return robot.home.clone().add(robot.station.userData.expanded.clone().sub(robot.station.userData.home).multiplyScalar(expanded));
  }
  function meetingHeading(robot){return Math.atan2(-robot.root.position.x,.70-robot.root.position.z);}
  function spreadStations(expanded,instant=false){
    for(const station of stations){
      const s=station.userData;s.spreadFrom=s.spread;s.spreadTarget=expanded?1:0;s.spreadStart=visualTime;
      if(instant||reduced){s.spread=s.spreadTarget;s.spreadFrom=s.spreadTarget;station.position.lerpVectors(s.home,s.expanded,s.spread);}
    }
  }
  function setMeeting(members,topic='',instant=false) {
    const targets=meetingTargets(members);
    meeting=members.length?{participants:[...members],topic}:null;
    spreadStations(members.length>0,instant);
    for(const r of agents.values()){
      const wasMeeting=r.meet;r.meet=members.includes(r.id);
      if(r.meet||wasMeeting){
        moveTo(r,targets.get(r.id)||workPosition(r,members.length?1:0),instant);
        if(!r.meet&&r.moving)r.motionDuration=Math.max(r.motionDuration,3.2);
      }else if(instant||reduced){r.root.position.copy(workPosition(r));r.target.copy(r.root.position);r.moving=false;}
      if(instant||reduced)r.root.rotation.y=r.meet?meetingHeading(r):r.workYaw;
    }
    dotMessage=topic||'五个专业，朝着同一个目标。';
    meetingRing.visible=members.length>0;
    heroHud.visible=members.length===0;
    collaborationCard.classList.toggle('visible',members.length>0);
    collaborationCard.innerHTML=members.length?`<span class="collab-eyebrow">${mode==='demo'?'DEMO · ':''}COLLABORATION</span><strong>${members.map(id=>agents.get(id).config.name).join(' × ')}</strong>`:'';
    notify();
  }
  function applyStage(index, instant=false) {
    stageIndex=index;const stage=DEMO_STAGES[index];setMeeting(stage.members,stage.topic,instant);
    for(const r of agents.values())r.status=stage.assembled?'done':'work';
    setArtifactPose(!!stage.assembled,instant||reduced);
    notify();
  }
  function notify(markDirty=true) {
    if(markDirty)needsRender=true;
    if(!listeners.size&&!options.onChange)return;
    const snapshot=getSnapshot();for(const listener of listeners)listener(snapshot);options.onChange?.(snapshot);
  }
  function getSnapshot() {
    return {version:1,mode,paused,reducedMotion:reduced,time:Number(demoTime.toFixed(3)),duration:DEMO_DURATION,speed,camera:currentCamera,stage:mode==='demo'?DEMO_STAGES[Math.max(0,stageIndex)].label:meeting?'实时协作':'等待运行事件',stageIndex,meeting:meeting?{participants:[...meeting.participants],topic:meeting.topic}:null,
      agents:[...agents.values()].map(r=>({id:r.id,status:r.status,message:r.message,meeting:r.meet,moving:r.moving,position:r.root.position.toArray(),home:r.home.toArray(),target:r.target.toArray(),heading:r.root.rotation.y,workHeading:r.workYaw,activity:r.moving?'walking':r.meet?'discussing':r.status==='work'?'typing':'idle'})),
      workstations:stations.map(g=>({id:g.userData.agent,position:g.position.toArray(),home:g.userData.home.toArray(),yaw:g.rotation.y,spread:g.userData.spread,moving:Math.abs(g.userData.spread-g.userData.spreadTarget)>.001})),
      artifact:{assembled:mode==='demo'?!!DEMO_STAGES[Math.max(0,stageIndex)].assembled:!!central.userData.assembled,layerHeights:deviceLayers.slice(0,5).map(l=>l.obj.getWorldPosition(new THREE.Vector3()).y)},
      presentation:{glassTransmission:glass.transmission,bloom:!!composer,technologyExhibits:installations.length,titleRendering:'vector-outlines',dotMessage},
      events:acceptedEvents.length,errors:[...errors],renderer:{calls:renderer.info.render.calls,triangles:renderer.info.render.triangles}};
  }
  function dispatch(event) {
    if(disposed)throw new Error('Studio is disposed');
    if(mode!=='live')return {accepted:false,reason:'Set mode to live before dispatching execution events.'};
    if(!event||typeof event!=='object'||typeof event.type!=='string')return {accepted:false,reason:'Invalid event'};
    if(event.id && eventIds.has(event.id))return {accepted:false,reason:'duplicate'};
    if(event.id!==undefined&&(typeof event.id!=='string'||!event.id.trim()))return {accepted:false,reason:'Invalid event id'};
    if(event.type==='agent.status') {
      const r=agents.get(event.agent);
      if(!r)return {accepted:false,reason:'Unknown agent'};
      if(!['work','waiting','blocked','error','done'].includes(event.status))return {accepted:false,reason:'Invalid status'};
      r.status=event.status;r.message=String(event.message||'').slice(0,300);
    } else if(event.type==='meeting.start') {
      const participants=event.participants;
      if(!Array.isArray(participants)||participants.length<2||participants.length>5||new Set(participants).size!==participants.length||participants.some(id=>!agents.has(id)))return {accepted:false,reason:'Meeting needs 2–5 distinct known agents'};
      setMeeting(participants,String(event.topic||'').slice(0,300));
    } else if(event.type==='meeting.end') {setMeeting([],String(event.summary||'返回工位，继续工作。').slice(0,300));}
    else if(event.type==='dot.message')dotMessage=String(event.message||'').slice(0,300);
    else if(event.type==='artifact.update') {
      if(typeof event.assembled!=='boolean')return {accepted:false,reason:'assembled must be boolean'};
      central.userData.assembled=event.assembled;
      setArtifactPose(event.assembled,paused||reduced);
    } else return {accepted:false,reason:'Unknown event type'};
    if(event.id){eventIds.add(event.id);if(eventIds.size>4096)eventIds.delete(eventIds.values().next().value);}
    acceptedEvents.push({type:event.type,id:event.id||null,at:liveTime});if(acceptedEvents.length>4096)acceptedEvents.shift();
    notify();return {accepted:true};
  }
  function setMode(next) {
    if(!['demo','live'].includes(next))throw new TypeError('mode must be demo or live');
    if(mode===next)return api;
    mode=next;demoTime=0;stageIndex=-1;central.userData.assembled=false;eventIds.clear();acceptedEvents.length=0;
    setArtifactPose(false,true);
    setMeeting([],next==='live'?'等待真实 Agent 运行事件。':'五个专业，朝着同一个目标。',true);
    for(const r of agents.values()){r.status=next==='live'?'waiting':'work';r.message='';}
    if(next==='demo')applyStage(0,true);
    notify();return api;
  }
  function seek(seconds) {
    if(mode!=='demo')return api;
    demoTime=clamp(Number(seconds)||0,0,DEMO_DURATION-.001);
    const idx=DEMO_STAGES.findLastIndex(s=>demoTime>=s.at);applyStage(idx,true);notify();return api;
  }
  const raycaster=new THREE.Raycaster(), pointer=new THREE.Vector2();
  let down=null;
  const onPointerDown=e=>{down=[e.clientX,e.clientY];};
  const onPointerUp=e=>{
    if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;
    const rect=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(pointer,camera);
    const objects=[...agents.values()].map(r=>r.root);const hits=raycaster.intersectObjects(objects,true);
    if(hits.length){let p=hits[0].object;while(p.parent&&!objects.includes(p))p=p.parent;const r=[...agents.values()].find(r=>r.root===p);if(r)setCamera(r.id);}
  };
  renderer.domElement.addEventListener('pointerdown',onPointerDown);renderer.domElement.addEventListener('pointerup',onPointerUp);
  const onKey=e=>{if(e.key==='Escape')setCamera('overview');if(e.key===' '){e.preventDefault();paused=!paused;notify();}};
  renderer.domElement.addEventListener('keydown',onKey);
  const resize=()=>{const w=Math.max(1,container.clientWidth),h=Math.max(1,container.clientHeight);camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);composer?.setSize(w,h);bloomComposer?.setSize(Math.floor(w*.65),Math.floor(h*.65));needsRender=true;if(cameraPresets[currentCamera]){camera.position.copy(fittedPosition(currentCamera));controls.target.fromArray(cameraPresets[currentCamera].target);cameraTransition=null;controls.update();}};
  const observer=new ResizeObserver(resize);observer.observe(container);resize();
  const onContextLost=e=>{e.preventDefault();errors.push('WebGL context lost');notify();};renderer.domElement.addEventListener('webglcontextlost',onContextLost);
  const onVisibility=()=>{lastFrame=performance.now();};document.addEventListener('visibilitychange',onVisibility);

  const worldPos=new THREE.Vector3();
  let lastNotify=0;
  function render(now) {
    if(disposed)return;
    animationFrame=requestAnimationFrame(render);
    const dt=Math.max(0,Math.min((now-lastFrame)/1000,.5));lastFrame=now;
    const activeDt=!paused&&!document.hidden?dt*speed:0;
    visualTime+=activeDt;liveTime+=activeDt;
    if(mode==='demo'){
      demoTime=(demoTime+activeDt)%DEMO_DURATION;
      const idx=DEMO_STAGES.findLastIndex(s=>demoTime>=s.at);
      if(idx!==stageIndex)applyStage(idx);
    }
    if(cameraTransition){const t=clamp((now/1000-cameraTransition.start)/1.45,0,1);camera.position.lerpVectors(cameraTransition.from,cameraTransition.to,ease(t));controls.target.lerpVectors(cameraTransition.targetFrom,cameraTransition.targetTo,ease(t));if(t>=1)cameraTransition=null;}
    controls.update();
    if((paused||document.hidden)&&!needsRender&&!cameraTransition){if(now-lastNotify>350){lastNotify=now;notify(false);}return;}
    for(const station of stations){
      const s=station.userData,p=clamp((visualTime-s.spreadStart)/s.spreadDuration,0,1);
      s.spread=THREE.MathUtils.lerp(s.spreadFrom,s.spreadTarget,ease(p));
      station.position.lerpVectors(s.home,s.expanded,s.spread);
    }
    dotRoot.position.y=5.36+(reduced?0:Math.sin(visualTime*1.25)*.095);halo.rotation.z=visualTime*.07;
    dotEyes.scale.y=reduced?1:(Math.sin(visualTime*2.9)> .996?.14:1);
    for(const r of agents.values()){
      const seed=AGENTS.findIndex(a=>a.id===r.id), t=visualTime;
      if(r.moving){
        const p=clamp((t-r.motionStart)/r.motionDuration,0,1),s=ease(p);
        if(r.motionCurve)r.root.position.copy(r.motionCurve.getPoint(s));else r.root.position.lerpVectors(r.from,r.target,s);
        r.root.position.y+=Math.abs(Math.sin(p*Math.PI*6))*.032;
        const tangent=r.motionCurve?r.motionCurve.getTangent(s):r.target.clone().sub(r.from);
        const angle=Math.atan2(tangent.x,tangent.z);r.root.rotation.y=angle;
        if(p>=1)r.moving=false;
      } else {
        if(!r.meet){r.root.position.copy(workPosition(r));r.target.copy(r.root.position);}
        const targetAngle=r.meet?meetingHeading(r):r.workYaw;
        if(!paused)r.root.rotation.y+=Math.atan2(Math.sin(targetAngle-r.root.rotation.y),Math.cos(targetAngle-r.root.rotation.y))*Math.min(1,dt*4);
      }
      r.body.position.y=reduced?0:Math.sin(t*2.15+seed)*.014;
      r.body.rotation.x=!r.meet&&!r.moving&&r.status==='work'?.045:0;
      r.head.rotation.y=reduced?0:(r.meet?Math.sin(t*.7+seed)*.14:Math.sin(t*.55+seed)*.035);
      r.head.rotation.x=r.meet?-.045:-.10+Math.sin(t*.7+seed)*.025;
      r.head.rotation.z=reduced?0:Math.sin(t*.6+seed)*.025;
      r.eyes.scale.y=reduced?1:Math.sin(t*2.8+seed)> .996?.13:1;
      r.arms.forEach((arm,i)=>{
        const typing=r.status==='work'&&!r.meet&&!r.moving;
        arm.rotation.x=r.moving?Math.sin(t*9+i*Math.PI)*.38:r.meet?-.42+Math.sin(t*1.7+seed+i)*.22:typing?-.78+Math.sin(t*6.4+seed+i*Math.PI)*.065:-.18;
        arm.rotation.z=r.meet?(i===0?.28:-.28)+Math.sin(t*1.5+seed)*.09:typing?(i===0?-.07:.07):0;
      });
      r.legs.forEach((leg,i)=>leg.rotation.x=r.moving?Math.sin(t*9+i*Math.PI)*.32:0);
      r.feetShadow.position.set(r.root.position.x,r.root.position.y+.001,r.root.position.z);
      const participants=meeting?.participants||[];
      const speaking=participants.length?participants[Math.floor(visualTime/3.5)%participants.length]:null;
      r.talk.classList.toggle('speaking',r.id===speaking&&!r.moving);
      const demoLines={mechanical:'装配间隙和传感灵敏度，需要一起检查。',circuit:'先对齐输入信号与工作电压。',pcb:'我来检查走线与器件净空。',power:'峰值任务是否有足够的能量？',firmware:'唤醒、处理与发射时序一起对齐。'};
      r.talk.textContent=mode==='demo'?demoLines[r.id]:(r.message||'正在参与协作');
    }
    const assembled=mode==='demo'?!!DEMO_STAGES[Math.max(0,stageIndex)].assembled:!!central.userData.assembled;
    device.rotation.y=reduced?0:visualTime*.13;
    const baseHeight=assembled?1.95:.94,baseScale=assembled?1.55:1.34;
    device.position.y+=(baseHeight+(reduced?0:Math.sin(visualTime*.9)*.045)-device.position.y)*Math.min(1,dt*3);
    device.scale.lerp(new THREE.Vector3(baseScale,baseScale,baseScale),Math.min(1,dt*3));
    for(const layer of deviceLayers){const target=(assembled?layer.closed:layer.open)+(!assembled&&!reduced?Math.sin(visualTime*1.15+layer.seed)*.027:0);layer.obj.position.y+= (target-layer.obj.position.y)*Math.min(1,dt*3);}
    heroOrbits.forEach((ring,i)=>{ring.rotation.z=(i?-.25:.25)+Math.sin(visualTime*.38+i)*.15;ring.rotation.y=visualTime*.1*(i?1:-1);});
    for(const c of connectors){
      const spread=c.station.userData.spread;
      if(Math.abs(spread-c.spread)>.005){
        const pos=c.station.position;c.curve.v0.set(pos.x,.51,pos.z);c.curve.v1.set(pos.x*.6,.55,pos.z*.65);c.curve.v2.set(pos.x*.23,.47,pos.z*.25);
        geometries.delete(c.tube.geometry);c.tube.geometry.dispose();c.tube.geometry=new THREE.TubeGeometry(c.curve,48,.010,5,false);geometries.add(c.tube.geometry);c.spread=spread;
      }
      c.packet.position.copy(c.curve.getPoint((visualTime*.13+c.offset)%1));
    }
    for(const h of holo){
      if(h.kind==='scan')h.obj.position.y=.72+(visualTime*.29)%2.8;
      if(h.kind==='charge')h.obj.scale.y=.25+((visualTime*.055)%1)*.75;
      if(h.kind==='beacon'){h.obj.position.y=h.base+Math.sin(visualTime+ h.seed)*.025;h.obj.rotation.y=visualTime*.3+h.seed;}
    }
    const members=meeting?.participants||[];
    meetingLines.forEach((l,i)=>{
      const r=agents.get(members[i]);l.visible=!!r&&!r.moving;
      if(!l.visible)return;
      const from=r.root.position.clone().add(new THREE.Vector3(0,.9,0)),to=new THREE.Vector3(0,2.1,0);l.position.copy(from).lerp(to,.5);l.scale.y=from.distanceTo(to);l.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),to.sub(from).normalize());
    });
    for(const l of labels){
      l.obj.getWorldPosition(worldPos);worldPos.add(l.offset);
      if(l.speech)worldPos.x+=l.obj.position.x<0?-1.25:1.25;
      worldPos.project(camera);
      const visible=l.obj.visible&&worldPos.z<1&&worldPos.z>-1&&Math.abs(worldPos.x)<1.2&&Math.abs(worldPos.y)<1.2;
      l.el.style.display=visible?'':'none';l.el.style.transform=`translate(-50%,-50%) translate(${(worldPos.x*.5+.5)*container.clientWidth}px,${(-worldPos.y*.5+.5)*container.clientHeight}px)`;
    }
    renderFrame(activeDt);
    needsRender=false;
    if(now-lastNotify>350){lastNotify=now;notify(false);}
  }
  const api={
    dispatch,setMode,setCamera,seek,getSnapshot,
    play(){paused=false;lastFrame=performance.now();notify();return api;},
    pause(){paused=true;notify();return api;},
    setSpeed(value){speed=clamp(Number(value)||1,.25,3);notify();return api;},
    subscribe(listener){listeners.add(listener);listener(getSnapshot());return()=>listeners.delete(listener);},
    resize,
    dispose(){
      if(disposed)return;disposed=true;cancelAnimationFrame(animationFrame);observer.disconnect();controls.removeEventListener('start',onControlStart);controls.removeEventListener('change',onControlsChange);controls.dispose();
      renderer.domElement.removeEventListener('pointerdown',onPointerDown);renderer.domElement.removeEventListener('pointerup',onPointerUp);renderer.domElement.removeEventListener('keydown',onKey);renderer.domElement.removeEventListener('webglcontextlost',onContextLost);document.removeEventListener('visibilitychange',onVisibility);
      scene.traverse(o=>{if(o.geometry)geometries.add(o.geometry);if(o.material){const ms=Array.isArray(o.material)?o.material:[o.material];ms.forEach(m=>materials.add(m));}});
      for(const g of geometries)g.dispose();for(const m of materials)m.dispose();for(const t of textures)t.dispose();bloomPass?.dispose();outputPass?.dispose();compositePass?.dispose();bloomComposer?.dispose();composer?.dispose();mirror?.getRenderTarget().dispose();envTarget.dispose();renderer.dispose();renderer.domElement.remove();overlay.remove();listeners.clear();if(!hadHostClass)container.classList.remove('agent-studio');
    },
  };
  currentCamera='front';camera.position.copy(fittedPosition('front'));controls.target.fromArray(cameraPresets.front.target);controls.update();
  if(mode==='demo')applyStage(0,true);else {setMeeting([],'等待真实 Agent 运行事件。',true);for(const r of agents.values())r.status='waiting';}
  lastFrame=performance.now();animationFrame=requestAnimationFrame(render);
  return api;
}
