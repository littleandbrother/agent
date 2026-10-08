"""Publish a distinct catalogue-sourced electronics draft to a named owner.

No old seal, Agent assembly, or acceptance result is modified. Native checks
and current sourcing evidence remain independently inspectable.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

from bfworld.agentlab.store import Store
from bfworld.agentlab.product_results import ProductResults


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--owner', required=True)
    p.add_argument('--version', required=True)
    a=p.parse_args();root=a.root;revision=root/'electronics-D3'
    board=json.loads((revision/'pcb/board.json').read_text())
    routing=json.loads((revision/'pcb/routing-checks.json').read_text())
    supply=json.loads((revision/'power/report.json').read_text())
    sourcing=json.loads((revision/'bom/procurement-receipt.json').read_text())
    if routing['unconnected'] or routing['clearance_violations'] or routing['antenna_keepout_violations']:
        raise ValueError('DRAFT_ROUTING_CHECK_FAILED')
    if not sourcing['catalogue_available_for_one_board']:
        raise ValueError('PROCUREMENT_NOT_AVAILABLE')
    groups=[]
    def group(key,kind,title,scope,paths,**extra):
        files=[]
        for rel in paths:
            path=root/rel
            files.append(dict(path=rel,name=rel.replace('/','--'),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        groups.append(dict(id=key,domain='circuit',kind=kind,title=title,scope=scope,files=files,**extra))
    prefix='electronics-D3/'
    group('schematic','jlceda','D3 · 完整电源与无线原理图',
          '同一网表的引脚—网络复核；LTC3588-1 3.3 V / E73-2G4M04S1B LDO。原生 ERC 未执行。',
          [prefix+'pcb/'+f for f in ['schematic.png','schematic.svg','schematic.pdf','schematic-checks.json']]+[prefix+'definition.json'],
          checks={'引脚与PCB网表一致':True,'原生ERC':None})
    group('pcb','jlceda','D3 · 双面真实布线与工程交换文件',
          '80×30 mm，实际 Freerouting 铜线与铺铜；独立二维检查通过。模块焊盘手册衍生，内侧延伸缩短以消除转角冲突；待原生封装、ERC/DRC、贴合与RF审核，禁止投板。',
          [prefix+'pcb/'+f for f in ['pcb-combined.png','pcb-top.png','pcb-bottom.png','pcb-combined.svg','pcb-top.svg','pcb-bottom.svg','pcb-combined.pdf','pcb-top.pdf','pcb-bottom.pdf','door-magnetic-D3-electronics.epro2','door-magnetic-D3-electronics.epru','door.dsn','door.ses','board.json','routed-copper.json','routing-checks.json','router.log']]+[prefix+'footprint-provenance.json']+
          [str(f.relative_to(root)) for f in sorted((revision/'pcb/gerber-draft').glob('*'))],
          checks={'网络连通':True,'独立二维铜间距':True,'天线禁布区':True,'原生DRC':None,'制造放行':False},
          metrics={k:routing[k] for k in ['pads','tracks','vias','minimum_clearance_mm','minimum_trace_width_mm']})
    group('power','spice','D3 · 三工况原生 LTspice 波形',
          '本次 ADI 宏模型复算；零初始储能，47 µF 输入 / 100 µF 输出，14 mA TX负载包络。三个工况冷启动失败。采用沿用D2的单向ROM输入，不替代后续双向联合模型、程序能耗或硬件标定。',
          [str(f.relative_to(root)) for f in sorted((revision/'power').rglob('*')) if f.is_file()],
          design_status='FAIL',checks={'原生求解完成':True,'冷启动达到':False,'硬件校准':False},
          metrics={'VIN_peak_V':supply['cases']['nominal']['storage_peak'],'peak_supply_V':supply['cases']['nominal']['output_peak'],'tx_completed':0},
          inputs={'initial_storage_V':0,'Cin_uF':47,'Cout_uF':100,'load_A':.014,'inductor_dcr_ohm':supply.get('inductor_dcr_ohm',.4),'source':'unchanged D2 mechanical ROM'})
    group('bom','bom','D3 · 嘉立创现货 BOM 与查询凭据',
          '11种料号、14个装配件；2026-10-03目录库存快照，仅覆盖一块样机。PMIC库存4个。库存可用不等于贴片服务资格；未下单，制造未放行。',
          [prefix+'bom/bom-jlc.csv',prefix+'bom/procurement-receipt.json']+
          [str(f.relative_to(root)) for f in sorted((root/'procurement/20261003').glob('*-jlc.json')) if f.name!='C358713-jlc.json']+
          ['procurement/20261003/E73-vendor.pdf','procurement/20261003/E73-dimensions.png','procurement/20261003/SRN4018-vendor.pdf'],
          checks={'逐项料号与型号匹配':True,'一块样机查询库存足够':True,'贴片服务资格':None,'已下单':False},
          metrics={'unique_parts':11,'fitted_parts':14})
    # Retain original mechanical field evidence with an explicit unchanged-source
    # boundary. It never certifies the new module's stack-up or new electronics.
    group('fem-reference','comsol','D2机械基线 · COMSOL场图参考',
          '沿用原D2机械场图：原生应力/位移/磁场已求解；磁场网格差7.65%未达5%门槛。电子修订未重新装配或进行机械场求解。',
          ['simulation/beam-v4/'+f for f in ['stress.png','displacement.png','stress.glb','displacement.glb','model-with-plots.mph','native-receipt.json']]+
          ['simulation/magnetic-D2-final/'+f for f in ['field.png','field.glb','model-with-plots.mph','native-receipt.json']],
          design_status='FAIL',checks={'磁场网格门槛':False})
    groups[-1]['domain']='mechanical'
    manifest=dict(schema_version='bf-engineering-case-v1',id='door-magnetic',version=a.version,
                  title='磁耦合门磁 · 电路采购修订',authority='operator-assisted',hardware_verified=False,
                  autonomous_agent_verified=False,design_sha256=hashlib.sha256((revision/'definition.json').read_bytes()).hexdigest(),groups=groups)
    (revision/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    archive=revision/'electronics-D3-engineering-draft.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(revision.rglob('*')):
            if file.is_file() and file!=archive and file.name!='publication.json':
                z.write(file,file.relative_to(revision))
        # Sourcing/footprint provenance must remain verifiable after downloading
        # just this electronics package, without the operator's source folders.
        for g in groups:
            if g['id']=='bom':
                for f in g['files']:
                    if not f['path'].startswith(prefix):
                        z.write(root/f['path'],'references/'+f['path'])
    group('delivery','engineering-report','D3 · 修订说明与完整电子工程包',
          '含图纸、实际布线、BOM、原生电路波形及复算源；工程草案，未整机验收，非Pi自主交付。原D2机械、固件和完整报告保留为独立历史版本。',
          [prefix+'README.md',prefix+'electronics-D3-engineering-draft.zip',prefix+'delivery-manifest.json'])
    groups[-1]['domain']='system'
    catalog=ProductResults(SimpleNamespace(store=Store(a.state)))
    saved=catalog.cases.publish(a.owner,root,manifest)
    _,files,_=catalog.cases.collect(a.owner)
    chosen=[f for f in files if f['case_version']==a.version]
    if not all(f['integrity'] for f in chosen):raise ValueError('PUBLISHED_READBACK_FAILED')
    receipt=dict(owner=a.owner,files=len(chosen),groups=len(groups),integrity=True,
                 manifest_sha256=hashlib.sha256(json.dumps(saved,sort_keys=True).encode()).hexdigest(),
                 autonomous_agent_verified=False,manufacturing_released=False)
    (revision/'publication.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))


if __name__=='__main__':main()
