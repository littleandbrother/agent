#!/usr/bin/env python3
"""Source-bound P01 template proof. No model/solver/native engineering calls."""
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
        self.c.setTitle('P01 工程报告 - '+('八页简版样稿' if mode=='simple' else '详版模板与数据样稿'))
        self.c.setAuthor('BF Agent / engineering report template proof')
        self.bounds=[]; self.page=0

    def text(self, text, x, y, width, size=9.5, color=NAVY, bold=False, leading=None):
        style=ParagraphStyle('p',fontName='BF-Bold' if bold else 'BF-Regular',fontSize=size,
                             leading=leading or size*1.5,textColor=HexColor(color),wordWrap='CJK')
        p=Paragraph(escape(str(text)).replace('\n','<br/>'),style)
        _,height=p.wrap(width, self.h)
        p.drawOn(self.c,x,self.h-y-height)
        self.bounds.append({'page':self.page,'x':x,'y':y,'w':width,'h':height,'text':str(text)[:70]})
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
        raster=ROOT/'output/native-previews'/path.with_suffix('.png').name
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

    def start(self,title,en,total):
        if self.page:self.c.showPage()
        self.page+=1
        w=self.w
        self.rect(25,17,2,17,BLUE,radius=0)
        self.text('P01 无电池无线感知微系统 · 工程报告',35,15,w-200,8.8,MUTED,True)
        self.text('模板样稿 · 实际数据填充',w-175,17,150,8,MUTED)
        self.line(25,42,w-25,42,'#9EC9EB',.8)
        self.text(f'{self.page:02d}  {title}',25,57,w-50,23,NAVY,True)
        self.text(en,71,92,w-100,9.3,MUTED)
        self.line(25,self.h-37,w-25,self.h-37,'#9EC9EB',.75)
        target=self.data['system']['id'][:11]
        footer=f'P01 TENG / nRF52832 / BLE     |     最新修订 {target}     |     2026-10-16'
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


def field_inventory(data,candidate):
    event=json.loads((candidate/'public-interface-facts-20261014/firmware-events.json').read_text())
    historical=event.get('source_sha256',{})
    stale=[]
    for path,digest in historical.items():
        rel=next((key for key in data['system']['files'] if path.endswith('/'+key)),None)
        if rel and data['system']['files'][rel]['sha256']!=digest:stale.append(rel)
    gaps=[
      {'id':'R01','pages':[1], 'kind':'出图','owner':'BF Lead','task':'制作同版整机组成图，关联 TENG、采能电路、感知节点与接收端','source':'assembly.json + native schematic/PCB + receiver/','acceptance':'图中模块均能对应当前工程对象'},
      {'id':'R02','pages':[2], 'kind':'出图','owner':'BF Lead / CAD 工具','task':'导出同版等轴视图，补完整尺寸与安装标注','source':'selected CAD STEP + CAD readback','acceptance':'标注数值与原生几何读回一致'},
      {'id':'R03','pages':[3], 'kind':'出图','owner':'BF Lead / CAD 工具','task':'导出带零件编号的爆炸图与装配步骤','source':'assembly.json + selected CAD STEP','acceptance':'编号与零件清单一致，标明运动件和固定件'},
      {'id':'R04','pages':[4], 'kind':'标注','owner':'Power Pi','task':'对 PCB 功能区与关键接口进行标注','source':'current PCB top/bottom + native parts/nets','acceptance':'每个区域、接口指向真实器件和网络'},
      {'id':'R05','pages':[5], 'kind':'出图','owner':'Power Pi','task':'导出采能/SECE、储能稳压、CDC/MCU 三组关键回路局部图','source':'current native schematic','acceptance':'图中器件编号、数值和网络与原生工程一致'},
      {'id':'R06','pages':[6], 'kind':'分析图','owner':'Firmware Pi','task':'审定当前固件状态图，补异常、重试与重连路径','source':'project-fw-s132/main.c + app_policy.c/.h','acceptance':'每个状态/转换有当前源码函数依据'},
      {'id':'R07','pages':[6,7], 'kind':'事件数据','owner':'Firmware Pi','task':'补当前源码绑定的事件记录；旧记录源码已有变化','source':'current firmware source + selected build','acceptance':'事件记录包含当前输入哈希；记录实际测试条件','stale_sources':stale},
      {'id':'R08','pages':[7], 'kind':'分析','owner':'Power Pi','task':'完成现有 RAW 的源、储能、负载、损耗能量核算','source':'current RAW + chain_joint.cir + interface-params.json','acceptance':'给出积分口径、单位及异常接通样本的处理'},
      {'id':'R09','pages':[1,8], 'kind':'结论','owner':'BF Lead','task':'依据当前八项检查完成逐页结论和下一版目标','source':'current_qualification + selected engineering results','acceptance':'逐项对应同一候选的检查与交付文件'},
      {'id':'E01','pages':[2,3], 'kind':'工程数据','owner':'BF Lead / 机械任务','task':'补 PCB 放置变换、安装孔对应及器件高度','source':'geometry_fit pending fields','acceptance':'装配检查能消费这些尺寸和变换'},
      {'id':'E02','pages':[5,7], 'kind':'工程数据','owner':'Power Pi','task':'解决器件/绕组身份、采能源与 SECE 参数适用性','source':'source_domain + schematic_bom_pins','acceptance':'参数具备来源、条件及可用范围'},
    ]
    pages=[
      ('整机方案与交付结论','当前任务、八项检查、CAD与电气对象','R01、R09'),
      ('CAD 外形、尺寸与安装接口','三张尺寸图；168 × 187.5 × 20 mm 外包络；40 × 70 mm PCB','R02、E01'),
      ('机械结构、装配与工作原理','assembly.json、38 件 CAD、STEP','R03、E01'),
      ('电气架构与 PCB','原生 PCB 正反面、39 器件/172 引脚、52 间距/50 连接问题','R04'),
      ('电路原理图与关键回路','原生矢量原理图、BOM/引脚/网络','R05、E02'),
      ('固件状态与任务时序','当前源码、目标构建、时序参数、声明负载窗口','R06、R07'),
      ('供能、功耗与储能仿真','165130 点 RAW、16.001 s 结果、当前独立检查','R07、R08、E02'),
      ('需求验收与交付目录','八项当前门、89 文件清单、同版审查包','R09'),
    ]
    return {'schema_version':'bf-report-asset-inventory-v1','system_commit':data['system']['id'],
            'pages':[{'page':i+1,'title':t,'ready':ready,'missing':missing} for i,(t,ready,missing) in enumerate(pages)],
            'tasks':gaps,'historical_event_record_stale_inputs':stale}


def timeline(doc,timeline,x,y,w,h):
    left=x+67; width=w-84; top=y+22
    windows=timeline['windows_ms']
    conn=windows['connection_event']; end_ms=timeline['timeline']['t_stop_s']*1000
    rows=[('广播',windows['advertising']['windows'],BLUE),
          ('连接',[[conn['first_ms']+conn['period_ms']*k,conn['first_ms']+conn['period_ms']*k+conn['pulse_ms']]
                     for k in range(conn['count'])], '#5476BA'),
          ('CDC',windows['cdc_convert']['windows'],GREEN),('Notify',windows['notify']['windows'],'#9B62B9')]
    for index,(label,events,color) in enumerate(rows):
        yy=top+index*28
        doc.text(label,x+6,yy-1,58,8.7,MUTED)
        doc.rect(left,yy,width,13,'#E9F0F7',radius=0)
        for start,end in events:
            doc.rect(left+width*start/end_ms,yy,max(.65,width*(end-start)/end_ms),13,color,radius=0)
    for t in (0,4,8,12,16):
        doc.text(str(t),left+width*t/(end_ms/1000)-2,top+114,25,7.5,MUTED)
    doc.text('时间 / s',left+width-40,top+132,50,7.5,MUTED)


def simple_pdf(path,data,src,inventory,templates):
    d=Document(path,data); c=src/'sources/candidate'; p=src/'sources/previews'
    params=json.loads((c/'project-chain/interface-params.json').read_text())
    tl=json.loads((c/'project-chain/load-timeline.json').read_text())
    gates=data['system']['validations']; power=gates['power_load_chain']['findings']
    f=source_facts(data,src)
    cadjob=next(j for j,v in data['system']['jobs'].items() if 'project-cad_summary.json' in v['artifacts'])
    cad=json.loads((src/'sources/jobs'/cadjob/'project-cad_summary.json').read_text())
    parts=json.loads((c/'assembly.json').read_text())['parts']
    x=25; left=478; rx=517; right=d.w-rx-25

    for index,page in enumerate(templates['simple_pages']):
        d.start(page['title'],page['english'],8)
        if index==0:
            d.panel(x,119,left,280,'整机组成','System composition')
            d.image(p/'cad-top.png',x+8,164,285,218)
            d.text('接触分离 TENG',x+308,170,150,13,BLUE,True)
            d.bullets(['机械输入：往复接触 / 分离','采能与储能：SECE 包络、220 µF','感知：AD7156 电容采集','节点：nRF52832 + S132 / BLE','接收：PC 解码与显示'],x+300,202,160,9.5,5)
            d.panel(x,411,left,130,'能量与信息路径','Energy and information flow')
            labels=['机械输入','TENG / SECE','储能 / 供电','感知 / BLE','PC 接收']
            for n,label in enumerate(labels):
                xx=x+12+n*93
                d.rect(xx,465,83,35,'#FFFFFF',LINE)
                d.text(label,xx+5,475,74,8.7,BLUE,True)
                if n<4:d.arrow(xx+83,483,xx+91,483)
            d.text('人工接通 MCU，人工建立 BLE 连接。',x+15,514,left-30,9,MUTED)
            yy=d.panel(rx,119,right,104,'产品任务','Product task')
            d.text('在声明机械输入和初态下完成供能、人工接通、周期电容采样、BLE 传输与 PC 解码。',rx+14,yy,right-28,10)
            yy=d.panel(rx,235,right,155,'当前结论','Current conclusion')
            d.bullets(['已通过：固件事件逻辑、同版交付。','需修复：供能与任务负载、PCB DRC。','待核实：采能源、器件引脚、板级接口、机械装配。'],rx+13,yy,right-26,10,8)
            yy=d.panel(rx,402,right,139,'交付内容','Delivery scope')
            d.bullets([f'当前候选包含 {f["candidate_files"]} 份工程与报告文件。','已有 CAD / STEP、原理图、PCB、目标固件和原生仿真输出。','物理验证：未进行。'],rx+13,yy,right-26,9.8,7)
        elif index==1:
            d.panel(x,119,left,422,'现有 CAD 尺寸视图','Native CAD dimensions')
            d.image(p/'cad-top.png',x+8,167,250,180)
            d.image(p/'cad-front.png',x+264,167,201,180)
            d.image(p/'cad-side.png',x+8,358,250,168)
            d.pending(x+272,367,190,140,'等轴视图、安装孔位置与接口标注。')
            yy=d.panel(rx,119,right,238,'主要尺寸','Dimensions from CAD / native review')
            d.table([['项目','当前数值'],['总外包络',' × '.join(f'{v:g}' for v in f['cad_bbox_mm'])+' mm'],['PCB 外形',' × '.join(f'{v:g}' for v in f['board_mm'])+' mm'],['PCB 厚度',f'{f["board_thickness_mm"]:g} mm'],['CAD 零件数量',str(cad['parts'])],['接触分离行程',f'{params["mechanical"]["d_max_m"]*1000:g} mm（名义输入）']],rx+12,yy,[111,right-135],9.2)
            yy=d.panel(rx,369,right,172,'安装与装配','Mounting and assembly')
            d.bullets(['PCB 与 CAD 板外形尺寸一致。','元件中心位于板框内。','待补：器件高度、板卡放置变换、安装孔对应。'],rx+13,yy,right-26,10,8)
        elif index==2:
            d.panel(x,119,left,258,'接触分离结构 · 分层示意','Layer diagram derived from assembly.json')
            layers=[('亚克力背板',150,'#C7D9E9'),('铜电极',100,'#B88B65'),('PTFE',100,'#E5E8EB'),('10 mm 接触 / 分离空间',100,'#DFF1FF'),('PI 膜',100,'#D9B368'),('铜电极',100,'#B88B65'),('亚克力背板',150,'#C7D9E9')]
            for n,(label,width,color) in enumerate(layers):
                yy=174+n*23; ww=width*1.8
                d.rect(x+35+(270-ww)/2,yy,ww,9 if n!=3 else 20,color,radius=0)
                d.text(label,x+322,yy-3,144,8.8,MUTED)
                d.line(x+310,yy+4,x+319,yy+4,BLUE,.5)
            d.text('层间距为排版示意；工程尺寸见 CAD。',x+17,352,left-34,8.5,MUTED)
            yy=d.panel(x,389,left,152,'主要部件','Main components')
            d.table([['部件','作用'],['亚克力 / 铜 / PTFE / PI','接触分离采能结构'],['导向 / 支撑 / 弹簧包络','约束往复运动'],['PCB / 储能 / CDC / 连接件','电气功能与系统接口']],x+12,yy,[196,left-220],9)
            yy=d.panel(rx,119,right,153,'工作原理','Working principle')
            d.bullets(['往复接触与分离形成电荷转移。','整流与提能回路向储能端供能。','人工接通后，MCU 采集电容数据并经 BLE 发送。'],rx+13,yy,right-26,10,7)
            d.pending(rx,284,right,126,'同版 STEP 爆炸图、零件编号、固定件 / 运动件和装配顺序。')
            yy=d.panel(rx,422,right,119,'当前装配问题','Open assembly items')
            d.text('器件高度、PCB 到 CAD 的坐标变换和安装孔对应需要补齐。',rx+14,yy,right-28,10)
        elif index==3:
            yy=d.panel(x,119,left,112,'系统电气架构','Current engineering chain')
            labels=['TENG','整流 / SECE','储能 / 稳压','AD7156','nRF / BLE']
            for n,label in enumerate(labels):
                xx=x+12+n*93
                d.rect(xx,175,83,33,'#FFFFFF',LINE);d.text(label,xx+5,184,75,8.5,BLUE,True)
                if n<4:d.arrow(xx+83,191,xx+91,191)
            d.panel(x,243,left,298,'原生 PCB 视图','Native top and bottom exports')
            d.svg(p/'pcb-top.svg',x+12,289,218,208)
            d.svg(p/'pcb-bottom.svg',x+246,289,218,208)
            d.text('正面 / Top',x+70,507,150,9,MUTED);d.text('背面 / Bottom',x+306,507,150,9,MUTED)
            yy=d.panel(rx,119,right,222,'板级信息','Board-level facts')
            d.table([['项目','读回结果'],['外形',' × '.join(f'{v:g}' for v in f['board_mm'])+' mm'],['对应器件',str(f['schematic_components'])],['对应引脚',str(f['schematic_pins'])],['原理图 / PCB 对应','编号、引脚、网络一致'],['制造资料','已有 Gerber ZIP']],rx+12,yy,[112,right-136],9.0)
            yy=d.panel(rx,353,right,99,'DRC 待修复','Current DRC result')
            d.text(f'{f["drc"]["Clearance Error"]} 项间距错误\n{f["drc"]["Connection Error"]} 项连接错误',rx+14,yy,right-28,12,RED,True)
            d.pending(rx,464,right,77,'PCB 功能分区、关键接口标注。')
        elif index==4:
            d.panel(x,119,left,306,'整体原理图','Native schematic export')
            d.svg(p/'schematic.svg',x+8,164,left-16,246)
            d.pending(x,437,left,104,'导出三组关键回路局部图：采能 / SECE、储能稳压、CDC / MCU。')
            yy=d.panel(rx,119,right,233,'关键器件与接口','Devices and interfaces')
            d.table([['对象','当前用途'],['TENG / SECE','接触分离采能与提能'],['储能 / 稳压','220 µF / 1.8 V 模型'],['AD7156','电容采样 / I²C'],['nRF52832 / S132','BLE 节点目标'],['PC 接收程序','帧解码与显示']],rx+12,yy,[105,right-129],9.0)
            yy=d.panel(rx,364,right,177,'核对与补齐','Review items')
            d.bullets(['39 器件、172 引脚的原理图 / PCB 对应已读回。','厂商引脚、封装、绕组参数仍需逐项核对。','MCU / CDC 的论文来源差异需在设计说明中处理。'],rx+13,yy,right-26,9.8,7)
        elif index==5:
            d.panel(x,119,left,200,'当前固件流程草图','Source-based diagram; Pi to complete exception paths')
            nodes=[('人工接通',x+15,178),('受限广播',x+170,178),('已连接',x+324,178),('采样 / 转换',x+324,252),('待发送 / 通知',x+170,252),('等待下一周期',x+15,252)]
            for label,xx,yy in nodes:
                d.rect(xx,yy,132,36,'#FFFFFF',LINE);d.text(label,xx+11,yy+10,111,10,BLUE,True)
            for a,b in [(0,1),(1,2),(3,4),(4,5)]:
                la,xa,ya=nodes[a];lb,xb,yb=nodes[b]
                d.arrow(xa+(132 if xb>xa else 0),ya+18,xb+(0 if xb>xa else 132),yb+18)
            d.arrow(x+390,214,x+390,250)
            d.text('图源：当前 app_policy.c；异常、重连与重试路径由 Pi 补齐。',x+14,299,left-28,8,MUTED)
            d.panel(x,331,left,210,'当前负载模型的任务窗口','Declared model timeline')
            timeline(d,tl,x+10,371,left-20,155)
            yy=d.panel(rx,119,right,253,'实际源码配置','Current source configuration')
            tm=f['timing']
            d.table([['参数','配置'],['GAP 广播间隔',f'{tm["advertising_ms"]:g} ms'],['策略广播周期',f'{tm["policy_advertising_ms"]:g} ms'],['广播窗口',f'{f["burst"]["MS"]} ms / {f["burst"]["EVENTS"]} 事件'],['连接间隔',f'{tm["connection_min_ms"]:g} - {tm["connection_max_ms"]:g} ms'],['采样周期',f'{tm["sample_ms"]:g} ms'],['目标','nRF52832 / S132']],rx+12,yy,[118,right-142],9.0)
            d.pending(rx,384,right,157,'审定状态图；补当前源码哈希绑定的事件记录。现有沿用事件文件中的 3 份源码已变化。')
        elif index==6:
            d.panel(x,119,left,84,'当前仿真条件','Declared nominal scenario')
            d.text('机械输入：10 mm / 5 Hz    储能：220 µF / 初始 4.2 V\n目标供电：1.8 V    人工接通：t = 0    时间窗：16.001 s',x+14,160,left-28,10)
            rawjob=next(j for j,v in data['system']['jobs'].items() if 'project-trace.raw' in v['artifacts'])
            channels=raw_channels(src/'sources/jobs'/rawjob/'project-trace.raw')
            d.rect(x,215,left,326)
            chart(d,x+10,228,left-20,145,channels['time'],channels['v(storage_rail)'],'储能电压 · 原生 RAW','V',4.5)
            chart(d,x+10,385,left-20,145,channels['time'],channels['v(supply_1v8)'],'供电电压 · 原生 RAW','V',2.0,'#478EAF')
            yy=d.panel(rx,119,right,230,'关键结果','Current native simulation results')
            d.table([['项目','结果'],['样本数',str(power['points'])],['储能电压',f'{power["storage_v"][0]:.3f} → {power["storage_v"][1]:.3f} V'],['最低供电电压',f'{power["minimum_supply_v"]:.6f} V'],['负载 PWL',f'{power["load_binding"]["actual_points"]} 点 / 期望 {power["load_binding"]["expected_points"]} 点'],['接通模型','出现异常负电压']],rx+12,yy,[122,right-146],9.0)
            yy=d.panel(rx,361,right,85,'当前结论','Power / load result')
            d.text('供能与任务负载检查未通过。下一版先修负载窗口对应和人工接通模型。',rx+14,yy,right-28,10,RED)
            d.pending(rx,458,right,83,'源 / 储能 / 负载 / 损耗能量表及单次事件放大图。')
        elif index==7:
            yy=d.panel(x,119,left,300,'需求与检查结果','Current candidate acceptance matrix')
            rows=[['检查项','结果','当前重点']]
            short={'source_domain':'源参数与 SECE','schematic_bom_pins':'器件 / 引脚 / 绕组','pcb_connectivity_drc':'52 间距 / 50 连接','geometry_fit':'高度 / 变换 / 安装孔','firmware_event_logic':'当前输入复用检查','board_firmware_interfaces':'板级外设与引脚','power_load_chain':'PWL / 接通 / 供电','delivery_version':'89 文件与实际作业'}
            for key in data['project']['requirements']['required_gates']:
                rows.append([LABELS[key],STATUS[gates[key]['status']],short[key]])
            d.table(rows,x+12,yy,[170,65,left-259],9.2)
            yy=d.panel(x,431,left,110,'交付目录','Editable engineering package')
            d.text('CAD / STEP    原理图 / PCB / Gerber    固件 / 接收源码\nSPICE / RAW    独立检查    版本清单 / 审查包',x+15,yy,left-30,10)
            yy=d.panel(rx,119,right,154,'交付结论','Delivery conclusion')
            d.bullets(['当前版适合工程审查与继续修订。','固件事件和同版交付已通过。','下一版优先处理供能、PCB 和关键接口。'],rx+13,yy,right-26,10,7)
            yy=d.panel(rx,285,right,136,'下一步','Next iteration')
            d.bullets(['1. 修负载窗口与接通模型。','2. 修 PCB 间距与连接。','3. 补器件、接口与装配数据。'],rx+13,yy,right-26,10,6)
            d.pending(rx,433,right,108,'BF Lead 完成逐页工程结论，并按缺项清单组织专业补图。')
    d.finish()


def detail_pdf(path,data,src,inventory,templates):
    d=Document(path,data,'detail');x=25;w=d.w-50
    gates=data['system']['validations']; c=src/'sources/candidate'; p=src/'sources/previews'
    f=source_facts(data,src); power=f['power']; tm=f['timing']
    for i,title in enumerate(templates['detailed_chapters']):
        d.start(title,'Technical report template / source-bound P01 example',12)
        if i==0:
            d.rect(x,124,w,85)
            d.text('P01 · 接触分离 TENG 无线感知微系统',x+16,140,w-32,19,BLUE,True)
            d.text('详版技术报告模板 · 当前候选数据样稿',x+16,176,w-32,11,MUTED)
            d.image(p/'cad-top.png',x+25,224,w-50,260)
            yy=d.panel(x,500,w,151,'当前工程结论')
            d.bullets(['固件事件逻辑和同版本交付通过。','供能与任务负载、PCB 连接与 DRC 需要修复。','采能源、器件引脚、板级接口、机械装配四项待核实。','物理验证未进行。'],x+15,yy,w-30,11,9)
            d.text('报告对象：'+data['system']['id'],x+3,675,w-6,8,MUTED)
            d.text('采用版单独保留：'+data['adopted_system'],x+3,709,w-6,8,MUTED)
        elif i==1:
            yy=d.panel(x,124,w,259,'使用场景与要求')
            d.table([['项目','当前任务定义'],['机械输入','名义 10 mm 接触分离 / 5 Hz'],['启动方式','人工接通 MCU，人工建立 BLE 连接'],['感知任务','AD7156 电容采样，5000 ms 周期'],['数据链','nRF52832 / S132 → BLE → PC 解码'],['首版目标','完整可执行数字工程及同版本交付'],['检查结构','八项核心门分别记录']],x+12,yy,[130,w-154],10)
            yy=d.panel(x,399,w,255,'需求到验收的对应')
            d.table([['需求方向','检查入口'],['来源与适用工况','source_domain'],['电路、引脚与接口','schematic_bom_pins / board_firmware_interfaces'],['制造与装配','pcb_connectivity_drc / geometry_fit'],['程序与供能','firmware_event_logic / power_load_chain'],['交付一致性','delivery_version']],x+12,yy,[155,w-179],9.7)
            d.pending(x,672,w,83,'BF Lead 补齐需求编号、验收阈值与检查记录的逐项对应。')
        elif i==2:
            yy=d.panel(x,124,w,306,'来源与参数分类')
            d.table([['类型','当前内容','来源'],['论文','TENG 架构、器件表、实验条件','contract.json / BOM 文档'],['实际工程','原理图、PCB、固件、CAD','当前 System Commit 文件树'],['本轮假设','源电容、SECE 包络、耗电幅值','interface-params / load-timeline'],['原生执行','165130 点 RAW、目标固件、STEP','当前选定的三个作业'],['待核实','器件身份、绕组、源与负载参数','独立检查 pending 字段']],x+12,yy,[90,218,w-332],9.5)
            yy=d.panel(x,446,w,171,'主要模型参数')
            d.table([['参数','当前值'],['储能电容 / 初态','220 µF / 4.2 V'],['名义供电 / 效率','1.8 V / 0.85（声明值）'],['TENG 开路峰值 / 电容','361.8 V / 1 nF（声明值）']],x+12,yy,[190,w-214],10)
            d.pending(x,637,w,118,'Power Pi 整理逐参数来源、适用条件，以及器件和论文身份差异的处理。历史 contract 中的旧运行预算另存为历史。')
        elif i==3:
            d.panel(x,124,w,229,'原生 CAD 与尺寸')
            d.image(p/'cad-top.png',x+10,160,270,178);d.image(p/'cad-front.png',x+290,160,240,178)
            yy=d.panel(x,369,w,211,'几何与装配检查')
            d.table([['项目','结果'],['总外包络',' × '.join(f'{v:g}' for v in f['cad_bbox_mm'])+' mm'],['CAD 组成',f'{f["cad_parts"]} 件'],['PCB 外形对应',' × '.join(f'{v:g}' for v in f['board_mm'])+' mm，读回一致'],['元件中心','均位于板框内'],['待补','器件高度、坐标变换、安装孔对应']],x+12,yy,[165,w-189],10)
            d.pending(x,600,w,155,'补等轴图、爆炸图、编号零件表、装配步骤、运动约束与配合尺寸；图表使用当前 STEP 和 assembly.json。')
        elif i==4:
            d.panel(x,124,w,320,'当前原生原理图')
            d.svg(p/'schematic.svg',x+10,164,w-20,267)
            yy=d.panel(x,460,w,168,'器件和网络核对')
            d.bullets(['原理图与 PCB 的 39 个器件、172 个引脚对应一致。','厂商引脚、封装与 T1 绕组参数仍待核对。','BOM 文档记录了 MCU、CDC、储能器件的来源差异。'],x+15,yy,w-30,10.5,9)
            d.pending(x,648,w,107,'Power Pi 提交关键回路局部图与逐器件说明；完整原理图作为附图保留。')
        elif i==5:
            d.panel(x,124,w,355,'原生 PCB 正反面')
            d.svg(p/'pcb-top.svg',x+14,165,246,276);d.svg(p/'pcb-bottom.svg',x+285,165,246,276)
            yy=d.panel(x,495,w,132,'DRC 摘要')
            d.table([['问题','数量'],['间距错误',str(f['drc']['Clearance Error'])],['连接错误',str(f['drc']['Connection Error'])]],x+12,yy,[250,w-274],11)
            d.pending(x,647,w,108,'补真实功能分区、关键网络标注、DRC 问题定位及修复后检查；已有 Gerber 继续按当前版本归档。')
        elif i==6:
            yy=d.panel(x,124,w,270,'目标与实际配置')
            d.table([['项目','当前内容'],['目标','nRF52832 + S132 / nRF5 SDK'],['广播参数',f'GAP {tm["advertising_ms"]:g} ms；策略周期 {tm["policy_advertising_ms"]:g} ms'],['受限广播窗口',f'{f["burst"]["EVENTS"]} 事件 / {f["burst"]["MS"]} ms'],['连接参数',f'{tm["connection_min_ms"]:g} - {tm["connection_max_ms"]:g} ms'],['采样周期',f'{tm["sample_ms"]:g} ms'],['程序产物','ELF / HEX / BIN / MAP / 源包']],x+12,yy,[145,w-169],10)
            yy=d.panel(x,410,w,175,'状态、通信与接收')
            d.bullets(['当前 app_policy 包含接通、广播、连接、采样、通知和断连处理。','事件逻辑复用精确相同输入的独立检查。','接收端包括 BLE 后端、帧解码、管线和 GUI 源码。'],x+15,yy,w-30,10.5,8)
            d.pending(x,605,w,150,'Firmware Pi 审定完整状态图，补当前源码绑定的事件与接收示例。沿用 firmware-events.json 的 main / policy 源码摘要有 3 处变化。')
        elif i==7:
            yy=d.panel(x,124,w,260,'供能—负载接口')
            d.table([['对象','当前模型'],['机械 → TENG','10 mm / 5 Hz 接触分离名义输入'],['提能','单向 SECE 平均包络'],['储能','220 µF，初始 4.2 V'],['人工接通','t = 0，理想开关，动作能量 0'],['负载折算','I_store = I_1V8 × (1.8 / 4.2) / 0.85'],['仿真时间','16.001 s']],x+12,yy,[135,w-159],10)
            d.panel(x,400,w,207,'本轮声明任务时序')
            tl=json.loads((c/'project-chain/load-timeline.json').read_text());timeline(d,tl,x+15,438,w-30,155)
            d.pending(x,627,w,128,'Power Pi 完成实际电路与包络模型的对应、负载幅值依据及器件适用范围。当前独立检查记录负载窗口与网表仍不一致。')
        elif i==8:
            rawjob=next(j for j,v in data['system']['jobs'].items() if 'project-trace.raw' in v['artifacts'])
            ch=raw_channels(src/'sources/jobs'/rawjob/'project-trace.raw')
            d.rect(x,124,w,350)
            chart(d,x+10,141,w-20,155,ch['time'],ch['v(storage_rail)'],'储能电压 · 现有 RAW','V',4.5)
            chart(d,x+10,307,w-20,155,ch['time'],ch['v(supply_1v8)'],'供电电压 · 现有 RAW','V',2.0)
            yy=d.panel(x,490,w,156,'执行与结果')
            d.table([['指标','当前结果'],['原始样本',f'{power["points"]} 点 / {len(ch)} 通道'],['储能首末值',f'{power["storage_v"][0]:.3f} V → {power["storage_v"][1]:.6f} V'],['最低供电',f'{power["minimum_supply_v"]:.6f} V'],['独立负载检查',f'实际 {power["load_binding"]["actual_points"]} 点 / 期望 {power["load_binding"]["expected_points"]} 点']],x+12,yy,[180,w-204],10)
            d.pending(x,666,w,89,'补电流、单次事件放大图与能量账；保留人工接通负压异常的原始样本。')
        elif i==9:
            yy=d.panel(x,124,w,325,'当前八项独立检查')
            rows=[['检查','当前结果']]+[[LABELS[k],STATUS[gates[k]['status']]] for k in data['project']['requirements']['required_gates']]
            d.table(rows,x+12,yy,[345,w-369],10)
            yy=d.panel(x,465,w,172,'优先修订顺序')
            d.bullets(['先修负载窗口对应、人工接通与供电行为。','随后处理 PCB 间距和连接错误。','再补器件参数、板级接口、机械安装数据。'],x+15,yy,w-30,11,10)
            d.pending(x,657,w,98,'BF Lead 为每个未关闭问题补责任专业、拟采取行动与关闭条件，并审定结果摘要。')
        elif i==10:
            yy=d.panel(x,124,w,167,'设计版本')
            d.text('报告候选：'+data['system']['id'],x+14,yy,w-28,8.5)
            d.text('父候选：'+str(data['system'].get('parent')),x+14,yy+45,w-28,8.5)
            d.text('采用版：'+data['adopted_system'],x+14,yy+90,w-28,8.5)
            yy=d.panel(x,307,w,186,'实际选定作业')
            rows=[['类别','作业身份']]
            for job,ref in data['system']['jobs'].items():
                kind='SPICE' if 'project-trace.raw' in ref['artifacts'] else ('CAD' if 'project-cad_summary.json' in ref['artifacts'] else '目标固件')
                rows.append([kind,job])
            d.table(rows,x+12,yy,[130,w-154],10)
            yy=d.panel(x,509,w,147,'本次报告制作记录')
            d.text('Codex：数据收集、模板和原始数据绘图。\nPi：本阶段未派发，补齐任务已按专业列出。\n模型请求 0；工程作业 0；已有成功仿真复用。',x+14,yy,w-28,10.5)
            d.pending(x,676,w,79,'后续正式报告补 Pi 实际生成轨迹、采用的 Skill 版本及报告耗费。')
        elif i==11:
            yy=d.panel(x,124,w,160,'工程交付')
            d.text('候选文件：89 份；本次报告读取与核对 108 份资产。\n目录涵盖 CAD、原生 EDA、固件、接收源码、模型和检查。\n报告数据、模板、来源清单和复现脚本随样稿提供。',x+14,yy,w-28,11)
            yy=d.panel(x,300,w,285,'Pi 报告补齐任务')
            rows=[['任务','负责内容']]
            for task in inventory['tasks'][:9]:rows.append([task['id'],task['task']])
            d.table(rows,x+12,yy,[49,w-73],8.8)
            yy=d.panel(x,601,w,100,'复现入口')
            d.text('REPRODUCE.md 记录收集、渲染和核对命令。\nreport-input.json 绑定候选及来源摘要。\ntemplates.json 控制八页结构与详版章节。',x+14,yy,w-28,9.7)
            d.text('来源 DOI：10.1038/s41378-026-01315-z',x+4,716,w-8,9,MUTED)
            d.text('后续补图和工程修订沿现有 V2 Lead / Power / Firmware 会话继续。',x+4,744,w-8,9,MUTED)
    d.finish()


def main(folder,output):
    src=Path(folder).resolve();out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    pdfmetrics.registerFont(TTFont('BF-Regular','/System/Library/Fonts/STHeiti Light.ttc',subfontIndex=0))
    pdfmetrics.registerFont(TTFont('BF-Bold','/System/Library/Fonts/STHeiti Medium.ttc',subfontIndex=0))
    pdfmetrics.registerFontFamily('BF-Regular',normal='BF-Regular',bold='BF-Bold')
    data=verified_input(src); templates=json.loads((ROOT/'templates.json').read_text())
    subprocess.run([
        '/Users/depengsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node',
        str(ROOT/'render_native_previews.mjs'),str(src/'sources/previews'),str(ROOT/'output/native-previews'),
    ],check=True)
    inventory=field_inventory(data,src/'sources/candidate')
    save(ROOT/'asset-inventory.json',inventory)
    save(ROOT/'report-facts.json',source_facts(data,src))
    with (ROOT/'来源索引.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['kind','path','job_id','local_path','sha256','bytes','system_commit'])
        writer.writeheader();writer.writerows(data['assets'])
    save(ROOT/'report-data.json',{'schema_version':'bf-report-data-v1','system_commit':data['system']['id'],
                                 'source_snapshot':'input/report-input.json','template_version':templates['version'],
                                 'stage':'template proof','inventory':'asset-inventory.json',
                                 'gates':{k:v['status'] for k,v in data['system']['validations'].items()}})
    simple_pdf(out/'P01_简版八页报告_模板样稿.pdf',data,src,inventory,templates)
    detail_pdf(out/'P01_详版技术报告_模板样稿.pdf',data,src,inventory,templates)
    rows=['# P01 八页内容映射与补齐清单','',f'报告候选：`{data["system"]["id"]}`','',
          '| 页 | 内容 | 已有数据与图片 | Pi 补齐任务 |','|---|---|---|---|']
    rows += [f'| {p["page"]} | {p["title"]} | {p["ready"]} | {p["missing"]} |' for p in inventory['pages']]
    rows += ['','| 编号 | 类型 | 负责人 | 要补什么 | 验收条件 |','|---|---|---|---|---|']
    rows += [f'| {r["id"]} | {r["kind"]} | {r["owner"]} | {r["task"]} | {r["acceptance"]} |' for r in inventory['tasks']]
    rows += ['','现有事件文件的旧输入：'+ '、'.join(inventory['historical_event_record_stale_inputs']),
             '','样稿使用当前独立检查、实际 RAW 和当前负载模型；黄色区域对应补齐任务。']
    (ROOT/'P01_八页内容映射与补齐清单.md').write_text('\n'.join(rows)+'\n')
    print(json.dumps({'simple_pages':8,'detailed_pages':12,'assets_verified':len(data['assets']),
                      'missing_report_tasks':9,'engineering_data_tasks':2,'target':data['system']['id']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',default=str(ROOT/'input'))
    parser.add_argument('--output',default=str(ROOT/'output/pdf'))
    args=parser.parse_args();main(args.input,args.output)
