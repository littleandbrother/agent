"""Capability-specific recovery and single-product scheduling, without verdicts.

No model invocation, native execution, database construction or design editing
belongs here. The original operator binding and acceptance authorities remain.
"""
import threading
import json
import os
from pathlib import Path


CAPABILITIES = {'eda', 'cadquery', 'spice', 'firmware-nrf52832',
                'firmware-nrf52832-s132', 'firmware-stm32l031',
                'firmware-stm32l432', 'host-tests', 'receiver'}


def eda_capability_failure(exc):
    """Keep public cause/dispatch facts in the current client's error text.

    That client consumes only `error`, so an additional `reason` field alone
    hides the actual failure. This grants no retry or identity acceptance.
    """
    reason = str(exc)[:500]
    return {'error': 'EDA_CAPABILITY_UNAVAILABLE: '+reason+'; native_write_dispatched=false',
            'error_code': 'EDA_CAPABILITY_UNAVAILABLE', 'reason': reason,
            'scope': 'This EDA action only; other product capabilities remain available.',
            'native_write_dispatched': False}


def startup_capabilities(phase, focused=None):
    """A bound optional tool is not a prerequisite for an unrelated phase."""
    policy = (focused or {}).get('capability_policy')
    if policy is None:
        return {'eda'} if phase == 'eda' else set()
    if (not isinstance(policy, dict) or
            policy.get('schema_version') != 'bf-phase-capability-policy-v1'):
        raise ValueError('PHASE_CAPABILITY_POLICY_INVALID')
    required = policy.get('required_at_start', [])
    if (not isinstance(required, list) or any(not isinstance(x, str) or
            x not in CAPABILITIES for x in required) or len(set(required)) != len(required)):
        raise ValueError('PHASE_CAPABILITY_REQUIRED_INVALID')
    return set(required) | ({'eda'} if phase == 'eda' else set())


def selected_paper(item, papers=None):
    """Filtering happens before a worker mutates a canonical queue record."""
    return papers is None or item.get('paper') in papers


def process_alive(pid):
    if type(pid) is not int or pid < 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def project_snapshot(workspace, relative):
    """The execution request's exact source identity, with no build or writes."""
    from ..engineering_projects import relative_file, KINDS
    from ..store import identity
    path = relative_file(Path(workspace), relative)
    spec = json.loads(path.read_text())
    if (set(spec) != {'schema_version', 'kind', 'entrypoint', 'files', 'interfaces'} or
            spec['schema_version'] != 'bf-engineering-project-v1' or spec['kind'] not in KINDS or
            not isinstance(spec['files'], list) or not 1 <= len(spec['files']) <= 32 or
            len(set(spec['files'])) != len(spec['files']) or spec['entrypoint'] not in spec['files']):
        raise ValueError('PROJECT_SCHEMA')
    sources = {name: relative_file(path.parent, name).read_text() for name in spec['files']}
    return {'kind': spec['kind'], 'interfaces': spec['interfaces'],
            'project_sha256': identity({'manifest': spec, 'sources': sources}),
            'source_files': list(spec['files']), 'path': relative}


def reusable_job(snapshot, request, status, assembly_hashes, artifacts_valid):
    """An exact execution can be reused; this never grants functional acceptance."""
    source_exact = request.get('project_sha256') == snapshot['project_sha256']
    dimensions = request.get('input_dimensions', {})
    inputs_exact = bool(dimensions) and all(assembly_hashes.get(k) == v for k, v in dimensions.items())
    return {'source_exact': source_exact, 'inputs_exact': inputs_exact,
            'artifacts_valid': artifacts_valid,
            'execution_reusable': status == 'SUCCEEDED' and source_exact and inputs_exact and artifacts_valid,
            'functional_passed': False, 'full_product_passed': False}


def needs_live_eda(body):
    from ..eda_cli import offline_command
    action = body.get('action', 'inspect')
    if action == 'inspect':
        return True
    if action != 'command':
        return False
    argv = body.get('argv')
    return isinstance(argv, list) and bool(argv) and not offline_command(argv)


class DeferredCapability:
    """Resolve once at actual use; a failed attempt does not end other work.

    Job receipt reads, help and skill loads never require a live application.
    The resolver retains its own exact-file/owner checks. No command retry or
    UNKNOWN operation replay is performed by this wrapper.
    """
    def __init__(self, resolve, initial=None):
        self.resolve = resolve
        self.value = initial
        self.lock = threading.Lock()

    def for_eda_request(self, body):
        if not needs_live_eda(body):
            return self.value
        with self.lock:
            if self.value is None:
                self.value = self.resolve()
            return self.value
