#!/usr/bin/env python3
"""Persist the provider-backed execution path using an ISOLATED TEST transport.

No credentials, original account or network. The fixture protocol is not real
owner authorization; the formal launcher rejects this purpose/transport pair.
"""
import json
import sys
from dataclasses import replace
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'packages/python/bfworld/src'))
sys.path.insert(0, str(REPO/'tests/campaign'))
from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json
from bfworld.coupled.engine import Design, Reference
from bfworld.coupled.profiled import LoadProfile
from bfworld.campaign.budget import Ledger
from bfworld.campaign.compiler import compile_candidate
from bfworld.campaign.scientific import execute_qualification
from bfworld.campaign.splits import task_record
from bfworld.campaign.task_context import physics_for, public_context, execute_candidate
from bfworld.campaign.trials import ARMS, TOOLS, history_from_runs
from bfworld.campaign.live_trials import VERSION, implementation, execution_pins, run_matrix
from bfworld.campaign.repair import checked
from test_b2_scientific import fixture
from test_b2_repair_bridge import fixture_protocol
from test_b2_live_trials import DecisionTransport


def main():
    source = {'implementation': implementation(), 'builder_hash': file_hash(Path(__file__)),
              'test_sources': {n: file_hash(REPO/'tests/campaign'/n) for n in
                               ('test_b2_scientific.py', 'test_b2_repair_bridge.py', 'test_b2_live_trials.py')}}
    root = REPO/'.bfworld/provider-trial-controls'/canonical_hash(source).split(':')[1]
    root.mkdir(parents=True, exist_ok=True)
    qt, qp, candidate = fixture()
    mechanical = compile_candidate(candidate, [public_context(qt[0])], root/'sandbox')
    qualification = execute_qualification(candidate, mechanical, qt, qp, root/'qualification', acquisition_cost_complete=True)
    history = history_from_runs([(qt[0], 'small', execute_candidate(qt[0], 'small'))])
    designs = {'small': replace(Design(), capacitance_f=.00033, esr_ohm=18), 'large': Design()}
    tasks = [task_record(name, 'development', physics_for(designs, replace(Reference(), source_phase_rad=phase), LoadProfile()), prior_exposure='public')
             for name, phase in [('use-control', .1), ('confirmation-control', .2)]]
    capsule = {'candidate': candidate, 'history_hash': history['content_hash'],
               'text_lesson': 'Small-capacitor failure is a public computational observation; no learned transfer is asserted.'}
    plan = {'schema_version': VERSION, 'purpose': 'provider-controls', 'arms': ARMS, 'tools': TOOLS,
            'max_turns': 5, 'max_experiments': 2, 'session_namespace': 'persistent-provider-control',
            'candidate_order_rule': 'stable-capacitance-ascending', 'task_id': tasks[0]['task_id'], 'confirmation_id': tasks[1]['task_id']}
    protocol_path = root/'FIXTURE-PROTOCOL-NOT-AUTHORIZATION.json'
    if protocol_path.exists():
        protocol = json.loads(protocol_path.read_text())
    else:
        protocol = fixture_protocol()
        protocol['task_manifest_hash'] = canonical_hash(tasks)
        protocol['matched_trial_execution'] = {**execution_pins(plan, tasks, history, capsule, qualification), 'model_fingerprint': 'fixture-fingerprint'}
        protocol['owner_approval'] = {'approval_id': 'TEST-FIXTURE-NOT-REAL-OWNER-AUTHORIZATION',
                                    'protocol_hash': canonical_hash({k: v for k, v in protocol.items() if k != 'owner_approval'})}
        write_canonical_json(protocol_path, protocol)
    # Deliberately a separate test-repository root, never the original account.
    ledger = Ledger(root/'.bfworld/paid-campaign/cost.sqlite')
    transport = DecisionTransport(ledger)
    try:
        report = run_matrix(plan, tasks, history, capsule, qualification, protocol, root, transport, root/'matrix')
        before = ledger.summary()
        replay = run_matrix(plan, tasks, history, capsule, qualification, protocol, root, transport, root/'matrix', reconcile_only=True)
        if replay != report or ledger.summary() != before:
            raise ValueError('fixture replay changed the ledger or result')
    finally:
        ledger.db.close()
    result = {'schema_version': 'inspectable-provider-control-v1', 'source': source,
              'artifact_root': str(root.relative_to(REPO)), 'report': report,
              'actual_provider_calls': 0, 'actual_paid_cny': 0, 'credentials_loaded': False,
              'replay_changed_ledger': False, 'claim_boundary': 'Isolated synthetic transport and hand-authored fixtures; not G3/G4, Agent benefit, blind transfer, or an owner-approved real campaign.'}
    result['content_hash'] = canonical_hash(result)
    write_canonical_json(REPO/'docs/b2-development/provider-trial-control.json', result)
    print(json.dumps({'status': 'pass', 'artifact_root': str(root), 'report_hash': report['content_hash'],
                      'mock_settled_calls': report['cost']['provider_calls'], 'actual_provider_calls': 0, 'replay_changed_ledger': False}))


if __name__ == '__main__': main()
