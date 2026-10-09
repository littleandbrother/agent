import * as THREE from 'three';

// Small visual assemblies, kept separate from the event/movement controller.
// These are illustrative props, not engineering models or evaluated results.
export function createStudioDetails(kit) {
  const {box,cyl,torus,line,plane,mesh,mat,canvasTex,textPanel,pcb,
    white,chrome,pale,black,glass,softGlass,goldMetal,blueGlow,glowMaterial,quality}=kit;
  const tau=Math.PI*2;
  const graphite=mat(0x263647,{metalness:.46,roughness:.40,clearcoat:.35});
  const rubber=mat(0x101b28,{metalness:0,roughness:.78,clearcoat:0});
  const solder=mat(0xaebbc7,{metalness:.95,roughness:.29});
  const copper=mat(0xbb783b,{metalness:.9,roughness:.27});
  const red=mat(0xc45350,{roughness:.44,metalness:.18});
  const teal=mat(0x36a6b8,{roughness:.35,metalness:.32});
  const ceramic=mat(0xb7b19f,{roughness:.57,metalness:.06});
  const led=glowMaterial(0xbbddff,1.6);
  const brushing=canvasTex(256,256,c=>{
    c.fillStyle='#bababa';c.fillRect(0,0,256,256);
    for(let y=0;y<256;y++){
      const value=154+Math.round(Math.sin(y*2.1)*18+Math.sin(y*.31)*9);
      c.fillStyle=`rgb(${value},${value},${value})`;c.fillRect(0,y,256,1);
    }
  });
  brushing.colorSpace=THREE.NoColorSpace;
  const aluminum=mat(0xb9c7d3,{metalness:.94,roughness:.38,roughnessMap:brushing,clearcoat:.3});
  const silk=canvasTex(1024,680,c=>{
    c.clearRect(0,0,1024,680);c.strokeStyle='rgba(216,239,214,.65)';c.lineWidth=3;
    c.strokeRect(352,203,290,280);c.strokeRect(54,93,245,138);c.strokeRect(694,86,234,108);
    c.font='27px monospace';c.fillStyle='#d3e5d2';
    for(const [s,x,y] of [['U1',410,189],['U2',61,80],['C07',713,236],['J2',66,365],['RF',857,358],['DOT / NODE.01',382,623]])c.fillText(s,x,y);
    for(const [x,y] of [[74,49],[950,49],[74,628],[950,628]]){
      c.beginPath();c.arc(x,y,24,0,tau);c.stroke();c.beginPath();c.moveTo(x-33,y);c.lineTo(x+33,y);c.moveTo(x,y-33);c.lineTo(x,y+33);c.stroke();
    }
  });
  const silkMat=mat(0xffffff,{map:silk,transparent:true,depthWrite:false,roughness:.8,metalness:0,clearcoat:0});
  const pcbTracks=[
    [[-.40,-.28],[-.20,-.28],[-.12,-.20],[-.12,-.08]],
    [[-.40,-.24],[-.22,-.24],[-.16,-.18],[-.16,-.06]],
    [[-.40,.28],[-.19,.28],[-.09,.18],[-.09,.07]],
    [[-.35,.23],[-.21,.23],[-.12,.14],[-.12,.06]],
    [[.40,-.25],[.24,-.25],[.12,-.14],[.12,-.07]],
    [[.44,-.19],[.28,-.19],[.17,-.09],[.12,-.04]],
    [[.44,.27],[.26,.27],[.14,.15],[.14,.06]],
    [[.38,.22],[.27,.22],[.18,.12],[.13,.04]],
    [[-.34,-.07],[-.24,-.07],[-.19,0],[-.13,0]],
    [[-.35,.10],[-.24,.10],[-.20,.03],[-.13,.03]],
    [[.15,0],[.23,0],[.29,.07],[.42,.07]],
    [[-.38,-.30],[-.02,-.30],[.06,-.22],[.34,-.22]],
    [[-.03,.12],[-.03,.27],[.07,.30],[.42,.30]],
    [[.42,.12],[.48,.12],[.48,.03],[.44,.03],[.44,-.06],[.49,-.06]],
  ];
  function track(parent,points,y,material=copper,width=.008) {
    for(let i=1;i<points.length;i++){
      const [x0,z0]=points[i-1],[x1,z1]=points[i];
      const segment=box(parent,width,.002,Math.hypot(x1-x0,z1-z0),material,(x0+x1)/2,y,(z0+z1)/2,.001);
      segment.rotation.y=Math.atan2(x1-x0,z1-z0);
    }
  }
  function sticker(parent,text,w,h,x,y,z,flat=false,color='#667a8d',background='rgba(235,242,247,.94)') {
    const p=textPanel(parent,text,w,h,color,background);p.position.set(x,y,z);
    if(flat)p.rotation.x=-Math.PI/2;p.castShadow=false;return p;
  }
  function surface(parent,texture,w,d,x,y,z) {
    const p=plane(parent,w,d,mat(0xffffff,{map:texture,roughness:.85,metalness:0,clearcoat:0}),x,y,z);
    p.rotation.x=-Math.PI/2;return p;
  }
  function bolt(parent,x,y,z,r=.022) {
    cyl(parent,r,.026,solder,x,y,z,6);
    box(parent,r*1.25,.003,.006,graphite,x,y+.014,z,.001);
  }
  function tray(parent,x,y,z,w=.64,d=.43) {
    const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);
    box(g,w,.045,d,aluminum,0,0,0,.017);box(g,w-.05,.017,d-.05,graphite,0,.027,0,.010);
    for(const xx of [-1,1])box(g,.023,.058,d,aluminum,xx*(w/2-.012),.021,0,.007);
    for(const zz of [-1,1])box(g,w,.058,.023,aluminum,0,.021,zz*(d/2-.012),.007);
    return g;
  }
  function instrument(parent,x,y,z,w=.67,h=.36,label='TEST',color='#9bd8e9') {
    const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);
    box(g,w,h,.33,white,0,0,0,.035);box(g,w-.035,h-.035,.015,aluminum,0,0,.174,.014);
    box(g,w*.61,h*.50,.01,black,-w*.105,h*.08,.187,.012);
    sticker(g,label,w*.57,h*.31,-w*.105,h*.08,.197,false,color,'rgba(13,32,46,1)');
    for(let i=0;i<2;i++){
      const knob=cyl(g,.032,.029,graphite,w*.37,h*.19-i*h*.37,.189,16);knob.rotation.x=Math.PI/2;
      box(g,.004,.023,.006,solder,w*.37,h*.19-i*h*.37+.015,.208,.001);
    }
    for(let i=0;i<3;i++){
      const socket=cyl(g,.016,.012,i===0?red:rubber,-w*.33+i*w*.14,-h*.30,.188,12);socket.rotation.x=Math.PI/2;
    }
    for(const xx of [-1,1])box(g,.063,.026,.15,rubber,xx*w*.33,-h/2-.01,0,.007);
    return g;
  }
  function board(g) {
    const mask=plane(g,1.035,.684,silkMat,0,.024,0);mask.rotation.x=-Math.PI/2;mask.castShadow=false;
    pcbTracks.forEach((points,i)=>track(g,points,.027,i%3===0?goldMetal:copper,i%4===0?.012:.007));
    box(g,.255,.058,.255,black,.02,.060,0,.010);
    box(g,.195,.002,.195,graphite,.02,.090,0,.006);
    for(let i=0;i<8;i++){
      const s=-.088+i*.030;
      for(const side of [-1,1]){
        box(g,.034,.010,.014,solder,side*.139+.02,.039,s,.002);
        box(g,.014,.010,.034,solder,s+.02,.039,side*.139,.002);
      }
    }
    for(const [x,z,w,d] of [[-.335,-.16,.16,.10],[.32,-.195,.14,.08],[-.285,.19,.12,.09]]){
      box(g,w,.044,d,black,x,.049,z,.006);
      for(let i=0;i<4;i++)for(const side of [-1,1])box(g,.015,.009,.030,solder,x-w*.34+i*w*.22,.031,z+side*d*.58,.002);
    }
    for(let i=0;i<12;i++){
      const x=i<6?.255+(i%3)*.085:-.385+(i%3)*.078,z=i<6?-.035+Math.floor(i/3)*.092:.06+Math.floor((i-6)/3)*.075;
      box(g,.047,.027,.027,i%3===0?black:ceramic,x,.037,z,.004);
      for(const side of [-1,1])box(g,.011,.014,.029,solder,x+side*.024,.033,z,.002);
    }
    box(g,.063,.078,.29,rubber,-.455,.061,0,.005);
    for(let i=0;i<6;i++)box(g,.025,.112,.018,goldMetal,-.455,.065,-.125+i*.050,.002);
    box(g,.115,.028,.059,aluminum,.24,.042,-.30,.012);
    const viaCount=quality==='low'?14:28;
    for(let i=0;i<viaCount;i++){
      const x=-.40+(i%7)*.128,z=-.285+Math.floor(i/7)*.178;
      if(Math.abs(x)<.17&&Math.abs(z)<.17)continue;
      cyl(g,.012,.002,goldMetal,x,.029,z,12);cyl(g,.0045,.003,black,x,.031,z,8);
    }
    for(const x of [-.44,.44])for(const z of [-.26,.26]){
      torus(g,.023,.006,goldMetal,x,.028,z);cyl(g,.011,.003,black,x,.030,z,12);
    }
    box(g,.20,.077,.12,aluminum,.30,.060,.325,.011);box(g,.13,.024,.003,black,.30,.069,.388,.003);
    for(let i=0;i<5;i++)box(g,.011,.003,.04,goldMetal,.263+i*.018,.052,.337,.001);
  }
  function mechanical(g) {
    const fixture=tray(g,-1.26,.565,.34,.74,.64);
    for(let r=0;r<4;r++)for(let c=0;c<4;c++)cyl(fixture,.017,.004,black,-.25+c*.166,.040,-.21+r*.14,12);
    for(const side of [-1,1]){
      box(fixture,.095,.14,.35,aluminum,side*.235,.111,0,.012);
      bolt(fixture,side*.235,.196,-.12);bolt(fixture,side*.235,.196,.12);
    }
    torus(fixture,.126,.026,chrome,0,.105,0);cyl(fixture,.075,.075,graphite,0,.08,0,24);
    // A compact digital caliper and a dimensioned drawing mat.
    const caliper=new THREE.Group();caliper.position.set(.81,.567,1.26);caliper.rotation.y=-.30;g.add(caliper);
    box(caliper,.91,.021,.035,aluminum,0,0,0,.004);
    for(const x of [-.37,-.05]){
      box(caliper,.045,.031,.24,aluminum,x,.010,-.085,.006);
      box(caliper,.10,.022,.037,aluminum,x+.026,.010,-.211,.004);
    }
    box(caliper,.18,.055,.14,graphite,-.015,.027,0,.010);
    sticker(caliper,'12.80',.14,.055,-.015,.056,0,true,'#19384c','rgba(169,197,181,1)');
    for(let i=0;i<21;i++)box(caliper,.004,.002,i%5===0?.033:.019,graphite,-.39+i*.037,.012,.012,.001);
    const drawing=canvasTex(640,420,c=>{
      c.fillStyle='#edf2f7';c.fillRect(0,0,640,420);c.strokeStyle='#9aaebe';c.lineWidth=2;
      c.strokeRect(12,12,616,396);c.beginPath();c.arc(215,206,105,0,tau);c.arc(215,206,67,0,tau);c.stroke();
      for(let i=0;i<6;i++){const a=i/6*tau;c.beginPath();c.arc(215+Math.sin(a)*86,206+Math.cos(a)*86,8,0,tau);c.stroke();}
      c.strokeRect(381,134,162,49);c.beginPath();c.moveTo(114,70);c.lineTo(317,70);c.moveTo(114,61);c.lineTo(114,83);c.moveTo(317,61);c.lineTo(317,83);c.stroke();
      c.font='18px monospace';c.fillStyle='#5c7489';c.fillText('ENCLOSURE / SECTION A',31,375);c.fillText('Ø 42.0',169,58);c.fillText('DEMO DRAWING',382,272);
    });
    surface(g,drawing,1.04,.69,.81,.528,1.36);
    const parts=tray(g,-.92,.563,1.65,.57,.27);
    for(let i=0;i<4;i++){bolt(parts,-.20+i*.13,.060,0,.019);torus(parts,.035,.008,chrome,-.19+i*.13,.044,.085);}
    line(g,[[1.32,.57,.75],[1.58,.57,.63],[1.67,.56,.82]],rubber,.010);
    box(g,.06,.037,.40,graphite,1.59,.55,1.28,.017);cyl(g,.015,.21,aluminum,1.59,.55,1.01,12).rotation.x=Math.PI/2;
  }
  function circuit(g) {
    instrument(g,1.24,1.12,.23,.79,.25,'CH1 / CH2');
    instrument(g,-1.30,.77,.15,.72,.34,'3.30 V  ·  DC');
    const breadboard=new THREE.Group();breadboard.position.set(-1.16,.554,.83);breadboard.rotation.y=.12;g.add(breadboard);
    box(breadboard,.74,.05,.36,white,0,0,0,.015);
    for(let r=0;r<4;r++)for(let c=0;c<13;c++)box(breadboard,.008,.003,.008,rubber,-.32+c*.052,.027,-.12+r*.079,.001);
    track(breadboard,[[-.32,.15],[.32,.15]],.028,red,.008);track(breadboard,[[-.32,-.15],[.32,-.15]],.028,teal,.008);
    box(breadboard,.13,.045,.10,black,0,.048,0,.006);
    line(g,[[-1.58,.575,.72],[-1.60,.63,.99],[-.96,.65,1.13],[-.92,.59,.86]],red,.011);
    line(g,[[-1.47,.57,.66],[-1.36,.65,.43],[-.90,.63,.50],[-.81,.59,.80]],teal,.010);
    line(g,[[1.41,.98,.42],[1.73,.77,.70],[1.74,.56,1.12],[1.14,.56,1.48],[.97,.56,1.31]],rubber,.015);
    const probe=box(g,.045,.038,.28,graphite,.97,.558,1.29,.010);probe.rotation.y=-.30;
    const tip=cyl(g,.008,.13,solder,.93,.558,1.11,12);tip.rotation.x=Math.PI/2;tip.rotation.z=-.30;
    const bins=tray(g,-.88,.56,1.67,.49,.24);
    for(let i=0;i<5;i++)box(bins,.045,.04,.055,i%2?ceramic:black,-.18+i*.09,.066,0,.004);
  }
  function pcbWorkspace(g) {
    // Optical inspection stand with an illuminated lens and a sample fixture.
    const inspection=new THREE.Group();inspection.position.set(-1.43,.53,-.08);g.add(inspection);
    box(inspection,.62,.06,.54,graphite,0,.03,0,.024);
    cyl(inspection,.046,.72,aluminum,0,.40,-.18,20);box(inspection,.33,.045,.053,aluminum,.12,.72,-.18,.008);
    cyl(inspection,.106,.16,white,.25,.70,-.18,24);cyl(inspection,.062,.035,black,.25,.598,-.18,24);
    torus(inspection,.086,.012,led,.25,.578,-.18);box(inspection,.18,.025,.13,ceramic,.25,.082,-.16,.006);
    const reel=cyl(g,.20,.07,aluminum,1.38,.571,1.51,32);cyl(g,.083,.075,black,1.38,.575,1.51,20);
    for(let i=0;i<8;i++){const a=i/8*tau;cyl(g,.027,.074,graphite,1.38+Math.sin(a)*.142,.575,1.51+Math.cos(a)*.142,12);}
    const tape=box(g,.115,.014,.62,rubber,1.24,.527,1.12,.004);tape.rotation.y=.29;
    for(let i=0;i<7;i++)box(g,.032,.011,.034,ceramic,1.18+i*.024,.543,.86+i*.078,.004);
    const chips=tray(g,-.84,.568,1.68,.56,.26);
    for(let i=0;i<4;i++)box(chips,.080,.05,.08,black,-.18+i*.12,.066,0,.007);
    for(const z of [.52,.82,1.12])cyl(g,.018,.37,goldMetal,1.78,.706,z,12);
    sticker(g,'INSPECT / ASSEMBLE',.90,.13,-1.26,.505,1.39,true);
  }
  function power(g) {
    const solar=new THREE.Group();solar.position.set(-1.27,.63,.58);solar.rotation.x=-.15;solar.rotation.y=.18;g.add(solar);
    box(solar,.64,.038,.51,aluminum,0,0,0,.020);
    const cell=mat(0x153752,{metalness:.54,roughness:.19,clearcoat:1});
    for(let r=0;r<3;r++)for(let c=0;c<4;c++){
      box(solar,.136,.008,.142,cell,-.226+c*.15,.025,-.157+r*.158,.005);
      for(let k=0;k<3;k++)box(solar,.125,.001,.002,solder,-.226+c*.15,.030,-.20+r*.158+k*.039,.001);
    }
    line(g,[[-1.48,.61,.75],[-1.69,.56,1.01],[-1.25,.55,1.24],[-.92,.56,1.05]],rubber,.010);
    const storage=tray(g,-1.22,.566,1.40,.65,.40);
    for(let i=0;i<3;i++){
      cyl(storage,.070,.17,aluminum,-.21+i*.20,.13,0,20);cyl(storage,.057,.012,black,-.21+i*.20,.225,0,20);
      box(storage,.006,.085,.011,goldMetal,-.21+i*.20,.11,.070,.001);
    }
    instrument(g,1.54,.78,-.22,.64,.35,'µA / ENERGY', '#e5ca80');
    for(let i=0;i<6;i++)box(g,.010,.034,.35,graphite,-1.59+i*.071,.89,-.13,.002);
    sticker(g,'HARVEST → STORE',.85,.13,-1.18,.506,1.05,true);
    const capBand=torus(g,.213,.012,graphite,.97,.91,.67);
    for(let i=0;i<5;i++)box(g,.018,.014,.036,goldMetal,.84+i*.061,.52,1.69,.003);
  }
  function firmware(g) {
    const debugAdapter=new THREE.Group();debugAdapter.position.set(-1.29,.57,.18);g.add(debugAdapter);
    box(debugAdapter,.50,.085,.24,graphite,0,.035,0,.014);box(debugAdapter,.33,.007,.19,aluminum,0,.081,0,.008);
    sticker(debugAdapter,'DEBUG / SWD',.29,.067,0,.087,0,true);
    for(let i=0;i<3;i++)cyl(debugAdapter,.010,.005,i===0?teal:i===1?goldMetal:red,-.15+i*.045,.090,.063,12);
    box(debugAdapter,.10,.033,.08,aluminum,-.30,.04,0,.006);
    line(g,[[-1.60,.607,.18],[-1.74,.56,.45],[-1.10,.54,.72],[-.77,.75,.38],[-.66,1.058,.19]],rubber,.013);
    line(g,[[-1.02,.60,.18],[-.85,.57,-.06],[.49,.545,-.15],[1.07,.56,.62]],teal,.009);
    instrument(g,1.52,.78,1.50,.67,.33,'SWD / UART', '#cdb9f0');
    const terminal=tray(g,-1.35,.55,1.65,.64,.24);
    for(let i=0;i<8;i++){box(terminal,.041,.048,.08,rubber,-.255+i*.072,.064,0,.004);cyl(terminal,.010,.055,goldMetal,-.255+i*.072,.105,0,8);}
    const pad=canvasTex(512,256,c=>{
      c.fillStyle='#283844';c.fillRect(0,0,512,256);c.strokeStyle='#566878';c.lineWidth=1;
      for(let x=0;x<512;x+=32){c.beginPath();c.moveTo(x,0);c.lineTo(x,256);c.stroke();}for(let y=0;y<256;y+=32){c.beginPath();c.moveTo(0,y);c.lineTo(512,y);c.stroke();}
      c.fillStyle='#98aab9';c.font='18px monospace';c.fillText('PROGRAM / TRACE / ITERATE',28,230);
    });
    surface(g,pad,.88,.42,1.04,.523,.93);
  }
  function workstation(g,config) {
    const edge=glowMaterial(config.color,.48);
    for(let i=0;i<10;i++){
      const a=i/10*tau,x=Math.sin(a)*2.365,z=Math.cos(a)*2.365;
      const clip=box(g,.13,.105,.014,aluminum,x,.265,z,.009);clip.rotation.y=a;
      const slit=box(g,.080,.010,.004,edge,x+Math.sin(a)*.009,.260,z+Math.cos(a)*.009,.002);slit.rotation.y=a;
    }
    box(g,2.80,.027,.14,aluminum,0,2.50,-.76,.010);box(g,2.55,.008,.040,led,0,2.482,-.70,.003);
    for(const x of [-.59,.59])bolt(g,x,1.083,-.15,.015);
    ({mechanical,circuit,pcb:pcbWorkspace,power,firmware}[config.id])(g);
  }
  function product({central,bottom,coil,board:boardLayer,housing,lid}) {
    for(let i=0;i<6;i++){
      const a=i/6*tau,x=Math.sin(a)*.554,z=Math.cos(a)*.554;
      bolt(bottom,x,.076,z,.022);cyl(bottom,.026,.114,aluminum,x,.128,z,16);
      torus(bottom,.037,.008,rubber,x,.188,z);
      bolt(lid,Math.sin(a)*.640,.052,Math.cos(a)*.640,.019);
      const vent=new THREE.Group();vent.position.set(Math.sin(a)*.709,0,Math.cos(a)*.709);vent.rotation.y=a;housing.add(vent);
      for(let k=0;k<3;k++)box(vent,.011,.063,.004,graphite,-.024+k*.024,.003,0,.002);
      cyl(housing,.022,.024,aluminum,Math.sin(a)*.586,.080,Math.cos(a)*.586,12);
    }
    const fluxMat=mat(0x3c4956,{metalness:.73,roughness:.35});
    for(let i=0;i<8;i++){
      const a=i/8*tau;
      mesh(new THREE.CylinderGeometry(.445,.445,.042,12,1,false,a,.54),fluxMat,coil,0,-.042,0);
    }
    cyl(coil,.105,.042,black,0,.052,0,24);cyl(coil,.079,.006,aluminum,0,.077,0,24);
    line(coil,[[.43,.02,-.09],[.49,.05,-.15],[.40,.08,-.21]],copper,.009);
    line(coil,[[.45,.026,.04],[.50,.063,.07],[.43,.086,.16]],copper,.009);
    const board=boardLayer.children.find(c=>c.isGroup);
    if(board){
      for(const x of [-.435,.435])for(const z of [-.256,.256]){
        cyl(board,.024,.067,solder,x,-.045,z,16);torus(board,.033,.006,rubber,x,-.077,z);
      }
      for(let i=0;i<5;i++)cyl(board,.022,.016,goldMetal,-.35+i*.165,-.033,.22,16);
    }
    // Fine seam rings, sapphire inset and an engraved lid mark.
    torus(housing,.682,.006,graphite,0,.055,0);torus(housing,.520,.008,aluminum,0,-.050,0);
    torus(lid,.559,.006,graphite,0,.069,0);torus(lid,.327,.008,aluminum,0,.070,0);
    for(let i=0;i<24;i++){
      const a=i/24*tau;
      const mark=box(lid,.005,.003,.025,pale,Math.sin(a)*.520,.074,Math.cos(a)*.520,.001);mark.rotation.y=a;
    }
    sticker(lid,'DOT / NODE.01',.42,.083,0,.083,.28,true,'#496784','rgba(224,237,247,.7)');
    for(const x of [-.12,0,.12])cyl(lid,.008,.005,blueGlow,x,.081,-.282,12);
    for(let i=0;i<12;i++){
      const a=i/12*tau,x=Math.sin(a)*1.62,z=Math.cos(a)*1.62;
      const projector=cyl(central,.045,.023,aluminum,x,.536,z,20);cyl(central,.026,.007,blueGlow,x,.552,z,16);
      if(i%3===0){const bracket=box(central,.09,.045,.16,graphite,x,.519,z,.012);bracket.rotation.y=a;}
    }
    for(let i=0;i<12;i++){
      const a=i/12*tau,clip=box(central,.12,.089,.024,aluminum,Math.sin(a)*2.535,.195,Math.cos(a)*2.535,.007);clip.rotation.y=a;
    }
  }
  function room(g) {
    // Two infrastructure cabinets and a few atrium finishes. The central
    // circulation and all specialist/meeting paths remain empty.
    for(const side of [-1,1]){
      const rack=new THREE.Group();rack.position.set(side*12.9,0,-6.8);rack.rotation.y=side*-.18;g.add(rack);
      box(rack,1.25,2.56,.62,white,0,1.30,0,.08);
      box(rack,1.10,2.29,.025,graphite,0,1.33,.33,.025);box(rack,1.11,2.32,.027,softGlass,0,1.33,.36,.030);
      for(let n=0;n<7;n++){
        box(rack,.91,.185,.032,aluminum,0,.39+n*.28,.365,.015);
        for(let k=0;k<6;k++)box(rack,.071,.007,.005,graphite,-.33+k*.111,.39+n*.28,.385,.001);
        cyl(rack,.014,.009,blueGlow,.41,.39+n*.28,.389,12).rotation.x=Math.PI/2;
      }
      sticker(rack,'STUDIO / COMPUTE',1.04,.12,0,2.36,.378,false,'#afc7d8','rgba(30,48,64,.98)');
      for(const x of [-.45,.45])box(rack,.08,.075,.37,rubber,x,.038,0,.012);
      // Small illuminated circulation marker outside the expanded stations.
      for(let i=0;i<5;i++)box(g,.045,.007,.22,led,side*10.6,.013,-7.7+i*.55,.003);
    }
    for(const x of [-7.2,7.2]){
      box(g,4.6,.06,.14,aluminum,x,8.3,-13.0,.020);box(g,4.43,.018,.08,led,x,8.267,-12.97,.007);
    }
    for(const side of [-1,1]){
      box(g,4.5,.82,.025,softGlass,side*5.6,.75,-10.7,.035);
      box(g,4.6,.045,.05,aluminum,side*5.6,1.18,-10.7,.010);
      for(const x of [-2.1,2.1])box(g,.030,1.02,.030,aluminum,side*5.6+x,.64,-10.7,.005);
    }
    const tablet=new THREE.Group();tablet.position.set(.10,.735,-9.3);tablet.rotation.x=-.28;g.add(tablet);
    box(tablet,.48,.029,.32,graphite,0,0,0,.018);box(tablet,.43,.008,.27,glass,0,.019,0,.014);
    for(let i=0;i<4;i++)box(tablet,.16+i*.040,.003,.012,teal,-.065,.025,-.08+i*.053,.002);
    sticker(g,'DESIGN · TEST · INTEGRATE',2.3,.22,0,1.19,-11.45,false,'#778b9d');
  }
  return {board,workstation,product,room,aluminum,brushing};
}
