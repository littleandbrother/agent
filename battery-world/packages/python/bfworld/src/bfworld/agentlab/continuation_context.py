"""Provenance-bound context for closed native controller stages, never user history deletion."""
import hashlib
import json
import re
from pathlib import Path
from .store import canonical, identity

KEY = '_closed_continuation_context'
SCHEMA = 'bf-closed-native-continuation-context-v1'
PREFIXES = ('当前任务事实快照（覆盖过时上下文；不改变既定要求）：',
            '历史任务事实快照（仅保留追溯；当前事实以最新快照为准）：')
DELIMITER = '\n用户消息：'


def enabled(focused):
    value = (focused or {}).get('archive_closed_continuations', False)
    if type(value) is not bool:
        raise ValueError('CLOSED_CONTINUATION_STRATEGY_INVALID')
    return value


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _operation(target):
    return 'native-cont-' + identity(str(target))[:20]


def _row(db, owner, operation, *, active=False):
    row = db.execute('SELECT * FROM chat_messages WHERE conversation=? AND operation=?',
                     (owner, operation)).fetchone()
    statuses = ('QUEUED', 'SENT', 'ACCEPTED') if active else ('ACCEPTED',)
    if not row or row['status'] not in statuses:
        raise ValueError('CLOSED_CONTINUATION_MESSAGE_MISSING')
    return {'id': row['id'], 'owner': owner, 'operation': operation, 'text': row['text'],
            'text_sha256': hashlib.sha256(row['text'].encode()).hexdigest()}


def build_manifest(root, owner, target, db):
    """Read only. Every eligible message has its own completed original-owner attempt."""
    root, target = Path(root).resolve(), Path(target)
    runs = root / 'campaign/native-runs'
    # Native operation identity uses the controller's exact lexical path. Use
    # resolve only for ownership validation, never to rewrite historical ids.
    if (not target.is_absolute() or not target.resolve().is_relative_to(runs)
            or target.parent.name != 'continuations'):
        raise ValueError('CLOSED_CONTINUATION_TARGET_INVALID')
    original = json.loads((target.parent.parent / 'attempt.json').read_text())
    if original.get('owner') != owner:
        raise ValueError('CLOSED_CONTINUATION_OWNER_MISMATCH')
    # The controller pins the just-queued intent before launching Pi. Projection
    # additionally requires the exact active text to be present in SDK history.
    active = _row(db, owner, _operation(target), active=True)
    phase = target / 'phase-task.json'
    if not phase.is_file():
        raise ValueError('CLOSED_CONTINUATION_PHASE_MISSING')
    body = json.loads(phase.read_text())
    if not isinstance(body.get('task'), str) or body['task'] not in active['text']:
        raise ValueError('CLOSED_CONTINUATION_ACTIVE_TASK_MISMATCH')
    closed = []
    for attempt in sorted(target.parent.glob('turn-*/attempt.json')):
        folder = attempt.parent
        result = folder / 'result.json'
        if folder == target or not result.is_file():
            continue
        a = json.loads(attempt.read_text())
        if (a.get('owner') != owner or not a.get('continuation') or
                a.get('task') != original.get('task')):
            continue
        try:
            row = _row(db, owner, _operation(folder))
        except ValueError:
            continue
        row.update(attempt={'path': str(attempt), 'sha256': _digest(attempt)},
                   closed_result={'path': str(result), 'sha256': _digest(result)})
        closed.append(row)
    return {'schema_version': SCHEMA, 'owner': owner, 'paper_id': original['paper'],
            'generated_by': 'native-controller', 'active_message': active,
            'active_phase': {'path': str(phase), 'sha256': _digest(phase)},
            'closed_messages': closed}


def load_manifest(store, owner):
    """Verify server-owned metadata, original message rows and immutable closure bytes."""
    with store.connect() as db:
        # A standalone provider without Organization has no history policy.
        # Preserve that supported default rather than requiring a new schema.
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_contexts'").fetchone():
            return None
        row = db.execute('SELECT config FROM chat_contexts WHERE owner=?', (owner,)).fetchone()
        reference = json.loads(row['config']).get(KEY) if row else None
        if reference is None:
            return None
        if not isinstance(reference, dict) or reference.get('owner') != owner:
            raise ValueError('CLOSED_CONTINUATION_OWNER_MISMATCH')
        root = Path(store.root).resolve().parent.parent
        path = Path(reference['path'])
        if (path.is_symlink() or not path.resolve().is_relative_to(root / 'campaign/native-runs')
                or path.stat().st_size > 2 * 1024 * 1024 or _digest(path) != reference['sha256']):
            raise ValueError('CLOSED_CONTINUATION_MANIFEST_INTEGRITY')
        manifest = json.loads(path.read_text())
        if (manifest.get('schema_version') != SCHEMA or manifest.get('owner') != owner or
                manifest.get('generated_by') != 'native-controller'):
            raise ValueError('CLOSED_CONTINUATION_MANIFEST_INVALID')
        active = manifest['active_message']
        if _row(db, owner, active['operation'], active=True) != active:
            raise ValueError('CLOSED_CONTINUATION_MESSAGE_CHANGED')
        phase = manifest['active_phase']
        if Path(phase['path']).parent != path.parent or _digest(phase['path']) != phase['sha256']:
            raise ValueError('CLOSED_CONTINUATION_ACTIVE_PHASE_CHANGED')
        if json.loads(Path(phase['path']).read_text())['task'] not in active['text']:
            raise ValueError('CLOSED_CONTINUATION_ACTIVE_TASK_MISMATCH')
        for item in manifest['closed_messages']:
            message = {k: item[k] for k in ('id', 'owner', 'operation', 'text', 'text_sha256')}
            if item['owner'] != owner or _row(db, owner, item['operation']) != message:
                raise ValueError('CLOSED_CONTINUATION_MESSAGE_CHANGED')
            attempt, result = item['attempt'], item['closed_result']
            folder = Path(attempt['path']).parent
            if (folder == path.parent or folder.parent != path.parent.parent or
                    Path(result['path']) != folder / 'result.json' or
                    item['operation'] != _operation(folder)):
                raise ValueError('CLOSED_CONTINUATION_CLOSURE_SCOPE')
            for fact in (attempt, result):
                p = Path(fact['path'])
                if p.is_symlink() or _digest(p) != fact['sha256']:
                    raise ValueError('CLOSED_CONTINUATION_CLOSURE_CHANGED')
            a = json.loads(Path(attempt['path']).read_text())
            if a.get('owner') != owner or not a.get('continuation'):
                raise ValueError('CLOSED_CONTINUATION_OWNER_MISMATCH')
        return manifest


def _snapshot(message):
    if message.get('role') != 'user':
        return None
    raw = message.get('content')
    if isinstance(raw, list):
        if len(raw) != 1 or not isinstance(raw[0], dict) or raw[0].get('type') != 'text':
            return None
        text = raw[0].get('text')
    else:
        text = raw
    if not isinstance(text, str):
        return None
    prefix = next((p for p in PREFIXES if text.startswith(p)), None)
    if not prefix:
        return None
    try:
        state, end = json.JSONDecoder().raw_decode(text[len(prefix):])
    except (ValueError, TypeError):
        return None
    suffix = text[len(prefix) + end:]
    if (not isinstance(state, dict) or state.get('schema_version') != 'bf-product-context-v1'
            or not suffix.startswith(DELIMITER)):
        return None
    return raw, state, suffix[len(DELIMITER):]


def project_closed_continuations(messages, archive, manifest, *, aggregate=False):
    """Only exact registered closed controller messages; current and human messages stay exact."""
    if not archive or not manifest:
        return list(messages), []
    owner = getattr(archive, 'owner', None)
    if manifest.get('schema_version') != SCHEMA or manifest.get('owner') != owner:
        raise ValueError('CLOSED_CONTINUATION_OWNER_MISMATCH')
    active = manifest['active_message']['text']
    snapshots = [(i, _snapshot(m)) for i, m in enumerate(messages)]
    active_indices = [i for i, s in snapshots if s and s[2] == active]
    if not active_indices:
        return list(messages), []
    active_index = active_indices[-1]
    latest = snapshots[active_index][1][1]
    if (latest.get('owner') != owner or latest.get('paper_id') != manifest['paper_id'] or
            latest.get('context_scope') not in ('current-original-paper-native-phase', 'single-candidate-lifecycle')):
        return list(messages), []
    by_text = {}
    for item in manifest['closed_messages']:
        by_text.setdefault(item['text'], []).append(item)
    # Identical generated messages in separate attempts cannot be identified by
    # content alone. Leave them intact instead of inventing a specific closure.
    eligible = {text: items[0] for text, items in by_text.items() if len(items) == 1}
    projected, records = list(messages), []
    for i, s in snapshots:
        if not s or i >= active_index or s[2] not in eligible:
            continue
        raw, state, text = s
        item = eligible[text]
        if (state.get('owner') not in (None, owner) or
                state.get('paper_id') not in (None, manifest['paper_id']) or
                hashlib.sha256(text.encode()).hexdigest() != item['text_sha256']):
            continue
        record = archive(messages[i])
        historical = {'schema_version': SCHEMA, 'state_authority': 'CLOSED_CONTROLLER_STAGE',
                      'message_id': item['id'], 'operation': item['operation'],
                      'closed_result': item['closed_result'], **record,
                      'current_stage_message_id': manifest['active_message']['id']}
        for key in ('requirements', 'assumptions'):
            if key in state and canonical(state[key]) != canonical(latest.get(key)):
                historical[key] = state[key]
        content = '历史控制器阶段（已封存；当前任务保留在最新阶段）：' + canonical(historical)
        projected[i] = {**messages[i], 'content': [{**raw[0], 'text': content}] if isinstance(raw, list) else content}
        records.append({'kind': 'closed_controller_continuation', 'source_index': i,
                        'source_message_sha256': identity(messages[i]), 'message_id': item['id'], **record})
    if aggregate and len(records) > 1:
        positions = {r['source_index'] for r in records}
        # One immutable index replaces only exact, provenance-verified controller
        # messages. Distinct prior constraints remain in the live request.
        index = archive({'schema_version': 'bf-closed-controller-index-v1',
                         'owner': owner, 'current_stage_message_id': manifest['active_message']['id'],
                         'records': records})
        constraints = {}
        for i in sorted(positions):
            state = snapshots[i][1][1]
            for key in ('requirements', 'assumptions'):
                for item in state.get(key, []):
                    if canonical(item) not in {canonical(x) for x in latest.get(key, [])}:
                        constraints.setdefault(key, {})[canonical(item)] = item
        summary = {'schema_version': SCHEMA, 'state_authority': 'CLOSED_CONTROLLER_STAGE',
                   'closed_stage_count': len(records), **index,
                   'current_stage_message_id': manifest['active_message']['id'],
                   **{k: list(v.values()) for k, v in constraints.items()}}
        first = min(positions)
        projected[first] = {'role': 'user', 'content': '历史控制器索引：' + canonical(summary)}
        projected = [m for i, m in enumerate(projected) if i == first or i not in positions]
        records.append({'kind': 'closed_controller_index', 'source_index': first, **index})
    return projected, records
