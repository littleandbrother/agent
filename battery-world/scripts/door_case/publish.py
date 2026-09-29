"""Bind this immutable engineering version to an existing, explicitly named owner."""
import argparse,hashlib,json
from pathlib import Path
from types import SimpleNamespace
from bfworld.agentlab.store import Store
from bfworld.agentlab.product_results import ProductResults

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--owner',required=True);a=p.parse_args();r=a.root
    groups=[]
    def group(id,domain,kind,title,scope,paths,status=None,metrics=None):
        files=[]
        for path in paths:
            f=r/path
            if not f.is_file():raise FileNotFoundError(f)
            files.append({'path':path,'name':path.replace('/','--'),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
        groups.append(dict(id=id,domain=domain,kind=kind,title=title,scope=scope,design_status=status,metrics=metrics or {},files=files))
    group('installation','mechanical','blender','D2 · 开门动画与安装展示','与 CAD 同尺寸；规定门角动画，不代表柔性动力学求解',
        ['animation-D2/'+f for f in ['door-opening.mp4','door-installation.blend','door-animation.glb','installation.png','mechanism.png','mechanism-door-open.png']])
    group('cad','mechanical','cadquery','D2 · 原生 CAD 与 22 张图纸','实体和离散刚体间距已检查；加工公差与连续扫掠未完成',
        ['mechanical-D2/assembly.step','mechanical-D2/installation.step','mechanical-D2/input.json','mechanical-D2/native_builder.py','mechanical-D2/cad-readback.json','mechanical-D2/motion-clearance.json','mechanical-D2/bom.csv']+
        [str(f.relative_to(r)) for f in sorted((r/'mechanical-D2/drawings').glob('*.pdf'))],metrics={'parts':22,'minimum_sampled_clearance_mm':20.656382016745283})
    group('fem','mechanical','comsol','D2 · COMSOL 应力、位移与磁场','实际原生场图；磁力网格最大差约 7.65%，未达到 5% 门槛',
        [f'simulation/beam-v4/{f}' for f in ['stress.png','displacement.png','stress.glb','displacement.glb','model-with-plots.mph','DoorBeam.java','native-receipt.json','plot-receipt.json','solver.log']]+
        [f'simulation/magnetic-D2-final/{f}' for f in ['field.png','field.glb','model-with-plots.mph','DoorMagnetic.java','native-receipt.json','plot-receipt.json','solver.log']],status='FAIL')
    group('rom','mechanical','beam-event','D2 · 门动作与机电计算','受载荷影响的线性降阶模型；没有物理标定',
        ['report/figures/coupled.png']+[str(f.relative_to(r)) for f in sorted((r/'simulation/coupled-D2').glob('*')) if f.is_file()],
        metrics={'normal_resistor_energy_uJ':11.0609135732,'slow_resistor_energy_uJ':1.21786003})
    group('power','circuit','spice','D2 · 电源电路与冷启动结果','ADI 宏模型真实执行；单次开门冷启动失败，当前仅单向机电耦合',
        ['report/figures/power.png','report/power-summary.json']+[str(f.relative_to(r)) for f in sorted((r/'circuit/ltspice-D2').rglob('*')) if f.is_file() and f.suffix in ['.cir','.raw','.csv','.pwl','.log','.sub','.json']],status='FAIL',metrics={'VIN_peak_V':.1355317831,'startup':False})
    group('pcb','circuit','jlceda','D2 · 原理图、实际布线与 PCB','独立检查无断网/间距违规；原生 EDA ERC/DRC 未执行，制造草案',
        [f'pcb/D2/{f}' for f in ['schematic.png','pcb-combined.png','pcb-top.png','pcb-bottom.png','schematic.pdf','pcb-combined.pdf','door-D2.epro2','door-D2.epru','door.dsn','door.ses','bom.csv','routing-checks.json','native-import-receipt.json','board.json']]+
        [str(f.relative_to(r)) for f in sorted((r/'pcb/D2/gerber-draft').glob('*')) if f.is_file()],
        metrics={'pads':72,'tracks':68,'vias':12,'native_DRC':None})
    group('firmware','firmware','mcu-firmware','D2 · nRF52832 固件与时序','目标编译和重复构建通过；未烧录、未测功耗时延、未无线接收',
        ['report/figures/firmware-sequence.png']+[f'firmware-D2-release/{f}' for f in ['main.c','firmware.elf','_build/nrf52832_xxaa.hex','_build/nrf52832_xxaa.bin','s132_nrf52_3.0.0_softdevice.hex','FLASH.md','flash_pluck_firmware.py','pluck_receiver.py','resources.json','receipt.json','reproducibility.json','receiver-check.json','receiver-fixture.jsonl']],
        metrics={'application_flash_bytes':4896,'static_RAM_bytes':180,'hardware_measured':False})
    group('report','system','engineering-report','D2 · 完整报告与工程包','完整数字工程基线；整机验收未通过。操作者辅助，非 Pi 独立交付证据',
        ['report/door-case.pdf','report/door-case.tex','report/verification.json','report/figure-provenance.json','door-magnetic-D2-engineering.zip','case-files.json','package-receipt.json','reproduction/README.md'],status='FAIL')
    m={'schema_version':'bf-engineering-case-v1','id':'door-magnetic','version':'D2','authority':'operator-assisted','hardware_verified':False,'autonomous_agent_verified':False,'design_sha256':hashlib.sha256((r/'requirements/design-D2.json').read_bytes()).hexdigest(),'groups':groups}
    store=Store(a.state);catalog=ProductResults(SimpleNamespace(store=store));saved=catalog.cases.publish(a.owner,r,m)
    (r/'publication.json').write_text(json.dumps({'owner':a.owner,'manifest':saved},ensure_ascii=False,indent=2))
    _,files,_=catalog.cases.collect(a.owner);assert all(f['integrity'] for f in files)
    print(json.dumps({'owner':a.owner,'groups':len(groups),'files':len(files),'integrity':True}))
if __name__=='__main__':main()
