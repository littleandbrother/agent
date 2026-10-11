"""Frozen task, environment, validation and design identities (no verdict in D)."""
import hashlib
import json
import re
from pathlib import Path
from ..store import canonical, identity

SCHEMA = 'bf-design-task-v1'
CASE = 'magnetic-switch-v1'
SCOPE = 'C-F0-opening-event-fixed-D5-envelope-v1'
OWNER = re.compile(r'^pi-chat-[0-9a-f]{16}$')
GATES = ('source_build_binding', 'power_fixed_point', 'event_identity',
         'deadline_receive', 'application_dedup', 'reference_integrity')
PHYSICAL = ('pcb_bom', 'board_pins', 'flashed_target', 'physical_rf', 'measured_power')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            h.update(block)
    return h.hexdigest()


def sealed(path, value):
    """Write once; identical retries are safe, changed data is rejected."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical(value)
    try:
        with path.open('x') as stream:
            stream.write(text)
    except FileExistsError:
        if path.read_text() != text:
            raise ValueError('IMMUTABLE_ARTIFACT_CONFLICT')
    return sha(path)


def owner(value):
    if not isinstance(value, str) or not OWNER.fullmatch(value):
        raise ValueError('DESIGN_OWNER_INVALID')
    return value


def contract(environment_id, validation_id):
    value = {
        'schema_version': SCHEMA, 'case': CASE, 'scope': SCOPE,
        'goal': '开门事件在约定期限内由虚拟接收端正确接收并去重；保留零初始电能及完整关闭积能过程。',
        'environment_id': environment_id, 'validation_id': validation_id,
        'requirements': list(GATES), 'physical_requirements': list(PHYSICAL),
        'event': {'time_s': 2.5, 'event_id': 260011, 'kind': 1,
                  'meaning': 'opening begins', 'deadline_s': 3.0,
                  'response_deadline_s': 0.5},
        'wire': {'bytes': 12, 'magic_ascii': 'BFMC', 'version': 1,
                 'layout': '0..3 magic;4 version;5 kind(1=open,2=close);6..9 uint32 little-endian event_id;10 flags=0;11 XOR of bytes0..10'},
        'supported_actions': ['edit application C/H', 'compile shared C logic and Cortex-M4 object',
                              'execute actual compiled C', 'inspect timed observations',
                              'adopt tested snapshot', 'deliver same snapshot'],
        'fixed': ['D5 mechanical/electrical/ROM/force inputs', '100us clock',
                  'stage-current envelope', 'reset below 1.8V', 'virtual lossless link'],
        'load_policy': 'Native evidence reused only when every time/current/state sample equals the frozen fixed point; changed loads require a new qualified native solve, never a PASS from replay.',
        'execution_level': 'F0 compiled application logic plus F1 Cortex-M4 relocatable object; no emulated SoC, flash image or measured current.',
        'sensor_port': 'Trusted virtual event port derived from the frozen actuator opening onset, available at each tick. GPIO/sensor hardware remains NOT_CHECKED.',
        'claim': 'Finite digital event-service acceptance only; complete product, fabrication, physical and method-gain claims are separate.',
    }
    return {**value, 'task_id': 'task-C-'+identity(value)[:20]}


def snapshot(task, sources, parent=None):
    if not isinstance(sources, dict) or not 1 <= len(sources) <= 16 or 'program.c' not in sources:
        raise ValueError('DESIGN_SOURCE_REQUIRED')
    total = 0
    for name, text in sources.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*\.(c|h)', name) or not isinstance(text, str):
            raise ValueError('DESIGN_SOURCE_PATH_DENIED')
        total += len(text.encode())
    if total > 128_000:
        raise ValueError('DESIGN_SOURCE_SIZE')
    value = {'schema_version': 'bf-design-snapshot-v1', 'task_id': task['task_id'],
             'environment_id': task['environment_id'], 'scope': task['scope'],
             'parent': parent, 'sources': sources,
             'dimensions': {'application': identity(sources), 'physical': task['environment_id']}}
    return {**value, 'design_id': 'D-'+identity(value)}


def check_snapshot(task, value):
    expected = snapshot(task, value.get('sources'), value.get('parent'))
    if value != expected:
        raise ValueError('DESIGN_SNAPSHOT_TAMPER')
    return value


def acceptance(task, design_id, check, current_design):
    """Only called with a trusted check loaded from the service-owned store."""
    exact = (check['task_id'] == task['task_id'] and check['design_id'] == design_id
             and check['environment_id'] == task['environment_id']
             and check['validation_id'] == task['validation_id'] and check['scope'] == task['scope'])
    if not exact:
        raise ValueError('CHECK_BINDING_MISMATCH')
    gates = dict(check['gates'])
    if set(gates) != set(GATES) or any(v not in ('PASS', 'FAIL', 'UNEVALUABLE') for v in gates.values()):
        raise ValueError('CHECK_GATE_SET_MISMATCH')
    stale = design_id != current_design
    passed = not stale and all(v == 'PASS' for v in gates.values())
    return {'schema_version': 'bf-design-acceptance-v1', 'task_id': task['task_id'],
            'design_id': design_id, 'environment_id': task['environment_id'],
            'validation_id': task['validation_id'], 'scope': task['scope'],
            'scoped_status': 'STALE' if stale else 'PASS' if passed else
                             'FAIL' if 'FAIL' in gates.values() else 'UNEVALUABLE',
            'scoped_passed': passed, 'gates': {k: 'STALE' if stale else v for k, v in gates.items()},
            'full_product_passed': False, 'physical': {k: 'NOT_CHECKED' for k in PHYSICAL},
            'method_gain': 'NOT_EVALUATED', 'check_id': check['check_id']}

