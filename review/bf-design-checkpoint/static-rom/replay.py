#!/usr/bin/env python3
"""Portable saved-data replay; standard library only; no provider imports/solves."""
import hashlib, json, math
from pathlib import Path
ROOT = Path(__file__).resolve().parent
read = lambda p: json.loads((ROOT / p).read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    manifest = read('FILE-MANIFEST.json')
    for f in manifest['files']:
        p = ROOT / f['path']
        assert p.is_file() and p.stat().st_size == f['bytes'], f['path']
        assert sha(p) == f['sha256'], f['path']
    listed={f['path'] for f in manifest['files']}
    actual={str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()}
    assert actual == listed | {'FILE-MANIFEST.json','SHA256SUMS.txt'}, 'Unlisted or missing file'
    export = read('SOURCE-EXPORT-MAP.json')
    excluded = {r['source_relative_path']: r for r in export['excluded_original_files']}
    original_verified = 0
    for group, name in [('beam','MANIFEST.json'),('beam-review','MANIFEST.json'),('magnetic','FILE-MANIFEST.json'),('magnetic-review','MANIFEST.json')]:
        for f in read(group+'/'+name)['files']:
            p = ROOT / group / f['path']
            if group=='beam' and f['path'] in excluded:
                assert excluded[f['path']]['sha256'] == f['sha256']
                assert not p.exists()
            else:
                assert p.is_file() and sha(p)==f['sha256'], str(p)
                original_verified += 1
    for f in read('beam/FINAL-SEAL.json')['files']:
        assert sha(ROOT/'beam'/f['path'])==f['sha256']
    plan=read('magnetic/STATIC-PLAN.json')
    original=read('magnetic/outputs/STATIC-RESULTS.json')
    raw=read('magnetic/evidence-completion-replay/RAW-REPLAY-RESULTS.json')
    summary=read('magnetic/outputs/SUMMARY.json')
    count=equalities=0; errors=[]; order_changes=[]
    assert len(plan['states'])==len(original['states'])==len(raw['states'])==5
    for state, saved, rerecorded in zip(plan['states'],original['states'],raw['states']):
        assert state==saved['state']==rerecorded['state']
        assert len(saved['orders'])==len(rerecorded['orders'])==3
        for order, a, b in zip(plan['quadrature_orders'],saved['orders'],rerecorded['orders']):
            d=b['nominal']; assert a['quadrature_order']==b['quadrature_order']==order
            for key in ['mutual_potential_J','force_beam_N','tip_torque_about_COM_beam_N_m','generalized_force_N']:
                assert a[key]==d[key]; equalities+=1
            Q=sum(d['projection_terms'].values())
            assert math.isclose(Q,d['generalized_force_N'],rel_tol=0,abs_tol=1e-14)
            assert d['contact']['obb_separated']
            assert len(b['raw_perturbation_pairs'])==len(a['q_energy_finite_differences'])==3
            for h, pair, prior in zip(plan['q_central_difference_steps_m'],b['raw_perturbation_pairs'],a['q_energy_finite_differences']):
                assert h==pair['h_m']==prior['h_m']
                for label,sign in [('plus',1),('minus',-1)]:
                    assert pair[label]['q_m']==state['q_m']+sign*h
                    assert pair[label]['contact']['obb_separated']
                derivative=-(pair['plus']['mutual_potential_J']-pair['minus']['mutual_potential_J'])/(2*h)
                assert derivative==pair['minus_dU_dq_N']==prior['minus_dU_dq_N']; equalities+=1
                error=abs(derivative-Q)
                atol,rtol=plan['predeclared_numeric_checks']['virtual_work_abs_plus_relative_N']
                assert error <= atol+rtol*abs(Q)
                assert pair['virtual_work_passed'] and prior['passed']
                errors.append(error); count+=1
        q6=saved['orders'][1]['generalized_force_N'];q10=saved['orders'][2]['generalized_force_N']
        change=q10-q6;atol,rtol=plan['predeclared_numeric_checks']['quadrature_6_to_10_abs_plus_relative_Q_N']
        assert abs(change)<=atol+rtol*abs(q10)
        assert change==saved['quadrature_check']['order6_to10_Q_change_N'];order_changes.append(abs(change))
    assert count==45 and equalities==105
    assert math.isclose(max(errors),summary['maximum_virtual_work_absolute_error_N'],rel_tol=0,abs_tol=1e-14)
    assert max(order_changes)==summary['maximum_6_to10_Q_change_N']
    assert original['identity']['time_integrations']==original['identity']['equilibrium_solves']==0
    assert not original['identity']['native_equivalent'] and not original['identity']['physical_qualified']
    print(json.dumps({'schema':'bf-static-checkpoint-portable-retained-replay-v1','passed':True,'delivery_files_verified':len(manifest['files']),'original_manifest_files_verified':original_verified,'excluded_third_party_source_snapshots':len(excluded),'composite_seal_entries_verified':6,'states':5,'raw_energy_derivatives':count,'recording_replay_equalities':equalities,'quadrature_comparisons':len(order_changes),'maximum_virtual_work_error_N':max(errors),'maximum_6_to10_Q_change_N':max(order_changes),'new_force_evaluations':0,'scientific_solves':0,'dynamic_runs':0,'native_or_physical_qualification':False,'formal_agent_success':False},indent=2))
if __name__=='__main__':main()
