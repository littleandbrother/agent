"""Scoped task reports: one candidate, actual acceptance, profile sections."""
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from ..store import canonical, identity
from .contracts import sealed
from .repository import file_hash
from .repository_profiles import REPORTS
from .report_runtime import report_python

SECTION_LABELS = {
    'task_and_model': '任务与模型', 'mechanics_and_source': '机械与采能',
    'firmware_and_receiver': '程序与接收', 'energy_and_service': '供能与服务',
    'conclusion_and_files': '结论与交付', 'target_and_conditions': '目标与条件',
    'curves_and_error': '曲线与误差', 'board_and_interfaces': '板卡与接口',
    'layout_and_checks': '布局与检查', 'changes_and_checks': '修改与检查',
}
GATE_LABELS = {
    'source_model': '源模型与适用范围', 'load_binding': '程序与负载对应',
    'coupling_numerics': '反馈收敛与步长复核',
    'power_service': '任务供电', 'receiver_service': '数字接收',
    'delivery_version': '交付版本', 'curve_binding': '曲线条件对应',
    'curve_accuracy': '曲线误差', 'pcb_connectivity_drc': 'PCB 连通与设计规则',
    'board_pin_mapping': '板级引脚对应',
}


def report_font():
    path = Path('/System/Library/Fonts/STHeiti Light.ttc')
    return {'path': str(path), 'sha256': file_hash(path)} if path.is_file() else {'cid': 'STSong-Light'}


def prepare(repo, owner, body, operator=False):
    from .repository_validation import qualification
    p = repo.leader(body['project_id'], owner); s = repo.system(p['id'], body['system_id'])
    task = s.get('task_definition')
    if not task or task['profile'] == 'p01-digital-v1': raise ValueError('TASK_SCOPED_REPORT_REQUIRED')
    q = qualification(repo, s)
    if any(v['status'] == 'NOT_CHECKED' for v in q['gates'].values()): raise ValueError('TASK_CHECKS_REQUIRED_BEFORE_REPORT')
    content = json.loads(body['content'])
    if set(content) != {'conclusion', 'sections'} or not isinstance(content['conclusion'], str) or not content['conclusion'].strip():
        raise ValueError('TASK_REPORT_CONTENT_SCHEMA')
    if not isinstance(content['sections'], dict) or set(content['sections']) != set(REPORTS[task['report']]):
        raise ValueError('TASK_REPORT_SECTIONS_REQUIRED')
    for section in content['sections'].values():
        if not isinstance(section, dict) or set(section) != {'text', 'sources'} or not isinstance(section['text'], str) or not section['text'].strip():
            raise ValueError('TASK_REPORT_SECTION_SCHEMA')
        if not isinstance(section['sources'], list) or not section['sources']: raise ValueError('TASK_REPORT_SOURCES_REQUIRED')
        for path in section['sources']:
            if path not in s['files'] and path not in q['gates']: raise ValueError('TASK_REPORT_SOURCE_UNKNOWN')
    from .repository_task_execution import current_execution
    from .repository_task_result import facts
    execution = current_execution(repo, s) if task['case_adapter'] in ('piezo-reference-v1','piezo-feedback-v1','tabulated-curve-v1') else None
    value = {'project_id': p['id'], 'title': p['title'], 'system_id': s['id'], 'task': task,
        'qualification': q, 'content': content, 'files': s['files'], 'author': owner, 'source_author': 'operator' if operator else 'Pi',
        'measured_facts': facts(repo, s, execution) if execution else [],
        'font': report_font(), 'renderer_sha256': file_hash(__file__),
        'runtime_contract_sha256': file_hash(Path(__file__).with_name('report_runtime.py'))}
    rid = 'TR-' + identity(value)
    def apply(db):
        folder = repo.root/'task-reports'/rid
        sealed(folder/'input.json', value)
        quality_file = folder/'quality.json'
        if not quality_file.exists():
            env = {**os.environ, 'PYTHONPATH': str(Path(__file__).parents[3])}
            result = subprocess.run([report_python(), '-m', 'bfworld.agentlab.design_lab.repository_task_reports', str(folder)],
                env=env, capture_output=True, text=True, timeout=45)
            if result.returncode: raise ValueError('TASK_REPORT_RENDER_FAILED: '+result.stderr[-2000:])
        quality = json.loads(quality_file.read_text())
        for path, ref in quality['outputs'].items():
            if file_hash(folder/path) != ref['sha256']: raise ValueError('TASK_REPORT_OUTPUT_CHANGED')
        pointer = repo.root/'task-reports/by-system'/(s['id']+'.json')
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(canonical({'id': rid, 'quality_sha256': identity(quality)}))
        return {'id': rid, 'project_id': p['id'], 'system_id': s['id'], 'status': 'PASS', 'outputs': quality['outputs']}
    return repo.mutate(owner, body, apply)


def required(repo, owner, system):
    from .repository_validation import qualification
    repo.leader(system['project_id'], owner)
    pointer = repo.root/'task-reports/by-system'/(system['id']+'.json')
    if not pointer.exists(): raise ValueError('REQUIRED_TASK_REPORT_MISSING')
    pin = json.loads(pointer.read_text()); folder = repo.root/'task-reports'/pin['id']
    value = json.loads((folder/'input.json').read_text())
    if pin['id'] != 'TR-'+identity(value): raise ValueError('TASK_REPORT_INPUT_CHANGED')
    quality = json.loads((folder/'quality.json').read_text())
    if identity(quality) != pin['quality_sha256']: raise ValueError('TASK_REPORT_QUALITY_CHANGED')
    if value['system_id'] != system['id'] or value['qualification'] != qualification(repo, system):
        raise ValueError('TASK_REPORT_ACCEPTANCE_CHANGED')
    for path, ref in quality['outputs'].items():
        if file_hash(folder/path) != ref['sha256']: raise ValueError('TASK_REPORT_OUTPUT_CHANGED')
    return folder, quality


def render(folder):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib import colors
    from pypdf import PdfReader
    value = json.loads((folder/'input.json').read_text()); task = value['task']; q = value['qualification']
    font = value.get('font', {'cid': 'STSong-Light'})
    if 'path' in font:
        if file_hash(font['path']) != font['sha256']: raise ValueError('TASK_REPORT_FONT_CHANGED')
        pdfmetrics.registerFont(TTFont('BFTaskChinese', font['path'], subfontIndex=0))
        font_name = 'BFTaskChinese'
    else:
        font_name = font['cid']; pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    normal = ParagraphStyle('body', fontName=font_name, fontSize=9.5, leading=15, wordWrap='CJK', spaceAfter=8)
    title_style = ParagraphStyle('title', parent=normal, fontSize=19, leading=26, textColor=colors.HexColor('#10365c'), spaceAfter=14)
    heading = ParagraphStyle('heading', parent=normal, fontSize=13, leading=20, textColor=colors.HexColor('#10365c'), spaceBefore=12, spaceAfter=8, keepWithNext=True)
    small = ParagraphStyle('source', parent=normal, fontSize=8, leading=12, textColor=colors.HexColor('#526176'))
    p = lambda text, style=normal: Paragraph(html.escape(str(text)), style)
    status = {'PASS':'通过','FAIL':'未通过','NOT_CHECKED':'待检查','UNEVALUABLE':'缺少评价条件','REPAIR_REQUIRED':'需修订','CHECKS_PENDING':'待检查'}
    sections = REPORTS[task['report']]
    scope = {'vendor-PMIC-program-feedback':'压电源、厂商电源模型与实际程序的双向执行', 'nominal-reference-chain':'名义参考链：源模型、储能、主机程序与数字接收', 'curve-reproduction':'指定条件下的曲线数据对比', 'pcb-completion':'当前原生板卡审查'}.get(task['scope'], task['scope'])
    story = [p(value['title'], title_style), p(task['goal']), p('验收范围：'+scope),
             p('当前结果：'+status.get(q['status'],q['status'])), p(value['content']['conclusion']), p('候选身份：'+value['system_id'], small)]
    def make_table(data, widths):
        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e7f2fc')), ('GRID',(0,0),(-1,-1),.3,colors.lightgrey),
            ('VALIGN',(0,0),(-1,-1),'TOP'), ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        return table
    data = [[p('检查'), p('结果')]] + [[p(GATE_LABELS.get(k,k)), p(status.get(v['status'],v['status']))] for k,v in q['gates'].items()]
    table = make_table(data, [365, 140])
    story += [table, Spacer(1, 16)]
    measured = value.get('measured_facts', [])
    if measured:
        story += [p('当前执行的数值摘要', heading), p('由已保存的事件和波形计算；来源与完整数值保存在 input.json。', small)]
        data = [[p('项目'), p('数值')]] + [[p(f['label']),p(f"{f['value']:.6g} {f['unit']}")] for f in measured]
        story += [make_table(data,[365,140]),Spacer(1,8)]
    for key in sections:
        section = value['content']['sections'][key]
        section_heading = p(SECTION_LABELS.get(key,key.replace('_',' ')), heading)
        # Keep a heading with its first paragraph, and the final paragraph with
        # its source list, even when the section crosses a page boundary.
        chunks, part = [], ''
        for sentence in re.split(r'(?<=。)', section['text']):
            if not sentence: continue
            if part and len(part)+len(sentence)>450: chunks.append(part);part=''
            part += sentence
        if part: chunks.append(part)
        source_line = p('依据：'+', '.join(section['sources']),small)
        if len(chunks) == 1:
            story.append(KeepTogether([section_heading,p(chunks[0]),source_line]))
        else:
            story.append(KeepTogether([section_heading,p(chunks[0])]))
            story.extend(p(chunk) for chunk in chunks[1:-1])
            story.append(KeepTogether([p(chunks[-1]),source_line]))
    pdf = folder/'task-report.pdf'
    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont(font_name,8);canvas.setFillColor(colors.HexColor('#526176'))
        canvas.drawString(42,22,value['system_id'][:15]+' · '+task['scope'])
        canvas.drawRightString(doc.pagesize[0]-42,22,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(pdf), title=value['title'], author='BF Pi / fixed task report',
        leftMargin=42, rightMargin=42, topMargin=40, bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    md = [value['title'], '', task['goal'], '', 'System: '+value['system_id'], 'Scope: '+task['scope'],
          'Result: '+q['status'], '', value['content']['conclusion']]
    if measured:
        md += ['', '## 当前执行的数值摘要', '', '| 项目 | 数值 |', '|---|---|']
        md += [f"| {f['label']} | {f['value']:.6g} {f['unit']} |" for f in measured]
    for key in sections:
        section = value['content']['sections'][key]; md += ['', '## '+key, '', section['text'], '', 'Sources: '+', '.join(section['sources'])]
    (folder/'task-report.md').write_text('\n'.join(md)+'\n')
    reader = PdfReader(str(pdf))
    if not reader.pages or any(not page.extract_text().strip() for page in reader.pages): raise ValueError('TASK_PDF_TEXT_MISSING')
    quality = {'status': 'PASS', 'system_commit': value['system_id'], 'report_profile': task['report'],
        'pages': len(reader.pages), 'sections': sections, 'qualification': q,
        'outputs': {f: {'sha256': file_hash(folder/f), 'bytes': (folder/f).stat().st_size} for f in ['task-report.pdf', 'task-report.md', 'input.json']}}
    sealed(folder/'quality.json', quality)


if __name__ == '__main__': render(Path(sys.argv[1]))
