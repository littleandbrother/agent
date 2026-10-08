"""Finalize the local E2 engineering archive; PDF plots remain vector pages.

Run with the bundled Python providing ReportLab and pypdf. Never modifies E1.
Native models are preserved, not silently recomputed by this packaging step.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def report(root):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from pypdf import PdfReader, PdfWriter
    import html

    root = Path(root); output = root / 'report'
    index = json.loads((output / 'figure-index.json').read_text())
    font = os.environ.get('BF_FIGURE_PDF_FONT', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    pdfmetrics.registerFont(TTFont('BFUnicode', font))
    styles = {name: ParagraphStyle(name, fontName='BFUnicode', fontSize=size, leading=size*1.6,
                                   textColor=colors.HexColor('#222A31'), wordWrap='CJK', alignment=TA_LEFT,
                                   spaceAfter=8) for name, size in [('title',22),('h',15),('body',10),('small',8.5)]}
    def paragraph(text, style='body'):
        return Paragraph(html.escape(str(text)).replace('\n','<br/>'), styles[style])
    items = [paragraph(index['title'],'title'), paragraph('源数据绑定的工程与学术图组档案 / 2026-10-05 / E2'),
             paragraph(index['conclusion'],'h'), paragraph('本档案由操作者整理和原生工具计算。没有将文献图、绘图成功、SIL状态、诊断外加电流或构建成功改写为实物、产品或Agent自主复现通过。'),
             paragraph(f"六组共70个预声明子图：已有来源 {index['counts']['available']}；缺证 {index['counts']['missing']}。这个比例描述图组供应，不能称为80%自主复现成功。")]
    for text in index['limitations']: items.append(paragraph(text))
    items.extend([paragraph('本次新增计算','h'),paragraph('12个电阻控制覆盖两种磁方向、0.25/2s动作时间和三档负载。4个22/47/100/220µF输入电容在相同2s动作、Cout100µF、初始0V与无外加电流下，由LTspice和C程序重新执行。四个原生候选均没有冷启动、完整TX或接收事件。'),
                  paragraph('加载循环使用规定闭门/开门轨迹与同一名义磁势能计算反力功。8001个采样点的能量账相对残差为0.379%；这是同模型的数值检查。磁场固定姿态网格差约11.29%，仍未达到5%门槛。'),
                  paragraph('阅读顺序','h'),paragraph('1 产品与装配 → 2 加载释放 → 3 受控比较 → 4 电路供电 → 5 程序服务 → 6 可信度。每组先给问题、结论和边界，再给完整组图；附录保留70个独立大图及其来源身份。'),
                  paragraph('文件与复算','h'),paragraph('figure-atlas.html用于离线逐图阅读，scientific-figures.zip提供全部图与相同输入。reproduce-plan.json和scientific_renderer.py只重新绘图，不重新运行原生求解。inputs保存E1原生工程，analysis保存本轮原生运行与控制。每个子图的provenance和source CSV均可独立核对。'),
                  paragraph('输入身份：'+index['source_identity'],'small'),PageBreak()])
    segments=[]
    def footer(canvas, doc):
        canvas.setFont('BFUnicode',8.5);canvas.setFillColor(colors.HexColor('#56616A'))
        canvas.drawString(40,25,'E2 · 工程/仿真档案 · 未完成产品冷启动或实物验收')
        canvas.drawRightString(A4[0]-40,25,str(doc.page))
    def flush(path, content):
        SimpleDocTemplate(str(path),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=38,bottomMargin=40).build(content,onFirstPage=footer,onLaterPages=footer)
        segments.append(path)
    flush(output/'report-introduction.pdf',items)
    for group in index['groups']:
        captions=[paragraph(f"图组 {group['order']} · {group['title']}",'h'),paragraph(group['question']),paragraph(group['conclusion'])]
        for line in group['limitations']:captions.append(paragraph(line,'small'))
        for panel in group['panels']:
            captions.extend([paragraph(panel['id']+' · '+panel['title'],'body'),paragraph(panel['caption'],'small'),
                             paragraph('证据性质：'+panel['evidence_kind']+'；来源：'+', '.join(panel['dependencies']),'small')])
        flush(output/f"figure-{group['order']}-captions.pdf",captions)
        segments.append(output/group['pdf'])
    # Readable appendix preserves individual native render rasters and vector graphs.
    appendix=[paragraph('附录：70个独立子图','title'),paragraph('这里保留各子图的完整图、表与标注；组图的紧凑表格是明确标记的摘录，完整行列见本附录和CSV。')]
    flush(output/'report-appendix.pdf',appendix)
    segments.extend(output/p['pdf'] for p in index['panels'])
    writer=PdfWriter()
    for path in segments:writer.append(str(path))
    writer.add_metadata({'/Title':index['title'],'/Author':'BF Agent Engineering','/Subject':'Source-bound computational evidence; no physical qualification'})
    dest=output/'door-evidence-report.pdf'
    with dest.open('wb') as f:writer.write(f)
    return {'pages':len(PdfReader(dest).pages),'sha256':sha(dest),'vector_graphs_preserved':True,'physical_qualification':False}


def complete(e1, root, repository):
    e1,root,repository=map(Path,(e1,root,repository))
    # Verify E1's source seal before copying and after copying.
    seal=json.loads((e1/'inputs/source-index.json').read_text())
    for record in seal['files']:
        if sha(e1/'inputs'/record['path'])!=record['sha256']:raise ValueError('E1_SOURCE_CHANGED:'+record['path'])
    if not (root/'inputs').exists():shutil.copytree(e1/'inputs',root/'inputs')
    for record in seal['files']:
        if sha(root/'inputs'/record['path'])!=record['sha256']:raise ValueError('E2_INPUT_CHANGED:'+record['path'])
    rep=root/'reproduce';rep.mkdir(exist_ok=True)
    for name in ('build_door_atlas.py','complete_door_atlas.py','door_analysis.py','door_views.py','verify_scientific_atlas.py'):
        path=repository/'scripts/figures'/name
        if path.exists():shutil.copyfile(path,rep/name)
    (rep/'README.md').write_text('E2 freezes engineering/data/figures separately.\n\n'
        'Figure-only replay: install numpy, matplotlib and Pillow; configure BF_FIGURE_FONT to a licensed CJK font.\n'
        'python report/scientific_renderer.py report/reproduce-plan.json /tmp/e2-figures\n\n'
        'Archive check: python reproduce/verify_scientific_atlas.py /path/to/E2\n\n'
        'PDF assembly additionally needs ReportLab, pypdf and BF_FIGURE_PDF_FONT.\n'
        'Original STEP/BREP/STL, COMSOL MPH/Java, circuit decks, PCB sources, target HEX and source code are under inputs; new native capacitor decks/raw/PWL/receipts are under analysis.\n'
        'The native tools and proprietary solver libraries are not replaced by the figure renderer. '
        'Native re-execution needs the pinned BFWorld solver/toolchain and its declared model assumptions; supplied run files are preserved results, not a claim of universally portable native simulation. '
        'The 250 literature crops are a separate attributed reference archive, not product measurements.\n')
    pdf=report(root)
    quality=json.loads((root/'report/figure-quality.json').read_text())
    quality.update(visual_inspection='Reviewed all six groups and individual tables; native-image embedded labels use full-size/source files.',report=pdf)
    (root/'report/figure-quality.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2)+'\n')
    index=json.loads((root/'report/figure-index.json').read_text());index['quality']=quality
    (root/'report/figure-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(root/'report/scientific-figures.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for p in sorted((root/'report').glob('*')):
            if p.is_file() and p.suffix!='.zip':archive.write(p,p.name)
    records=[{'path':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(root.rglob('*'))
             if p.is_file() and p.name not in ('seal.json','publication.json','publication-receipt.json','verification.json')]
    value={'schema_version':'bf-scientific-atlas-seal-v1','source_identity':index['source_identity'],'files':records,
           'counts':index['counts'],'product_accepted':False,'hardware_verified':False,'autonomous_agent_verified':False,'report':pdf}
    (root/'seal.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return {'files':len(records),'counts':index['counts'],'report':pdf}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--e1',required=True);p.add_argument('--root',required=True);p.add_argument('--repository',required=True)
    a=p.parse_args();print(json.dumps(complete(a.e1,a.root,a.repository)))
