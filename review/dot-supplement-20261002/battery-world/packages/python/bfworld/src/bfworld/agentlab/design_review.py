"""Evidence-first product cards, derived from current bindings, not LLM claims."""
from .product_authority import binding_inputs

GROUPS = {
 'mission': ('产品要完成什么服务？', {'requirements','references','interfaces'}),
 'mechanical': ('结构是否可重建，尺寸与装配检查是否成立？', {'cad','drawings','clearance','presentation','magnetics','fem','mapping','convergence'}),
 'energy': ('声明的输入与负载下能否完成服务？', {'spice','circuit-selection','joint','matrix'}),
 'circuit': ('电路、PCB 和当前板级接口是否一致？', {'schematic','spice','electrical-checks','pcb','pcb-checks','manufacturing'}),
 'firmware': ('当前程序为哪块板构建，资源和通信有哪些证据？', {'firmware','firmware-resources','flash-guide','receiver','receiver-tests','direction'}),
 'ml': ('是否需要学习模型，数据与目标板评估是否充分？', set()),
 'integrated': ('同一产品版本的跨域证据是否闭合？', {'joint','system-acceptance','matrix','interfaces'}),
 'evidence': ('哪些检查可以追溯到当前输入和原始产物？', {'raw-data','figures','system-acceptance'}),
 'release': ('当前阶段能交付什么，还缺少什么？', {'release','system-acceptance','manufacturing','flash-guide'}),
}


def native_checks(app, owner, task, binding, current):
    """Only narrowly scoped checks, never promote an entire task on tool exit."""
    checks=[]
    if not binding or not current:return checks
    for ref in binding.get('jobs', []):
        try:
            job=app.engineering.get(owner, ref['id'])
            result=job.get('result') or {}
            for f in result.get('artifacts', []):app.engineering.artifact(owner, job['id'], f['name'])
            bound=job.get('assembly')
            fresh=bool(bound and binding_inputs(task, bound)==binding_inputs(task, current))
            if job['engine']=='product-model':
                details=result.get('checks', {})
            elif job['engine']=='engineering-project':
                details={'independent_native_readback':result.get('readback_passed',False)}
            else:
                details=result.get('checks', {})
            for name, passed in details.items():
                checks.append(dict(name=name,passed=passed is True and fresh and job['status']=='SUCCEEDED',
                                   job_id=job['id'],current=fresh,scope=job['scope']))
        except (ValueError, PermissionError, OSError):
            checks.append(dict(name='artifact_integrity', passed=False, job_id=ref['id']))
    return checks


def cards(snapshot, current):
    result={}
    for node,(question,ids) in GROUPS.items():
        tasks=[t for t in snapshot['tasks'] if t['id'] in ids and t.get('applicability')!='not_applicable']
        missing=[{'id':t['id'],'label':t['label'],'delivery':t['delivery_status'],'validation':t['validation_status'],'reason':t['validation_reason']} for t in tasks if t['validation_status']!='passed']
        checks=[c for t in tasks for c in t.get('checks', [])]
        result[node]=dict(question=question,
            conclusion=f'{sum(c["passed"] for c in checks)} 项有来源的局部检查通过；{len(missing)} 项完整验收尚未完成。' if ids else '仅在任务需要学习模型时启用；当前清单不要求 NN/NAS。',
            assumptions=current['payload'].get('assumptions',[]) if current else [],
            revision=current['revision'] if current else None, profile=snapshot['profile'],
            checks=checks, open_questions=missing,
            evidence=[{'task':t['id'],'file':f['id'],'name':f['name'],'sha256':f['digest']} for t in tasks for f in (t.get('binding') or {}).get('files',[])],
            claim_boundary='局部检查、文件齐套、完整工程验收、实测分别记录。')
    return result
