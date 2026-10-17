"""Source extraction and deterministic report diagrams; no engineering dispatch."""
import hashlib
import json
from pathlib import Path
import re

from ..store import canonical, identity
from .repository import file_hash, name


def verify_input(folder):
    value = json.loads((folder/'report-input.json').read_text())
    if 'report_id' in value and value['report_id'] != 'RP-' + identity({k:v for k,v in value.items() if k != 'report_id'}):
        raise ValueError('REPORT_INPUT_IDENTITY')
    for a in value['assets']:
        if a['system_commit'] != value['system']['id']: raise ValueError('REPORT_ASSET_CANDIDATE')
        f = folder/name(a['local_path'])
        if f.is_symlink() or file_hash(f) != a['sha256']: raise ValueError('REPORT_ASSET_HASH')
    return value


def load_json(folder, path):
    return json.loads((folder/'sources/candidate'/path).read_text())


def schematic(folder):
    choices = []
    for p in (folder/'sources/candidate').glob('*/schematic-readback.json'):
        data = json.loads(p.read_text()); data = data.get('result', data)
        parts = [x for x in data.get('components', []) if x.get('componentType') == 'part']
        if parts and all('designator' in x and 'pins' in x for x in parts): choices.append((len(parts), str(p), {**data,'components':parts}))
    if not choices: raise ValueError('REPORT_NATIVE_PIN_READBACK_REQUIRED')
    return max(choices, key=lambda x:(x[0],x[1]))[2]


def fact_pack(folder):
    v = verify_input(folder); s = v['system']; c = folder/'sources/candidate'
    sch = schematic(folder)
    components = [{'ref': p['designator'], 'part': p.get('manufacturerId') or p.get('name'),
                   'role': p.get('otherProperty',{}).get('EasyEDA Agent Role'),
                   'pins': [{'pin': x['pinNumber'], 'name': x['pinName'], 'net': x['net'], 'nc': x['noConnected']} for x in p['pins']]}
                  for p in sch['components']]
    src = []
    for f in sorted(c.rglob('*')):
        if f.is_file() and f.suffix in ('.c','.h','.py'):
            text = f.read_text()
            symbols = re.findall(r'^\s*(?:static\s+)?(?:void|bool|int|uint\w+|ret_code_t|app_actions_t|app_action_t)\s+([a-zA-Z_]\w*)\s*\(',text,re.M)
            src.append({'path': str(f.relative_to(c)), 'sha256': file_hash(f), 'symbols': symbols, 'bytes': f.stat().st_size})
    gates = {k: {'status': a['status'], 'scope': a.get('scope'), 'findings': a.get('findings',{})} for k,a in s['validations'].items()}
    cadjob = next(j for j,a in s['jobs'].items() if 'project-cad_summary.json' in a['artifacts'])
    cad = json.loads((folder/'sources/jobs'/cadjob/'project-cad_summary.json').read_text())
    assembly = load_json(folder, 'assembly.json')
    return {'report_id': v['report_id'], 'system_commit': s['id'], 'adopted_system': v['adopted_system'],
            'project_title': v['project']['title'], 'files': len(s['files']),
            'components': components, 'parameters': load_json(folder, 'project-chain/interface-params.json'),
            'cad': cad, 'assembly_parts': [{'id':p['id'],'name':p['name'],'role':p['role'],'geometry':p['geometry']} for p in assembly['parts']],
            'gates': gates, 'source_index': src,
            'report_method': 'Actual native symbols and frozen pin-net graph are rearranged for readable connected circuits; native engineering files remain attached. Firmware sequence is checked against current frozen source, not an old event export.'}


def source_ref(source, folder):
    if not isinstance(source,dict) or not source.get('symbol'): raise ValueError('REPORT_SOURCE_LOCATOR_REQUIRED')
    path = name(source.get('path',''))
    f = folder/'sources/candidate'/path
    if not f.is_file() or f.is_symlink() or source['symbol'] not in f.read_text(): raise ValueError('REPORT_SOURCE_LOCATOR_STALE:'+path)


def strings(values, key):
    if not isinstance(values,list) or not values or any(not isinstance(x,str) or not x.strip() for x in values):
        raise ValueError('REPORT_TEXT_REQUIRED:'+key)


def check_author(content, scope, value, folder):
    if scope == 'power':
        groups = content.get('circuit_groups', [])
        if not 3 <= len(groups) <= 8: raise ValueError('REPORT_CIRCUIT_GROUPS_REQUIRED')
        refs = [x for g in groups for x in g.get('refs',[])]
        expected = sorted(p['designator'] for p in schematic(folder)['components'])
        if sorted(refs) != expected: raise ValueError('REPORT_CIRCUIT_COVERAGE:'+','.join(sorted(set(expected)-set(refs))))
        if len({g['id'] for g in groups}) != len(groups): raise ValueError('REPORT_CIRCUIT_GROUP_ID')
        for g in groups:
            name(g['id']); strings(g.get('notes'), 'circuit notes')
            if not g.get('title'): raise ValueError('REPORT_CIRCUIT_TITLE')
        if not content.get('pcb_regions'): raise ValueError('REPORT_PCB_REGIONS_REQUIRED')
        for region in content['pcb_regions']:
            if not region.get('name') or not region.get('description') or not region.get('refs') or not set(region['refs']) <= set(expected):
                raise ValueError('REPORT_PCB_REGION_REFERENCE')
        strings(content.get('energy_interpretation'), 'energy_interpretation')
        strings(content.get('conclusions'), 'conclusions')
    elif scope == 'firmware':
        actors = content.get('participants',[]); ids = {p['id'] for p in actors}
        if len(ids) != len(actors) or not 4 <= len(ids) <= 6: raise ValueError('REPORT_SEQUENCE_PARTICIPANTS')
        messages = content.get('messages',[])
        if not 12 <= len(messages) <= 32: raise ValueError('REPORT_SEQUENCE_MESSAGES_REQUIRED')
        if not {'start','sample','notify','error','disconnect'} <= {x.get('kind') for x in messages}:
            raise ValueError('REPORT_SEQUENCE_BRANCHES_REQUIRED')
        for message in messages:
            if message.get('from') not in ids or message.get('to') not in ids or not message.get('label') or not message.get('time'):
                raise ValueError('REPORT_SEQUENCE_MESSAGE')
            source_ref(message.get('source'), folder)
        for constraint in content.get('constraints',[]): source_ref(constraint.get('source'), folder)
        strings(content.get('explanations'), 'sequence explanations')
    elif scope == 'lead':
        if not content.get('summary') or not content.get('task') or len(content.get('system_modules',[])) < 4:
            raise ValueError('REPORT_OVERVIEW_REQUIRED')
        pages = content.get('pages',[])
        if sorted(p.get('page') for p in pages) != list(range(1,9)) or any(not p.get('conclusion') or not p.get('notes') for p in pages):
            raise ValueError('REPORT_EIGHT_PAGES_REQUIRED')
        reqs = content.get('requirements',[])
        if {x.get('gate') for x in reqs} != set(value['system']['validations']): raise ValueError('REPORT_REQUIREMENTS_COVERAGE')
        strings(content.get('assembly_notes'), 'assembly_notes'); strings(content.get('handoff'), 'handoff')


def connected_circuits(folder, power, output):
    """Rearrange frozen native symbols and route their exact pin-net graph.

    Grid search routes around symbol bodies. Crossings are drawn without junctions;
    junction dots only join the same named net. Ground uses conventional symbols.
    """
    import copy, heapq, math
    from xml.etree import ElementTree as E
    ns = 'http://www.w3.org/2000/svg'; E.register_namespace('',ns)
    tag = lambda x:'{'+ns+'}'+x
    original = E.parse(folder/'sources/previews/schematic.svg').getroot()
    by_ref = {p['designator']:p for p in schematic(folder)['components']}
    native = {}
    for p in by_ref.values():
        for group in original.iter(tag('g')):
            if group.get('c_partid') == 'part' and any(x.get('id','').startswith(p['primitiveId']+'-') for x in group.iter()):
                native[p['designator']] = group; break
    if set(native) != set(by_ref): raise ValueError('REPORT_NATIVE_SYMBOL_COVERAGE')
    colors = ['#006fb7','#31866e','#8a62b2','#b07223','#275f83','#a64f63']
    output.mkdir(parents=True,exist_ok=True); records=[]; pin_binding=[]
    for gi, group in enumerate(power['circuit_groups']):
        refs=group['refs']; parts=[by_ref[r] for r in refs]
        big = next((p for p in parts if p['bbox']['maxX']-p['bbox']['minX']>200), None)
        # Small devices remain close to their functional core. Native dimensions
        # and native pin coordinates are retained under rigid layout transforms.
        placements={}; sizes={}
        for p in parts:
            b=p['bbox']; xs=[b['minX'],b['maxX']]+[x['x'] for x in p['pins']]; ys=[-b['maxY'],-b['minY']]+[-x['y'] for x in p['pins']]
            sizes[p['designator']] = (min(xs)-28,min(ys)-30,max(xs)+28,max(ys)+24)
        if big:
            others=[p for p in parts if p is not big]; height=max(600, 105*math.ceil(len(others)/2)+90); width=1100
            b=sizes[big['designator']];placements[big['designator']]=(410-b[0],height/2-(b[1]+b[3])/2)
            for i,p in enumerate(others):
                b=sizes[p['designator']]; col=i%2; row=i//2
                placements[p['designator']]=((95 if col==0 else 840)-b[0],85+row*105-b[1])
        else:
            cols=min(3,len(parts)); rows=math.ceil(len(parts)/cols)
            maxw=max(sizes[p['designator']][2]-sizes[p['designator']][0] for p in parts)
            maxh=max(sizes[p['designator']][3]-sizes[p['designator']][1] for p in parts)
            cw=max(270,maxw+100); ch=max(160,maxh+85); width=cw*cols+80; height=ch*rows+70
            for i,p in enumerate(parts):
                b=sizes[p['designator']]; placements[p['designator']]=(55+(i%cols)*cw-b[0],65+(i//cols)*ch-b[1])
        # Pilot page composition. Positions are presentation only; each symbol's
        # geometry and every connection still come from the frozen native graph.
        hints = [
            ({'J1','D2','T1','D1'},(1100,400),{'J1':(245,160),'D2':(425,160),'T1':(660,175),'D1':(870,160)}),
            ({'C2','U4','J2','L1'},(1260,480),{'C2':(270,330),'C9':(430,330),'DZ1':(590,330),'U3':(475,165),'R3':(275,130),'J2':(680,160),'U4':(895,200),'L1':(1080,170),'C5':(1060,330),'C10':(1175,330)}),
            ({'U5','U6','R1'},(1180,450),{'R1':(270,130),'R2':(390,235),'C1':(490,235),'U5':(625,205),'U6':(845,235),'C13':(835,110),'R8':(1040,110)}),
            ({'Q1','R6'},(790,340),{'R6':(320,160),'Q1':(590,160)}),
            ({'U1','Y1'},(1260,660),{'U1':(685,335),'Y1':(1030,290),'AE1':(1030,485),'C11':(960,390),'C12':(1120,390),'C3':(325,170),'C4':(450,170),'C6':(325,310),'C7':(450,310),'C8':(390,460),'J3':(1040,120)}),
            ({'U2','J4'},(1160,440),{'U2':(650,220),'J4':(985,220),'R7':(335,120),'R4':(335,240),'R5':(335,340)})]
        angles={}
        for required, canvas_size, positions in hints:
            if required<=set(refs) and set(refs)<=set(positions):
                width,height=canvas_size
                for p in parts:
                    xx,yy=positions[p['designator']];placements[p['designator']]=(xx-p['x'],yy+p['y'])
                    if p['designator'] in {'R2','C1','C2','C9','C5','C10','C11','C12','C3','C4','C6','C7','C8'}:angles[p['designator']]=90
                break
        def transform(p,x,y):
            dx,dy=placements[p['designator']];a=math.radians(angles.get(p['designator'],0));cx,cy=p['x'],-p['y']
            return (cx+dx+(x-cx)*math.cos(a)-(y-cy)*math.sin(a),cy+dy+(x-cx)*math.sin(a)+(y-cy)*math.cos(a))
        root=E.Element(tag('svg'),{'viewBox':f'0 0 {width} {height}','width':str(width),'height':str(height)})
        for item in original:
            if item.tag in (tag('defs'),tag('style')):root.append(copy.deepcopy(item))
        E.SubElement(root,tag('rect'),{'width':str(width),'height':str(height),'fill':'white'})
        E.SubElement(root,tag('text'),{'x':'18','y':'25','font-size':'17','font-family':'Arial, sans-serif','fill':colors[gi%len(colors)]}).text=group['title']
        lines=E.SubElement(root,tag('g'),{'fill':'none','stroke':'#15597f','stroke-width':'1.5','stroke-linecap':'round','stroke-linejoin':'round'})
        labels=E.SubElement(root,tag('g'),{'fill':'#15597f','font-size':'11','font-family':'Arial, sans-serif'})
        obstacles=set(); ends={}; nc=[]
        grid=5; maxx=math.ceil(width/grid)-3;maxy=math.ceil(height/grid)-3
        for p in parts:
            dx,dy=placements[p['designator']]; b=p['bbox']
            corners=[transform(p,x,y) for x in (b['minX'],b['maxX']) for y in (-b['maxY'],-b['minY'])]
            xmin=min(x for x,y in corners);xmax=max(x for x,y in corners);ymin=min(y for x,y in corners);ymax=max(y for x,y in corners)
            # Body only is a routing obstacle; pins extend outside it.
            for xx in range(math.floor((xmin-5)/grid),math.ceil((xmax+5)/grid)+1):
                for yy in range(math.floor((ymin-5)/grid),math.ceil((ymax+5)/grid)+1):obstacles.add((xx,yy))
            for pin in p['pins']:
                xy=transform(p,pin['x'],-pin['y'])
                a=math.radians(pin['rotation']-angles.get(p['designator'],0));vx=round(math.cos(a));vy=-round(math.sin(a))
                end=(round((xy[0]+vx*25)/grid),round((xy[1]+vy*25)/grid))
                record={'ref':p['designator'],'pin':pin['pinNumber'],'net':pin['net'],'nc':pin['noConnected'],
                        'point':list(xy),'end':list(end),'group':group['id']}
                pin_binding.append(record)
                if pin['noConnected'] or not pin['net']:nc.append((xy,bool(pin['noConnected'])));continue
                ends.setdefault(pin['net'],[]).append((xy,end))
                E.SubElement(lines,tag('path'),{'d':f'M{xy[0]:g},{xy[1]:g} L{end[0]*grid:g},{end[1]*grid:g}',
                            'data-net':pin['net'],'data-ref':p['designator'],'data-pin':pin['pinNumber']})
        occupied={}; edge_records=[]; route_failures=[]
        def route(start, targets, net):
            queue=[(0,0,start,None)]; costs={(start,None):0}; previous={}; found=None
            while queue:
                _,cost,point,direction=heapq.heappop(queue)
                if cost != costs.get((point,direction)):continue
                if point in targets:found=(point,direction);break
                for dd in ((1,0),(-1,0),(0,1),(0,-1)):
                    q=(point[0]+dd[0],point[1]+dd[1])
                    if q in obstacles and q not in targets or not (3<=q[0]<=maxx and 9<=q[1]<=maxy):continue
                    penalty=1+(2 if direction is not None and direction!=dd else 0)
                    if q in occupied and occupied[q]!=net:penalty+=14
                    cc=cost+penalty; state=(q,dd)
                    if cc>=costs.get(state,1e30):continue
                    costs[state]=cc;previous[state]=(point,direction)
                    heuristic=min(abs(q[0]-t[0])+abs(q[1]-t[1]) for t in targets)
                    heapq.heappush(queue,(cc+heuristic,cc,q,dd))
            if found is None:return None
            result=[found[0]]
            while found in previous:
                found=previous[found];result.append(found[0])
            return result[::-1]
        for net, connections in sorted(ends.items(),key=lambda x:(x[0] in ('GND','supply_1v8','storage_rail'),-len(x[1]),x[0])):
            if net=='GND':
                for _,point in connections:
                    x,y=point[0]*grid,point[1]*grid
                    E.SubElement(lines,tag('path'),{'d':f'M{x},{y} v8 m-7,0 h14 m-11,4 h8 m-6,4 h4','data-net':net})
                continue
            tree={connections[0][1]}; edges=[]
            for _,point in connections[1:]:
                path=route(point,tree,net)
                if path is None:raise ValueError('REPORT_WIRE_ROUTE_FAILED:'+group['id']+':'+net)
                E.SubElement(lines,tag('path'),{'d':'M'+' L'.join(f'{a*grid},{b*grid}' for a,b in path), 'data-net':net})
                if path[-1] in tree and len(connections)>2:
                    E.SubElement(labels,tag('circle'),{'cx':str(path[-1][0]*grid),'cy':str(path[-1][1]*grid),'r':'2.5'})
                tree.update(path);edges.append([list(x) for x in path])
                for point2 in path:occupied.setdefault(point2,net)
            # Named ports live in a dedicated margin, away from IC pin text.
            external=any(any(pin['net']==net and not pin['noConnected'] for pin in p['pins']) for p in by_ref.values() if p['designator'] not in refs)
            if external or len(connections)==1:
                port=(33,15+6*sum(1 for r in edge_records if r['port']))
                path=route(port,tree,net)
                if path is None:raise ValueError('REPORT_PORT_ROUTE_FAILED:'+net)
                E.SubElement(lines,tag('path'),{'d':'M'+' L'.join(f'{a*grid},{b*grid}' for a,b in path),'data-net':net})
                x,y=port[0]*grid,port[1]*grid
                E.SubElement(labels,tag('rect'),{'x':str(x-3),'y':str(y-3),'width':'6','height':'6','fill':'white','stroke':'#15597f'})
                E.SubElement(labels,tag('text'),{'x':'8','y':str(y-5),'font-size':'10'}).text=net
                edges.append([list(x) for x in path]);tree.update(path)
            edge_records.append({'net':net,'pins':len(connections),'routes':edges,'port':external or len(connections)==1,
                                 'port_point':[port[0]*grid,port[1]*grid] if external or len(connections)==1 else None})
        for p in parts:
            dx,dy=placements[p['designator']]; symbol=copy.deepcopy(native[p['designator']])
            for child in list(symbol):
                if child.get('c_partid')=='part_attr':symbol.remove(child)
            angle=angles.get(p['designator'],0)
            symbol.set('transform',f'translate({dx:g} {dy:g}) rotate({angle} {p["x"]} {-p["y"]})'); root.append(symbol)
            b=p['bbox'];corners=[transform(p,x,y) for x in (b['minX'],b['maxX']) for y in (-b['maxY'],-b['minY'])]
            tx=min(x for x,y in corners);ty=min(y for x,y in corners)-19
            title=E.SubElement(root,tag('text'),{'x':str(tx),'y':str(ty),'font-size':'12','font-family':'Arial, sans-serif','fill':'#192f47'})
            title.text=p['designator']+' '+str(p.get('otherProperty',{}).get('Value') or p.get('manufacturerId') or p.get('name') or '')[:28]
        for (x,y),explicit_nc in nc:
            if explicit_nc:E.SubElement(root,tag('path'),{'d':f'M{x-3},{y-3} l6,6 m0,-6 l-6,6','stroke':'#bd4d56','stroke-width':'1.2'})
            else:E.SubElement(root,tag('circle'),{'cx':str(x),'cy':str(y),'r':'3','stroke':'#bd4d56','stroke-width':'1.2','fill':'white','data-open-pin':'true'})
        dest=output/(group['id']+'.svg'); E.ElementTree(root).write(dest,encoding='utf-8',xml_declaration=True)
        records.append({'id':group['id'],'file':dest.name,'title':group['title'],'refs':refs,
                        'native_symbols':len(parts),'width':width,'height':height,'nets':edge_records})
    # The manifest is the graph consumed by the drawing, including every NC.
    expected=sorted((p['designator'],x['pinNumber'],x['net'],bool(x['noConnected'])) for p in by_ref.values() for x in p['pins'])
    actual=sorted((p['ref'],p['pin'],p['net'],bool(p['nc'])) for p in pin_binding)
    if expected!=actual:raise ValueError('REPORT_DRAWN_NETLIST_MISMATCH')
    graph={'schema_version':'bf-connected-circuit-report-v1','source_sha256':file_hash(folder/'sources/previews/schematic.svg'),
           'groups':records,'pins':pin_binding,'components':len(by_ref),'pin_count':len(actual),
           'netlist_sha256':identity(expected),'drawing_netlist_sha256':identity(actual),'graph_equal':True,
           'method':'frozen native symbols; rigid layout transforms; actual local wires; named cross-module ports and common ground',
           'native_engineering_modified':False}
    # A complete sheet links the real cross-module ports to shared wire buses.
    # Separate enlarged sheets remain available for component/pin inspection.
    occurrences={}
    for g in records:
        for n in g['nets']:
            if n['port_point']:occurrences.setdefault(n['net'],[]).append((g,n))
    shared={k:v for k,v in occurrences.items() if len(v)>1}
    width=max(g['width'] for g in records)+340
    height=sum(g['height']+35 for g in records)+100
    overview=E.Element(tag('svg'),{'width':str(width),'height':str(height),'viewBox':f'0 0 {width} {height}'})
    E.SubElement(overview,tag('rect'),{'width':str(width),'height':str(height),'fill':'white'})
    offsets={};yy=90
    for g in records:
        offsets[g['id']]=yy
        E.SubElement(overview,tag('rect'),{'x':'330','y':str(yy),'width':str(g['width']),'height':str(g['height']),
                     'rx':'7','fill':'white','stroke':'#d8e5f1'})
        yy+=g['height']+35
    cross=[]
    for i,(net,ports) in enumerate(sorted(shared.items())):
        bx=38+i*34
        targets=[(330+n['port_point'][0],offsets[g['id']]+n['port_point'][1]) for g,n in ports]
        low,high=min(y for x,y in targets),max(y for x,y in targets)
        E.SubElement(overview,tag('path'),{'d':f'M{bx},{low} V{high}','fill':'none','stroke':'#15597f','stroke-width':'1.6','data-net':net})
        title=E.SubElement(overview,tag('text'),{'x':str(bx+3),'y':str(low-8),'font-size':'12','fill':'#15597f',
                         'transform':f'rotate(-65 {bx+3} {low-8})'});title.text=net
        for x,y in targets:
            # Crossings have no junction dots. Dots join only this named bus.
            E.SubElement(overview,tag('path'),{'d':f'M{bx},{y} H{x}','fill':'none','stroke':'#15597f','stroke-width':'1.6','data-net':net})
            E.SubElement(overview,tag('circle'),{'cx':str(bx),'cy':str(y),'r':'3','fill':'#15597f','data-net':net})
        cross.append({'net':net,'groups':[g['id'] for g,n in ports],'endpoints':targets})
    for g in records:
        pane=E.parse(output/g['file']).getroot()
        # The overall wire bus carries these names, so remove the duplicate
        # local port labels while retaining every native symbol and local wire.
        for parent in pane.iter():
            for child in list(parent):
                if child.tag==tag('text') and child.get('x')=='8' and child.text in shared:parent.remove(child)
        body=E.SubElement(overview,tag('g'),{'transform':f'translate(330 {offsets[g["id"]]})'})
        for child in pane:
            if child.tag==tag('rect') and child.get('fill')=='white' and child.get('width')==str(g['width']):continue
            body.append(copy.deepcopy(child))
    E.ElementTree(overview).write(output/'schematic-connected.svg',encoding='utf-8',xml_declaration=True)
    graph['cross_module_wires']=cross;graph['overview_file']='schematic-connected.svg'
    (output/'circuit-graph.json').write_text(canonical(graph));return graph


def rasterize(source, output):
    """Headless Chromium implements the native SVG color filters faithfully."""
    import subprocess, os
    # Locate from the configured Pi source, not a current working directory.
    from ..runtime_config import PI
    skill=PI/'packages/bf-harness/resources/skills/bf-engineering-report/scripts/rasterize.mjs'
    node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
    proc=subprocess.run([str(node),str(skill),str(source),str(output)],capture_output=True,text=True,timeout=120)
    if proc.returncode:raise ValueError('REPORT_RASTER_FAILED:'+proc.stderr[-1600:])


def native_svg_xy(root, layer_id, x, y):
    """Apply the actual layer and ancestor transforms, in SVG composition order."""
    import math
    def locate(node, chain):
        chain=chain+[node.get('transform','')]
        if node.get('id')==layer_id:return chain
        for child in node:
            found=locate(child,chain)
            if found is not None:return found
        return None
    chain=locate(root,[])
    if chain is None:raise ValueError('REPORT_PCB_NATIVE_LAYER_MISSING:'+layer_id)
    for transform in reversed(chain):
        operations=re.findall(r'([A-Za-z]+)\s*\(([^)]*)\)',transform)
        for name,args in reversed(operations):
            a=[float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',args)]
            if name=='translate':x+=a[0];y+=a[1] if len(a)>1 else 0
            elif name=='scale':x*=a[0];y*=a[1] if len(a)>1 else a[0]
            elif name=='matrix':x,y=a[0]*x+a[2]*y+a[4],a[1]*x+a[3]*y+a[5]
            elif name=='rotate':
                cx,cy=a[1:3] if len(a)>1 else (0,0);r=math.radians(a[0]);x,y=x-cx,y-cy
                x,y=x*math.cos(r)-y*math.sin(r)+cx,x*math.sin(r)+y*math.cos(r)+cy
            else:raise ValueError('REPORT_PCB_TRANSFORM_UNSUPPORTED:'+name)
    return x,y


def pcb_annotations(folder, power, output):
    from xml.etree import ElementTree as E
    ns='http://www.w3.org/2000/svg';tag=lambda x:'{'+ns+'}'+x
    p=next((folder/'sources/candidate').glob('*/pcb-readback.json'))
    data=json.loads(p.read_text());data=data.get('result',data)
    parts={x['designator']:x for x in data['components'] if x.get('designator')}
    records=[];sources={}
    for side in ('top','bottom'):
        src=folder/'sources/previews'/('pcb-'+side+'.svg');root=E.parse(src).getroot();sources[side]=file_hash(src)
        overlay=E.SubElement(root,tag('g'),{'id':'bf-report-pcb-markers','font-family':'Arial, sans-serif'})
        for i,region in enumerate(power['pcb_regions']):
            refs=[r for r in region['refs'] if r in parts]
            if not refs:raise ValueError('REPORT_PCB_MARKER_MISSING')
            part=parts[refs[0]];native_x=part['x']*.0254;native_y=part['y']*.0254
            x,y=native_svg_xy(root,'l-'+side+'-copper',native_x,native_y)
            E.SubElement(overlay,tag('circle'),{'cx':str(x),'cy':str(y),'r':'1.4','fill':'#ffffff','stroke':'#0086d6','stroke-width':'.3'})
            E.SubElement(overlay,tag('text'),{'x':str(x),'y':str(y+.5),'font-size':'1.4','text-anchor':'middle','fill':'#005c9f'}).text=str(i+1)
            if side=='top':records.append({'number':i+1,'name':region['name'],'description':region['description'],
                                           'refs':refs,'marker_ref':refs[0],'xy_mm':[native_x,native_y],'svg_xy':{side:[x,y]}})
            else:records[i]['svg_xy'][side]=[x,y]
        E.ElementTree(root).write(output/('pcb-'+side+'-annotated.svg'),encoding='utf-8',xml_declaration=True)
    (output/'pcb-annotations.json').write_text(canonical({'source_sha256':file_hash(p),'source_previews':sources,'regions':records,'units':'mm','coordinate_transform':'native mil * 0.0254, then exact SVG layer and ancestor transforms'}))
    return records


def energy_ledger(folder, channels):
    import numpy as np
    params=load_json(folder,'project-chain/interface-params.json');rawfile=next((folder/'sources/jobs').glob('*/project-trace.raw'))
    text=(folder/'sources/candidate/project-chain/chain_joint.cir').read_text()
    match=re.search(r'^Iload\s+(\S+)\s+(\S+)\s+PWL\((.*?)\)',text,re.M|re.S|re.I)
    if not match:raise ValueError('REPORT_LOAD_PWL_REQUIRED')
    values=[float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',match.group(3))]
    points=np.array(values).reshape(-1,2);t=np.asarray(channels['time']);vs=np.asarray(channels['v(storage_rail)']);vm=np.asarray(channels['v(mcu_rail)']);vr=np.asarray(channels['v(teng_rect)'])
    currents=np.interp(t,points[:,0],points[:,1]);isece=params['sece']['g_se_s']*np.maximum(vr-vs,0)
    integral=lambda y:float(np.trapezoid(y,t))
    c=params['storage']['c_store_f'];e0=.5*c*vs[0]**2;e1=.5*c*vs[-1]**2
    return {'schema_version':'bf-report-energy-ledger-v1','raw_sha256':file_hash(rawfile),'netlist_sha256':file_hash(folder/'sources/candidate/project-chain/chain_joint.cir'),
            'units':{'time':'s','voltage':'V','current':'A','energy':'J'},'span_s':[float(t[0]),float(t[-1])],
            'initial_storage_J':e0,'final_storage_J':e1,'storage_delta_J':e1-e0,
            'sece_received_J':integral(vs*isece),'leakage_J':integral(vs*vs/params['storage']['r_leak_ohm']),
            'source_delivered_J':-integral(np.asarray(channels['v(teng_oc)'])*np.asarray(channels['i(bvoc)'])),
            'load_port_absorbed_J':integral(vm*currents),'actual_load_charge_C':integral(currents),
            'negative_mcu_samples':int(np.count_nonzero(vm<0)),'minimum_mcu_V':float(vm.min()),
            'minimum_supply_V':float(min(channels['v(supply_1v8)'])),'actual_pwl_points':len(points),
            'load_nodes':list(match.group(1,2)),
            'integration':'signed trapezoidal integration of every original RAW sample; load current interpolated from actual solver PWL; no anomaly samples removed',
            'conclusion':('Manual switch output has negative voltage samples. Signed load-port energy is diagnostic. Efficiency is unavailable until the switch/load model is repaired.' if np.any(vm<0) else 'No negative MCU-rail samples observed. Signed port-energy integrals are supplied; conversion efficiency requires a matching device and energy-boundary model.')}


def cad_views(folder, output):
    """Read existing mesh and assembly dimensions. No CAD rebuild or simulation."""
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    meshfile=next((folder/'sources/jobs').glob('*/project-preview-mesh.json'))
    mesh=json.loads(meshfile.read_text()); vertices=np.array(mesh['vertices']); faces=np.array(mesh['triangles'])
    assembly=load_json(folder,'assembly.json')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig=plt.figure(figsize=(9,6.2),facecolor='white');ax=fig.add_subplot(111,projection='3d')
    poly=Poly3DCollection(vertices[faces],facecolors='#a9c9d9',edgecolors='none',alpha=.96,rasterized=True);ax.add_collection3d(poly)
    low=vertices.min(axis=0);high=vertices.max(axis=0)
    ax.set(xlim=(low[0],high[0]),ylim=(low[1],high[1]),zlim=(low[2],high[2]+10),xlabel='X / mm',ylabel='Y / mm',zlabel='Z / mm')
    ax.set_box_aspect((high-low+np.array([0,0,15])));ax.view_init(25,-50);ax.grid(False)
    fig.subplots_adjust(left=0,right=1,bottom=0,top=1);fig.savefig(output/'cad-isometric.png',dpi=220);plt.close(fig)
    # Exploded layer envelopes use the exact declared dimensions and transforms.
    # This is a labelled assembly drawing; the native mesh view above is retained.
    fig=plt.figure(figsize=(9,6.2),facecolor='white');ax=fig.add_subplot(111,projection='3d')
    layers=[p for p in assembly['parts'] if p['geometry'].get('kind')=='box' and p['id'] in
            ('acrylic_backing_neg','copper_neg','ptfe_neg','gap_separation','pi_pos','copper_pos','acrylic_backing_pos')]
    def box(center,size):
        x,y,z=center;sx,sy,sz=np.array(size)/2
        v=np.array([[x+dx*sx,y+dy*sy,z+dz*sz] for dz in (-1,1) for dy in (-1,1) for dx in (-1,1)])
        return [[v[i] for i in face] for face in ((0,1,3,2),(4,5,7,6),(0,1,5,4),(2,3,7,6),(0,2,6,4),(1,3,7,5))]
    for i,p in enumerate(layers):
        if p['id']=='gap_separation':continue
        g=p['geometry'];center=list(g['center_mm']);center[2]+=i*13
        col=p.get('color',[.7,.8,.9]);ax.add_collection3d(Poly3DCollection(box(center,g['size_mm']),facecolors=col,edgecolors='#6d879b',linewidths=.35,alpha=.9))
        ax.text(78,0,center[2],f'{i+1}  {p["id"]}',fontsize=8,color='#143a59')
    ax.set(xlim=(-80,120),ylim=(-60,60),zlim=(0,105));ax.set_box_aspect((200,120,105));ax.view_init(20,-60);ax.set_axis_off()
    fig.subplots_adjust(left=0,right=1,bottom=0,top=1);fig.savefig(output/'cad-exploded.png',dpi=220);plt.close(fig)
    result={'mesh_sha256':file_hash(meshfile),'assembly_sha256':file_hash(folder/'sources/candidate/assembly.json'),
            'bounds_mm':(high-low).tolist(),'parts':len(assembly['parts']),
            'exploded_layers':[{'id':p['id'],'size_mm':p['geometry']['size_mm'],'center_mm':p['geometry']['center_mm']} for p in layers],
            'exploded_view':'dimension-bound layer envelopes; visual separation offset is presentation only'}
    (output/'cad-views.json').write_text(canonical(result));return result


def build_report(repo, owner, body, root, value):
    from .repository_reports import authors, validate_content
    records = authors(root)
    if set(records) != {'power','firmware','lead'}: raise ValueError('REPORT_THREE_PI_AUTHORS_REQUIRED')
    for k,v in records.items(): validate_content(v['content'], k, value, root/'input')
    bindings = {p.name: file_hash(p) for p in Path(__file__).parent.glob('report_*.py')}
    from ..runtime_config import PI
    resources=PI/'packages/bf-harness/resources/skills/bf-engineering-report'
    bindings.update({'resources/'+str(p.relative_to(resources)):file_hash(p) for p in resources.rglob('*') if p.is_file()})
    bid = 'RB-' + identity({'input':value['report_id'], 'authors':{k:v['sha256'] for k,v in records.items()}, 'renderer':bindings})
    dest = root/'builds'/bid
    def apply(db):
        dest.mkdir(parents=True,exist_ok=True)
        existing = dest/'quality.json'
        if existing.exists():
            old=json.loads(existing.read_text())
            if old['status'] != 'PASS': raise ValueError('REPORT_FAILED_BUILD_RETAINED')
            for path, ref in old['outputs'].items():
                if file_hash(dest/name(path)) != ref['sha256']: raise ValueError('REPORT_OUTPUT_TAMPER')
            return {'id':bid,'report_id':value['report_id'],'project_id':value['project']['id'],
                    'system_commit':value['system']['id'],'status':'PASS','reused':True,'outputs':old['outputs']}
        from .contracts import sealed
        sealed(dest/'renderer-binding.json', bindings)
        script = Path(__file__).with_name('report_render.py')
        runtime = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
        python = str(runtime if runtime.is_file() else __import__('sys').executable)
        import os, subprocess
        env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[3])}
        proc=subprocess.run([python,'-m','bfworld.agentlab.design_lab.report_render','--input',str(root/'input'),
                             '--authors',str(root/'authors'),'--output',str(dest)],capture_output=True,text=True,env=env,timeout=180)
        if proc.returncode: raise ValueError('REPORT_BUILD_FAILED:'+proc.stdout[-1000:]+proc.stderr[-3000:])
        quality = json.loads((dest/'quality.json').read_text())
        if quality['status'] != 'PASS': raise ValueError('REPORT_QUALITY_FAILED:'+canonical(quality['checks']))
        pointer={'id':bid,'quality_sha256':identity(quality)}
        (root/'CURRENT-BUILD.json').write_text(canonical(pointer))
        system_pointer=repo.root/'reports/by-system'/(value['system']['id']+'.json')
        system_pointer.parent.mkdir(exist_ok=True);system_pointer.write_text(canonical({'report_id':value['report_id'],**pointer}))
        repo.lab.event(owner,'engineering_report_checked',{'report_id':value['report_id'],'build_id':bid,
                       'system_commit':value['system']['id'],'status':'PASS'},db)
        return {'id':bid,'report_id':value['report_id'],'project_id':value['project']['id'],
                'system_commit':value['system']['id'],'status':'PASS','checks':quality['checks'],
                'outputs':quality['outputs']}
    return repo.mutate(owner, body, apply)
