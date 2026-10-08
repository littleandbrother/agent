"""Factual review of completed Pi submissions and independently read sources.

Never changes submitted candidates, task scores, provider usage or raw traces.
The review separates a lower intermediate voltage from the task objective.
"""
import argparse
import json
import shutil
from pathlib import Path
from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json


def review(root):
    root = Path(root).resolve(); paper = root / 'paper'
    pilot = json.loads((root / 'pilot/trajectory-summary.json').read_text())
    facts = []
    for t in pilot['trials']:
        selected = next(j for j in t['jobs'] if j['job_id'] == t['submitted_job'])
        completed = [j for j in t['jobs'] if j['status'] == 'completed']
        better_intermediates = [j['job_id'] for j in completed if j['job_id'] != selected['job_id'] and
                               j['metrics']['peak_storage_V'] > selected['metrics']['peak_storage_V'] and
                               j['metrics']['drive_ledger']['pmic_port_J'] > selected['metrics']['drive_ledger']['pmic_port_J']]
        facts.append({'trial': t['trial'], 'selected_job': selected['job_id'], 'completed_candidates': len(completed),
                      'out_of_domain_candidates': sum(j['status'] == 'out_of_domain' for j in t['jobs']),
                      'selected_nominal_status': selected['evaluation']['nominal_task_status'],
                      'earlier_candidates_with_higher_vin_and_port_energy': better_intermediates,
                      'selection_objective_not_established': True,
                      'rationale_only_completed_claim_contradicted': t['trial'] == 'domain-r1' and len(completed) > 1,
                      'scope': 'No ranking based solely on voltage: all admissible candidates failed the frozen event task; no physical design ranking is admitted.'})
    source = root.parents[0] / 'door-magnetic-v1/sources'
    out = paper / 'operator-sources'; out.mkdir(exist_ok=True)
    for name in ('LTC3588-1.pdf', 'LTC3588-1.txt'):
        shutil.copy2(source / name, out / name)
    text = (out / 'LTC3588-1.txt').read_text()
    if not all(v in text for v in ('3.3V Output Selected', '4.73', '5.05', '5.37', '4.04')):
        raise ValueError('DATASHEET_CONTENT_NOT_CONFIRMED')
    assisted = next(t for t in pilot['trials'] if t['trial'] == 'domain-r1')
    texts = {s['url']: (root / 'pilot/domain-r1/reference-blobs' / s['text_sha256']).read_text() for s in assisted['acquired_sources']}
    j40 = next(v for k, v in texts.items() if 'J40.pdf' in k)
    j101 = next(v for k, v in texts.items() if 'J101_' in k)
    j128 = next(v for k, v in texts.items() if 'J128_' in k)
    if '10-μF storage capacitor' not in j40 or '330 µF' not in j101 or '47 μF' not in j128:
        raise ValueError('PRIMARY_CAPACITANCE_FACT_NOT_CONFIRMED')
    source_review = {'authority': 'operator independent source review after trials; not information retroactively delivered to Pi',
                    'primary_sources': assisted['acquired_sources'],
                    'facts': [
                        {'source': 'ViPSN-Pluck', 'locator': 'PDF page7 / V.System Implementation A.Hardware; Fig6 operation',
                         'value': 10, 'unit': 'uF', 'node': 'paper storage capacitor monitored by MIC841; cannot infer this D4 VIN capacitor without schematic binding',
                         'accepted_scope': 'Paper indeed states10uF; larger capacitors are not universally required.'},
                        {'source': 'Unified framework', 'locator': 'Fig3(c), capacitor charging comparison; Table2 and system application',
                         'value': [22, 33, 47, 100, 220, 330], 'unit': 'uF',
                         'node': 'SP-SECE versus SEH storage/impedance study; architecture differs from direct D4 LTC3588 interface'},
                        {'source': 'Cross-domain', 'locator': 'SP-SECE component table / storage Cstore; charging-capacitance comparison',
                         'value': 47, 'unit': 'uF', 'node': 'Cstore after harvesting interface; cannot equate numerical value alone to a D4 node'},
                        {'source': 'LTC3588-1 official datasheet', 'url': 'https://www.analog.com/media/en/technical-documentation/data-sheets/35881fc.pdf',
                         'locator': 'PDF page3 Electrical Characteristics, VIN Rising, D1=1/D0=0 / 3.3V output',
                         'min': 4.73, 'typ': 5.05, 'max': 5.37, 'unit': 'V',
                         'lower_output_typical': 4.04, 'lower_output_minimum': 3.77,
                         'node': 'VIN startup threshold; not output supply threshold', 'pi_acquired': False,
                         'operator_pdf_sha256': file_hash(out / 'LTC3588-1.pdf'), 'operator_text_sha256': file_hash(out / 'LTC3588-1.txt')}
                    ],
                    'rejected_inferences': ['About4V cannot be treated as the3.3V output-setting startup threshold.',
                                            'A4700uF VIN candidate does not receive more mechanical energy by changing C.',
                                            'Source title/fetch and requested text chunks do not prove full-text interpretation.',
                                            'Two native completed candidates contradict the second submission rationale that only its selected candidate completed.'],
                    'next_seam': 'A node- and implementation-bound extraction/loading mechanism such as the literature SP-SECE interface must be evaluated as a new apparatus/version, not injected into this frozen pilot.'}
    write_json(paper / 'source-assumption-review.json', source_review)
    write_json(root / 'pilot/selection-review.json', {'protocol_sha256': pilot['protocol_sha256'],
              'trajectory_summary_sha256': file_hash(root / 'pilot/trajectory-summary.json'), 'trials': facts,
              'score_or_submission_changed': False, 'source_review': str(paper / 'source-assumption-review.json')})
    return {'trials': len(facts), 'source_facts': len(source_review['facts']), 'unsupported_selection_claims': sum(f['rationale_only_completed_claim_contradicted'] for f in facts)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True); a = p.parse_args()
    print(json.dumps(review(a.root)))
