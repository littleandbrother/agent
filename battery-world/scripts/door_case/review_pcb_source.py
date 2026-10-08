#!/usr/bin/env python3
"""Read-only coverage audit of a SPICE source and participant PCB intermediates.

Checks D/Q/M electrical roles and literal device identities, explicit ballast
resistors, BOM presence and layout presence. It does not certify package pinouts,
physical routing, DRC, behavior-source implementation, or manufacturability.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_devices(path):
    roles = {'D': ('A','K'), 'Q': ('C','B','E'), 'M': ('D','G','S','B')}
    result = {}; level = 0
    for line_no, line in enumerate(path.read_text().splitlines(),1):
        tokens = line.split(';',1)[0].split()
        if not tokens: continue
        if tokens[0].lower()=='.subckt': level += 1
        if tokens[0].lower()=='.ends': level = max(0,level-1)
        if level or tokens[0][0].upper() not in roles: continue
        key = tokens[0]; names = roles[key[0].upper()]
        if len(tokens) < len(names)+2: continue
        result[key] = {'model':tokens[len(names)+1], 'roles':dict(zip(names,tokens[1:])), 'source_line':line_no}
    return result


def load_bom(path):
    if path.suffix.lower() != '.csv': return json.loads(path.read_text())
    lines=[]
    with path.open(newline='') as stream:
        for item in csv.DictReader(stream):
            refs=[x.strip() for x in item.get('Refdes','').split(',') if x.strip()]
            lines.append({'refs':refs,'quantity':item.get('Qty'),'mpn':item.get('MPN'),
                          'package':item.get('Package'),'lcsc':item.get('LCSC')})
    if not lines or any(not item['refs'] for item in lines): raise ValueError('Unsupported or empty BOM CSV schema')
    return {'lines':lines}


def review_csv_netlist(path):
    """A serialized device must retain every declared terminal, even above five."""
    findings=[]
    with path.open(newline='') as stream:
        rows=csv.DictReader(stream)
        fields=rows.fieldnames or []
        if not {'ref','nodes'}.issubset(fields): raise ValueError('Unsupported netlist CSV schema')
        columns=[k for k in fields if k.startswith('net') and k[3:].isdigit()]
        for row in rows:
            declared=int(row['nodes']);retained=sum(bool(row[k]) for k in columns)
            if declared != retained:
                findings.append({'ref':row['ref'],'kind':'netlist_terminal_loss','declared':declared,'retained':retained})
    return findings


def review(source, physical, bom, layout=None, native=None):
    expected=source_devices(source); findings=[]
    if not expected: raise ValueError('No supported source devices; cannot declare a vacuous pass')
    parts=physical.get('instances',{})
    bom_refs={ref for item in bom.get('lines',[]) for ref in item.get('refs',[])}
    seen=set()
    for item in bom.get('lines',[]):
        refs=item.get('refs',[])
        if item.get('quantity') is not None and str(len(refs)) != str(item['quantity']):
            findings.append({'kind':'bom_quantity_mismatch','refs':refs,'declared':item['quantity'],'actual':len(refs)})
        for ref in refs:
            if ref in seen: findings.append({'ref':ref,'kind':'duplicate_bom_instance'})
            seen.add(ref)
    layout_refs=set()
    if layout:
        items=layout.get('components',layout.get('placements',layout.get('placement',[])))
        if isinstance(items,dict):layout_refs=set(items)
        else:layout_refs={item.get('source_ref',item.get('ref')) for item in items if isinstance(item,dict)}
    for ref, spec in expected.items():
        item=parts.get(ref)
        if not item:
            findings.append({'ref':ref,'kind':'missing_physical_instance','source_line':spec['source_line']})
        else:
            for name,net in spec['roles'].items():
                actual=item.get('roles',{}).get(name)
                if actual != net:findings.append({'ref':ref,'kind':'electrical_role_mismatch','role':name,'expected':net,'actual':actual,'source_line':spec['source_line']})
            if item.get('mpn','').split(',')[0].upper() != spec['model'].upper():
                findings.append({'ref':ref,'kind':'model_identity_requires_equivalence','source_model':spec['model'],'candidate':item.get('mpn')})
        if ref not in bom_refs:findings.append({'ref':ref,'kind':'missing_bom_instance'})
        if layout is not None and ref not in layout_refs:findings.append({'ref':ref,'kind':'missing_layout_instance'})
    ballast=[]
    for line in source.read_text().splitlines():
        tokens=line.split()
        if tokens and tokens[0].startswith('Rbal_'):ballast.append(tokens[0])
    for ref in ballast:
        if ref not in bom_refs:findings.append({'ref':ref,'kind':'missing_bom_ballast'})
        if layout is not None and ref not in layout_refs:findings.append({'ref':ref,'kind':'missing_layout_ballast'})
    if native is not None:
        # Require exact source refs or an explicit participant-owned alias.
        # A similar symbol or representative package is not a whole bank.
        parts=native.get('result',{}).get('components',[])
        aliases=physical.get('native_refs',{})
        actual={c.get('designator'):c for c in parts if c.get('componentType')=='part'}
        for ref,spec in expected.items():
            target=aliases.get(ref,ref);part=actual.get(target)
            if not part:
                findings.append({'ref':ref,'native_ref':target,'kind':'missing_native_instance'});continue
            pin_nets={p.get('pinName'):p.get('net') for p in part.get('pins',[])}
            for role,net in spec['roles'].items():
                if pin_nets.get(role) != net:
                    findings.append({'ref':ref,'kind':'native_pin_role_unverified','role':role,'expected':net,'actual':pin_nets.get(role)})
            if part.get('manufacturerId','').upper() != spec['model'].upper():
                findings.append({'ref':ref,'kind':'native_model_requires_equivalence','source_model':spec['model'],'candidate':part.get('manufacturerId')})
        for ref in ballast:
            if aliases.get(ref,ref) not in actual:findings.append({'ref':ref,'kind':'missing_native_ballast'})
    return {'schema_version':'bf-pcb-source-coverage-v1','source_sha256':hash_file(source),
            'source_dqm_instances':len(expected),'source_ballast_instances':len(ballast),
            'findings':findings,'covered_checks_passed':not findings,
            'layout_checked':layout is not None,'native_checked':native is not None,'engineering_passed':False,
            'still_required':['all R/C/L/X connections and values','manufacturer package pinout','behavioral block physical implementation','native pad and net readback','copper connectivity and clearance','DRC and save/reload','current hardware qualification'],
            'scope':__doc__.strip()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--physical',type=Path,required=True);p.add_argument('--bom',type=Path,required=True);p.add_argument('--layout',type=Path);p.add_argument('--native',type=Path);p.add_argument('--netlist',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    value=review(a.source,json.loads(a.physical.read_text()),load_bom(a.bom),json.loads(a.layout.read_text()) if a.layout else None,json.loads(a.native.read_text()) if a.native else None)
    if a.netlist:
        value['findings']+=review_csv_netlist(a.netlist)
        value['covered_checks_passed']=not value['findings']
    value['inputs']={key:{'path':str(path),'sha256':hash_file(path)} for key,path in [('source',a.source),('physical',a.physical),('bom',a.bom),('layout',a.layout),('native',a.native),('netlist',a.netlist)] if path}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(value,ensure_ascii=False,indent=2))
    print(json.dumps({'covered_checks_passed':value['covered_checks_passed'],'findings':len(value['findings']),'engineering_passed':False,'output':str(a.out)},ensure_ascii=False))


if __name__=='__main__':main()
