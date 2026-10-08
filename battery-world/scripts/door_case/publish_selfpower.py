"""Publish the actual D5 reference, not a promotion of the old D4 PCB."""
import argparse
import csv
import json
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

from bfworld.agentlab.store import Store
from bfworld.agentlab.product_results import ProductResults
from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json


def publish(run, figures, output, state, owner, audit=None):
    run, figures, output = map(lambda p: Path(p).resolve(), (run, figures, output))
    result = json.loads((run / 'result.json').read_text())
    if result['run_status'] != 'completed': raise ValueError('PUBLISH_REQUIRES_COMPLETED_RUN')
    if result['qualification']['nominal_status'] == 'satisfied':
        audit_value=json.loads(Path(audit).read_text()) if audit else {}
        matching=[r for r in audit_value.get('runs',[]) if Path(r['path']).resolve()==run
                  and r['result_sha256']==file_hash(run/'result.json') and r['design_id']==result['design_id']]
        if audit_value.get('passed') is not True or audit_value.get('cold_repeat',{}).get('passed') is not True or not matching:
            raise ValueError('SELFPOWER_POSITIVE_REQUIRES_INDEPENDENT_AUDIT')
    index=json.loads((figures/'figure-index.json').read_text())
    if index['design_id']!=result['design_id'] or Path(index['source_run']).resolve()!=run:
        raise ValueError('SELFPOWER_FIGURE_SOURCE_MISMATCH')
    for item in index['artifacts']:
        if file_hash(figures/item['path'])!=item['sha256']:
            raise ValueError('SELFPOWER_FIGURE_IDENTITY_CHANGED')
    if output.exists(): raise ValueError('DELIVERY_VERSION_ALREADY_EXISTS')
    output.mkdir(parents=True)
    for name in ('design-spec.json', 'result.json', 'system-manifest.json', 'rom.json',
                 'waveform.csv', 'program.csv', 'energy.json', 'receiver.json', 'rating-check.json',
                 'coupling-iterations.json', 'time-step-check.json', 'drive-ledger.json', 'drive-ledger.csv',
                 'system.cir', 'system.log', 'engineering-evidence.zip'):
        shutil.copy2(run / name, output / name)
    if (run/'gate-observation.json').exists():shutil.copy2(run/'gate-observation.json',output/'gate-observation.json')
    shutil.copytree(figures, output / 'figures')
    shutil.copytree(run / 'firmware', output / 'firmware')
    shutil.copytree(run / 'cad', output / 'cad')
    shutil.copytree(run / 'force', output / 'force')
    shutil.copytree(run / 'executor-source', output / 'executor-source')
    # Saved fine-step facts must remain inspectable outside the separate native
    # evidence archive. Large RAWs and iteration copies stay in that source run.
    shutil.copytree(run / 'time-step', output / 'time-step',
                    ignore=shutil.ignore_patterns('iteration-*', '*.raw', '*.xz', '*.gz', '*.db'))
    if audit: shutil.copy2(audit, output / 'independent-audit.json')
    case = run.parent
    for name in ('CANDIDATE-RATIONALE.md', 'EXPERIMENT-BOUNDARY.json',
                 'CONTROLLER-REVIEW.zh.md','prospective-e96-gate.json',
                 'prospective-e96-6v3-pushpull.json','prospective-low-trip.json',
                 'prospective-program-clock.json','prospective-environment-repair.json',
                 'STORAGE-RECOVERY.zh.md','RESERVE-WINDOW.zh.md','reserve-window-check.json',
                 'full-low-trip-46-01-failure-recovery.json','prospective-rating-gap-revision.json',
                 'storage-summary.json','storage-validation-copy-result.json',
                 'storage-cache-actions.jsonl','storage-validation-copy-actions.jsonl',
                 'verification-runtime-policy.json','storage-restore-sample.json',
                 'prospective-confirmation-guard.json','application-verification-confirmation-guard.json',
                 'targeted-cold-launch-audit.json','native-cycle-ledger.json',
                 'prospective-low-voltage-switch-20261007.json','implementation-low-voltage-switch-20261007.json',
                 'application-verification-si2333.json','full-low-trip-46p2-02-cycle-receipt.json',
                 'application-verification-si2333-local-runtime.json','application-verification-native-containment.json',
                 'DIAGNOSIS-20261007.zh.md','prospective-output-reserve-22uF-20261007.json',
                 'prospective-output-gate-e96-5v43-20261007.json','prospective-qualified-gate-e96-5v16-20261007.json',
                 'prospective-rating-observable-20261007.json','prospective-rating-repair-v2-20261007.json',
                 'storage-recovery-consolidated-20261007.json',
                 'storage-transparent-local-pilot-20261007.json','storage-transparent-project-20261007.json',
                 'storage-immutable-zip-actions-20261007.json','storage-legacy-text-20261007.json',
                 'storage-diagnostic-raw-20261007.json',
                 'storage-transparent-observations-20261007.json',
                 'storage-old-project-raw-summary-20261007.json',
                 'storage-old-project-compression-error-readback-20261007.json',
                 'storage-extra-verified-copies-20261007.json',
                 'product-case-storage-recovery-complete-20261007.json',
                 'product-case-local-readback-20261007.json',
                 'product-case-http-files-20261007.json',
                 'application-verification-final-selfpower-20261007.json',
                 'application-verification-final-selfpower-resident-20261007.json',
                 'verification-runtime-selection-20261007.json',
                 'verification-resource-deferral-20261007.json',
                 'audit-json-repair-20261007.json',
                 'audit-json-repair-tests-20261007.log',
                 'independent-bank3-audit-20261007.log',
                 'delivery-artifact-preflight-20261007.json',
                 'D5-final-figures-verification-20261007.json',
                 'D5-final-figures-visual-20261007.json',
                 'D5-browser-verification-limitation-20261007.json',
                 'cold-repeat-model-rehydration-20261007.json',
                 'cold-repeat-model-local-link-20261007.json'):
        if (case / name).exists(): shutil.copy2(case / name, output / name)
    if json.loads((run/'design-spec.json').read_text()).get('gate_switch')=='Si2333CDS':
        sources=output/'device-sources';sources.mkdir()
        for name in ('Si2333CDS.spice.txt','Si2333CDS.pdf','Si2333CDS-model-guide.pdf'):
            shutil.copy2(case/'sources'/name,sources/name)
    sources=output/'device-sources';sources.mkdir(exist_ok=True)
    for name in ('terminal-ratings-provenance.json','2N5401-onsemi.pdf'):
        if (case/'sources'/name).exists():shutil.copy2(case/'sources'/name,sources/name)
    rows = []
    failures = output / 'candidate-history'; failures.mkdir()
    for path in sorted(case.glob('full-*/result.json')):
        item = json.loads(path.read_text()); spec = json.loads((path.parent / 'design-spec.json').read_text())
        m = item.get('metrics', {}); b = spec['base_design']
        manifest_path=path.parent/'system-manifest.json'
        executor=json.loads(manifest_path.read_text())['executor_sha256'] if manifest_path.is_file() else 'preflight-no-native-manifest'
        rows.append({'run': path.parent.name, 'result_sha256': file_hash(path),
                     'design_id': item['design_id'], 'executor_sha256': executor,
                     'gap_mm': b['mechanical']['gap_mm'], 'cin_uF': b['circuit']['cin_uF'], 'cout_uF': b['circuit']['cout_uF'],
                     'envelope_pF': spec['extraction']['envelope_pF'], 'gate': spec['gate'],
                     'gate_switch':spec.get('gate_switch','BSS84'),
                     'diodes':spec['extraction']['diodes'],'rating_protocol':item.get('rating_protocol','legacy-series-proxy-v1'),
                     'monitor_device': spec['parts']['monitor'].split()[0],
                     'gate_pullup_ohm': spec['parts'].get('gate_pullup_ohm', 470000.),
                     'packet_policy': spec.get('application', {}).get('packet_policy', 'legacy'),
                     'run_status': item['run_status'], 'nominal_status': item['qualification']['nominal_status'],
                     'peak_storage_V': m.get('peak_storage_V', ''), 'piezo_port_uJ': m.get('energy_ledger', {}).get('piezo_port_J', '') * 1e6 if m.get('energy_ledger') else '',
                     'complete_TX': m.get('tx_completed', ''), 'received_events': m.get('received_events', ''),
                     'failure': item.get('error', '')})
        target = failures / path.parent.name; target.mkdir()
        for name in ('result.json', 'design-spec.json', 'system-manifest.json', 'coupling-iterations.json', 'time-step-check.json',
                     'joint/provisional-solve.json'):
            if '/' in name and (path.parent / name).is_file():
                shutil.copy2(path.parent / name, target / Path(name).name)
                continue
            if (path.parent / name).is_file(): shutil.copy2(path.parent / name, target / name)
    recovery=case/'full-low-trip-46-01-failure-recovery.json'
    if recovery.is_file():
        target=failures/'full-low-trip-46-01';target.mkdir(exist_ok=True)
        shutil.copy2(recovery,target/'failure-recovery.json')
        if (case/'full-low-trip-46-01/design-spec.json').is_file():
            shutil.copy2(case/'full-low-trip-46-01/design-spec.json',target/'design-spec.json')
    with (output / 'candidate-comparison.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    metric = result['metrics']; energy = metric['energy_ledger']; q = result['qualification']
    gate_facts=metric.get('gate_observation',{})
    drive_energy=json.loads((output/'drive-ledger.json').read_text())
    d = json.loads((output / 'design-spec.json').read_text())
    status = {'satisfied': '名义仿真自供能成功',
              'unsatisfied': '名义仿真尚未满足事件任务',
              'not_evaluable': '已计算，但尚未通过名义模型验收'}[q['nominal_status']]
    failed_checks = ', '.join(k for k, v in result['checks'].items() if v is not True) or '无'
    independent = (json.loads(Path(audit).read_text()).get('passed') is True) if audit else False
    repeat_table = '本版本没有通过两次独立冷复算审计。'
    if independent:
        comparison = ['|运行|步长|VIN峰值 / V|梁峰值 / mm|完整TX|虚拟RX|首个TX / s|',
                      '|---|---|---:|---:|---:|---:|---:|']
        for audited in json.loads(Path(audit).read_text())['runs']:
            source = Path(audited['path'])
            for scale, facts in (('标准', audited['metrics']),
                                 ('半步长', json.loads((source/'time-step/solve.json').read_text()))):
                comparison.append(f"|{source.name}|{scale}|{facts['peak_storage_V']:.9f}|"
                                  f"{facts['peak_tip_mm']:.9f}|{facts['tx_completed']}|"
                                  f"{facts['received_events']}|{facts['first_TX_s']}|")
        repeat_table = '\n'.join(comparison)
    switch_scope = (
        '本方案使用 Si2333CDS 原厂典型 PSpice 子电路；独立外供电夹具已核对模型导通电阻与数据表测试点。'
        'LEVEL3 尺寸建议警告原样保留，没有拟合模型来强迫整机通过。'
        if d.get('gate_switch', 'BSS84') == 'Si2333CDS' else
        '本方案使用安装版 LTspice 的 BSS84 非线性器件模型，模型来源与执行身份保存在本次工程包中。'
        '此前 Si2333CDS 外供电夹具属于另一器件的控制实验，不计作本方案器件验收。'
    )
    report = f'''# D5 门磁自供能工程参考

当前结论：**{status}**。初始电能为0，完成发送{metric['tx_completed']}次，虚拟接收事件{metric['received_events']}个。操作者辅助原生工程，未计为Pi自主设计或实物验证。

设计：磁体间距{d['base_design']['mechanical']['gap_mm']:g} mm，CIN {d['base_design']['circuit']['cin_uF']:g} µF，COUT {d['base_design']['circuit']['cout_uF']:g} µF，SECE包络电容{d['extraction']['envelope_pF']:g} pF，门控{d['gate']}，负载开关{d.get('gate_switch','BSS84')}，应用{d['application']['packet_policy']}。

## 实际执行结果

|项目|结果|
|---|---|
|梁峰值位移|{metric['peak_tip_mm']:.6f} mm；上限8 mm|
|压电端峰值|{metric['peak_piezo_V']:.6f} V|
|输入储能峰值|{metric['peak_storage_V']:.6f} V|
|监控器有效供电后的输入峰值|{gate_facts.get('powered_VIN_peak_V','旧版本未记录')} V|
|监控器有效控制峰值|{gate_facts.get('powered_control_peak_V','旧版本未记录')} V|
|门控首次实际接通|{gate_facts.get('first_gate_enabled_s','旧版本未记录')} s|
|MCU供电峰值|{metric['peak_supply_V']:.6f} V|
|压电端净输出|{energy['piezo_port_J']*1e6:.3f} µJ|
|规定门运动的正向输入功|{drive_energy['actuator_positive_input_J']*1e3:.6f} mJ|
|磁力返回规定运动端的功|{drive_energy['actuator_returned_J']*1e3:.6f} mJ|
|规定运动端的净输入功|{drive_energy['actuator_net_input_J']*1e3:.6f} mJ|
|完整应用耗能|{energy['application_J']*1e6:.3f} µJ，使用实际V(t)和冻结阶段电流|
|首次完整TX|{metric['first_TX_s']} s|
|首次虚拟接收|{metric['first_RX_s']} s|
|机械/压电能量相对残差|{energy['mechanical_piezo_relative_residual']:.8g}|
|步长确认|{result['checks']['time_step']}|
|器件判据版本|{result.get('rating_protocol','legacy-series-proxy-v1')}|
|集电极峰值电流|{metric['ratings'].get('collector_peak_A','旧版没有直接观测')} A|
|电感峰值电流|{metric['ratings'].get('coil_peak_A')} A|
|未通过的检查|{failed_checks}|
|独立冷复算与重编译C|{'通过' if independent else '本版本未通过该验收'}|

本任务是完整的关闭—停留—打开过程内完成一次通知。驱动功来自规定运动和同一磁力模型的反力计算，正负功分别记录；返回运动端的功不是已经实测回收的电能。这些量不自动构成硬件采能效率或单次开门的独立成功证明。

## 独立复算对照

{repeat_table}

独立审计同时核对归档RAW的完整字节、原生启动目录与时间、保存的器件端口、重新编译的应用C和虚拟接收。重复运行没有使用成功数值缓存；共享的是声明一致的工程输入。相同名义预测不等于物理不确定性已经消失。

审计的首次尝试在写出JSON时因NumPy布尔类型中断，没有生成合格参考。修复仅涉及严格序列化和只读校验的并行读取，保留原失败日志及40项针对性测试；通过重新完整审计后才发布本结果。原生执行器、输入和验收判据没有因此更改。

## 电路器件与判据修复

二极管配置：{d['extraction']['diodes']}。并联配置若存在，其实际清单为：{json.dumps(d['parts'].get('diode_bank',{}),ensure_ascii=False)}。新原生网表逐支路执行，不使用理想二极管或事后平摊电流。判据v2将2N5401的集电极电流与电感电流分开检查；BAT46WJ重复脉冲不再借用2.5A单次浪涌值。250mA逐支路峰值筛选是保守的充分条件，超过它表示尚未获得脉冲资格，并不自动证明元件损坏。此前结果保留旧判据身份，不追溯改写成通过。

## 证据顺序

1. 尺寸与任务：真实STEP、安装坐标和固定完整门动作。
2. 机械取能：互易力、电压反作用、梁响应、驱动功和压电端能量。
3. 电路：实际原生网表、非理想提取器件、LTC3588-1宏模型与有耗电门控。
4. 联合过程：同一时轴上的位移、压电电压、储能、供电、程序状态和负载。
5. 应用：重编译C的完整BOOT/INIT/TX、真实电压复位规则及虚拟接收。
6. 验收：全部数值检查、额定筛查、失败历史、步长和独立复算。

六组图共{index['subpanels']}子图，提供逐张可编辑SVG、矢量PDF及300dpi PNG；每个子图绑定具体来源，可在产品页逐张查看。D5-figure-atlas.pdf汇总六组。绘图来自本次原生数据；电路功能图是网表的辅助说明，不冒充EDA原理图或实物照片。独立开关夹具使用外供电，明确列为器件控制实验，不计入整机自供能成功。

## 复算和完整原生数据

engine=door-selfpower，parameters.candidate见design-spec.json，confirmation=true。软件依赖是已配置的CAD Python、原生LTspice、ARM/主机编译器，以及ROM和哈希绑定的器件模型。executor-source保存了本次执行源码；engineering-evidence.zip保存原生网表和小型回执。

大型RAW按字节无损压缩保留在源运行目录 `{run}`。system-manifest.json记录原始大小/SHA、XZ或gzip大小/SHA及恢复命令。按时间窗/通道读取waveform.csv和program.csv即可检查公开反馈；压缩RAW没有采样丢失。此前失败运行的gzip重存回执还验证了原gzip文件字节可精确恢复，旧报告和结果文件不被改写。

## 仍未证明的内容

- 本次属于固定梁和器件家族的名义仿真，有限FEM锚点不能代替全旋转域、应变/疲劳/接触或制造公差确认。
- MIC841L采用有供电耗能的推挽行为模型；此前MIC841N的输出极性标注错误已在复审中保留并修正，旧结果不能升格为真实N器件验证。未证实全部器件热脉冲SOA、漏电/温度、核心损耗及真实目标代码功耗。
- {switch_scope} 典型模型不代表所有温度、公差或器件实测。
- 主机在环C和Cortex-M4对象不是新的完整可烧录镜像；虚拟接收不是实物RF测量，one-shot也不保证跨重启恰好一次或开/关状态真值。
- **D4的PCB和其CAD中的PCB包络不包含D5新增提取电路与门控，仍为stale，不能拿旧板投产。** 本版本不包含伪造的新版PCB布线或已制造声明。
- candidate-comparison.csv保留不同固件/电路版本和执行身份；这些开发候选不是等信息、等预算的方法对照实验。数值失败不记为器件不可行，磁盘资源错误记为环境失败，未收敛TX不记为任务成功。
- compiled C 使用整数微秒累计阶段时间；既往浮点时间误差已通过移位时钟和完成时掉电的实际编译控制检查。实际储能余量依赖动态采能和转换器，而非静态电容窗口求和。

参考来源：[ViPSN-Pluck](https://metal.shanghaitech.edu.cn/publication/J40.pdf)、[统一跨域仿真论文](https://sms-lab.github.io/publications/J101_Tang%20et%20al_2025_10.10881361-665xadd8d4.pdf)、[LTC3588-1数据表](https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf)、[MIC841数据表](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/20005758A.pdf)、[7447471471线圈](https://www.we-online.com/components/products/datasheet/7447471471.pdf)、[BAT46WJ数据表](https://assets.nexperia.com/documents/data-sheet/BAT46WJ.pdf)、[2N5401数据表](https://www.onsemi.com/download/data-sheet/pdf/2n5401-d.pdf)、[Si2333CDS数据表](https://www.vishay.com/docs/68717/si2333cd.pdf)、[原厂模型](https://www.vishay.com/docs/68516/si2333cd.txt)。本电路是有声明器件替换和输出极性适配的参考辅助设计，不是论文原图的逐器件原样复现。
'''
    (output / 'REPORT.zh.md').write_text(report)
    reproduce = output / 'reproduce'; reproduce.mkdir()
    for name in ('render_selfpower.py', 'audit_selfpower.py', 'run_selfpower.py'):
        shutil.copy2(Path(__file__).parent / name, reproduce / name)
    write_json(reproduce / 'scripts.json', {
        'scripts': [{'name': p.name, 'sha256': file_hash(p)}
                    for p in sorted(reproduce.glob('*.py'))],
        'executor_sha256': json.loads((output / 'system-manifest.json').read_text())['executor_sha256'],
        'requires': 'Matching bfworld installation; NumPy and Matplotlib for plotting; native tools for full rerun.',
        'large_native_raw_included': False,
    })
    (reproduce / 'README.zh.md').write_text('''# 从本包重绘与复核

在工程包根目录执行，使用与记录匹配、已安装 bfworld、NumPy、Matplotlib 的 Python：

```sh
python reproduce/render_selfpower.py --run . --output redraw
```

这条命令从本包波形和回执重绘六组图，不启动新的求解器或付费模型。重绘目录必须不存在。原始审计绑定原运行路径；迁移后的重绘不重新冒用旧路径的冷复算资格，因此会将冷复算显示为待核对。原已验收图集和独立审计原文仍完整保留。

重新做独立原生审计还需要 system-manifest.json 指向的两次完整运行、所有无损 RAW 归档、绑定模型和编译器。大归档没有装入此轻量交付包，不可把只有 CSV 的重绘当作新的原生求解或独立审计。

完整求解入口和审计脚本一起保存；使用前核对 scripts.json 的执行身份、依赖与原任务条件。executor-source 是原生执行源码快照，不是完整软件依赖环境。
''')
    with zipfile.ZipFile(output / 'D5-engineering-package.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if (p.is_file() and p.name != 'D5-engineering-package.zip'
                    and p.suffix not in ('.dylib', '.pyc','.raw','.xz','.gz')):
                z.write(p, p.relative_to(output))
    sha = file_hash(output / 'design-spec.json')
    descriptors = [
        ('design','mechanical','cadquery','尺寸与任务','规定门动作与机械实体；新增电路未进入旧PCB包络',
         ['design-spec.json','cad/assembly.step','cad/installation.step','cad/cad-readback.json',
          'cad/d4-cad-receipt.json','cad/bom.csv','cad/top.svg','cad/front.svg','cad/side.svg','cad/drawing-index.json']),
        ('mechanics','mechanical','beam-event','机械取能','同一互易模型的实际响应和驱动功；没有新增物理标定',
         ['waveform.csv','rom.json','drive-ledger.json','drive-ledger.csv','force/force-domain.json']),
        ('circuit','circuit','spice','自供能电路','非理想SECE、原厂PMIC、有耗电行为门控；新版PCB仍缺失',
         ['system.cir','system.log','design-spec.json','rating-check.json']),
        ('joint','system','closed-simulation','完整联合过程','原生供电与完整编译C达到固定点；名义模型范围',
         ['waveform.csv','program.csv','energy.json','coupling-iterations.json','result.json']),
        ('program','firmware','mcu-firmware','完整应用与虚拟接收','主机在环及ARM对象；未烧录、未测真实功耗或RF',
         ['firmware/program.c','firmware/policy.h','firmware/build-receipt.json','firmware/program-arm.o','receiver.json','program.csv']),
        ('acceptance','system','engineering-report','验收与交付','名义仿真逐项检查及历史失败；物理制造均未放行',
         ['result.json','system-manifest.json','time-step-check.json','time-step/solve.json',
          'time-step/program.csv','time-step/waveform.csv','time-step/energy.json',
          'time-step/rating-check.json','time-step/receiver.json','time-step/coupling-iterations.json',
          'candidate-comparison.csv','REPORT.zh.md','engineering-evidence.zip','D5-engineering-package.zip',
          'figures/D5-figure-atlas.pdf','reproduce/README.zh.md','reproduce/scripts.json',
          'reproduce/render_selfpower.py','reproduce/audit_selfpower.py','reproduce/run_selfpower.py']
         +(['independent-audit.json'] if audit else []))]
    stems = ['figure-1-design','figure-2-mechanical','figure-3-circuit','figure-4-joint-timeline','figure-5-program','figure-6-acceptance']
    groups = []
    for i, ((gid, domain, kind, title, scope, paths), stem) in enumerate(zip(descriptors, stems), 1):
        paths += ['figures/'+stem+'.'+ext for ext in ('png','svg','pdf','provenance.json')]
        panels=[p for p in index.get('panels',[]) if p['id'].startswith(str(i))]
        for panel in panels:
            paths += [panel[k] for k in ('figure','pdf','svg','provenance')]+panel['dependencies']
        if gid=='circuit' and (output/'device-sources').exists():
            paths += [str(p.relative_to(output)) for p in sorted((output/'device-sources').iterdir())]
        if gid=='circuit' and (output/'gate-observation.json').exists():paths.append('gate-observation.json')
        paths=list(dict.fromkeys(paths))
        files = [{'path': s, 'name': s.replace('/', '--'), 'sha256': file_hash(output / s)} for s in paths]
        story = {'order': i, 'baseline_id': 'door-product-evidence', 'baseline_version': 'D5-selfpower',
                 'baseline_source_identity': sha, 'source_identity': sha, 'title': title,
                 'question': '该部分实际执行了什么，证据与适用范围是什么？',
                 'conclusion': scope, 'baseline_conclusion': status, 'component_summary': status,
                 'dependencies': paths, 'limitations': ['名义仿真；物理、制造与硬件未放行'],
                 'navigation_title':['尺寸','取能','电路','联合','程序','验收'][i-1],
                 'figure': 'figures/'+stem+'.png', 'panels': panels}
        groups.append({'id':gid,'domain':domain,'kind':kind,'title':'D5 · '+title,'scope':scope,
                       'metrics':metric if gid=='joint' else {},'checks':result['checks'] if gid=='acceptance' else {},
                       'design_status':'insufficient_evidence','files':files,'evidence_story':story})
    manifest = {'schema_version':'bf-engineering-case-v1','id':'door-product-evidence','version':'D5-selfpower',
                'title':'门磁自供能 · D5 名义仿真参考','authority':'operator-assisted',
                'hardware_verified':False,'autonomous_agent_verified':False,'design_sha256':sha,'groups':groups}
    catalog = ProductResults(SimpleNamespace(store=Store(state)))
    saved = catalog.cases.publish(owner, output, manifest)
    write_json(output/'publication.json',{'owner':owner,'manifest':saved})
    return {'owner':owner,'groups':6,'files':sum(len(g['files']) for g in groups),'output':str(output),'status':status}


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    for k in ('run','figures','output','state'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--owner',required=True);p.add_argument('--audit',type=Path)
    a=p.parse_args();print(json.dumps(publish(a.run,a.figures,a.output,a.state,a.owner,a.audit),ensure_ascii=False))
