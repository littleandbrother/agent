"""Read-only F1 B outcome and frozen-prefix verification; no model/science calls."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
S0 = BASE / 's0'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = read(HERE / 'FINAL-RECEIPT.json')
    for row in receipt['evidence_bindings'] + receipt['paper_bindings']:
        path = Path(row['path'])
        assert path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], path
    old = read(HERE / 'PAPER-PREFIX-BASELINES.json')['papers']
    for before, after in zip(old, receipt['paper_bindings']):
        data = Path(after['path']).read_bytes()
        assert len(data) > before['bytes'] and sha_bytes(data[:before['bytes']]) == before['sha256']
        assert data[before['bytes']:].count(b'\n\n') == 1
    batch = read(S0 / 'batch-result.json')
    assert batch['complete'] is True and len(batch['rows']) == 12
    rows = {r['episode']: r for r in batch['rows']}
    for condition in ('h2', 'h4'):
        formation = read(S0 / 'episodes' / ('form-' + condition) / 'formation.json')
        assert formation['proposals']['status'] == 'OK'
        assert formation['raw_proposals'][0]['payload'] == {'status': 'OK', 'patches': []}
        assert formation['raw_proposal_count'] == 0 and formation['selected_candidate'] is False
        assert formation['parent_retained'] is True
        for task in ('t1', 't2'):
            assert rows[task + '-' + condition]['status'] == 'NOT_EXECUTED_NO_QUALIFIED_DESCENDANT'
    for task in ('t1', 't2'):
        for condition in ('h0', 'h1', 'h3'):
            episode = task + '-' + condition
            row = rows[episode]
            transcript = read(S0 / 'episodes' / episode / 'method-transcript.json')
            assert row['status'] == 'FINITE_ATTEMPT_COMPLETE'
            assert transcript['initial_update']['status'] == 'UPDATED'
            assert len(row['actions']) == len(transcript['steps'])
            for action in row['actions']:
                public = read(Path(action['path']) / 'public-result.json')
                assert public['public_check'] == action['public_check']
                assert action['readback']['sha256'] == sha(Path(action['readback']['path']))
        h3 = rows[task + '-h3']
        transcript = read(S0 / 'episodes' / (task + '-h3') / 'method-transcript.json')
        assert transcript['termination']['reason'] == 'HOOK_ERROR'
        assert len(h3['actions']) == 2 and all(
            a['actual_input']['operation'] == 'observe' and a['usage']['reused'] is True
            and a['usage']['numerical_inputs'] == 0 for a in h3['actions'])
        assert transcript['initial_update']['site_calls'][0]['loaded'] is True
        assert transcript['initial_update']['site_calls'][0]['triggered'] is True
        assert transcript['initial_update']['parent_design_preserved'] is True
        assert rows[task + '-h1']['last_public_check']['verdict'] == 'PASS'
        assert read(Path(rows[task + '-h1']['actions'][-1]['path']) / 'public-result.json')['model_valid'] is True
    assert rows['t1-h0']['last_public_check']['verdict'] == 'UNKNOWN'
    assert rows['t2-h0']['last_public_check']['verdict'] == 'PASS'
    assert read(Path(rows['t1-h0']['actions'][-1]['path']) / 'public-result.json')['model_valid'] is False
    totals = receipt['resource_summary']
    assert sum(r.get('accounting', {}).get('requests', 0) for r in batch['rows']) == totals['settled_provider_requests'] == 25
    assert abs(sum(r.get('accounting', {}).get('settled_charge_upper_bound_usd', 0) for r in batch['rows'])
               - totals['pinned_rate_estimate_usd']) < 1e-10
    ledger = read(S0 / 'resource-ledger.json')
    assert (ledger['full_dynamic_inputs'], ledger['cache_reuses'], ledger['candidate_evaluations'],
            ledger['cheap_calls']) == (6, 7, 11, 0)
    hook = read(S0 / 't1-h3-hook-readback.json')
    assert hook['exact_context_match'] is True and hook['over_frame_cap'] is True
    assert hook['encoded_frame_bytes'] == 2461796 and hook['immutable_worker_max_frame_bytes'] == 2000000
    assert batch['provider_after']['inflight'] == 0 and batch['provider_after']['statuses']['UNKNOWN'] == 1
    print(json.dumps({'status': 'PASS_READ_ONLY', 'formed_descendants': 0,
                      'executed_solves': 6, 'skipped_descendant_cells': 4,
                      'settled_provider_requests': 25, 'new_full_dynamic_inputs': 6,
                      'paper_prefixes_preserved': 2}, ensure_ascii=False))


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


if __name__ == '__main__':
    main()
