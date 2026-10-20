"""Engineering handoff from one node realization: readable views and two PDFs."""
import html
import json
from pathlib import Path
import sys


def waveform_svg(wave, start=0, end=None):
    end=end or wave['duration_s']; points=[p for p in wave['points'] if start<=p['t_s']<=end]
    if len(points)<2: raise ValueError('NODE_VIEW_WINDOW_EMPTY')
    rows=[('Displacement (mm)','displacement_mm','#546d85'),('VIN / VOUT / PGOOD (V)','vin_v','#738ba0'),
          ('Load (mA)','current_a','#248574')]
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600" viewBox="0 0 1000 600"><rect width="1000" height="600" fill="white"/>']
    for row,(label,key,color) in enumerate(rows):
        top=30+row*150; keys=['vin_v','vout_v','pgood_v'] if key=='vin_v' else [key]
        lo=min(0,min(p[k] for p in points for k in keys)); hi=max(p[k] for p in points for k in keys); span=max(hi-lo,1e-9)
        out.append(f'<text x="65" y="{top+14}" font-family="sans-serif" font-size="15" fill="#223a50">{label}</text>')
        if key=='vin_v':
            for n,(label,c) in enumerate(zip(('VIN','VOUT','PGOOD'),('#738ba0','#0075b5','#ce9c45'))):
                out.append(f'<path d="M{630+n*110} {top+9}h22" stroke="{c}" stroke-width="2"/><text x="{658+n*110}" y="{top+14}" font-size="12" font-family="sans-serif">{label}</text>')
        for tick in range(5):
            t=start+(end-start)*tick/4; x=75+850*tick/4
            out.append(f'<path d="M{x} {top+22}V{top+125}" stroke="#e0e6eb"/><text x="{x-14}" y="{top+145}" font-size="12" font-family="sans-serif">{t:.3f}</text>')
        for n,k in enumerate(keys):
            poly=' '.join(f'{75+850*(p["t_s"]-start)/(end-start):.2f},{top+120-90*(p[k]-lo)/span:.2f}' for p in points)
            c=['#738ba0','#0075b5','#ce9c45'][n] if len(keys)>1 else color
            out.append(f'<polyline points="{poly}" fill="none" stroke="{c}" stroke-width="1.4"/>')
        multiplier=1000 if key=='current_a' else 1
        out.append(f'<text x="5" y="{top+43}" font-size="12" font-family="sans-serif">{hi*multiplier:.3g}</text><text x="5" y="{top+120}" font-size="12" font-family="sans-serif">{lo*multiplier:.3g}</text>')
    out.append('<text x="65" y="503" font-size="15" font-family="sans-serif">Program / sample / transmit / digital receive</text>')
    for e in wave['events']:
        if not start<=e['t_s']<=end: continue
        x=75+850*(e['t_s']-start)/(end-start); color='#248574' if e['state']=='sample' else '#0075b5'
        w=max(3,850*e['duration_s']/(end-start)); y=520 if e['state']=='sample' else 543
        out.append(f'<rect x="{x:.2f}" y="{y}" width="{w:.2f}" height="12" fill="{color}"/>')
        if e['state']=='tx' and e['completed']:
            x+=850*e['duration_s']/(end-start)
            out.append(f'<circle cx="{x:.2f}" cy="575" r="3" fill="#24465d"/>')
    out.append('<text x="850" y="597" font-family="sans-serif" font-size="12">Shared time (s)</text></svg>')
    return ''.join(out)


def sequence_svg(wave):
    e=next(e for e in wave['events'] if e['state']=='sample' and e['completed'])
    tx=next(v for v in wave['events'] if v['state']=='tx' and v['seq']==e['seq'])
    powered=next(v['t_s'] for v in wave['transitions'] if v['powered'])
    labels=['PMIC / PGOOD','MCU / RTC','Sensor value','Radio','Digital receiver']
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600" viewBox="0 0 1000 600"><rect width="1000" height="600" fill="white"/>']
    for n,label in enumerate(labels):
        x=100+n*190; out.append(f'<text x="{x-70}" y="35" font-size="16" font-family="sans-serif">{label}</text><path d="M{x} 50V550" stroke="#acbac6" stroke-dasharray="5 4"/>')
    messages=[(0,1,90,powered,'Power admitted; reset / boot'),(1,1,155,powered,'Arm first task: +1.5 s'),
        (1,2,225,e['t_s'],'SAMPLE seq '+str(e['seq'])),(2,1,290,e['t_s']+e['duration_s'],'Value '+str(e['value'])),
        (1,3,355,tx['t_s'],'TX start; CRC '+str(tx['crc'])),(3,4,420,tx['t_s']+tx['duration_s'],'Valid digital frame'),
        (3,1,480,tx['t_s']+tx['duration_s'],'Return IDLE; next slot +0.8 s')]
    for a,b,y,t,label in messages:
        x1=100+a*190;x2=100+b*190
        if a==b:
            out.append(f'<path d="M{x1} {y}h45v25h-45" fill="none" stroke="#26719d"/>')
        else:
            out.append(f'<path d="M{x1} {y}H{x2}" stroke="#26719d"/><path d="M{x2-7} {y-4}L{x2} {y}l-7 4" fill="none" stroke="#26719d"/>')
        out.append(f'<text x="{min(x1,x2)+8}" y="{y-9}" font-family="sans-serif" font-size="13">{t:.4f} s | {html.escape(label)}</text>')
    out.append('<text x="35" y="585" font-family="sans-serif" font-size="13">Saved host execution. Target mapping and timing differences are listed in target-mapping.json.</text></svg>')
    return ''.join(out)


def render(folder):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    from pypdf import PdfReader
    inp=json.loads((folder/'input.json').read_text()); m=json.loads((folder/'engineering.json').read_text())
    d=json.loads((folder/'design.json').read_text()); wave=json.loads((folder/'timeline.json').read_text())
    cad=json.loads((folder/'assembly-readback.json').read_text()); target=json.loads((folder/'target-status.json').read_text())
    q=json.loads((folder/'qualification.json').read_text()); sid=inp['system_id']
    (folder/'waveform.svg').write_text(waveform_svg(wave))
    tx=next(e for e in wave['events'] if e['state']=='tx' and e['completed'])
    (folder/'waveform-event.svg').write_text(waveform_svg(wave,max(0,tx['t_s']-.025),tx['t_s']+.025))
    (folder/'firmware-sequence.svg').write_text(sequence_svg(wave))
    mapping=[['供电监控','PGOOD → P0.11；VDD 由 SAADC 测量','OFF/复位由硬件 POR/BOR 负责；低压停止服务'],
        ['时间','nRF RTC + APP_TIMER；LFRC 定期校准','主机离散步长 0.5 ms；目标时钟误差单独核对'],
        ['采样','nRF 内部 TEMP，1/4 °C 原始数值','参考接收器固定 2500；目标温度值带单位与编码，需接收端匹配'],
        ['通信','S132 单事件 BLE 广播；厂家数据 seq/value/CRC','参考 TX 4 ms；目标最短广播间隔20 ms、随机延时0..10 ms、超时40 ms。实际电荷和接收待测'],
        ['断电','RAM 状态丢失，重新启动并建立周期','本轮未引入非易失状态保存'],
        ['电流','参考 OFF/IDLE/SAMPLE/TX 四态声明值','模块、晶振、温度和无线的实际波形待测后替换']]
    (folder/'target-mapping.json').write_text(json.dumps({'system_id':sid,'mapping':mapping,
        'target_build':target,'reference_execution':wave['execution_id'],'host_target_equivalence':'OPEN'},ensure_ascii=False,indent=2))
    first=next(v['t_s'] for v in wave['transitions'] if v['powered'])
    received=q['gates']['receiver_service']['findings']['received_sequences']
    count=len(set(received));wave['received_sequences']=received
    native=inp.get('native') or {}; geometry=native.get('geometry',{})
    dfm=json.loads((folder/'native/pcb-dfm.json').read_text()) if (folder/'native/pcb-dfm.json').is_file() else {}
    dfm_labels={'parallel-coupling':'邻近并行走线复核','decap-too-far':'储能与去耦位置复核','power-not-poured':'供电网络铺铜',
        'width-under-spec':'供电走线加宽','fiducial-missing':'贴片定位点'}
    from collections import Counter
    warning_types=Counter(v['type'] for v in dfm.get('findings',[]) if v['level']=='WARN')
    board_issues=[f'{dfm_labels.get(kind,kind)}：{number}项。' for kind,number in warning_types.items()]
    # Native receipts and generated assembly close the earlier attachment todo.
    # Keep the original plan verbatim in engineering.json; show current issues.
    issues=[v for v in m['issues'] if not (native and v.startswith('PCB 本体已由开发者'))]+board_issues
    issues+=['C2/C3与连接器高度使用保守包络，装外壳前核对供应商尺寸；原生器件ESR与参考理想模型的差异见native/geometry.json。']
    conclusion=f'数字工程已形成：连线原理图、50 × 32 mm 双层 PCB、器件包络装配及 nRF52832 目标程序。参考仿真在20 s内完成{count}个有效数字帧；样机验证进入下一阶段。'
    summary={'system_id':sid,'execution_id':wave['execution_id'],'first_powered_s':first,'digital_frames':count,
        'physical_evidence':'digital reference','new_physics_solves':0,'target_build':target.get('status'),
        'motion_peak_mm':wave['peak_motion_mm'],'issues':issues,'assumptions':m['assumptions'],
        'judgment':conclusion,'native_drc_passed':native.get('native_drc_passed'),
        'component_count':len(geometry.get('components',[])),'board_review':dfm.get('summary',{})}
    (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    # The portable viewer embeds data; it opens directly from an extracted ZIP.
    app=Path(__file__).parents[7]/'apps/agent-studio'
    assets=[str(p.relative_to(folder)) for p in (folder/'native').rglob('*') if p.is_file()] if (folder/'native').exists() else []
    bundle={'summary':summary,'engineering':{**m,'issues':issues},'cad':cad,'mesh':json.loads((folder/'assembly-mesh.json').read_text()),
        'wave':wave,'target':target,'mapping':mapping,'native_assets':assets}
    page=(app/'node-engineering.html').read_text().replace('<!--BUNDLE-->',
        '<script>window.NODE_BUNDLE='+json.dumps(bundle,ensure_ascii=False).replace('<','\\u003c')+';</script>')
    page=page.replace('<link rel="stylesheet" href="/node-engineering.css">','<style>'+(app/'node-engineering.css').read_text()+'</style>')
    page=page.replace('<script src="/node-engineering.js" defer></script>','<script>'+(app/'node-engineering.js').read_text()+'</script>')
    (folder/'index.html').write_text(page)
    (folder/'viewer-data.json').write_text(json.dumps(bundle,ensure_ascii=False))
    (folder/'README.md').write_text(f'''# 压电采能节点数字工程

系统：{sid}

1. 解压全部文件，在浏览器打开 `index.html`。所有图纸、波形与下载均使用包内相对路径。
2. `brief.pdf` 是八页简报，`detailed.pdf` 是工程接手报告。
3. 立创专业版4.1.71导入 `native/project.epro2`；CAD软件打开 `assembly.step`。
4. `native/pcb-drc.json` 为严格原生DRC；`native/pcb-dfm.json` 为板级建议及定位。
5. `reference/` 保存原联合计算网表、原始压缩波形、程序和事件；`timeline.json` 保存可读的同轴结果和完整来源哈希。

## 重建目标固件

准备 nRF5 SDK 17.1.0_ddde560 和 GNU Arm GCC9 2020-q2-update。执行：

```sh
python3 rebuild-target.py --sdk /path/to/nRF5_SDK_17.1.0_ddde560 --compiler-bin /path/to/gcc-arm-none-eabi-9-2020-q2-update/bin --output /path/to/new-build
```

脚本核对SDK、编译器及链接脚本摘要，将记录的命令迁移到本机路径，生成应用ELF/HEX并比较交付HEX。
`target/combined.hex` 已包含 S132 7.2.0，烧录前断开外部压电输入并使用受控供电。目标BLE事件、电流和实际接收待台架核对。

## 复核文件

`checksums.json` 列出包内文件SHA256。`system.json`、`input.json`、`qualification.json` 和 `native/receipt.json` 保留候选、执行、检查与原生工程对应关系。

本轮新增物理求解0次。参考输入：零储能、30 Hz、0.5 g峰值、20 s；收到{count}个有效数字帧。
原生DRC通过；板级复核剩{dfm.get('summary',{}).get('warnings',0)}条警告。详报列出位置和修订顺序。
''')
    font=inp['font']
    if 'path' in font:
        pdfmetrics.registerFont(TTFont('NodeCN',font['path'],subfontIndex=0)); fn='NodeCN'
    else: pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light')); fn='STSong-Light'
    body=ParagraphStyle('body',fontName=fn,fontSize=10,leading=16,wordWrap='CJK',spaceAfter=7)
    title=ParagraphStyle('title',parent=body,fontSize=22,leading=30,textColor=colors.HexColor('#153953'),spaceAfter=16)
    heading=ParagraphStyle('heading',parent=body,fontSize=13,leading=20,spaceAfter=10,textColor=colors.HexColor('#2574a1'))
    p=lambda text,style=body:Paragraph(html.escape(str(text)),style)
    def table(rows,widths):
        t=Table([[p(c) for c in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf1f6')),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#ccd7df')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)])); return t
    def graphic(path,width=690,height=350):
        if not path.is_file(): return p('待补：'+path.name)
        drawing=svg2rlg(str(path))
        if not drawing: raise ValueError('NODE_SVG_READ_FAILED:'+str(path))
        scale=min(width/drawing.width,height/drawing.height); drawing.scale(scale,scale);drawing.width*=scale;drawing.height*=scale
        return drawing
    gate_labels={'source_model':'源模型与位移范围','load_binding':'程序与负载对应','power_service':'供电与任务窗口',
        'receiver_service':'数字帧接收','coupling_numerics':'联合收敛与步长','delivery_version':'源码、执行与同版交付'}
    status_labels={'PASS':'通过','FAIL':'未通过','NOT_CHECKED':'待检查','CHECKS_PENDING':'检查待完成','UNEVALUABLE':'缺少条件'}
    drc='通过' if native.get('native_drc_passed') else '待复核'
    board_rows=[['板级项目','当前值'],['板框 / 层数','50 × 32 × 1.6 mm / 2 层'],['原生器件',str(len(geometry.get('components',[])))+' 个'],
        ['原理图 → PCB','器件 uniqueId 和全部焊盘网络逐项读回'],['DRC',drc],['板级复核',f'{dfm.get("summary",{}).get("warnings",0)}条警告；详见后续改进表'],['天线区域','右侧43.6..50 mm，全层禁铜'],['安装','四孔 ⌀3.2 mm，M3 固定'],['制造输出','可编辑 epro2；Gerber 在立创中导出']]
    component_rows=[['器件','实现 / 位置来源','高度 mm']]+[[v['ref'],v['part'],str(v['height_mm'])] for v in geometry.get('components',[])]
    brief_pages=[('整机方案与交付结论','cad-isometric.svg',[
        conclusion,'压电梁 → LTC3588-1 → 储能与2.5 V电源 → 温度采样 → BLE广播。',
        '自由梁90 × 30 mm；零初始储能；名义30 Hz、0.5 g峰值输入。',
        '当前工程工作由Pi设计与Codex板级实现共同完成，原始候选与账本保留。']),
        ('CAD 外形、尺寸与安装接口','cad-top.svg',[
        f'自由梁 {cad["beam_free_length_mm"]:g} × {cad["beam_width_mm"]:g} mm；基底与压电层各0.2 mm。',
        '板卡侧置于梁外：PCB原点(20,35,3) mm，板框50 × 32 mm。',
        f'保存轨迹峰值 {wave["peak_motion_mm"]:.4f} mm；底座避让5.2849 mm，保留2 mm净余隙。',
        '四孔、支柱、M3螺钉和器件高度包络随原生布局更新。']),
        ('机械结构、装配与工作原理','cad-exploded.svg',[
        '底座、根部支撑及压板固定；x=0之外为90 mm自由悬臂。',
        'PCB与10个器件包络来自同版原生布局；高度采用器件手册或库数据。',
        f'STEP读回：{cad["solid_count"]}个有效实体，静态实体干涉0项。',
        '装配采用理想刚性夹持；夹持柔度和紧固预载在样机上复核。']),
        ('电气架构与 PCB 实现','native/pcb.svg',[
        '双层PCB，10个真实器件，6.5 mil信号布线，原生DRC通过。',
        f'右侧为E73无线模块，天线端留全层禁铜区；板级复核剩{dfm.get("summary",{}).get("warnings",0)}条警告。',
        '储能68 µF、输出220 µF、10 µH电感；PGOOD接P0.11。',
        '正反面矢量视图由保存读回的焊盘、走线、过孔及板框生成。']),
        ('电路原理图与关键回路','native/schematic.svg',[
        '压电两端：PZ_IN与GND → LTC3588-1内部整流 → VIN储能。',
        'CAP 1 µF跨接VIN；VIN2 4.7 µF到地；SW经10 µH到VOUT。',
        'D1接GND，D0接VIN2，固定输出2.5 V；模块与SWD使用同一电源。',
        '原生导出保留真实连线、器件编号和网络名；完整连接见工程文件。']),
        ('固件状态与任务时序','firmware-sequence.svg',[
        '时序图取自保存的主机执行：供电准入 → 1.5 s等待 → 11 ms采样 → 4 ms数字发送。',
        '目标：nRF52832，RTC/APP_TIMER、TEMP、SAADC、S132单事件广播。',
        f'目标构建通过：应用Flash {target.get("flash_bytes",0)} B，静态RAM {target.get("ram_static_bytes",0)} B。',
        'BLE事件、实际电流与数字参考存在实现差异，逐项列入目标映射。']),
        ('供能、功耗与储能仿真','waveform.svg',[
        f'首次供电 {first:.4f} s；20 s内收到{count}个有效数字帧。',
        '位移、VIN/VOUT/PGOOD、负载和收发事件使用同一时间轴。',
        '原执行的细步长波形、程序事件和收敛记录继续复用；本阶段新增物理求解0次。',
        '器件ESR、有效电容、实际负载及装配边界由下一轮实测具体化。']),
        ('需求验收与交付目录','waveform-event.svg',[
        f'原生DRC：{drc}；目标构建：通过；STEP静态干涉：0项。',
        f'参考任务：{count}帧 / 最少3帧；原始独立检查与来源随包保存。',
        'index.html：离线交互入口；assembly.step：装配；native/project.epro2：原生工程。',
        'target/：ELF、HEX与读回；target-source/：源码与构建参数；详报列出复核步骤和剩余问题。'])]
    def footer(canvas,doc):
        canvas.setFont(fn,8);canvas.setFillColor(colors.HexColor('#526b7e'));canvas.drawString(36,20,sid[:18]+' · '+wave['execution_id'][:18]);canvas.drawRightString(doc.pagesize[0]-36,20,str(doc.page))
    brief=[]
    right_style=ParagraphStyle('brief-note',parent=body,fontSize=12,leading=19,spaceAfter=13)
    brief_tables=[
        [['任务','输入 / 初态','服务结果','实现'],['压电采能温度节点','30 Hz / 0.5 g峰值 / 零储能',f'20 s内{count}个有效数字帧','LTC3588-1 + nRF52832']],
        [['梁 / 层叠','板框','固定孔','运动余量'],['90 × 30 / 0.2+0.2 mm','50 × 32 × 1.6 mm','四孔 ⌀3.2 mm / M3','峰值外2 mm净余隙']],
        [['夹持','装配对象','CAD检查','待核对边界'],['x=-15..0 mm理想根部',f'{cad["solid_count"]}个实体 / 10个器件包络','STEP读回有效 / 实体干涉0项','接触柔度、预紧及连接器高度']],
        [['导通 / 间距','铜层与布线','安装 / 天线','板级改进'],[f'原生DRC{drc}','2层 / 117段 / 6过孔','四孔 / 全层天线禁铜','铺铜、线宽、去耦、并行段']],
        [['连接','源端','消费端','读回'],['供电','U1.6 → L1/VOUT','U2.17 / J2.1','VDD_2V5'],['电源就绪','U1.10 PGOOD','U2.27 = P0.11','PGOOD'],['调试','J2.3/4/5','U2.38/39/37','SWDCLK / SWDIO / RESET']],
        [['行为','参考执行','目标实现','下一项核对'],['采样 / 周期','11 ms / 0.8 s','RTC / TEMP / SAADC','时基、温度编码与实际负载'],['发送','4 ms数字帧','BLE单事件 / 40 ms上限','测量电荷并独立接收']],
        [['首次供电','任务窗口','数字接收','求解复用'],[f'{first:.4f} s','20 s',f'{count}帧 / 最少3帧','原执行保持 / 新求解0次']],
        [['参考检查','本轮工程检查','工程文件','复核入口'],['六项通过','原生DRC、目标构建、CAD读回','原理图、PCB、STEP、C/H、ELF/HEX','index.html / README.md / checksums.json']]
    ]
    for n,(label,image,notes) in enumerate(brief_pages):
        if n:brief.append(PageBreak())
        brief += [p(str(n+1)+'. '+label,title)]
        panels=Table([[graphic(folder/image,490,375),[p(v,right_style) for v in notes]]],colWidths=[505,265])
        panels.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),12)]))
        brief += [panels,Spacer(1,14),table(brief_tables[n],[192.5]*4)]
    SimpleDocTemplate(str(folder/'brief.pdf'),title='压电采能节点 · 八页工程简报',author='BF Design · Pi / Codex',pagesize=landscape(A4),leftMargin=36,rightMargin=36,topMargin=30,bottomMargin=32).build(brief,onFirstPage=footer,onLaterPages=footer)
    detail=[p('压电采能节点 · 工程接手报告',title),p(conclusion),
        p('版本与交付身份',heading),table([['项目','绑定值'],['系统候选',sid],['参考执行',wave['execution_id']],
            ['原执行项目',wave['execution_origin']['project_id']],['原执行候选',wave['execution_origin']['system_id']],
            ['参考初态与输入','VIN/VOUT=0 V；30 Hz，4.905 m/s²峰值，20 s'],['首次供电 / 有效数字帧',f'{first:.4f} s / {count} 帧'],
            ['新增物理求解','0；复用输入未变的已通过执行'],['交付作者','Pi：安装决策、目标固件与结论；Codex：EDA实现、固定构建与视图生成']],[120,395]),
        p('原生工程与检查',heading),table(board_rows,[140,375]),
        PageBreak(),p('机械、安装与运动边界',title),graphic(folder/'cad-isometric.svg',505,300),
        table([['几何项目','尺寸或检查'],['自由段与层叠','90 × 30 mm；基底0.2 mm + 压电0.2 mm'],['坐标','梁根x=0；侧置板原点(20,35,3) mm'],
            ['运动峰值',f'{wave["peak_motion_mm"]:.9f} mm，spring两节点差除以模态刚度'],['基座与余隙',f'基座顶面z=-{cad["base_gap_mm"]:.6f} mm；运动外净间隙2 mm'],
            ['板卡安装','50 × 32 × 1.6 mm；孔中心距板边3 mm，孔径3.2 mm'],['实体读回',f'{cad["solid_count"]} 个有效实体；静态干涉0项'],
            ['模型适用条件','理想刚性根部；器件为保守空间包络；夹持柔度、线缆及装配公差后续核对']],[130,385]),
        PageBreak(),p('电路实现与器件',title),graphic(folder/'native/schematic.svg',515,290),table(component_rows,[45,395,75]),
        p('供电和控制连接',heading),p('LTC3588-1的PZ2、GND与EP接地，PZ1接压电输入；CAP电容跨接VIN，VIN2电容到地；SW经10 µH连接VOUT，D1=GND、D0=VIN2。VOUT=2.5 V为模块和SWD供电；PGOOD接模块物理焊盘27/P0.11。模块其余未用引脚明确NC。'),
        PageBreak(),p('PCB与装配对应',title),graphic(folder/'native/pcb.svg',515,280),graphic(folder/'native/pcb-bottom.svg',515,280),p('板图来自原生焊盘、117段走线、6个过孔、四安装孔与禁铜区的读回。原始EDA截图、DRC回执、完整坐标及原生工程保存在native/。'),
        PageBreak(),p('目标程序与参考行为',title),table([['功能','目标实现','对应条件']]+mapping,[70,205,240]),
        p('构建与内存',heading),table([['项目','结果'],['目标 / SDK /协议栈','nRF52832-QFAA / nRF5 SDK17.1.0 / S1327.2.0'],['构建',target.get('status')],
            ['应用Flash / 静态RAM',f'{target.get("flash_bytes",0)} B / {target.get("ram_static_bytes",0)} B'],['栈 / 堆预留',f'{target.get("reserved_stack_bytes",0)} B / {target.get("reserved_heap_bytes",0)} B'],
            ['上板检查','待烧录、时钟/电流测量和无线接收测试']],[130,385]),
        PageBreak(),p('程序时序与供电窗口',title),graphic(folder/'firmware-sequence.svg',505,310),graphic(folder/'waveform-event.svg',505,310),
        PageBreak(),p('联合运行与独立检查',title),graphic(folder/'waveform.svg',505,310),
        table([['检查','当前状态','来源候选']]+[[gate_labels.get(k,k),status_labels.get(v['status'],v['status']),v.get('evidence_target',sid)[:18]] for k,v in q['gates'].items()],[190,90,235]),
        p('窗口与证据',heading),p('负载采用固定四态声明包络；目标器件电流、BLE实际事件和接收行为待测。参考数字帧按有效采样、供电、序号与校验判定。联合波形使用原收敛执行，保留原始波形摘要及哈希。'),
        PageBreak(),p('剩余工程问题与交接',title)]+[p('• '+x) for x in issues]
    review_rows=[['位置 / 网络','板级问题','下一动作']]
    for item in dfm.get('findings',[]):
        location=item.get('designator') or item.get('net') or ' / '.join(item.get('nets',[])) or '板边'
        action={'parallel-coupling':'检查共行段并按信号带宽调整间距','decap-too-far':'区分储能电容与高频去耦，缩短模块供电回路',
            'power-not-poured':'在天线禁铜区外规划供电/接地铜面','width-under-spec':'按实际电流和回路阻抗加宽供电线',
            'fiducial-missing':'生产拼板阶段补定位点'}[item['type']]
        review_rows.append([location,dfm_labels[item['type']],action])
    detail += [p('PCB改进顺序：供电回路与铺铜 → 去耦位置 → 并行线间距 → 生产定位点',heading),table(review_rows,[105,150,260]),
        p('复核顺序',heading),p('1. 解压handoff.zip并核对checksums.json。2. 打开index.html查看总装、电路和运行。3. 用立创专业版导入native/project.epro2，核对原理图、PCB和DRC。4. 用CAD软件打开assembly.step，检查孔位和器件包络。5. 按README.md运行rebuild-target.py重建应用，使用target/combined.hex烧录。6. 测量VDD、PGOOD、采样和BLE电流，更新受影响模型后重新联合验证。'),
        p('采用的建模条件',heading)]+[p('• '+x) for x in m['assumptions']]
    sources=[('ADI LTC3588-1','https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf','引脚、外围电容、输出档位、PGOOD'),
        ('Ebyte E73手册','https://www.ebyte.com/downpdf/239.html','引脚表、17.5 × 28.7 × 2.6 mm与天线区域'),
        ('Ebyte E73原理图','https://www.ebyte.com/pdf-down/2316.html','模块晶振与DEC去耦'),
        ('Nordic nRF52832 PS1.9','https://docs-be.nordicsemi.com/bundle/nRF52832_PS_v1.9/raw/resource/enus/nRF52832_PS_v1.9.pdf','SAADC VDD通道、TEMP、RTC及电源'),
        ('Nordic SDK17.1.0','target-source/build-apparatus.json','本地固定构建链、实际编译单元与参数'),
        ('原生库与器件参数','native/geometry.json；native/bom.csv','位置、封装包络、高度及来源'),
        ('原参考执行','input.json；timeline.json；qualification.json','来源候选、不可变波形引用与独立检查')]
    detail += [PageBreak(),p('资料来源与复现索引',title),table([['来源','地址 / 文件','使用位置']]+sources,[105,285,125]),
        p('关键文件',heading),table([['文件','用途'],['native/project.epro2','可编辑原理图与PCB'],['assembly.step / assembly-readback.json','装配与实体检查'],['timeline.json / waveform.svg','统一时间轴与来源引用'],['target-source/ / target/','目标源码、构建参数、ELF/HEX及内存读回'],['target-mapping.json','主机与目标差异'],['input.json / qualification.json','冻结输入与检查快照'],['checksums.json','交付文件摘要']],[220,295]),
        p('设计理由',heading),p(m['judgment'])]
    SimpleDocTemplate(str(folder/'detailed.pdf'),title='压电采能节点 · 工程接手报告',author='BF Design · Pi / Codex',pagesize=A4,leftMargin=40,rightMargin=40,topMargin=34,bottomMargin=34).build(detail,onFirstPage=footer,onLaterPages=footer)
    for f in ('brief.pdf','detailed.pdf'):
        reader=PdfReader(str(folder/f))
        if not reader.pages or any(not p.extract_text().strip() for p in reader.pages): raise ValueError('NODE_PDF_TEXT_MISSING')
    if len(PdfReader(str(folder/'brief.pdf')).pages)!=8: raise ValueError('NODE_BRIEF_PAGE_OVERFLOW')


if __name__=='__main__': render(Path(sys.argv[1]))
