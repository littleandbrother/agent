"""Candidate dependency identities, applicability and exact artifact reuse.

This is apparatus code, not a participant's design script. An installed backend
is never promoted to a qualified physical model by this module.
"""
import json
import math
from pathlib import Path
from ..store import identity
from .contracts import sha, sealed

VERSION = 'bf-executable-candidate-builder-v1'
COMPONENTS = ('geometry', 'physical_bindings', 'circuit', 'firmware',
              'algorithm', 'hardware', 'scenario')
DEPENDENCIES = {
    'geometry_model': ('geometry',),
    'mechanical_model': ('geometry_model', 'physical_bindings', 'scenario'),
    'circuit_model': ('circuit', 'hardware', 'mechanical_model'),
    'target_build': ('firmware', 'algorithm', 'hardware'),
    'sensor_model': ('hardware', 'scenario', 'target_build', 'mechanical_model', 'circuit_model'),
    'joint_execution': ('mechanical_model', 'circuit_model', 'target_build', 'sensor_model'),
    'receiver': ('joint_execution', 'scenario'),
    'validation': ('receiver', 'joint_execution'),
    'delivery': ('validation', *COMPONENTS),
}


def candidate(components, environment_id, parent=None):
    if set(components) != set(COMPONENTS):
        raise ValueError('CANDIDATE_COMPONENT_SET_REQUIRED')
    # All source references are digests, not writable evaluator locations.
    for name, value in components.items():
        if not isinstance(value, dict) or not value:
            raise ValueError('CANDIDATE_COMPONENT_REQUIRED:' + name)
    value = {'schema_version': VERSION, 'environment_id': environment_id,
             'parent': parent, 'components': components,
             'component_ids': {name: identity(value) for name, value in components.items()}}
    return {**value, 'candidate_id': 'Dlab-' + identity(value)}


def plan(value, environment_versions, previous=None):
    expected = candidate(value['components'], value['environment_id'], value.get('parent'))
    if value != expected:
        raise ValueError('CANDIDATE_IDENTITY_DRIFT')
    keys = dict(value['component_ids'])
    stages = {}
    for stage, inputs in DEPENDENCIES.items():
        key = identity({'stage': stage, 'inputs': {n: keys[n] for n in inputs},
                        'backend': environment_versions.get(stage, 'UNQUALIFIED')})
        old = (previous or {}).get('stages', {}).get(stage, {})
        stages[stage] = {'input_id': key, 'inputs': list(inputs),
                         'action': 'REUSE_EXACT' if old.get('input_id') == key else 'REBUILD_REQUIRED',
                         'backend': environment_versions.get(stage, 'UNQUALIFIED')}
        keys[stage] = key
    value = {'schema_version': VERSION, 'candidate_id': value['candidate_id'],
             'environment_id': value['environment_id'], 'stages': stages}
    return {**value, 'plan_id': 'Build-' + identity(value)}


def verify_asset(root, descriptor, *, operating_point=None, action=None, require_qualified=False):
    """Reject missing/domain-incompatible assets before any backend dispatch."""
    required = {'id', 'version', 'files', 'interface', 'units', 'initial_state',
                'domain', 'calibration', 'qualification', 'supported_actions'}
    if not required.issubset(descriptor):
        raise ValueError('MODEL_DESCRIPTOR_INCOMPLETE')
    if (not isinstance(descriptor['files'],dict) or not descriptor['files'] or
        any(not isinstance(descriptor[k],dict) or not descriptor[k] for k in
            ('interface','units','initial_state','domain','calibration','qualification')) or
        not isinstance(descriptor['supported_actions'],list)):
        raise ValueError('MODEL_DESCRIPTOR_CONTENT_REQUIRED')
    if require_qualified and descriptor['qualification'].get('status')!='PASS':
        raise ValueError('MODEL_NOT_QUALIFIED')
    if action is not None and action not in descriptor['supported_actions']:
        raise ValueError('MODEL_ACTION_UNSUPPORTED')
    for name,value in (operating_point or {}).items():
        limit=descriptor['domain'].get(name)
        if not isinstance(limit,list) or len(limit)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in limit):
            raise ValueError('MODEL_DOMAIN_UNDECLARED:'+name)
        if type(value) not in (int,float) or not math.isfinite(value) or not limit[0]<=value<=limit[1]:
            raise ValueError('MODEL_OUT_OF_DOMAIN:'+name)
    root = Path(root).resolve()
    for name, digest in descriptor['files'].items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file() or sha(path) != digest:
            raise ValueError('MODEL_ASSET_DRIFT:' + name)
    return {'asset_id': descriptor['id'], 'version': descriptor['version'],
            'identity': identity(descriptor), 'qualification': descriptor['qualification'],
            'calibration': descriptor['calibration']}


def verified_cache(path, expected_input):
    """A cached success is reusable only if both inputs and actual files match."""
    path = Path(path)
    value = json.loads((path / 'receipt.json').read_text())
    if value.get('input_id') != expected_input or value.get('status') != 'PASS':
        raise ValueError('BUILD_CACHE_INPUT_OR_STATUS_MISMATCH')
    for name, digest in value.get('files', {}).items():
        file = path / name
        if not file.resolve().is_relative_to(path.resolve()) or not file.is_file() or sha(file) != digest:
            raise ValueError('BUILD_CACHE_ARTIFACT_DRIFT')
    if not value.get('files'):
        raise ValueError('BUILD_CACHE_EMPTY')
    return value


def publish_cache(path, input_id, files):
    path = Path(path)
    value = {'schema_version': VERSION, 'input_id': input_id, 'status': 'PASS',
             'files': {name: sha(path / name) for name in files}}
    sealed(path / 'receipt.json', value)
    return verified_cache(path, input_id)
