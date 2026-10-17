#!/usr/bin/env python3
"""Source-bound engineering PDFs: shared candidate report renderer."""
import argparse
import array
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
from PIL import Image
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle

NAVY = '#102C4B'; BLUE = '#0077CF'; MUTED = '#657B92'; PALE = '#F3F8FD'
LINE = '#D8E5F1'; GREEN = '#168468'; RED = '#B74043'; ORANGE = '#A5681B'
STATUS = {'PASS':'已通过', 'FAIL':'需修复', 'UNEVALUABLE':'待核实',
          'NOT_CHECKED':'待检查', 'RECHECK_REQUIRED':'需复查'}
LABELS = {'source_domain':'采能源与模型', 'schematic_bom_pins':'原理图 / 器件 / 引脚',
          'pcb_connectivity_drc':'PCB 连接与 DRC', 'geometry_fit':'机械与装配',
          'firmware_event_logic':'固件事件逻辑', 'board_firmware_interfaces':'板级与固件接口',
          'power_load_chain':'供能与任务负载', 'delivery_version':'同版本交付'}


def brief(text, limit=92):
    """Display excerpt; the complete Pi-authored record travels with the report."""
    text=str(text)
    return text if len(text)<=limit else text[:limit-1]+'…'


def dimensions(values):
    return ' × '.join(f'{v:g}' for v in values)


def drc_summary(facts):
    labels={'Clearance Error':'间距问题','Connection Error':'连接问题'}
    return '；'.join(f'{n} 处{labels.get(k,k)}' for k,n in facts['drc'].items())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def verified_input(folder):
    record = json.loads((folder/'report-input.json').read_text())
    for asset in record['assets']:
        if asset['system_commit'] != record['system']['id']:
            raise ValueError('ASSET_CANDIDATE_MISMATCH')
        if hashlib.sha256((folder/asset['local_path']).read_bytes()).hexdigest() != asset['sha256']:
            raise ValueError('ASSET_HASH_MISMATCH:'+asset['local_path'])
    return record


def source_facts(data,folder):
    """Keep template numbers tied to source values, not report prose literals."""
    c=folder/'sources/candidate'
    params=json.loads((c/'project-chain/interface-params.json').read_text())
    assembly=json.loads((c/'assembly.json').read_text())
    parts={v['id']:v['geometry']['size_mm'] for v in assembly['parts']}
    gates=data['system']['validations']
    native=lambda k:gates[k]['findings']['findings']
    power=gates['power_load_chain']['findings']
    cadjob=next(j for j,v in data['system']['jobs'].items() if 'project-cad_summary.json' in v['artifacts'])
    cad=json.loads((folder/'sources/jobs'/cadjob/'project-cad_summary.json').read_text())
    native_geo=native('geometry_fit');native_sch=native('schematic_bom_pins')
    timing=gates['board_firmware_interfaces']['findings']['timing_contract']['facts']['firmware']
    header=(c/'project-fw-s132/app_policy.h').read_text()
    burst={key:int(re.search(r'#define\s+APP_POLICY_BURST_'+key+r'\s+\((\d+)u\)',header).group(1)) for key in ('EVENTS','MS')}
    return {'candidate_files':len(data['system']['files']),'cad_parts':cad['parts'],
            'cad_bbox_mm':[cad['bbox_mm'][k] for k in ('xlen','ylen','zlen')],'board_mm':native_geo['outline']['pcb_mm'],
            'board_thickness_mm':native_geo['outline']['cad_step_boards'][0]['bbox'][2],
            'schematic_components':native_sch['part_pin_net_correspondence']['components'],
            'schematic_pins':native_sch['part_pin_net_correspondence']['pins'],
            'drc':native('pcb_connectivity_drc')['fresh_drc_counts'],
            'assembly_sizes':parts,
            'timing':timing,'burst':burst,'parameters':params,
            'power':power,'source_refs':{
                'dimensions':'selected CAD job/project-cad_summary.json + geometry_fit evidence',
                'pcb_counts':'schematic_bom_pins + pcb_connectivity_drc current qualification',
                'timing':'board_firmware_interfaces/timing_contract + project-fw-s132/app_policy.h',
                'power':'power_load_chain current qualification + selected native RAW',
                'scenario':'project-chain/interface-params.json'}}


class Document:
    def __init__(self, path, data, mode='simple'):
        self.path = path; self.data = data; self.mode = mode
        self.w,self.h = landscape(A4) if mode == 'simple' else A4
        self.c = canvas.Canvas(str(path), pagesize=(self.w,self.h), pageCompression=1)
        self.c.setTitle('P01 工程报告 - '+('八页工程简报' if mode=='simple' else '工程技术详报'))
        self.c.setAuthor('BF Agent / Pi engineering authors / fixed renderer')
        self.bounds=[]; self.page=0

    def text(self, text, x, y, width, size=9.5, color=NAVY, bold=False, leading=None):
        style=ParagraphStyle('p',fontName='BF-Bold' if bold else 'BF-Regular',fontSize=size,
                             leading=leading or size*1.5,textColor=HexColor(color),wordWrap='CJK')
        p=Paragraph(escape(str(text)).replace('\n','<br/>'),style)
        _,height=p.wrap(width, self.h)
        p.drawOn(self.c,x,self.h-y-height)
        self.bounds.append({'page':self.page,'page_width':self.w,'page_height':self.h,'x':x,'y':y,'w':width,'h':height,'text':str(text)[:70]})
        return height

    def rect(self,x,y,w,h,fill=PALE,stroke=None,radius=5):
        self.c.setFillColor(HexColor(fill)); self.c.setStrokeColor(HexColor(stroke or fill))
        self.c.roundRect(x,self.h-y-h,w,h,radius,fill=1,stroke=bool(stroke))

    def line(self,x1,y1,x2,y2,color=LINE,width=.65,dash=None):
        self.c.saveState(); self.c.setStrokeColor(HexColor(color)); self.c.setLineWidth(width)
        self.c.setDash(dash or []); self.c.line(x1,self.h-y1,x2,self.h-y2); self.c.restoreState()

    def arrow(self,x1,y1,x2,y2,color=BLUE):
        self.line(x1,y1,x2,y2,color,.9)
        import math
        a=math.atan2(y2-y1,x2-x1)
        for da in (-.45,.45):
            self.line(x2,y2,x2-5*math.cos(a+da),y2-5*math.sin(a+da),color,.9)

    def panel(self,x,y,w,h,title,en=None):
        self.rect(x,y,w,h)
        self.rect(x+10,y+12,2.3,12,BLUE,radius=0)
        self.text(title,x+20,y+9,w-32,11.8,BLUE,True)
        if en:self.text(en,x+20,y+29,w-32,7.6,MUTED)
        return y+(48 if en else 33)

    def bullets(self,rows,x,y,w,size=9.7,gap=7):
        for row in rows:
            self.text('•',x,y,9,size,BLUE)
            y+=self.text(row,x+12,y,w-12,size)+gap
        return y

    def table(self,rows,x,y,widths,size=9.0):
        for n,row in enumerate(rows):
            heights=[]
            for text,width in zip(row,widths):
                st=ParagraphStyle('cell',fontName='BF-Bold' if n==0 else 'BF-Regular',fontSize=size,
                                  leading=size*1.48,wordWrap='CJK')
                heights.append(Paragraph(escape(str(text)).replace('\n','<br/>'),st).wrap(width-13,999)[1])
            h=max(heights)+12
            self.rect(x,y,sum(widths),h,'#E6F1FC' if n==0 else ('#FFFFFF' if n%2 else '#F8FBFE'),radius=0)
            px=x
            for text,width in zip(row,widths):
                self.text(text,px+6,y+6,width-13,size,BLUE if n==0 else NAVY,n==0)
                px+=width
            self.line(x,y+h,x+sum(widths),y+h)
            y+=h
        return y

    def image(self,path,x,y,w,h):
        image=Image.open(path); iw,ih=image.size
        scale=min(w/iw,h/ih); ww,hh=iw*scale,ih*scale
        self.c.drawImage(str(path),x+(w-ww)/2,self.h-y-(h+hh)/2,ww,hh,mask='auto')

    def svg(self,path,x,y,w,h):
        # The native EDA exports use SVG filters to color traces. Render them
        # through Chromium, which supports those filters, rather than svglib.
        raster=ROOT/'native-previews'/path.with_suffix('.png').name
        meta=json.loads((raster.parent/'native-previews.json').read_text())
        ref=next(v for v in meta['items'] if v['source']==path.name)
        if ref['source_sha256']!=hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('NATIVE_PREVIEW_SOURCE_MISMATCH')
        if ref['output_sha256']!=hashlib.sha256(raster.read_bytes()).hexdigest():
            raise ValueError('NATIVE_PREVIEW_OUTPUT_MISMATCH')
        self.image(raster,x,y,w,h)

    def pending(self,x,y,w,h,text):
        self.rect(x,y,w,h,'#FFF8EE',stroke='#EAD8BD')
        self.text('Pi 待补',x+12,y+9,w-24,9,ORANGE,True)
        self.text(text,x+12,y+28,w-24,9.2,ORANGE)

    def start(self,title,en,total,page_size=None):
        if self.page:self.c.showPage()
        if page_size:
            self.w,self.h=page_size;self.c.setPageSize(page_size)
        self.page+=1
        w=self.w
        self.rect(25,17,2,17,BLUE,radius=0)
        self.text('P01 无电池无线感知微系统 · 工程报告',35,15,w-200,8.8,MUTED,True)
        self.text('同版工程 · Pi 交付报告',w-175,17,150,8,MUTED)
        self.line(25,42,w-25,42,'#9EC9EB',.8)
        self.text(f'{self.page:02d}  {title}',25,57,w-50,23,NAVY,True)
        self.text(en,71,92,w-100,9.3,MUTED)
        self.line(25,self.h-37,w-25,self.h-37,'#9EC9EB',.75)
        target=self.data['system']['id'][:11]
        footer=f'P01 TENG / nRF52832 / BLE     |     最新修订 {target}     |     同版工程报告'
        self.text(footer,25,self.h-29,w-90,7,MUTED)
        self.text(f'{self.page} / {total}',w-63,self.h-29,38,8,NAVY,True)

    def finish(self):
        self.c.save()
        save(self.path.with_suffix('.layout.json'),{'pages':self.page,'size':[self.w,self.h],
                                                   'bounds':self.bounds,'font':'embedded STHeiti'})


def raw_channels(path):
    raw=path.read_bytes(); start=raw.index(b'Binary:'); end=raw.index(b'\n',start)+1
    header=raw[:start].decode('ascii',errors='replace')
    count=int(re.search(r'No\. Variables:\s*(\d+)',header).group(1))
    points=int(re.search(r'No\. Points:\s*(\d+)',header).group(1))
    variables=[m.group(1) for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$',header,re.M)]
    values=array.array('d'); values.frombytes(raw[end:end+count*points*8])
    if sys.byteorder!='little':values.byteswap()
    return {name:[values[i*count+j] for i in range(points)] for j,name in enumerate(variables)}


def chart(doc,x,y,w,h,t,v,title,unit,maximum,color=BLUE):
    doc.text(title,x,y,w,9.5,NAVY,True)
    left=x+35; top=y+28; width=w-48; height=h-53
    for frac in (0,.25,.5,.75,1):
        yy=top+(1-frac)*height
        doc.line(left,yy,left+width,yy,LINE,.45)
        doc.text(f'{maximum*frac:.2g}',x,yy-5,30,7,MUTED)
    for tick in (0,4,8,12,16):
        xx=left+width*tick/t[-1]
        doc.text(str(tick),xx-3,top+height+5,20,7,MUTED)
    doc.text(unit,x,top-15,35,7,MUTED)
    doc.text('时间 / s',left+width-34,top+height+18,45,7,MUTED)
    doc.line(left,top,left,top+height,MUTED,.65)
    doc.line(left,top+height,left+width,top+height,MUTED,.65)
    stride=max(1,len(t)//700)
    indices={0,len(t)-1}
    for i in range(0,len(t),stride):
        end=min(len(t),i+stride)
        chunk=range(i,end)
        indices.add(min(chunk,key=lambda j:v[j])); indices.add(max(chunk,key=lambda j:v[j]))
    path=doc.c.beginPath(); first=True
    for i in sorted(indices):
        xx=left+width*t[i]/t[-1]; yy=doc.h-top-height+height*min(max(v[i]/maximum,0),1)
        if first:path.moveTo(xx,yy);first=False
        else:path.lineTo(xx,yy)
    doc.c.setStrokeColor(HexColor(color));doc.c.setLineWidth(.9);doc.c.drawPath(path)


def conclusion(doc, authors, page, x, y, w, size=9.2):
    entry=next(p for p in authors['lead']['content']['pages'] if p['page']==page)
    y+=doc.text(entry['conclusion'],x,y,w,size,NAVY,True)+6
    return doc.bullets(entry['notes'],x,y,w,size-1,4)


def sequence(doc, content, x, y, w, h, messages=None, source_labels=False):
    actors=content['participants'];messages=messages or content['messages']; positions={a['id']:x+35+(w-70)*i/(len(actors)-1) for i,a in enumerate(actors)}
    for a in actors:
        xx=positions[a['id']];doc.rect(xx-41,y,82,27,'#E3F1FC');doc.text(a['label'],xx-38,y+5,76,7.8,BLUE,True)
        doc.line(xx,y+29,xx,y+h,MUTED,.55,[2,3])
    rh=(h-40)/len(messages)
    for i,msg in enumerate(messages):
        yy=y+43+i*rh;xx=positions[msg['from']];xx2=positions[msg['to']]
        color=RED if msg['kind'] in ('error','disconnect') else BLUE
        if xx==xx2:
            # Keep the return above this row so it does not cross the next message label.
            doc.line(xx,yy-5,xx+19,yy-5,color);doc.line(xx+19,yy-5,xx+19,yy,color);doc.arrow(xx+19,yy,xx,yy,color)
            labelw=min(127,(w-70)/(len(actors)-1)-29)
            labelx=xx+23 if xx<x+w-90 else xx-labelw-23
        else:
            doc.arrow(xx,yy,xx2,yy,color);labelx=min(xx,xx2)+4;labelw=abs(xx2-xx)-7
        label=str(i+1)+'. '+msg['label']
        doc.text(label,labelx,yy-12.5,labelw,7.2 if not source_labels else 8,color,leading=8.8 if not source_labels else 12)
        # Time/event conditions are a separate small left-aligned line.
        if source_labels:
            doc.text(msg['time']+' / '+msg['source']['symbol'],x,yy+5,w,6.4,MUTED)


def overview_blocks(doc, lead, x, y, w):
    modules=lead['system_modules'];step=w/len(modules)
    for i,m in enumerate(modules):
        xx=x+step*i;doc.rect(xx,y,step-11,46,'#E7F2FC');doc.text(m['label'],xx+6,y+7,step-23,8.3,BLUE,True)
        doc.text(m['description'],xx+6,y+23,step-23,6.8,MUTED)
        if i<len(modules)-1:doc.arrow(xx+step-10,y+22,xx+step-1,y+22)


def simple_pdf(path,data,src,authors,graph,ledger):
    d=Document(path,data);f=source_facts(data,src);lead=authors['lead']['content'];power=authors['power']['content'];fw=authors['firmware']['content'];a=ROOT/'assets';p=src/'sources/previews'
    gates=data['system']['validations'];left=478;rx=517;right=300
    d.start('整机方案与交付结论','System Overview & Delivery Conclusion',8)
    yy=d.panel(25,119,left,359,'整机组成','Current candidate / frozen engineering')
    d.image(a/'cad-isometric.png',34,yy+3,left-18,239)
    overview_blocks(d,lead,36,419,left-22)
    d.text(f"当前设计：CS-TENG → SECE / 储能 → {f['parameters']['regulator']['v_out_v']:g} V → nRF52832 / AD7156 → BLE → PC",39,486,left-28,8.6,BLUE)
    d.panel(rx,119,right,112,'产品任务');d.text(lead['task'],rx+13,156,right-26,9)
    d.panel(rx,242,right,152,'当前结论');d.text(lead['summary'],rx+13,279,right-26,9.3)
    d.panel(rx,405,right,132,'交付范围');d.bullets(['可编辑原理图、PCB、CAD、目标固件与PC接收源码。','当前候选对应的仿真、独立检查、双PDF与来源清单。','下一版重点：供能、DRC、板级接口与装配。'],rx+13,443,right-26,9,5)

    d.start('CAD 外形、尺寸与安装接口','CAD Dimensions & Mounting Interface',8)
    d.panel(25,119,left,418,'同版 CAD 视图','Existing native mesh and exported orthographic views')
    for file,box,title in [('cad-top.png',(37,163,219,141),'俯视 / '+dimensions(f['cad_bbox_mm'][:2])+' mm'),('cad-front.png',(270,163,218,141),f"正视 / 外包络高度 {f['cad_bbox_mm'][2]:g} mm"),('cad-side.png',(37,331,219,155),'侧视'),('cad-isometric.png',(270,331,218,155),'等轴视图')]:
        d.image((a if file=='cad-isometric.png' else p)/file,*box);d.text(title,box[0]+3,box[1]+box[3]+3,box[2]-6,8,MUTED)
    layers=f['assembly_sizes'];mech=f['parameters']['mechanical']
    d.panel(rx,119,right,231,'尺寸与接口');d.table([['项目','本版尺寸'],['整机外包络 / mm',dimensions(f['cad_bbox_mm'])],['PCB / mm',dimensions(f['board_mm'])],['PCB 厚度 / mm',str(f['board_thickness_mm'])],['采能层',dimensions(layers['acrylic_backing_neg'][:2])+' mm 背板；'+dimensions(layers['ptfe_neg'][:2])+' mm 活性层'],['安装核对',STATUS.get(gates['geometry_fit']['status'],gates['geometry_fit']['status'])+'；详见装配检查']],rx+12,159,[125,151],8.5)
    d.panel(rx,363,right,174,'本页结论');conclusion(d,authors,2,rx+13,401,right-26,8.8)

    d.start('机械结构、装配与工作原理','Mechanical Structure, Assembly & Working Principle',8)
    d.panel(25,119,left,261,'分层爆炸图','Exact declared layer dimensions / presentation separation')
    d.image(a/'cad-exploded.png',36,163,left-22,203)
    d.panel(25,390,left,147,'关键装配参数');d.table([['组成','本版参数与作用'],['背板 / 电极',f"{layers['acrylic_backing_neg'][2]:g} mm 背板；铜/PTFE/PI："+'/'.join(f'{layers[k][2]*1000:g}' for k in ('copper_neg','ptfe_neg','pi_pos'))+' μm'],['运动间隙',f"{mech['d_max_m']*1000:g} mm 名义接触—分离行程"],['装配对象',f"{f['cad_parts']} 件；完整清单见技术详报与 assembly.json"]],37,427,[130,324],8.4)
    d.panel(rx,119,right,230,'装配说明');d.bullets(lead['assembly_notes'],rx+13,156,right-26,8.8,6)
    d.panel(rx,361,right,176,'本页结论');conclusion(d,authors,3,rx+13,399,right-26,8.5)

    d.start('电气架构与 PCB 实现','Electrical Architecture & PCB Implementation',8)
    overview_blocks(d,lead,25,121,792)
    d.panel(25,180,left,357,'同版 PCB 与功能定位','Native board layers; markers refer to actual components')
    d.image(a/'pcb-top-annotated.png',40,224,211,276);d.image(a/'pcb-bottom-annotated.png',265,224,211,276)
    d.text('正面',120,507,70,8,MUTED);d.text('背面',347,507,70,8,MUTED)
    d.panel(rx,180,right,232,'关键功能区');d.table([['定位','器件与接口']]+[[str(i+1)+' '+v['name'].split('（')[0],', '.join(v['refs'])] for i,v in enumerate(power['pcb_regions'])],rx+12,219,[120,156],7.7)
    d.panel(rx,423,right,114,'PCB 检查');d.text(f"{graph['components']} 个器件 / {graph['pin_count']} 引脚；板框 {dimensions(f['board_mm'])} mm。DRC：{drc_summary(f)}。",rx+13,460,right-26,9,RED)
    d.text('来源：冻结 PCB 导出、器件坐标与当前独立检查。',rx+13,507,right-26,7.4,MUTED)

    d.start('电路原理图与关键回路','Connected Circuit Schematic & Key Subcircuits',8)
    groups=graph['groups'];main=[g for g in groups if 'U1' not in g['refs']][:2]
    if len(main)<2:main=groups[:2]
    for i,g in enumerate(main):
        d.panel(25,119+i*204,542,194,g['title']);d.image(a/(g['id']+'.png'),35,151+i*204,522,153)
    d.panel(581,119,236,418,'回路与接口说明')
    yy=158
    for group in power['circuit_groups']:
        yy+=d.text(group['title'],594,yy,210,9,BLUE,True)+3
        yy+=d.text(', '.join(group['refs']),594,yy,210,7.4,MUTED)+3
        yy=d.bullets([brief(group['notes'][0],61)],594,yy,210,8,5)+5
    d.text('完整连接图见技术详报附图；每个器件及全部引脚均取自本版原生工程。',37,531,520,7.5,MUTED)

    d.start('固件交互与任务时序','Firmware Interaction & Task Sequence',8)
    step=792/len(fw['constraints'][:5])
    for i,v in enumerate(fw['constraints'][:5]):
        xx=25+i*step;d.rect(xx,119,step-8,66)
        d.text(v['label'],xx+9,127,step-26,9,BLUE,True)
        d.text(v['value'],xx+9,146,step-26,7.7)
    d.panel(25,196,792,341,'参与者交互时序 · 正常路径与错误恢复')
    sequence(d,fw,43,235,756,273)
    d.text('从上到下表示事件先后。红线为异常、断线与恢复分支；各消息触发条件与源码位置见详报。',42,519,758,7.4,MUTED)

    d.start('供能、功耗与储能仿真','Energy Harvesting, Load & Storage',8)
    params=f['parameters'];d.panel(25,119,left,78,'计算条件')
    d.text(f"{mech['d_max_m']*1000:g} mm / {mech['f_mech_hz']:g} Hz；储能 {params['storage']['c_store_f']*1e6:g} μF，初始 {params['storage']['initial_v']:g} V；人工接通 t={params['timeline']['manual_switch_close_s']:g} s；{params['regulator']['v_out_v']:g} V 输出；窗口 {ledger['span_s'][1]:g} s。",38,158,left-26,8.8)
    channels=raw_channels(next((src/'sources/jobs').glob('*/project-trace.raw')))
    chart(d,36,211,456,142,channels['time'],channels['v(storage_rail)'],'储能电压 / 全部原始采样','V',4.5)
    chart(d,36,365,456,143,channels['time'],channels['v(supply_1v8)'],'稳压输出观察量','V',2.0)
    d.panel(rx,119,right,243,'关键结果');d.table([['项目','当前结果'],['储能电压',f"{channels['v(storage_rail)'][0]:.6g} → {channels['v(storage_rail)'][-1]:.6g} V"],['最低供电电压',f"{ledger['minimum_supply_V']:.6g} V"],['接通节点异常',f"最低 {ledger['minimum_mcu_V']:.6g} V"],['储能变化',f"{ledger['storage_delta_J']*1e3:.6g} mJ"],['负载电荷',f"{ledger['actual_load_charge_C']*1e6:.5g} μC"],['供能检查',STATUS.get(gates['power_load_chain']['status'],gates['power_load_chain']['status'])]],rx+12,157,[130,146],8.4)
    d.panel(rx,374,right,163,'本页结论');conclusion(d,authors,7,rx+13,412,right-26,8.4)

    d.start('需求验收与交付目录','Requirements Review & Delivery Contents',8)
    d.panel(25,119,left,306,'需求与实现对照');d.table([['工程要求','当前状态','证据']]+[[LABELS[k],STATUS.get(v['status'],v['status']),v.get('validation_id','已有证据')[:12]] for k,v in gates.items()],37,158,[176,100,178],8.1)
    d.panel(25,437,left,100,'交付内容');d.text('双 PDF / 同版原理图、PCB、STEP与装配参数 / 目标固件与 PC 接收源码 / SPICE、RAW与积分数据 / 图表及来源清单 / Pi 作者记录。',38,475,left-26,9)
    d.panel(rx,119,right,180,'交付结论');conclusion(d,authors,8,rx+13,157,right-26,8.7)
    d.panel(rx,312,right,225,'工程接续');d.bullets(lead['handoff'],rx+13,351,right-26,8.6,6)
    d.finish()


def detailed_pdf(path,data,src,authors,graph,ledger):
    from reportlab.lib.pagesizes import A1, A3
    d=Document(path,data,'detail');a=ROOT/'assets';lead=authors['lead']['content'];fw=authors['firmware']['content'];power=authors['power']['content'];gates=data['system']['validations']
    f=source_facts(data,src);layers=f['assembly_sizes'];mech=f['parameters']['mechanical']
    # Long professional notes are paginated as text, never squeezed into cards.
    notes=[]
    for g in power['circuit_groups']:
        notes += [(g['title'], t) for t in g['notes']]
    notes += [('供能解释', t) for t in power['energy_interpretation']]
    notes += [('电路结论', t) for t in power['conclusions']]
    note_pages=[];page=[];used=0
    for heading,text in notes:
        style=ParagraphStyle('measure',fontName='BF-Regular',fontSize=9.2,leading=14,wordWrap='CJK')
        height=Paragraph(escape(text),style).wrap(515,9999)[1]+39
        if used+height>650 and page: note_pages.append(page);page=[];used=0
        page.append((heading,text));used+=height
    if page:note_pages.append(page)
    files=list(data['system']['files'].items());file_pages=[];page=[];used=25
    for path,ref in files:
        style=ParagraphStyle('filemeasure',fontName='BF-Regular',fontSize=7.4,leading=7.4*1.48,wordWrap='CJK')
        height=max(Paragraph(escape(path),style).wrap(372,999)[1],11)+12
        if used+height>658 and page:file_pages.append(page);page=[];used=25
        page.append((path,ref));used+=height
    if page:file_pages.append(page)
    total=11+len(file_pages)+len(note_pages)+len(graph['groups'])+max(1,(len(fw['messages'])+7)//8)
    d.start('结论与工程身份','Conclusion, Scope & Design Identity',total)
    yy=d.panel(25,126,545,208,'本版结论');yy+=d.text(lead['summary'],39,yy,517,11)+13
    d.text(lead['task'],39,yy,517,10)
    d.image(a/'cad-isometric.png',35,353,525,275)
    d.table([['身份','内容'],['候选',data['system']['id']],['已采用版',data['adopted_system']],['原始设计 owner',data['system']['origin_owner']],['来源','当前候选冻结文件、选定原生作业与独立检查']],25,651,[105,440],7.6)

    for page,title,en in [(2,'CAD 尺寸、视图与安装接口','Geometry & Interfaces'),(3,'装配组成与工作原理','Assembly & Working Principle')]:
        d.start(title,en,total)
        d.image(a/('cad-isometric.png' if page==2 else 'cad-exploded.png'),30,126,535,338)
        yy=d.table([['项目','当前值'],['整机外包络',dimensions(f['cad_bbox_mm'])+' mm'],['PCB',dimensions(f['board_mm']+[f['board_thickness_mm']])+' mm'],['背板',dimensions(layers['acrylic_backing_neg'])+' mm'],['活性层',dimensions(layers['ptfe_neg'][:2])+' mm；铜/PTFE/PI：'+'/'.join(f'{layers[k][2]*1000:g}' for k in ('copper_neg','ptfe_neg','pi_pos'))+' μm'],['名义运动',f"{mech['d_max_m']*1000:g} mm，{mech['f_mech_hz']:g} Hz"],['装配检查',STATUS.get(gates['geometry_fit']['status'],gates['geometry_fit']['status'])+'；见本版 geometry_fit 检查']],25,482,[160,385],9)
        conclusion(d,authors,page,34,yy+18,527,9.6)

    d.start('电气架构与 PCB','Electrical Architecture & Board',total)
    d.image(a/'pcb-top-annotated.png',38,129,245,285);d.image(a/'pcb-bottom-annotated.png',310,129,245,285)
    yy=d.table([['功能定位','器件','说明']]+[[str(i+1)+' '+brief(v['name'].split('（')[0],22),', '.join(v['refs']),brief(v['description'],56)] for i,v in enumerate(power['pcb_regions'])],25,436,[130,135,280],8)
    d.text('DRC：'+drc_summary(f)+'。原生板图与完整回执随交付包提供。',32,yy+16,530,9,RED)

    d.start('电路连接与完整性','Native Circuit Connectivity',total)
    yy=d.text('同版网表重排：保留原生符号、器件身份、引脚与 NC；组内导线直接连接，跨功能组使用命名接口。',28,130,537,11)
    yy=d.table([['回路','器件','说明']]+[[g['title'],', '.join(g['refs']),brief(g['notes'][0],82)] for g in power['circuit_groups']],25,170+yy,[125,170,250],8.4)
    yy=d.table([['完整性检查','结果'],['器件',str(graph['components'])],['引脚',str(graph['pin_count'])],['原生网表与绘图网表','逐引脚一致'],['图中导线','每个局部网络均连接真实端点'],['完整连接图','见后部 A1 总图及 A3 回路附图'],['网表身份',graph['netlist_sha256']]],25,yy+23,[155,390],8.5)
    d.text('完整逐组说明与 Pi 工程解释见后部“专业设计说明”；原始作者 JSON 随包交付。',32,yy+18,530,9.1,MUTED)

    d.start('固件配置与运行条件','Firmware Configuration & Conditions',total)
    yy=d.table([['配置','当前值','源码位置']]+[[v['label'],v['value'],v['source']['path']+' / '+v['source']['symbol']] for v in fw.get('constraints',[])],25,132,[125,205,215],8.5)
    d.bullets(fw['explanations'],32,yy+25,530,10,10)
    for n in range(0,len(fw['messages']),8):
        d.start('固件交互时序 '+str(n//8+1),'Source-bound Interaction Sequence',total)
        messages=fw['messages'][n:n+8];sequence(d,fw,30,139,535,514,messages,source_labels=True)
        d.text('时序按事件先后绘制。每条消息的触发条件、源码函数和哈希记录在 sequence.json。',31,690,533,9,MUTED)

    d.start('供能模型与积分口径','Power Model & Energy Ledger',total)
    rows=[['观测量','结果 / 单位']]
    for label,key,scale,unit in [('初始储能','initial_storage_J',1000,'mJ'),('最终储能','final_storage_J',1000,'mJ'),('储能变化','storage_delta_J',1000,'mJ'),('源端输出积分','source_delivered_J',1000,'mJ'),('SECE 到储能积分','sece_received_J',1000,'mJ'),('储能泄漏积分','leakage_J',1000,'mJ'),('负载端有符号积分','load_port_absorbed_J',1000,'mJ'),('负载电荷','actual_load_charge_C',1e6,'μC')]:rows.append([label,f"{ledger[key]*scale:.8g} {unit}"])
    yy=d.table(rows,25,134,[245,300],10)
    yy=d.text('积分使用全部原始 RAW 采样；Iload 由实际求解网表 PWL 插值。电压、电流、时间采用 SI 单位。SECE 为声明的平均包络。',31,yy+24,533,10)+yy+24
    d.text(f"人工接通节点最低 {ledger['minimum_mcu_V']:.8g} V，共 {ledger['negative_mcu_samples']} 个负电压样本。负载端有符号能量用于排查模型；本版效率留空，待接通/负载模型修复。",31,yy+17,533,10,RED)

    d.start('供能波形与设计问题','Native Waveforms & Findings',total)
    ch=raw_channels(next((src/'sources/jobs').glob('*/project-trace.raw')))
    chart(d,30,132,535,187,ch['time'],ch['v(storage_rail)'],'储能电压','V',4.5)
    chart(d,30,338,535,177,ch['time'],ch['v(supply_1v8)'],'供电范围观察量','V',2)
    d.bullets([f"储能电压由 {ch['v(storage_rail)'][0]:.6g} V 变为 {ch['v(storage_rail)'][-1]:.6g} V；稳压输出最低 {ledger['minimum_supply_V']:.6g} V。",
               f"实际 PWL 共 {ledger['actual_pwl_points']} 点；电荷积分 {ledger['actual_load_charge_C']*1e6:.6g} μC。",
               (f"接通节点有 {ledger['negative_mcu_samples']} 个负电压样本；保留全部采样和有符号积分，效率暂缺。" if ledger['negative_mcu_samples'] else '接通节点无负电压样本；各端口积分见本版能量账。'),
               '平均 SECE 包络、器件规格与实装驱动链的适用性列入后续工程核对。'],31,552,533,9.5,10)

    d.start('独立验收与后续工程','Independent Validation & Engineering Work',total)
    yy=d.table([['工程门','状态','验证范围']]+[[LABELS[k],STATUS.get(v['status'],v['status']),brief(v.get('scope') or v.get('findings',{}).get('scope','当前输入与原生回读'),120)] for k,v in gates.items()],25,132,[150,90,305],8.5)
    physical=data['system']['physical']
    physical=physical.get('status') if isinstance(physical,dict) else physical
    physical={'NOT_TESTED':'未进行','PASS':'已通过','FAIL':'未通过'}.get(physical,'见本版物理验证记录')
    remaining='；'.join(LABELS[k]+'：'+STATUS.get(v['status'],v['status']) for k,v in gates.items() if v['status']!='PASS')
    yy=d.text('物理验证：'+str(physical)+'。当前待处理：'+(remaining or '本版全部工程门已通过')+'。',31,yy+24,533,10)+yy+24
    d.bullets(lead['handoff'],31,yy+18,533,9.5,8)

    d.start('报告作者、来源与交付检查','Authors, Provenance & Required Delivery Checks',total)
    yy=d.table([['作者','原 Pi owner','内容身份']]+[[k,v['owner'],v['sha256']] for k,v in authors.items()],25,133,[80,180,285],8)
    checks=['图中全部器件、引脚、网络和 NC 与冻结 readback 一致。','固件时序包含启动、采样、通知、失败与断线恢复，每条绑定当前源码位置。','CAD视图、PCB标注与当前几何/原生坐标对应。','波形与能量积分使用当前选定 RAW；异常采样完整保留。','简版8页与技术详报均绑定本 System Commit。','发布交付包前，服务重新校验报告、作者、候选和输出哈希。']
    d.bullets(checks,31,yy+25,533,10,10)
    d.text('报告文件、图表 JSON、源码定位、来源索引与原生工程均随交付包提供。',31,700,533,10,BLUE)

    # All actual source files are listed, in addition to individual page references.
    for n,rows in enumerate(file_pages):
        d.start('同版文件索引 '+str(n+1),'Complete Candidate File Index',total)
        d.table([['文件路径','SHA-256 前16位']]+[[p,v['sha256'][:16]] for p,v in rows],25,129,[385,160],7.4)
    for n,rows in enumerate(note_pages):
        d.start('专业设计说明 '+str(n+1),'Pi-authored Circuit & Energy Notes',total)
        yy=130
        for heading,text in rows:
            yy+=d.text(heading,31,yy,533,10,BLUE,True)+5
            yy+=d.text(text,39,yy,515,9.2,leading=14)+18
    d.start('完整电路连接总图','Full Connected Schematic / Actual Cross-module Nets',total,page_size=A1)
    d.image(a/'schematic-connected.png',25,125,d.w-50,d.h-205)
    d.text('所有跨功能组网络均用实际导线接入同名母线；黑点表示相连，无点交叉不连接。',35,d.h-65,d.w-70,12,MUTED)
    for i,g in enumerate(graph['groups']):
        d.start('电路附图 '+str(i+1)+' · '+g['title'],'Native Symbols / Connected Frozen Netlist',total,page_size=landscape(A3))
        d.image(a/(g['id']+'.png'),30,127,d.w-60,d.h-247)
        d.text('器件：'+', '.join(g['refs']),35,d.h-108,d.w-70,11,BLUE)
        group=next(x for x in power['circuit_groups'] if x['id']==g['id'])
        d.text(brief('；'.join(group['notes']),180),35,d.h-85,d.w-70,10)
        d.text('跨组同名端口相连；黑点为接点，无点交叉不连接；红叉为 NC，红圈为空网络。逐引脚清单见附件。',35,d.h-61,d.w-70,9,MUTED)
    d.finish()


def channels_min(channels, key):
    return min(channels[key])


def quality(output,data,authors,graph,ledger,src):
    from pypdf import PdfReader
    from .report_assets import verify_input, source_ref, native_svg_xy
    from .repository import file_hash
    checks=[]
    def add(k,ok):checks.append({'id':k,'status':'PASS' if ok else 'FAIL'})
    add('all_native_parts_and_pins_drawn',graph['components']==len({p['ref'] for p in graph['pins']}) and graph['pin_count']==len(graph['pins']))
    add('exact_netlist_equality',graph['netlist_sha256']==graph['drawing_netlist_sha256'])
    add('connected_full_schematic',bool(graph.get('cross_module_wires')) and (output/'assets/schematic-connected.svg').is_file())
    add('all_required_diagrams',all((output/'assets'/(g['id']+'.svg')).is_file() and (output/'assets'/(g['id']+'.png')).is_file() for g in graph['groups']))
    source_index=json.loads((output/'assets/source-index.json').read_text())
    raw_ref=next(a for a in source_index['assets'] if a['path']=='project-trace.raw')
    add('exact_raw_energy_source',ledger['raw_sha256']==raw_ref['sha256'])
    add('all_current_engineering_gates',{r['gate'] for r in authors['lead']['content']['requirements']}==set(data['system']['validations']))
    fw=authors['firmware']['content']
    add('sequence_error_and_recovery',{'start','sample','notify','error','disconnect'}<={m['kind'] for m in fw['messages']})
    add('current_source_sequence',len(authors['firmware']['content']['messages'])>=12)
    add('three_original_pi_authors',all(v['source_author']=='Pi' for v in authors.values()))
    add('eight_filled_sections',len(authors['lead']['content']['pages'])==8)
    from xml.etree import ElementTree as E
    annotations=json.loads((output/'assets/pcb-annotations.json').read_text())
    native=json.loads(next((src/'sources/candidate').glob('*/pcb-readback.json')).read_text())
    parts={v['designator']:v for v in native.get('result',native)['components'] if v.get('designator')}
    marker_ok=True
    for side in ('top','bottom'):
        original=src/'sources/previews'/('pcb-'+side+'.svg');root=E.parse(original).getroot()
        annotated=E.parse(output/'assets'/('pcb-'+side+'-annotated.svg')).getroot()
        overlay=next(v for v in annotated if v.get('id')=='bf-report-pcb-markers')
        circles=[v for v in overlay if v.tag.endswith('}circle')]
        marker_ok &= annotations['source_previews'][side]==file_hash(original) and len(circles)==len(annotations['regions'])
        for region,circle in zip(annotations['regions'],circles):
            part=parts[region['marker_ref']]
            expected=native_svg_xy(root,'l-'+side+'-copper',part['x']*.0254,part['y']*.0254)
            actual=[float(circle.get('cx')),float(circle.get('cy'))]
            marker_ok &= all(abs(a-b)<1e-8 for a,b in zip(expected,actual)) and actual==region['svg_xy'][side]
    add('pcb_annotation_coordinate_binding',marker_ok)
    measured=json.loads((output/'assets/report-measurements.json').read_text())
    for mode,file in [('simple','P01_简版工程报告.pdf'),('detail','P01_详细技术报告.pdf')]:
        reader=PdfReader(output/file);text='\n'.join(p.extract_text() for p in reader.pages)
        add(mode+'_body_text',len(text)>(1800 if mode=='simple' else 7000))
        add(mode+'_page_count',len(reader.pages)==8 if mode=='simple' else len(reader.pages)>=16)
        add(mode+'_no_template_placeholders',not any(x in text for x in ('Pi 待补','模板样稿','XXX','TODO','占位图')))
        add(mode+'_candidate_binding',data['system']['id'][:11] in text)
        compact=lambda value:re.sub(r'\s+','',value)
        expected=[drc_summary(measured),dimensions(measured['cad_bbox_mm']),f"{ledger['minimum_supply_V']:.6g} V"]
        add(mode+'_current_measurements',all(compact(v) in compact(text) for v in expected))
        layout=json.loads((output/file).with_suffix('.layout.json').read_text());w,h=layout['size']
        # Per-page sizes may differ for A3 circuit sheets. The text engine stores
        # an explicit rectangle for each object, checked against its page size.
        add(mode+'_page_bounds',all(x['x']>=20 and x['y']>=0 and x['x']+x['w']<=x.get('page_width',w)+.1 and x['y']+x['h']<=x.get('page_height',h)-15 for x in layout['bounds']))
    outputs={str(p.relative_to(output)):{'sha256':file_hash(p),'bytes':p.stat().st_size} for p in sorted(output.rglob('*')) if p.is_file() and p.name!='quality.json'}
    result={'schema_version':'bf-report-quality-v1','report_id':data['report_id'],'system_commit':data['system']['id'],
            'authors':{k:v['sha256'] for k,v in authors.items()},'checks':checks,
            'status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL','outputs':outputs}
    save(output/'quality.json',result);return result


def main():
    global ROOT
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--authors',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    src=Path(args.input);ROOT=Path(args.output);ROOT.mkdir(parents=True,exist_ok=True)
    from .report_assets import verify_input, connected_circuits, rasterize, cad_views, pcb_annotations, energy_ledger, check_author
    data=verify_input(src);authors={p.stem:json.loads(p.read_text()) for p in Path(args.authors).glob('*.json')}
    for scope,record in authors.items(): check_author(record['content'],scope,data,src)
    pdfmetrics.registerFont(TTFont('BF-Regular','/System/Library/Fonts/STHeiti Light.ttc',subfontIndex=0));pdfmetrics.registerFont(TTFont('BF-Bold','/System/Library/Fonts/STHeiti Medium.ttc',subfontIndex=0))
    assets=ROOT/'assets';assets.mkdir(exist_ok=True)
    graph=connected_circuits(src,authors['power']['content'],assets)
    pcb_annotations(src,authors['power']['content'],assets)
    # Geometry plotting uses the existing CAD environment; PDF libraries stay in
    # the document runtime. Both executable identities travel with the output.
    import importlib.util, os
    cad_python=Path(os.environ.get('BF_REPORT_CAD_PYTHON',str(Path.home()/'.local/share/bf-agent-runtime/product-cad/bin/python')))
    if importlib.util.find_spec('matplotlib'):
        cad_views(src,assets);cad_runtime=sys.executable
    else:
        if not cad_python.is_file():raise ValueError('REPORT_CAD_PLOT_RUNTIME_REQUIRED')
        code='from pathlib import Path;from bfworld.agentlab.design_lab.report_assets import cad_views;import sys;cad_views(Path(sys.argv[1]),Path(sys.argv[2]))'
        subprocess.run([str(cad_python),'-c',code,str(src),str(assets)],check=True,capture_output=True,text=True)
        cad_runtime=str(cad_python)
    save(ROOT/'runtime.json',{'pdf_python':sys.executable,'cad_plot_python':cad_runtime,'pdf_engine':'ReportLab','native_svg_engine':'Chromium'})
    rasterize(assets,assets)
    raw=raw_channels(next((src/'sources/jobs').glob('*/project-trace.raw')));ledger=energy_ledger(src,raw);save(assets/'energy-ledger.json',ledger)
    save(assets/'report-measurements.json',source_facts(data,src))
    fw=authors['firmware']['content'];sequence_record={**fw,'source_hashes':{m['source']['path']:hashlib.sha256((src/'sources/candidate'/m['source']['path']).read_bytes()).hexdigest() for m in fw['messages']}}
    save(assets/'sequence.json',sequence_record)
    for scope,record in authors.items():save(ROOT/'authors'/(scope+'.json'),record)
    save(ROOT/'report-input.json',data)
    from ..runtime_config import PI
    import shutil
    resource=PI/'packages/bf-harness/resources/skills/bf-engineering-report'
    shutil.copytree(resource,ROOT/'template-skill',dirs_exist_ok=True)
    save(assets/'source-index.json',{'report_id':data['report_id'],'system_commit':data['system']['id'],'assets':data['assets']})
    simple_pdf(ROOT/'P01_简版工程报告.pdf',data,src,authors,graph,ledger)
    detailed_pdf(ROOT/'P01_详细技术报告.pdf',data,src,authors,graph,ledger)
    result=quality(ROOT,data,authors,graph,ledger,src);print(json.dumps({'status':result['status'],'checks':result['checks']},ensure_ascii=False))
    if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
