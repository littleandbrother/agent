"""Read-only method source binding and actual-provider capability checks.

Compatibility never supplies execution permission or scientific qualification.
"""
import hashlib
import json
import re
from pathlib import Path

PROFILES = {'strong_generic': (False, False), 'bf_design': (True, True),
            'representation_only': (True, False), 'revision_only': (False, True)}
PROVIDER = {'id': 'upstream-338d603-numeric-candidate-only', 'numeric_parameters': True,
            'architecture': False, 'candidate_artifact_sources': False}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def profile(method_id):
    if method_id not in PROFILES:
        raise ValueError('UNKNOWN_METHOD_PROFILE')
    r, q = PROFILES[method_id]
    return {'schema': 'bf-method-policy-v1', 'method_id': method_id, 'R': r, 'Q': q, 'candidate_opportunities': 2}

def bind_method(pi_root, method_id):
    root = Path(pi_root) / 'packages/bf-harness'
    files = {'method_source_sha256': root/'src/method.ts', 'method_build_sha256': root/'dist/method.js',
             'solver_source_sha256': root/'src/solver.ts', 'solver_build_sha256': root/'dist/solver.js'}
    value = {'schema': 'bf-method-binding-v1', 'profile': profile(method_id),
             **{key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in files.items()}}
    return {**value, 'binding_id': digest(value)}

def capability_admission(task):
    allowed = task.get('allowed_design')
    if not isinstance(allowed, dict) or not isinstance(allowed.get('permissions_per_arm'), dict) or not allowed['permissions_per_arm']:
        raise ValueError('TASK_CAPABILITY_REQUIREMENTS_MISSING')
    arms = allowed.get('all_main_arms')
    if not isinstance(arms, list) or not arms or len(set(arms)) != len(arms) or set(arms) != set(allowed['permissions_per_arm']):
        raise ValueError('TASK_ARM_COVERAGE_MISMATCH')
    components = allowed.get('candidate_components')
    source_components = {'beam_and_piezo_geometry', 'magnet_geometry_and_mount', 'passive_mechanical_release',
                         'rectifier_and_power_topology', 'real_storage_components', 'firmware_policy_and_payload'}
    numeric_components = {'bounded_numeric_parameters'}
    if not isinstance(components, list) or not components or any(not isinstance(x, str) or x not in source_components | numeric_components for x in components):
        raise ValueError('TASK_COMPONENT_CAPABILITY_UNKNOWN')
    permissions = list(allowed['permissions_per_arm'].values())
    fields = ('architecture_changes', 'mechanical_changes', 'circuit_changes', 'firmware_changes', 'cross_domain_changes')
    if any(not isinstance(p, dict) or any(type(p.get(key)) is not bool for key in fields) for p in permissions):
        raise ValueError('TASK_CAPABILITY_REQUIREMENTS_MALFORMED')
    # Never infer support from an arm label or permit a restricted strong baseline.
    if any(p != permissions[0] for p in permissions[1:]):
        raise ValueError('TASK_ARM_FREEDOM_MISMATCH')
    architecture = permissions[0]['architecture_changes']
    source_required = architecture or bool(set(components) & source_components)
    required = {'architecture': architecture, 'candidate_artifact_sources': source_required}
    blockers = []
    if architecture: blockers.append('PROVIDER_ARCHITECTURE_NOT_IMPLEMENTED')
    if source_required: blockers.append('PROVIDER_CANDIDATE_SOURCES_NOT_IMPLEMENTED')
    return {'provider': dict(PROVIDER), 'required': required, 'capability_compatible': not blockers,
            'blockers': blockers, 'execution_authorized': False, 'scientific_qualified': False}

def verify_activation(events, binding, *, pid, author_pid, nonce, packet_id, exit_code):
    """Trusted supervisor readback of this run, never participant-supplied IDs."""
    if (type(pid) is not int or pid <= 0 or type(author_pid) is not int or author_pid <= 0
        or pid == author_pid or type(exit_code) is not int or exit_code != 0
        or not isinstance(nonce, str) or not nonce.strip()
        or not isinstance(packet_id, str) or not re.fullmatch('[a-f0-9]{64}', packet_id)):
        raise ValueError('METHOD_PROCESS_NOT_QUALIFIED')
    rows = [e for e in events if e.get('type') == 'method_activation']
    if [(e.get('phase'), e.get('entrypoint')) for e in rows] != [('post_import', 'solver.method'), ('invoked', 'solver.solverPrompt')]:
        raise ValueError('METHOD_POST_IMPORT_INVOCATION_REQUIRED')
    for row in rows:
        if (row.get('pid') != pid or row.get('nonce') != nonce or row.get('packet_id') != packet_id
            or row.get('method_binding_id') != binding['binding_id'] or row.get('profile') != binding['profile']):
            raise ValueError('METHOD_ACTIVATION_BINDING_MISMATCH')
    prompt = rows[1].get('output')
    if not isinstance(prompt, str) or not prompt or rows[1].get('output_hash') != digest(prompt):
        raise ValueError('METHOD_ACTIVATION_OUTPUT_TAMPER')
    return {'method_binding_id': binding['binding_id'], 'profile': binding['profile'],
            'prompt_hash': rows[1]['output_hash'], 'post_import': True, 'invoked': True,
            'execution_authorized': False, 'scientific_success': False}
