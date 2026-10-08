"""Read-only source/native connectivity accounting, never a manufacturing verdict.

The participant supplies the mapping; this program does not invent a design.
Unmapped source elements and unsupported exclusions remain visible.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(path):
    elements=[];inside_subcircuit=False
    for number,line in enumerate(Path(path).read_text().splitlines(),1):
        words=line.strip().split()
        if number==1:continue  # SPICE title is not a component.
        if words and words[0].lower()=='.subckt':inside_subcircuit=True;continue
        if words and words[0].lower()=='.ends':inside_subcircuit=False;continue
        if inside_subcircuit:continue
        if not words or words[0][0].upper() not in 'RCLDMQX':
            continue
        letter=words[0][0].upper()
        if letter not in 'RCLDMQX' or words[0].startswith(('.', '*', '+')):
            continue
        terminals={'R':2,'C':2,'L':2,'D':2,'M':4,'Q':3}.get(letter)
        if letter=='X':
            # Subcircuit model name precedes optional PARAMS assignments.
            end=next((i for i,w in enumerate(words) if i>0 and ('=' in w or w.upper()=='PARAMS:')),len(words))
            terminals=end-2
        if terminals<1 or len(words)<terminals+2:
            raise ValueError('UNSUPPORTED_SOURCE_LINE:'+str(number))
        elements.append({'id':words[0],'line':number,'type':letter,
                         'nodes':words[1:1+terminals],'model_or_value':words[1+terminals:],
                         'source_text':line.strip()})
    return elements


def audit(source,native,mapping=None):
    elements=inventory(source);doc=json.loads(Path(native).read_text())
    components={};duplicates=[]
    for value in doc['components'].values():
        ref=value.get('props',{}).get('Designator')
        if ref in components:duplicates.append(ref)
        components[ref]=value
    result={'schema_version':'bf-schematic-source-accounting-v1',
            'source_sha256':sha(source),'native_sha256':sha(native),
            'source_elements':elements,'native_components':[
                {'ref':r,'mpn':c.get('props',{}).get('Manufacturer Part'),
                 'supplier':c.get('props',{}).get('Supplier Part'),
                 'value':c.get('props',{}).get('Value'),
                 'pins':{k:{'name':v.get('name'),'net':v.get('net')} for k,v in c.get('pinInfoMap',{}).items()}}
                for r,c in components.items()],
            'errors':['duplicate_native_designator:'+str(r) for r in duplicates],
            'unmapped':[],'declared_exclusions':[],'mapped':[],
            'value_and_rating_verified':False,'behavioral_realization_verified':False,
            'engineering_passed':False,
            'scope':'Source connectivity accounting only. Exclusions, physical values/ratings, functional completeness, behavioral realization and extra MCU/RF circuitry require independent review.'}
    if mapping is None:
        result['unmapped']=[e['id'] for e in elements];result['status']='mapping_required';return result
    data=json.loads(Path(mapping).read_text())
    for key in ('source_sha256','native_sha256'):
        if data.get(key)!=result[key]:result['errors'].append(key+'_mismatch')
    by_id={e['id']:e for e in elements}; aliases=data.get('net_aliases',{})
    entries=data.get('instances',{});exclusions=data.get('exclusions',{})
    for key in (entries.keys()|exclusions.keys())-by_id.keys():
        result['errors'].append('unknown_source_instance:'+key)
    for e in elements:
        key=e['id'];entry=entries.get(key)
        if key in exclusions:
            reason=exclusions[key]
            result['declared_exclusions'].append({'id':key,'reason':reason,'independently_accepted':False})
            if not isinstance(reason,str) or len(reason.strip())<20:result['errors'].append('exclusion_needs_reason:'+key)
            if entry:result['errors'].append('mapped_and_excluded:'+key)
            continue
        if not entry:result['unmapped'].append(key);continue
        ref=entry.get('ref');pins=entry.get('pins',[])
        if ref not in components:result['errors'].append('native_component_missing:'+key+':'+str(ref));continue
        if len(pins)!=len(e['nodes']):result['errors'].append('terminal_count:'+key);continue
        native_pins=components[ref].get('pinInfoMap',{})
        mismatches=[]
        for node,pin in zip(e['nodes'],pins):
            expected=aliases.get(node)
            actual=native_pins.get(str(pin),{}).get('net')
            if expected is None or not actual or actual!=expected:
                mismatches.append({'source_node':node,'native_pin':str(pin),'expected_native_net':expected,'actual_native_net':actual})
        result['mapped'].append({'id':key,'ref':ref,'mismatches':mismatches})
        if mismatches:result['errors'].append('connectivity_mismatch:'+key)
    result['mapping_sha256']=sha(mapping)
    result['status']='connectivity_accounted' if not result['errors'] and not result['unmapped'] else 'incomplete_or_mismatched'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spice',required=True,type=Path);p.add_argument('--native',required=True,type=Path)
    p.add_argument('--mapping',type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();value=audit(a.spice,a.native,a.mapping)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:value[k] for k in ('status','errors','unmapped','engineering_passed')},ensure_ascii=False))
