#!/usr/bin/env python3
"""Verify this portable delivery and rebuild figures/statistics from saved data.

Python >=3.11 standard library is sufficient for the common engineering/cost
checks. Paper-specific commands and optional plotting dependencies are declared
in reproduction-commands.json. No model, solver, device or network is invoked.
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def load(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify_manifest(root):
    if (root / 'SEAL.json').exists():
        seal = load(root / 'SEAL.json')
        assert sha(root / 'MANIFEST.json') == seal['manifest_sha256'], 'MANIFEST_SEAL_MISMATCH'
        assert sha(root / 'ACCEPTANCE.json') == seal['acceptance_sha256'], 'ACCEPTANCE_SEAL_MISMATCH'
    manifest = load(root / 'MANIFEST.json')
    for name, entry in manifest['files'].items():
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink():
            raise ValueError('UNSAFE_MANIFEST_PATH:' + name)
        if path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
            raise ValueError('FILE_DIGEST_MISMATCH:' + name)
    return len(manifest['files'])


def engineering(root, output):
    node = root / 'engineering/piezo-node'
    original = load(node / 'original-manifest.json')
    identity = original['system_id']
    for name in ['input.json', 'summary.json', 'target-mapping.json', 'timeline.json', 'native/receipt.json']:
        assert load(node / name)['system_id'] == identity, ('CANDIDATE_MISMATCH', name)
    omitted = {item['path'] for item in load(node / 'omitted-rebuildable.json')}
    for name, entry in original['outputs'].items():
        if name in omitted:
            assert name.startswith('target/objects/') and name.endswith('.o')
            continue
        assert sha(node / name) == entry['sha256'], ('FROZEN_ENGINEERING_ASSET_CHANGED', name)
    cad = load(node / 'assembly-readback.json')
    assert cad['native_valid'] and cad['solid_count'] == 32 and not cad['interferences']
    assert cad['beam_free_length_mm'] == 90 and cad['beam_width_mm'] == 30
    receipt = load(node / 'native/receipt.json')
    assert receipt['native_drc_passed'] and receipt['pin_net_match']
    schematic = load(node / 'native/schematic-readback.json')['result']
    svg = (node / 'native/schematic.svg').read_text()
    assert schematic['wiresAvailable'] and len(schematic['wires']) == 114
    wire_ids = {w['primitiveId'] for w in schematic['wires']}
    assert all(wire_id in svg for wire_id in wire_ids), 'SCHEMATIC_WIRE_PREVIEW_MISMATCH'
    assert len(wire_ids) == schematic['connectivitySummary']['wires'] == 21
    target = load(node / 'target-status.json')
    assert target['status'] == 'BUILT' and target['memory_fit']
    for name in ['firmware.hex', 'combined.hex']:
        for line in (node / 'target' / name).read_text().splitlines():
            record = bytes.fromhex(line.removeprefix(':'))
            assert line.startswith(':') and sum(record) % 256 == 0 and len(record) == record[0] + 5
    assert not target['flashed'] and not target['boot_tested'] and not target['radio_verified']
    timeline = load(node / 'timeline.json')
    assert timeline['execution_id'] == original['execution_id'] and timeline['converged']
    for name, entry in timeline['sources'].items():
        assert sha(node / 'reference' / name) == entry['sha256'], ('TIMELINE_SOURCE_MISMATCH', name)
    tx = [e for e in timeline['events'] if e['state'] == 'tx' and e['completed']]
    assert len(tx) == len({e['seq'] for e in tx}) == 15
    assert all(e['crc'] == ((e['seq'] ^ e['value'] ^ 0xA5) & 255) for e in tx), 'DIGITAL_CRC_MISMATCH'
    first_power = next(e['t_s'] for e in timeline['transitions'] if e['powered'])
    assert abs(first_power - 6.7505) < 1e-9
    raw_first_power, completed, previous = None, [], None
    with (node / 'reference/program.csv').open() as stream:
        for row in csv.DictReader(stream):
            row = {key: float(value) for key, value in row.items()}
            if row['powered'] and raw_first_power is None:
                raw_first_power = row['t_s']
            if previous and previous['state'] == 3 and row['state'] != 3:
                assert row['powered'] and row['state'] == 1, 'RAW_TX_INTERRUPTED'
                seq, value, crc = (int(previous[k]) for k in ['seq', 'value', 'crc'])
                assert crc == ((seq ^ value ^ 0xA5) & 255), 'RAW_PROGRAM_CRC_MISMATCH'
                completed.append(seq)
            previous = row
    assert abs(raw_first_power - first_power) < 1e-9
    assert completed == [e['seq'] for e in tx] and len(set(completed)) == 15, 'RAW_PROGRAM_TIMELINE_MISMATCH'
    # Reuse the exact saved-data report generator; do not execute its PDF renderer.
    generator = root / 'source/battery-world/packages/python/bfworld/src/bfworld/agentlab/design_lab/repository_node_report.py'
    spec = importlib.util.spec_from_file_location('saved_node_report', generator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, text in [('waveform.svg', module.waveform_svg(timeline)),
                       ('firmware-sequence.svg', module.sequence_svg(timeline))]:
        assert text.encode() == (node / name).read_bytes(), ('SAVED_DATA_FIGURE_CHANGED', name)
        (output / name).write_text(text)
    supplement = node / 'target_control_flow.py'
    spec = importlib.util.spec_from_file_location('target_control_flow', supplement)
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    control_svg, control_evidence = control.generate(node)
    assert control_svg == (node / 'target-control-flow.svg').read_text(), 'TARGET_FLOW_FIGURE_MISMATCH'
    assert control_evidence == load(node / 'target-control-flow.json'), 'TARGET_FLOW_SOURCE_MISMATCH'
    (output / 'target-control-flow.svg').write_text(control_svg)
    return {'system_id': identity, 'execution_id': original['execution_id'],
            'same_candidate_assets': True, 'STEP_solids_saved_readback': 32,
            'native_wire_segments': 114, 'native_wire_primitives': 21,
            'target_build': 'BUILT', 'target_hardware': 'NOT_TESTED',
            'first_powered_s': first_power, 'valid_saved_digital_frames': len(tx),
            'raw_program_csv_transition_and_crc_readback': 'PASS',
            'figures_rebuilt_byte_equal': ['waveform.svg', 'firmware-sequence.svg', 'target-control-flow.svg'],
            'target_control_flow': 'SOURCE_ONLY; hardware timing unmeasured',
            'new_models_science_native': 0}


def costs(root):
    rows = load(root / 'billing/campaign-requests.json')['rows']
    assert len(rows) == len({r['id'] for r in rows}) == 1238
    assert Counter(r['status'] for r in rows) == {'SETTLED': 1238}
    total = sum((Decimal(str(r['charged'])) for r in rows), Decimal(0))
    assert abs(total - Decimal('10.0268025')) < Decimal('0.00000000001')
    phase4 = load(root / 'evidence/phase4/result.json')
    assert phase4['accounting']['requests'] == 367
    assert phase4['accounting']['old_UNKNOWN_records_preserved'] == 24
    return {'original_campaign_plus_phases1_4_requests': len(rows),
            'provider_conservative_upper_usd': float(total),
            'invoice_verified': False, 'Codex_and_end_to_end_cost': 'UNKNOWN',
            'old_UNKNOWN_records_retained': 24}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    output = args.output.resolve()
    if output == root or root in output.parents:
        raise ValueError('USE_OUTPUT_OUTSIDE_DELIVERY')
    output.mkdir(parents=True, exist_ok=True)
    result = {'status': 'PASS', 'manifest_files': verify_manifest(root),
              'engineering': engineering(root, output), 'billing': costs(root), 'papers': []}
    for item in load(root / 'reproduction-commands.json')['commands']:
        argv = [sys.executable if s == '{python}' else s.replace('{output}', str(output)) for s in item['argv']]
        run = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=120)
        (output / (item['id'] + '.stdout.log')).write_text(run.stdout)
        (output / (item['id'] + '.stderr.log')).write_text(run.stderr)
        if run.returncode:
            raise RuntimeError('PAPER_REPRODUCTION_FAILED:' + item['id'])
        result['papers'].append({'id': item['id'], 'exit_code': run.returncode})
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
