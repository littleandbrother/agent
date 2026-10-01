"""Strict, standard-library-only readback of the trusted transport trace."""
import hashlib
import json

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def validate_trace(events, packet, manifest, pid, nonce, exit_code):
    if exit_code != 0 or type(pid) is not int or pid <= 0:
        raise ValueError('PROCESS_DID_NOT_COMPLETE')
    controls = [e for e in events if e.get('type') == 'controlled_activation']
    sequence = [(e.get('phase'), e.get('entrypoint')) for e in controls]
    if sequence != [('post_import', 'solver'), ('post_import', 'improver'),
                    ('invoked', 'solver.initialState'), ('invoked', 'solver.solverPrompt')]:
        raise ValueError('EXACT_POST_IMPORT_AND_INVOCATION_SEQUENCE_REQUIRED')
    loaded = {key: manifest['loaded_modules'][key] for key in ('solver', 'improver')}
    for event in controls:
        if (event.get('nonce') != nonce or event.get('pid') != pid or event.get('loaded') != loaded
            or event.get('mode') != 'solve' or event.get('binding_hash') != digest(packet)
            or event.get('app_build_hash') != manifest['app_build_hash']
            or event.get('harness_source_hash') != manifest['source_hash']):
            raise ValueError('ACTIVATION_BINDING_MISMATCH')
        if event['phase'] == 'invoked':
            raw = json.dumps(event['output'], ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            if hashlib.sha256(raw).hexdigest() != event.get('output_hash'):
                raise ValueError('INVOCATION_OUTPUT_MISMATCH')
    complete = [e for e in events if e.get('type') == 'session_complete']
    if len(complete) != 1 or complete[0].get('messages') != 0 or complete[0].get('submitted') is not False:
        raise ValueError('EXACT_ZERO_MODEL_COMPLETION_REQUIRED')
    if any(e.get('type') in {'message', 'model_dispatched'} for e in events):
        raise ValueError('MODEL_ACTIVITY_NOT_ALLOWED')
    runtime = [e for e in events if e.get('type') == 'controlled_runtime_configuration']
    if len(runtime) != 1 or runtime[0].get('packet_id') != packet['packet_id'] or runtime[0].get('model') != packet['runtime_profile']['model'] or runtime[0].get('budget') != packet['runtime_profile']['budget'] or runtime[0].get('autonomous_participant') is not False:
        raise ValueError('EXACT_RUNTIME_PROFILE_REQUIRED')
    bound = [e for e in events if e.get('type') == 'controlled_task_bound']
    expected_binding = {k: packet[k] for k in ('world_id', 'world_input_id', 'task_contract_hash', 'task_registry_sha256', 'evaluator_sha256')}
    if len(bound) != 1 or bound[0].get('packet_id') != packet['packet_id'] or bound[0].get('task_id') != packet['task_id'] or bound[0].get('binding') != expected_binding or bound[0].get('source') != 'actual-registry-service-read':
        raise ValueError('EXACT_TASK_PACKET_BINDING_REQUIRED')
    probes = [e for e in events if e.get('type') == 'trusted_controller_probe']
    if len(probes) != 1 or probes[0].get('tool_name') != 'bf_experiment' or probes[0].get('arguments') != {'operation_id': 'trusted-controller-probe-1'} or probes[0].get('packet_id') != packet['packet_id'] or probes[0].get('autonomous_participant') is not False:
        raise ValueError('EXACT_REGISTERED_TOOL_PROBE_REQUIRED')
    result = json.loads(probes[0]['result']['content'][0]['text'])
    if result.get('status') != 'BLOCKED' or result['request']['task_id'] != packet['task_id'] or result.get('execution_packet_id') != packet['packet_id'] or result.get('binding') != {k: packet[k] for k in ('world_id', 'task_contract_hash', 'evaluator_sha256')}:
        raise ValueError('NATIVE_BLOCK_OR_TASK_BINDING_MISMATCH')
    if result.get('native_tool_identities') != {} or not result.get('native_prepare_error', '').startswith('TOOL_IDENTITY_MISSING_OR_INVALID:') or result.get('model_calls') != 0 or result.get('native_solver_calls') != 0 or result.get('scientific_success') is not False:
        raise ValueError('MISSING_NATIVE_TOOLS_OR_SCIENTIFIC_SCOPE_CHANGED')
    return result

