"""Package the independently checked D4/E3 case without changing raw runs.

PDF/complete: bundled Python with ReportLab and pypdf. Publish: app Python.
Large RAW files and solver libraries are indexed, not embedded or relicensed.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import zipfile


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def report(stage, version):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak, Table, TableStyle
    from pypdf import PdfReader, PdfWriter

    out = stage / 'report'
    index = read(out / 'figure-index.json')
    result = read(stage / 'native/reference/result.json')
    m = result['metrics']; ledger = m['drive_ledger']
    fem = read(stage / 'verification/corrected-fem-anchors.json')
    pilot = read(stage / 'pilot/trajectory-summary.json')
    progress = read(stage / 'paper/final-progress.json')
    pdfmetrics.registerFont(TTFont('BFUnicode', os.environ.get(
        'BF_FIGURE_PDF_FONT', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf')))
    styles = {key: ParagraphStyle(key, fontName='BFUnicode', fontSize=size,
              leading=size * 1.6, textColor=colors.HexColor('#20282F'),
              spaceAfter=8, wordWrap='CJK')
              for key, size in [('title', 22), ('h', 14), ('body', 10), ('small', 8.5)]}
    def p(value, style='body'):
        return Paragraph(html.escape(str(value)).replace('\n', '<br/>'), styles[style])
    def table(rows, widths):
        t = Table([[p(v, 'small') for v in row] for row in rows], colWidths=widths,
                  repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EDF0F2')),
                   ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                   ('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#D6DCE0'))]))
        return t
    segments = []
    def footer(canvas, doc):
        canvas.setFont('BFUnicode', 8.5); canvas.setFillColor(colors.HexColor('#56616A'))
        canvas.drawString(40, 25, version + ' · 名义模型与真实 Pi 先导 · 未通过自供能或硬件验收')
        canvas.drawRightString(A4[0] - 40, 25, str(doc.page))
    def flush(name, content):
        path = out / name
        SimpleDocTemplate(str(path), pagesize=A4, leftMargin=40, rightMargin=40,
                          topMargin=38, bottomMargin=40).build(content, onFirstPage=footer,
                                                             onLaterPages=footer)
        segments.append(path)

    items = [p('磁耦合门动作节点\n完整加载循环与 Agent 修订证据', 'title'),
             p('2026-10-06 · ' + version + ' / D4 · 源数据绑定的工程、仿真与研究档案'),
             p('已形成可执行、可重算、可审查的受限仿真闭环；尚无合法自供能成功设计。', 'h'),
             p('本报告把操作者的模型确认、Pi 的实际行动、历史电子工程与仍缺的产品验收分开。66/70 是图组来源供应，14/20 是含操作者的独立任务检查，1/20 是当前获准计入的 Agent-owned 任务；均不能改称 80% 自主复现。'),
             p('一、固定任务与共享设计身份', 'h'),
             p('规定门从 65°远处平衡开始，2s 闭合、0.5s 保持、2s 打开、2s 稳定；初始电储能为 0，无外加诊断输入。任务为一次动作后按时收到正确运动通知，不是已认证的开/关状态检测器。梁、磁材、程序阶段负载、接收条件和数值精度冻结。'),
             p('可改的是安装间距、实际磁体支架高度/极性、输入/输出电容与允许的广播配置；变化进入 CAD、力模型、原生电路和共同 C 逻辑。阻尼、启动电流、丢包率或求解精度不能被偷偷降低来提高分数。'),
             p('D4 参考身份：' + result['design_id'], 'small'),
             p('六组图输入身份：' + index['source_identity'], 'small'),
             p('二、完整能量账与原生联合结果', 'h'),
             table([['项目', '参考结果', '解释'],
                    ['间距 / 支架 / 极性', '48mm / 0mm / -1', '铜/PZT 梁、LTC3588-1，Cin/Cout 10µF'],
                    ['位移峰值', f"{m['peak_tip_mm']:.4f}mm", '在 ±8mm ROM 范围内'],
                    ['压电端 / VIN 峰值', f"{m['peak_piezo_V']:.5f}V / {m['peak_storage_V']:.5f}V", '峰值不足以证明完整服务'],
                    ['MCU 电源峰值', f"{m['peak_supply_V']:.8f}V", '仍未启动'],
                    ['冷启动 / 完整 TX / RX', '0 / 0 / 0', '名义任务 unsatisfied'],
                    ['驱动正功 / 返回功', f"{ledger['actuator_positive_input_J']*1000:.6f} / {ledger['actuator_returned_J']*1000:.6f}mJ", '规定轨迹的反力功，不是实测输入'],
                    ['驱动净输入 / PMIC 端口能', f"{ledger['actuator_net_input_J']*1000:.6f}mJ / {ledger['pmic_port_J']*1e6:.5f}µJ", '净输入与端口能分列，不能直接混用'],
                    ['循环账相对残差', f"{ledger['total_relative_residual']:.4%}", '同模型数值一致性，未认证 PMIC 内部损耗']], [130, 140, 245]),
             p('机械、电压反作用和原厂 PMIC 宏模型在同一个 LTspice 求解；供电驱动同一 C 状态逻辑，程序反过来更新负载直到一致。半步长和真正的第二次冷启动原生计算通过。无供电与 TX 中断控制返回零完整报文，诊断 3.3V 能走通状态机。诊断电源不能算产品正例。'),
             p('三、旋转磁场检查与失败保留', 'h'),
             p('原模型三个远角度锚点虽通过局部网格收敛，仍与名义力模型相差约 28–62%。35°处仅加密驱动磁体仍未解决；扩大空气域后误差降至约 0.446%。随后在全部七个预选轨迹锚点应用相同修正，原失败结果保持不变。'),
             table([['锚点', '原相对误差', '修正相对误差', '修正网格差']] +
                   [[a['name'], f"{a['original_reference_error']:.4%}", f"{a['reference_error']:.4%}",
                     f"{a['mesh_delta']:.4%}"] for a in fem['anchors']], [130, 130, 130, 125]),
             p('这些是有限锚点确认，不是整个旋转设计域的物理校准。当前 COMSOL 云图是原生磁通密度 B/T，来自已保存的修正模型。相机裁切另存展示模型；没有把一阶梁模态的 Blender 动作投影称为三维瞬态应力云图。'),
             p('四、真实 Pi 修改轨迹', 'h'),
             table([['条件', '请求 / 候选', '费用', '来源与结果']] +
                   [[t['trial'], f"{t['model_requests']} / {len(t['jobs'])}",
                     f"USD {t['settled_cost_usd']:.7f}",
                     '两个完成、一个越界；均无事件。' + ('操作者提供四个文献 URL；Pi 实际获取三篇主文并读取片段。' if t['primary_locator_assistance'] else '未取得可用的原始论文 PDF。')]
                    for t in pilot['trials']], [95, 80, 85, 255]),
             p(f"共 {sum(t['model_requests'] for t in pilot['trials'])} 次真实模型请求、6 个候选、结算 USD {pilot['cost_upper_usd']:.7f}；本轮没有新增 usage unknown。两条轨迹均有真实原生运行和哈希绑定提交，无人工代填候选参数。原来 9 条未知用量保留，不能为改善页面状态而清零。"),
             p('第二条轨迹将所选候选说成唯一完成的计算，但实际上另一个也完成了；选择的电压和端口能还低于早先候选。由于所有候选都不满足冻结任务，不能反过来只用 VIN 给它们评定产品优劣。这暴露的是反馈对账和选择理由错误，而不是方法已经有效。'),
             p('五、文献参数：先绑定节点与架构', 'h'),
             p('ViPSN-Pluck 的实现明确使用 10µF 储能（PDF p7，V.A Hardware）；统一框架比较 22/33/47/100/220/330µF；Cross-domain 的 SP-SECE 表中 Cstore 为 47µF。它们不能只凭电容数值移植成 D4 的 VIN 节点，也不能断言储能电容都必须是几千微法。'),
             p('LTC3588-1 官方数据表 p3：3.3V 输出设定 D1=1、D0=0 时，VIN 上升启动阈值为 min4.73 / typ5.05 / max5.37V；低输出设定的 typ4.04V 不能当成 3.3V 启动阈值。该官方资料由操作者在试验后独立核对，不倒记为 Pi 当时取得的证据。'),
             p('下一项结构工作应由这些失败决定：审查捕获/释放的实际轨迹，以及具有节点和实现依据的能量提取界面（如参考中的 SP-SECE）。新拓扑必须形成新装置版本并进入联合评价，不注入已冻结试验或用降精度取得“成功”。'),
             p('六、预声明任务与复现分母', 'h'),
             p(f"20 个仿真任务中，含操作者共有 {progress['all_actors_independent_passed']} 个通过独立检查；Agent-owned 仅 {progress['agent_independent_passed']} 个，指实际运行及提交，不包含对已有模板的署名。4 个实物/寿命任务排除于仿真分母但仍列明。图6h保留重绘前快照（13/20），最终14/20见独立 final-progress.json，避免把图的生成结果循环用来证明同一张图。"),
             table([['任务', '记录 / 角色', '独立检查']] +
                   [[t['title'], t.get('record', {}).get('status', 'not_started') + ' / ' +
                     t.get('record', {}).get('actor', 'unknown'),
                     '通过' if t.get('record', {}).get('independently_passed') else '未通过 / 未知']
                    for t in progress['tasks']], [205, 185, 125]),
             p('七、阅读、交付与边界', 'h'),
             p('1 产品/装配 → 2 加载/释放 → 3 候选/干预 → 4 电路/供电 → 5 程序/服务 → 6 数值/复算。每组有完整大图与逐图来源，附录保留70个独立子图；缺项也作为缺项页保留。'),
             p('native/reference 是当前 D4 CAD、共同 C、ARM对象、LTspice deck 与数据；native/fem-corrected 保留七个原生 MPH，native/fem-original 保留原失败源代码/结果与大文件哈希。历史 D3.3 原理图/PCB/采购资料和 D2目标HEX单列于 history，未宣称已和 D4 元件与负载对应。'),
             p('RAW/恢复文件和专有工具库通过 external-native-files.json 记录哈希，不重复打入包。图形离线复算有完整输入和固定脚本；原生重算仍需相同 COMSOL、LTspice/ADI模型、编译器与装置配置。电子制造、目标烧录、事件重启语义、疲劳与实物能耗仍未通过。'),
             p('本轮验证：525项 Python测试通过，SDK/Studio类型、构建和2803样本投影通过；六组70子图独立重绘，228个PNG/SVG/PDF逐字节一致。单件图源和完整交付分别提供，Agent不需要把大原生档案塞进模型上下文。'), PageBreak()]
    flush('report-introduction.pdf', items)
    for g in index['groups']:
        captions = [p(f"图组 {g['order']} · {g['title']}", 'h'), p(g['question']), p(g['conclusion'])]
        captions.extend(p(line, 'small') for line in g['limitations'])
        for panel in g['panels']:
            captions.extend([p(panel['id'] + ' · ' + panel['title']), p(panel['caption'], 'small'),
                             p('证据：' + panel['evidence_kind'] + '；依赖：' + ', '.join(panel['dependencies']), 'small')])
        flush(f"figure-{g['order']}-captions.pdf", captions)
        segments.append(out / g['pdf'])
    flush('report-appendix.pdf', [p('附录：70个独立子图', 'title'),
          p('全尺寸图、表、明确缺项与来源身份。精确数据见CSV/JSON，不以四位有效数字的显示舍入替代原始数据。')])
    segments.extend(out / panel['pdf'] for panel in index['panels'])
    writer = PdfWriter()
    for path in segments:
        writer.append(str(path))
    writer.add_metadata({'/Title': index['title'], '/Author': 'BF Agent Engineering',
                         '/Subject': 'D4 nominal native model and real Pi pilot; no physical qualification'})
    dest = out / 'door-evidence-report.pdf'
    with dest.open('wb') as f:
        writer.write(f)
    return {'pages': len(PdfReader(dest).pages), 'sha256': sha(dest),
            'vector_graphs_preserved': True, 'physical_qualification': False}


def complete(root, history, repository, dest, archive, presentation=None, version='E3'):
    root, history, repository, dest, archive = map(Path, (root, history, repository, dest, archive))
    if dest.exists():
        raise ValueError('E3_DELIVERY_IMMUTABLE')
    presentation = Path(presentation) if presentation else root / 'presentation'
    verification = read(presentation / 'verification.json')
    if verification['status'] != 'passed' or not verification['redraw_identical']:
        raise ValueError('E3_REDRAW_REQUIRED')
    final = read(root / 'paper/final-progress.json')
    if final['target_80_percent_reached'] or final['predeclared_denominator'] != 20:
        raise ValueError('E3_TASK_BOUNDARY_CHANGED')
    stage = dest.with_name(dest.name + '.partial')
    if stage.exists():
        raise ValueError('E3_PARTIAL_REQUIRES_REVIEW')
    stage.mkdir(parents=True)
    external = []
    skipped = {'.raw', '.recovery', '.class', '.status', '.zip'}
    def tree(origin, target, exclude=skipped, omit_mph=False):
        origin = Path(origin)
        for path in sorted(origin.rglob('*')):
            if not path.is_file():
                continue
            if path.is_symlink():
                raise ValueError('E3_SOURCE_SYMLINK')
            rel = path.relative_to(origin)
            if path.suffix in exclude or (omit_mph and path.suffix == '.mph'):
                external.append({'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
                                 'reason': 'Large RAW/recovery/duplicate archive or original failed model retained externally.'})
                continue
            out = stage / target / rel; out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, out)
            if sha(path) != sha(out):
                raise ValueError('E3_COPY_CHANGED')
    tree(presentation / 'report', 'report', exclude=set())
    # Figure-only ZIP is rebuilt below, never edits the admitted figure metadata.
    tree(root / 'presentation/mechanics', 'native/blender')
    tree(root / 'presentation/fem', 'native/fem-presentation')
    tree(root / 'sealed-reference-v2', 'native/reference')
    tree(root / 'sealed-reference-v3', 'native/cold-repeat')
    tree(root / 'trajectory-fem-v1', 'native/fem-original', omit_mph=True)
    correction = read(root / 'verification/corrected-fem-anchors.json')
    for anchor in correction['anchors']:
        folder = Path(anchor['result_path']).parent
        tree(folder, 'native/fem-corrected/' + anchor['name'])
        shutil.copy2(folder.parent / 'declaration.json', stage / 'native/fem-corrected' / anchor['name'] / 'declaration.json')
    tree(root / 'far-field-diagnostic-v1/driver-refined', 'native/fem-driver-only', omit_mph=True)
    for name in ('screen-v2', 'fine-screen-v1'):
        tree(root / name, 'screen/' + name)
    tree(root / 'pilot', 'pilot')
    tree(root / 'paper', 'paper')
    tree(root / 'verification', 'verification')
    shutil.copy2(presentation / 'verification.json', stage / 'verification/figure-redraw.json')
    # Preserve the exact admitted receipts even when this delivery uses a later
    # font-only presentation revision. Never relabel new metadata as old proof.
    byhash = {}
    for path in stage.rglob('*'):
        if path.is_file():
            byhash.setdefault(sha(path), []).append(str(path.relative_to(stage)))
    locators = []
    for task in final['tasks']:
        for evidence in task.get('record', {}).get('evidence', []):
            identity = evidence['sha256']
            if identity not in byhash:
                origin = Path(evidence['path'])
                if not origin.is_file() or sha(origin) != identity:
                    raise ValueError('E3_ADMITTED_EVIDENCE_CHANGED:' + str(origin))
                target = Path('history/admitted-task-receipts') / (identity[:16] + '-' + origin.name)
                copied = stage / target
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origin, copied)
                byhash[identity] = [str(target)]
            locators.append({'task': task['id'], 'original_path': evidence['path'],
                             'sha256': identity, 'packaged_paths': byhash[identity]})
    write(stage / 'paper/portable-evidence-locators.json', {'scope':
          'Original admitted receipts resolved by content identity; historical proof is preserved, not reassigned to the font revision.',
          'evidence': locators})
    tree(history / 'inputs/engineering/electronics-D3', 'history/electronics-D3.3')
    tree(history / 'inputs/engineering/firmware-D2-final', 'history/firmware-D2')
    reproduce = stage / 'reproduce'; reproduce.mkdir()
    for folder, names in [('door_case', ['run_system.py', 'prepare_system_evidence.py', 'diagnose_far_field.py',
                            'audit_system_paper.py', 'prepare_system_pilot.py', 'review_system_pilot.py',
                            'summarize_system_pilot.py', 'export_system_field.py']),
                          ('figures', ['build_system_atlas.py', 'system_views.py',
                           'verify_system_atlas.py', 'complete_system_atlas.py', 'verify_system_delivery.py'])]:
        for name in names:
            shutil.copy2(repository / 'scripts' / folder / name, reproduce / name)
    tree(repository / 'configs/reference_cases/door-system-v3', 'configuration')
    for name in ('door-motion-structure-v2.json', 'loading-release-protocol.json'):
        shutil.copy2(repository / 'configs/reference_cases/design-pilot' / name, stage / 'configuration' / name)
    write(stage / 'external-native-files.json', {'scope': 'Original immutable native files remain on the operator workstation; not embedded or universally portable.', 'files': external})
    (stage / 'README.md').write_text('''# D4 / E3：完整加载循环和真实 Pi 修订档案

入口：report/door-evidence-report.pdf；report/figure-atlas.html。
六组共70个预声明子图（66有来源/4缺项）。这是图组供应，不是设备或80%自主复现成功。
当前全部合法原生候选均无冷启动、完整TX或RX。20任务中含操作者14项通过，Agent-owned仅1项；不能转署既有模板。

## 文件
- report：六组和70个子图PNG/SVG/PDF、精确CSV/JSON、图计划、provenance及固定绘图脚本。
- native/reference：共享D4身份的STEP/BREP/STL、图纸、固件C/共同逻辑/ARM对象、LTspice deck、力表与结果。ARM对象不是完整烧录镜像。
- native/fem-corrected：七个预选锚点的真实MPH/Java/输入/结果；fem-original保留原失败源和数据，大MPH通过外部索引。
- native/blender及fem-presentation：真实CAD渲染、共同相机的动作投影、原生B/T云图；展示模型未修改原求解模型。
- pilot：两个真实Pi会话，原始trace、消息、已观测用量、取得资料、全部候选与提交。第二条有明确URL定位协助，不是等信息方法比较。
- paper：预声明任务、前/后图形验收快照、独立来源核对、逐任务收据。
- history：D3.3电子设计和D2可烧录固件明确为历史工程，未通过D4整机对应或新原生EDA验收。
- paper/portable-evidence-locators.json：按内容哈希定位原始任务收据；字体修订前的图形验收保留在history/admitted-task-receipts，未改写原验收身份。
- external-native-files.json：未重复打包的RAW/恢复/原失败大模型，含原路径、尺寸和哈希。
- seal.json：完整本包文件身份；不把后续发布收据塞入自身哈希循环。

## 只重绘图（无需联网或仿真软件）
安装numpy、matplotlib、Pillow，使用许可合适的CJK字体：
BF_FIGURE_FONT="/System/Library/Fonts/Supplemental/Arial Unicode.ttf" python report/scientific_renderer.py report/reproduce-plan.json /tmp/e3-new-figures
精确逐字节复算需匹配verification/figure-redraw.json与report/figure-quality.json记录的库/字体环境。
可逐项核对seal.json。重定位改变来源路径身份，实际PNG/SVG/PDF仍应一致；不要用元数据路径变化当成数值变化。

## 原生复算边界
需要匹配的BFWorld源码、COMSOL6.2、LTspice/ADI宏模型、CadQuery和C工具链。
reproduce脚本保留当时命令逻辑；专有求解器/模型库和许可未打包，历史绝对路径可能需显式适配。
当前七个有限磁场锚点通过不等于全部设计域或实物确认；没有疲劳、制造/RF、D4烧录和跨重启唯一事件证据。
文献PDF作为本地取得的引用/审查资料保存，不自动允许重新发布至GitHub。
''')
    if version != 'E3':
        notes = stage / 'README.md'
        notes.write_text(notes.read_text().replace('# D4 / E3：', '# D4 / ' + version + '：', 1) +
            '\n技术修订：优先嵌入Arial Unicode TTF，并整理报告标题换行；数据、任务分母和原生/Agent结论与E3相同，旧E3保留。\n')
    pdf = report(stage, version)
    write(stage / 'report/delivery-quality.json', {'report': pdf, 'figure_verification': verification,
          'task_denominator': 20, 'all_actors_independent_passed': 14, 'agent_independent_passed': 1,
          'physical_qualification': False, 'self_powered_success': False})
    with zipfile.ZipFile(stage / 'report/scientific-figures.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted((stage / 'report').rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                z.write(path, path.relative_to(stage / 'report'))
    index = read(stage / 'report/figure-index.json')
    files = [{'path': str(p.relative_to(stage)), 'sha256': sha(p), 'bytes': p.stat().st_size}
             for p in sorted(stage.rglob('*')) if p.is_file()]
    seal = {'schema_version': 'bf-system-e3-delivery-seal-v1', 'version': version, 'source_identity': index['source_identity'],
            'files': files, 'counts': index['counts'], 'report': pdf,
            'task_denominator': 20, 'all_actors_independent_passed': 14, 'agent_independent_passed': 1,
            'physical_qualification': False, 'self_powered_success': False}
    write(stage / 'seal.json', seal)
    stage.rename(dest)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise ValueError('E3_ARCHIVE_ALREADY_EXISTS')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(dest.rglob('*')):
            if path.is_file(): z.write(path, path.relative_to(dest))
    with zipfile.ZipFile(archive) as z:
        if z.testzip(): raise ValueError('E3_ZIP_CRC')
        for entry in files:
            if hashlib.sha256(z.read(entry['path'])).hexdigest() != entry['sha256']:
                raise ValueError('E3_ZIP_READBACK')
    return {'files': len(files), 'report': pdf, 'source_identity': index['source_identity'],
            'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
            'delivery': str(dest), 'archive': str(archive), 'crc_and_readback': True}


def publish(stage, state, owner, receipt, version='E3'):
    from types import SimpleNamespace
    from bfworld.agentlab.store import Store
    from bfworld.agentlab.product_results import ProductResults
    from bfworld.agentlab.engineering_cases import EngineeringCases
    stage = Path(stage)
    seal = read(stage / 'seal.json')
    for entry in seal['files']:
        if sha(stage / entry['path']) != entry['sha256']:
            raise ValueError('E3_SEALED_SOURCE_CHANGED')
    index = read(stage / 'report/figure-index.json')
    lookup = {s['id']: s for s in read(stage / 'report/figure-sources.json')}
    def file(path):
        return {'path': path, 'sha256': sha(stage / path), 'name': path.replace('/', '--')}
    groups = []
    for g in index['groups']:
        panels = []; paths = {'report/' + g[k] for k in ('figure', 'pdf', 'vector')}
        paths.add(f"report/figure-{g['order']}-sources.zip")
        for panel in g['panels']:
            copies = {'figure': 'report/' + panel['figure'], 'pdf': 'report/' + panel['pdf'],
                      'svg': 'report/' + panel['vector'], 'provenance': 'report/' + panel['provenance']}
            records = [{**{k: v for k, v in lookup[s].items() if k != 'archive_file'},
                        'published_path': 'report/' + lookup[s]['archive_file']} for s in panel['dependencies']]
            deps = [s['published_path'] for s in records]
            paths.update(copies.values()); paths.update(deps)
            panels.append({**{k: v for k, v in panel.items() if k not in
                             ('figure', 'pdf', 'vector', 'provenance', 'dependencies')},
                           **copies, 'dependencies': deps, 'source_records': records})
        story = {k: g[k] for k in ('order', 'title', 'question', 'conclusion', 'limitations', 'reference_panels')}
        story.update(baseline_id='door-product-evidence', baseline_version=version,
                     baseline_source_identity=index['source_identity'], source_identity=index['source_identity'],
                     baseline_conclusion=index['conclusion'], figure='report/' + g['figure'],
                     component_summary='D4 full-cycle CAD/native solver/shared C and real Pi; historical D3.3 electronics/D2 target remain separate. No self-powered success.',
                     dependencies=sorted(paths), panels=panels)
        groups.append({'id': 'figure-' + str(g['order']),
                       'domain': {1: 'mechanical', 2: 'mechanical', 3: 'system', 4: 'circuit', 5: 'firmware', 6: 'system'}[g['order']],
                       'title': g['title'], 'kind': 'scientific-figures',
                       'scope': 'D4/E3源数据图谱；历史工程单列，仍无产品或硬件通过。',
                       'design_status': 'insufficient_evidence', 'evidence_story': story,
                       'metrics': {'panels_available': sum(p['status'] == 'available' for p in panels),
                                   'panels_missing': sum(p['status'] == 'missing' for p in panels)},
                       'files': [file(path) for path in sorted(paths)]})
    for id_, domain, title, folders in [
        ('mechanical-native', 'mechanical', 'D4尺寸工程、Blender与COMSOL原生模型', ['native/blender', 'native/fem-corrected', 'native/fem-original', 'native/fem-presentation', 'native/fem-driver-only', 'native/reference/cad']),
        ('electronics-history', 'circuit', '历史D3.3原理图、PCB、BOM（尚未绑定D4）', ['history/electronics-D3.3']),
        ('firmware-sources', 'firmware', '共同C/ARM对象与历史D2目标固件', ['native/reference/firmware', 'history/firmware-D2']),
        ('pilot-evidence', 'system', '两条真实Pi轨迹与全部候选', ['pilot']),
        ('validation', 'system', '任务分母、数值确认与源参数复核', ['paper', 'verification', 'screen'])]:
        paths = sorted(str(p.relative_to(stage)) for folder in folders for p in (stage / folder).rglob('*') if p.is_file())
        groups.append({'id': id_, 'domain': domain, 'title': title, 'kind': 'engineering-source',
                       'scope': '身份和来源保留；有限模型、操作者审查和历史工程不等于自主或物理通过。',
                       'files': [file(path) for path in paths]})
    used = {f['path'] for g in groups for f in g['files']}
    extras = sorted(str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file() and str(p.relative_to(stage)) not in used)
    groups.append({'id': 'report', 'domain': 'system', 'title': '完整E3报告、数据与离线复算包',
                   'kind': 'documentation', 'scope': '20任务独立审查，14项含操作者通过/1项Agent-owned；未达到80%自主复现。',
                   'files': [file(path) for path in extras]})
    manifest = {'schema_version': 'bf-engineering-case-v1', 'id': 'door-product-evidence',
                'version': version, 'title': index['title'].removesuffix(' E3') + ' ' + version, 'authority': 'operator-assisted',
                'hardware_verified': False, 'autonomous_agent_verified': False,
                'design_sha256': index['source_identity'], 'groups': groups}
    catalog = ProductResults(SimpleNamespace(store=Store(Path(state))))
    cases = EngineeringCases(catalog)
    cases.publish(owner, stage, manifest)
    _, files, paths = cases.collect(owner)
    current = [f for f in files if f.get('case_version') == version]
    if any(not f['integrity'] or sha(paths[f['id']]) != f['sha256'] for f in current):
        raise ValueError('E3_PUBLISHED_READBACK')
    value = {'owner': owner, 'version': version, 'groups': len(groups), 'published_files': len(current),
             'integrity_readback': True, 'source_identity': index['source_identity'],
             'prior_case_versions_retained': sorted({f.get('case_version') for f in files if f.get('case_version')}),
             'physical_qualification': False, 'autonomous_80_percent_reproduction': False}
    write(receipt, value)
    return value


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='action', required=True)
    c = sub.add_parser('complete')
    for name in ('root', 'history', 'repository', 'dest', 'archive'): c.add_argument('--' + name, type=Path, required=True)
    c.add_argument('--presentation', type=Path); c.add_argument('--version', default='E3')
    u = sub.add_parser('publish')
    for name in ('stage', 'state', 'receipt'): u.add_argument('--' + name, type=Path, required=True)
    u.add_argument('--owner', required=True)
    u.add_argument('--version', default='E3')
    a = vars(p.parse_args()); action = a.pop('action')
    print(json.dumps(complete(**a) if action == 'complete' else publish(**a), ensure_ascii=False))
