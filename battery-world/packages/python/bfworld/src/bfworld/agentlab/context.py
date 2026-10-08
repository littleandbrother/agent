"""Request-only projection; original Pi messages and tool evidence remain immutable."""
import json
import os
import re
from pathlib import Path
from .store import canonical, identity

REQUEST_BYTES = 128000
TARGET_BYTES = 103000
# Local authenticated Pi history is larger than the projected provider request.
# This bounds ingestion only; it never raises the provider wire/token budget.
INTERACTIVE_HISTORY_BYTES = 16 * 1024 * 1024
PRODUCT_STATE_PREFIX = '本次启动的产品状态（可能随消息更新，操作前 inspect）：'


class ContextArchive:
    """Owner-local, content-addressed records readable by Pi's existing tools."""
    def __init__(self, home, owner):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', owner):
            raise ValueError('CONTEXT_ARCHIVE_OWNER_INVALID')
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
        return {'record_file': 'context-records/' + path.name, 'sha256': digest, 'bytes': len(data)}


def _preview(value):
    text = value if isinstance(value, str) else canonical(value)
    data = text.encode()
    return {'head': data[:2400].decode('utf-8', errors='ignore'),
            'tail': data[-800:].decode('utf-8', errors='ignore'), 'partial': True}


def _reference(record):
    return {**record, 'context_projection': 'archived_not_deleted',
            'read_hint': '完整数据在当前工作区的 record_file。用 bash/Python 读取 JSON 并只提取本次需要的字段或片段，勿重复打印全文件。摘要不是新的验证。'}


def project_interactive(payload, archive=None, *, request_bytes=REQUEST_BYTES, target_bytes=TARGET_BYTES):
    if not 8000 <= target_bytes < request_bytes:
        raise ValueError('CONTEXT_LIMITS_INVALID')
    messages = payload.get('messages', [])
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        raise ValueError('MODEL_MESSAGES_INVALID')
    boundary = max((i for i, m in enumerate(messages) if m.get('role') == 'user'), default=0)
    # Observer JSON is machine state, not a new human requirement. Preserve the
    # surrounding instruction verbatim, archive its full bytes, and keep compact
    # findings. Otherwise repeated continuations crowd out the actual tool data.
    working = list(messages)
    observer_archives = []
    templates = [('交付观察器的实际结果：',('bf-product-authority-v1','bf-responsibility-review-v1'),'。原始执行任务仍未完成。'),
                 ('当前任务事实快照（覆盖过时上下文；不改变既定要求）：',('bf-product-context-v1',),'\n用户消息：')]
    if archive and len(canonical(payload).encode()) > target_bytes:
        for i, m in enumerate(messages[:boundary]):
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
    while len(canonical({**payload,'messages':projected}).encode()) > target_bytes:
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
    # A long engineering turn can exhaust the byte cap by repeatedly returning
    # native source and trajectories. Remove only complete old exchanges, never
    # an unmatched or the two most recent exchanges. Full trace is unchanged.
    current_omitted=[]
    while len(canonical({**payload, 'messages':projected}).encode()) > target_bytes + 1000:
        returned={m.get('tool_call_id') for m in projected if m.get('role')=='tool'}
        groups=[(i,[c.get('id') for c in m.get('tool_calls',[])]) for i,m in enumerate(projected)
                if m.get('role')=='assistant' and m.get('tool_calls')]
        complete=[(i,ids) for i,ids in groups if all(k and k in returned for k in ids)]
        if len(complete)<=2:break
        source_pos,ids=complete[0];drop=set(ids);removable.update(ids)
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
            if len(canonical({**payload, 'messages': projected}).encode()) <= target_bytes:
                break
            if m.get('role') != 'system' or not isinstance(m.get('content'), str):
                continue
            lines = m['content'].splitlines(keepends=True)
            for j, line in enumerate(lines):
                # Only the explicitly tagged, machine-generated JSON state is
                # replaceable. Surrounding instructions are never truncated.
                if not line.startswith(PRODUCT_STATE_PREFIX):
                    continue
                raw = line[len(PRODUCT_STATE_PREFIX):]
                try:
                    state = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(state, dict) or len(raw.encode()) <= 8000:
                    continue
                record = archive(state)
                reference = _reference(record)
                for key in ('current_revision', 'binding'):
                    if key in state and len(canonical(state[key]).encode()) <= 1000:
                        reference[key] = state[key]
                reference['preview'] = _preview(raw)
                lines[j] = PRODUCT_STATE_PREFIX + canonical(reference) + ('\n' if line.endswith('\n') else '')
                archived.append({'kind': 'product_state', 'source_index': source_indices.get(id(m)),
                                 'source_message_sha256': identity(m), **record})
            projected[i] = {**m, 'content': ''.join(lines)}
        candidates = sorted(((len(canonical(m.get('content')).encode()), i, m)
            for i, m in enumerate(projected)
            if (m.get('role') == 'tool' and m.get('tool_call_id') in complete_ids
                or m.get('role') == 'assistant' and not m.get('tool_calls'))
            and m.get('content')), reverse=True)
        for size, i, m in candidates:
            if len(canonical({**payload, 'messages': projected}).encode()) <= target_bytes:
                break
            if size <= 8000:
                continue
            record = archive(m)
            projected[i] = {**m, 'content': canonical({**_reference(record), 'preview': _preview(m['content'])})}
            archived.append({'kind': m['role'], 'source_index': source_indices.get(id(m)), **record})
    if removable or omitted_text or archived:
        projected.insert(0, {'role': 'system', 'content':
            '较早的工具交换明细及容量不足时的旧助手文字已从本次上下文省略，原始记录仍保留在 Trace。'
            '用户消息与工程规则保留；标注 archived_not_deleted 的大块数据已存为可回读文件，预览不完整。已有文字总结不等于新的验证；'
            '需要精确事实时读取工作区文件或已有实验结果。不要因明细省略而重复提交已完成实验。'})
    result = {**payload, 'messages': projected}
    audit = {'schema_version': 'bf-interactive-context-v2', 'source_sha256': identity(payload),
             'projected_sha256': identity(result), 'source_bytes': len(canonical(payload).encode()),
             'projected_bytes': len(canonical(result).encode()), 'source_messages': len(messages),
             'projected_messages': len(projected), 'omitted_tool_call_ids': sorted(removable),
             'current_turn_preserved': not current_omitted and not archived and not any(
                 x['source_index'] is not None and x['source_index']>=boundary for x in omitted_text),
             'bounded_turn_omitted_call_ids':current_omitted,'omitted_assistant_messages':omitted_text,
              'archived_messages': archived, 'limit_bytes': request_bytes,
              'fits': len(canonical(result).encode()) <= request_bytes,
             'projected_bytes_by_role': {role: sum(len(canonical(m).encode()) for m in projected if m.get('role') == role)
                                         for role in ('system', 'user', 'assistant', 'tool')},
             'tool_schema_bytes': len(canonical(payload.get('tools', [])).encode())}
    return result, audit
