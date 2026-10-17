"""Read already executed task artifacts and derive compact, source-bound facts."""
import json


def facts(repo, system, execution):
    if execution['status'] != 'SUCCEEDED' or system['task_definition']['case_adapter'] != 'piezo-reference-v1':
        return []
    def raw(path):
        return (repo.root/'blobs'/execution['artifacts'][path]['sha256']).read_text()
    scenario = system['task_definition']['scenario']
    events = json.loads(raw('events.json'))
    pairs = json.loads(raw('load.json'))
    rows = [[float(v) for v in line.split()] for line in raw('storage.dat').splitlines() if line.strip()]
    design = json.loads(raw('design.json'))
    charge = sum((b[0]-a[0])*(a[1]+b[1])/2 for a,b in zip(pairs,pairs[1:]))
    average_load = scenario['rail_v']*charge/scenario['duration_s']
    out = []
    def add(key, label, value, unit, sources):
        out.append({'key': key, 'label': label, 'value': value, 'unit': unit,
                    'execution_id': execution['id'], 'sources': sources})
    add('storage_uf', '储能电容', design['storage_f']*1e6, 'µF', ['design.json'])
    add('rail_v', '负载电源轨', scenario['rail_v'], 'V', ['task_definition.scenario.rail_v'])
    add('load_charge_uc', '负载总电荷', charge*1e6, 'µC', ['load.json'])
    add('load_energy_uj', '负载总能量', scenario['rail_v']*charge*1e6, 'µJ', ['load.json', 'task_definition.scenario.rail_v'])
    add('average_load_uw', '平均负载功率', average_load*1e6, 'µW', ['load.json', 'task_definition.scenario'])
    add('available_power_uw', '转换后可用平均功率', execution['metrics']['available_power_w']*1e6, 'µW', ['source.dat', 'storage.cir'])
    add('supply_load_ratio', '可用功率 / 平均负载', execution['metrics']['available_power_w']/average_load, '倍', ['load.json', 'storage.cir'])
    minima = []
    for event in events:
        if event['state'] not in ('sample', 'tx'): continue
        window = [r[1] for r in rows if event['t_s'] <= r[0] <= event['t_s']+event['duration_s']]
        if window:
            minimum = min(window); minima.append(minimum)
            label = '采样' if event['state'] == 'sample' else '发送'
            add(f"{event['state']}_{event['seq']}_minimum_v", f"第 {event['seq']} 帧{label}窗口最低储能电压",
                minimum, 'V', ['storage.dat', 'events.json'])
    if minima:
        add('minimum_service_margin_v', '采样与发送窗口最小电压余量', min(minima)-scenario['minimum_storage_v'],
            'V', ['storage.dat', 'events.json', 'task_definition.scenario.minimum_storage_v'])
    integrate = lambda col: sum((b[0]-a[0])*(a[col]+b[col])/2 for a,b in zip(rows,rows[1:]))
    net = integrate(2)-integrate(3)-integrate(4)
    delta = .5*design['storage_f']*(rows[-1][1]**2-scenario['initial_storage_v']**2)
    add('energy_residual_uj', '储能核算绝对残差', abs(delta-net)*1e6, 'µJ', ['storage.dat', 'design.json'])
    if abs(net) > 1e-15:
        add('energy_residual_percent', '储能核算相对残差', abs(delta-net)/abs(net)*100, '%', ['storage.dat', 'design.json'])
    return out


def read(repo, owner, body):
    from .repository_task_execution import current_execution
    project = repo.project(body['project_id'], owner)
    system = repo.system(project['id'], body.get('system_id') or project['submitted'])
    task = system.get('task_definition')
    if not task or task['case_adapter'] not in ('piezo-reference-v1','tabulated-curve-v1'):
        raise ValueError('TASK_PROFILE_EXECUTION_REQUIRED')
    execution = current_execution(repo, system)
    if not execution: raise ValueError('TASK_CURRENT_EXECUTION_MISSING')
    result = {'system_id': system['id'], 'execution_id': execution['id'], 'status': execution['status'],
              'metrics': execution['metrics'], 'facts': facts(repo, system, execution), 'artifacts': execution['artifacts']}
    path = body.get('path')
    if path:
        if path not in execution['artifacts']: raise ValueError('TASK_EXECUTION_ARTIFACT_UNKNOWN')
        offset, limit = body.get('offset', 0), body.get('limit', 8000)
        if type(offset) != int or offset < 0 or type(limit) != int or not 1 <= limit <= 24000:
            raise ValueError('TASK_RESULT_READ_RANGE')
        ref = execution['artifacts'][path]
        try: text = (repo.root/'blobs'/ref['sha256']).read_text()
        except UnicodeDecodeError: raise ValueError('TASK_RESULT_BINARY_ARTIFACT') from None
        result['read'] = {**ref, 'path': path, 'offset': offset, 'total_chars': len(text),
            'content': text[offset:offset+limit], 'next_offset': offset+limit if offset+limit < len(text) else None}
    return result
