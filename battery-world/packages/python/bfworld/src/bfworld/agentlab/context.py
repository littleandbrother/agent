"""Request-only projection; original Pi messages and tool evidence remain immutable."""
import json
import hashlib
import os
import re
from pathlib import Path
from .store import canonical, identity

REQUEST_BYTES = 128000
TARGET_BYTES = 103000
# Local authenticated Pi history is larger than the projected provider request.
# This bounds ingestion only; it never raises the provider wire/token budget.
# Authenticated local SDK history may outgrow 16 MiB in a preserved long session.
# This is a bounded ingress envelope, not the provider wire/context allowance;
# project_interactive still archives completed exchanges and enforces its pinned
# profile limit. The original SDK session and all billing remain untouched.
INTERACTIVE_HISTORY_BYTES = 64 * 1024 * 1024
PRODUCT_STATE_PREFIX = '本次启动的产品状态（可能随消息更新，操作前 inspect）：'
PRODUCT_STATE_PREFIXES = (PRODUCT_STATE_PREFIX, '启动事实快照（操作前 inspect 核对）：')


class _RequestSize:
    """Exact canonical UTF-8 size, without serializing the whole history per eviction."""
    def __init__(self, payload):
        self.base = len(canonical({**payload, 'messages': []}).encode())
        self.cache = {}

    def __call__(self, messages):
        sizes = []
        for m in messages:
            key = id(m)
            if key not in self.cache:
                self.cache[key] = (m, len(canonical(m).encode()))
            sizes.append(self.cache[key][1])
        return self.base + sum(sizes) + max(0, len(messages)-1)


class ContextArchive:
    """Owner-local, content-addressed records readable by Pi's existing tools."""
    def __init__(self, home, owner):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', owner):
            raise ValueError('CONTEXT_ARCHIVE_OWNER_INVALID')
        self.owner = owner
        self.home = Path(home).resolve()
        self.parts = ('participants', owner, 'context-records')

    def __call__(self, value):
        directory = self.home
        for part in self.parts:
            directory = directory / part
            if directory.is_symlink():
                raise ValueError('CONTEXT_ARCHIVE_SYMLINK')
            directory.mkdir(mode=0o700, exist_ok=True)
        data = canonical(value).encode()
        digest = identity(value)
        path = directory / (digest + '.json')
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError('CONTEXT_ARCHIVE_CONFLICT')
        else:
            with os.fdopen(fd, 'wb') as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            path.chmod(0o444)
        record = {'record_file': 'context-records/' + path.name, 'sha256': digest, 'bytes': len(data)}
        # Raw model messages are not the same schema as their tool text. Keep
        # the original bytes and expose a deterministic readable companion;
        # the model must not spend calls guessing successive JSON wrappers.
        if isinstance(value, dict) and value.get('role') == 'tool':
            content = value.get('content')
            decoded = content
            if isinstance(content, str):
                try: decoded = json.loads(content)
                except ValueError: pass
            blocks = decoded.get('content') if isinstance(decoded, dict) else decoded
            if (isinstance(blocks, list) and blocks and
                    all(isinstance(x, dict) and x.get('type') == 'text' and isinstance(x.get('text'), str) for x in blocks)):
                content = '\n'.join(x['text'] for x in blocks)
            if isinstance(content, str):
                raw = content.encode();text_path = directory / (digest + '.tool.txt')
                try: fd = os.open(text_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                except FileExistsError:
                    if text_path.is_symlink() or text_path.read_bytes() != raw: raise ValueError('CONTEXT_ARCHIVE_CONFLICT')
                else:
                    with os.fdopen(fd, 'wb') as file:
                        file.write(raw);file.flush();os.fsync(file.fileno())
                    text_path.chmod(0o444)
                record.update(text_file='context-records/'+text_path.name,
                              text_sha256=hashlib.sha256(raw).hexdigest(),text_bytes=len(raw))
        return record


def _preview(value, *, head_bytes=2400, tail_bytes=800):
    text = value if isinstance(value, str) else canonical(value)
    data = text.encode()
    return {'head': data[:head_bytes].decode('utf-8', errors='ignore'),
            'tail': data[-tail_bytes:].decode('utf-8', errors='ignore'), 'partial': True}


def _reference(record):
    return {**record, 'context_projection': 'archived_not_deleted',
            'read_hint': ('用 read 分段读取 text_file，它是已解包的原工具文本；不要猜 preview/content 的嵌套格式。record_file 保留原始消息及身份，二者哈希分别记录；旧文本不是新验证。'
                          if record.get('text_file') else
                          '完整数据在当前工作区的 record_file。用 bash/Python 读取 JSON 并只提取本次需要的字段或片段，勿重复打印全文件。摘要不是新的验证。')}


def _project_superseded_phase_states(messages, archive):
    """Archive only recognized generated state; keep all surrounding user text."""
    prefix = '当前任务事实快照（覆盖过时上下文；不改变既定要求）：'
    snapshots = []
    for index, message in enumerate(messages):
        if message.get('role') != 'user':
            continue
        raw = message.get('content')
        text = raw
        if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], dict) and raw[0].get('type') == 'text':
            text = raw[0].get('text')
        if not isinstance(text, str) or not text.startswith(prefix):
            continue
        try:
            state, end = json.JSONDecoder().raw_decode(text[len(prefix):])
        except (ValueError, TypeError):
            continue
        suffix = text[len(prefix) + end:]
        if (not isinstance(state, dict) or state.get('schema_version') != 'bf-product-context-v1'
                or not suffix.startswith('\n用户消息：')
                or state.get('state_authority') == 'HISTORICAL_SUPERSEDED'):
            continue
        snapshots.append((index, message, raw, state, suffix))
    if not archive or len(snapshots) < 2:
        return list(messages), []
    latest_index, _, _, latest, _ = snapshots[-1]
    if (latest.get('context_scope') not in ('current-original-paper-native-phase', 'single-candidate-lifecycle')
            or latest.get('owner') != getattr(archive, 'owner', None)
            or not latest.get('owner')
            or any(not isinstance(latest.get(k, []), list) for k in ('requirements', 'assumptions'))):
        return list(messages), []
    projected, records = list(messages), []
    for index, message, raw, state, suffix in snapshots[:-1]:
        # Do not subsume a separately identified owner/paper into this phase.
        if (state.get('owner') not in (None, latest['owner'])
                or state.get('paper_id') not in (None, latest.get('paper_id'))):
            continue
        record = archive(state)
        historical = {'schema_version': state['schema_version'], **_reference(record),
                      'state_authority': 'HISTORICAL_SUPERSEDED',
                      'current_snapshot_source_index': latest_index,
                      'constraints_kept_verbatim_in_latest': []}
        for key in ('requirements', 'assumptions'):
            if key not in state:
                continue
            if canonical(state[key]) == canonical(latest.get(key)):
                historical['constraints_kept_verbatim_in_latest'].append(key)
            else:
                historical[key] = state[key]
        reduced = '历史任务事实快照（仅保留追溯；当前事实以最新快照为准）：' + canonical(historical) + suffix
        projected[index] = {**message, 'content': [{**raw[0], 'text': reduced}] if isinstance(raw, list) else reduced}
        records.append({'kind': 'superseded_product_context', 'source_index': index,
                        'source_message_sha256': identity(message), **record})
    return projected, records


def project_interactive(payload, archive=None, *, request_bytes=REQUEST_BYTES, target_bytes=TARGET_BYTES, active_skills=(), compact_state=False, closed_continuations=None, aggregate_closed=False, deduplicate_skills=False):
    if not 8000 <= target_bytes < request_bytes:
        raise ValueError('CONTEXT_LIMITS_INVALID')
    if type(compact_state) is not bool:
        raise ValueError('CONTEXT_STRATEGY_INVALID')
    state_prefixes = PRODUCT_STATE_PREFIXES if compact_state else (PRODUCT_STATE_PREFIX,)
    messages = payload.get('messages', [])
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        raise ValueError('MODEL_MESSAGES_INVALID')
    # Server-owned frozen methods survive completed tool-pair compaction. They
    # never contain task facts or promote untrusted tool output into policy.
    if deduplicate_skills and active_skills:
        by_id = {x['id']: x for x in active_skills}
        if any(x['sha256'] != by_id[x['id']]['sha256'] or x['manifest_sha256'] != by_id[x['id']]['manifest_sha256'] for x in active_skills):
            raise ValueError('ACTIVE_SKILL_VERSION_CONFLICT')
        active_skills = tuple(by_id[k] for k in sorted(by_id))
        # Activation output is already supplied by the protected frozen method.
        # Keep its identity and resource index in history, rather than a second body.
        reduced = []
        for m in messages:
            replacement = m
            if m.get('role') == 'tool' and isinstance(m.get('content'), str):
                try:
                    value = json.loads(m['content'])
                except ValueError:
                    value = None
                if isinstance(value, dict) and value.get('schema_version') == 'bf-skill-activation-v1':
                    method = by_id.get(value.get('id'))
                    if method and value.get('sha256') == method['sha256'] and value.get('manifest_sha256') == method['manifest_sha256'] and value.get('content') == method['content']:
                        record = archive(m) if archive else None
                        if record:
                            replacement = {**m, 'content': canonical({**{k:v for k,v in value.items() if k != 'content'}, **record, 'body_in_protected_skill_context': True})}
            reduced.append(replacement)
        messages = reduced
    if active_skills:
        methods='\n\n'.join('Skill '+x['id']+' @ '+x['sha256']+'\n'+x['content'] for x in active_skills)
        protected={'role':'system','content':'本运行已激活的专业方法（不改变用户任务、权限或预算）：\n'+methods}
        messages=[*messages[:1],protected,*messages[1:]]
        payload={**payload,'messages':messages}
    request_size = _RequestSize(payload)
    boundary = max((i for i, m in enumerate(messages) if m.get('role') == 'user'), default=0)
    # Observer JSON is machine state, not a new human requirement. Preserve the
    # surrounding instruction verbatim, archive its full bytes, and keep compact
    # findings. Otherwise repeated continuations crowd out the actual tool data.
    from .continuation_context import project_closed_continuations
    # Registered finished controller stages are history at any request size.
    # Keep the current registered stage and actual human instructions exact.
    source_message_count = len(messages)
    managed, closed_archives = project_closed_continuations(messages, archive, closed_continuations, aggregate=aggregate_closed)
    working, observer_archives = _project_superseded_phase_states(managed, archive)
    observer_archives = [*closed_archives, *observer_archives]
    # Aggregation changes positions. Subsequent compaction operates on the new
    # list, retaining current user boundaries and native call/result pairs.
    messages = working
    boundary = max((i for i, m in enumerate(messages) if m.get('role') == 'user'), default=0)
    # Current startup state has a new explicit machine tag. Compact it before
    # evicting useful exchanges. Human text copied into it may be omitted only
    # when the same text is still verbatim in an actual user message.
    user_texts = []
    for m in messages:
        if m.get('role') != 'user':
            continue
        c = m.get('content', '')
        user_texts.append(c if isinstance(c, str) else '\n'.join(
            p.get('text', '') for p in c if isinstance(p, dict)) if isinstance(c, list) else '')
    if archive and (compact_state or request_size(working)>target_bytes):
        for i, m in enumerate(messages):
            if m.get('role') != 'system' or not isinstance(m.get('content'), str):
                continue
            lines = m['content'].splitlines(keepends=True)
            changed = False
            for j, line in enumerate(lines):
                prefixes = state_prefixes if compact_state else ('启动事实快照（操作前 inspect 核对）：',)
                p = next((p for p in prefixes if line.startswith(p)), None)
                if not p:
                    continue
                raw = line[len(p):]
                try:
                    value = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(value, dict) or len(raw.encode()) <= 8000:
                    continue
                copied = value.get('messages')
                duplicated = isinstance(copied,list) and all(
                    isinstance(x,dict) and isinstance(x.get('text'),str)
                    and any(x['text'] in u for u in user_texts) for x in copied)
                if not compact_state and (not copied or not duplicated):
                    continue  # Distinct copied human requirements remain exact.
                record = archive(value)
                reference = _reference(record)
                for key in ('current_revision', 'binding', 'assembly', 'engineering', 'instruction'):
                    if key in value and len(canonical(value[key]).encode()) <= 4000:
                        reference[key] = value[key]
                if isinstance(copied, list):
                    if duplicated:
                        reference['human_messages_preserved_in_user_history'] = True
                    else:
                        reference['messages'] = copied
                if not compact_state and 'instruction' in value:
                    reference['instruction'] = value['instruction']
                reference['preview'] = _preview(raw)
                lines[j] = p + canonical(reference) + ('\n' if line.endswith('\n') else '')
                observer_archives.append({'kind':'product_state','source_index':i,
                                          'source_message_sha256':identity(m),**record})
                changed = True
            if changed:
                working[i] = {**m,'content':''.join(lines)}
    templates = [('交付观察器的实际结果：',('bf-product-authority-v1','bf-responsibility-review-v1'),'。原始执行任务仍未完成。'),
                 ('当前任务事实快照（覆盖过时上下文；不改变既定要求）：',('bf-product-context-v1',),'\n用户消息：')]
    if archive and len(canonical(payload).encode()) > target_bytes:
        for i, m in enumerate(messages[:boundary]):
            if working[i] is not messages[i]:
                continue  # Already a scoped superseded-state reference.
            raw_content = m.get('content')
            content = raw_content
            if isinstance(raw_content,list) and len(raw_content)==1 and isinstance(raw_content[0],dict) and raw_content[0].get('type')=='text':
                content = raw_content[0].get('text')
            if m.get('role') != 'user' or not isinstance(content, str): continue
            template = next((x for x in templates if content.startswith(x[0])),None)
            if template is None: continue
            prefix, schemas, suffix_start = template
            try: value, end = json.JSONDecoder().raw_decode(content[len(prefix):])
            except (ValueError, TypeError): continue
            suffix = content[len(prefix)+end:]
            if not isinstance(value, dict) or value.get('schema_version') not in schemas or not suffix.startswith(suffix_start): continue
            if len(canonical(value).encode()) < 2000: continue
            record = archive(value)
            review = value.get('responsibility_review', value)
            compact = {k:review[k] for k in ('schema_version','status','source_revision','revision','requirements','assumptions','missing','errors','actionable','blocked','engineering_passed','agent_autonomy_proven') if k in review}
            compact.update(_reference(record))
            reduced = prefix + canonical(compact) + suffix
            working[i] = {**m, 'content':[{**raw_content[0],'text':reduced}] if isinstance(raw_content,list) else reduced}
            observer_archives.append({'kind':'delivery_observation' if len(schemas)>1 else 'product_context','source_index':i,'source_message_sha256':identity(m),**record})
    # Keep real call/result pairs across user/observer boundaries. Dropping
    # every previous-turn tool call while retaining its "I will read..." prose
    # creates a false, action-free transcript and loses current engineering facts.
    # Complete old exchanges are evicted atomically below only under pressure.
    removable = set()
    projected = list(working)
    # Repeated resumptions also accumulate assistant prose. Its original text
    # remains in the journal; discard only older assistant-only messages under
    # byte pressure. Never trim user requirements or unresolved tool exchanges.
    omitted_text=[]
    recent_text={id(m) for m in [m for m in projected
        if m.get('role')=='assistant' and m.get('content')][-4:]}
    source_indices={id(m):i for i,m in enumerate(messages)}
    # Reserve space for the projection notice itself.
    while request_size(projected) > target_bytes:
        candidate=next((i for i,m in enumerate(projected)
            if m.get('role')=='assistant' and not m.get('tool_calls')
            and id(m) not in recent_text),None)
        if candidate is None:break
        m=projected.pop(candidate)
        source_index=source_indices.get(id(m))
        if source_index is None:
            source_index=next((i for i,original in enumerate(messages)
                if {k:v for k,v in original.items() if k!='tool_calls'}==m),None)
        omitted_text.append({'source_index':source_index,'sha256':identity(m),
                             'bytes':len(canonical(m).encode())})
    # Evict complete historical exchanges first. When exact archives are
    # available, spill current evidence before evicting current call/results.
    # Otherwise a large protected user history repeatedly leaves only the last
    # two reads, even when compact evidence would preserve much more work.
    current_omitted=[]
    while request_size(projected) > target_bytes + 1000:
        returned={m.get('tool_call_id') for m in projected if m.get('role')=='tool'}
        groups=[(i,[c.get('id') for c in m.get('tool_calls',[])]) for i,m in enumerate(projected)
                if m.get('role')=='assistant' and m.get('tool_calls')]
        complete=[(i,ids) for i,ids in groups if all(k and k in returned for k in ids)]
        if len(complete)<=2:break
        eligible=[(i,ids) for i,ids in complete
                  if not archive or source_indices.get(id(projected[i]),0)<boundary]
        if not eligible:break
        source_pos,ids=eligible[0];drop=set(ids);removable.update(ids)
        if source_indices.get(id(projected[source_pos]), 0) >= boundary:
            current_omitted.extend(ids)
        reduced=[]
        for m in projected:
            if m.get('role')=='tool' and m.get('tool_call_id') in drop:continue
            mids=[c.get('id') for c in m.get('tool_calls',[])]
            if mids and set(mids)<=drop:continue
            reduced.append(m)
        projected=reduced
    # The last two exchanges and recent prose are useful, but not unbounded.
    # Spill only completed evidence/content to immutable owner-local records;
    # keep every call id/argument, system instruction and user message intact.
    archived = list(observer_archives)
    if archive:
        returned = {m.get('tool_call_id') for m in projected if m.get('role') == 'tool'}
        complete_ids = {key for m in projected if m.get('role') == 'assistant'
                        for ids in [[c.get('id') for c in m.get('tool_calls', [])]]
                        if ids and all(key and key in returned for key in ids) for key in ids}
        for i, m in enumerate(projected):
            if request_size(projected) <= target_bytes:
                break
            if m.get('role') != 'system' or not isinstance(m.get('content'), str):
                continue
            lines = m['content'].splitlines(keepends=True)
            for j, line in enumerate(lines):
                # Only the explicitly tagged, machine-generated JSON state is
                # replaceable. Surrounding instructions are never truncated.
                matched_prefix = next((p for p in state_prefixes if line.startswith(p)), None)
                if matched_prefix is None:
                    continue
                raw = line[len(matched_prefix):]
                try:
                    state = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(state, dict) or len(raw.encode()) <= 8000:
                    continue
                if compact_state and state.get('context_projection') == 'archived_not_deleted':
                    continue  # Never recursively spill protected copied human text.
                record = archive(state)
                reference = _reference(record)
                fields = ('current_revision', 'binding', 'assembly', 'engineering', 'instruction') if compact_state else ('current_revision', 'binding')
                for key in fields:
                    if key in state and len(canonical(state[key]).encode()) <= 1000:
                        reference[key] = state[key]
                reference['preview'] = _preview(raw)
                lines[j] = matched_prefix + canonical(reference) + ('\n' if line.endswith('\n') else '')
                archived.append({'kind': 'product_state', 'source_index': source_indices.get(id(m)),
                                 'source_message_sha256': identity(m), **record})
            projected[i] = {**m, 'content': ''.join(lines)}
        candidates = sorted(((len(canonical(m.get('content')).encode()), i, m)
            for i, m in enumerate(projected)
            if (m.get('role') == 'tool' and m.get('tool_call_id') in complete_ids
                or m.get('role') == 'assistant' and not m.get('tool_calls'))
            and m.get('content')), reverse=True)
        for size, i, m in candidates:
            if request_size(projected) <= target_bytes:
                break
            if size <= 1600:
                continue
            record = archive(m)
            # A completed parallel batch can exceed the cap even when each
            # reply is below the large-result threshold. Keep all call IDs,
            # arguments and results; spill the evidence bytes, not the pair.
            preview = (_preview(m['content']) if size > 8000 else
                       _preview(m['content'], head_bytes=768, tail_bytes=256))
            content = canonical({**_reference(record), 'preview': preview})
            if len(content.encode()) >= size:
                continue  # A reference must actually reduce this message.
            projected[i] = {**m, 'content': content}
            archived.append({'kind': m['role'], 'source_index': source_indices.get(id(m)),
                             'preview_budget_bytes': 3200 if size > 8000 else 1024,
                             'before_current_turn_eviction': True, **record})
    # Compact current evidence may still exceed the cap (e.g. many large call
    # arguments or small replies). Only then remove complete exchanges, keeping
    # unresolved/partial batches and the two newest complete exchanges intact.
    while request_size(projected)>target_bytes+1000:
        returned={m.get('tool_call_id') for m in projected if m.get('role')=='tool'}
        groups=[(i,[c.get('id') for c in m.get('tool_calls',[])]) for i,m in enumerate(projected)
                if m.get('role')=='assistant' and m.get('tool_calls')]
        complete=[(i,ids) for i,ids in groups if all(k and k in returned for k in ids)]
        if len(complete)<=2:break
        source_pos,ids=complete[0];drop=set(ids);removable.update(ids)
        if source_indices.get(id(projected[source_pos]),0)>=boundary:current_omitted.extend(ids)
        projected=[m for m in projected if not (
            m.get('role')=='tool' and m.get('tool_call_id') in drop or
            m.get('tool_calls') and set(c.get('id') for c in m['tool_calls'])<=drop)]
    if removable or omitted_text or archived:
        projected.insert(0, {'role': 'system', 'content':
            '较早的工具交换明细及容量不足时的旧助手文字已从本次上下文省略，原始记录仍保留在 Trace。'
            '用户消息与工程规则保留；标注 archived_not_deleted 的大块数据已存为可回读文件，预览不完整。已有文字总结不等于新的验证；'
            '需要精确事实时读取工作区文件或已有实验结果。不要因明细省略而重复提交已完成实验。'})
    result = {**payload, 'messages': projected}
    audit = {'schema_version': 'bf-interactive-context-v2', 'source_sha256': identity(payload),
             'projected_sha256': identity(result), 'source_bytes': len(canonical(payload).encode()),
              'projected_bytes': len(canonical(result).encode()), 'source_messages': source_message_count,
             'projected_messages': len(projected), 'omitted_tool_call_ids': sorted(removable),
             'current_turn_preserved': not current_omitted and not archived and not any(
                 x['source_index'] is not None and x['source_index']>=boundary for x in omitted_text),
             'bounded_turn_omitted_call_ids':current_omitted,'omitted_assistant_messages':omitted_text,
             'current_turn_retained_call_ids':[c['id'] for m in projected
                 if m.get('role')=='assistant' and source_indices.get(id(m),0)>=boundary
                 for c in m.get('tool_calls',[]) if c.get('id')],
              'archived_messages': archived, 'limit_bytes': request_bytes,
              'fits': len(canonical(result).encode()) <= request_bytes,
             'projected_bytes_by_role': {role: sum(len(canonical(m).encode()) for m in projected if m.get('role') == role)
                                         for role in ('system', 'user', 'assistant', 'tool')},
             'tool_schema_bytes': len(canonical(payload.get('tools', [])).encode()),
             'active_skills': [{k:x[k] for k in ('id','version','sha256','manifest_sha256')} | {
                 'present_in_projected_request': any(x['content'] in m.get('content','') for m in projected if isinstance(m.get('content'),str))
             } for x in active_skills]}
    return result, audit
