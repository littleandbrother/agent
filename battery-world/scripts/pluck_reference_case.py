#!/usr/bin/env python3
"""Offline, bounded reference-case execution. Never launches an LLM.

Runs and protocol are immutable directories. --seal writes the operator-facing
receipt only after every attempted result and limitation has been recorded.
"""
import argparse
import copy
import csv
import gzip
import json
import math
import shutil
from pathlib import Path
import time

from bfworld.agentlab import pluck_case as engine

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--run-id',required=True);p.add_argument('--seal',action='store_true');a=p.parse_args()
    if not a.run_id.replace('-','').isalnum():p.error('run-id must be letters/digits/hyphens')
    case=json.loads((ROOT/'configs/reference_cases/pluck-v1/case.json').read_text())
    root=a.home/'runs'/a.run_id;root.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(engine.__file__,root/'engine-snapshot.py')
    shutil.copyfile(__file__,root/'runner-snapshot.py')
    started=time.monotonic();wall_seconds=1500
    protocol={'schema_version':'bf-pluck-case-protocol-v1','case':case,'engine_sha256':engine.digest(engine.__file__),'model_calls':0,'wall_seconds':wall_seconds,'stages':['source integrity','analytic checks','paper comparison','system simulation','negative controls','receiver'],'frozen_tolerances':case['acceptance'],'author':'engineering coordinator, not Pi'}
    protocol['runner_sha256']=engine.digest(__file__)
    (root/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
    sources=[]
    for s in case['sources']:
        path=a.home/'sources'/s['file'];sources.append({**s,'verified':path.exists() and path.read_bytes().startswith(b'%PDF-') and engine.digest(path)==s['sha256']})
    if not all(s['verified'] for s in sources):raise ValueError('SOURCE_IDENTITY_MISMATCH')
    # Potential gradient and curvature independently constrain magnetic polarity.
    m=case['mechanics'];q=.001;b=.005;gap=.026;eps=1e-7
    u0,f=engine.magnetic(q,b,m,gap);up=engine.magnetic(q+eps,b,m,gap)[0];um=engine.magnetic(q-eps,b,m,gap)[0]
    gradient_error=abs(f+(up-um)/(2*eps))/max(abs(f),1e-9)
    slope=(engine.magnetic(eps,0,m,gap)[1]-engine.magnetic(-eps,0,m,gap)[1])/(2*eps)
    results=[]
    jobs=[('seh-47','SEH · 47 µF',{},case),('seh-47-fine','SEH · 半步长',{'step':10e-6},case),('sece-47','SP-SECE · 47 µF',{'interface':'sece'},case),('sece-47-fine','SP-SECE · 半步长',{'interface':'sece','step':10e-6},case),('seh-330','SEH · 330 µF',{'capacitance_f':330e-6},case),('sece-330','SP-SECE · 330 µF',{'interface':'sece','capacitance_f':330e-6},case),('product','整机 · 24 mm 间距',{'interface':'sece','gap':.024,'loaded':True},case),('product-fine','整机 · 半步长',{'interface':'sece','gap':.024,'loaded':True,'step':10e-6},case),('zero','负对照 · 无机械输入',{'interface':'sece','motion_scale':0,'loaded':True},case),('low','负对照 · 弱磁耦合',{'interface':'sece','gap':.06,'loaded':True},case)]
    free=copy.deepcopy(case);free['motion']['duration_s']=.3
    jobs.append(('free','自由衰减 · 解析校验',{'interface':'open','motion_scale':0,'initial_deflection_m':.001},free))
    literal=copy.deepcopy(case);literal['mechanics']['magnetic_polarity']=1
    jobs.append(('polarity','公式正号解释 · 单列分支',{'interface':'seh'},literal))
    for name,label,params,c in jobs:
        if time.monotonic()-started>wall_seconds:raise TimeoutError('CASE_WALL_LIMIT')
        try:
            r=engine.run(c,root/name,**params)
            numeric=all(v for k,v in r['checks'].items() if k!='service' and v is not None)
        except Exception as error:
            r={'error':str(error),'checks':{'execution':False}};numeric=False
            (root/name/'result.json').write_text(json.dumps(r,indent=2))
        row={'id':name,'label':label,'result':r,'numeric_pass':numeric,'result_path':str((root/name/'result.json').relative_to(a.home))};results.append(row)
        (root/'running-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print(json.dumps({'id':name,'numeric':numeric,'peak_v':r.get('peak_storage_v'),'packets':len(r.get('tx_complete_times_s',[])),'error':r.get('error')},ensure_ascii=False),flush=True)
    by={r['id']:r['result'] for r in results}
    convergence={}
    for name in ('seh-47','sece-47','product'):
        x,y=by[name],by[name+'-fine'];vx=x.get('final_storage_v');vy=y.get('final_storage_v')
        error=abs(vx-vy)/max(abs(vy),1e-9) if vx is not None and vy is not None else None
        peak_error=abs(x['peak_storage_v']-y['peak_storage_v'])/max(abs(y['peak_storage_v']),1e-9) if vx is not None and vy is not None else None
        tx_x=x.get('tx_complete_times_s',[]);tx_y=y.get('tx_complete_times_s',[])
        packet_match=len(tx_x)==len(tx_y)
        first_tx_error=abs(tx_x[0]-tx_y[0])/max(tx_y[0],1e-9) if tx_x and tx_y else (0 if not tx_x and not tx_y else 1)
        convergence[name]={'relative_final_voltage_change':error,'relative_peak_voltage_change':peak_error,'packet_count_match':packet_match,'relative_first_tx_change':first_tx_error,'passed':error is not None and max(error,peak_error,first_tx_error)<case['acceptance']['numeric_relative_tolerance'] and packet_match and x['checks']['complete'] and y['checks']['complete']}
    alpha=m['damping_ns_m']/(2*m['mass_kg']);omega=math.sqrt((m['stiffness_n_m']+m['coupling_n_v']**2/m['piezo_capacitance_f'])/m['mass_kg']-alpha**2)
    free_error=0.0
    if (root/'free/channels.csv.gz').exists():
        with gzip.open(root/'free/channels.csv.gz','rt') as stream:
            for row in csv.DictReader(stream):
                t=float(row['time_s']);expected=.001*math.exp(-alpha*t)*(math.cos(omega*t)+alpha/omega*math.sin(omega*t));free_error=max(free_error,abs(float(row['displacement_m'])-expected)/.001)
    else:free_error=1.0
    comparisons=[]
    for cap in (47,330):
        anchor=next(x for x in case['paper_charging_anchors'] if x['c_uf']==cap)
        for interface in ('seh','sece'):
            r=by[f'{interface}-{cap}'];voltage=r.get('final_storage_v');target=anchor[interface+'_v'];error=abs(voltage-target)/target if voltage is not None else None
            comparisons.append({'interface':interface,'capacitance_uf':cap,'paper_voltage_v':target,'simulation_voltage_v':voltage,'relative_error':error,'within_declared_tolerance':error is not None and error<=case['acceptance']['paper_voltage_relative_tolerance'] and r['checks']['complete']})
    packets=by['product'].get('tx_complete_times_s',[]);received=engine.receive(packets);lost=engine.receive(packets,range(len(packets)))
    receiver={'events':received,'all_packets_lost_events':lost,'direction':'unknown','physical_reception_verified':False}
    (root/'receiver.json').write_text(json.dumps(receiver,indent=2))
    calibration={'magnetic_gradient_relative_error':gradient_error,'repulsive_local_force_slope_n_m':slope,'free_decay_max_normalized_error':free_error,'convergence':convergence,'paper_comparisons':comparisons,'scope':'numerical calibration plus held paper points; not new physical measurements'}
    (root/'calibration.json').write_text(json.dumps(calibration,indent=2))
    numeric=all(r['numeric_pass'] for r in results) and all(v['passed'] for v in convergence.values()) and gradient_error<1e-5 and slope>0 and free_error<.01
    agreement=all(x['within_declared_tolerance'] for x in comparisons)
    negative=not by['zero'].get('tx_complete_times_s',[1]) and not by['low'].get('tx_complete_times_s',[1]) and not lost
    firmware=a.home/'firmware/receipt.json';compiled=firmware.exists() and json.loads(firmware.read_text()).get('status')=='COMPILED'
    cad=a.home/'cad/cad-readback.json';cad_report=json.loads(cad.read_text()) if cad.exists() else {}
    gates=[{'label':'资料与身份','passed':True,'detail':'3 篇全文、版本、定位与哈希已绑定。'}, {'label':'数值校验','passed':numeric,'detail':'自由衰减解析解、磁力势能梯度、两档步长和能量平衡。'}, {'label':'论文储能点复现','passed':agreement,'detail':'固定 20% 电压容差；47 / 330 µF，SEH 与 SP-SECE 分别核对。'}, {'label':'固件构建','passed':compiled,'detail':'nRF52832 / S132 实际 HEX/BIN；尚未烧录和测量。'}, {'label':'事件服务仿真','passed':bool(received) and by['product'].get('checks',{}).get('service',False),'detail':'输入与输出双储能；完成 MCU 初始化、BLE 初始化、发包后才产生模拟接收。'}, {'label':'负对照','passed':negative,'detail':'无输入、弱耦合、全丢包不得产生成功事件。'}, {'label':'参考几何','passed':bool(cad_report.get('step_reopened_valid')) and not cad_report.get('collisions',[1]),'detail':'ViPSN 原始尺寸 STEP 参考；不套用为后两篇 MFC 的实物模型。'}, {'label':'方向与实物','passed':None,'detail':'判向分布、硬件接收、实际固件功耗尚未验证。'}]
    limitations=['磁力符号与原文极性描述存在解释差异；两种解释均保留，未静默更改。','SP-SECE 晶体管采用厂商参数的兼容子集，二极管及寄生参数仍有假设；尚无作者原始 LTspice 工程。','PMIC 是有输入/输出储能的行为模型，未复现开关纹波；负载是 ViPSN 论文测量替代，不是当前固件实测。','三篇配置分开：2021 Parallel SP-SSHI / 10µF；2025 SP-SECE / 470µH；2026 SP-SECE / 1mH。当前整机是明确标记的组合衍生设计。','CAD 为 2021 结构参考；2025/2026 的 MFC 叠层和完整制造尺寸仍待补齐。','方向保持 unknown；静默间隔分组可能合并相邻动作，不能凭仿真包数宣布方向识别成功。']
    receipt={'schema_version':'bf-pluck-case-receipt-v1','id':'pluck-v1','title':case['title'],'run_id':a.run_id,'summary':'参考工程与仿真结果已记录；完整校准准入尚待所有门槛通过。','gates':gates,'runs':results,'calibration':calibration,'sources':sources,'limitations':limitations,'hardware_verified':False,'model_calls':0,'evaluation':{**case['evaluation'],'reference_numeric_pass':numeric,'paper_agreement_pass':agreement,'dispatch_enabled':False,'reason':'方向、实际负载绑定及完整模型校准未封板；不进入正式 Agent/Harness 比较。'}}
    artifacts=[]
    candidates=list(root.rglob('*'))+[a.home/'sources'/s['file'] for s in case['sources']]+list((a.home/'firmware').glob('*.json'))+list((a.home/'firmware/_build').glob('*.hex'))+list((a.home/'firmware/_build').glob('*.bin'))+[a.home/'firmware/main.c']+list((a.home/'cad').glob('*'))+list((a.home/'comsol').glob('*'))
    for file in sorted(set(candidates)):
        if not file.is_file() or file.suffix in ('.class','.mphbin','.mphstatus') or file.name=='running-results.json':continue
        path=str(file.relative_to(a.home));featured=file.name in ('calibration.json','assembly.step','model.glb','preview.png','main.c','nrf52832_xxaa.hex','nrf52832_xxaa.bin','beam.mph') or file.suffix=='.pdf'
        artifacts.append({'path':path,'sha256':engine.digest(file),'bytes':file.stat().st_size,'featured':featured,'kind':file.suffix.lstrip('.'),'label':file.name})
    receipt['artifacts']=artifacts
    receipt['qualification']='QUALIFIED_SIMULATION_REFERENCE' if numeric and agreement and all(g['passed'] is not False for g in gates) else 'NOT_QUALIFIED'
    receipt['protocol_sha256']=engine.digest(root/'protocol.json')
    (root/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    if a.seal:(a.home/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps({'output':str(root),'numeric':numeric,'paper_agreement':agreement,'hardware':False,'formal_agent_dispatch':False}),flush=True)

if __name__=='__main__':main()
