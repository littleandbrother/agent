"""Bounded offline routing of an empty, explicitly bound two-layer PCB."""
import hashlib
import json
import math
from pathlib import Path
import re
import time
from .eda_mcp import MCPClient


def route_rules(dsn, width, clearance):
    if not all(type(x) in (int,float) and math.isfinite(x) for x in (width,clearance)) or not 6<=width<=40 or not 6.5<=clearance<=40:
        raise ValueError('ROUTER_RULE_RANGE')
    if '(layer TopLayer' not in dsn or '(layer BottomLayer' not in dsn:
        raise ValueError('ROUTER_TWO_LAYER_REQUIRED')
    result=re.sub(r'\(width\s+[0-9.]+\)',lambda m:'(width '+str(width)+')',dsn)
    result=re.sub(r'\((clear|clearance)\s+([0-9.]+)',lambda m:'('+m[1]+' '+str(max(float(m[2]),clearance)),result)
    if result==dsn:raise ValueError('ROUTER_RULES_NOT_FOUND')
    return result


def run(adapter,job,directory):
    from .jlceda import guard, READBACK
    eng=adapter.e;binding=job['binding'];owner=job['owner'];key=job['id'];p=job['parameters']
    home=eng.store.root.parent/'toolchains/freerouting'
    executable=home/'freerouting.app/Contents/MacOS/freerouting'
    receipt=home/'download-receipt.json'
    if not executable.is_file() or not receipt.is_file():raise ValueError('FREEROUTING_NOT_INSTALLED')
    distribution=json.loads(receipt.read_text())
    (directory/'router-distribution.json').write_text(json.dumps(distribution,indent=2))
    width=p['trace_width_mil'];clearance=p['clearance_mil']
    with MCPClient(lambda r:adapter.audit(owner,key,directory,r)) as c:
        pre=guard(binding,'pcb')+'''const lines=(await eda.pcb_PrimitiveLine.getAll()).filter(l=>[1,2].includes(l.getState_Layer()));
if(lines.length || (await eda.pcb_PrimitiveVia.getAll()).length)throw Error('ROUTER_REQUIRES_UNROUTED_BOARD');
const f=await eda.pcb_ManufactureData.getDsnFile('route-input');if(!f)throw Error('DSN_EXPORT_FAILED');return {dsn:await f.text()};'''
        initial=c.execute(pre,binding['window_id'],45)['dsn']
        (directory/'native.dsn').write_text(initial)
        routed=route_rules(initial,width,clearance)
        (directory/'route-input.dsn').write_text(routed)
        (directory/'routing-policy.json').write_text(json.dumps({'trace_width_mil':width,'minimum_clearance_mil':clearance,
            'native_rules_changed':False,'native_input_sha256':hashlib.sha256(initial.encode()).hexdigest(),
            'routing_input_sha256':hashlib.sha256(routed.encode()).hexdigest(),
            'scope':'Explicit candidate trace width; exported clearances are only increased. Native DRC is authoritative.'},indent=2))
        eng.command(key,owner,[str(executable),'-de',str(directory/'route-input.dsn'),'-do',str(directory/'route-output.ses'),
            '-mp','24','-mt','2','-da','--gui.enabled=false','--api_server.enabled=false',
            '--user_data_path='+str(home/'state'),'--logging.file.location='+str(directory/'routing-logs')],directory,time.monotonic()+165)
        ses=directory/'route-output.ses'
        if not ses.is_file() or ses.stat().st_size>8*1024*1024:raise ValueError('ROUTER_NO_BOUNDED_RESULT')
        fresh=c.execute(pre,binding['window_id'],45)['dsn']
        if fresh!=initial:raise ValueError('ROUTER_BOARD_CHANGED_DURING_RUN')
        code=guard(binding,'pcb')+'const isPcb=true;const out={};\n'+f'''
out.imported=await eda.pcb_Document.importAutoRouteSesFile(new File([{json.dumps(ses.read_text())}],'route-output.ses',{{type:'text/plain'}}));
if(out.imported!==true)throw Error('SES_IMPORT_FAILED');
// EasyEDA 3.2.148 imports SES paths at default width. Restore the explicit
// uniform candidate width and recheck with the untouched native rules.
for(const l of await eda.pcb_PrimitiveLine.getAll())if([1,2].includes(l.getState_Layer())){{if(!await eda.pcb_PrimitiveLine.modify(l,{{lineWidth:{width}}}))throw Error('ROUTER_WIDTH_UPDATE_FAILED');}}
out.saved=await eda.pcb_Document.save();if(!out.saved)throw Error('ROUTER_SAVE_FAILED');
const ok=await eda.pcb_Drc.check(true,false,false);out.drc={{raw:ok??null,status:ok===true?'passed':ok===false?'failed':'unavailable'}};
if(ok!==true)out.drc.details=await eda.pcb_Drc.check(true,false,true);
'''+READBACK
        result=c.execute(code,binding['window_id'],90)
    (directory/'pcb.epro-source').write_text(result.pop('source'))
    if result.get('netlist'):(directory/'pcb-readback.net').write_text(result.pop('netlist'))
    result.update(engine='JLCEDA Pro + FreeRouting',operation='freeroute',binding=binding,product_verified=False,
        native_rules_changed=False,scope='Offline candidate routing and native DRC; no manufacturing approval.')
    return result
