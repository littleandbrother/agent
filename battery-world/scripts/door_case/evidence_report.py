"""Readable PDF edition of the same six-group product evidence baseline."""
import json
import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle


def build(root):
    b=json.loads((root/'report/baseline.json').read_text())
    font=Path(os.environ.get('BF_EVIDENCE_PDF_FONT','/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    if not font.is_file():raise RuntimeError('Set BF_EVIDENCE_PDF_FONT to a CJK TrueType font')
    pdfmetrics.registerFont(TTFont('EvidenceSans',str(font)))
    p=root/'report/door-evidence-report.pdf'
    # A3 landscape keeps six-channel plots readable in the exported document.
    c=canvas.Canvas(str(p),pagesize=(1191,842),invariant=1);c.setTitle('门磁产品证据档案 E1');c.setAuthor('BF Agent Studio')
    style=ParagraphStyle('body',fontName='EvidenceSans',fontSize=11,leading=18,textColor=HexColor('#3d474f'))
    def text(x,y,s,size=12,color='#20252a'):
        c.setFillColor(HexColor(color));c.setFont('EvidenceSans',size);c.drawString(x,y,s)
    def para(s,x,y,w,size=11):
        st=ParagraphStyle('p',parent=style,fontSize=size,leading=size*1.6);el=Paragraph(escape(s),st);_,h=el.wrap(w,1000);el.drawOn(c,x,y-h);return y-h
    def page(n,title):
        c.setFillColor(HexColor('#ffffff'));c.rect(0,0,1191,842,stroke=0,fill=1)
        text(42,809,'BF / PRODUCT EVIDENCE',12,'#66727b');text(999,809,'E1 · 2026-10-05',12)
        text(42,767,title,30);c.setStrokeColor(HexColor('#dce2e6'));c.line(42,42,1149,42)
        text(42,24,'数字工程证据 · 未通过整机冷启动 · 无实物验收',10,'#59656e');text(1128,24,str(n),11)
    page(1,'门动作磁耦合压电节点')
    para(b['conclusion'],42,700,1090,23)
    para('本档案将既有机械、电子、固件和联合仿真按六个问题重新组织。图组由保存的数据生成；没有新增原生求解，没有改写失败结果，也没有把不同修订视作已验证的整机。',42,625,1090,16)
    y=491
    for g in b['groups']:
        text(42,y,f'0{g["order"]}   {g["title"]}',19);text(569,y,g['question'],14);y-=57
    text(42,93,'统一来源身份：'+b['source_identity'],11);c.showPage()
    for g in b['groups']:
        page(g['order']+1,f'图组 {g["order"]}  /  '+g['title'])
        para(g['question'],42,739,1107,15)
        path=root/g['figure'];reader=ImageReader(str(path));iw,ih=reader.getSize();scale=min(1110/iw,574/ih)
        width,height=iw*scale,ih*scale
        c.drawImage(reader,(1191-width)/2,136+(574-height)/2,width=width,height=height)
        y=para('结论：'+g['conclusion'],42,123,1107,15)
        para('范围：'+'；'.join(g['limitations']),42,y-7,1107,11)
        c.showPage()
    page(8,'版本关系、验收边界与下一步')
    y=702
    for comp in b['components']:
        text(42,y,comp['id']+' / '+comp['revision'][:22],16);para(comp['role'],450,y+8,690,15);y-=65
    text(42,335,'下一步工程工作',22);y=296
    for i,t in enumerate(b['next_actions'],1):y=para(f'{i}. {t}',42,y,1107,16)-12
    para('文件可读取性、来源一致性与图组展示属于本次验收。冷启动、全旋转磁场确认、制造检查、硬件测试和 Agent 自主复现是不同验收，仍未完成。完整路径和 SHA-256 位于随附 source-index.json；图组依赖位于 figure-N-provenance.json。',42,109,1107,12)
    c.showPage();c.save()

if __name__=='__main__':build(Path(sys.argv[1]))
