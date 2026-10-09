/** Native, high-resolution display graphics. Numbers and routes are illustrative.
 * Keep them independent from runtime status: the host owns engineering evidence.
 */
export function createStudioScreens(canvasTex) {
  const C={bg:'#0d1d2c',panel:'#132a3a',edge:'#345063',ink:'#ecf5fc',muted:'#9db5c6',orange:'#ffb35d',teal:'#57dce1',green:'#a6d786',gold:'#ffcf66',purple:'#c0a2ff'};
  const font='Arial, sans-serif';
  function text(c,s,x,y,size=26,color=C.ink,weight=500,align='left',family=font){c.fillStyle=color;c.font=`${weight} ${size}px ${family}`;c.textAlign=align;c.textBaseline='alphabetic';c.fillText(s,x,y);}
  function rect(c,x,y,w,h,fill,stroke=null,r=12){c.beginPath();c.roundRect(x,y,w,h,r);if(fill){c.fillStyle=fill;c.fill();}if(stroke){c.strokeStyle=stroke;c.lineWidth=2;c.stroke();}}
  function path(c,points,color,width=3){c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.strokeStyle=color;c.lineWidth=width;c.lineJoin='round';c.lineCap='round';c.stroke();}
  function circle(c,x,y,r,fill,stroke=null,width=2){c.beginPath();c.arc(x,y,r,0,Math.PI*2);if(fill){c.fillStyle=fill;c.fill();}if(stroke){c.strokeStyle=stroke;c.lineWidth=width;c.stroke();}}
  function arrow(c,x1,y1,x2,y2,color=C.teal,width=3){path(c,[[x1,y1],[x2,y2]],color,width);const a=Math.atan2(y2-y1,x2-x1);path(c,[[x2-12*Math.cos(a-.5),y2-12*Math.sin(a-.5)],[x2,y2],[x2-12*Math.cos(a+.5),y2-12*Math.sin(a+.5)]],color,width);}
  function badge(c,label,x,y,color,w=128){rect(c,x,y,w,34,color,null,8);text(c,label,x+w/2,y+24,20,C.bg,700,'center');}
  function grid(c,x,y,w,h,step=38){c.save();c.beginPath();c.rect(x,y,w,h);c.clip();for(let a=x;a<=x+w;a+=step)path(c,[[a,y],[a,y+h]],'#233d50',1);for(let a=y;a<=y+h;a+=step)path(c,[[x,a],[x+w,a]],'#233d50',1);c.restore();}
  function screen(w,h,title,color,draw){
    return canvasTex(w*2,h*2,c=>{
      c.scale(2,2);c.fillStyle=C.bg;c.fillRect(0,0,w,h);
      path(c,[[24,65],[w-24,65]],C.edge,2);circle(c,33,33,6,color);
      text(c,title,51,44,30,C.ink,600);badge(c,'DEMO',w-117,16,color,93);
      draw(c,w,h);
    });
  }
  function pcbDrawing(c,x,y,w,h,showLabels=true){
    c.save();c.translate(x,y);c.scale(w/570,h/345);
    rect(c,0,0,570,345,'#103e30','#82b88a',12);
    const traces=['#b8c979','#78a864','#d6ce88'];
    for(let i=0;i<22;i++){
      const yy=25+i*13;
      path(c,[[18,yy],[55+i%4*8,yy],[90+i%5*11,yy+20],[137,yy+20],[173,Math.min(317,yy+48)],[230,Math.min(317,yy+48)]],traces[i%3],2.4);
      path(c,[[553,yy],[490-i%4*9,yy],[460-i%3*13,yy+25],[420,yy+25],[396,Math.min(324,yy+45)],[361,Math.min(324,yy+45)]],traces[(i+1)%3],2.4);
    }
    for(let i=0;i<12;i++)path(c,[[212+i*12,17],[212+i*12,51],[231+i*9,71],[231+i*9,110]],traces[i%3],2);
    for(let i=0;i<9;i++)path(c,[[247+i*11,252],[247+i*11,282],[210+i*16,306],[210+i*16,332]],traces[i%3],2);
    path(c,[[30,314],[106,314],[152,268],[193,268],[210,250],[210,98],[181,67],[146,67]],'#f6d07b',5);
    path(c,[[349,198],[380,198],[404,222],[496,222],[530,257]],'#f6d07b',5);
    function chip(xx,yy,ww,hh,label){
      for(let i=0;i<8;i++){const offset=(i+1)*ww/9;rect(c,xx+offset-2,yy-10,4,14,'#e3ca8a',null,1);rect(c,xx+offset-2,yy+hh-4,4,14,'#e3ca8a',null,1);}
      for(let i=0;i<8;i++){const offset=(i+1)*hh/9;rect(c,xx-10,yy+offset-2,14,4,'#e3ca8a',null,1);rect(c,xx+ww-4,yy+offset-2,14,4,'#e3ca8a',null,1);}
      rect(c,xx,yy,ww,hh,'#14212b','#728777',3);circle(c,xx+9,yy+9,3,'#c2d3bd');
      if(showLabels)text(c,label,xx+ww/2,yy+hh/2+5,20,'#dbeac9',600,'center');
    }
    for(let i=0;i<24;i++){
      const xx=37+i%8*68,yy=42+Math.floor(i/8)*108;
      if(xx>185&&xx<355)continue;
      rect(c,xx,yy,22,10,'#173029','#d1cf92',2);rect(c,xx+1,yy+1,4,8,'#d6d7bd',null,1);rect(c,xx+17,yy+1,4,8,'#d6d7bd',null,1);
    }
    for(let i=0;i<30;i++)circle(c,37+i%10*53,31+Math.floor(i/10)*139,3.7,'#1a4835','#e0bf68',2);
    // Component bodies cover underlying copper/vias, keeping chip labels clear.
    chip(226,112,122,119,'MCU');chip(79,122,63,69,'AFE');chip(409,66,58,64,'PMIC');chip(404,262,59,37,'RF');
    for(const [xx,yy] of [[14,14],[556,14],[14,331],[556,331]])circle(c,xx,yy,6,'#112c25','#efd484',3);
    rect(c,175,303,139,34,'#1c2530','#677c73',3);for(let i=0;i<9;i++)rect(c,183+i*14,310,7,18,'#b7c0bb',null,1);
    if(showLabels){text(c,'SENSOR NODE',275,92,22,'#dbe9d6',600,'center');text(c,'ANT',471,323,19,'#dbe9d6');}
    c.restore();
  }
  const mechanical=screen(1140,532,'MECHANICAL / Assembly explorer',C.orange,c=>{
    rect(c,22,83,642,428,'#e5edf4');
    c.save();c.beginPath();c.rect(22,83,642,428);c.clip();
    for(let xx=42;xx<660;xx+=35)path(c,[[xx,83],[xx,510]],'#c6d3df',1);
    for(let yy=102;yy<510;yy+=35)path(c,[[22,yy],[664,yy]],'#c6d3df',1);
    const metal=c.createLinearGradient(173,0,484,0);metal.addColorStop(0,'#8295a6');metal.addColorStop(.3,'#faffff');metal.addColorStop(.65,'#b1c0cb');metal.addColorStop(1,'#718697');
    function ring(y,rx,ry,h){
      c.beginPath();c.ellipse(313,y+h,rx,ry,0,0,Math.PI*2);c.fillStyle='#899dad';c.fill();
      c.fillStyle=metal;c.fillRect(313-rx,y,rx*2,h);
      c.beginPath();c.ellipse(313,y,rx,ry,0,0,Math.PI*2);c.fillStyle=metal;c.fill();c.strokeStyle='#788d9f';c.lineWidth=2;c.stroke();
      c.beginPath();c.ellipse(313,y,rx*.65,ry*.67,0,0,Math.PI*2);c.fillStyle='#cad8e2';c.fill();c.stroke();
    }
    path(c,[[313,115],[313,465]],'#7195b0',2);
    ring(144,124,35,16);circle(c,313,141,16,'#c7dbe8','#87a8bd');
    ring(222,95,25,12);
    pcbDrawing(c,210,269,209,71,false);
    for(let i=0;i<6;i++){c.beginPath();c.ellipse(313,363+i*3,65,17,0,0,Math.PI*2);c.strokeStyle=i%2?'#c58a49':'#eecc95';c.lineWidth=3;c.stroke();}
    ring(441,118,35,20);
    for(const [yy,label] of [[145,'LID'],[223,'HOUSING'],[303,'BOARD'],[373,'COIL'],[447,'BASE']]){
      path(c,[[447,yy],[482,yy],[495,yy-8],[538,yy-8]],'#7393aa',2);text(c,label,548,yy-1,22,'#3e566c',600);
    }
    for(const xx of [193,433]){path(c,[[xx,211],[xx,435]],'#7b9ab0',2);for(const yy of [240,401]){rect(c,xx-5,yy,10,17,metal,'#718698',2);rect(c,xx-9,yy-3,18,6,'#d9e3ea','#718698',2);}}
    c.restore();
    rect(c,681,83,437,428,C.panel,C.edge);
    text(c,'DIMENSIONS',706,122,28,C.orange,600);
    c.strokeStyle='#bfd4e3';c.lineWidth=3;c.beginPath();c.ellipse(893,240,115,49,0,0,Math.PI*2);c.stroke();
    path(c,[[778,240],[778,270],[1008,270],[1008,240]],'#bfd4e3',3);
    arrow(c,778,164,1008,164,C.orange);arrow(c,1008,164,778,164,C.orange);
    path(c,[[778,175],[778,214]],C.edge,2);path(c,[[1008,175],[1008,214]],C.edge,2);
    text(c,'Ø 42.0 mm',893,154,32,C.ink,600,'center');
    rect(c,778,321,230,43,null,'#bfd4e3',7);arrow(c,1042,321,1042,364,C.orange);arrow(c,1042,364,1042,321,C.orange);
    text(c,'12.8 mm',893,409,30,C.ink,600,'center');
    path(c,[[706,434],[1093,434]],C.edge,2);text(c,'Al 6061 / PC',707,476,29,C.muted);
  });
  const circuit=screen(1024,512,'CIRCUIT / Low-power front end',C.teal,c=>{
    rect(c,22,84,980,408,C.panel,C.edge);text(c,'HARVEST  →  CONDITION  →  SENSE  →  TRANSMIT',49,125,26,C.muted,600);
    const nodes=[['INPUT',59,82],['RECT',259,134],['LDO',459,134],['MCU',658,145],['RF',879,74]];
    const centers=nodes.map(([label,x,w])=>x+w/2);
    for(let i=0;i<nodes.length-1;i++)arrow(c,nodes[i][1]+nodes[i][2],265,nodes[i+1][1],265,C.teal,4);
    nodes.forEach(([label,x,w],i)=>{
      text(c,label,x+w/2,182,33,C.ink,600,'center');
      if(i===0||i===4){path(c,[[x+w/2,266],[x+w/2,223],[x+8,204],[x+w-8,204],[x+w/2,223]],C.ink,4);}
      else if(i===1){path(c,[[x+w/2,221],[x+w/2+46,265],[x+w/2,310],[x+w/2-46,265],[x+w/2,221]],C.ink,3);for(const [dx,dy] of [[-23,0],[23,0],[0,-23],[0,23]]){path(c,[[x+w/2+dx-8,265+dy],[x+w/2+dx+8,265+dy]],C.teal,4);}}
      else {rect(c,x,218,w,94,'#203e51',C.teal,9);text(c,i===2?'VDD':'ULP',x+w/2,277,28,C.ink,600,'center');for(let k=0;k<4;k++){const px=x+24+k*28;path(c,[[px,208],[px,219]],C.teal,3);path(c,[[px,312],[px,324]],C.teal,3);}}
    });
    for(const x of centers.slice(1,4)){path(c,[[x,325],[x,349]],C.muted,2);path(c,[[x-13,351],[x+13,351]],C.muted,2);path(c,[[x-9,357],[x+9,357]],C.muted,2);path(c,[[x-4,363],[x+4,363]],C.muted,2);}
    rect(c,50,395,438,63,'#203e51');circle(c,79,426,7,C.teal);text(c,'SENSOR / I²C',103,437,29,C.ink,600);
    rect(c,511,395,463,63,'#203e51');circle(c,540,426,7,C.gold);text(c,'ENERGY-AWARE MCU',565,437,28,C.ink,600);
  });
  const pcb=screen(1024,512,'PCB / Routing workspace',C.green,c=>{
    rect(c,22,83,704,407,C.panel,C.edge);pcbDrawing(c,40,110,668,359);
    rect(c,744,83,258,407,C.panel,C.edge);text(c,'BOARD STACK',763,123,26,C.green,600);
    const layers=[['TOP',C.green],['SIGNAL',C.gold],['GROUND','#78becb'],['BOTTOM','#b7a1dc']];
    layers.forEach(([s,col],i)=>{rect(c,767,148+i*50,210,13,col,null,3);text(c,s,873,186+i*50,23,C.muted,500,'center');});
    path(c,[[764,357],[982,357]],C.edge,2);text(c,'4 LAYERS',873,400,31,C.ink,600,'center');text(c,'LAYOUT PREVIEW',873,450,22,C.muted,500,'center');
  });
  const power=screen(1280,506,'POWER / Energy flow & storage',C.gold,c=>{
    rect(c,22,83,575,400,C.panel,C.edge);text(c,'INPUT → OUTPUT',46,123,29,C.gold,600);grid(c,48,148,522,243,43);
    const ys=[191,268,346],colors=[C.gold,C.teal,C.green];
    ys.forEach((yy,n)=>{const pts=[];for(let x=51;x<566;x+=2){const a=(x-51)/515;pts.push([x,yy-(n===2?Math.min(42,a*49):Math.sin(a*60)*(n===0?17:8)+Math.sin(a*21)*9)]);}path(c,pts,colors[n],4);});
    text(c,'HARVEST',48,439,24,C.gold,600);text(c,'DC',274,439,24,C.teal,600);text(c,'STORAGE',405,439,24,C.green,600);
    rect(c,615,83,246,400,C.panel,C.edge);text(c,'PATH',738,123,28,C.gold,600,'center');
    ['HARVEST','RECTIFY','STORE','DELIVER'].forEach((label,i)=>{if(i)arrow(c,738,165+(i-1)*77+46,738,165+i*77-6,C.gold);rect(c,639,157+i*77,198,50,'#294052',C.edge,8);text(c,label,738,190+i*77,25,C.ink,600,'center');});
    rect(c,879,83,379,400,C.panel,C.edge);text(c,'CAPACITOR',1069,123,29,C.gold,600,'center');
    const metal=c.createLinearGradient(993,0,1143,0);metal.addColorStop(0,'#778a9a');metal.addColorStop(.35,'#e5f0f7');metal.addColorStop(.65,'#b5c7d4');metal.addColorStop(1,'#607385');
    rect(c,1002,167,130,216,metal,'#c8d9e5',18);rect(c,1047,151,40,19,'#c6d5df',null,5);rect(c,1038,233,59,131,C.gold,null,7);
    for(let i=0;i<3;i++){c.beginPath();c.ellipse(1067,392,94+i*14,13+i*5,0,0,Math.PI*2);c.strokeStyle=i===0?C.gold:'#53614e';c.lineWidth=3;c.stroke();}
    text(c,'STORE → WAKE',1069,450,28,C.ink,600,'center');
  });
  const firmware=screen(1280,490,'FIRMWARE / Embedded C & state sequence',C.purple,c=>{
    rect(c,22,83,657,386,C.panel,C.edge);text(c,'sensor_node.c',49,121,29,C.purple,600);
    path(c,[[45,138],[657,138]],C.edge,2);
    const rows=[['// energy-aware loop',C.green],['void loop() {',C.gold],['  if (energy_ready()) {',C.ink],['    sense();',C.teal],['    process();',C.ink],['    transmit();',C.purple],['  }',C.ink],['  deep_sleep();',C.teal],['}',C.gold]];
    rows.forEach(([s,col],i)=>{text(c,String(i+1).padStart(2,'0'),48,174+i*32,23,'#6c879b',400,'left','monospace');text(c,s,97,174+i*32,27,col,500,'left','monospace');});
    rect(c,697,83,561,386,C.panel,C.edge);text(c,'STATE MACHINE',977,124,30,C.purple,600,'center');
    const nodes=[['SENSE',977,184],['PROCESS',1133,279],['TX',977,374],['SLEEP',821,279]];
    arrow(c,1051,189,1106,246,C.purple);arrow(c,1106,312,1051,367,C.purple);arrow(c,903,367,847,312,C.purple);arrow(c,847,246,903,189,C.purple);
    nodes.forEach(([s,x,y])=>{rect(c,x-72,y-28,144,56,'#29334f',C.purple,12);text(c,s,x,y+10,27,C.ink,600,'center');});
    circle(c,977,277,29,null,'#615983',2);circle(c,977,277,12,C.purple);text(c,'LOW-POWER RUNTIME',977,443,25,C.muted,500,'center');
  });
  const signal=screen(480,512,'SIGNAL',C.teal,c=>{
    rect(c,20,85,440,407,C.panel,C.edge);grid(c,39,115,401,268,40);
    for(let n=0;n<2;n++){
      const pts=[];for(let x=40;x<440;x+=2){const t=(x-40)/400;pts.push([x,n===0?189-Math.sin(t*42)*34:302-(Math.sin(t*32)>0?28:0)]);}path(c,pts,n===0?C.gold:C.teal,4);
    }
    text(c,'VRECT',52,423,30,C.gold,600);text(c,'VDD',275,423,30,C.teal,600);text(c,'FRONT-END PREVIEW',240,468,24,C.muted,500,'center');
  });
  const runtime=screen(480,446,'RUNTIME',C.purple,c=>{
    ['SENSE','PROCESS','TRANSMIT','SLEEP'].forEach((s,i)=>{
      rect(c,30,86+i*83,420,63,C.panel,C.edge);circle(c,60,117+i*83,7,i===3?C.purple:C.teal);
      text(c,s,89,128+i*83,31,C.ink,600);
    });
  });
  return {mechanical,circuit,pcb,power,firmware,signal,runtime};
}
