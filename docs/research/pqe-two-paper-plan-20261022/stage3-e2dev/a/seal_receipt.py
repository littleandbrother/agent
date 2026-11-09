"""Seal A's completed readback without reopening any scientific raw.

Uses only the thirteen compact raw ledgers, the prior two checkpoints, frozen
public materials, and original episode metadata. No scientific execution.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
PLAN = STAGE.parent
ROOT = PLAN.parents[2]
CAN = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def main():
    destination = HERE / 'A-RECEIPT.json'
    assert not destination.exists(), 'FINAL_RECEIPT_ALREADY_SEALED'
    free_before = shutil.disk_usage(ROOT).free
    assert free_before >= 10_001_000_000
    prospective = read(HERE / 'A-PROSPECTIVE.json')
    dossier_path = HERE / 'A-EPISODE-READBACK.json'
    dossier = read(dossier_path)
    original_dossier_sha256 = digest(dossier_path)
    materials_path = CAN / 'studies/pqe20261022/shared/e2dev-public-materials.json'
    assert digest(materials_path) == '511b70601a0ff8bd997557525dddf7c08b1e0d2177037da305f284b355975f9d'
    materials = read(materials_path)
    tasks = read(CAN / 'studies/pqe20261022/shared/door-tasks.json')
    # This repairs an A checker assumption, not scientific data or semantics.
    # Full Task hashes were already checked in every raw/cache binding. The
    # model deliberately receives the frozen public projection of that Task.
    for cell in dossier['cells']:
        transcript_path = STAGE / 's0/episodes' / cell['episode'] / 'method-transcript.json'
        assert digest(transcript_path) == cell['source_byte_hashes']['method-transcript.json']
        transcript = read(transcript_path)
        task = tasks[cell['task_id']]
        assert identity(task) == prospective['task_bindings'][cell['task_id']]['Task_sha256']
        assert transcript['initial_state']['task'] == materials[cell['task_id']]
        other_checks = {k: v for k, v in cell['checks'].items() if k != 'full_Task_frozen'}
        assert all(other_checks.values())
        cell['checks']['full_Task_frozen'] = True
        cell['checks']['model_public_Task_matches_frozen_materials'] = True
    dossier['checks']['all_cell_checks'] = all(all(c['checks'].values()) for c in dossier['cells'])
    assert all(dossier['checks'].values())
    dossier['status'] = 'INDEPENDENT_READBACK_COMPLETE'
    dossier['A_checker_correction'] = {
        'prior_dossier_byte_sha256': original_dossier_sha256,
        'original_status': 'AUDIT_MISMATCH_STOP',
        'original_failed_check': 'full_Task_frozen combined full Task hash with equality to model public Task',
        'cause': 'The model Task is the frozen pilot.public_task projection, with five host-only keys omitted and public_inputs filtered. It is intentionally not the complete host Task.',
        'resolution': 'Compare host full Task to its frozen canonical hash, and model Task to the already frozen e2dev-public-materials object. All twelve bindings pass. Existing raw/model/cache full-Task identities remain unchanged.',
        'scientific_data_or_semantics_changed': False, 'additional_raw_reads': 0,
        'additional_provider_or_numerical_executions': 0,
    }
    dossier_path.write_text(json.dumps(dossier, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    ledgers = {}
    for path in sorted((HERE / 'raw-readback').glob('*.json')):
        ledger = read(path)
        assert ledger['status'] == 'COMPLETE' and ledger['raw_reads'] == 1 and all(ledger['checks'].values())
        assert ledger['new_scientific_executions'] == 0
        ledgers[path.stem] = ledger
    assert len(ledgers) == 13
    by_cell = {c['episode']: c for c in dossier['cells']}
    d07_h = by_cell['d07-b3']['actions'][0]
    assert d07_h['compact_public_result_sha256'] == '5f3d4dd8e4271ae2d3481bc716545926bb8fd953b8275f520d56789260874219'
    assert d07_h['scientific_result_sha256'] == '5e4541cfb857bb9971eeba5ae59abdafffb091db2cf63362ae0aa52f0ecf99a2'
    assert d07_h['binding_checks']['compact_result_hash'] and d07_h['binding_checks']['compact_scientific_source_identity']
    assert by_cell['d07-b2']['actions'][0]['scope_effect_independent']['Design_changed_fields'] == ['esr_ohm']
    assert all(c['actual_P_scope_consumed'] for name, c in by_cell.items() if name.startswith('m3-'))
    assert all(not c['actual_P_scope_consumed'] for name, c in by_cell.items() if not name.startswith('m3-'))
    matrix = []
    for prefix in ('d15', 'd07', 'm3'):
        cells = [by_cell[f'{prefix}-b{i}'] for i in range(4)]
        matrix.append({'task_id': cells[0]['task_id'],
            'B0_strong_generic': cells[0]['last_applicable_scientific_result']['independent_service']['verdict'],
            'B1_fixed_sequence': cells[1]['last_applicable_scientific_result']['independent_service']['verdict'],
            'B2_ordinary_feedback': cells[2]['last_applicable_scientific_result']['independent_service']['verdict'],
            'B3_full_h': cells[3]['last_applicable_scientific_result']['independent_service']['verdict'],
            'actual_P_scope_consumed_all_four': all(c['actual_P_scope_consumed'] for c in cells)})
    observations = []
    for name, ledger in ledgers.items():
        r = ledger['review']
        observations.append({'case': name, 'scientific_result_sha256': ledger['scientific_result_sha256'],
            'verdict': r['independent_service']['verdict'], 'model_valid': ledger['model_valid'], 'domain_errors': ledger['domain_errors'],
            'unique_received': r['unique_received_count'], 'boot_count': r['boot_count'],
            'first_boot_s': r['first_boot_s'], 'first_capture_s': r['first_capture_s'],
            'activity_counts': r['activity_counts'], 'reset_mode_counts': r['state']['reset_mode_counts'],
            'reported_min_TX_terminal_v': r['supply']['reported_min_TX_v'],
            'retained_trace_terminal_v_range': r['stored_trace_terminal_v_range'],
            'trace_boundary': 'Retained trace is sampled; its extrema need not contain the full-step extrema.'})
    claims = [
        {'claim': 'D15 current volatile initial has distinct committed records reusing sequence numbers across resets, with receiver service loss.',
         'status': 'SUPPORTED_BY_PRIOR_EXACT_RAW_REVIEW', 'evidence': 'A-PROSPECTIVE and prior stage2-d15/a/A-RECEIPT; initial cache identity retained in INITIAL-CACHE-PROPOSAL.'},
        {'claim': 'All four D15 methods choose persistent_queue=true and achieve current finite service PASS.',
         'status': 'SUPPORTED', 'evidence': 'A-D15-FOUR-READBACK plus dossier all four full cache bindings.',
         'boundary': 'Four independent model decisions consume the same exact cached scientific result; not four numerical replicates. Only empty-queue IDLE resets are exercised after repair.'},
        {'claim': 'D07 current initial exhibits TX brownout and failed service.',
         'status': 'SUPPORTED', 'evidence': 'A-D07-INITIAL-READBACK: 755 boots/resets, 753 TX resets, zero complete frames/receives, four external events missed.'},
        {'claim': 'D07 repair necessarily requires a joint or multivariable edit.',
         'status': 'REFUTED_ON_THIS_FROZEN_TASK', 'evidence': 'd07-b2 changes only ESR from60 to0.1 ohm, valid complete PASS4/4, raw eed978c6a291b901586134cfad76a4baaed4cd4d7ef19ca1f46d9eaa961fc100.'},
        {'claim': 'All four D07 methods eventually reach valid complete finite service PASS.',
         'status': 'SUPPORTED', 'evidence': 'Six new raw ledgers retain B1 two invalid trials plus valid third; B0/B2/B3 each one valid PASS.',
         'boundary': 'B1 select/report are NO_EXECUTION UNKNOWN/NO_NEW_ASSESSMENT; its prior applicable action03 remains authoritative. Two earlier4-receive MODEL_DOMAIN trials remain UNKNOWN.'},
        {'claim': 'M3 scope reform is actually consumed in Design/model rather than merely described.',
         'status': 'SUPPORTED_ALL_FOUR_CONDITIONS',
         'evidence': 'Each first chosen action releases fixed mechanism{} and startup2.2, activates both, selects startup1.9 and stroke0.0085/base0.007. Pre-execution receipt, actual Design, connected model elements, model hash and raw hash all bind.',
         'boundary': 'The permission release was common to all four methods; it does not identify an H-exclusive ability or service gain.'},
        {'claim': 'Tested M3 designs achieve service after the scope reform.',
         'status': 'REFUTED_FOR_SEVEN_EXECUTED_DESIGNS',
         'evidence': 'All seven new M3 raw readbacks valid COMPLETE FAIL with zero receivers. Three80/82/100uF cases and the distinct80uF retry variant exhibit SAVE/TX failures;50uF has only partial SAVEs;800uF and1mF have zero boots.',
         'boundary': 'Finite attempted designs only. Current-P source exclusion and full-domain optimistic voltage bound remain the prior frozen qualifications.'},
        {'claim': 'M3 is globally service-infeasible over the complete legal Task domain.',
         'status': 'UNKNOWN_NOT_ESTABLISHED',
         'evidence': 'No new uniform proof or authorized qualification. B1 global argument adds an unsupported boot-by-first-truth requirement. Finite model FAILs do not close the domain.'},
        {'claim': 'B3/H has superior service success or exclusive P-consumption on this development set.',
         'status': 'NOT_ESTABLISHED', 'evidence': 'D15 and D07 tie at all-four PASS; M3 ties at all-four final FAIL and all-four actual P consumption.',
         'boundary': 'One finite development attempt per condition/task. No repeated-run comparison, held-out evaluation, method learning, population loss estimate, physical qualification or calibrated hardware acceptance.'},
        {'claim': 'Explanatory text and local hypothesis consistency certify a unique cause or learned H.',
         'status': 'NOT_ESTABLISHED', 'evidence': 'Pre-action predictions and retained deterministic updates are in dossier. CONSISTENT hypotheses carry unique_cause=false; model_UPDATE_calls=0 and methods remain frozen.'},
    ]
    textual_audits = [
        {'episode': 'm3-b1', 'assessment': 'CURRENT_MODEL_FAIL_SUPPORTED; GLOBAL_SCOPE_OVERCLAIM',
         'original_model_conclusion': by_cell['m3-b1']['model_self_assessment'],
         'unsupported_premise': 'The claim C<=~0.41mF requires boot before the first open truth time (~62.7s). The service contract instead matches an ordered received packet within2s after external truth. DoorProgram can boot later and debounce the then-current contact level; an earlier edge need not have been recorded while OFF.',
         'code_evidence': [
             {'path': str(CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022/door_program.py'),
              'sha256': prospective['current_five_scientific_sources']['door_program.py'],
              'locations': 'begin_step85-103; advance115-146; invalidate_contact_sample156-158',
              'fact': 'Boot from capacitor threshold; IDLE capture uses current stable contact versus retained last_direction, not a required powered truth-edge interrupt.'},
             {'path': str(CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022/executor.py'),
              'sha256': prospective['current_five_scientific_sources']['executor.py'],
              'locations': 'contact lookup123-125', 'fact': 'Current contact level obtained with bisect_right then passed to begin_step.'},
             {'path': str(CAN / 'packages/python/bfworld/src/bfworld/agentlab/pqe20261022/evaluator.py'),
              'sha256': prospective['current_five_scientific_sources']['evaluator.py'],
              'locations': 'event_truth and receive matching130-131',
              'fact': 'External truth is independent of power; packet time minus truth must lie in[0, receive_deadline_s=2] within numerical tolerance.'}],
         'decision': 'Preserve observed82uF FAIL and all original text. Reject the additional boot deadline as a necessary premise; the disjoint inequalities therefore do not establish global NO_GO. No claim that a feasible late-boot design exists; no new design, theorem, qualification or search.'},
        {'episode': 'm3-b0', 'assessment': 'CURRENT_MODEL_FAIL_SUPPORTED; CAPACITANCE_DIRECTION_TEXT_ERROR',
         'original_model_conclusion': by_cell['m3-b0']['model_self_assessment'],
         'actual_change': {'before_f': 0.0001, 'after_f': 0.00008, 'direction': 'DECREASE'},
         'model_wording': 'even after raising capacitance to80uF',
         'decision': 'Direction is wrong; the4boots,1SAVEreset,3TXresets and0wire/0receives support current FAIL independently. Preserve original text.'},
        {'episode': 'd07-b3', 'assessment': 'REFERENCE_RESOLVED_TWO_LEGITIMATE_OBJECT_IDENTITIES',
         'compact_public_Result_object_sha256': d07_h['compact_public_result_sha256'],
         'scientific_raw_result_sha256': d07_h['scientific_result_sha256'],
         'checks': {'compact_object_identity_recomputed': d07_h['binding_checks']['compact_result_hash'],
                    'embedded_result_and_source_result_bound': d07_h['binding_checks']['compact_scientific_source_identity']},
         'decision': 'The5f3d... scope reference identifies the actual compact public Result object; its embedded scientific result/hypothesis provenance points to5e454.... It is not a mismatched evidence reference.'},
        {'episode': 'm3-b2', 'assessment': 'FINITE_FAIL_SUPPORTED; NO_NEW_DOMAIN_PROOF',
         'decision': '80uF SAVE/TX brownouts and800uF zero boots are supported. The proposed~0.9mF charging inference is not promoted into new qualification or a global service proof; model scope expressly remains finite.'},
        {'episode': 'm3-b3', 'assessment': 'FINITE_FAIL_AND_LOCAL_SCOPE_SUPPORTED',
         'decision': '50uF four partial SAVEs,100uF one committed SAVE then TX brownouts with minimum1.6822798V, and1mF zero boots are supported. Sampled trace extrema remain sampled observations.'},
        {'episode': 'd07-b1', 'assessment': 'TRANSIENT_DOMAIN_ERRORS_AND_NO_EXECUTION_PRESERVED',
         'decision': 'Action01 assembly_envelope_exceeded and02 cam_pressure_angle_exceeded each return UNKNOWN despite four diagnostic receives. Action03 valid PASS. Action04 select and05 report create no new science; model final local PASS refers to03.'},
        {'episode': 'm3-b0', 'assessment': 'ONE_CONTRACT_CORRECTION_MODEL_RESUBMITTED',
         'evidence': by_cell['m3-b0']['contract_corrections'],
         'decision': 'Initial READ_ACTION_HAS_EDIT feedback has zero scientific executions and no automatic Design repair. The model resubmits a legal edit, which executes once. Its request and cost remain charged in the39-request total.'},
    ]
    verification = {
        'all_thirteen_raw_identity_model_and_independent_service_checks': all(all(x['checks'].values()) for x in ledgers.values()),
        'all_twelve_episode_bindings_scope_and_usage_checks': all(dossier['checks'].values()),
        'all39_requests_SETTLED_with_usage': len([r for c in dossier['cells'] for r in c['billing']]) == 39
            and all(r['status'] == 'SETTLED' and r['usage'] and not r['error'] for c in dossier['cells'] for r in c['billing']),
        'no_raw_reopened_during_sealing': True,
        'verification_boundary': 'Offline immutable-output audit only. No init.sh run or repository-wide health claim for this A-owned receipt. No model/evaluator rerun, provider call, native solver or hardware verification.',
    }
    receipt = {'schema': 'pqe-e2dev-a-final-independent-receipt-v1', 'package': prospective['package'],
        'feature': prospective['feature'], 'owner': 'campaign-a', 'at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'COMPLETE_A_OFFLINE_REVIEW; HANDOFF_TO_S0; IDLE',
        'frozen_criteria': {'path': str(HERE / 'A-PROSPECTIVE.json'), 'sha256': digest(HERE / 'A-PROSPECTIVE.json')},
        'matrix': matrix, 'totals': dossier['totals'], 'shared_initial_new_numerical_inputs': 1,
        'total_S0_new_scientific_inputs': 14,
        'cost_boundary': 'USD0.562077 is the current pinned-rate usage estimate, not invoice or provider billed amount. No new missing usage/reservations. Historical unrelated UNKNOWN accounting is untouched.',
        'reported_model_identity': dossier['cells'][0]['model_identity'],
        'identity_boundary': 'Same reported endpoint/profile across12cells; upstream weights remain unreported. No claim of a verified upstream weight revision.',
        'raw_observation_summary': observations, 'claim_ledger': claims, 'model_explanation_audits': textual_audits,
        'independent_readback_dossier': {'path': str(dossier_path), 'sha256': digest(dossier_path)},
        'initial_and_cache_readback': [
            {'path': str(HERE / 'A-D07-INITIAL-READBACK.json'), 'sha256': digest(HERE / 'A-D07-INITIAL-READBACK.json')},
            {'path': str(HERE / 'A-D15-FOUR-READBACK.json'), 'sha256': digest(HERE / 'A-D15-FOUR-READBACK.json')},
            {'path': str(HERE / 'INITIAL-CACHE-PROPOSAL.json'), 'sha256': digest(HERE / 'INITIAL-CACHE-PROPOSAL.json')}],
        'S0_original_results': {'path': str(STAGE / 's0/RESULTS.json'), 'sha256': dossier['S0_results_byte_sha256'],
            'batch_result_sha256': dossier['S0_batch_result_byte_sha256']},
        'verification': verification,
        'A_checker_correction': dossier['A_checker_correction'],
        'resources': {**dossier['resources'], 'seal_available_before_bytes': free_before,
            'seal_estimated_peak_additional_bytes': 1_000_000, 'seal_extra_raw_reads': 0,
            'available_after_bytes': shutil.disk_usage(ROOT).free,
            'A_raw_reads_total_this_package': 14, 'A_retained_full_raw_copies': 0,
            'storage_note': 'Only compact readbacks, metadata, scripts and one final receipt retained in A. Original raw remains canonical under S0. No new environment, backup, clone, worker, or copied wire/context payload.'},
        'handoff': {'to': 'S0', 'action': 'Use the final local service matrix and separate textual-scope findings for E2DEV closure. S0 alone owns root/shared state and manuscripts.',
            'A_state': 'IDLE', 'new_batch_authorized': False, 'new_qualification_or_theorem_authorized': False,
            'no_commit_or_push': True, 'pending_A_work': []},
    }
    inventory = []
    for path in sorted(HERE.rglob('*')):
        if path.is_file() and path != destination:
            inventory.append({'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path)})
    receipt['retained_output_inventory_excluding_self'] = inventory
    receipt['resources']['retained_bytes_excluding_receipt'] = sum(x['bytes'] for x in inventory)
    with destination.open('x') as f:
        f.write(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    total_bytes = sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())
    assert total_bytes < 1_000_000
    assert all(v for k, v in verification.items() if isinstance(v, bool))
    # Independent readback of the final compact artifact; never a scientific raw.
    sealed = read(destination)
    assert sealed['totals']['final_applicable_service'] == {'PASS': 8, 'FAIL': 4, 'UNKNOWN': 0}
    assert len(sealed['raw_observation_summary']) == 13 and len(sealed['matrix']) == 3
    for item in sealed['retained_output_inventory_excluding_self']:
        assert digest(Path(item['path'])) == item['sha256']
    print(json.dumps({'status': sealed['status'], 'receipt_path': str(destination), 'receipt_sha256': digest(destination),
        'A_total_retained_bytes': total_bytes, 'free_after_bytes': shutil.disk_usage(ROOT).free,
        'totals': sealed['totals'], 'all_verification_checks': True, 'extra_raw_reads_during_seal': 0}, indent=2))


if __name__ == '__main__':
    main()
