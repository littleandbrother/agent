"""Read-only audit and NEW unexecuted save-only deck derivative.

Does not import, acquire, license, or execute any vendor model/tool. Original
RAW, deck and evidence remain intact. New physical stimuli require separate
explicit fixture definitions, rather than silently modifying original runs.
"""
import argparse,hashlib,json,pathlib,re
REQUIRED=('V(vin2)','V(cap)','V(vin,cap)','I(Ccap)','I(Cvin2)')
RECOMMENDED=('I(Cstorage)','I(Cout)','I(L1)','I(Idiagnostic)')

def audit(text):
    saved=[]
    for line in text.splitlines():
        if line.strip().lower().startswith('.save '):saved.extend(line.strip().split()[1:])
    low={s.lower() for s in saved}
    return {'saved':saved,'required_missing':[s for s in REQUIRED if s.lower() not in low],'recommended_missing':[s for s in RECOMMENDED if s.lower() not in low], 'rail_charge_discharge_observable':all(s.lower() in low for s in REQUIRED),'subcircuit_port_order_verified':False,'raw_header_still_required':True}

def add_saves(input_path,output_path):
    src=pathlib.Path(input_path);out=pathlib.Path(output_path)
    if out.exists():raise ValueError('OUTPUT_MUST_BE_NEW')
    text=src.read_text();lines=text.splitlines();ends=[i for i,l in enumerate(lines) if l.strip().lower()=='.end']
    if len(ends)!=1:raise ValueError('REQUIRE_EXACTLY_ONE_END')
    for element in ('Ccap','Cvin2','Cstorage','Cout','L1','Idiagnostic'):
        if not any(l.lower().startswith(element.lower()+' ') for l in lines):raise ValueError('MISSING_REQUIRED_ELEMENT:'+element)
    missing=audit(text);signals=missing['required_missing']+missing['recommended_missing']
    lines[ends[0]:ends[0]]=['* UNEXECUTED OBSERVATION-ONLY DERIVATIVE; preserve original native evidence.', '.save '+' '.join(signals)] if signals else []
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text('\n'.join(lines)+'\n')
    return {'input_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'added_signals':signals,'physical_stimulus_changed':False,'vendor_executed':False,'original_evidence_preserved':True,'requires':['model .SUBCKT port order mapped to XU1 instance','new legal/authorized native execution','retained RAW header and rail waveforms','step/tolerance refinement']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path);args=p.parse_args()
    print(json.dumps(add_saves(args.input,args.output) if args.output else audit(args.input.read_text()),indent=2))
