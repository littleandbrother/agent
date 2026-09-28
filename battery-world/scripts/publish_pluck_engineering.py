#!/usr/bin/env python3
"""Seal an explicitly incomplete engineering snapshot and operator-only view."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--version',default='engineering-v1')
    args=parser.parse_args()
    case=args.case.resolve();work=case/'delivery/work';out=case/'delivery'/args.version
    out.mkdir(parents=True,exist_ok=False)
    contract=json.loads((ROOT/'configs/reference_cases/engineering-delivery-v1.json').read_text())
    maps={'cad-v2':2,'clearance-v2':2,'animation-v2':2,'comsol-coupled-v1':3,'comsol-transient-v2':3,
          'ltspice-3v3-v1':4,'pmic-comparison-v1':4,'firmware-v3':6,'receiver-v1':7,'matrix-v1':8,'native-plots-v1':10}
    files=[]
    for folder,index in maps.items():
        for source in sorted((work/folder).rglob('*')):
            if source.is_file() and not source.is_symlink() and source.suffix not in ('.status','.lock'):
                files.append({'path':str(source.relative_to(case)), 'archive_path':contract['directories'][index]+'/'+folder+'/'+str(source.relative_to(work/folder)), 'sha256':sha(source),'bytes':source.stat().st_size})
    for source in sorted((case/'sources').glob('*.pdf')):
        files.append({'path':str(source.relative_to(case)),'archive_path':contract['directories'][1]+'/'+source.name,'sha256':sha(source),'bytes':source.stat().st_size})
    for name in ['plot_pluck_native_results.py','plot_pluck_ltspice.py','compare_pluck_pmic.py','run_pluck_ltspice.py','publish_pluck_engineering.py']:
        shutil.copy2(ROOT/'scripts'/name,out/name)
    (out/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2))
    (out/'manifest.json').write_text(json.dumps({'files':files,'complete':False,'hardware_verified':False},ensure_ascii=False,indent=2))
    readme='''# 拨动压电产品：仿真阶段工程快照

此包包含可打开的 COMSOL、STEP、Blender、LTspice 网表、nRF52832 编译产物、接收端与原始计算记录。它不是已校准、可制造或已烧录的最终产品。

## 本次实际求解
- COMSOL 6.2：三维铜梁、假定 PZT-5A 压电层、磁体质量及电阻负载。静态、模态、两档电阻扫频、0.4 s 瞬态已经求解；原生 MPH 保留结果。
- LTspice 26.0.2：官方 LTC3588-1 模型，3.3 V 档，47 uF 输入/输出电容。持续输入、1 s 输入和零输入都有独立网表、原始波形和原生测量。
- ngspice：同一预设输入下对照现有平均降压模型；原参考参数没有被改写。

## 结果与边界
1 mN 静载最大位移 12.54 um，一阶模态 15.93 Hz，两档静态网格位移差 0.88%。10 mN 高斯脉冲、100 kohm 下，0.4 s 内电阻获得约 71 nJ。此脉冲不是磁拨动门运动。
200 uA、100 Hz 理想输入持续供能时，LTspice 输出约 2.333 s 达到 3.2 V；只输入 1 s 则不启动。与平均模型对照，启动相差约 61 ms、负载能量约 6.8%。这些是模块对照，不能替代压电源阻抗与电路双向耦合。

## 未完成项
磁力有限元/实验标定；完整瞬态与应力收敛；PZT 实际材料与粘接层；论文 SECE 复现差异；原生立创完整原理图/PCB/ERC/DRC/Gerber；制造公差与全运动干涉；实物烧录及功耗、无线、方向校准。不得从本快照产生最终交付通过声明。

## 打开和复算
COMSOL 打开 coupled_Model.mph 或 transient_Model.mph。各目录的 Java/Python、protocol.json、solver.log 保留建模输入和计算依据。
LTspice 打开 continuous、one-second-burst、zero 下的 power.cir，使用官方 LTC3588-1 库；原始 power.raw 可直接打开。需安装对应工具和许可证。
固件需 receipt.json 指定的 Nordic SDK、S132 和 ARM 工具链；当前两次本机干净构建 HEX/BIN 一致，但不等于已验证任意新机器独立构建。
manifest.json 核对源路径、ZIP 内路径、字节数和 SHA-256。查看 contract.json 中每项最终验收要求。原始失败运行仍保留在案例目录，不因发布本快照被删除。
'''
    (out/'README.md').write_text(readme)
    task_files={'cad':['cad-v2'],'drawings':['cad-v2'],'clearance':['clearance-v2'],'presentation':['cad-v2','animation-v2'],
        'fem':['comsol-coupled-v1','comsol-transient-v2'],'convergence':['comsol-coupled-v1'],
        'spice':['ltspice-3v3-v1','pmic-comparison-v1'],'firmware':['firmware-v3'],'firmware-resources':['firmware-v3'],'flash-guide':['firmware-v3'],
        'receiver':['receiver-v1'],'direction':['receiver-v1'],'receiver-tests':['receiver-v1'],'joint':['matrix-v1'],'matrix':['matrix-v1'],'raw-data':['matrix-v1'],'figures':['native-plots-v1']}
    tasks=[]
    for task in contract['tasks']:
        selected=[f for f in files if any('/'+folder+'/' in f['path'] for folder in task_files.get(task['id'],[]))]
        tasks.append({**task,'delivery_status':'partial' if selected else 'missing','validation_status':'not_run',
            'validation_reason':'已有本机计算或工程产物；未满足此任务完整验收标准。' if selected else '本快照未登记符合最终标准的任务文件。',
            'files':selected,'missing_files':[]})
    (out/'acceptance-status.json').write_text(json.dumps({'complete':False,'tasks':tasks},ensure_ascii=False,indent=2))
    archive=out/'engineering-snapshot.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=2) as z:
        z.write(out/'README.md','README.md')
        for folder in contract['directories']:
            z.writestr(folder+'/STATUS.md','此目录是未完成工程快照的一部分；以根 README、contract.json 和 acceptance-status.json 的验收状态为准。\n')
        for item in files:
            source=case/item['path']
            if sha(source)!=item['sha256']:raise ValueError('SOURCE_CHANGED_DURING_PACKAGE')
            z.write(source,item['archive_path'])
        for source in sorted(out.iterdir()):
            if source.is_file() and source!=archive:z.write(source,contract['directories'][11]+'/'+source.name)
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad:raise ValueError('ZIP_CRC_FAILED:'+bad)
        for item in files:
            with z.open(item['archive_path']) as f:
                h=hashlib.file_digest(f,'sha256').hexdigest()
            if h!=item['sha256']:raise ValueError('ZIP_READBACK_FAILED')
    prefix='delivery/work/'
    native=[{'title':'COMSOL 三维压电与电路耦合','result':'一阶模态 15.93 Hz；1 mN 静载位移 12.54 µm；两档静态网格差 0.88%。',
        'scope':'假定 PZT-5A 候选；尚未完成磁拨动、粘接层及完整收敛校准。','figure':prefix+'native-plots-v1/comsol-frequency.png',
        'files':[{'path':prefix+'comsol-coupled-v1/coupled_Model.mph','label':'COMSOL 原生模型（约 82 MB）'},{'path':prefix+'comsol-coupled-v1/report.json','label':'扫频与网格结果'}]},
        {'title':'COMSOL 瞬态','result':'10 mN 测试脉冲：峰值电压 0.203 V、梁端位移 95 µm、0.4 s 负载能量约 71 nJ。',
        'scope':'预设脉冲，不是门运动；未完成时间步收敛。','figure':prefix+'native-plots-v1/comsol-transient.png',
        'files':[{'path':prefix+'comsol-transient-v2/transient_Model.mph','label':'瞬态原生模型（约 484 MB）'},{'path':prefix+'comsol-transient-v2/report.json','label':'瞬态结果'}]},
        {'title':'LTspice 官方 LTC3588-1 模型','result':'持续供能约 2.333 s 启动；1 s 短时供能与零输入均不启动。与平均模型启动相差 61 ms、负载能量相差约 6.8%。',
        'scope':'200 µA / 100 Hz 预设输入；模块模型对照，尚未与磁拨动动力学闭环。','figure':prefix+'ltspice-3v3-v1/ltspice-startup.png',
        'files':[{'path':prefix+'ltspice-3v3-v1/continuous/power.cir','label':'LTspice 可运行网表'},{'path':prefix+'ltspice-3v3-v1/report.json','label':'三工况结果'},{'path':prefix+'pmic-comparison-v1/report.json','label':'ngspice 对照'}]}]
    artifacts=[{'path':f['path'],'sha256':f['sha256'],'label':Path(f['path']).name,'kind':'engineering-evidence','featured':False} for f in files]
    for source,kind,label in [(archive,'engineering-package','仿真阶段工程快照 · 未完成最终验收'),(out/'README.md','engineering-guide','本次结果与未完成项')]:
        artifacts.append({'path':str(source.relative_to(case)),'sha256':sha(source),'kind':kind,'label':label,'featured':True})
    report={'version':args.version,'complete':False,'hardware_verified':False,'contract':contract,'tasks':tasks,'native_simulations':native,
        'summary':'已取得 COMSOL 与官方 LTspice 的真实求解结果；本包仍未完成校准、制造及实物验收。','artifacts':artifacts,
        'archive_readback':{'crc':True,'all_source_hashes':True,'files':len(files)}}
    receipt=out/'report.json';receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    temp=case/'delivery/latest.tmp';temp.write_text(json.dumps({'path':str(receipt.relative_to(case)),'sha256':sha(receipt)},indent=2));temp.replace(case/'delivery/latest.json')
    print(json.dumps({'report':str(receipt),'archive':str(archive),'bytes':archive.stat().st_size,'files':len(files),'complete':False}))


if __name__=='__main__':main()
