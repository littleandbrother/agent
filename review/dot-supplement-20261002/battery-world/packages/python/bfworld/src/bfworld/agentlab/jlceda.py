"""JLCEDA Pro: typed operations on explicitly bound documents, via real MCP."""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import time
from .eda_mcp import MCPClient, SERVER, REFERENCES
from .store import canonical

SCOPE='立创专业版原生原理图与 PCB；数字设计与规则检查不等于实物验证或生产批准。'
OPERATIONS=['inspect','components','wires','fanout','import_pcb','layout','tracks','autoroute','freeroute','check','export']
SKILL_PATHS={k:Path.home()/'.codex/skills'/k/'SKILL.md' for k in ('easyeda-api','easyeda-schematic-net-fanout','easyeda-pcb-routing')}
CONTEXT='return {project:await eda.dmt_Project.getCurrentProjectInfo(),document:await eda.dmt_SelectControl.getCurrentDocumentInfo(),boards:await eda.dmt_Board.getAllBoardsInfo()};'


def parse_text(response):
    value='\n'.join(c.get('text','') for c in response.get('content',[]) if c.get('type')=='text')
    if value.startswith('[EDA') or value.startswith('[eda'):value=value.split('\n',1)[-1]
    return json.loads(value)


def validate(p):
    if not isinstance(p,dict) or p.get('operation') not in OPERATIONS:raise ValueError('EDA_OPERATION_REQUIRED')
    fields={'operation','document','components','wires','pin_nets','positions','board_width_mm','board_height_mm','tracks','nets','ignore_nets','trace_width_mil','clearance_mil'}
    if set(p)-fields:raise ValueError('EDA_UNKNOWN_PARAMETER')
    op=p['operation']
    if p.get('document','schematic') not in ('schematic','pcb'):raise ValueError('EDA_DOCUMENT_INVALID')
    expected='schematic' if op in ('components','wires','fanout') else 'pcb' if op in ('import_pcb','layout','tracks','autoroute','freeroute') else None
    if expected and p.get('document',expected)!=expected:raise ValueError('EDA_OPERATION_DOCUMENT_CONFLICT')
    def num(v,limit=10000):
        if type(v) not in (int,float) or not math.isfinite(v) or abs(v)>limit:raise ValueError('EDA_COORDINATE_INVALID')
    def name(s):
        if not isinstance(s,str) or not re.fullmatch(r'[A-Za-z0-9_+./-]{1,64}',s):raise ValueError('EDA_NAME_INVALID')
    if op=='fanout':
        assignments=p.get('pin_nets')
        if not isinstance(assignments,dict) or not 1<=len(assignments)<=40:raise ValueError('EDA_PIN_NETS_REQUIRED')
        for ref,pins in assignments.items():
            name(ref)
            if not isinstance(pins,dict) or not 1<=len(pins)<=144:raise ValueError('EDA_PIN_NETS_INVALID')
            for pin,net in pins.items():
                name(pin)
                if net is not None:name(net)
    if op=='components':
        cs=p.get('components')
        if not isinstance(cs,list) or not 1<=len(cs)<=40:raise ValueError('EDA_COMPONENTS_REQUIRED')
        refs=set()
        for c in cs:
            if set(c)-{'lcsc','ref','x','y','rotation'}:raise ValueError('EDA_COMPONENT_INVALID')
            name(c.get('ref'))
            if c['ref'] in refs:raise ValueError('EDA_DUPLICATE_REFERENCE')
            refs.add(c['ref'])
            if not re.fullmatch(r'C\d{1,12}',str(c.get('lcsc'))):raise ValueError('EDA_LCSC_REQUIRED')
            for k in ('x','y'):num(c.get(k))
            if c.get('rotation',0) not in (0,90,180,270):raise ValueError('EDA_ROTATION_INVALID')
    if op=='wires':
        ws=p.get('wires')
        if not isinstance(ws,list) or not 1<=len(ws)<=100:raise ValueError('EDA_WIRES_REQUIRED')
        for w in ws:
            if set(w)!={'net','points'}:raise ValueError('EDA_WIRE_INVALID')
            name(w['net']);pts=w['points']
            if not isinstance(pts,list) or not 4<=len(pts)<=40 or len(pts)%2:raise ValueError('EDA_WIRE_POINTS_INVALID')
            for v in pts:num(v)
    if op=='layout':
        for k in ('board_width_mm','board_height_mm'):
            num(p.get(k),300)
            if p[k]<10:raise ValueError('EDA_BOARD_SIZE_INVALID')
        if not isinstance(p.get('positions'),list) or not 1<=len(p['positions'])<=40:raise ValueError('EDA_POSITIONS_REQUIRED')
        for x in p['positions']:
            name(x.get('ref'))
            for k in ('x_mm','y_mm'):num(x.get(k),300)
            if not 0<x['x_mm']<p['board_width_mm'] or not 0<x['y_mm']<p['board_height_mm']:raise ValueError('EDA_POSITION_OUTSIDE_BOARD')
            if x.get('rotation',0) not in (0,90,180,270):raise ValueError('EDA_ROTATION_INVALID')
    if op=='tracks':
        ts=p.get('tracks')
        if not isinstance(ts,list) or not 1<=len(ts)<=100:raise ValueError('EDA_TRACKS_REQUIRED')
        for t in ts:
            name(t.get('net'))
            if t.get('layer',1) not in (1,2):raise ValueError('EDA_COPPER_LAYER_INVALID')
            for k in ('x1_mm','y1_mm','x2_mm','y2_mm','width_mm'):num(t.get(k),300)
            if not .1<=t['width_mm']<=5:raise ValueError('EDA_TRACK_WIDTH_INVALID')
    if op=='autoroute':
        if not isinstance(p.get('nets'),list) or not p['nets']:raise ValueError('EDA_EXPLICIT_ROUTING_NETS_REQUIRED')
        for n in p['nets']+p.get('ignore_nets',[]):name(n)
        if set(p['nets']) & set(p.get('ignore_nets',[])):raise ValueError('EDA_ROUTING_NET_CONFLICT')
    if op=='freeroute':
        from .freerouting import route_rules
        route_rules('(layer TopLayer)(layer BottomLayer)(rule(width 10))',p.get('trace_width_mil'),p.get('clearance_mil'))
    return p


def guard(binding,document):
    doc=binding[document+'_uuid'];project=binding['project_uuid']
    return f'''const _p=await eda.dmt_Project.getCurrentProjectInfo();
if(_p?.uuid!=={json.dumps(project)})throw new Error('EDA_PROJECT_CHANGED');
const _target={json.dumps(doc)};
const _tab=await eda.dmt_EditorControl.openDocument(_target);
if(!_tab || !await eda.dmt_EditorControl.activateDocument(_tab))throw new Error('EDA_ACTIVATION_FAILED');
const _d=await eda.dmt_SelectControl.getCurrentDocumentInfo();
if(_d?.uuid!==_target || _d?.parentProjectUuid!=={json.dumps(project)})throw new Error('EDA_DOCUMENT_MISMATCH');
'''


# Getter names and units are from the installed official API reference.
READBACK='''const comps=await (isPcb?eda.pcb_PrimitiveComponent:eda.sch_PrimitiveComponent).getAll();
const components=[];for(const c of comps){const ref=c.getState_Designator();if(!ref)continue;
const pins=await (isPcb?eda.pcb_PrimitiveComponent:eda.sch_PrimitiveComponent).getAllPinsByPrimitiveId(c.getState_PrimitiveId());
components.push({ref,id:c.getState_PrimitiveId(),x:c.getState_X(),y:c.getState_Y(),rotation:c.getState_Rotation(),pins:(pins||[]).map(p=>({number:isPcb?p.getState_PadNumber():p.getState_PinNumber(),x:p.getState_X(),y:p.getState_Y(),rotation:p.getState_Rotation(),...(isPcb?{net:p.getState_Net()}: {})}))});}
try{const nf=await (isPcb?eda.pcb_ManufactureData:eda.sch_ManufactureData).getNetlistFile('readback');out.netlist=nf?await nf.text():null;}catch(e){out.netlist_error=String(e);}
if(isPcb){try{out.lines=(await eda.pcb_PrimitiveLine.getAll()).map(l=>({id:l.getState_PrimitiveId(),net:l.getState_Net(),layer:l.getState_Layer(),width:l.getState_LineWidth(),x1:l.getState_StartX(),y1:l.getState_StartY(),x2:l.getState_EndX(),y2:l.getState_EndY()}));}catch(e){out.lines_error=String(e);}}
const source=await eda.sys_FileManager.getDocumentSource();
if(typeof source!=='string'||!source.length)throw new Error('EDA_SOURCE_MISSING');
return {components,source,coordinate_unit:isPcb?'mil (0.0254 mm)':'0.01 inch (0.254 mm)',...out};'''


class JLCEDA:
    def __init__(self,engineering):
        self.e=engineering;self.store=engineering.store;self.latest={'status':'not_probed'}
        with self.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS eda_bindings(owner TEXT PRIMARY KEY, binding TEXT, created REAL)')

    def binding(self,owner):
        with self.store.connect() as db:r=db.execute('SELECT binding FROM eda_bindings WHERE owner=?',(owner,)).fetchone()
        return json.loads(r['binding']) if r else None

    def catalog(self,owner=None):
        return {'installed':SERVER.is_file(),'server':'easyeda-pro-mcp','publisher':'Nambers (community)','license':'Apache-2.0',
                'bridge':'official easyeda-api API Gateway','transport':'mcp-stdio → local WebSocket bridge',
                'status':self.latest,'binding':self.binding(owner) if owner else None,'operations':OPERATIONS,
                'scope':SCOPE,'setup':'半离线版请在立创中新建独立工程并打开原理图，再在这里绑定；绑定后仅操作该板。'}

    def audit(self,owner,key,directory,receipt):
        raw=canonical(receipt);name='mcp-'+str(time.time_ns())+'.json';(directory/name).write_text(raw)
        args=receipt.get('request',{}).get('params',{})
        self.e.event(owner,key,'mcp_call',{'server':'easyeda-pro-mcp','transport':'mcp-stdio','method':receipt['method'],
                     'tool':args.get('name',receipt['method']),'status':receipt['status'],'duration_ms':receipt['duration_ms'],
                     'server_source_sha256':receipt.get('server_source_sha256'),
                     'started':receipt['started'],'input':args.get('arguments',{}),'error':receipt.get('error'),
                     'raw_artifact':name,'sha256':hashlib.sha256(raw.encode()).hexdigest(),
                     'response':receipt.get('response') if len(raw)<24000 else {'stored_in_artifact':name,'bytes':len(raw)}})

    def probe(self,owner):
        # Explicit probe only. Ordinary UI polling never invokes EDA or generates trace noise.
        with MCPClient() as c:
            tools=c.request('tools/list',{})['tools'];health=parse_text(c.call('eda_health'));windows=parse_text(c.call('eda_windows'))
            self.latest={'status':'connected' if health.get('edaConnected') else 'disconnected','checked_at':time.time(),
                         'health':health,'windows':windows,'tools':tools}
        self.e.event(owner,None,'mcp_probe',{'status':self.latest['status'],'tool_count':len(tools),'health':health})
        return self.catalog(owner)

    def bind(self,owner,window,project,board):
        if not all(isinstance(v,str) and v for v in (window,project,board)):raise ValueError('EDA_BINDING_IDENTITIES_REQUIRED')
        with MCPClient() as c:r=c.execute(CONTEXT,window)
        p=r.get('project') or {};b=next((b for b in r.get('boards',[]) if b['uuid']==board),None)
        if p.get('uuid')!=project or not b:raise ValueError('EDA_BINDING_MISMATCH')
        pages=(b.get('schematic') or {}).get('page',[])
        if len(pages)!=1 or not b.get('pcb'):raise ValueError('EDA_ONE_SCHEMATIC_PAGE_AND_PCB_REQUIRED')
        binding={'window_id':window,'project_uuid':project,'project_name':p.get('friendlyName'), 'board_uuid':board,'board_name':b['name'],
                 'schematic_uuid':pages[0]['uuid'],'schematic_root_uuid':b['schematic']['uuid'],'pcb_uuid':b['pcb']['uuid']}
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM engineering_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone():raise ValueError('ENGINEERING_BUSY')
            db.execute('INSERT OR REPLACE INTO eda_bindings VALUES(?,?,?)',(owner,canonical(binding),time.time()))
        self.e.event(owner,None,'eda_binding',binding);return binding

    def context(self,window):
        if not isinstance(window,str) or not window:raise ValueError('EDA_WINDOW_REQUIRED')
        with MCPClient() as c:return c.execute(CONTEXT,window)

    def run(self,job,directory):
        owner,key=job['owner'],job['id'];p=job['parameters'];b=job['binding'];op=p['operation']
        if op=='freeroute':
            from .freerouting import run
            return run(self,job,directory)
        document='pcb' if op in ('import_pcb','layout','tracks','autoroute') else 'schematic' if op in ('components','wires','fanout') else p.get('document','schematic')
        pcb=document=='pcb';out={};code=guard(b,document)+'const isPcb='+str(pcb).lower()+';const out={};const args='+json.dumps(p,ensure_ascii=False)+';\n'
        if op=='components':code+='''
const existing=(await eda.sch_PrimitiveComponent.getAll()).filter(c=>c.getState_Designator());
const refs=new Set(existing.map(c=>c.getState_Designator()));
for(const spec of args.components)if(refs.has(spec.ref))throw new Error('EDA_REFERENCE_EXISTS:'+spec.ref);
const devices=[];for(const spec of args.components){let list=await eda.lib_Device.getByLcscIds(spec.lcsc,undefined,true);if(!Array.isArray(list))list=list?[list]:[];
const d=list.find(x=>x.supplierId===spec.lcsc && x.footprintUuid);if(!d)throw new Error('EDA_DEVICE_OR_FOOTPRINT_MISSING:'+spec.lcsc);devices.push(d);}
for(let i=0;i<args.components.length;i++){const s=args.components[i],d=devices[i];const c=await eda.sch_PrimitiveComponent.create({uuid:d.uuid,libraryUuid:d.libraryUuid},s.x,s.y,undefined,s.rotation||0,false,true,true);if(!c)throw new Error('EDA_COMPONENT_CREATE_FAILED');const a=c.toAsync();a.setState_Designator(s.ref);await a.done();}out.library_devices=devices;
'''
        elif op=='wires':code+='''for(const w of args.wires){if(!await eda.sch_PrimitiveWire.create(w.points,w.net))throw new Error('EDA_WIRE_CREATE_FAILED:'+w.net);}out.wires=await eda.sch_PrimitiveWire.getAll();'''
        elif op=='fanout':code+='''
const cs=await eda.sch_PrimitiveComponent.getAll();const byRef=new Map(cs.filter(c=>c.getState_Designator()).map(c=>[c.getState_Designator(),c]));
const entries=[];const wires=await eda.sch_PrimitiveWire.getAll();
for(const [ref,assignments] of Object.entries(args.pin_nets)){
 const c=byRef.get(ref);if(!c)throw new Error('EDA_REFERENCE_MISSING:'+ref);
 const pins=await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(c.getState_PrimitiveId());
 if(pins.length!==Object.keys(assignments).length || pins.some(p=>!(p.getState_PinNumber() in assignments)))throw new Error('EDA_PIN_ASSIGNMENT_INCOMPLETE:'+ref);
 for(const p of pins){const x=p.getState_X(),y=p.getState_Y();if(wires.some(w=>w.line?.some((v,i)=>i%2===0 && Math.abs(v-x)<.01 && Math.abs(w.line[i+1]-y)<.01)))throw new Error('EDA_PIN_ALREADY_WIRED:'+ref+':'+p.getState_PinNumber());entries.push({p,net:assignments[p.getState_PinNumber()]});}
}
for(const {p,net} of entries){if(net===null){const a=p.toAsync();a.setState_NoConnected(true);await a.done();continue;}
 const x=p.getState_X(),y=p.getState_Y(),rot=p.getState_Rotation();const d=rot===0?[20,0]:rot===180?[-20,0]:rot===270?[0,-20]:rot===90?[0,20]:null;if(!d)throw new Error('EDA_PIN_DIRECTION_INVALID');
 if(!await eda.sch_PrimitiveComponent.createNetPort('BI',net,x+d[0],y+d[1],rot,false))throw new Error('EDA_NET_PORT_CREATE_FAILED');
 if(!await eda.sch_PrimitiveWire.create([x,y,x+d[0],y+d[1]],net))throw new Error('EDA_WIRE_CREATE_FAILED');
}out.fanout_pin_count=entries.length;
'''
        elif op=='import_pcb':code+='''if(!await eda.pcb_Document.importChanges('''+json.dumps(b['schematic_root_uuid'])+'''))throw new Error('EDA_IMPORT_FAILED');'''
        elif op=='layout':code+='''
const cs=await eda.pcb_PrimitiveComponent.getAll();const byRef=new Map(cs.map(c=>[c.getState_Designator(),c]));
for(const s of args.positions)if(!byRef.has(s.ref))throw new Error('EDA_REFERENCE_MISSING:'+s.ref);
if((await eda.pcb_PrimitiveLine.getAll(undefined,11)).length || (await eda.pcb_PrimitivePolyline.getAll()).some(p=>p.getState_Layer()===11))throw new Error('EDA_OUTLINE_ALREADY_EXISTS');
for(const s of args.positions){const c=byRef.get(s.ref);if(!await eda.pcb_PrimitiveComponent.modify(c,{x:s.x_mm/.0254,y:s.y_mm/.0254,rotation:s.rotation||0}))throw new Error('EDA_MOVE_FAILED');}
const W=args.board_width_mm/.0254,H=args.board_height_mm/.0254;
const poly=eda.pcb_MathPolygon.createPolygon([0,0,'L',Number(W.toFixed(4)),0,Number(W.toFixed(4)),Number(H.toFixed(4)),0,Number(H.toFixed(4)),0,0]);
if(!poly||!await eda.pcb_PrimitivePolyline.create('',11,poly,4))throw new Error('EDA_OUTLINE_CREATE_FAILED');
out.board_mm={width:args.board_width_mm,height:args.board_height_mm};'''
        elif op=='tracks':code+='''const nets=new Set((await eda.pcb_Net.getAllNets()).map(n=>n.net));
for(const t of args.tracks)if(!nets.has(t.net))throw new Error('EDA_NET_MISSING:'+t.net);
for(const t of args.tracks){if(!await eda.pcb_PrimitiveLine.create(t.net,t.layer||1,t.x1_mm/.0254,t.y1_mm/.0254,t.x2_mm/.0254,t.y2_mm/.0254,t.width_mm/.0254))throw new Error('EDA_TRACK_CREATE_FAILED');}'''
        elif op=='autoroute':code+='''
if(typeof eda.pcb_Document.autoRouting!=='function')throw new Error('EDA_AUTOROUTING_UNAVAILABLE');
if(!(await eda.pcb_PrimitiveLine.getAll(undefined,11)).length)throw new Error('EDA_OUTLINE_REQUIRED');
out.routing=await eda.pcb_Document.autoRouting({RoutingNets:args.nets,ignoreNets:args.ignore_nets||[],layers:[1,2],existingPrimitiveMode:'keep'});
if(!out.routing || typeof out.routing.success!=='boolean')throw new Error('EDA_ROUTING_RESULT_UNAVAILABLE');'''
        if op in ('check','autoroute','tracks'):
            code+='''try {const drc=isPcb?eda.pcb_Drc:eda.sch_Drc;const r=await drc.check(true,false,false);out.drc={status:r===true?'passed':r===false?'failed':'unavailable',raw:r??null};if(r===false){try{out.drc.details=await drc.check(true,false,true);}catch(e){out.drc.details_error=String(e);}}}catch(e){out.drc={status:'unavailable',error:String(e)};}'''
        if op not in ('inspect','check','export'):
            code+='''out.saved=await (isPcb?eda.pcb_Document:eda.sch_Document).save();if(out.saved!==true)throw new Error('EDA_SAVE_NOT_CONFIRMED');'''
        with MCPClient(lambda r:self.audit(owner,key,directory,r)) as c:
            out=c.execute(code+READBACK,b['window_id'],120 if op=='autoroute' else 45)
            if out.get('netlist'):
                net=out.pop('netlist');(directory/(document+'-readback.net')).write_text(net)
                try:
                    parsed=json.loads(net);out['pin_nets']={v['props']['Designator']:{k:p.get('net') for k,p in v['pinInfoMap'].items()} for v in parsed.get('components',{}).values()}
                except (ValueError,KeyError,TypeError):out['netlist_parse_status']='unavailable'
            source=out.pop('source');(directory/(document+'.epro-source')).write_text(source)
            if op=='import_pcb':
                out['requires_ui_action']=True
                out['_job_status']='NEEDS_ACTION'
                out['next_action']='立创当前版本会弹出确认导入信息。应用修改后运行 check/inspect 读回，再继续布局。'
                out['import_verified']=False
            if op=='export':
                # Exported bytes come from official EDA APIs, never synthesized stand-ins.
                exports={'project.epro2':"eda.sys_FileManager.getProjectFile('BF-design',undefined,'epro2')",
                         document+'-netlist.net':f"eda.{'pcb' if pcb else 'sch'}_ManufactureData.getNetlistFile('netlist')"}
                if pcb:exports['gerber.zip']="eda.pcb_ManufactureData.getGerberFile('BF-Gerber')"
                else:exports['bom.csv']="eda.sch_ManufactureData.getBomFile('BOM','csv')"
                out['exports']={}
                for name,expression in exports.items():
                    try:
                        raw=c.execute(guard(b,document)+'''const f=await '''+expression+''';if(!f)throw new Error('EDA_EXPORT_UNAVAILABLE');const a=new Uint8Array(await f.arrayBuffer());let s='';for(let i=0;i<a.length;i++)s+=String.fromCharCode(a[i]);return {base64:btoa(s),bytes:a.length};''',b['window_id'],45)
                        data=base64.b64decode(raw['base64'],validate=True)
                        if not data or len(data)!=raw['bytes']:raise ValueError('EDA_EXPORT_BYTES_MISMATCH')
                        (directory/name).write_bytes(data);out['exports'][name]={'status':'exported','bytes':len(data)}
                    except Exception as exc:out['exports'][name]={'status':'unavailable','error':str(exc)[:400]}
            out.update(engine='JLCEDA Pro',operation=op,binding=b,scope=SCOPE,product_verified=False)
        return out
