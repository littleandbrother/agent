#!/usr/bin/env python3
"""Portable retained-data replay; never imports production code or runs a solve.

Default: Python standard-library integrity + accounting + unchanged-plan checks.
--full: also execute the sealed independent NumPy-only data audits in a temporary
output directory. Only BASE/OUT path assignments are rebound in memory.
"""
from pathlib import Path
import argparse, contextlib, hashlib, io, json, sys, tempfile

ROOT = Path(__file__).resolve().parent
OLD = ROOT/'passive-source-storage-20261001'
NEW = ROOT/'passive-source-storage-jacobian-20261001'
OREV = ROOT/'passive-source-storage-independent-review-20261001'
NREV = ROOT/'passive-jacobian-independent-review-20261001'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(base, mapping):
    for name, digest in mapping.items():
        p=base/name
        assert p.is_file(), 'Missing archive component: '+str(p)
        assert sha(p)==digest, 'Hash mismatch: '+str(p)
    return len(mapping)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',action='store_true',help='Run retained-data independent audits; requires NumPy, no SciPy or solver')
    args=parser.parse_args()
    manifest=read(ROOT/'PACKAGE-MANIFEST.json')
    count=verify(ROOT,manifest['files'])
    for base in (OLD,NEW):
        verify(base,read(base/'SOURCE-MANIFEST.json'))
        verify(base,read(base/'PLAN-SEAL.json')['bindings'])
        final=read(base/'FINAL-SEAL.json')
        assert sha(base/'FINAL-MANIFEST.json')==final['manifest_sha256']
        verify(base,read(base/'FINAL-MANIFEST.json'))
        for run in (base/'outputs').glob('cin*-*'):
            if run.is_dir():verify(run,read(run/'RUN-SEAL.json')['files'])
    for base,name in [(OREV,'PROSPECTIVE-REVIEW-MANIFEST.json'),(NREV,'PROSPECTIVE-MANIFEST.json'),(OREV/'post-run','MANIFEST.json'),(NREV/'post-run','MANIFEST.json')]:
        verify(base,read(base/name)['files'])
    handoff=ROOT/'passive-native-handoff-20261001'
    assert sha(handoff/'MANIFEST.json')==read(handoff/'SEAL.json')['manifest_sha256']
    verify(handoff,read(handoff/'MANIFEST.json'))
    a,b=read(OLD/'PLAN.json'),read(NEW/'PLAN.json')
    changed=[k for k in sorted(a.keys()|b.keys()) if a.get(k)!=b.get(k)]
    expected=['authorization_status','implementation_revision','jacobian','model_version']
    assert changed==expected,changed
    assert a['gates']==b['gates'] and a['resolutions']==b['resolutions']
    counts=read(NEW/'FINAL-RECEIPT.json')['totals_across_versions']
    assert counts=={'attempted':5,'completed':4,'stopped':1}
    assert len(list((OLD/'outputs').glob('cin*-*/STARTED.json')))==1
    assert len(list((NEW/'outputs').glob('cin*-*/STARTED.json')))==4
    stopped=read(OLD/'STOPPED-STUDY-RECEIPT.json')
    assert stopped['scientific_trajectories_unrun']==3 and stopped['comparison_admitted'] is False
    comparison=read(NEW/'outputs/COMPARISON.json');assert comparison['all_pass'] is True
    review=read(NREV/'post-run/REVIEW-RECEIPT.json')
    assert review['completed_repaired_trajectories']==4 and review['total_attempted_trajectories']==5
    for cid in ('cin47','cin10'):
        s=read(NEW/'outputs'/f'{cid}-fine'/'SUMMARY.json')
        assert abs(.5*s['case']['cin_F']*s['final_state'][3]**2-s['final_storage_J'])<1e-18
    out={'status':'INTEGRITY_AND_ACCOUNTING_PASS','files_verified':count,'unchanged_physical_parameters_and_gates':True,'only_plan_fields_changed':changed,'attempted':5,'completed':4,'stopped':1,'old_unrun':3,'new_scientific_solves':0,'full_independent_data_audit':False}
    if args.full:
        import numpy
        with tempfile.TemporaryDirectory(prefix='passive-retained-replay-') as tmp:
            td=Path(tmp)
            jobs=[(OREV/'post-run/tests/audit_partial_run.py',OLD,[],OREV/'post-run/reports/partial-run-readback.json')]
            jobs += [(NREV/'post-run/tests/audit_cell.py',NEW,[cid],NREV/'post-run/reports'/f'{cid}-readback.json') for cid in b['execution_order']]
            jobs += [(NREV/'post-run/tests/audit_comparison.py',NEW,[],NREV/'post-run/reports/comparison-readback.json')]
            for script,base,argv,expected_report in jobs:
                source=script.read_text()
                lines=source.splitlines()
                assert sum(line.startswith('BASE') and '=' in line for line in lines)==1
                assert sum(line.startswith('OUT') and '=' in line for line in lines)==1
                lines=[('BASE = Path('+repr(str(base))+')') if line.startswith('BASE') and '=' in line else ('OUT = Path('+repr(str(td))+')') if line.startswith('OUT') and '=' in line else line for line in lines]
                before=sys.argv;sys.argv=[str(script),*argv]
                try:
                    with contextlib.redirect_stdout(io.StringIO()):exec(compile('\n'.join(lines),str(script),'exec'),{'__file__':str(script),'__name__':'__main__'})
                finally:sys.argv=before
                assert read(td/expected_report.name)==read(expected_report), 'Readback differs: '+expected_report.name
            out.update(full_independent_data_audit=True,retained_audits_exactly_reproduced=6,numpy_version=numpy.__version__,status='FULL_RETAINED_REPLAY_PASS')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
