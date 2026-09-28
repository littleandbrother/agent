#!/usr/bin/env python3
"""Create plots and an operator publication receipt without changing verdicts."""
import argparse
import copy
import csv
import json
from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from bfworld.agentlab.pluck_case import digest

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--run-id',required=True);a=p.parse_args()
    run=a.home/'runs'/a.run_id
    receipt=copy.deepcopy(json.loads((run/'receipt.json').read_text()))
    for artifact in receipt['artifacts']:
        if digest(a.home/artifact['path'])!=artifact['sha256']:raise ValueError('BASE_ARTIFACT_MISMATCH')
    output=a.home/'presentation';output.mkdir(exist_ok=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
    rows=receipt['calibration']['paper_comparisons']
    fig,ax=plt.subplots(figsize=(8,4.5));x=list(range(len(rows)))
    ax.bar([v-.18 for v in x],[r['paper_voltage_v'] for r in rows],.36,label='Published experiment',color='#9ba6b4')
    ax.bar([v+.18 for v in x],[r['simulation_voltage_v'] or 0 for r in rows],.36,label='Local simulation',color='#315ea8')
    ax.set_xticks(x,[f"{r['interface'].upper()}\n{r['capacitance_uf']} uF" for r in rows]);ax.set_ylabel('Final storage voltage (V)');ax.legend(frameon=False)
    ax.set_title('Paper anchors vs local model — failures retained')
    fig.text(.02,.01,'Paper data: Tang et al. (2025), Table 3. Predeclared acceptance: 20% voltage error.',fontsize=8)
    fig.tight_layout(rect=(0,.04,1,1));fig.savefig(output/'paper-comparison.png');fig.savefig(output/'paper-comparison.pdf');plt.close(fig)
    for name in ('product','seh-47','sece-47'):
        trace=run/name/'trace.csv'
        if not trace.exists():continue
        samples=list(csv.DictReader(trace.read_text().splitlines()));t=[float(r['time_s']) for r in samples]
        fig,axes=plt.subplots(3,1,figsize=(8,6),sharex=True)
        for ax,columns,label in zip(axes,[['displacement_m'],['piezo_v','storage_v'],['output_v'] ],['Beam tip (mm)','Voltage (V)','Output rail (V)']):
            for column in columns:ax.plot(t,[float(r[column])*(1000 if column=='displacement_m' else 1) for r in samples],lw=1,label=column)
            ax.set_ylabel(label);ax.grid(alpha=.15);ax.legend(frameon=False,loc='upper right',fontsize=8)
        if name=='product':
            result=next(r['result'] for r in receipt['runs'] if r['id']=='product')
            for tx in result.get('tx_complete_times_s',[]):axes[-1].axvline(tx,color='#32806c',alpha=.25,lw=.6)
        axes[-1].set_xlabel('Time (s)');axes[0].set_title(name+' — coupled simulation, not hardware measurement')
        fig.tight_layout();fig.savefig(output/(name+'.png'));fig.savefig(output/(name+'.pdf'));plt.close(fig)
    # Reuse original editable board files as source references, not new validated PCB.
    circuit=a.home/'circuit-reference';circuit.mkdir(exist_ok=False)
    for folder in ('EEU/EEU_PSSHI','EMU/EMU_comparator'):
        for f in (a.home/'upstream'/folder).glob('*'):
            if f.suffix in ('.SchDoc','.PcbDoc'):shutil.copy2(f,circuit/f.name)
    (circuit/'README.md').write_text('Author ViPSN board references, commit 5a6b13f85c9ee8dfa40e231bae94218f9b562ac4.\nParallel SP-SSHI and comparator EMU. These are not the new SP-SECE board; no local EDA rule check, fabrication or hardware claim. Preserve upstream license.\n')
    for name in ('case.json','main.c','study-contract.json'):
        shutil.copyfile(ROOT/'configs/reference_cases/pluck-v1'/name,output/name)
    shutil.copyfile(ROOT/'docs/agentlab/PLUCK-REFERENCE-CASE.md',a.home/'README.md')
    shutil.copyfile(ROOT/'scripts/pluck_receiver.py',a.home/'firmware/receiver.py')
    base_paths={item['path'] for item in receipt['artifacts']}
    extras=list(output.glob('*'))+list(circuit.glob('*'))+list((a.home/'cad').glob('*'))+list((a.home/'firmware').glob('*'))+list((a.home/'firmware/_build').glob('*'))+[a.home/'README.md',a.home/'sources/ltc3588-1.pdf']
    for file in extras:
        if not file.is_file() or file.suffix in ('.o','.d','.class','.map'):continue
        rel=str(file.relative_to(a.home))
        if rel not in base_paths:
            receipt['artifacts'].append({'path':rel,'sha256':digest(file),'bytes':file.stat().st_size,'featured':file.name in ('README.md','model.glb','model.blend','preview.png','paper-comparison.pdf','receiver.py','s132_nrf52_3.0.0_softdevice.hex'),'kind':file.suffix.lstrip('.'),'label':file.name})
    receipt['publication']={'base_receipt_sha256':digest(run/'receipt.json'),'added':'plots, executable source references and engineering readbacks; no changed gate','coordinator_authored':True}
    receipt['evaluation']['reason']='当前数值校验与论文量值复现尚待全部通过；用户本轮选择纯仿真，实物连接与判向不作为事件检测仿真阶段的前置条件。'
    target=output/'published-receipt.json'
    target.write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    (a.home/'receipt.json').write_text(target.read_text())
    print(json.dumps({'artifact_count':len(receipt['artifacts']),'qualification':receipt['qualification'],'publication_sha256':digest(target)}))

if __name__=='__main__':main()
