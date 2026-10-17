"""Local, bounded parameterized engineering adapters; no arbitrary participant code."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
from .store import canonical, identity
from .jlceda import JLCEDA, SKILL_PATHS, SCOPE as EDA_SCOPE, validate as validate_eda
from .eda_mcp import SERVER as EDA_SERVER
from . import product_build, deployment, tinyml, event_design, references, engineering_projects, beam_event, simulation_chain, scientific_figures, door_system, door_selfpower

TEMPLATES = Path(__file__).with_name('engineering_templates')
from .runtime_config import BLENDER, COMSOL, HOME_ROOT
from .design_lab.native_slot import native_slot
SPECS = {
    'blender': {'template': 'enclosure-v1', 'defaults': {'length_mm':80., 'width_mm':50., 'height_mm':25., 'wall_mm':2.},
                'ranges': {'length_mm':(30,300),'width_mm':(25,300),'height_mm':(15,150),'wall_mm':(1,6)},
                'scope':'尺寸参数化外壳、元件占位、GLB 与渲染；未验证制造、公差或防护性能。'},
    'comsol': {'template':'cantilever-static-v1', 'defaults': {'length_mm':50.,'width_mm':10.,'thickness_mm':1.,'young_gpa':200.,'force_n':.1},
               'ranges': {'length_mm':(10,200),'width_mm':(2,50),'thickness_mm':(.5,10),'young_gpa':(1,250),'force_n':(.001,10)},
               'scope':'均匀悬臂梁、线弹性静力、固定根部、端面均布力；两档网格，非压电或整机验证。'}
}
SKILLS = {
 'door-selfpower': door_selfpower.SKILL,
 'door-system': door_system.SKILL,
 'scientific-figures': scientific_figures.SKILL,
 'closed-simulation': simulation_chain.SKILL,
 'beam-event': beam_event.SKILL,
 'engineering-project': engineering_projects.SKILL,
 'engineering-delivery': '# 完整数字产品交付\n调用 bf_product delivery_inspect 读取当前适用的依赖清单与统一阶段判定；每项按输入依据、原生文件、真实检查和下游影响推进。先 publish_file，再 delivery_bind 绑定文件ID和实际job ID。未知需求用显式假设继续。几何、仿真、原生EDA、目标固件、接收回放必须属于同一产品；修改后检查 stale。delivery_package 打包文件与缺口，不自动通过验收。文件存在/工具成功/文献校准/实测是不同事实。制造与烧录准备可以先完成，实物结果保留未执行。',
 'reference-research':references.SKILL,
 'event-transient':event_design.SKILL,
 'product-model':product_build.SKILL,
 'mcu-firmware':deployment.SKILL,
 'tinyml-nas':tinyml.SKILL,
 'pcb-offline-routing': '# 立创 PCB 本地布线\n使用 bf_engineering run，engine=jlceda，parameters={"operation":"freeroute","document":"pcb","trace_width_mil":6.1,"clearance_mil":6.5}。必须先完成真实器件、网络、板框、安装孔与布局，并绑定当前原生工程；仅支持无铜线、无过孔的双层未布线板，已有布线会拒绝运行。先按电流与制造要求选择明确的线宽/间距，本操作不会降低原生设计规则。导出 DSN、本地 FreeRouting 求解、核对源板未变、导入 SES、应用明确的候选线宽后，重新执行原生 DRC。保留 DSN/SES、MCP/CLI 记录和原生检查。求解器零飞线不等于原生 DRC 通过；DRC 通过不等于模拟电路、布局质量或硬件功能已验证。失败后读取实际反馈，禁止覆盖其他工程或用放宽规则消除问题。',
 'blender-enclosure': '# Blender 外壳展示\n使用 bf_engineering run，engine=blender。parameters 为 length_mm,width_mm,height_mm,wall_mm。所有尺寸为毫米；记录是假设还是实测。产物含 model.blend、model.glb、preview.png 和尺寸记录。它是展示模型，不是制造 CAD 或装配验收。先说明尺寸来源，提交稳定 operation_id，使用 job 查询结果，引用实际产物。',
 'comsol-cantilever': '# COMSOL 悬臂梁静力\n使用 bf_engineering run，engine=comsol。parameters 为 length_mm,width_mm,thickness_mm,young_gpa,force_n。根部固定、端面均布力，泊松比 0.3，线弹性小变形。读取两档网格位移变化、Euler-Bernoulli 参考误差和小变形检查；失败不能当作通过。此模板不支持压电发电、共振或整机强度认证。使用 job 查询，保留 .mph、输入参数、求解日志与校验记录。'
}


def validate(engine, parameters):
    if engine=='door-selfpower':return door_selfpower.validate(parameters)
    if engine=='door-system':return door_system.validate(parameters)
    if engine=='scientific-figures':return scientific_figures.validate(parameters)
    if engine=='closed-simulation':return simulation_chain.validate(parameters)
    if engine=='beam-event':return beam_event.validate(parameters)
    if engine=='engineering-project':return engineering_projects.validate(parameters)
    if engine=='event-transient':
        if not isinstance(parameters,dict) or set(parameters)!={'spec_path'} or not isinstance(parameters['spec_path'],str):raise ValueError('EVENT_SPEC_PATH_REQUIRED')
        return parameters
    if engine in ('mcu-firmware','tinyml-nas'):
        if not isinstance(parameters,dict):raise ValueError('ENGINEERING_PARAMETERS_INVALID')
        return (deployment if engine=='mcu-firmware' else tinyml).validate(parameters)
    if engine=='product-model':
        if not isinstance(parameters,dict):raise ValueError('ENGINEERING_PARAMETERS_INVALID')
        return parameters
    if engine not in SPECS: raise ValueError('ENGINE_NOT_SUPPORTED')
    spec=SPECS[engine]
    if not isinstance(parameters,dict) or set(parameters)-set(spec['defaults']): raise ValueError('ENGINEERING_PARAMETERS_INVALID')
    p={**spec['defaults'],**parameters}
    for key,value in p.items():
        low,high=spec['ranges'][key]
        if type(value) not in (float,int) or not math.isfinite(value) or not low<=value<=high: raise ValueError('PARAMETER_OUT_OF_RANGE:'+key)
    if engine=='blender' and (min(p['length_mm'],p['width_mm'])<=6*p['wall_mm'] or p['height_mm']<=4*p['wall_mm']+2):
        raise ValueError('ENCLOSURE_CLEARANCE_INVALID')
    if engine=='comsol' and p['length_mm']/p['thickness_mm']<10: raise ValueError('CANTILEVER_SLENDERNESS_REQUIRES_L_OVER_H_10')
    return p


class Engineering:
    def __init__(self,app):
        self.app=app;self.store=app.store;self.root=self.store.root.parent/'engineering'
        self.root.mkdir(exist_ok=True);self.lock=threading.Lock();self.repository_dispatch_lock=threading.Lock();self.repository_workers={}
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS engineering_jobs(id TEXT PRIMARY KEY,owner TEXT,operation TEXT,request_hash TEXT,request TEXT,status TEXT,created REAL,started REAL,ended REAL,result TEXT,error TEXT,UNIQUE(owner,operation));
            CREATE TABLE IF NOT EXISTS engineering_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT,job_id TEXT,time REAL,kind TEXT,data TEXT);''')
            db.execute("UPDATE engineering_jobs SET status='UNKNOWN',error='服务重启，未自动重试；检查保留的进程日志和产物。' WHERE status IN ('RUNNING','QUEUED')")

        self.eda=JLCEDA(self)
        from .simulation_tasks import SimulationTasks
        self.tasks=SimulationTasks(self.store)
        from .tool_responses import ToolResponses
        self.responses=ToolResponses(self)

    def authorize(self,owner,operator=False):
        if operator:return
        with self.store.connect() as db:
            row=db.execute('SELECT config FROM chat_contexts WHERE owner=?',(owner,)).fetchone()
            grant=db.execute('SELECT expires FROM grants WHERE owner=?',(owner,)).fetchone()
            from .budget_policy import unbounded_time
            wall_authorized=unbounded_time(db,owner)
        if not row or 'bf_engineering' not in json.loads(row['config'])['tools'] or not grant or (not wall_authorized and grant['expires']<time.time()):
            raise PermissionError('ENGINEERING_TOOL_NOT_ENABLED')

    def catalog(self,owner=None):
        result = {'schema_version':'bf-engineering-catalog-v1','engines':[{'id':k,'installed':p.is_file(),'transport':'cli','executable':str(p),**SPECS[k]} for k,p in [('blender',BLENDER),('comsol',COMSOL)]]+[{'id':'event-transient','installed':event_design.SPICE.is_file(),'transport':'cli','executable':str(event_design.SPICE),'template':'coupled-event-v1','defaults':{'spec_path':'event-design.json'},'scope':event_design.SCOPE},{'id':'beam-event','installed':event_design.SPICE.is_file(),'transport':'cli','template':'geometry-rom-v1','defaults':{'assembly_revision':1,'mapping_path':'beam-mapping.json','spec_path':'event-design.json'},'scope':beam_event.SCOPE}],
                'skills':[{'id':k,'name':v.splitlines()[0][2:],'sha256':hashlib.sha256(v.encode()).hexdigest(),'status':'available'} for k,v in SKILLS.items()],
                'deployment':{'firmware':{'installed':deployment.GCC.is_file(),'target':'STM32L031K6T6','engine':'mcu-firmware'},'tinyml':{'installed':product_build.CAD.is_file() and deployment.GCC.is_file(),'engine':'tinyml-nas','scope':tinyml.SCOPE}},
                'cad':{'status':'available' if product_build.CAD.is_file() else 'not_installed','engine':'product-model','executable':str(product_build.CAD),'scope':product_build.SCOPE},'limits':{'timeout_seconds':180,'cpu_cores':2,'concurrent_jobs':1,'jobs_per_session':40,'model_calls':0},
                'eda':self.eda.catalog(owner), 'mcp':{'status':'configured','note':'立创 EDA 使用真实 MCP stdio；连接状态需探测。Blender/COMSOL 使用本地 CLI。'}, 'eda_skills':[{'id':k,'name':k,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'status':'available'} for k,p in SKILL_PATHS.items() if p.is_file()]}

        if hasattr(self.app,'eda_cli'):
            result['typed_eda'] = {'tool':'bf_eda','transport':'typed CLI','installed':Path(__import__('bfworld.agentlab.eda_cli',fromlist=['CLI']).CLI).is_file(),
                'binding':self.app.eda_cli.binding(owner) if owner else None,
                'scope':'仅操作绑定的独立工程；源数据、原生保存、读回与 DRC 分别留存回执。'}
        ltroot=HOME_ROOT/'toolchains/ltspice-26/Package.pkg/Payload/Applications/LTspice.app/Contents/SharedSupport/ltspice'
        dependencies={'CAD Python':product_build.CAD.is_file(),'COMSOL':COMSOL.is_file(),
                      'ARM compiler':deployment.GCC.is_file(),'host compiler':bool(shutil.which('cc')),
                      'LTspice':(ltroot/'bin/wine').is_file() and (ltroot/'support/ltspice/drive_c/Program Files/ADI/LTspice/LTspice.exe').is_file(),
                      'PMIC model':(ltroot/'support/ltspice/drive_c/users/crossover/AppData/Local/LTspice/lib/sub/LTC3588-1.sub').is_file()}
        result['engines'].append({'id':'closed-simulation','installed':all(dependencies.values()),'dependencies':dependencies,
          'transport':'cli','template':'door-closed-simulation-v1','defaults':{'candidate':{},'confirmation':True},'scope':simulation_chain.SCOPE})
        from .door_selfpower.pipeline import storage_observation
        selfpower_storage=storage_observation(door_selfpower.REFERENCE_ROOT)
        result['engines'].append({'id':'door-selfpower','storage':selfpower_storage,'installed':all(dependencies.values()),'dependencies':dependencies,
          'transport':'cli','template':'door-selfpower-v1','defaults':{'candidate':{},'confirmation':True},
          'scope':door_selfpower.SCOPE,'reference_ready':door_selfpower.reference_ready()})
        result['engines'].append({'id':'door-system','installed':all(dependencies.values()),'dependencies':dependencies,'transport':'cli','template':'door-system-v2','defaults':{'candidate':{},'confirmation':True},'scope':door_system.SCOPE})
        result['engines'].append({'id':'scientific-figures','installed':product_build.CAD.is_file(),
          'transport':'cli','template':'scientific-figures-v1','defaults':{'plan_path':'figures/plan.json'},'scope':scientific_figures.SCOPE})
        result['projects'] = [{'id':kind,'engine':'engineering-project','installed':exe.is_file(),
            'runnable':exe.is_file() and __import__('platform').system()=='Darwin',
            'inputs':'immutable project manifest and participant source',
            'validator':'native readback, not participant verdict', 'scope':engineering_projects.SCOPE}
            for kind,exe in engineering_projects.KINDS.items()]
        for item in result['engines']:
            history=[j for j in self.jobs(owner) if j['engine']==item['id']] if owner else []
            reference_ok=item['id']!='door-selfpower' or item['reference_ready']
            storage_ok=item.get('storage',{}).get('ready',True)
            item.update(runnable=item['installed'] and reference_ok and storage_ok,
                        operator_runnable=item['installed'] and storage_ok,
                        blocked_reason=('SELFPOWER_STORAGE_UNAVAILABLE' if not storage_ok else
                                        None if reference_ok else 'SELFPOWER_NO_AGENT_REFERENCE_NOT_QUALIFIED'),
                        probe_status='not_probed',last_execution=history[0]['status'] if history else None)
        result['task_binding']=self.tasks.binding(owner) if owner else None
        from .research_methods import profile, capabilities
        result['research_method']={'profile':profile(), 'capabilities':capabilities()} if result['task_binding'] else None
        if owner and not result['task_binding'] and hasattr(self.app,'skills'):
            resource_catalog=self.app.skills.catalog(owner)
            result['skills']=resource_catalog['skills']
            result['eda_skills']=[s for s in result['skills'] if s['adapter']=='easyeda-typed-v1']
            result['resource_manifest']={k:resource_catalog[k] for k in ('manifest_sha256','frozen','active','plugins')}
            result['mcp']={'status':'not_probed','note':'插件声明方法与适配器；bf_eda 使用绑定的 typed CLI，legacy jlceda MCP 是独立接口。安装状态不等于连接或执行通过。'}
        return result

    def event(self,owner,job,kind,data):
        with self.store.connect() as db:db.execute('INSERT INTO engineering_events(owner,job_id,time,kind,data) VALUES(?,?,?,?,?)',(owner,job,time.time(),kind,canonical(data)))

    def skill(self,owner,key,initiator='unrecorded'):
        if not self.tasks.binding(owner) and hasattr(self.app,'skills') and self.app.skills.catalog(owner)['frozen']:
            value={**self.app.skills.action(owner,{'action':'activate','skill_id':key}),'initiator':initiator}
            binding=self.tasks.binding(owner)
            if binding and key in ('closed-simulation','door-system','door-selfpower'):
                value={**value,'task_binding':binding}
            self.event(owner,None,'skill_read',{k:v for k,v in value.items() if k!='content'})
            return value
        if key not in SKILLS and key not in SKILL_PATHS:raise ValueError('SKILL_NOT_FOUND')
        content=SKILL_PATHS[key].read_text() if key in SKILL_PATHS else SKILLS[key]
        binding=self.tasks.binding(owner)
        if binding and key in ('closed-simulation','door-system','door-selfpower'):
            content+='\n## 本会话冻结任务（优先于通用参数列表）\n'+json.dumps(binding,ensure_ascii=False)+'\n只允许任务列明的设计变量；confirmation必须为true。完成比较后调用bf_engineering action=submit，指定已有job_id与rationale。提交失败候选是合法结论，不等于产品通过。'
        value={'id':key,'content':content,'sha256':hashlib.sha256(content.encode()).hexdigest(),'status':'read_not_execution','initiator':initiator}
        self.event(owner,None,'skill_read',value)
        return value

    @staticmethod
    def project(row):
        d=dict(row);request=json.loads(d.pop('request'));d.pop('request_hash',None)
        d.update(request);d['result']=json.loads(d['result']) if d['result'] else None
        return d

    def jobs(self,owner=None):
        with self.store.connect() as db:
            rows=db.execute('SELECT * FROM engineering_jobs'+(' WHERE owner=?' if owner else '')+' ORDER BY created DESC', (owner,) if owner else ()).fetchall()
        return [self.project(r) for r in rows]

    def events(self,owner):
        with self.store.connect() as db:rows=db.execute('SELECT * FROM engineering_events WHERE owner=? ORDER BY seq',(owner,)).fetchall()
        return [{**dict(r),'data':json.loads(r['data'])} for r in rows]

    def get(self,owner,key,operator=False):
        with self.store.connect() as db:r=db.execute('SELECT * FROM engineering_jobs WHERE id=?',(key,)).fetchone()
        if not r or (not operator and r['owner']!=owner):raise PermissionError('ENGINEERING_JOB_NOT_FOUND')
        return self.project(r)

    def submit(self,owner,body,initiator='unrecorded'):
        from .runtime_config import require_capability
        require_capability('native')
        engine=body.get('engine');p=validate_eda(body.get('parameters',{})) if engine=='jlceda' else validate(engine,body.get('parameters',{}));op=body.get('operation_id')
        task_binding=self.tasks.guard(owner,engine,p)
        if engine=='door-selfpower' and initiator!='operator' and not door_selfpower.reference_ready():
            raise ValueError('SELFPOWER_NO_AGENT_REFERENCE_NOT_QUALIFIED')
        if not isinstance(op,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',op):raise ValueError('OPERATION_ID_REQUIRED')
        revision=body.get('design_revision')
        if revision is not None and (type(revision) is not int or revision<1):raise ValueError('DESIGN_REVISION_INVALID')
        with self.store.connect() as db:
            message=db.execute("SELECT id FROM chat_messages WHERE conversation=? AND status IN ('SENT','ACCEPTED') ORDER BY created DESC LIMIT 1",(owner,)).fetchone()
        assembly=tinyml.request(self.app,owner,p) if engine=='tinyml-nas' else product_build.request(self.app,owner,p) if engine in ('product-model','mcu-firmware') else {}
        if engine=='beam-event':assembly=beam_event.request(self.app,owner,p)
        if engine=='engineering-project':assembly=engineering_projects.request(self.app,owner,p)
        if engine=='event-transient':assembly=event_design.request(self.app,owner,p)
        if engine=='scientific-figures':assembly=scientific_figures.request(self.app,owner,p)
        template=Path(door_selfpower.__file__) if engine=='door-selfpower' else Path(door_system.__file__) if engine=='door-system' else Path(scientific_figures.__file__) if engine=='scientific-figures' else Path(simulation_chain.__file__) if engine=='closed-simulation' else Path(__file__).with_name('beam_event.py') if engine=='beam-event' else Path(__file__).with_name('engineering_projects.py') if engine=='engineering-project' else Path(__file__).with_name('event_design.py') if engine=='event-transient' else Path(__file__).with_name('product_build.py') if engine=='product-model' else Path(__file__).with_name('jlceda.py') if engine=='jlceda' else TEMPLATES/('blender_enclosure.py' if engine=='blender' else 'Cantilever.java')
        template_hash=door_selfpower.template_hash() if engine=='door-selfpower' else door_system.template_hash() if engine=='door-system' else scientific_figures.template_hash() if engine=='scientific-figures' else simulation_chain.template_hash() if engine=='closed-simulation' else deployment.template_hash() if engine in ('mcu-firmware','tinyml-nas') else product_build.template_hash(TEMPLATES) if engine=='product-model' else hashlib.sha256(template.read_bytes()+(Path(__file__).with_name('freerouting.py').read_bytes() if engine=='jlceda' and p['operation']=='freeroute' else b'')).hexdigest()
        request={'engine':engine,'template':engine+'-v1' if engine in ('mcu-firmware','tinyml-nas','event-transient','engineering-project','beam-event','closed-simulation','scientific-figures','door-system','door-selfpower') else 'product-model-v1' if engine=='product-model' else ('jlceda-'+p['operation']+'-v1') if engine=='jlceda' else SPECS[engine]['template'],'template_sha256':template_hash,'parameters':p,'design_revision':revision,
                 'turn_id':message['id'] if message and initiator!='operator' else None, 'initiator':initiator, 'scope':door_selfpower.SCOPE if engine=='door-selfpower' else door_system.SCOPE if engine=='door-system' else scientific_figures.SCOPE if engine=='scientific-figures' else simulation_chain.SCOPE if engine=='closed-simulation' else beam_event.SCOPE if engine=='beam-event' else engineering_projects.SCOPE if engine=='engineering-project' else event_design.SCOPE if engine=='event-transient' else tinyml.SCOPE if engine=='tinyml-nas' else deployment.SCOPE if engine=='mcu-firmware' else product_build.SCOPE if engine=='product-model' else EDA_SCOPE if engine=='jlceda' else SPECS[engine]['scope']}
        request.update(assembly)
        if task_binding:request['task_binding']=task_binding
        if engine=='jlceda':
            request['binding']=self.eda.binding(owner)
            if not request['binding']:raise ValueError('EDA_BINDING_REQUIRED')
        digest=identity({k:v for k,v in request.items() if k!='turn_id'})
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT * FROM engineering_jobs WHERE owner=? AND operation=?',(owner,op)).fetchone()
            if previous:
                original=json.loads(previous['request'])
                if any(original.get(k)!=request.get(k) for k in ('engine','parameters','design_revision','dataset_source_sha256','event_spec_sha256','project_sha256','mapping_sha256','figure_project_sha256')):raise ValueError('ENGINEERING_OPERATION_CONFLICT')
                return self.project(previous)
            self.tasks.reserve_check(db,owner,task_binding)
            if revision is not None:
                current=(self.app.products.context(owner).get('proposal') or {}).get('revision')
                if current!=revision:raise ValueError('DESIGN_REVISION_STALE')
            if db.execute("SELECT 1 FROM engineering_jobs WHERE status IN ('RUNNING','QUEUED')").fetchone():raise ValueError('ENGINEERING_BUSY')
            if engine=='jlceda' and p['operation'] not in ('inspect','check','export'):
                for r in db.execute("SELECT request FROM engineering_jobs WHERE status='UNKNOWN'"):
                    old=json.loads(r['request'])
                    if old.get('engine')=='jlceda' and old.get('binding',{}).get('project_uuid')==request['binding']['project_uuid']:raise ValueError('EDA_UNKNOWN_OPERATION_REQUIRES_REVIEW')
            # Interrupted jobs keep their original identity and are never silently replayed.
            for row in db.execute("SELECT e.data FROM engineering_events e JOIN engineering_jobs j ON j.id=e.job_id WHERE j.status='UNKNOWN' AND e.kind='process_spawned'"):
                pid=json.loads(row['data'])['pid']
                try:os.killpg(pid,0)
                except ProcessLookupError:continue
                raise ValueError('ENGINEERING_RECOVERY_REQUIRED')
            if not (product_build.CAD if engine in ('closed-simulation','scientific-figures','door-system','door-selfpower') else engineering_projects.KINDS[assembly['project']['manifest']['kind']] if engine=='engineering-project' else event_design.SPICE if engine in ('event-transient','beam-event') else deployment.GCC if engine in ('mcu-firmware','tinyml-nas') else product_build.CAD if engine=='product-model' else EDA_SERVER if engine=='jlceda' else BLENDER if engine=='blender' else COMSOL).is_file():raise ValueError('ENGINE_NOT_INSTALLED')
            if db.execute('SELECT COUNT(*) FROM engineering_jobs WHERE owner=?',(owner,)).fetchone()[0]>=40:raise ValueError('ENGINEERING_SESSION_JOB_CAP')
            key='eng-'+secrets.token_hex(8);now=time.time()
            db.execute('INSERT INTO engineering_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,owner,op,digest,canonical(request),'QUEUED',now,None,None,None,None))
        self.event(owner,key,'job_queued',scientific_figures.public_response(request) if engine=='scientific-figures' else request)
        threading.Thread(target=self.run,args=(key,owner),daemon=True).start()
        return self.get(owner,key)

    def submit_repository(self,owner,operation,project,binding,db=None):
        """Repository inputs use the existing engineering job and native lock."""
        from .runtime_config import require_capability
        require_capability('native')
        if not self.app.design_lab.repository.bound(owner):raise PermissionError('REPOSITORY_OWNER_REQUIRED')
        template=Path(engineering_projects.__file__)
        request={'engine':'engineering-project','template':'engineering-project-v1',
                 'template_sha256':hashlib.sha256(template.read_bytes()).hexdigest(),
                 'parameters':{'repository':binding},'project':project,'project_sha256':identity(project),
                 'design_revision':None,'scope':engineering_projects.SCOPE,'initiator':'Pi',
                 'repository_binding':binding}
        digest=identity(request)
        from contextlib import nullcontext
        external=db is not None
        with (nullcontext(db) if external else self.store.connect()) as db:
            if not external:db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT * FROM engineering_jobs WHERE owner=? AND operation=?',(owner,operation)).fetchone()
            if prior:
                if prior['request_hash']!=digest:raise ValueError('ENGINEERING_OPERATION_CONFLICT')
                return self.project(prior)
            if db.execute("SELECT 1 FROM engineering_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone():raise ValueError('ENGINEERING_BUSY')
            if not engineering_projects.KINDS[project['manifest']['kind']].is_file():raise ValueError('ENGINE_NOT_INSTALLED')
            key='eng-'+secrets.token_hex(8);now=time.time()
            db.execute('INSERT INTO engineering_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (key,owner,operation,digest,canonical(request),'QUEUED',now,None,None,None,None))
            db.execute('INSERT INTO engineering_events(owner,job_id,time,kind,data) VALUES(?,?,?,?,?)',(owner,key,now,'job_queued',canonical(request)))
            registered=self.project(db.execute('SELECT * FROM engineering_jobs WHERE id=?',(key,)).fetchone())
        if not external:self.dispatch_repository(owner,key)
        return registered

    def dispatch_repository(self,owner,key):
        # Called only after the repository transaction is committed.
        with self.repository_dispatch_lock:
            worker=self.repository_workers.get(key)
            if worker and worker.is_alive():return
            if self.get(owner,key)['status']!='QUEUED':return
            worker=threading.Thread(target=self.run,args=(key,owner),daemon=True)
            self.repository_workers[key]=worker;worker.start()

    def command(self,key,owner,args,directory,deadline):
        self.event(owner,key,'process_start',{'transport':'cli','argv':args,'cwd':str(directory)})
        with (directory/'process.log').open('ab') as log:
            process=subprocess.Popen(args,cwd=directory,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.event(owner,key,'process_spawned',{'transport':'cli','pid':process.pid})
            try:code=process.wait(timeout=max(1,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=4)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                raise RuntimeError('ENGINEERING_TIMEOUT')
        self.event(owner,key,'process_end',{'transport':'cli','exit_code':code})
        if code:raise RuntimeError('ENGINEERING_PROCESS_EXIT_'+str(code))

    def run(self,key,owner):
        with self.lock,native_slot():
            try:
                directory=self.root/key;directory.mkdir()
                job=self.get(owner,key);p=job['parameters'];deadline=time.monotonic()+(12000 if job['engine']=='door-selfpower' else 3600 if job['engine'] in ('closed-simulation','door-system') else 600 if job['engine']=='scientific-figures' else 900 if job['engine']=='product-model' else 120 if job['engine']=='tinyml-nas' else 180)
                with self.store.connect() as db:db.execute("UPDATE engineering_jobs SET status='RUNNING',started=? WHERE id=?",(time.time(),key))
                (directory/'input.json').write_text(canonical({k:job[k] for k in ('engine','template','template_sha256','parameters','design_revision','scope','assembly','assembly_hashes','dataset','dataset_source_sha256','event_spec','event_spec_sha256','project','project_sha256','input_dimensions','geometry_rom','mapping_sha256','task_binding','figure_project_sha256') if k in job}))
                template=Path(door_selfpower.__file__) if job['engine']=='door-selfpower' else Path(door_system.__file__) if job['engine']=='door-system' else Path(scientific_figures.__file__) if job['engine']=='scientific-figures' else Path(simulation_chain.__file__) if job['engine']=='closed-simulation' else Path(__file__).with_name('beam_event.py') if job['engine']=='beam-event' else Path(__file__).with_name('engineering_projects.py') if job['engine']=='engineering-project' else Path(__file__).with_name('event_design.py') if job['engine']=='event-transient' else Path(__file__).with_name('jlceda.py') if job['engine']=='jlceda' else TEMPLATES/('blender_enclosure.py' if job['engine']=='blender' else 'Cantilever.java')
                source_bytes=template.read_bytes()
                if job['engine']=='jlceda' and p['operation']=='freeroute':source_bytes+=Path(__file__).with_name('freerouting.py').read_bytes()
                if job['engine']=='closed-simulation' and simulation_chain.template_hash()!=job['template_sha256']:raise RuntimeError('ENGINEERING_TEMPLATE_CHANGED')
                if job['engine']=='scientific-figures' and scientific_figures.template_hash()!=job['template_sha256']:raise RuntimeError('ENGINEERING_TEMPLATE_CHANGED')
                if job['engine']=='door-selfpower' and door_selfpower.template_hash()!=job['template_sha256']:raise RuntimeError('ENGINEERING_TEMPLATE_CHANGED')
                if job['engine']=='door-system' and door_system.template_hash()!=job['template_sha256']:raise RuntimeError('ENGINEERING_TEMPLATE_CHANGED')
                if job['engine'] not in ('product-model','mcu-firmware','tinyml-nas','closed-simulation','scientific-figures','door-system','door-selfpower') and hashlib.sha256(source_bytes).hexdigest()!=job['template_sha256']:raise RuntimeError('ENGINEERING_TEMPLATE_CHANGED')
                if job['engine']=='door-selfpower':
                    result=door_selfpower.run(self,job,directory,deadline)
                    if task_binding:=job.get('task_binding'):
                        from .simulation_tasks import attach_evaluation
                        evaluation=attach_evaluation(task_binding,directory,result)
                        self.event(owner,key,'task_evaluated',evaluation)
                elif job['engine'] in ('closed-simulation','door-system'):
                    result=(door_system if job['engine']=='door-system' else simulation_chain).run(self,job,directory,deadline)
                    if task_binding:=job.get('task_binding'):
                        from .simulation_tasks import attach_evaluation
                        evaluation=attach_evaluation(task_binding,directory,result)
                        self.event(owner,key,'task_evaluated',evaluation)
                elif job['engine']=='scientific-figures':
                    result=scientific_figures.run(self,job,directory,deadline)
                elif job['engine']=='beam-event':
                    result=beam_event.run(self,job,directory,deadline)
                elif job['engine']=='engineering-project':
                    result=engineering_projects.run(self,job,directory,deadline)
                elif job['engine']=='event-transient':
                    result=event_design.run(self,job,directory,deadline)
                elif job['engine'] in ('mcu-firmware','tinyml-nas'):
                    result=(deployment if job['engine']=='mcu-firmware' else tinyml).run(self,job,directory,deadline)
                    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
                elif job['engine']=='product-model':
                    result=product_build.run(self,job,directory,TEMPLATES,BLENDER,deadline)
                elif job['engine']=='jlceda':
                    result=self.eda.run(job,directory)
                    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
                elif job['engine']=='blender':
                    script=directory/'build.py';script.write_bytes(source_bytes)
                    self.command(key,owner,[str(BLENDER),'--background','--factory-startup','--threads','2','--python-exit-code','1','--python',str(script),'--',str(directory)],directory,deadline)
                    result=json.loads((directory/'result.json').read_text())
                    if not all((directory/name).stat().st_size>0 for name in ('model.blend','model.glb','preview.png')):raise RuntimeError('BLENDER_ARTIFACT_MISSING')
                else:
                    source=source_bytes.decode()
                    for key_name,param in [('L','length_mm'),('B','width_mm'),('H','thickness_mm'),('E','young_gpa'),('F','force_n')]:source=source.replace('__'+key_name+'__',str(float(p[param])))
                    script=directory/'Cantilever.java';script.write_text(source)
                    self.command(key,owner,[str(COMSOL),'compile',str(script)],directory,deadline)
                    if not (directory/'Cantilever.class').is_file():raise RuntimeError('COMSOL_COMPILATION_FAILED_SEE_PROCESS_LOG')
                    self.command(key,owner,[str(COMSOL),'-np','2','batch','-inputfile',str(directory/'Cantilever.class'),'-outputfile',str(directory/'batch.mph'),'-batchlog',str(directory/'solver.log')],directory,deadline)
                    log=(directory/'process.log').read_text(errors='replace')+(directory/'solver.log').read_text(errors='replace')
                    metrics={m[0]:(float(m[1]),float(m[2])) for m in re.findall(r'BF_METRICS,(coarse|fine),([0-9.Ee+\-]+),([0-9.Ee+\-]+)',log)}
                    if set(metrics)!={'coarse','fine'}:raise RuntimeError('COMSOL_SOLVE_OR_EXPORT_FAILED_SEE_SOLVER_LOG')
                    (directory/'metrics.csv').write_text('mesh,displacement_m,max_von_mises_pa\n'+'\n'.join(f'{name},{metrics[name][0]},{metrics[name][1]}' for name in ('coarse','fine'))+'\n')
                    models=list(directory.glob('batch*.mph'))
                    if len(models)!=1:raise RuntimeError('COMSOL_NATIVE_MODEL_MISSING_OR_AMBIGUOUS')
                    shutil.copyfile(models[0],directory/'model.mph')
                    rows=list(csv.DictReader((directory/'metrics.csv').open()))
                    coarse,fine=[float(r['displacement_m']) for r in rows];stress=float(rows[-1]['max_von_mises_pa'])
                    if not all(math.isfinite(v) and v>0 for v in (coarse,fine,stress)) or not (directory/'model.mph').is_file():raise RuntimeError('COMSOL_RESULT_INVALID')
                    length=p['length_mm']/1000; width=p['width_mm']/1000;height=p['thickness_mm']/1000
                    theory=4*p['force_n']*length**3/(p['young_gpa']*1e9*width*height**3)
                    delta=abs(fine-coarse)/fine; error=abs(fine-theory)/theory
                    version=re.search(r'COMSOL Multiphysics[^\n]*',log)
                    result={'engine':'COMSOL','version':version.group(0) if version else None,'template':job['template'],'displacement_mm':fine*1000,'max_von_mises_mpa':stress/1e6,
                            'mesh_displacement_relative_change':delta,'beam_reference_displacement_mm':theory*1000,'beam_reference_relative_error':error,
                            'checks':{'mesh_displacement_under_5_percent':delta<.05,'beam_reference_under_10_percent':error<.1,'small_deflection_under_5_percent_length':fine/length<.05},
                            'scope':job['scope'],'product_verified':False,'limitations':['固定约束角部应力存在奇异性，最大应力不能直接用于强度认证。','两档位移检查仅是本模板数值检查，不证明一般网格收敛。']}
                    result['numerical_checks_passed']=all(result['checks'].values())
                    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
                artifacts=[]
                for f in sorted(directory.iterdir()):
                    if f.is_file() and f.suffix in ('.json','.jsonl','.log','.csv','.tsv','.cir','.png','.blend','.glb','.mph','.py','.java','.epro-source','.epro2','.net','.zip','.step','.stl','.brep','.svg','.dsn','.ses','.c','.h','.ld','.elf','.hex','.bin','.raw','.map','.md','.pdf','.html'):
                        artifacts.append({'name':f.name,'bytes':f.stat().st_size,'sha256':simulation_chain.file_hash(f)})
                result.update(artifacts=artifacts,design_revision=job['design_revision'],input_hash=hashlib.sha256((directory/'input.json').read_bytes()).hexdigest())
                status=result.pop('_job_status','SUCCEEDED')
                with self.store.connect() as db:db.execute("UPDATE engineering_jobs SET status=?,ended=?,result=? WHERE id=?",(status,time.time(),canonical(result),key))
                self.event(owner,key,'job_completed',{'artifact_count':len(artifacts),'result':result})
            except Exception as exc:
                status='UNKNOWN' if any(term in str(exc).upper() for term in ('TIMEOUT','TIMED OUT','DISCONNECTED','NO LONGER CONNECTED')) else 'FAILED'
                artifacts=[{'name':f.name,'bytes':f.stat().st_size,'sha256':simulation_chain.file_hash(f)} for f in (self.root/key).iterdir() if f.is_file()]
                with self.store.connect() as db:db.execute("UPDATE engineering_jobs SET status=?,ended=?,error=?,result=? WHERE id=?",(status,time.time(),str(exc)[:800],canonical({'artifacts':artifacts,'product_verified':False}),key))
                self.event(owner,key,'job_failed',{'error':str(exc)[:800]})

    def artifact(self,owner,key,name,operator=False):
        job=self.get(owner,key,operator)
        if name not in {a['name'] for a in (job.get('result') or {}).get('artifacts',[])} | {'process.log','input.json','solver.log'}:raise PermissionError('ARTIFACT_NOT_FOUND')
        root=(self.root/key).resolve();path=(root/name).resolve()
        if path.parent!=root or not path.is_file():raise PermissionError('ARTIFACT_NOT_FOUND')
        entry=next((a for a in (job.get('result') or {}).get('artifacts',[]) if a['name']==name),None)
        if entry and simulation_chain.file_hash(path)!=entry['sha256']:raise ValueError('ARTIFACT_HASH_MISMATCH')
        return path
