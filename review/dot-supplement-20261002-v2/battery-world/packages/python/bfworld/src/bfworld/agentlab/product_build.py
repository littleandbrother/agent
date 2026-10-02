"""Native product build shared by the UI and Pi; every artifact is input-bound."""
import hashlib
import json
from pathlib import Path
from .store import identity
from .product_energy import calculate

from .runtime_config import CAD
SCRIPTS = ('product_cad.py', 'product_blender.py', 'product_readback.py')
SCOPE = '参数化原生实体 CAD、STEP 读回、Blender 装配/剖视/爆炸展示、尺寸与干涉检查；未代替电气、制造或实物验收。'
SKILL = '''# 完整产品数字样机
先用 bf_product action=assembly_inspect 读取当前产品记录。assembly_write 使用 assembly_path 指定工作目录中的 JSON，source_message_id、operation_id、expected_revision 做来源与并发校验。JSON 必须含 units=mm、title、parts、required_roles、requirements、assumptions、interfaces、energy、presentation。
requirements、assumptions、interfaces 必须是列表（可为空）；presentation.camera_deg 是单个角度数字（例如35），不是数组。source.basis 只能为 datasheet-envelope、design-assumption、native-component；source.note 必填，datasheet-envelope 还必须有 HTTPS source.url。
parts 每项含 id,name,role,source(basis,note,url)、geometry(kind,size_mm,center_mm,rotation_deg,fillet_mm,wall_mm,cutouts)、color(RGB 0..1)。支持 box,rounded_box,shell,cylinder,sphere；圆柱局部 Z 轴、球直径相等；shell 向局部 +Y 开口。元件包络需来源，不冒充原厂精细模型。allowed_contacts 仅记录有意装配接触，不能掩盖干涉。
bf_engineering run engine=product-model parameters={assembly_revision:整数}，稳定 operation_id。job 查询后阅读实际 cad-readback.json、blender-readback.json、energy.json 与 result.json。尺寸原生毫米；GLB/Blender 为米，独立读回检查换算。所有图、STEP、STL、BREP、脚本和输入可下载。camera_deg 只改变展示身份，不改变物理身份。geometry_changed/physical_changed 时不能继承旧版验收。
role 只能取 housing,cover,solar,storage,pcb,controller,power,input,feedback,mount,connector,decoration。required_roles 为这些值的列表。所有 size_mm/center_mm/rotation_deg 是三个数字的数组；rounded_box 的 fillet_mm 必须小于最短边一半；shell wall_mm 至少0.5，开口在局部+Y。
energy 计算字段必须包含 pv_power_mw,illuminance_lux,lit_hours,conversion_efficiency,capacitance_f,capacitance_tolerance_low,v_high,v_low,sleep_ua,leakage_ua,supply_v,led_total_ma,pulse_ms,mcu_event_mj,events_per_day；每项数值均来自说明明确的资料或假设。缺字段只生成几何，能源状态会记为未完成。时间仿真是条件性一阶估计，不是实测或SPICE。
工程返回的 artifacts 带真实文件标识与哈希；job 结果有原生检查、包络和能源数据。用 bf_engineering action=artifact,job_id,artifact_name 下载指定产物到本工作目录，随后 read 查看 JSON/文本或图像（模型不支持图像时不能宣称视觉检查）。若无法访问图像，明确未视觉审查，不能声称看过。
不要修改测量或检查结果来通过。energy 为有来源的采集工作点和显式假设，不能将计算称为硬件通过。产品电路与固件须另外发布并验证。publish_file 注册工作目录文件，传 revision,file_path,file_kind；注册不是验收。
'''


def template_hash(templates):
    return identity({**{name: hashlib.sha256((templates/name).read_bytes()).hexdigest() for name in SCRIPTS},
                     **{name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('product_build.py','product_energy.py')}})


def request(app, owner, parameters):
    if set(parameters) != {'assembly_revision'} or type(parameters['assembly_revision']) is not int:
        raise ValueError('ASSEMBLY_REVISION_REQUIRED')
    record = app.assemblies.get(owner, parameters['assembly_revision'])
    if not record['source_valid'] or record['revision'] != app.assemblies.get(owner)['revision']:
        raise ValueError('ASSEMBLY_REVISION_STALE')
    return {'assembly': record, 'assembly_hashes': record['hashes']}


def run(engineering, job, directory, templates, blender, deadline):
    if template_hash(templates) != job['template_sha256']:
        raise RuntimeError('ENGINEERING_TEMPLATE_CHANGED')
    for name in SCRIPTS:
        (directory/name).write_bytes((templates/name).read_bytes())
    for name in ('product_build.py','product_energy.py'):
        (directory/name).write_bytes(Path(__file__).with_name(name).read_bytes())
    command = lambda args: engineering.command(job['id'], job['owner'], args, directory, deadline)
    command([str(CAD), str(directory/'product_cad.py'), str(directory)])
    for name in SCRIPTS[1:]:
        command([str(blender), '--background', '--factory-startup', '--threads', '2', '--python-exit-code', '1', '--python', str(directory/name), '--', str(directory)])
    cad = json.loads((directory/'cad-readback.json').read_text())
    blend = json.loads((directory/'blender-readback.json').read_text())
    checks = {'step_reopened_valid': cad['step_reopened_valid'], 'no_undeclared_intersections': not cad['collisions'],
              'blender_readback_valid': blend['passed'], 'each_part_is_one_solid':all(p['solid_count']==1 for p in cad['parts'])}
    result = {'engine': 'CadQuery + Blender', 'scope': SCOPE, 'checks': checks, 'digital_checks_passed': all(checks.values()),
              'assembly_hashes': job['assembly_hashes'], 'assembly_revision': job['assembly']['revision'],
              'part_count': len(cad['parts']), 'bounds_mm': cad['assembly_bounds'], 'product_verified': False,
              'limitations': ['厂商尺寸包络不等于详细封装与制造公差验收。', '渲染、干涉和尺寸检查不证明电路、供能或固件在实物上工作。']}
    try:
        energy=calculate(job['assembly']['payload']['energy'])
    except (ValueError,KeyError) as exc:
        energy={'calculation_passed':False,'status':'UNSUPPORTED_OR_INCOMPLETE','error':str(exc)}
    (directory/'energy.json').write_text(json.dumps(energy,ensure_ascii=False,indent=2))
    result['energy']=energy
    (directory/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
