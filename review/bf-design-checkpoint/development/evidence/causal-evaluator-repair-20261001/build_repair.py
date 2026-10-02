#!/usr/bin/env python3
"""Build separate v2 apparatus from exact pinned v1 functions, without editing upstream."""
import ast, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
UP=Path('/workspace/shared/current-cache-integration-20261001/working/battery-world')
P=UP/'packages/python/bfworld/src/bfworld/agentlab/event_design.py'
s=P.read_text(); tree=ast.parse(s)
def func(name):
    n=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    return ast.get_source_segment(s,n)
code='''"""Separately versioned, generic reduced-order diagnostic apparatus.
Not a vendor PMIC model; not authoritative door-world or hardware evidence.
Derived from pinned event_design.py; attribution and hash in source-binding.json.
"""
import math
import re
from pathlib import Path
MODEL_VERSION = "bf-event-apparatus-v2-fixed-reset-ports"
SPEC_VERSION = "bf-event-design-v2"
CHANNEL_KEYS = ['time_s','drive','displacement_m','velocity_m_s','piezo_v','storage_v','enabled','stage_time_s','force_n','rectifier_a','load_a','diode_loss_w','quiescent_a','piezo_to_bridge_a','negative_rail_v']
'''
code+='\n\n'+func('number')
v=func('validate').replace("'bf-event-design-v1'","SPEC_VERSION")
v=v.replace("    return spec", """    control=spec.get('control',{})
    number(control.get('timer_reset_tau_s'),'timer_reset_tau_s',1e-9,.01)
    if control.get('feedback_mode') not in ('reciprocal','no-feedback'):
        raise ValueError('EVENT_FEEDBACK_MODE_REQUIRED')
    if 'control' not in groups:
        raise ValueError('EVENT_CONTROL_PROVENANCE_REQUIRED')
    return spec""")
code+='\n\n'+v
n=func('netlist').replace("    m,s,p,w,d=", "    validate(spec)\n    number(step,'step',1e-7,spec['simulation']['step_s'])\n    if not re.fullmatch(r'[A-Za-z0-9_.-]+',out_name):\n        raise ValueError('EVENT_OUTPUT_BASENAME_REQUIRED')\n    m,s,p,w,d=")
n=n.replace('BF event reduced-order coupled transient v1','BF event apparatus v2 fixed-reset explicit ports')
n=n.replace("{m['coupling_n_v']:.12g}*v(p)","{(m['coupling_n_v'] if spec['control']['feedback_mode']=='reciprocal' else 0):.12g}*v(p)")
n=n.replace('D1 p rect Dbridge','Vpiezo_port p bridge_p 0\nD1 bridge_p rect Dbridge').replace('D3 neg p Dbridge','D3 neg bridge_p Dbridge')
n=n.replace('{step/10:.12g}',"{spec['control']['timer_reset_tau_s']:.12g}")
n=n.replace('set noaskquit','set noaskquit\nset numdgt=17')
n=n.replace('load_i diode_loss @bquiescent[i]','load_i diode_loss @bquiescent[i] i(Vpiezo_port) v(neg)')
code+='\n\n'+n+'\n\n'+func('integrate')
code+='''\n\ndef read_channels(path):
    with Path(path).open() as f:
        header=f.readline()
        rows=[[float(x) for x in line.split()] for line in f if line.strip()]
    if len(rows)<10 or any(len(r)!=len(CHANNEL_KEYS) or any(not math.isfinite(v) for v in r) for r in rows):
        raise ValueError('EVENT_SPICE_CHANNELS_INVALID:'+header[:100])
    if any(b[0]<=a[0] for a,b in zip(rows,rows[1:])):
        raise ValueError('EVENT_SPICE_TIME_NOT_STRICT')
    return [dict(zip(CHANNEL_KEYS,r)) for r in rows]
'''
(ROOT/'src/event_apparatus_v2.py').write_text(code)
test=UP/'tests/agentlab/test_reference_event.py'; ts=test.read_text(); tn=next(n for n in ast.parse(ts).body if isinstance(n,ast.FunctionDef) and n.name=='fixture')
scope={};exec(compile(ast.Module(body=[tn],type_ignores=[]),str(test),'exec'),scope)
fixture=scope['fixture']();fixture['schema_version']='bf-event-design-v2';fixture['power'].update(start_v=.8,stop_v=.5,output_v=.4)
fixture['control']={'timer_reset_tau_s':1e-6,'feedback_mode':'reciprocal'}
fixture['provenance'].append({'parameter':'control','origin':'assumption','source':'prospective generic apparatus diagnostic v2','locator':'contracts/prospective-plan-v2.json','conditions':'Fixed mathematical reset timescale, not measured firmware or physical PMIC state'})
(ROOT/'contracts/base-fixture-v2.json').write_text(json.dumps(fixture,indent=2)+'\n')
(ROOT/'source-binding.json').write_text(json.dumps({'schema_version':'causal-repair-source-binding-v1','source_commit':'338d60384d5805abf1e02252a4513860066a2c39','source_files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [P,test]},'old_results_preserved':True,'production_imports_changed':False},indent=2)+'\n')
