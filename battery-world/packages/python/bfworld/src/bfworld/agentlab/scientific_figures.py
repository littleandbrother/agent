"""Source-bound, declarative publication figures. No participant plotting code.

The renderer verifies bytes, units and finite data. It does not certify the
physical model, participant claims, or hardware. Missing evidence is retained
as a gap and never counted as an available result.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil

from .engineering_projects import relative_file
from .runtime_config import CAD
from .store import identity

SCHEMA = 'bf-scientific-figure-plan-v1'
SCOPE = '逐子图输入快照、单位检查、矢量绘图与缺项记录；图像生成不证明物理模型、产品或自主复现通过。'
SKILL = '''# 学术图组与逐子图证据
先以 bf_reference 检索、获取和阅读原论文，登记主图/子图及它回答的问题、证据性质和前后依赖；文献图片只作注明出处的参考。
为当前产品写 figures/plan.json，schema_version=bf-scientific-figure-plan-v1，title,version,conclusion,limitations,sources,groups。
sources 为 {id,path,sha256,columns:{列名:单位},origin,scope}；路径相对 plan.json，最多80文件/64MB，禁止符号链接、网络和源码执行。origin 可为 native-simulation,derived-analysis,engineering-geometry,schematic,reference-literature,software-in-loop；均为声明，检查只验证文件/数据，不能自证物理。
groups 为1至6个 {order,title,question,conclusion,limitations,panels}，总计最多80子图。每个panel有 id(例如1a),label(a),title,question,caption,evidence_kind,dependencies(来源id),status=available|missing|not_applicable。
available 子图 types: line/scatter/bar/heatmap/image/diagram/table。数值图必须从来源CSV取数；series=[{source,x,y,x_unit,y_unit,label,linestyle,marker}]；热图为{source,x,y,z,x_unit,y_unit,z_unit}；image={source}；表格为{source,columns}；diagram={nodes:[{id,label,x,y,width,height}],edges:[{from,to,label}]}且evidence_kind必须illustration。
缺项填写reason；不生成伪波形、假SEM或成功应用图，不把missing/not_applicable算作完成。所有概念示意、静载云图、实际动作和诊断输入范围分别说明。
执行 bf_engineering action=run engine=scientific-figures parameters={plan_path:"figures/plan.json"}，稳定operation_id。读取job/result、figure-quality.json和缺项；产物为逐子图PDF/SVG/PNG、组图、plan、来源快照、figure-index和可打开的离线HTML/ZIP。学术制图采用白底、至少8pt、矢量文字/曲线、明确单位、色盲安全且双重编码，不给确定性单次结果添加虚构误差条。
机械先用真实CAD生成安装/剖切/爆炸/同相机状态图，标明比例、磁极、固定端和运动方向。场图来自对应原生结果，变形放大倍数明确。设计改动后重新绑定实际数据，以新operation_id生成新版本；保留失败与未知。
完整性=可提供面板/预先声明的适用面板，不等于复现成功率。硬件、数值复现、Agent自主完成应单独记录。'''


def validate(parameters):
    if not isinstance(parameters, dict) or set(parameters) != {'plan_path'} or not isinstance(parameters['plan_path'], str):
        raise ValueError('FIGURE_PLAN_PATH_REQUIRED')
    return parameters


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get('schema_version') != SCHEMA:
        raise ValueError('FIGURE_PLAN_SCHEMA')
    for key in ('title', 'version', 'conclusion'):
        if not isinstance(plan.get(key), str) or not 1 <= len(plan[key]) <= 2000:
            raise ValueError('FIGURE_TEXT_REQUIRED:' + key)
    sources = plan.get('sources')
    groups = plan.get('groups')
    if not isinstance(sources, list) or not 1 <= len(sources) <= 80 or not isinstance(groups, list) or not 1 <= len(groups) <= 6:
        raise ValueError('FIGURE_PLAN_BOUNDS')
    names = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('FIGURE_SOURCE_SCHEMA')
        sid = source.get('id', '')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}', sid) or sid in names:
            raise ValueError('FIGURE_SOURCE_ID')
        names.add(sid)
        if not re.fullmatch('[a-f0-9]{64}', source.get('sha256', '')) or not isinstance(source.get('columns', {}), dict):
            raise ValueError('FIGURE_SOURCE_HASH_OR_UNITS')
        if not source.get('scope') or not source.get('origin'):
            raise ValueError('FIGURE_SOURCE_SCOPE')
    ids = set()
    if any(not isinstance(g, dict) for g in groups) or [g.get('order') for g in groups] != list(range(1, len(groups) + 1)):
        raise ValueError('FIGURE_GROUP_SEQUENCE')
    for group in groups:
        if (not all(isinstance(group.get(k), str) and 0 < len(group[k]) <= 2000 for k in ('title', 'question', 'conclusion'))
                or not isinstance(group.get('limitations'), list) or not group['limitations']
                or not all(isinstance(s, str) for s in group['limitations'])
                or not isinstance(group.get('panels'), list) or not group['panels']):
            raise ValueError('FIGURE_GROUP_NARRATIVE')
        for panel in group['panels']:
            if not isinstance(panel, dict):
                raise ValueError('FIGURE_PANEL_SCHEMA')
            pid = panel.get('id', '')
            if not re.fullmatch('[1-6][a-z]', pid) or pid in ids or pid[0] != str(group['order']):
                raise ValueError('FIGURE_PANEL_ID')
            ids.add(pid)
            if panel.get('label') != pid[1] or not all(isinstance(panel.get(k), str) and 0 < len(panel[k]) <= 2000 for k in ('label', 'title', 'question', 'caption', 'evidence_kind')):
                raise ValueError('FIGURE_PANEL_NARRATIVE')
            if panel.get('status') not in ('available', 'missing', 'not_applicable'):
                raise ValueError('FIGURE_PANEL_STATUS')
            deps = panel.get('dependencies', [])
            if not isinstance(deps, list) or not deps or not all(isinstance(d, str) for d in deps) or len(set(deps)) != len(deps) or set(deps) - names:
                raise ValueError('FIGURE_PANEL_DEPENDENCY:' + pid)
            if panel['status'] != 'available':
                if not panel.get('reason'):
                    raise ValueError('FIGURE_GAP_REASON')
                continue
            if not deps or panel.get('type') not in ('line', 'scatter', 'bar', 'heatmap', 'image', 'diagram', 'table'):
                raise ValueError('FIGURE_PANEL_INPUT')
            references = ([s.get('source') for s in panel.get('series', [])] if panel['type'] in ('line', 'scatter')
                          else [panel.get('source')] if panel['type'] != 'diagram' else [])
            if panel['type'] in ('line', 'scatter') and not references:
                raise ValueError('FIGURE_SERIES_REQUIRED')
            if any(ref not in deps for ref in references):
                raise ValueError('FIGURE_UNBOUND_DATA')
            if panel['type'] == 'diagram' and panel['evidence_kind'] != 'illustration':
                raise ValueError('FIGURE_DIAGRAM_IS_ILLUSTRATION')
            if panel.get('error_bars'):
                raise ValueError('FIGURE_ERROR_BARS_REQUIRE_REPLICATE_CONTRACT')
            if panel['type'] == 'table':
                columns = panel.get('columns')
                compact = panel.get('compact', {})
                if (not isinstance(columns, list) or not columns or not all(isinstance(c, str) for c in columns)
                        or not isinstance(compact, dict) or not set(compact.get('columns', columns)) <= set(columns)
                        or type(compact.get('rows', 4)) is not int or not 1 <= compact.get('rows', 4) <= 20):
                    raise ValueError('FIGURE_TABLE_SCHEMA')
    if not 1 <= len(ids) <= 80:
        raise ValueError('FIGURE_PANEL_BOUNDS')
    return plan


def public_response(value):
    """Expose source identities and plan, never base64 binary input in tool context."""
    if isinstance(value, dict) and value.get('engine') == 'scientific-figures' and 'figure_project' in value:
        result = {k: v for k, v in value.items() if k != 'figure_project'}
        result['figure_plan'] = value['figure_project']['plan']
        return result
    if isinstance(value, dict) and isinstance(value.get('jobs'), list):
        return {**value, 'jobs': [public_response(j) for j in value['jobs']]}
    return value


def request(app, owner, parameters):
    workspace = app.store.root.parent / 'participants' / owner
    path = relative_file(workspace, parameters['plan_path'])
    if path.stat().st_size > 256_000:
        raise ValueError('FIGURE_PLAN_TOO_LARGE')
    plan = validate_plan(json.loads(path.read_text()))
    blobs = {}
    total = 0
    for source in plan['sources']:
        p = relative_file(path.parent, source['path'])
        if p.suffix.lower() not in ('.csv', '.json', '.png', '.jpg', '.jpeg', '.svg'):
            raise ValueError('FIGURE_SOURCE_TYPE')
        if source['path'] in blobs:
            continue
        total += p.stat().st_size
        if total > 64_000_000:
            raise ValueError('FIGURE_SOURCE_BUDGET')
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != source['sha256']:
            raise ValueError('FIGURE_SOURCE_CHANGED')
        blobs[source['path']] = base64.b64encode(data).decode()
    snapshot = {'plan': plan, 'sources': blobs}
    return {'figure_project': snapshot, 'figure_project_sha256': identity(snapshot)}


def renderer():
    return Path(__file__).with_name('scientific_renderer.py')


def template_hash():
    return hashlib.sha256(Path(__file__).read_bytes() + renderer().read_bytes()).hexdigest()


def run(engineering, job, directory, deadline):
    snapshot = job['figure_project']
    if identity(snapshot) != job['figure_project_sha256']:
        raise ValueError('FIGURE_SNAPSHOT_CHANGED')
    source = directory / 'figure-inputs'
    source.mkdir()
    for name, data in snapshot['sources'].items():
        p = source / name
        if p.is_absolute() and not p.resolve().is_relative_to(source.resolve()):
            raise ValueError('FIGURE_SOURCE_PATH')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(base64.b64decode(data, validate=True))
    (source / 'plan.json').write_text(json.dumps(snapshot['plan'], ensure_ascii=False, indent=2))
    script = directory / 'scientific_renderer.py'
    shutil.copyfile(renderer(), script)
    engineering.command(job['id'], job['owner'], [str(CAD), str(script), str(source / 'plan.json'), str(directory)], directory, deadline)
    result = json.loads((directory / 'figure-index.json').read_text())
    result.update(engine='scientific-figures', scope=SCOPE, readback_passed=True,
                  product_verified=False, hardware_verified=False, design_status='insufficient_evidence')
    (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
