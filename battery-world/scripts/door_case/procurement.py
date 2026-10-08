"""Build a catalogue-backed, explicitly unqualified electronics revision.

The radio module is a new footprint, not a drop-in BOM substitution. Geometry
is derived from the Ebyte manual p.4, top-view pin numbering, rotated 90deg.
Library metadata readback is recorded separately from unavailable native ERC/DRC.
"""
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
if __package__:
    from .board import uid, MIL
else:
    from board import uid, MIL

PIN_NAMES = {0:'GND',1:'GND',2:'GND',3:'DEC2',4:'DEC3',12:'DEC4',13:'DCC',14:'DEC1',15:'GND',16:'VCC',37:'SWDCLK',38:'SWDIO',42:'GND',43:'GND'}
PIN_NAMES.update({i:f'P0.{i+20:02d}' for i in range(5,12)})
PIN_NAMES.update({i:f'P0.{i-15:02d}' for i in range(17,37)})
PIN_NAMES.update({39:'P0.22',40:'P0.23',41:'P0.24'})


def module_pads():
    pads=[]
    for num in range(44):
        if 16 <= num <= 27:
            x,y=6.98-(num-16)*1.27,13.75
            w,h=.65,1.20
        elif num <= 15:
            x=8.15
            y=12.60-(15-num)*1.27 if num>=2 else (-6.45 if num==1 else -7.72)
            w,h=1.20,.65
        else:
            x=-8.15
            y=12.60-(num-28)*1.27 if num<=41 else (-6.45 if num==42 else -7.72)
            w,h=1.20,.65
        pads.append(dict(id='pad-'+str(num),num=str(num),centerX=-y/MIL,centerY=x/MIL,padAngle=0,
                         defaultPad=dict(padType='RECT',width=h/MIL,height=w/MIL),layerId=1,plated=False))
    return pads


def seed(root, output):
    libs=output/'circuit/libraries';libs.mkdir(parents=True,exist_ok=True)
    for code in ['C685115','C555369','C15849','C19666','C15008','C14663','C503307']:
        shutil.copytree(root/'circuit/libraries'/code,libs/code,dirs_exist_ok=True)
    for source,target,mpn,value in [('C685115','C685122','LTC3588IMSE-1#TRPBF',''),('C14663','C14858','CL10C101JB8NNNC','100pF')]:
        shutil.copytree(libs/source,libs/target,dirs_exist_ok=True)
        file=libs/target/'device2.json';info=json.loads(file.read_text());dev=next(iter(info['devices'].values()))
        dev['uuid']=uid(target+'reviewed-device');a=dev['attributes'];a.update({'Manufacturer Part':mpn,'Supplier Part':target,'Value':value or a.get('Value','')})
        info['devices']={dev['uuid']:dev};file.write_text(json.dumps(info,indent=2))
    folder=libs/'C411306';folder.mkdir(exist_ok=True)
    attrs={'Manufacturer Part':'E73-2G4M04S1B','Manufacturer':'EBYTE','Supplier Part':'C411306',
           'Symbol':uid('D3-E73-symbol'),'Footprint':uid('D3-E73-manual-footprint-90deg'),
           'Datasheet':'https://www.cdebyte.com/pdf-down.aspx?id=2984','Value':'nRF52832 module'}
    device=uid('D3-E73-reviewed-device');(folder/'device2.json').write_text(json.dumps({'devices':{device:{'uuid':device,'attributes':attrs}}},indent=2))
    records=[({'type':'DOCHEAD'},{'docType':'SYMBOL','uuid':attrs['Symbol'],'editVersion':'3.2.148'}),
             ({'type':'PART','id':'E73.1'},{'title':'E73.1','BBOX':[-20,-10,20,900]})]
    for num,name in PIN_NAMES.items():
        pin='pin-'+str(num);records.append(({'type':'PIN','id':pin},{'partId':'E73.1','x':-30,'y':num*20,'length':10,'rotation':0,'display':True}))
        for key,value in [('Pin Number',str(num)),('Pin Name',name)]:records.append(({'type':'ATTR','id':pin+key},{'parentId':pin,'key':key,'value':value}))
    records.append(({'type':'DOCHEAD'},{'docType':'FOOTPRINT','uuid':attrs['Footprint'],'editVersion':'3.2.148'}))
    for p in module_pads():records.append(({'type':'PAD','id':p['id']},{k:v for k,v in p.items() if k!='id'}))
    (folder/'ProLib_pc_2026-09-29.elibu').write_text('\n'.join(json.dumps(h)+'||'+json.dumps(v)+'|' for h,v in records))
    receipt={'source':'Ebyte E73-2G4M04S1B User Manual, dimensional figure p.4','source_sha256':hashlib.sha256((root/'procurement/20261003/E73-vendor.pdf').read_bytes()).hexdigest(),
             'pad_count':44,'module_body_mm':[28.7,17.5,2.6],'rotation_deg':90,'land_size_mm':[1.2,.65],
             'pad_pitch_mm':1.27,'native_library_footprint_readback':False,'native_erc':None,'native_drc':None,
             'scope':'Manual-derived rectangular lands with shortened inner extension (1.2 vs 1.5 mm vendor bottom pad), retaining 0.65 mm castellated width; native library export and land-pattern fabrication review pending.', 'decoupling_reference':'https://docs.nordicsemi.com/r/bundle/ps_nrf52832/page/ref_circuitry.html', 'DEC2':'Unconnected for QFAA; Nordic reference C6 is not mounted.'}
    (output/'footprint-provenance.json').write_text(json.dumps(receipt,indent=2))
    parts=[['U1','C685122',24,15],['U2','C411306',63,15],['C1','C555369',18,9],['C2','C15849',24,10],['C3','C19666',25,20],['C4','C15008',34,17],['C5','C14663',45,23],['L1','C503307',29,11],['C6','C14663',50,27],['C7','C15849',54,27],['C9','C14858',63,27]]
    nets={'U1':{'1':'PZ1','2':'PZ2','3':'CAP','4':'VIN','5':'SW','6':'VOUT','7':'VIN2','8':'VIN2','9':'GND','10':'PGOOD','11':'GND'},
          'U2':{'0':'GND','1':'GND','2':'GND','4':'DEC3','12':'DEC4','14':'DEC1','15':'GND','16':'VOUT','26':'PGOOD','27':'DEBUG','37':'SWDCLK','38':'SWDIO','42':'GND','43':'GND'},
          'C1':{'1':'VIN','2':'GND'},'C2':{'1':'CAP','2':'VIN'},'C3':{'1':'VIN2','2':'GND'},'C4':{'1':'VOUT','2':'GND'},'C5':{'1':'VOUT','2':'GND'},'L1':{'1':'SW','2':'VOUT'},
          'C6':{'1':'DEC1','2':'GND'},'C7':{'1':'DEC4','2':'GND'},'C9':{'1':'DEC3','2':'GND'},
          'J1':{'1':'PZ1','2':'PZ2'},'J2':{'1':'VOUT','2':'GND','3':'SWDIO','4':'SWDCLK'},'J3':{'1':'DEBUG','2':'GND'}}
    definition=dict(design='door-magnetic-D3-electronics',components=parts,nets=nets,headers=[['J1',2,11,15],['J2',4,44,6],['J3',2,44,14]],
                    header_parts={r:{'lcsc':c,'mpn':m} for r,c,m in [('J1','C124375','B-2100S02P-A110'),('J2','C124378','B-2100S04P-A110'),('J3','C124375','B-2100S02P-A110')]},
                    rf_keepout_mm=[72.35,5.5,80,24.5],rf_notch_mm=[0,0,0,0],scope='Electronics procurement revision; same 80x30 outline, radio package changed. Mechanical stack-up, RF and native ERC/DRC remain unqualified.')
    (output/'definition.json').write_text(json.dumps(definition,indent=2))
    print(json.dumps({'output':str(output),'parts':len(parts)+3,'source':'datasheet + catalogue + recorded library exports'}))


def catalogue_record(folder, code):
    path = folder / (code + '-jlc.json')
    if not path.exists():
        path = folder / 'header-2pin-jlc.json'
    snapshot = json.loads(path.read_text())
    matches = [r for r in snapshot['response'] if r.get('componentCode') == code]
    if len(matches) != 1:
        raise ValueError('CATALOGUE_ID_NOT_UNIQUE: ' + code)
    return snapshot, matches[0], path


def build_bom(root, output):
    board = json.loads((output/'pcb/board.json').read_text())
    groups = {}
    for part in board['components']:
        groups.setdefault(part['lcsc'], []).append(part)
    rows, audit = [], []
    for code, parts in groups.items():
        snapshot, record, path = catalogue_record(root/'procurement/20261003', code)
        mpn = parts[0]['attrs']['Manufacturer Part']
        if record['componentModelEn'] != mpn:
            raise ValueError('BOM_MPN_MISMATCH: ' + code)
        stock = int(record['stockCount'])
        if stock < len(parts):
            raise ValueError('BOM_INSUFFICIENT_STOCK: ' + code)
        datasheet = ('https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf'
                     if code == 'C685122' else 'https://www.cdebyte.com/pdf-down.aspx?id=2984'
                     if code == 'C411306' else 'https://www.bourns.com/docs/product-datasheets/srn4018.pdf'
                     if code == 'C503307' else record.get('dataManualUrl', ''))
        catalogue_url = record.get('lcscGoodsUrl') or ('https://jlcpcb.com/partdetail/'+record['urlSuffix'] if record.get('urlSuffix') else '')
        rows.append([','.join(p['ref'] for p in parts), len(parts), mpn, code,
                     record['componentBrandEn'], record['componentSpecificationEn'],
                     record['describe'], stock, snapshot['checked_at'],
                     '现货目录；贴片服务资格待确认', catalogue_url, datasheet])
        audit.append(dict(code=code, mpn=mpn, quantity=len(parts), stock=stock,
                          checked_at=snapshot['checked_at'], source=snapshot.get('source','https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList'),
                          source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          assemblyComponentFlag=record.get('assemblyComponentFlag'),
                          catalogue_package=record['componentSpecificationEn']))
    folder = output/'bom';folder.mkdir(exist_ok=True)
    with (folder/'bom-jlc.csv').open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['位号','数量','制造商型号','嘉立创编号','制造商','封装','规格','查询库存','查询时间UTC','采购状态','目录链接','数据手册'])
        writer.writerows(rows)
    receipt = dict(schema='door-procurement-v1', design=board['design'],
                   unique_parts=len(rows), fitted_parts=sum(r[1] for r in rows),
                   catalogue_available_for_one_board=True, assembly_qualified=False,
                   purchase_placed=False, native_drc=None, manufacturing_released=False,
                   records=audit, replacements=[
                       dict(old='C685115',new='C685122',reason='Old PMIC catalogue stock zero; same MSOP-10-EP pinout, different temperature grade.'),
                       dict(old='C2828282',new='C411306',reason='Old module catalogue stock zero; same SoC family, different 44-pad package: layout and BOM rebuilt. Not drop-in, RF and target validation pending.')])
    (folder/'procurement-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('case',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--bom',action='store_true')
    args=parser.parse_args()
    if args.bom:print(json.dumps(build_bom(args.case,args.output),ensure_ascii=False))
    else:seed(args.case,args.output)
