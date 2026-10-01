"""Read-only sealed pilot audit. Standard library; no extraction or runtime imports."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import zipfile

ARCHIVE_SHA = 'e1cdbed3c16d1469392b32ee178fcb107a3902951a23cda2ff0c2480c04b82c2'
SEALED_BASE = '338d60384d5805abf1e02252a4513860066a2c39'
PUBLICATION = '87e7d75b4c5cd13c96560b8aaa4168a292ddc3c9'
CHAIN = 'packages/python/bfworld/src/bfworld/agentlab/simulation_chain/'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def digest(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())

def close(a, b):
    return math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-15)

class Archive:
    def __init__(self, path, expected=ARCHIVE_SHA):
        raw = Path(path).read_bytes()
        require(sha(raw) == expected, 'ARCHIVE_SHA_MISMATCH')
        self.size = len(raw)
        self.z = zipfile.ZipFile(io.BytesIO(raw))
        names = self.z.namelist()
        require(len(names) == len(set(names)), 'DUPLICATE_MEMBER')
        require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts
                    and '\\' not in n for n in names), 'UNSAFE_MEMBER')
        require(sum(i.file_size for i in self.z.infolist()) < 200_000_000, 'ARCHIVE_SIZE_LIMIT')
        require(self.z.testzip() is None, 'ARCHIVE_CRC')
        self.names = set(names)
        self.manifest = self.json('manifest.json')
        require(self.names == set(self.manifest) | {'manifest.json'}, 'MEMBER_SET')
        for name, expected_hash in self.manifest.items():
            require(sha(self.read(name)) == expected_hash, 'MEMBER_HASH:' + name)

    def read(self, name):
        return self.z.read(name)

    def json(self, name):
        return json.loads(self.read(name))

    def table(self, name):
        rows = list(csv.DictReader(io.StringIO(self.read(name).decode())))
        return {k: [float(row[k]) for row in rows] for k in rows[0]}


def relative_channels(a, b):
    require(a.keys() == b.keys() and a['time_s'] == b['time_s'], 'COLD_TIME_OR_CHANNELS')
    return {k: max(abs(x-y) for x,y in zip(a[k], b[k])) / max(max(map(abs, a[k])), 1e-12)
            for k in a if k != 'time_s'}


def observed(a, p, receiver, stop):
    for table in (a, p):
        require(all(math.isfinite(v) for col in table.values() for v in col), 'NONFINITE_CHANNEL')
        require(all(b > a for a,b in zip(table['time_s'], table['time_s'][1:])), 'TIME_ORDER')
    transitions = [p['time_s'][i] for i in range(1,len(p['state'])) if p['state'][i] != p['state'][i-1]]
    return {'waveform_rows': len(a['time_s']), 'program_rows': len(p['time_s']),
        'waveform_channels': list(a), 'program_channels': list(p),
        'waveform_max_step_s': max(b-a for a,b in zip(a['time_s'],a['time_s'][1:])),
        'program_max_step_s': max(b-a for a,b in zip(p['time_s'],p['time_s'][1:])),
        'drive_stop_s': stop, 'drive_stop_sample_present': stop in a['time_s'],
        'drive_stop_one_sided_power': 'MISSING: no force/port-current channels or left/right power samples',
        'program_states': sorted(set(p['state'])), 'program_state_transitions': transitions,
        'receiver_events': len(receiver['events']), 'complete_tx': len(receiver['transmitted']),
        'event_resolution': 'sampled SIL states and saved event list only; no sub-step/native event reconstruction',
        'raw_native_grid': 'MISSING_RAW', 'raw_hash_verified': False,
        'energy_integral_reconstruction': 'UNSUPPORTED: missing native grid, force, port current, ROM coefficients and losses',
        'pmic_internal_loss': 'NOT_OBSERVABLE: encrypted macro-model',
        'sampled_peak_storage_V': max(a['storage_V']), 'sampled_peak_supply_V': max(a['supply_V'])}


def audit(path):
    a = Archive(path)
    seal, task, protocol = [a.json(n+'.json') for n in ('seal','task','protocol')]
    require(seal['protocol'] == protocol and seal['task'] == task, 'SEAL_BINDING')
    require(protocol['baseline_release'] == SEALED_BASE, 'SEALED_BASE')
    require(digest(task['task']) == task['task_hash'], 'TASK_HASH')
    source_index = {}
    for name, expected in seal['sources'].items():
        member = 'source-snapshot/' + name
        require(sha(a.read(member)) == expected, 'SEALED_SOURCE:' + name)
        source_index[name] = {'member': member, 'sha256': expected}
    mapping = {v['id']: v['candidate'] for v in protocol['mapping_candidates']}
    cold = protocol['cold_controls']
    recovery = {n.split('/')[-1][:-5]: a.json(n) for n in a.names
                if n.startswith('environment/') and n.endswith('-runtime-recovery1.json')}
    ids = {n.split('/')[1] for n in a.names if n.startswith('records/') and n.endswith('/receipt.json')}
    require(ids == set(mapping) | set(cold) | set(recovery), 'COHORT_MEMBERS')
    require((len(mapping),len(cold),len(recovery)) == (12,2,3), 'COHORT_COUNTS')
    runs, waves, programs = {}, {}, {}
    omitted = Counter()
    for id in sorted(ids):
        base = 'records/'+id+'/'
        receipt, spec = a.json(base+'receipt.json'), a.json(base+'design-spec.json')
        candidate = a.json(base+'candidate.json')
        expected = mapping[recovery[id]['repeats']] if id in recovery else mapping.get(id,{})
        require(candidate == receipt['candidate'] == expected and receipt['id'] == id, 'CANDIDATE_RECEIPT:'+id)
        normalized = json.loads(json.dumps(task['task']['baseline']))
        for group, values in candidate.items():
            normalized[group].update(values)
        require(normalized == spec, 'CANDIDATE_SPEC:'+id)
        if id in recovery:
            prior = 'records/'+recovery[id]['repeats']+'/'
            require(sha(a.read(prior+'receipt.json')) == recovery[id]['original_receipt_sha256'], 'RECOVERY_RECEIPT')
            old_hash = recovery[id].get('original_result_sha256')
            require(old_hash is None or sha(a.read(prior+'result.json')) == old_hash, 'RECOVERY_RESULT')
            require(recovery[id]['candidate'] == candidate and recovery[id]['new_design_choice'] is False, 'RECOVERY_IDENTITY')
        row = {'cohort': 'environment_recovery' if id in recovery else 'cold_control' if id in cold else 'declared_design',
               'repeat_of': recovery[id]['repeats'] if id in recovery else None,
               'status': receipt['run_status'], 'result_present': base+'result.json' in a.names}
        require(receipt['cold_control'] == (id in cold), 'COLD_IDENTITY')
        if not row['result_present']:
            require(receipt['result_sha256'] is None and receipt['run_status']=='tool_fail', 'MISSING_RESULT')
            row['classification'] = 'execution_failure; no physical verdict'
            row['observed_channels'] = 'MISSING_RESULT_AND_RAW'
            runs[id] = row
            continue
        result = a.json(base+'result.json')
        require(sha(a.read(base+'result.json')) == receipt['result_sha256'], 'RESULT_RECEIPT')
        require(result['run_status'] == receipt['run_status'], 'RUN_STATUS')
        for artifact in result['artifacts']:
            member = base + artifact['name']
            if member in a.names:
                raw = a.read(member)
                require(sha(raw) == artifact['sha256'] and len(raw)==artifact['bytes'], 'ARTIFACT:'+member)
            else:
                omitted[artifact['name']] += 1
        ev = result['task_evaluation']
        require(ev == a.json(base+'task-evaluation.json') and ev['task_hash']==task['task_hash']
                and ev['candidate_hash']==digest(spec), 'EVALUATION_BINDING')
        require(all(result['implementation'][n] == seal['sources'][CHAIN+n] for n in result['implementation']), 'IMPLEMENTATION_BINDING')
        physical = {k:v for k,v in spec.items() if k != 'presentation'}
        require(result['physics_hash']==digest({'spec':physical,'implementation':result['implementation'],'tools':result['tools']}), 'PHYSICS_HASH')
        require(all(result['stages'][k]['key']==v for k,v in result['model_versions'].items()), 'STAGE_IDENTITY')
        row.update(classification={'completed':'completed_nominal_unsatisfied', 'out_of_domain':'model_domain_rejection; not product infeasibility',
                    'tool_fail':'execution_failure; no physical verdict'}[receipt['run_status']],
                   nominal_task=ev['nominal_task_status'], physical_ranking=ev['design_ranking_eligible'],
                   physics_hash=result['physics_hash'], model_version=result['model_version'],
                   model_stage_keys='matched saved stage keys; cache inputs/payloads not independently rehashed',
                   tools='declared hashes only; external binaries/vendor payloads absent',
                   source_implementation_hashes_verified=True)
        require(ev['design_ranking_eligible'] is False, 'RANKING_BOUNDARY')
        if receipt['run_status']=='completed':
            require(ev['nominal_task_status']=='unsatisfied', 'UNEXPECTED_NOMINAL_STATUS')
            require(sha(a.read(base+'program.c'))==seal['sources'][CHAIN+'program.c'], 'PROGRAM_SOURCE')
            e = a.json(base+'energy.json')
            require(e == result['energy_ledger'], 'ENERGY_COPY')
            endpoint = e['final_mechanical_piezo_J']-e['initial_mechanical_piezo_J']+e['pmic_port_energy_J']+e['mechanical_loss_J']-e['external_force_work_J']
            require(abs(endpoint) <= e['mechanical_piezo_residual_J']+1e-15, 'ENERGY_ENDPOINT_BOUND')
            row['energy'] = {'endpoint_balance_J':endpoint, 'reported_max_path_residual_J': e['mechanical_piezo_residual_J'],
                'endpoint_within_reported_max':True, 'scope':'scalar algebra only; integrals and path maximum NOT independently verified',
                'initial_mechanical_piezo_J':e['initial_mechanical_piezo_J'], 'capacitor_initial_energy_J':e['pmic_initial_storage_J']}
            waves[id], programs[id] = a.table(base+'waveform.csv'), a.table(base+'program.csv')
            receiver = a.json(base+'receiver.json')
            row['observations'] = observed(waves[id], programs[id], receiver, spec['mechanical']['opening_s'])
            require(row['observations']['program_states']==result['metrics']['program_states_reached']
                    and len(receiver['transmitted'])==result['metrics']['tx_completed'], 'EVENT_READBACK')
        else:
            row['observed_channels'] = 'MISSING_RAW_AND_COMPLETED_WAVEFORM'
        runs[id] = row
    comparisons = []
    for prior in a.json('cold-repeat.json')['comparisons']:
        id = prior['id']
        delta = relative_channels(waves['nominal'], waves[id])
        require(delta.keys()==prior['waveform_relative_max'].keys()
                and all(close(v,prior['waveform_relative_max'][k]) for k,v in delta.items()), 'COLD_WAVEFORM_READBACK')
        facts = {'program_csv_identical': a.read('records/nominal/program.csv')==a.read('records/'+id+'/program.csv'),
            'receiver_json_identical': a.read('records/nominal/receiver.json')==a.read('records/'+id+'/receiver.json'),
            'program_time_state_current_identical': all(programs['nominal'][k]==programs[id][k] for k in ('time_s','state','current_A'))}
        require(all(prior[k]==v for k,v in facts.items()), 'COLD_EVENTS_READBACK')
        comparisons.append({'id':id,'waveform_relative_max':delta, **facts,
            'raw_peak_scalar_difference':'NOT_INDEPENDENTLY_VERIFIED: native RAW absent; sampled extrema are not native extrema',
            'empty_cache_independence':'receipt assertion only; historical cache contents absent'})
    status = dict(Counter(r['status'] for r in runs.values()))
    require(status==a.json('summary.json')['statuses'], 'STATUS_SUMMARY')
    return {'schema':'bf-pilot-independent-receipt-audit-v1', 'status':'SCOPED_AUDIT_PASS_WITH_MISSING_RAW',
        'archive':{'sha256':ARCHIVE_SHA,'bytes':a.size,'members':len(a.names),'manifest_verified':len(a.manifest)},
        'identity':{'sealed_base':SEALED_BASE,'publication_base':PUBLICATION,'publication_is_not_sealed_run_base':True,
            'task_hash':task['task_hash'],'sealed_sources_verified':len(source_index),
            'program_sha256':seal['sources'][CHAIN+'program.c'],
            'migration_paths':'P/R or source/runtime paths are location aliases, never independent replicas'},
        'cohort':{'declared_designs':12,'cold_controls':2,'environment_recovery_attempts':3,'total_attempts':17,
                  'all_attempt_statuses':status,'original_failures_preserved':True,'pi_status':a.json('summary.json')['pi_status']},
        'runs':runs,'cold_observed_comparisons':comparisons,
        'missing_artifacts':{'hash_verified':False,'declared_but_absent_counts':dict(sorted(omitted.items())),
            'large_native_index_entries':len(a.json('large-native-artifacts.json')),
            'local_path_read_attempts':0,'scope':'external hashes are declarations, not verified bytes'},
        'source_index':source_index,
        'execution':{'native_calls':0,'provider_calls':0,'new_trajectories':0,'scientific_success':False},
        'limitations':['No new physics, evaluation gate, report figure or force quadrature.',
            'No independent continuous energy integration or PMIC loss certification from resampled channels.',
            'Drive-stop and SIL observations do not supply one-sided native event power.',
            'No Agent benefit, hardware feasibility or design ranking claim.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if os.path.lexists(args.out) or args.out.resolve()==args.archive.resolve():
        parser.error('Output must be a new path; existing files/links/directories are protected')
    try:
        result = audit(args.archive)
        code = 0
    except Exception as exc:
        result = {'status':'BLOCKED_OR_FAILED','error_type':type(exc).__name__,'error':str(exc),'scientific_success':False}
        code = 1
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status':result['status'],'out':str(args.out)}))
    return code

if __name__=='__main__':
    raise SystemExit(main())
