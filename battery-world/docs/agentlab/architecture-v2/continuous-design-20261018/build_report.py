#!/usr/bin/env python3
"""Render the saved finite-pilot results; no model or solver invocation."""
import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape


def main():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

    parser=argparse.ArgumentParser()
    parser.add_argument('--summary',type=Path,default=Path(__file__).parent/'results/summary.json')
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'output/pdf/连续设计与组织对照_实验报告.pdf')
    args=parser.parse_args();data=json.loads(args.summary.read_text())
    font=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    if font.is_file():
        pdfmetrics.registerFont(TTFont('BFStudy',str(font)));name='BFStudy'
    else:
        name='STSong-Light';pdfmetrics.registerFont(UnicodeCIDFont(name))
    navy=colors.HexColor('#143551');blue=colors.HexColor('#176aba');grey=colors.HexColor('#526176')
    body=ParagraphStyle('body',fontName=name,fontSize=10,leading=16,wordWrap='CJK',spaceAfter=8)
    small=ParagraphStyle('small',parent=body,fontSize=8.3,leading=12,textColor=grey,spaceAfter=5)
    title=ParagraphStyle('title',parent=body,fontSize=22,leading=30,textColor=navy,spaceAfter=16)
    heading=ParagraphStyle('heading',parent=body,fontSize=14,leading=21,textColor=navy,spaceBefore=10,spaceAfter=9)
    cell=ParagraphStyle('cell',parent=small,textColor=navy,spaceAfter=0)
    story=[]
    def p(text,style=body):return Paragraph(escape(str(text)).replace('\n','<br/>'),style)
    def table(rows,widths):
        value=Table([[p(c,cell) for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        value.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf2fa')),
            ('GRID',(0,0),(-1,-1),.45,colors.HexColor('#d7e1ec')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
            ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.extend([value,Spacer(1,10)])
    story.extend([p('连续设计与组织对照',title),p('BFA-042 | 2轮原会话修订 + 4项资料试验 + 16项设计试验',small)])
    story.append(p('1. 原主设计者连续修订',heading))
    table([['轮次','真实改变','独立检查与交付'],
        ['第1轮','储能150改为68 µF；修改供电确认、采样与发送策略','20秒4个有效帧；5次启动；欠压发送导致供电门失败。保留审查，PDF及同版工程包齐备。'],
        ['第2轮','继承第1轮完整源树，再改固件启动与发送策略','欠压发送归零，只有1个有效帧；供电、接收门失败。保留审查，PDF及同版工程包齐备。']],[48,199,264])
    story.append(p(f"原会话新增{data['original']['new_model_calls']}次模型请求，登记费用${data['original']['cost_upper_bound_usd']:.6f}。历史采用版保留。"))
    story.append(p('2. 临时资料工作者',heading))
    source=[t for t in data['trials'] if t['stage']=='sources']
    rows=[['任务','直接读取','委派后主会话提交','直接费用','委派总费用']]
    for pair,label in zip(data['source_pairs'],['时序与电流','启动与有效期']):
        rows.append([label,'正确' if pair['direct_correct'] else '无有效提交',
            '正确' if pair['worker_correct'] else '无有效提交',f"${pair['direct_cost_usd']:.6f}",f"${pair['worker_cost_usd']:.6f}"])
    table(rows,[100,93,118,100,100])
    direct=sum(t['cost_upper_bound_usd'] for t in source if t['organization']=='single')
    worker=sum(t['cost_upper_bound_usd'] for t in source if t['organization']=='temporary')
    story.append(p(f'两组均1/2正确；委派费用为直接读取的{worker/direct:.2f}倍。两名工作者提交了有效来源结果，主会话均读取。默认采用直接读取，保留按需委派入口。'))
    story.append(p('资料任务为短JSON参数核对；费用包含主设计者与全部工作者。',small))
    story.append(PageBreak())
    story.append(p('3. 同任务组织对照',title))
    labels={'single':'单主设计者','temporary':'按需资料委派','fixed':'固定双专业提议','joint':'按证据选择范围'}
    tasks=[('V1-local-capacitance','局部电容'),('V2-cold-feedback','零储能启动'),('T1-fixed-power-scheduling','固定电源调度'),('T2-short-validity','8 ms有效期')]
    rows=[['固定任务',*[labels[a] for a in labels]]]
    for key,label in tasks:
        row=[label]
        for arm in labels:
            t=next(t for t in data['trials'] if t['case']==key and t['organization']==arm)
            status=('通过并交付' if t['end_to_end_service'] else '服务通过' if t['valid_service']
                else '失败审查已交付' if t['same_version_releases'] else '未完成交付')
            row.append(status+f"\n${t['cost_upper_bound_usd']:.3f} / {t['model_calls']}请求")
        rows.append(row)
    table(rows,[95,104,104,104,104])
    cold=[t for t in data['trials'] if t['case']=='V2-cold-feedback']
    values=[]
    for arm in labels:
        t=next(t for t in cold if t['organization']==arm)
        values.append(labels[arm]+f"：{t['power_result']['first_powered_s']:.2f} s上电、"+
            str(len(t['receiver_result']['received_sequences']))+'帧')
    story.append(p('零储能实际结果：'+'；'.join(values)+'。固定双专业组的数值精化检查失败。',small))
    story.append(p('三项可行任务合计：',small))
    rows=[['组织','服务通过','同版交付','工作者','请求数','模型费用']]
    for a in data['organizations']:
        rows.append([labels[a['organization']],f"{a['feasible_task_service']}/{a['feasible_tasks']}",
            f"{a['feasible_deliveries']}/3",str(a['feasible_workers']),str(a['feasible_model_calls']),f"${a['feasible_cost_usd']:.4f}"])
    table(rows,[125,85,75,55,65,106])
    story.append(p('四组固定相同任务、资料、初态、模型与判据。每项试验共享80次模型请求和4个候选执行输入，包含父子调用；每任务每组运行一次。'))
    story.append(p('固定双专业组由Power和Firmware工作者返回文件提议，主设计者执行与集成；按需组是否调用工作者以原始轨迹为准。'))
    story.append(p('8 ms任务存在定义缺陷：公开任务未说明有效期起点，检查器从采样开始计龄；最短采样10 ms加发送4 ms已超限。四组原始结果保留，该任务单列。',small))
    story.append(p('排序及配置固定；供应商请求未传入随机种子。耗时受共享求解缓存与本机文件冷加载影响。',small))
    story.append(PageBreak())
    story.append(p('4. 交付与后续选择',title))
    calls=data['total_pilot_calls']+data['original']['new_model_calls']
    cost=data['total_pilot_cost_usd']+data['original']['cost_upper_bound_usd']
    completed=sum(t['completed_candidate_loop'] for t in data['trials'] if t['stage']=='organizations')
    passed=sum(t['end_to_end_service'] for t in data['trials'] if t['stage']=='organizations')
    story.append(p(f'有限清单已记录2轮原会话修订和20项试验；设计对照{completed}/16完成候选交付闭环，{passed}/16服务通过。新增{calls}次模型请求，总登记费用${cost:.6f}。'))
    story.append(p(f"两次零调用启动失败保留原回执，沿原身份恢复。T2-joint遇到磁盘耗尽，原试验未重采样；对账登记失败及{data['storage_reconciliation']['partial_native_dispatches']}次已发生的原生调用，新增求解为0。",small))
    story.append(p(f"T2-fixed达到80次共享请求后结束，联合计算未收敛；追加结算记录补入{data['late_native_dispatches']}次原生调用。原结束快照保留。",small))
    story.append(p('交付核对',heading))
    for text in [
        '源树：连续修订保留父文件；编译输入、实际二进制与求解参数逐项核对。',
        '版本：执行、独立检查、PDF与ZIP均引用同一System Commit。',
        '实验：任务、初始文件、模型和Harness身份一致；全部工作者费用进入账本。',
        '历史：Baseline、Demo、原十会话与工程、历史费用和UNKNOWN保留。',
        '恢复：已完成输入走缓存；原生求解移出SQLite写事务，恢复保留已有操作。']:
        story.append(p('• '+text))
    story.append(p('已发现的问题',heading))
    table([['位置','下一项具体改动'],
        ['来源协议','为资料结果提供files:{}合法示例；错误反馈给出具体字段、路径和定位器。'],
        ['结果引用','统一冻结源文件与执行产物的证据引用；减少把来源塞入文字条件的做法。'],
        ['结束条件','根据已保存回执结束；任务允许可复查的约束冲突出口。'],
        ['报告语义','校核电气能量残差定义，分清储能变化、负载和转换损耗。'],
        ['运行预检','检查磁盘峰值空间、Git身份、依赖实际导入；失败作业保留调用计数。']],[105,406])
    story.append(p('保留完整源树、双向执行、同版交付和按需工作者能力。默认保持原有单主设计者；本批短资料委派未进入默认配置。组织配置固定运行完全部清单，T1/T2用于最终测试，后续优先修复来源协议与任务定义。'))
    story.append(p('V2回归294项通过，44件封存文件及11项控制通过。根目录全量检查在旧iCloud占位文件读取处中止，记录见results/regression.json。',small))
    story.append(p('数据：results/summary.json、trials.csv；复核：scripts/verify_continuous_design.py；原始候选、PDF和工程包保存在V2 Repository。',small))
    story.append(p('本批使用已资格化的压电/厂商PMIC模型、主机C与声明电流。每任务每组织一次，结果用于下一批工程选择。',small))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    def footer(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(colors.HexColor('#d7e1ec'));canvas.line(42,39,553,39)
        canvas.setFont(name,8);canvas.setFillColor(grey)
        canvas.drawString(42,25,'BF Design | BFA-042 | protocol '+data['protocol_sha256'][:12])
        canvas.drawRightString(553,25,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(args.out),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=52,
        title='BF Design 连续设计与组织对照',author='Codex - saved evidence analysis').build(story,onFirstPage=footer,onLaterPages=footer)
    receipt={'path':str(args.out),'sha256':hashlib.sha256(args.out.read_bytes()).hexdigest(),
        'summary_sha256':hashlib.sha256(args.summary.read_bytes()).hexdigest()}
    args.out.with_suffix('.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
