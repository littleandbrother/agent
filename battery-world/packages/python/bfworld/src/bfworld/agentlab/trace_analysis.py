"""Independent, read-only BF trace projections. Observations never become verdicts."""
import json
import math
from .store import identity


def obj(value):
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def analyze(snapshot, engineering=None, capability_events=None):
    """All metric provenance points back to an immutable review snapshot."""
    receipt = snapshot.get('receipt') or {}
    engineering = snapshot.get('engineering_jobs',[]) if engineering is None else engineering
    capability_events = snapshot.get('capability_events',[]) if capability_events is None else capability_events
    conversation = snapshot.get('conversation') or {}
    turns = [{'id': 'unassigned', 'title': '未绑定轮次 / 启动', 'start': None, 'end': None, 'status': 'unknown'}]
    active = turns[0]
    row_turn = {}
    findings, timeline = [], []
    if conversation.get('error'):
        findings.append({'kind':'conversation-error','level':'error','title':'会话执行受阻或失败','detail':conversation['error'],'turn_id':'unassigned'})
    inputs = {x['id']: x for x in snapshot.get('inputs', [])}
    for event in snapshot['events']:
        data = event['data']; kind = data.get('type'); at = number(data.get('time'))
        if kind == 'input_accepted':
            key = str(data.get('message_id') or 'line-' + str(event['seq']))
            if data.get('delivery') != 'steer':
                active = {'id': key, 'title': inputs.get(key, {}).get('text', '用户请求')[:100],
                          'start': at, 'end': None, 'status': 'running'}
                # A recovery can emit input_accepted for the same message again.
                old = next((x for x in turns if x['id'] == key), None)
                if old:
                    active = old
                else:
                    turns.append(active)
            timeline.append({'id': 'event-' + str(event['seq']), 'lane': 'conversation', 'label': '补充消息' if data.get('delivery') == 'steer' else '收到任务',
                             'time': at, 'end': None, 'turn_id': active['id'], 'seq': event['seq'], 'status': 'recorded', 'detail': data})
        row_turn[event['seq']] = active['id']
        if kind in ('turn_complete', 'turn_error', 'turn_stopped'):
            active.update(end=at, status={'turn_complete': 'completed', 'turn_error': 'error', 'turn_stopped': 'stopped'}[kind])
            timeline.append({'id': 'event-' + str(event['seq']), 'lane': 'conversation', 'label': {'turn_complete':'本轮结束','turn_error':'本轮错误','turn_stopped':'已停止'}[kind],
                             'time': at, 'end': None, 'turn_id': active['id'], 'seq': event['seq'], 'status': active['status'], 'detail': data})
        if kind in ('product_context_snapshot','delivery_observation','harness_loaded'):
            timeline.append({'id':'event-'+str(event['seq']),'lane':'conversation','label':{'product_context_snapshot':'当前产品上下文快照','delivery_observation':'统一交付判定','harness_loaded':'实际加载的 Harness'}[kind], 'time':at,'end':None,'turn_id':active['id'],'seq':event['seq'],'status':'recorded','detail':data})
        message = obj(data.get('message'))
        if message.get('role') == 'assistant' and message.get('stopReason') == 'length':
            findings.append({'kind': 'output-truncated', 'level': 'error', 'title': '模型输出被截断',
                             'detail': '返回的 stopReason=length；检查该请求输出额度和输入规模。', 'turn_id': active['id'], 'source_seq': event['seq']})
    for call in snapshot['calls']:
        status = 'error' if call['error'] else 'completed' if call['finished'] else 'unknown'
        args=obj(call['input']);name=call['name'] or 'tool'
        category='mcp' if name.startswith('mcp__') else 'skill' if (name in ('bf_engineering','bf_reference','bf_eda') and args.get('action')=='skill') or (name=='read' and str(args.get('path',args.get('file_path',''))).endswith('SKILL.md')) else 'reference' if name=='bf_reference' else 'tool'
        timeline.append({'id': 'tool-' + str(call['seq']), 'lane': 'tools', 'label': call['name'], 'time': number(call['start_time']),
                         'end': number(call['end_time']), 'duration_ms': call['duration_ms'], 'turn_id': row_turn.get(call['seq'], 'unassigned'),
                         'seq': call['seq'], 'status': status, 'category':category, 'detail': call})
    contexts = {r['request_id']: r for r in snapshot['model_context_projections']}
    requests = []
    for rejection in snapshot.get('model_context_rejections', []):
        timeline.append({'id': 'context-rejected-' + str(rejection['seq']), 'lane': 'model',
                         'label': '上下文预检未通过 · 未发送模型', 'time': rejection['time'], 'end': None,
                         'turn_id': 'unassigned', 'seq': None, 'status': 'error',
                         'detail': {**rejection, 'data': obj(rejection['data']), 'dispatched': False}})
    for r in snapshot['model_requests']:
        ctx = contexts.get(r['id'], {}); usage = obj(r.get('usage')); projection = obj(ctx.get('projection'))
        turn_id = ctx.get('message_id') or 'unassigned'
        if not any(t['id'] == turn_id for t in turns):
            turns.append({'id': turn_id, 'title': inputs.get(turn_id, {}).get('text', '账本绑定请求')[:100], 'start': None, 'end': None, 'status': 'unknown'})
        item = {'id': r['id'], 'turn_id': turn_id, 'time': r['created'], 'status': r['status'],
                'input_tokens': number(usage.get('prompt_tokens')), 'output_tokens': number(usage.get('completion_tokens')),
                'cached_tokens': number(usage.get('prompt_cache_hit_tokens')), 'total_tokens': number(usage.get('total_tokens')),
                'charged_usd': number(r.get('charged')) if r['status'] == 'SETTLED' else None,
                'reserved_usd': number(r.get('reserved')), 'projection': projection, 'source': 'model_requests/' + r['id']}
        requests.append(item)
        timeline.append({'id': 'model-' + r['id'], 'lane': 'model', 'label': '模型请求', 'time': r['created'], 'end': None,
                         'turn_id': turn_id, 'seq': None, 'status': r['status'], 'detail': {**item, 'request_hash': r['request_hash'], 'error': r.get('error')}})
        if r['status'] == 'UNKNOWN':
            findings.append({'kind': 'unknown-usage', 'level': 'error', 'title': '模型用量待核对', 'detail': r.get('error') or r['id'], 'turn_id': turn_id, 'request_id': r['id']})
    for job in snapshot['jobs']:
        timeline.append({'id': 'experiment-' + job['id'], 'lane': 'experiments', 'label': obj(job.get('request')).get('task_id', '实验'),
                         'time': number(job.get('created')), 'end': None, 'turn_id': 'unassigned', 'seq': None,
                         'status': job['status'], 'detail': job})
    for job in engineering:
        timeline.append({'id': job['id'], 'lane': 'engineering', 'label': job['engine'] + ' · ' + job['template'],
                         'time': job['created'], 'end': job.get('ended'), 'turn_id': job.get('turn_id') or 'unassigned',
                         'seq': None, 'status': job['status'], 'detail': job})
    for event in capability_events:
        timeline.append({'id':'capability-'+str(event['seq']),'lane':'capabilities','label':event['data'].get('tool',event['kind']),
                         'time':event['data'].get('started',event['time']),'end':event['time'],'turn_id':next((j.get('turn_id') for j in engineering if j['id']==event['job_id']),None) or 'unassigned',
                         'seq':None,'duration_ms':event['data'].get('duration_ms'),'category':'mcp' if event['kind'].startswith('mcp_') else 'skill' if event['kind']=='skill_read' else 'reference' if event['kind'].startswith('reference_') else 'measurement' if event['kind']=='measurement_imported' else 'tool','status':event['data'].get('status','recorded'),'detail':event})
    for issue in snapshot['issues']:
        findings.append({'kind': issue['kind'], 'level': 'warning', 'title': '原始事件关联需核对', 'detail': issue,
                         'turn_id': row_turn.get(issue.get('seq'), 'unassigned'), 'source_seq': issue.get('seq')})
    # Failed calls are facts. Repeated reads, solver polling and replications are not classified as waste.
    for item in timeline:
        if item['lane'] == 'tools' and item['status'] == 'error':
            findings.append({'kind': 'tool-error', 'level': 'error', 'title': item['label'] + ' 返回错误', 'detail': '展开调用检查原始返回。',
                             'turn_id': item['turn_id'], 'source_seq': item['seq']})
    times = [i['time'] for i in timeline if number(i['time']) is not None]
    times += [i['end'] for i in timeline if number(i.get('end')) is not None]
    start = number(receipt.get('started')); end = number(receipt.get('ended'))
    metrics = {}
    for key in ('input_tokens', 'output_tokens', 'cached_tokens', 'total_tokens', 'charged_usd'):
        known = [r[key] for r in requests if r[key] is not None]
        metrics[key] = {'value': sum(known) if known or not requests else None, 'known': len(known), 'total': len(requests), 'source': 'recorded'}
    metrics['cost_upper_bound_usd'] = sum((r['charged_usd'] if r['charged_usd'] is not None else r['reserved_usd'] or 0) for r in requests)
    metrics['duration_ms'] = (end - start) * 1000 if start is not None and end is not None and end >= start else None
    source = {'snapshot_id': snapshot['snapshot_id'], 'trace_sha256': snapshot['source']['sha256'], 'committed_sha256': snapshot['source']['committed_sha256'],
              'pending_tail_bytes': snapshot['source']['pending_tail_bytes'], 'harness': receipt.get('harness', {}).get('identity'), 'model': receipt.get('harness', {}).get('model')}
    registrations=[e['data'].get('tools',[]) for e in snapshot['events'] if e['data'].get('type')=='shared_context_loaded']
    payload = {'schema_version': 'bf-trace-analysis-v1', 'session_id': snapshot['session_id'], 'source': source,
               'registered_tools': registrations[-1] if registrations else None,
               'status': conversation.get('status', receipt.get('status', 'unknown')), 'turns': turns, 'timeline': timeline,
               'requests': requests, 'metrics': metrics, 'findings': findings, 'range': [min(times), max(times)] if times else None,
               'coverage': {'timed_tools': sum(c['duration_ms'] is not None for c in snapshot['calls']), 'tools': len(snapshot['calls']),
                            'raw_events': len(snapshot['events']), 'untimed_items': sum(i['time'] is None for i in timeline)},
               'boundary': '只读观测；结束不等于设计通过。缺失时间不推算，Token 来自账本，未自动评分或提升 Harness。'}
    return {**payload, 'analysis_id': identity(payload)}


def compare(left, right):
    def total(analysis, key):
        metric = analysis['metrics'][key]
        return metric['value'] if metric['known'] == metric['total'] else None
    metrics = []
    for key in ('input_tokens', 'output_tokens', 'total_tokens', 'charged_usd'):
        a, b = total(left, key), total(right, key)
        metrics.append({'key': key, 'baseline': a, 'candidate': b, 'delta': b - a if a is not None and b is not None else None})
    for key, a, b in [('tools', left['coverage']['tools'], right['coverage']['tools']),
                      ('duration_ms', left['metrics']['duration_ms'], right['metrics']['duration_ms'])]:
        metrics.append({'key': key, 'baseline': a, 'candidate': b, 'delta': b-a if a is not None and b is not None else None})
    return {'schema_version': 'bf-trace-comparison-v1', 'baseline': left['session_id'], 'candidate': right['session_id'],
            'sources': [left['source'], right['source']], 'metrics': metrics,
            'harness_relation': 'same' if left['source']['harness'] and left['source']['harness'] == right['source']['harness'] else 'different_or_unknown',
            'mode': 'exploratory', 'attribution': None,
            'boundary': '探索性差异；尚未证明任务、输入和实验条件相同，不能据此判定改进或自动提升。'}
