"""Native no-Agent circuit development; every trial is retained separately."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
import numpy as np
from bfworld.agentlab.door_system import solver, native
from bfworld.agentlab.door_selfpower.extraction import replace_power
from bfworld.agentlab.simulation_chain.contracts import write_json, file_hash


def run(source, out, topology, ce, inductance, dcr, profile='prototype'):
    if out.exists():
        raise ValueError('RETAINED_PROBE_DIRECTORY_EXISTS')
    out.mkdir(parents=True)
    started = time.time()
    design = json.loads((source/'design-spec.json').read_text())
    rom = json.loads((source/'rom.json').read_text())
    spec = native.solver_spec(design)
    t = np.linspace(0, 6.5, 65001)
    solver.deck(out, spec, rom, source/'force/force-table.npz', t, np.full(len(t), .3e-6))
    text = replace_power((out/'system.cir').read_text(), spec, topology,
                         ce=ce, inductance=inductance, dcr=dcr, profile=profile)
    if topology in ('psshi','sece','sece-floating'):
        text = text.replace('I(Bload)', 'I(Bload) I(L'+('p)' if topology=='psshi' else 'extract)'))
    if topology in ('sece','sece-floating'):
        text=text.replace('I(Bload)','I(Bload) V(rect) V(env) V(base) V(nb) V(lx) V(collector) I(Dtransfer) I(Dblock) I(Denv) I(Dbase)')
    (out/'system.cir').write_text(text)
    write_json(out/'input.json', {'source':str(source), 'design':design, 'topology':topology,
        'ce_F':ce, 'inductance_H':inductance, 'dcr_ohm':dcr, 'device_profile':profile, 'source_rom_sha256':file_hash(source/'rom.json'),
        'source_force_sha256':file_hash(source/'force/force-table.npz'),
        'claim_boundary':'Operator circuit probe with no application loop; not task acceptance or hardware reproduction.'})
    try:
        timepoints, v = solver.native_solve(out, 6.5)
        peak = float(np.max(abs(v['v(q)'])))*1000
        from scipy.integrate import trapezoid
        result = {'status':'completed' if peak<=8. else 'out_of_domain', 'peak_tip_mm':peak,
                  'peak_piezo_V':float(np.max(abs(v['v(pz1,pz2)']))),
                  'peak_vin_V':float(np.max(v['v(vin)'])),
                  'peak_out_V':float(np.max(v['v(out)'])),
                  'port_J':float(trapezoid(v['v(pz1,pz2)']*v['i(vsense)'],timepoints))}
        grid = np.linspace(0,6.5,13001)
        names = ['v(q)','v(u)','v(pz1,pz2)','v(vin)','v(out)','v(pgood)']
        np.savetxt(out/'waveform.csv',np.column_stack([grid]+[np.interp(grid,timepoints,v[k]) for k in names]),
                   delimiter=',',header='time_s,tip_m,velocity_m_s,piezo_V,storage_V,supply_V,pgood_V',comments='')
    except Exception as exc:
        result={'status':getattr(exc,'status','tool_fail'),'error':str(exc)}
    result.update(topology=topology, elapsed_s=time.time()-started, model_calls=0,
                  deck_sha256=file_hash(out/'system.cir'))
    write_json(out/'result.json',result)
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--topology',choices=['d4','seh','psshi','sece','sece-floating'],required=True)
    p.add_argument('--ce',type=float,default=680e-12);p.add_argument('--inductance',type=float,default=1e-3);p.add_argument('--dcr',type=float,default=15.)
    p.add_argument('--profile',choices=['prototype','rated-sece','schottky'],default='prototype')
    a=p.parse_args();run(a.source,a.out,a.topology,a.ce,a.inductance,a.dcr,a.profile)
