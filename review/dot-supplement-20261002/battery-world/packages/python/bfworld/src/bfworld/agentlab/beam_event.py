"""Explicit rectangular-beam CAD to tip-coordinate ROM mapping.

Not a magnetic model or calibrated laminated piezoelectric beam. Piezo coupling
and capacitance stay independently sourced inputs. Fixed event evaluator reused.
"""
import json
import math
from pathlib import Path
from . import event_design, product_build
from .engineering_projects import relative_file
from .store import identity

SCOPE = '均匀细长矩形悬臂梁几何到单模态候选模型，联合整流/储能/估算负载；未校准磁体、复合梁、PMIC或硬件。'
SKILL = '''# 几何绑定的联合计算
bf_engineering run engine=beam-event parameters={assembly_revision:当前版本,mapping_path:"beam-mapping.json",spec_path:"event-design.json"}。
mapping JSON 仅含 beam_part（当前零件ID）, axes（依次为长度/宽度/弯曲厚度的0/1/2置换）, young_pa,density_kg_m3,tip_mass_kg,damping_ratio,material_source（非空来源定位字符串）。仅均匀矩形 box，禁止孔洞、壳、圆角；L/h>=10。固定根部，端位移坐标；k=3EI/L^3，I=b*h^3/12，m_eff=0.2357*rho*b*h*L+tip_mass。阻尼来自声明的阻尼比；不是拟合/实测。
event-design.json 使用 event-transient 的完整输入。其质量、刚度、阻尼会由映射覆盖；压电耦合/电容仍需独立来源，不从CAD颜色或体积猜测。细长模型不能代表复合梁、磁释放或碰撞。输出 geometry-rom.json 和同一次 ngspice 通道；变更尺寸必须重新求解。工作负载保持 estimate，除非已有操作者导入的真实测量。
比较不同几何时必须使用相同外部轨迹、储能初值与程序负载；镜头改动不改变 ROM 或仿真输入身份。数值收敛与能量守恒不代表文献或物理校准。'''


def validate(p):
    if not isinstance(p,dict) or set(p)!={'assembly_revision','mapping_path','spec_path'} or type(p['assembly_revision']) is not int or any(not isinstance(p[k],str) for k in ('mapping_path','spec_path')):
        raise ValueError('BEAM_EVENT_PARAMETERS')
    return p


def derive(assembly, mapping, mechanics):
    if not isinstance(mapping,dict) or set(mapping)!={'beam_part','axes','young_pa','density_kg_m3','tip_mass_kg','damping_ratio','material_source'}:
        raise ValueError('BEAM_MAPPING_SCHEMA')
    if not isinstance(mapping['material_source'],str) or not mapping['material_source'].strip():raise ValueError('BEAM_MATERIAL_SOURCE_REQUIRED')
    axes=mapping['axes']
    if not isinstance(axes,list) or len(axes)!=3 or any(type(x) is not int for x in axes) or set(axes)!={0,1,2}:raise ValueError('BEAM_AXES_INVALID')
    part=next((p for p in assembly['payload']['parts'] if p['id']==mapping['beam_part']),None)
    if not part:raise ValueError('BEAM_PART_MISSING')
    g=part['geometry']
    if g['kind']!='box' or g.get('cutouts') or g.get('fillet_mm',0):raise ValueError('BEAM_MAPPING_UNSUPPORTED_GEOMETRY')
    length,width,height=[g['size_mm'][i]/1000 for i in axes]
    if length/height<10:raise ValueError('BEAM_SLENDERNESS_OUT_OF_DOMAIN')
    E=event_design.number(mapping['young_pa'],'young_pa',1e6,1e12)
    rho=event_design.number(mapping['density_kg_m3'],'density',1,30000)
    tip=event_design.number(mapping['tip_mass_kg'],'tip_mass',0,1)
    zeta=event_design.number(mapping['damping_ratio'],'damping_ratio',.00001,.2)
    inertia=width*height**3/12
    k=3*E*inertia/length**3;m=.2357*rho*length*width*height+tip
    values={**mechanics,'mass_kg':m,'stiffness_n_m':k,'damping_ns_m':2*zeta*math.sqrt(k*m)}
    receipt=dict(schema_version='bf-geometry-rom-v1', geometry_hash=assembly['hashes']['geometry_hash'],
                 mapping=mapping,dimensions_m=[length,width,height],area_m2=width*height,inertia_m4=inertia,
                 mechanics=values,frequency_short_circuit_hz=math.sqrt(k/m)/(2*math.pi),
                 scope=SCOPE,calibrated=False,hardware_verified=False,
                 independent_parameters=['coupling_n_v','piezo_capacitance_f','damping_ratio'],
                 assumptions=['uniform rectangular Euler-Bernoulli beam','clamped root and tip coordinate','effective mass factor 0.2357','tip mass excludes rotary inertia'])
    return values,receipt


def request(app,owner,p):
    record=product_build.request(app,owner,{'assembly_revision':p['assembly_revision']})
    root=app.store.root.parent/'participants'/owner
    mp=relative_file(root,p['mapping_path']);sp=relative_file(root,p['spec_path'])
    if mp.stat().st_size>16000 or sp.stat().st_size>100000:raise ValueError('BEAM_EVENT_INPUT_SIZE')
    spec=json.loads(sp.read_text());mapping=json.loads(mp.read_text())
    spec['mechanics'],receipt=derive(record['assembly'],mapping,spec.get('mechanics',{}))
    event_design.validate(spec)
    if spec['workload']['origin']=='measured':
        from .event_measurement import verified_load
        measured=verified_load(app.store.root.parent,owner,spec['workload']);v=spec['power']['output_v']
        if abs(measured['voltage_min_v']-v)>v*.05 or abs(measured['voltage_max_v']-v)>v*.05:raise ValueError('MEASUREMENT_REGULATED_VOLTAGE_MISMATCH')
    return {**record,'event_spec':spec,'event_spec_sha256':identity(spec),'geometry_rom':receipt,'mapping_sha256':identity(mapping)}


def run(engineering,job,directory,deadline):
    (directory/'geometry-rom.json').write_text(json.dumps(job['geometry_rom'],ensure_ascii=False,indent=2))
    result=event_design.run(engineering,job,directory,deadline)
    result.update(geometry_rom=job['geometry_rom'],scope=SCOPE)
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
