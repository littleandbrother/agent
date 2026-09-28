"""Scope-selection pilot adapter over the unchanged programmable reference.

The three editable JSON artifacts parameterize circuit, classifier and schedule.
They are not real mechanical geometry, a trained network, or a manufactured
product. This pilot checks scope interventions before the physical A study.
"""
from dataclasses import asdict
import json
from pathlib import Path

from .. import programmed
from ..experiments import BASELINE_DESIGN
from ..store import identity
from bfworld.coupled.engine import Design, Reference

SCOPES = {'circuit': ['capacitance_f', 'clamp_v', 'esr_ohm', 'start_v', 'tx_power_w'],
          'classifier': ['model_threshold', 'flash_bytes', 'sram_bytes'],
          'schedule': ['release_s']}


def cases():
    return {
        'local-voltage': dict(BASELINE_DESIGN),
        'voltage-quality': {**BASELINE_DESIGN, 'model_threshold': 10000},
        'quality-timing': {**BASELINE_DESIGN, 'clamp_v': 3.45, 'model_threshold': 10000, 'release_s': .98},
        'voltage-timing': {**BASELINE_DESIGN, 'release_s': .98},
    }


def artifacts(design):
    return {name+'.json': {k: design[k] for k in keys} for name, keys in SCOPES.items()}


def read_design(workspace):
    value = {}
    for name, fields in SCOPES.items():
        data = json.loads((Path(workspace)/(name+'.json')).read_text())
        if set(data) != set(fields):
            raise ValueError('SCOPE_ARTIFACT_SCHEMA')
        value.update(data)
    return value


def policy(obs):
    if obs['time_s'] < obs['requirements']['release_s']:
        return {'action': 'wait', 'duration_s': .02}
    for action in ['sense', 'infer', 'report']:
        if action not in obs['completed_actions']:
            return {'action': action}
    return {'action': 'wait', 'duration_s': .1}


def evaluate(design):
    if set(design) != set(BASELINE_DESIGN) or design['flash_bytes'] != 8192 or design['sram_bytes'] != 2048:
        raise ValueError('SCOPE_IMMUTABLE_RESOURCE_CONTRACT')
    if not .018 <= design['tx_power_w'] <= .06 or not .1 <= design['esr_ohm'] <= 20:
        raise ValueError('SCOPE_COMPONENT_DOMAIN')
    result = programmed.execute(Design(**design), Reference(), programmed.LoadProfile(), policy)
    programmed.verify(result, reproduce=True)
    return {'checks': result['physical_mission_pass'], 'summary': result['summary'],
            'request': {k: result['request'][k] for k in ['prediction', 'receive_s', 'deadline_s']},
            'content_hash': result['content_hash'], 'energy_ledger': result['energy_ledger'],
            'fidelity': result['fidelity'], 'model': result['model_artifact'],
            'independent_replay': True, 'hardware_verified': False}


def scope_for(arm, feedback):
    if arm == 'fixed-local':
        return ['circuit']
    if arm in {'fixed-global', 'free-scope'}:
        return list(SCOPES)
    if arm != 'adaptive-closure':
        raise ValueError('SCOPE_ARM')
    checks = feedback['checks']
    scope = []
    if not checks['electrical_safe'] or not checks['deployment_feasible']:
        scope.append('circuit')
    if not checks['quality_valid']:
        scope.append('classifier')
    if not checks['deadline_met'] or not checks['delivered']:
        scope.append('schedule')
    return scope or ['circuit']


def apply_patch(workspace, patch, allowed):
    if not isinstance(patch, dict) or not patch or set(patch)-set(allowed):
        raise ValueError('SCOPE_PATCH_OUTSIDE_EDITABLE_ARTIFACTS')
    old = read_design(workspace)
    new = dict(old)
    for domain, changes in patch.items():
        if not isinstance(changes, dict) or set(changes)-set(SCOPES[domain]):
            raise ValueError('SCOPE_PATCH_FIELDS')
        new.update(changes)
    # Validate before writing; malformed model output cannot execute code.
    if new['flash_bytes'] != 8192 or new['sram_bytes'] != 2048:
        raise ValueError('SCOPE_IMMUTABLE_RESOURCE_CONTRACT')
    if not .018 <= new['tx_power_w'] <= .06 or not .1 <= new['esr_ohm'] <= 20:
        raise ValueError('SCOPE_COMPONENT_DOMAIN')
    programmed.validate_inputs(Design(**new), Reference(), programmed.LoadProfile())
    for name, values in artifacts(new).items():
        (Path(workspace)/name).write_text(json.dumps(values, sort_keys=True))
    return {'before': identity(old), 'after': identity(new),
            'actual_edit_scope': [name for name in SCOPES if any(old[k] != new[k] for k in SCOPES[name])],
            'changed_fields': [k for k in old if old[k] != new[k]]}


def prompt(design, feedback, allowed, history):
    return [
        {'role': 'system', 'content': 'You repair declared computational BF-AIoT artifacts. Return ONLY a JSON object mapping editable artifact IDs to changed field values. The only possible top-level IDs are circuit, classifier, schedule (no .json suffix; no design/patch wrapper). Use only IDs listed in editable_artifacts. No prose, no tools, no code. Do not edit requirements, resource accounting, model or evaluator. This is synthetic computational development, not hardware.'},
        {'role': 'user', 'content': json.dumps({
            'design': {name: {k: design[k] for k in fields} for name, fields in SCOPES.items()}, 'feedback': feedback, 'editable_artifacts': allowed,
            'requirements': {'deadline_s': 1.1, 'max_voltage_v': 3.6, 'capacitance_max_f': .0047,
                             'quality_min': .7, 'receiver_delivery': True},
            'public_contract': {'classifier': 'int8 first-difference classifier; model_threshold is an integer scale (reference value 25), not a probability; fixed 8192 Flash and 2048 SRAM',
                                'circuit': 'capacitance_f in [0.0001,0.0047]; optional ideal clamp_v in (1.8,3.6]; esr_ohm [0.1,20]; start_v (1.8,3.6]; tx_power_w [0.018,0.06]',
                                'schedule': 'release_s >= 0; sense 0.08s, infer 0.035s, TX 0.04s plus receiver delay 0.008s'},
            'history': history}, ensure_ascii=False)}]


def selection_prompt(design, feedback):
    return [{'role': 'system', 'content': 'Select the editable artifact scope BEFORE a separate shared generator repairs the design. Return ONLY a nonempty JSON array of artifact IDs: circuit, classifier and/or schedule. IDs never contain .json. You have the same public feedback as the heuristic selector. No private evaluator access.'},
            {'role': 'user', 'content': json.dumps({'artifacts': {name: {k: design[k] for k in fields} for name, fields in SCOPES.items()}, 'feedback': feedback,
                'scope_contract': SCOPES, 'cost': 'This scope decision consumes one of the same three model calls allowed per trial.'})}]
