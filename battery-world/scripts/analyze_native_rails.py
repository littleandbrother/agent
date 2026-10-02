#!/usr/bin/env python3
"""Independent new readback of retained RAW; does not replace failed receipts."""
import argparse
import importlib.util
import json
import re
from pathlib import Path
import numpy as np
from scipy.integrate import trapezoid
from bfworld.agentlab.simulation_chain import solver
from bfworld.agentlab.simulation_chain.contracts import write_json, file_hash


def refinement_identity(coarse_deck, fine_deck):
    def step(text):
        m=re.search(r'(?m)^\.tran\s+\S+\s+\S+\s+\S+\s+(\S+)',text)
        return float(m[1]) if m else None
    a,b=step(coarse_deck),step(fine_deck)
    valid=a is not None and b is not None and np.isclose(b,a/2,rtol=1e-12,atol=0)
    return {'coarse_max_step_s':a,'fine_max_step_s':b,
        'refinement_admitted':bool(valid),
        'reason':None if valid else 'MAX_STEP_NOT_HALVED; matching waveforms do not prove refinement'}


def analyze(root, evaluator, output=None, reference=None):
    output = output or root/'reviewed-readback'
    if output.exists(): raise ValueError('READBACK_ALREADY_EXISTS')
    output.mkdir()
    spec = importlib.util.spec_from_file_location('frozen_settling', evaluator)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    request = json.loads((root/'request.json').read_text())
    criteria = request['settling']; results = []; waves = {}
    for name in request['fixtures']:
        directory = root/name
        log = (directory/'system.log').read_text(errors='replace')
        if 'Total elapsed time:' not in log:
            results.append({'id': name, 'status': 'native_incomplete'}); continue
        t, v = solver.read_raw(directory/'system.raw', 4)
        rows = {'time_s': t, 'vin_V': v['v(vin)'], 'cap_V': v['v(cap)'],
            'vin2_V': v['v(vin2)'], 'icap_A': v['i(ccap)'], 'ivin2_A': v['i(cvin2)'],
            'source_connected': (v['v(control)'] > .5).astype(float) if 'v(control)' in v else np.zeros(len(t)),
            'out_V': v['v(out)'], 'pgood_V': v['v(pgood)']}
        for name2 in ('v(drive)', 'i(vdrive)', 'i(vpmicvin)', 'i(vpmicout)'):
            if name2 in v: rows[name2] = v[name2]
        cap_gap = rows['vin_V']-rows['cap_V']; rows['cap_gap_V'] = cap_gap
        target = output/(name+'.csv')
        np.savetxt(target, np.column_stack(list(rows.values())), delimiter=',', header=','.join(rows), comments='', fmt='%.12g')
        params = {**criteria, 'phase': 'source_off' if rows['source_connected'][-1]==0 else 'source_on'}
        settling = module.evaluate(rows, params)
        energies = {}
        for label, voltage, current, capacitance in [('CAP',cap_gap,v['i(ccap)'],1e-6),('VIN2',v['v(vin2)'],v['i(cvin2)'],4.7e-6)]:
            energy = .5*capacitance*voltage**2
            work = float(trapezoid(voltage*current,t))
            energies[label] = {'initial_J':float(energy[0]),'final_J':float(energy[-1]),
                'signed_work_J':work,'balance_residual_J':float(energy[-1]-energy[0]-work)}
        result = {'id':name, 'status':'raw_readback_completed', 'raw_sha256':file_hash(directory/'system.raw'),
            'original_attempt_receipt_sha256':file_hash(directory/'receipt.json'),
            'csv_sha256':file_hash(target), 'samples':len(t), 'saved_variables':sorted(v),
            'peak_vin_V':float(max(v['v(vin)'])), 'peak_out_V':float(max(v['v(out)'])),
            'terminal_vin_V':float(v['v(vin)'][-1]), 'rail_energy':energies, 'settling':settling,
            'source_work_J':float(trapezoid(-v['v(drive)']*v['i(vdrive)'],t)) if 'v(drive)' in v else None,
            'diagnostic_only':not name.startswith('baseline'), 'self_powered_success':False}
        results.append(result); waves[name]=(t,v)
    refinement=[]
    if reference:
        t,v=solver.read_raw(reference/'baseline-observation/system.raw',4)
        waves['baseline-observation']=(t,v)
    for coarse, fine in [('baseline-observation','baseline-fine'),('charge-disconnect','charge-disconnect-fine')]:
        if coarse in waves and fine in waves:
            ta,a=waves[coarse];tb,b=waves[fine]
            coarse_directory=(reference if reference and coarse=='baseline-observation' else root)/coarse
            identity=refinement_identity((coarse_directory/'system.cir').read_text(),(root/fine/'system.cir').read_text())
            refinement.append({'coarse':coarse,'fine':fine,**identity,
                'coarse_deck_sha256':file_hash(coarse_directory/'system.cir'),
                'fine_deck_sha256':file_hash(root/fine/'system.cir'),
                'coarse_raw_sha256':file_hash(coarse_directory/'system.raw'),
                'fine_raw_sha256':file_hash(root/fine/'system.raw'),
                'max_normalized_difference':{
                k:float(np.max(abs(a[k]-np.interp(ta,tb,b[k])))/max(np.max(abs(b[k])),1e-6))
                for k in ('v(vin)','v(out)','v(vin2)','v(cap)')}})
    receipt={'schema_version':'native-rail-reviewed-readback-v1','request_sha256':file_hash(root/'request.json'),
        'evaluator_sha256':file_hash(evaluator),'reader_sha256':file_hash(Path(solver.__file__)),
        'fixtures':results,'step_refinement':refinement,'original_receipts_unchanged':True,
        'scope':'Native voltage/current observations; external diagnostic power cannot establish self-powered product success.'}
    write_json(output/'receipt.json',receipt)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes=plt.subplots(3,1,figsize=(9,8),sharex=True)
    for name in waves:
        if name not in waves: continue
        t,v=waves[name];stride=max(1,len(t)//2500)
        for ax,key in zip(axes,('v(vin)','v(vin2)','v(out)')):
            ax.plot(t[::stride],v[key][::stride],label=name,linewidth=1)
            ax.set_ylabel(key+' [V]'); ax.grid(alpha=.15)
    axes[0].legend(fontsize=8);axes[-1].set_xlabel('Native simulation time [s]');fig.tight_layout()
    fig.savefig(output/'rails.svg');fig.savefig(output/'rails.png',dpi=150);plt.close(fig)
    print(json.dumps({'fixtures':len(results),'completed':len(waves),'output':str(output),'self_powered_success':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--evaluator',type=Path,required=True)
    p.add_argument('--output',type=Path);p.add_argument('--reference',type=Path)
    a=p.parse_args();analyze(a.root,a.evaluator,a.output,a.reference)
