"""Independent operator admission of predeclared D4 tasks.

Illustrations, inherited code and participant prose never create an Agent pass.
The pre-render snapshot is immutable input to the figures. A separate final
receipt may admit the figure check afterwards, avoiding a self-hashing cycle.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

import numpy as np

from bfworld.agentlab.paper_reproduction import evaluate, seal
from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json
from bfworld.agentlab.simulation_chain.solver import execute_program


def audit(root, final=False):
    root = Path(root).resolve()
    paper = root / 'paper'
    target = paper / ('final-progress.json' if final else 'progress.json')
    if target.exists():
        raise ValueError('PAPER_PROGRESS_IMMUTABLE:' + str(target))
    plan = json.loads((paper / 'task-plan.json').read_text())
    plan_hash = seal(plan)
    ref = root / 'sealed-reference-v2'
    read = lambda p: json.loads(Path(p).read_text())
    result = read(ref / 'result.json')
    design = read(ref / 'design-spec.json')
    manifest = read(ref / 'system-manifest.json')
    did = design['design_id']
    cad = read(ref / 'cad/d4-cad-receipt.json')
    parts = read(ref / 'cad/cad-readback.json')
    force = read(ref / 'force/force-domain.json')
    build = read(ref / 'build-receipt.json')
    pilot = read(root / 'pilot/trajectory-summary.json')
    if final:
        base = read(paper / 'progress.json')
        figure = read(root / 'presentation/verification.json')
        if figure.get('status') != 'passed' or not figure.get('redraw_identical'):
            raise ValueError('FIGURES_NOT_INDEPENDENTLY_VERIFIED')
        records = base['records']
        trusted = base['trusted_receipts']
    else:
        records, trusted = [], {}
    folder = paper / ('final-validator-receipts' if final else 'validator-receipts')
    folder.mkdir()

    def record(tid, status, paths, reason, check=True, actor='operator', trace=None):
        evidence = [{'path': str(Path(p).resolve()), 'sha256': file_hash(p)} for p in paths]
        if status == 'passed' and not check:
            raise ValueError('INDEPENDENT_CRITERION_FAILED:' + tid)
        row = {'task_id': tid, 'status': status, 'actor': actor, 'evidence': evidence, 'reason': reason}
        receipt = {'plan_sha256': plan_hash, 'task_id': tid, 'status': status, 'actor': actor,
                   'evidence': evidence, 'validator_id': 'door-system-operator-admission-v1',
                   'criterion_met': bool(check), 'reason': reason}
        if trace:
            row['agent_trace_sha256'] = file_hash(trace)
            row['human_candidate_edits'] = 0
            receipt['agent_trace'] = {'path': str(Path(trace).resolve()), 'sha256': file_hash(trace)}
            receipt['human_candidate_edits'] = 0
            receipt['retrieval_condition'] = 'operator provided primary URL locators before trial; no numerical or candidate hints'
        path = folder / (tid + '.json')
        write_json(path, receipt)
        row['executor_receipt_sha256'] = file_hash(path)
        trusted[file_hash(path)] = str(path)
        records[:] = [r for r in records if r['task_id'] != tid]
        records.append(row)

    if not final:
        # These identities are emitted and checked by the native executor; the
        # reviewer independently verifies their hashes rather than trusting text.
        stable = result['source_stable'] and result['run_status'] == 'completed'
        identity = stable and all(v['design_id'] == did for v in (result, manifest, cad, force, build))
        bound = all(file_hash(ref / name) == next(a['sha256'] for a in result['artifacts'] if a['name'] == name)
                    for name in ('assembly.step', 'installation.step', 'program.c', 'rom.json', 'waveform.csv', 'system-manifest.json'))
        record('design-contract', 'passed', [ref / 'design-spec.json', ref / 'system-manifest.json', ref / 'result.json'],
               'Sealed no-Agent reference native identities and listed output hashes match; not Agent authorship.', identity and bound)
        record('cad-native', 'passed', [ref / 'cad/cad-readback.json', ref / 'cad/d4-cad-receipt.json', ref / 'assembly.step'],
               '22 OCCT solids independently read; static dimensional validity only.',
               len(parts['parts']) == 22 and all(p['native_valid'] and p['solid_count'] == 1 for p in parts['parts']) and not cad['collisions'])
        job = root / 'pilot/nominal-r1/jobs/eng-fba4bfdd7fe6ce3f'
        jd, jc, jm = [read(job / p) for p in ('design-spec.json', 'd4-cad-receipt.json', 'system-manifest.json')]
        jf = next(s['receipt'] for s in jm['stages'] if s['stage'] == 'force')
        pose = jc['driver_closed_world_mm']
        record('drive-configuration', 'passed', [ref / 'cad/d4-cad-receipt.json', job / 'design-spec.json', job / 'd4-cad-receipt.json', job / 'system-manifest.json'],
               'Actual offset bracket was built and entered force stage; operator validates Pi-produced artifact, no architecture-synthesis claim.',
               jm['design_id'] == jc['design_id'] == jf['design_id'] == jd['design_id'] and
               np.allclose(pose, [904-jd['mechanical']['gap_mm'], 75.265+jd['mechanical']['closed_dz_mm'], 2140]) and pose != cad['driver_closed_world_mm'])
        record('beam-rom', 'passed', [ref / 'rom.json', ref / 'system-manifest.json'],
               'Existing beam ROM hash is pinned in native manifest. Reused, not freshly calibrated.',
               file_hash(ref / 'rom.json') == manifest['source_rom_sha256'])
        rec = read(root / 'verification/reciprocity.json')
        record('reciprocity', 'passed', [root / 'verification/reciprocity.json', ref / 'energy.json'],
               'Central difference of the same magnetic potential and coupled energy ledger; not physical validation.',
               rec['passed'] and result['checks']['energy_balance'])
        record('force-interpolation', 'passed', [ref / 'force/force-domain.json'],
               'Angle/domain and high-gradient holdouts meet declared interpolation threshold.',
               force['angle_deg'] == [0., 65.] and force['tip_m'] == [-.008, .008] and force['max_interpolation_error_over_peak'] <= .02)
        fem = read(root / 'verification/corrected-fem-anchors.json')
        record('rotated-fem', 'passed', [root / 'verification/corrected-fem-anchors.json', root / 'trajectory-fem-v1/trajectory-anchors.json'],
               'All seven preselected finite anchors pass after a separately declared air-domain correction; full domain remains unqualified.',
               fem['design_id'] == did and len(fem['anchors']) == 7 and all(a['passed'] for a in fem['anchors']) and not fem['full_rotating_domain_coverage'])
        ledger = read(ref / 'drive-ledger.json')
        record('full-cycle-ledger', 'passed', [ref / 'drive-ledger.json', ref / 'drive-ledger.csv', ref / 'design-spec.json'],
               'Far equilibrium and full close/hold/open/settle ledger, zero initial electric energy, residual <=1%.',
               ledger['design_id'] == did and ledger['initial_electric_J'] == 0 and ledger['total_relative_residual'] <= .01 and
               [p['phase'] for p in ledger['phases']] == ['close', 'hold', 'open', 'settle'])
        log = (ref / 'system.log').read_text()
        measures = {k: float(re.search(k+r': MAX\([^\n]+?\)=([\deE+.-]+)', log).group(1)) for k in ('storage_peak', 'output_peak')}
        check = np.isclose(measures['storage_peak'], result['metrics']['peak_storage_V'], rtol=1e-8) and np.isclose(measures['output_peak'], result['metrics']['peak_supply_V'], rtol=1e-8)
        record('pmic-native', 'passed', [ref / 'system.cir', ref / 'system.log', ref / 'result.json'],
               'Native encrypted ADI model; RAW-derived peaks agree with .meas. Internal PMIC energy loss not independently certified.', check)
        # Execute the already-built identical C library with diagnostic rails;
        # these are controls, never energy supplied to the product candidate.
        t = np.linspace(0, .15, 1501)
        z = np.zeros(len(t)); v = np.full(len(t), 3.3)
        current, states0, events0 = execute_program(ref / 'firmware', t, z, z)
        _, states, events = execute_program(ref / 'firmware', t, v, v)
        first = np.flatnonzero(states == 4)[0]
        v[first+2:] = 0
        _, states_b, events_b = execute_program(ref / 'firmware', t, v, v)
        controls = {'program_sha256': file_hash(ref / 'firmware/program.c'), 'no_supply_tx': len(events0),
                    'no_supply_load_positive': bool((current > 0).all()), 'diagnostic_3v3_tx': len(events),
                    'interrupted_tx': len(events_b), 'brownout_final_state': int(states_b[-1]),
                    'passed': not events0 and len(events) > 0 and not events_b and states_b[-1] == 0 and (current > 0).all(),
                    'scope': 'Synthetic diagnostic rails through sealed shared C; not a native self-powered positive or cycle-accurate SoC simulation.'}
        controls['passed'] = bool(controls['passed'])
        write_json(root / 'verification/sil-controls.json', controls)
        record('sil-coupling', 'passed', [ref / 'coupling-iterations.json', ref / 'build-receipt.json', root / 'verification/sil-controls.json'],
               'Candidate fixed point converges; independent controls preserve no-supply and incomplete-TX behavior.',
               controls['passed'] and result['checks']['program_power_fixed_point'])
        step = read(ref / 'time-step-check.json')
        record('time-step', 'passed', [ref / 'time-step-check.json'], 'Independent half-step candidate agrees within1% and equal TX/RX.', step['passed'])
        record('cold-repeat', 'passed', [root / 'verification/cold-repeat.json'], 'Two same-executor independent native launches, not a cache read.', read(root / 'verification/cold-repeat.json')['passed'])
        record('self-powered-start', 'failed', [ref / 'result.json', root / 'pilot/trajectory-summary.json'], 'Every admissible new native candidate still has zero cold start/TX/RX.', False)
        record('packet-service', 'failed', [ref / 'receiver.json', root / 'pilot/trajectory-summary.json'], 'Zero completed TX and zero correct timely received packets; no fabricated event.', False)
        record('source-parameters', 'unknown', [root / 'pilot/trajectory-summary.json'], 'Primary papers fetched only in source-assisted trial; input/output capacitor nodes and 3.3V UVLO were not adequately bound in Pi reasoning.', False, 'agent')
        record('electronics-binding', 'unknown', [ref / 'design-spec.json'], 'D3.3 historical board is not rematerialized and native-EDA checked as this D4 candidate.', False)
        record('flash-core', 'generated', [ref / 'build-receipt.json'], 'Same-source host library and Cortex-M4 object exist; no complete D4 flashable target.', False)
        record('restart-semantics', 'unknown', [ref / 'receiver.json'], 'Incomplete TX control exists, but cross-restart event identity/exactly-once behavior is not established.', False)
        record('figure-provenance', 'executed', [root / 'presentation/mechanics/render-receipt.json'], 'Pre-render progress snapshot: CAD renders exist; six-group redraw not yet admitted.', False)
        trial = next(t for t in pilot['trials'] if t['trial'] == 'domain-r1')
        selected = next(j for j in trial['jobs'] if j['job_id'] == trial['submitted_job'])
        trace = Path(trial['trace_path'])
        record('agent-delivery', 'passed', [root / 'pilot/domain-r1/submission.json', root / 'pilot/trajectory-summary.json'],
               'Real Pi fetched primary texts, executed three candidates, and submitted a hash-bound result with no human candidate edits. Source-locator assisted; selection quality and product success are not implied.',
               trial['human_candidate_edits'] == 0 and trial['usage_unknown_count'] == 0 and selected['status'] == 'completed' and
               trial['submission']['result_sha256'] == selected['result_sha256'] and any(s['extraction'] == 'pdf-text' and s['read_requests'] for s in trial['acquired_sources']),
               'agent', trace)
        for tid in ('hardware-energy', 'hardware-flash', 'hardware-rf', 'lifetime'):
            record(tid, 'not_started', [], 'Excluded from simulation denominator; no connected physical apparatus.', False)
    else:
        record('figure-provenance', 'passed', [root / 'presentation/verification.json', root / 'presentation/report/figure-index.json', root / 'presentation/report/figure-quality.json'],
               'Seventy predeclared panels and explicit gaps, hashes/units and independent redraw checked. Fig6h intentionally preserves earlier pre-render progress snapshot.', True)

    progress = evaluate(plan, plan_hash, records, trusted)
    progress.update(records=records, trusted_receipts=trusted,
                    stage='post-figure independent admission' if final else 'immutable pre-figure admission',
                    source_locator_assisted_trial=True,
                    template_artifacts_counted_as_agent_authorship=False,
                    interpretation='Only agent-delivery is admitted as Agent-owned. Operator model/CAD/solver checks are not Agent reproduction credit; no 80% or self-powered success.')
    write_json(target, progress)
    return {k: progress[k] for k in ('predeclared_denominator', 'agent_independent_passed', 'all_actors_independent_passed', 'target_80_percent_reached')}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--final', action='store_true')
    args = p.parse_args()
    print(json.dumps(audit(args.root, args.final)))
