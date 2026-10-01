#!/usr/bin/env python3
"""Bounded offline CSV replay. Python >=3.10 and NumPy >=2.0. No network/solver.

Usage: python replay_native_rails.py --coarse INPUT --fine INPUT --packet INPUT \
  --evaluator INPUT --freeze INPUT --provenance INPUT --out replay-results
Output is an exclusive-created direct child of this script's directory.
No path strings are emitted in results or error messages. Inputs cannot contain
symlink components. Hashes bind all real inputs before numerical parsing.
"""
import argparse, csv, hashlib, io, json, math, os, stat, sys, tempfile
from pathlib import Path
import numpy as np

EXPECTED = {
    'coarse': (12164148, '4bdbbb62543bbd61b20651d678858b8ac618b2ae03dd19410ff2869f268da84a'),
    'fine': (24303900, '7c75a9cf25709dc45bcf745200f5ef023a795d5c974852faf73df266ddb3253b'),
    'packet': (None, 'a4824d3765ca6411871f4b507a64b10e3c0ca46af539ecdcfdb1d1b42d7f8243'),
    'evaluator': (4166, 'b2ad2549049ddb8de5da3df0d1d5359d84ae257926cbcf73bb1414624f3ec567'),
    'provenance': (11070, 'd8e811cab9ad439c5dd14a34df6e4b48550af685de7d9d527233661d2afea2bd'),
    'freeze': (4186, 'c6f54200ab56a0d952a2e0806c407b6f9e765aca7fbd7f02d2281bf8c9ae7fd0'),
}
P = dict(window_s=.5, voltage_peak_to_peak_tol_V=.001,
         slope_voltage_change_tol_V=.001, energy_drift_tol_J=1e-8,
         charge_consistency_tol_C=1e-8, max_sample_interval_s=.001,
         cap_F=1e-6, vin2_F=4.7e-6, phase='source_off')
COLUMNS = ('time_s','vin_V','cap_V','vin2_V','icap_A','ivin2_A',
           'source_connected','out_V','pgood_V','cap_gap_V')
REQUIRED = COLUMNS[:7]
MAX_INPUT = 32 * 1024 * 1024
class ReplayError(Exception): pass

def safe_parent(path):
    """Return an open parent directory and leaf, rejecting every symlink."""
    raw = os.fspath(path)
    if not raw or any(p in ('.', '..') for p in raw.split('/')):
        raise ReplayError('UNSAFE_PATH_COMPONENT')
    absolute = raw if raw.startswith('/') else os.getcwd() + '/' + raw
    parts = absolute.split('/')[1:]
    if not parts or any(not p for p in parts):
        raise ReplayError('UNSAFE_PATH_COMPONENT')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for p in parts[:-1]:
            child = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd); fd = child
        return fd, parts[-1]
    except OSError:
        os.close(fd); raise ReplayError('UNSAFE_OR_MISSING_PARENT') from None

def read_verified(path, expected=None):
    parent, leaf = safe_parent(path)
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
    except OSError:
        raise ReplayError('UNSAFE_OR_MISSING_INPUT') from None
    finally:
        os.close(parent)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ReplayError('INPUT_NOT_REGULAR_FILE')
        if before.st_size > MAX_INPUT:
            raise ReplayError('INPUT_SIZE_BOUND_EXCEEDED')
        if expected and expected[0] is not None and before.st_size != expected[0]:
            raise ReplayError('INPUT_SIZE_MISMATCH')
        chunks = []; total = 0
        while True:
            chunk = os.read(fd, min(1024*1024, MAX_INPUT + 1 - total))
            if not chunk: break
            chunks.append(chunk); total += len(chunk)
            if total > MAX_INPUT: raise ReplayError('INPUT_SIZE_BOUND_EXCEEDED')
        after = os.fstat(fd)
        sig = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if sig(before) != sig(after) or total != before.st_size:
            raise ReplayError('INPUT_CHANGED_DURING_READ')
        data = b''.join(chunks); digest = hashlib.sha256(data).hexdigest()
        if expected and digest != expected[1]: raise ReplayError('INPUT_HASH_MISMATCH')
        return data, {'bytes':len(data),'sha256':digest,'verified':True}
    finally: os.close(fd)

def validate(x):
    if any(k not in x for k in REQUIRED): raise ReplayError('MISSING_TRACE_COLUMNS')
    t = x['time_s']; n = len(t)
    if n < 3 or any(len(v)!=n or not np.isfinite(v).all() for v in x.values()):
        raise ReplayError('INVALID_OR_NONFINITE_TRACE')
    if t[0]<0 or np.any(np.diff(t)<=0): raise ReplayError('NONMONOTONIC_TRACE')
    if not np.isin(x['source_connected'],[0,1]).all():
        raise ReplayError('NONBINARY_SOURCE_LABEL')

def parse_csv(data):
    try:
        text = data.decode('utf-8'); header = next(csv.reader(io.StringIO(text)))
        if tuple(header) != COLUMNS: raise ReplayError('CSV_SCHEMA_MISMATCH')
        a = np.loadtxt(io.StringIO(text),delimiter=',',skiprows=1,ndmin=2)
        if a.shape[1] != len(COLUMNS): raise ReplayError('CSV_SCHEMA_MISMATCH')
        x = {k:a[:,j] for j,k in enumerate(COLUMNS)}
    except (UnicodeError,ValueError,StopIteration):
        raise ReplayError('INVALID_CSV') from None
    validate(x)
    return x

def rails(x):
    return [('CAP_gap',x['vin_V']-x['cap_V'],x['icap_A'],P['cap_F']),
            ('VIN2',x['vin2_V'],x['ivin2_A'],P['vin2_F'])]

def windows(x):
    t=x['time_s']; changes=np.flatnonzero(np.diff(x['source_connected'])!=0)+1
    start=int(changes[-1]) if len(changes) else 0
    if x['source_connected'][-1] != 0:
        return None, {'settled':False,'reason':'WRONG_TERMINAL_SOURCE_PHASE'}
    if t[-1]-t[start] < 2*P['window_s']:
        return None, {'settled':False,'reason':'INSUFFICIENT_POST_TRANSITION_TRACE'}
    out=[]
    for factor in (1,2):
        first=max(start,int(np.searchsorted(t,t[-1]-factor*P['window_s'],side='right')-1))
        tt=t[first:]
        if len(tt)<8 or float(np.max(np.diff(tt)))>P['max_sample_interval_s']:
            return None, {'settled':False,'reason':'INSUFFICIENT_SAMPLING','window_multiple':factor}
        out.append((factor,first))
    return out,None

def independent_settling(x):
    validate(x); wins,err=windows(x)
    if err: return err
    metrics=[]; t=x['time_s']
    for factor,first in wins:
        tt=t[first:]; dt=tt-tt[0]; centered=dt-np.mean(dt)
        for name,v,i,C in rails(x):
            vv=v[first:]; ii=i[first:]
            # Independent centered ordinary least-squares slope; no polyfit here.
            slope=float(np.dot(centered,vv-np.mean(vv))/np.dot(centered,centered))
            ptp=float(np.max(vv)-np.min(vv)); elapsed=float(tt[-1]-tt[0])
            e=.5*C*vv*vv; de=float(abs(e[-1]-e[0]))
            qerr=float(abs(C*(vv[-1]-vv[0])-np.trapezoid(ii,tt)))
            checks=dict(voltage_peak_to_peak=ptp<=P['voltage_peak_to_peak_tol_V'],
                        slope_over_observation_window=abs(slope)*elapsed<=P['slope_voltage_change_tol_V'],
                        energy_drift=de<=P['energy_drift_tol_J'],
                        signed_charge_consistency=qerr<=P['charge_consistency_tol_C'])
            metrics.append(dict(rail=name,window_multiple=factor,window_start_s=float(tt[0]),
                window_end_s=float(tt[-1]),samples=len(tt),max_sample_gap_s=float(np.max(np.diff(tt))),
                voltage_peak_to_peak_V=ptp,slope_V_s=slope,slope_voltage_change_V=abs(slope)*elapsed,
                energy_drift_J=de,signed_charge_consistency_error_C=qerr,checks=checks,
                passed=all(checks.values())))
    return dict(settled=all(m['passed'] for m in metrics),phase='source_off',criteria=P,metrics=metrics)

def accounting(x,first=0):
    t=x['time_s'][first:]; result={}
    for name,v,i,C in rails(x):
        v=v[first:]; i=i[first:]; power=v*i
        e0=float(.5*C*v[0]**2); e1=float(.5*C*v[-1]**2)
        q0=float(C*v[0]); q1=float(C*v[-1]); dq=float(C*(v[-1]-v[0]))
        work=float(np.trapezoid(power,t)); charge=float(np.trapezoid(i,t))
        result[name]=dict(capacitance_F=C,window_start_s=float(t[0]),window_end_s=float(t[-1]),
            initial_voltage_V=float(v[0]),final_voltage_V=float(v[-1]),
            initial_charge_C=q0,final_charge_C=q1,delta_charge_C=dq,integrated_current_C=charge,
            signed_charge_residual_C=dq-charge,absolute_charge_residual_C=abs(dq-charge),
            initial_energy_J=e0,final_energy_J=e1,delta_energy_J=e1-e0,signed_work_J=work,
            signed_energy_residual_J=(e1-e0)-work,absolute_energy_residual_J=abs((e1-e0)-work),
            positive_power_integral_J=float(np.trapezoid(np.maximum(power,0),t)),
            negative_power_integral_J=float(np.trapezoid(np.minimum(power,0),t)))
    return result

def compare(coarse,fine):
    tc=coarse['time_s']; tf=fine['time_s']; lo=max(tc[0],tf[0]); hi=min(tc[-1],tf[-1])
    if hi<=lo: raise ReplayError('NO_SHARED_TIME_INTERVAL')
    gc=tc[(tc>=lo)&(tc<=hi)]; gf=tf[(tf>=lo)&(tf<=hi)]
    results={}
    for mode,g in [('common_coarse_grid',gc),('common_union_grid',np.union1d(gc,gf))]:
        if len(g)<2: raise ReplayError('INSUFFICIENT_COMPARISON_SAMPLES')
        metrics={}
        for name in ('vin_V','cap_V','vin2_V','cap_gap_V','out_V','pgood_V','icap_A','ivin2_A'):
            c=coarse['vin_V']-coarse['cap_V'] if name=='cap_gap_V' else coarse[name]
            f=fine['vin_V']-fine['cap_V'] if name=='cap_gap_V' else fine[name]
            ci=np.interp(g,tc,c); fi=np.interp(g,tf,f); err=fi-ci
            scale=float(max(np.max(np.abs(ci)),np.max(np.abs(fi))))
            mx=float(np.max(np.abs(err))); duration=float(g[-1]-g[0]); k=int(np.argmax(np.abs(err)))
            metrics[name]=dict(max_absolute_error=mx,time_of_max_absolute_error_s=float(g[k]),
                time_weighted_rms_error=float(np.sqrt(np.trapezoid(err*err,g)/duration)),
                time_weighted_mean_signed_error=float(np.trapezoid(err,g)/duration),
                terminal_fine_minus_coarse=float(err[-1]),pooled_peak_absolute_signal=scale,
                max_error_over_pooled_peak=mx/scale if scale else None,
                units='A' if name.endswith('_A') else 'V')
        results[mode]=dict(samples=len(g),start_s=float(g[0]),end_s=float(g[-1]),metrics=metrics)
    return dict(method='Piecewise linear interpolation in shared interval; no extrapolation',
        numerical_acceptance_threshold=None,convergence_verdict=None,grids=results)

def make_dir_exclusive(path):
    parent,leaf=safe_parent(path)
    try:
        os.mkdir(leaf,mode=0o700,dir_fd=parent)
        return os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    except OSError: raise ReplayError('OUTPUT_EXISTS_OR_UNSAFE') from None
    finally: os.close(parent)

def write_exclusive(fd,name,data):
    if '/' in name or name in ('.','..'): raise ReplayError('UNSAFE_OUTPUT_NAME')
    try:
        out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444,dir_fd=fd)
        with os.fdopen(out,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    except OSError: raise ReplayError('OUTPUT_WRITE_REJECTED') from None

def encoded(x): return (json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()

def self_tests(base):
    tests=[]
    def check(name,ok):
        if not ok: raise ReplayError('SELF_TEST_FAILED:'+name)
        tests.append({'test':name,'passed':True})
    def rejects(name,fn,code=None):
        try: fn()
        except ReplayError as e: check(name,code is None or str(e)==code)
        else: check(name,False)
    t=np.linspace(0,2,4001); v=.2+1e-4*t; v2=.3-1e-4*t
    x={'time_s':t,'vin_V':v+.07,'cap_V':np.full(t.shape,.07),'vin2_V':v2,
       'icap_A':np.full(t.shape,1e-10),'ivin2_A':np.full(t.shape,-4.7e-10),
       'source_connected':np.zeros(t.shape)}
    a=accounting(x)
    check('synthetic_passive_sign_charge_energy_identities',all(
       z['absolute_energy_residual_J']<1e-20 and z['absolute_charge_residual_C']<1e-20 for z in a.values()))
    check('synthetic_charge_and_discharge_work_signs',a['CAP_gap']['signed_work_J']>0 and a['VIN2']['signed_work_J']<0)
    check('synthetic_two_window_settling',independent_settling(x)['settled'])
    xx=dict(x); xx['icap_A']=-x['icap_A']
    check('synthetic_inverted_current_detected',accounting(xx)['CAP_gap']['absolute_charge_residual_C']>1e-10)
    xx=dict(x); xx.pop('icap_A'); rejects('missing_column_rejected',lambda:validate(xx))
    xx={k:v.copy() for k,v in x.items()}; xx['vin_V'][2]=np.nan
    rejects('nonfinite_trace_rejected',lambda:validate(xx))
    xx={k:v.copy() for k,v in x.items()}; xx['time_s'][2]=xx['time_s'][1]
    rejects('duplicate_time_rejected',lambda:validate(xx))
    xx={k:v.copy() for k,v in x.items()}; xx['source_connected'][2]=.5
    rejects('invalid_source_label_rejected',lambda:validate(xx))
    xx={k:v.copy() for k,v in x.items()}; xx['source_connected'][:]=1
    check('wrong_terminal_phase_rejected',not independent_settling(xx)['settled'])
    short={k:v[:100] for k,v in x.items()}
    check('short_post_transition_rejected',not independent_settling(short)['settled'])
    sparse={k:v[::10] for k,v in x.items()}
    check('sparse_window_rejected',not independent_settling(sparse)['settled'])
    with tempfile.TemporaryDirectory(prefix='self-test-',dir=base) as d:
        p=Path(d); good=p/'good'; good.write_bytes(b'abc'); digest=hashlib.sha256(b'abc').hexdigest()
        read_verified(good,(3,digest)); check('valid_input_identity_accepted',True)
        rejects('tamper_hash_rejected',lambda:read_verified(good,(3,'0'*64)),'INPUT_HASH_MISMATCH')
        rejects('truncation_size_rejected',lambda:read_verified(good,(4,digest)),'INPUT_SIZE_MISMATCH')
        rejects('missing_file_rejected',lambda:read_verified(p/'absent'))
        (p/'link').symlink_to(good)
        rejects('input_leaf_symlink_rejected',lambda:read_verified(p/'link'))
        (p/'parent-link').symlink_to(p,target_is_directory=True)
        rejects('input_parent_symlink_rejected',lambda:read_verified(p/'parent-link'/'good'))
        fd=make_dir_exclusive(p/'out'); write_exclusive(fd,'a',b'original')
        rejects('file_overwrite_rejected',lambda:write_exclusive(fd,'a',b'changed'))
        check('original_file_unchanged',(p/'out'/'a').read_bytes()==b'original'); os.close(fd)
        rejects('directory_overwrite_rejected',lambda:make_dir_exclusive(p/'out'))
        (p/'out-link').symlink_to(p/'out',target_is_directory=True)
        rejects('output_symlink_rejected',lambda:make_dir_exclusive(p/'out-link'))
    return tests

def report_for(x,official):
    validate(x); own=independent_settling(x); frozen=official.evaluate(x,P)
    wins,err=windows(x)
    deltas=[]
    for a,b in zip(own.get('metrics',[]),frozen.get('metrics',[])):
        if a['checks'] != b['checks']: raise ReplayError('INDEPENDENT_PREDICATE_DISAGREEMENT')
        deltas.append(dict(rail=a['rail'],window_multiple=a['window_multiple'],
            independent_minus_polyfit_slope_V_s=a['slope_V_s']-b['slope_V_s']))
    if own['settled'] != frozen['settled']: raise ReplayError('INDEPENDENT_PREDICATE_DISAGREEMENT')
    t=x['time_s']; d=np.diff(t)
    return dict(samples=len(t),start_s=float(t[0]),end_s=float(t[-1]),min_sample_gap_s=float(d.min()),
        max_sample_gap_s=float(d.max()),median_sample_gap_s=float(np.median(d)),
        source_connected_values=np.unique(x['source_connected']).tolist(),
        source_connection_interpretation='Synthetic absent-control fallback; not observed disconnection',
        exported_cap_gap_max_abs_difference_V=float(np.max(np.abs(x['cap_gap_V']-(x['vin_V']-x['cap_V'])))),
        peak_vin_V=float(np.max(x['vin_V'])),peak_out_V=float(np.max(x['out_V'])),
        terminal_vin_V=float(x['vin_V'][-1]),terminal_out_V=float(x['out_V'][-1]),
        frozen_evaluator=frozen,independent_settling=own,independent_predicate_checks_agree=True,
        slope_reimplementation_differences=deltas,whole_trace_accounting=accounting(x),
        trailing_window_accounting={str(f):accounting(x,k) for f,k in (wins or [])})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in EXPECTED: p.add_argument('--'+name)
    p.add_argument('--out'); p.add_argument('--self-test',action='store_true'); a=p.parse_args()
    # Restrict every created artifact to this standalone script's own directory.
    base=Path(__file__).absolute().parent
    # Refuse a symlinked work directory before creating even self-test files.
    parent,leaf=safe_parent(base)
    try:
        basefd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
        os.close(basefd)
    except OSError: raise ReplayError('UNSAFE_WORK_DIRECTORY') from None
    finally: os.close(parent)
    tests=self_tests(base)
    if a.self_test:
        print(json.dumps({'status':'passed','tests':tests},allow_nan=False)); return
    if not all(getattr(a,k) for k in EXPECTED) or not a.out:
        raise ReplayError('ALL_SIX_INPUTS_AND_OUTPUT_NAME_REQUIRED')
    if '/' in a.out or a.out in ('.','..'): raise ReplayError('OUTPUT_MUST_BE_DIRECT_CHILD_NAME')
    out=base/a.out
    # Reject existing output before expensive reads; exclusive mkdir still guards races.
    if os.path.lexists(out): raise ReplayError('OUTPUT_EXISTS_OR_UNSAFE')
    inputs={}; identities={}
    for name,expected in EXPECTED.items():
        inputs[name],identities[name]=read_verified(getattr(a,name),expected)
    freeze=json.loads(inputs['freeze']); packet=json.loads(inputs['packet'])
    if freeze['parameters']!=P: raise ReplayError('FROZEN_PARAMETER_MISMATCH')
    # Only execute the hash-verified 4166-byte trace predicate, never a solver or wrapper.
    import types
    official=types.ModuleType('hash_verified_settling_predicate')
    exec(compile(inputs['evaluator'],'<hash-verified-settling-predicate>','exec'),official.__dict__)
    provenance=json.loads(inputs['provenance'])
    for key in ('six_fixture','true_refinement'):
        params=provenance['settling']['request_parameters'][key]
        if {**params,'phase':'source_off'}!=P: raise ReplayError('PROVENANCE_PARAMETER_INCOMPATIBILITY')
    if provenance['refinement']['waveform_acceptance_threshold'] is not None:
        raise ReplayError('UNEXPECTED_CONVERGENCE_GATE')
    coarse=parse_csv(inputs['coarse']); fine=parse_csv(inputs['fine'])
    cr=report_for(coarse,official); fr=report_for(fine,official)
    step=packet['rail']['step_refinement_reported']['separate_true_baseline'][0]
    results=dict(schema_version='native-rail-reanalysis-v1',scope='Read-only offline CSV replay',
       software={'python':sys.version.split()[0],'numpy':np.__version__},self_tests=tests,
       coarse=cr,fine=fr,waveform_comparison=compare(coarse,fine),
       reported_step_refinement={'coarse_max_step_s':step['coarse_max_step_s'],
           'fine_max_step_s':step['fine_max_step_s'],
           'declared_step_exactly_halved':step['fine_max_step_s']==step['coarse_max_step_s']/2,
           'basis':'Sanitized packet metadata, no deck/RAW/binary reread'},
       limitations=freeze['limits']+[freeze['energy_accounting']['scope'],
           'Predicate phase is synthetic baseline bookkeeping, not physical disconnection.',
           'Numerical waveform convergence has no prospectively declared acceptance threshold.'])
    # Compare summaries descriptively; this does not validate historical wrapper bytes.
    fixtures=packet['rail']['fixtures']; fc=next(x for x in fixtures if x['id']=='baseline-observation')
    ff=next(x for x in fixtures if x['collection']=='separate-baseline-refinement')
    matches={}
    for label,calc,fixture in [('coarse',cr,fc),('fine',fr,ff)]:
        rep=fixture['metrics_reported']; diff={}
        for key in ('peak_vin_V','peak_out_V','terminal_vin_V'): diff[key]=calc[key]-rep[key]
        for local,old in [('CAP_gap','CAP'),('VIN2','VIN2')]:
            n=calc['whole_trace_accounting'][local]; o=rep['rail_energy'][old]
            for nk,ok in [('initial_energy_J','initial_J'),('final_energy_J','final_J'),
                          ('signed_work_J','signed_work_J'),('signed_energy_residual_J','balance_residual_J')]:
                diff[local+'.'+nk]=n[nk]-o[ok]
        matches[label]={'recomputed_minus_reported':diff,
                        'settling_boolean_matches_reported':calc['frozen_evaluator']['settled']==fixture['verifier_outcome_reported']['settled']}
    results['historical_summary_comparison']=matches
    historical_expression={}
    for native,key in [('v(vin)','vin_V'),('v(out)','out_V'),('v(vin2)','vin2_V'),('v(cap)','cap_V')]:
        # Supplementary reconstruction of producer's explicitly supplied expression.
        # This has a 1 uV floor and fine-only peak denominator, unlike the frozen
        # replay's pooled-scale metrics. Neither expression defines an acceptance gate.
        a=coarse[key]; b=fine[key]
        ratio=float(np.max(abs(a-np.interp(coarse['time_s'],fine['time_s'],b)))/max(np.max(abs(b)),1e-6))
        reported=step['max_normalized_difference'][native]
        historical_expression[native]={'recomputed_ratio':ratio,'reported_ratio':reported,'difference':ratio-reported}
    results['supplemental_producer_expression_check']={
        'formula':'max(abs(coarse-interp(fine,coarse_time)))/max(max(abs(fine)),1e-6)',
        'basis':'Explicit producer provenance received before CSV access; descriptive only',
        'changes_frozen_comparison_method':False,'metrics':historical_expression}
    results['producer_provenance_compatibility']={'parameters_match_frozen_replay':True,
        'wrapper_phase_mapping_matches':True,'no_new_convergence_gate':True,
        'source_wrapper_historical_identity_sealed':False}

    script,script_id=read_verified(Path(__file__).absolute())
    manifest=dict(schema_version='immutable-input-identity-v1',input_identities=identities,
        replay_script_identity=script_id,method_freeze_identity=identities['freeze'],
        notes=['No absolute input paths retained.','Exact hashes bound before CSV parsing.',
               'CSV identity is verified; export fidelity to native RAW is not.',
               'Files are exclusive-created and chmod read-only; hashes detect later changes.',
               'This replay is new evidence, not a replacement/restamp of historical receipts.'])
    payloads={'input-manifest.json':encoded(manifest),'results.json':encoded(results),
              'method-freeze.json':inputs['freeze'],'settling_validator.py':inputs['evaluator'],
              'replay_native_rails.py':script}
    digest={name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in payloads.items()}
    payloads['artifact-sha256.json']=encoded(digest)
    fd=make_dir_exclusive(out)
    try:
        for name,data in payloads.items(): write_exclusive(fd,name,data)
        os.fsync(fd)
    finally: os.close(fd)
    print(json.dumps({'status':'completed','coarse_settled':cr['frozen_evaluator']['settled'],
        'fine_settled':fr['frozen_evaluator']['settled'],'convergence_verdict':None,
        'artifacts':digest,'self_tests_passed':len(tests)},allow_nan=False))

if __name__=='__main__':
    try: main()
    except ReplayError as e:
        print(json.dumps({'status':'rejected','error':str(e)})); sys.exit(2)
    except Exception:
        # Avoid leaking caller paths or source data through exceptions/tracebacks.
        print(json.dumps({'status':'rejected','error':'UNEXPECTED_ANALYSIS_ERROR'})); sys.exit(2)
