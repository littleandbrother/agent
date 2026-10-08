"""Build a traceable JLCEDA Pro exchange project and Specctra routing input.

Symbols and pads come from recorded live JLCEDA library exports.  The independent
netlist is authoritative for this draft; native ERC/DRC remains a separate gate.
"""
import argparse, csv, hashlib, html, json, math, re, zipfile
from pathlib import Path

MIL=.0254
def records(text):
    return [tuple(map(json.loads,line.rstrip('|').split('||'))) for line in text.splitlines() if '||' in line]
def uid(s):return hashlib.sha256(s.encode()).hexdigest()[:32]
def esc(s):return html.escape(str(s))
def main():
    p=argparse.ArgumentParser();p.add_argument('case',type=Path);p.add_argument('--definition',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();root=a.case;out=a.output or root/'pcb/D2';out.mkdir(parents=True,exist_ok=True)
    config=json.loads(a.definition.read_text()) if a.definition else {}
    # ref, supplier ID, x/y mm; all placement on top, angle 0.
    spec=[('U1','C685115',24,15),('U2','C2828282',61,18),('C1','C555369',18,9),('C2','C15849',24,10),('C3','C19666',25,20),('C4','C15008',34,17),('C5','C14663',54,13),('L1','C503307',29,11)]
    nets={'U1':{'1':'PZ1','2':'PZ2','3':'CAP','4':'VIN','5':'SW','6':'VOUT','7':'VIN2','8':'VIN2','9':'GND','10':'PGOOD','11':'GND'},
          'U2':{'1':'GND','11':'VOUT','12':'GND','24':'GND','25':'PGOOD','26':'DEBUG','36':'SWDCLK','37':'SWDIO','39':'GND'},
          'C1':{'1':'VIN','2':'GND'},'C2':{'1':'CAP','2':'VIN'},'C3':{'1':'VIN2','2':'GND'},'C4':{'1':'VOUT','2':'GND'},'C5':{'1':'VOUT','2':'GND'},'L1':{'1':'SW','2':'VOUT'},
          'J1':{'1':'PZ1','2':'PZ2'},'J2':{'1':'VOUT','2':'GND','3':'SWDIO','4':'SWDCLK'},'J3':{'1':'DEBUG','2':'GND'}}
    spec=config.get('components',spec);nets=config.get('nets',nets)
    libs=[];parts=[];seen=set()
    for ref,lcsc,x,y in spec:
        d=root/'circuit/libraries'/lcsc;info=json.loads((d/'device2.json').read_text());dev=next(iter(info['devices'].values()));attrs=dev['attributes'];r=records((d/'ProLib_pc_2026-09-29.elibu').read_text());ctx=None;pins={};pinattrs={};pads=[];partid=None
        for h,v in r:
            if h['type']=='DOCHEAD':ctx=v['docType']
            if ctx=='SYMBOL' and h['type']=='PART':partid=h['id']
            if ctx=='SYMBOL' and h['type']=='PIN':pins[h['id']]=v
            if ctx=='SYMBOL' and h['type']=='ATTR':pinattrs.setdefault(v.get('parentId'),{})[v['key']]=v.get('value')
            if ctx=='FOOTPRINT' and h['type']=='PAD':pads.append(dict(v,id=h['id']))
        if lcsc not in seen:libs+=r;seen.add(lcsc)
        parts.append(dict(ref=ref,lcsc=lcsc,x=x,y=y,attrs=attrs,device=dev['uuid'],partid=partid,pins=[dict(v,num=pinattrs[k].get('Pin Number'),name=pinattrs[k].get('Pin Name')) for k,v in pins.items()],pads=pads))
    for ref,n,x,y in config.get('headers',[('J1',2,11,15),('J2',4,44,9),('J3',2,44,22)]):
        pads=[dict(id='p'+str(i+1),num=str(i+1),centerX=0,centerY=(i-(n-1)/2)*100,padAngle=0,defaultPad={'padType':'ELLIPSE','width':70.866,'height':70.866},hole={'holeType':'ROUND','width':39.37,'height':39.37},layerId=12,plated=True) for i in range(n)]
        procurement=config.get('header_parts',{}).get(ref,{})
        attrs={'Manufacturer Part':procurement.get('mpn','Generic 2.54mm header - qualification pending'),'Footprint':uid(ref+'foot'),'Symbol':uid(ref+'sym'),'Value':str(n)+' pin','Supplier Part':procurement.get('lcsc','')}
        parts.append(dict(ref=ref,lcsc=procurement.get('lcsc'),x=x,y=y,attrs=attrs,device=uid(ref+'device'),partid=ref+'.1',pins=[dict(x=-30,y=i*20,num=str(i+1),name=nets[ref][str(i+1)],rotation=0) for i in range(n)],pads=pads,custom=True))
    for c in parts:
        if not set(nets[c['ref']]).issubset({str(p['num']) for p in c['pads']}):raise ValueError('NET_PIN_NOT_IN_FOOTPRINT')
    # Explicit no-connect declarations, including DEC4/DCC in LDO mode. Internal
    # DEC4 1uF is documented in Raytac Version O p.30; DCDC is not enabled in firmware.
    nc={c['ref']:[str(p['num']) for p in c['pads'] if str(p['num']) not in nets[c['ref']]] for c in parts}
    netlist={'design':'door-magnetic-D2','components':parts,'nets':nets,'no_connects':nc,'board_mm':[80,30,1.6],'mounting_holes_mm':[[4,4,2.4],[76,4,2.4],[4,26,2.4],[76,26,2.4]],'rf_keepout_mm':[52,24.2,70,30],'rf_notch_mm':[58.8,21,63,24.2],'native_erc':None,'native_drc':None,'manufacturing_released':False}
    for k in ['design','rf_keepout_mm','rf_notch_mm','mounting_holes_mm','scope']:
        if k in config:netlist[k]=config[k]
    (out/'board.json').write_text(json.dumps(netlist,indent=2,ensure_ascii=False))
    with (out/'bom.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['reference','part','lcsc','value','x_mm','y_mm','side','angle_deg'])
        for c in parts:w.writerow([c['ref'],c['attrs']['Manufacturer Part'],c['lcsc'],c['attrs'].get('Value',''),c['x'],c['y'],'top',0])
    # Standard Specctra DSN: true pad dimensions, all unused pads retained as obstacles.
    dsn=['(pcb door-D2 (parser (string_quote ")) (resolution um 10) (unit um)', '(structure (layer F.Cu (type signal) (property (index 0))) (layer B.Cu (type signal) (property (index 1))) (boundary (rect pcb 0 0 80000 30000)) (via Via) (rule (width 152.4) (clearance 165.1))']
    for layer in ['F.Cu','B.Cu']:
        for name in ['rf_keepout_mm','rf_notch_mm']:
            box=netlist[name]
            if box[2]>box[0] and box[3]>box[1]:dsn.append(f'(keepout {name}_{layer} (rect {layer} '+ ' '.join(str(v*1000) for v in box)+'))')
        for i,(x,y,_) in enumerate(netlist['mounting_holes_mm']):dsn.append(f'(keepout hole{i}_{layer} (circle {layer} 3400 {x*1000} {y*1000}))')
    dsn.append(') (placement')
    for c in parts:dsn.append(f'(component {c["ref"]} (place {c["ref"]} {c["x"]*1000} {c["y"]*1000} front 0))')
    dsn.append(') (library');stacks=[]
    for c in parts:
        dsn.append(f'(image {c["ref"]}')
        for p in c['pads']:
            name=c['ref']+'_'+p['num'];w=p['defaultPad']['width']*25.4;h=p['defaultPad']['height']*25.4;angle=p.get('padAngle',0)
            dsn.append(f'(pin {name} (rotate {angle}) {p["num"]} {p["centerX"]*25.4:.5f} {p["centerY"]*25.4:.5f})')
            shape='circle' if abs(w-h)<.01 and p['defaultPad']['padType'] in ('ELLIPSE','OVAL') else 'rect'
            layers=['F.Cu','B.Cu'] if p.get('hole') else ['F.Cu']
            shapes=' '.join(f'(shape (circle {ly} {w:.5f}))' if shape=='circle' else f'(shape (rect {ly} {-w/2:.5f} {-h/2:.5f} {w/2:.5f} {h/2:.5f}))' for ly in layers)
            stacks.append(f'(padstack {name} {shapes} (attach off))')
        dsn.append(')')
    dsn+=stacks;dsn.append('(padstack Via (shape (circle F.Cu 650)) (shape (circle B.Cu 650)) (attach off))) (network')
    names=sorted({v for m in nets.values() for v in m.values()})
    for n in names:dsn.append(f'(net {n} (pins '+ ' '.join(c+'-'+p for c,m in nets.items() for p,v in m.items() if v==n)+'))')
    dsn.append('(class default '+' '.join(names)+' (circuit (use_via Via)) (rule (width 152.4) (clearance 165.1)))) (wiring))')
    (out/'door.dsn').write_text('\n'.join(dsn))
    # Valid documented line-record source; JLCEDA native import is a separate check.
    rr=[];ticket=0
    def put(t,v,i=None):
        nonlocal ticket
        ticket+=1;rr.append(({'type':t,'id':i or uid(str(ticket)),'ticket':ticket},v))
    def doc(t,u,title,**kw):
        rr.append(({'type':'DOCHEAD'},{'docType':t,'uuid':u,'editVersion':'3.2.148','client':netlist['design'],'version':'1','user':{}}));put('META',dict(title=title,**kw),'META')
    rr+=libs
    for c in parts:
        doc('DEVICE',c['device'],c['attrs']['Manufacturer Part'],attributes=c['attrs'])
        if c.get('custom'):
            doc('FOOTPRINT',c['attrs']['Footprint'],c['ref']+'_2.54mm')
            for p in c['pads']:put('PAD',{k:v for k,v in p.items() if k!='id'},p['id'])
            doc('SYMBOL',c['attrs']['Symbol'],c['ref']);put('PART',{'title':c['partid'],'BBOX':[-20,-10,20,20*len(c['pins'])]},c['partid'])
            for p in c['pins']:
                pi=uid(c['ref']+p['num']);put('PIN',dict(partId=c['partid'],x=p['x'],y=p['y'],length=10,rotation=0,display=True),pi)
                for k,v in [('Pin Number',p['num']),('Pin Name',p['name'])]:put('ATTR',dict(partId=c['partid'],parentId=pi,key=k,value=v,valueVisible=True))
    board,sch,page,pcb=[uid(netlist['design']+s) for s in ['board','sch','page','pcb']]
    doc('BOARD',board,netlist['design']);doc('SCH',sch,'Door power and radio',board=board);doc('SCH_PAGE',page,netlist['design']+' schematic',schematic=sch)
    # Every pin connects to a short, explicitly named net. This avoids wire crossings.
    for index,c in enumerate(parts):
        x=220+(index%4)*320;y=160+(index//4)*380;ci=uid('sch'+c['ref'])
        put('COMPONENT',dict(partId=c['partid'],x=x,y=y,rotation=0,isMirror=False,attrs={},zIndex=index),ci)
        for key,value in [('Symbol',c['attrs']['Symbol']),('Device',c['device']),('Footprint',c['attrs']['Footprint']),('Designator',c['ref'])]:put('ATTR',dict(parentId=ci,key=key,value=value,x=x,y=y-130,valueVisible=key=='Designator',rotation=0))
        for p in c['pins']:
            n=nets[c['ref']].get(str(p['num']))
            if not n:continue
            px=x+p['x'];py=y+p['y'];ang=math.radians(p.get('rotation',0));ex=px-25*math.cos(ang);ey=py-25*math.sin(ang);wi=uid(ci+p['num'])
            put('WIRE',dict(zIndex=ticket),wi);put('LINE',dict(startX=px,startY=py,endX=ex,endY=ey,lineGroup=wi));put('ATTR',dict(parentId=wi,key='NET',value=n,x=ex,y=ey,valueVisible=True,rotation=0))
    doc('PCB',pcb,netlist['design']+' routed board',board=board,parent='')
    for c in parts:
        ci=uid('pcb'+c['ref']);put('COMPONENT',dict(positionX=c['x']/MIL,positionY=c['y']/MIL,angle=0,layerId=1,attrs=dict(c['attrs'],Designator=c['ref'],Device=c['device']),locked=False,zIndex=1),ci)
        for p in c['pads']:put('PAD_NET',dict(padNum=p['num'],padNet=nets[c['ref']].get(p['num'],''),padId=p['id']),ci)
    for x1,y1,x2,y2 in [(0,0,80,0),(80,0,80,30),(80,30,0,30),(0,30,0,0)]:put('LINE',dict(layerId=11,startX=x1/MIL,startY=y1/MIL,endX=x2/MIL,endY=y2/MIL,width=4,netName=''))
    (out/'source-records.json').write_text(json.dumps(rr,ensure_ascii=False))
    write_project(out,rr,netlist['design'])
    schematic_svg(out,parts,nets,nc,netlist['design'])
    print(json.dumps({'parts':len(parts),'nets':len(names),'pads':sum(len(c['pads']) for c in parts),'output':str(out)}))

def write_project(out,rr,design='door-magnetic-D2'):
    stem='door-D2' if design=='door-magnetic-D2' else design
    text='\n'.join(json.dumps(h,separators=(',',':'))+'||'+json.dumps(v,ensure_ascii=False,separators=(',',':'))+'|' for h,v in rr)+'\n'
    (out/(stem+'.epru')).write_text(text)
    with zipfile.ZipFile(out/(stem+'.epro2'),'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('project2.json',json.dumps({'title':design+' - engineering draft','editorVersion':'3.2.148','cbb_project':0,'description':'Native ERC/DRC pending; cold start failed; not released for manufacture.'}));z.writestr(stem+'.epru',text)

def schematic_svg(out,parts,nets,nc,design='door-magnetic-D2'):
    # Pin-labelled functional schematic generated from the same netlist, not a PCB picture.
    s=['<svg xmlns="http://www.w3.org/2000/svg" width="1700" height="1100" viewBox="0 0 1700 1100"><rect width="1700" height="1100" fill="white"/><style>text{font-family:Arial,sans-serif;fill:#182536} .net{fill:#17634a} .wire{stroke:#17634a;stroke-width:2} .box{fill:#f5f8fb;stroke:#24394e;stroke-width:2}</style><text x="40" y="45" font-size="26">Door D2 | LTC3588-1 power path + nRF52832 / MDBT42Q-512KV2</text><text x="40" y="75" font-size="16">Named nets are electrically connected. Supply 3.3 V; LDO radio mode. Native ERC pending.</text>']
    for idx,c in enumerate(parts):
        col=idx%4;row=idx//4;x=90+col*410;y=135+row*310;active=[p for p in c['pins'] if str(p['num']) in nets[c['ref']]];h=max(80,len(active)*21+38)
        s.append(f'<rect class="box" x="{x}" y="{y}" width="230" height="{h}" rx="4"/><text x="{x+10}" y="{y+22}" font-size="19">{c["ref"]} · {esc(c["attrs"].get("Value") or c["lcsc"] or "2.54mm")}</text>')
        for i,p in enumerate(active):
            yy=y+47+i*21;n=nets[c['ref']][str(p['num'])];s.append(f'<text x="{x+9}" y="{yy}" font-size="13">{p["num"]} {esc(p.get("name",""))}</text><path class="wire" d="M {x+230},{yy-4} h 25"/><text class="net" x="{x+260}" y="{yy}" font-size="13">{n}</text>')
        if nc[c['ref']]:s.append(f'<text x="{x}" y="{y+h+18}" font-size="11">NC: {esc(", ".join(nc[c["ref"]]))}</text>')
    s.append('<text x="40" y="1080" font-size="14">D2 / 2026-09-30 | Library-derived pin identities; Gerber and native validation are separate deliverables.</text></svg>');(out/'schematic.svg').write_text('\n'.join(s))

if __name__=='__main__':main()
