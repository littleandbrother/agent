"""Independent acceptance of cold, zero-charge D5 native reference runs.

This operator command promotes only a nominal-model execution reference. It
does not promote hardware, fabrication, physical calibration or Agent claims.
"""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import gzip
import lzma
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from bfworld.agentlab.audit_checkpoint import Checkpoints, atomic_json, inspect_archive, archive_matches
from bfworld.agentlab.door_selfpower import contracts
from bfworld.agentlab.door_system.solver import execute_program, receive
from bfworld.agentlab.simulation_chain.contracts import file_hash, write_json


def json_primitives(value):
    """Preserve scalar values at the strict JSON boundary, including false."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: json_primitives(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_primitives(item) for item in value]
    return value


def verify_native_archive(path, item, checkpoints=None):
    archive = Path(path) / Path(item['path']).parent / item['archive_name']
    inspect = lambda: inspect_archive(archive)
    observed = (checkpoints.run('archive-readback', [archive], inspect)
                if checkpoints else inspect())
    # Separate binding validation: a second reference cannot borrow a different
    # manifest's successful verdict, even when it points at the same inode.
    passed = archive_matches(observed, item)
    print(json.dumps({'archive': str(archive), 'readback_passed': passed}), flush=True)
    return passed


def independent_terminal_currents(stage, design):
    """Stream original RAW values, independently of solver ratings/plot CSVs."""
    stage=Path(stage)
    receipt=json.loads((stage/'system.raw.archive.json').read_text())
    archive=stage/receipt['archive_name']
    opener=lzma.open if archive.suffix=='.xz' else gzip.open
    names=[];maximum={};minimum={};rows=0;last_time=0.;kcl_peak=0.
    with opener(archive,'rb') as stream:
        header=bytearray();marker='Binary:\n'.encode('utf-16-le')
        while not header.endswith(marker):
            char=stream.read(2)
            if not char or len(header)>65536:raise ValueError('AUDIT_RAW_HEADER_INVALID')
            header.extend(char)
        text=header.decode('utf-16-le')
        flags=re.search(r'Flags: ([^\n]+)',text)[1]
        if 'real' not in flags or any(x in flags for x in ('double','FastAccess','complex')):
            raise ValueError('AUDIT_RAW_FLAGS_UNSUPPORTED')
        n=int(re.search(r'No. Variables:\s*(\d+)',text)[1])
        count=int(re.search(r'No. Points:\s*(\d+)',text)[1])
        names=[line.split()[1].lower() for line in text.split('Variables:\n')[1].split('Binary:')[0].splitlines() if line.strip()]
        dtype=np.dtype([('t','<f8'),('v','<f4',(n-1,))]);stride=dtype.itemsize
        columns={name:i for i,name in enumerate(names[1:])}
        chosen=[name for name in columns if name.startswith('i(d') or name in ('ic(qp)','i(lextract)')]
        if not {'ic(qp)','i(lextract)'}.issubset(chosen):raise ValueError('AUDIT_TERMINAL_CURRENTS_MISSING')
        maximum=dict.fromkeys(chosen,0.);minimum=dict.fromkeys(chosen,0.)
        while chunk:=stream.read(stride*32768):
            if len(chunk)%stride:raise ValueError('AUDIT_RAW_TRUNCATED')
            data=np.frombuffer(chunk,dtype=dtype);time=np.abs(data['t']);rows+=len(time)
            if (np.diff(time)<0).any() or time[0]<last_time:raise ValueError('AUDIT_RAW_TIME_INVALID')
            last_time=float(time[-1]);mask=time>1e-7
            if not np.any(mask):continue
            values=data['v'][mask]
            if not np.isfinite(values).all():raise ValueError('AUDIT_RAW_NONFINITE')
            for name in chosen:
                a=values[:,columns[name]].astype(float)
                maximum[name]=max(maximum[name],float(max(a)))
                minimum[name]=min(minimum[name],float(min(a)))
            kcl=values[:,columns['ic(qp)']].astype(float)
            for name in chosen:
                if name.startswith('i(dblock'):kcl=kcl+values[:,columns[name]]
            kcl_peak=max(kcl_peak,float(max(abs(kcl))))
    if rows!=count or abs(last_time-design['base_design']['frozen']['task']['deadline_s'])>1e-7:
        raise ValueError('AUDIT_RAW_INCOMPLETE')
    bank=design['parts'].get('diode_bank')
    positions=['dbr1','dbr2','dbr3','dbr4','dblock','dtransfer']
    expected=(['i('+name+'_'+str(i)+')' for name in positions for i in range(1,4)] if bank
              else ['i('+name+')' for name in positions])+['i(denv)','i(dbase)']
    limit=.25 if design['parts']['diodes'].startswith('BAT46WJ') else .2
    reported=json.loads((stage/'rating-check.json').read_text())
    collector=max(maximum['ic(qp)'],-minimum['ic(qp)'])
    coil=max(maximum['i(lextract)'],-minimum['i(lextract)'])
    complete=all(name in maximum for name in expected)
    matches=complete and np.isclose(collector,reported['collector_peak_A'],rtol=1e-6,atol=1e-9) and np.isclose(coil,reported['coil_peak_A'],rtol=1e-6,atol=1e-9)
    if complete:
        matches=matches and all(np.isclose(maximum[name],reported['diodes'][name[2:-1]]['forward_peak_A'],rtol=1e-6,atol=1e-9) for name in expected)
    checks={'complete_branch_coverage':complete,'reported_peaks_match':bool(matches),
            'collector_below600mA':collector<.6,'coil_below_typical_saturation_screen':coil<design['parts']['coil']['Isat10_A_typ'],
            'per_die_repetitive_peak':complete and all(maximum[name]<=limit for name in expected),'collector_KCL':kcl_peak<1e-4}
    return {'passed':all(checks.values()),'checks':checks,'collector_peak_A':collector,'coil_peak_A':coil,
            'diode_peaks_A':{name:maximum[name] for name in expected if name in maximum},
            'collector_KCL_max_A':kcl_peak,'archive_sha256':file_hash(archive),
            'scope':'Independent current screening from native RAW; no pulse thermal or tolerance qualification.'}


def native_launch_identity(path):
    """A copied result directory is not an independent native cold launch."""
    path = Path(path).resolve()
    rows = []
    for stage in ('joint', 'time-step'):
        iterations = json.loads((path / stage / 'coupling-iterations.json').read_text())
        if not iterations:
            return {'passed': False, 'launches': rows, 'reason': 'missing native iterations'}
        for iteration in iterations:
            directory = path / stage / f"iteration-{iteration['iteration']:02}"
            log = directory / 'system.log'
            text = log.read_text()
            circuit = re.search(r'^Circuit: (.+)$', text, re.M)
            start = re.search(r'^Start Time: (.+)$', text, re.M)
            elapsed = re.search(r'^Total elapsed time: ([\d.]+) seconds\.$', text, re.M)
            rows.append({'stage': stage, 'iteration': iteration['iteration'],
                         'log_sha256': file_hash(log),
                         'circuit_matches_run': bool(circuit and Path(circuit[1]).resolve() == directory / 'system.cir'),
                         'started_local': start[1] if start else None,
                         'completed': bool(elapsed and float(elapsed[1]) > 0 and 'Fatal' not in text),
                         'requested_tolerance_kept': 'tolerance relaxed' not in text.lower()})
    return {'passed': bool(rows) and all(r['circuit_matches_run'] and r['started_local'] and r['completed'] and r['requested_tolerance_kept'] for r in rows),
            'launches': rows,
            'scope': 'Native completion logs bound to each run path; independent replay and RAW readback are separate checks.'}


def audit_run(path, checkpoints=None):
    path = Path(path).resolve()
    result = json.loads((path / 'result.json').read_text())
    manifest = json.loads((path / 'system-manifest.json').read_text())
    design = contracts.verify_design(json.loads((path / 'design-spec.json').read_text()))
    checks = {}
    checks['nominal_eligible'] = result['qualification']['nominal_prediction_eligible'] is True
    checks['event_delivered'] = result['qualification']['nominal_status'] == 'satisfied'
    checks['no_agent_reference'] = (result['model_calls'] == 0
        and result.get('execution_authority') in ('operator-reference', 'operator-engineering'))
    checks['source_stable'] = result['source_stable'] is True
    checks['current_executor'] = manifest['executor_sha256'] == contracts.template_hash()
    checks['design_identity'] = result['design_id'] == manifest['design_id'] == design['design_id']
    checks['artifact_integrity'] = all(
        (path / item['name']).is_file()
        and (path / item['name']).stat().st_size == item['bytes']
        and file_hash(path / item['name']) == item['sha256']
        for item in result['artifacts']
    )
    checks['dependency_integrity'] = all(
        Path(p).is_file() and file_hash(Path(p)) == digest
        for p, digest in manifest['source_dependencies'].items()
    )
    # Independent read-only streams; every result and exception is consumed.
    # One decompressor avoids competing with the next native solver. Hardlinks
    # and resumed checks reuse an immutable object checkpoint.
    with ThreadPoolExecutor(max_workers=1) as pool:
        archives_ok = list(pool.map(lambda item: verify_native_archive(path, item, checkpoints),
                                    manifest.get('native_archives', [])))
    checks['native_archive_receipts']=bool(archives_ok) and all(archives_ok)
    ledger = json.loads((path / 'energy.json').read_text())
    checks['zero_electrical_input'] = all(ledger[k] == 0 for k in (
        'initial_electric_J', 'independent_control_source_J', 'diagnostic_source_J'))
    deck = (path / 'system.cir').read_text()
    # Cmass/Cposition are mechanical states; every specified electrical IC is
    # zero. Unspecified native UIC capacitor/inductor states start from zero.
    electrical_ics = [float(x) for line in deck.splitlines()
                      if not line.startswith(('Cmass ', 'Cposition '))
                      for x in re.findall(r'\bIC=([-+\d.eE]+)', line)]
    checks['native_zero_initial_charge'] = bool(electrical_ics) and all(x == 0 for x in electrical_ics)
    checks['native_uic'] = bool(re.search(r'^\.tran .*\buic\s*$', deck, re.M))
    checks['no_diagnostic_generator'] = 'Idiagnostic' not in deck and 'Vdiagnostic' not in deck
    waveform = np.genfromtxt(path / 'waveform.csv', delimiter=',', names=True)
    program = np.genfromtxt(path / 'program.csv', delimiter=',', names=True)
    checks['finite_saved_channels'] = all(np.isfinite(waveform[n]).all() for n in waveform.dtype.names)
    checks['time_domain'] = bool(program['time_s'][0] == 0
                            and np.isclose(program['time_s'][-1], design['base_design']['frozen']['task']['deadline_s']))
    # Recompile the saved C source, not the already loaded executor library.
    with tempfile.TemporaryDirectory(prefix='bf-d5-independent-') as td:
        replay = Path(td)
        for name in ('program.c', 'policy.h', 'receiver.py'):
            shutil.copy2(path / 'firmware' / name, replay / name)
        subprocess.run(['cc', '-O2', '-shared', '-fPIC', 'program.c', '-o', 'program.dylib'],
                       cwd=replay, check=True, capture_output=True, timeout=30)
        current, states, events = execute_program(
            replay, program['time_s'], program['mcu_supply_V'], program['pgood_V'])
        checks['independent_compiled_program'] = bool(
            np.array_equal(states, program['state'].astype(int))
            and np.array_equal(current, program['current_A']))
        task = design['base_design']['frozen']['task']
        receiver = receive(replay, events, {'seed': task['seed'], 'scan_duty': task['scan_duty'],
                                          'loss_probability': task['link_loss_probability']})
        recorded = json.loads((path / 'receiver.json').read_text())
        checks['independent_receiver'] = receiver == recorded
        checks['complete_program_event'] = len(events) == result['metrics']['tx_completed'] >= 1
        fine = json.loads((path / 'time-step/solve.json').read_text())
        fine_program = np.genfromtxt(path / 'time-step/program.csv', delimiter=',', names=True)
        fine_current, fine_states, fine_events = execute_program(
            replay, fine_program['time_s'], fine_program['mcu_supply_V'], fine_program['pgood_V'])
        checks['independent_fine_program'] = bool(
            np.array_equal(fine_states, fine_program['state'].astype(int))
            and np.array_equal(fine_current, fine_program['current_A'])
            and len(fine_events) == fine['tx_completed'] == result['metrics']['tx_completed'])
        fine_receiver = receive(replay, fine_events, {'seed': task['seed'], 'scan_duty': task['scan_duty'],
                                                    'loss_probability': task['link_loss_probability']})
        checks['independent_fine_receiver'] = fine_receiver == json.loads((path / 'time-step/receiver.json').read_text())
    checks['full_stage_loads'] = all(
        np.all(program['current_A'][program['state'] == state] == expected)
        and np.any(program['state'] == state)
        for state, expected in ((1, .410e-3), (3, 1.596e-3), (4, 3.659e-3)))
    checks['fine_step_confirmation'] = json.loads((path / 'time-step-check.json').read_text())['passed'] is True
    checks['fine_nominal_eligibility'] = bool(
        fine['peak_tip_mm'] <= 8. and fine['numerical_energy_passed'] is True
        and fine['drive_ledger']['numerical_passed'] is True
        and fine['energy_ledger']['energy_lower_bound_passed'] is True
        and fine['ratings']['passed'] is True and fine['coupling_converged'] is True)
    terminal={}
    if result.get('rating_protocol')=='bf-component-rating-v2':
        with ThreadPoolExecutor(max_workers=2) as pool:
            names = ('joint', 'time-step')
            def terminal_check(name):
                stage = path / name
                r = json.loads((stage / 'system.raw.archive.json').read_text())
                inputs = [stage / r['archive_name'], stage / 'rating-check.json', path / 'design-spec.json']
                operation = lambda: independent_terminal_currents(stage, design)
                return (checkpoints.run('terminal-currents', inputs, operation) if checkpoints else operation())
            terminal = dict(zip(names, pool.map(terminal_check, names)))
        checks['independent_terminal_current_screen']=all(x['passed'] for x in terminal.values())
    checks['independent_step_agreement'] = bool(
        abs(result['metrics']['peak_tip_mm'] - fine['peak_tip_mm']) / max(abs(fine['peak_tip_mm']), 1e-12) <= .01
        and abs(result['metrics']['peak_storage_V'] - fine['peak_storage_V']) / max(abs(fine['peak_storage_V']), 1e-12) <= .01
        and fine['tx_completed'] == result['metrics']['tx_completed']
        and fine['received_events'] == result['metrics']['received_events'])
    launches = native_launch_identity(path)
    checks['native_launch_identity'] = launches['passed']
    return {'path': str(path), 'result_sha256': file_hash(path / 'result.json'),
            'design_id': design['design_id'], 'executor_sha256': manifest['executor_sha256'],
            'checks': checks, 'passed': all(checks.values()),
            'metrics': {k: result['metrics'][k] for k in (
                'peak_tip_mm', 'peak_piezo_V', 'peak_storage_V', 'peak_supply_V',
                'tx_completed', 'received_events', 'first_TX_s', 'first_RX_s')},
            'native_execution': launches, 'independent_terminal_currents':terminal,
            'no_success_cache': launches['passed']}


def audit(primary, repeat, output, promote=False, checkpoint_root=None):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('AUDIT_OUTPUT_ALREADY_EXISTS')
    # Fail fast on destination/serialization errors before touching large RAW.
    atomic_json(output.with_suffix('.preflight.json'), {'boolean': np.bool_(False), 'scalar': np.float64(1.0)})
    from bfworld.agentlab import audit_checkpoint
    checker = file_hash(Path(__file__)) + file_hash(Path(audit_checkpoint.__file__)) + contracts.template_hash()
    checkpoints = Checkpoints(checkpoint_root or output.parent / 'audit-checkpoints', checker)
    def one(path):
        path = Path(path).resolve()
        inputs = sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        manifest = json.loads((path / 'system-manifest.json').read_text())
        inputs += sorted(Path(p) for p in manifest['source_dependencies'])
        compiler = shutil.which('cc')
        if compiler:
            inputs.append(Path(compiler))
        # Result identity includes all retained inputs. A report write failure
        # retries only this small aggregation, not decompression or C replay.
        return checkpoints.run('run-audit', inputs, lambda: audit_run(path, checkpoints),
                               context={'run': str(path), 'numpy': np.__version__})
    a, b = one(primary), one(repeat)
    if a['path'] == b['path']:
        raise ValueError('COLD_REPEAT_REQUIRES_DISTINCT_RUNS')
    peaks = {k: abs(a['metrics'][k] - b['metrics'][k]) / max(abs(a['metrics'][k]), 1e-12)
             for k in ('peak_tip_mm', 'peak_piezo_V', 'peak_storage_V', 'peak_supply_V')}
    same = a['design_id'] == b['design_id'] and a['executor_sha256'] == b['executor_sha256']
    counts = all(a['metrics'][k] == b['metrics'][k] for k in ('tx_completed', 'received_events'))
    starts_a = {r['started_local'] for r in a['native_execution']['launches']}
    starts_b = {r['started_local'] for r in b['native_execution']['launches']}
    independent = (a['native_execution']['passed'] and b['native_execution']['passed']
                   and starts_a.isdisjoint(starts_b))
    cold = same and counts and independent and max(peaks.values()) <= .01
    result = {'schema_version': 'bf-door-selfpower-audit-v1', 'runs': [a, b],
              'cold_repeat': {'same_input_executor': same, 'counts_equal': counts,
                              'distinct_native_launches': independent,
                              'peak_relative_difference': peaks, 'target': .01, 'passed': cold},
              'passed': a['passed'] and b['passed'] and cold,
              'claim_boundary': 'Independent native cold launches and rebuilt-C replay in the declared nominal model. No physical, hardware, RF, manufacturing or autonomous Agent qualification.'}
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('AUDIT_OUTPUT_ALREADY_EXISTS')
    result = json_primitives(result)
    result['checkpoint_usage'] = {'hits': checkpoints.hits, 'misses': checkpoints.misses}
    atomic_json(output, result)
    if promote:
        if not result['passed']:
            raise ValueError('SELFPOWER_REFERENCE_AUDIT_FAILED')
        root = Path(primary).resolve().parent
        if not Path(repeat).resolve().is_relative_to(root):
            raise ValueError('REFERENCE_ROOT_MISMATCH')
        write_json(root / 'qualified-reference.json', {
            'schema_version': 'bf-door-selfpower-reference-v1',
            'result_path': str(Path(primary).resolve() / 'result.json'),
            'result_sha256': a['result_sha256'], 'executor_sha256': a['executor_sha256'],
            'audit_path': str(output), 'audit_sha256': file_hash(output),
            'scope': result['claim_boundary']})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--primary', type=Path, required=True)
    parser.add_argument('--repeat', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--promote', action='store_true')
    parser.add_argument('--checkpoint-root', type=Path)
    args = parser.parse_args()
    value = audit(args.primary, args.repeat, args.output, args.promote, args.checkpoint_root)
    print(json.dumps(value, ensure_ascii=False))
    raise SystemExit(0 if value['passed'] else 1)
