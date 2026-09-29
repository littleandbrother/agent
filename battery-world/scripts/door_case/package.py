"""Bundle a versioned engineering case, without upgrading its failed verdict."""
import argparse,hashlib,importlib.util,json,shutil,zipfile
from pathlib import Path
APP=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();r=a.root
    source=r/'reproduction/source'
    for rel in ['scripts/door_case','configs/reference_cases/door-magnetic-v1']:
        shutil.copytree(APP/rel,source/rel,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for rel in ['scripts/build_pluck_product.py','scripts/flash_pluck_firmware.py','scripts/pluck_receiver.py','packages/python/bfworld/src/bfworld/agentlab/engineering_templates/product_cad.py']:
        dst=source/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(APP/rel,dst)
    previous=r.parent/'pluck-v1';refs=r/'sources/papers';refs.mkdir(parents=True,exist_ok=True)
    for f in (previous/'sources').glob('*'):
        if f.is_file() and f.suffix in ('.pdf','.json'):shutil.copy2(f,refs/f.name)
    sdk=previous/'upstream'
    license_files=list(sdk.glob('*LICENSE*'))+list(sdk.glob('*license*'))
    license_files+=list((sdk/'EUU/software/beacon_version').glob('*license*'))
    for f in license_files:
        if f.is_file():
            dst=r/'reproduction/licenses'/f.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
    fw=r/'firmware-D2-release'
    ms=importlib.util.spec_from_file_location('door_receiver',fw/'pluck_receiver.py');mod=importlib.util.module_from_spec(ms);ms.loader.exec_module(mod)
    payload=b'BFD2'+bytes(range(8))
    assert mod.decode(payload)['device_id']=='0001020304050607'
    assert mod.decode(b'BFP1'+bytes(range(8))) is None and mod.decode(payload[:-1]) is None
    rows=[{'time_s':t,'payload_hex':payload.hex(),'capture_id':str(i),'origin':'synthetic-protocol-fixture'} for i,t in enumerate([0,.1,.2,.7])]
    events=mod.group(rows+[rows[0]])
    assert len(events)==2 and events[0]['packets']==3 and events[1]['packets']==1
    (fw/'receiver-fixture.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
    (fw/'receiver-check.json').write_text(json.dumps({'decoder_and_grouping_pass':True,'events':events,'hardware_received':False,'direction_qualified':False},indent=2))
    shutil.copy2(Path(__file__).with_name('REPRODUCTION.md'),r/'reproduction/README.md')
    included=[]
    roots=['requirements','mechanical-D2','animation-D2','simulation/beam-v4','simulation/magnetic-D2-final','simulation/coupled-D2','circuit/ltspice-D2','circuit/libraries','pcb/D2','firmware-D2-release','report','sources','reproduction']
    for base in roots:
        for f in (r/base).rglob('*'):
            rel=f.relative_to(r)
            if not f.is_file() or any(x in rel.parts for x in ['__pycache__','frames','review','placement-failure','router-state','router-state2','router-state3']):continue
            if f.suffix in ['.pyc','.aux','.toc','.out','.fls','.fdb_latexmk','.synctex','.db','.status','.class'] and base!='firmware-D2-release':continue
            if f.name.endswith(('.blend1','.recovery')) or 'blocked' in f.name.lower() or f.suffix=='.html':continue
            included.append(f)
    included=sorted(set(included))
    inventory={'schema_version':'door-case-files-v1','version':'D2','verdict':'NOT_ACCEPTED','files':[{'path':str(f.relative_to(r)),'bytes':f.stat().st_size,'sha256':sha(f)} for f in included]}
    (r/'case-files.json').write_text(json.dumps(inventory,indent=2,ensure_ascii=False))
    out=r/'door-magnetic-D2-engineering.zip'
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for f in included+[r/'case-files.json']:z.write(f,str(f.relative_to(r)))
    with zipfile.ZipFile(out) as z:
        if z.testzip():raise RuntimeError('ARCHIVE_CRC_FAILED')
        for f in inventory['files']:
            if hashlib.sha256(z.read(f['path'])).hexdigest()!=f['sha256']:raise RuntimeError('ARCHIVE_HASH_FAILED')
    (r/'package-receipt.json').write_text(json.dumps({'file':out.name,'sha256':sha(out),'bytes':out.stat().st_size,'files':len(included)+1,'crc_and_all_hashes_pass':True,'hardware_verified':False,'product_accepted':False},indent=2))
    print((r/'package-receipt.json').read_text())
if __name__=='__main__':main()
