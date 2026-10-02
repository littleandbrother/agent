"""Retained-data reporting only: no force evaluations or integrations."""
from pathlib import Path
import hashlib,json
import numpy as np
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
comp=json.loads((ROOT/'outputs/COMPARISON.json').read_text())
assert comp['all_pass']
fine={cid:comp['cases'][cid][1] for cid in ['cin47','cin10']}
rows={cid:np.load(ROOT/'outputs'/f'{cid}-fine/raw.npz')['sample'] for cid in fine}
plan=json.loads((ROOT/'PLAN.json').read_text())
for cid in fine:
    for resolution in ['coarse','fine']:
        d=ROOT/'outputs'/f'{cid}-{resolution}';seal=json.loads((d/'RUN-SEAL.json').read_text())
        assert all(sha(d/p)==h for p,h in seal['files'].items())
        assert json.loads((d/'REJECTED-EVALUATION.json').read_text()) is None
a,b=[fine[c] for c in ['cin47','cin10']]
ratio_v=b['final_state'][3]/a['final_state'][3];ratio_e=b['final_storage_J']/a['final_storage_J']
summary={'version':comp['version'],'status':'FOUR_CELLS_AND_FROZEN_COMPARISON_GATES_PASS','dynamic_trajectories':4,'completed':4,'rejected_internal_evaluations':0,'final_voltage_ratio_10_over_47':ratio_v,'final_storage_energy_ratio_10_over_47':ratio_e,'sup_fine_path_q_difference_m':float(np.max(abs(rows['cin10'][:,1]-rows['cin47'][:,1]))),'effects':comp['effects'],'costs':{'new_study_wall_s':sum(s['wall_s'] for ss in comp['cases'].values() for s in ss),'new_study_rhs_calls':sum(s['rhs_evaluations'] for ss in comp['cases'].values() for s in ss),'new_study_force_calls':sum(s['force_evaluations'] for ss in comp['cases'].values() for s in ss),'predecessor_attempted':1,'predecessor_completed':0,'predecessor_unrun':3,'predecessor_run_wall_s':28.77879858900269,'preflight_suite_provider_calls':16,'preflight_suite_new_derivative_calls':12},'fine_energy_ledgers_J':{},'independent_post_run_review':'pending at report generation; final receipt binds independent outcome','claim':'conditional numerical passive source/storage sensitivity only; assumed q-only path'}
for cid,s in fine.items():
    initial=s['initial_components_J'];final=s['final_components_J'];state=s['final_state']
    summary['fine_energy_ledgers_J'][cid]={'initial_kinetic':initial[0],'initial_elastic':initial[1],'initial_piezo':initial[2],'initial_storage':initial[3],'initial_mutual_magnetic':initial[4],'driver_translation':state[6],'driver_rotation':state[7],'driver_total':sum(state[6:8]),'damping_loss':state[4],'benchmark_resistor_loss':state[5],'final_kinetic':final[0],'final_elastic':final[1],'final_piezo':final[2],'final_storage':final[3],'final_mutual_magnetic':final[4],'final_balance_residual':sum(final)-sum(initial)+sum(state[4:6])-sum(state[6:8]),'max_balance_residual':s['max_energy_residual_J'],'independent_Simpson_minus_ODE':s['independent_simpson_minus_ode_ledger_J']}
(ROOT/'reports/RESULT-SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
review_path=Path('/workspace/shared/passive-jacobian-independent-review-20261001/post-run/reports/comparison-readback.json')
review=json.loads(review_path.read_text());assert review['status']=='FOUR_CELL_RETAINED_COMPARISON_AUDIT_PASS'
summary['independent_post_run_review']={'status':review['status'],'path':str(review_path),'sha256':sha(review_path),'reviewer_new_force_calls':0,'reviewer_new_time_integrations':0}
summary['cohort_accounting']={'across_versions_attempted':5,'across_versions_completed':4,'across_versions_stopped':1,'original_cohort':{'planned':4,'attempted':1,'completed':0,'stopped':1,'unrun':3},'repaired_cohort':{'planned':4,'attempted':4,'completed':4,'stopped':0,'unrun':0},'unrun_slots_are_not_attempts':True}
(ROOT/'reports/RESULT-SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')

energy_lines=[]
for label,key in [('Initial elastic','initial_elastic'),('Initial mutual magnetic (signed)','initial_mutual_magnetic'),('Initial kinetic / piezo / storage','initial_kinetic'),('Driver translational work','driver_translation'),('Driver rotational work','driver_rotation'),('Driver total work','driver_total'),('Damping loss','damping_loss'),('Benchmark resistor loss','benchmark_resistor_loss'),('Final storage capacitor','final_storage'),('Final mutual magnetic (signed)','final_mutual_magnetic'),('Final kinetic','final_kinetic'),('Final beam elastic','final_elastic'),('Final piezo','final_piezo'),('Final balance residual','final_balance_residual')]:
    vals=[summary['fine_energy_ledgers_J'][c][key]*1e6 for c in ['cin47','cin10']]
    energy_lines.append(f'| {label} | {vals[0]:.9g} | {vals[1]:.9g} |')
cell_lines=[]
for cid in ['cin47','cin10']:
    for s in comp['cases'][cid]:
        cell_lines.append(f"| {cid} {s['resolution']} | {s['final_state'][3]:.9f} | {s['final_storage_J']*1e6:.9f} | {s['max_energy_residual_J']:.3g} | {s['wall_s']:.3f} |")
report='''# Conditional passive source/storage result

## Finding

All four prospective trajectories completed 4 s and passed the frozen trajectory, energy, domain, force-quadrature, Jacobian and time-refinement checks. With the fixed ideal-bridge/100 kΩ benchmark, reducing Cin from 47 to 10 µF raised final storage voltage from **0.142364316 V to 0.591839203 V** and final capacitor energy from **0.476288565 µJ to 1.751368211 µJ**.

The voltage ratio is **4.157216×** and stored-energy ratio **3.677116×**. Both predeclared effect-resolution tests pass: the 1.275079646 µJ storage-energy difference is compared with an observed coarse/fine-delta sum of 0.00000123914 µJ; the 0.449474887 V peak-voltage difference is compared with 2.08219e−7 V. These are empirical resolution checks, not statistical confidence intervals or rigorous error bounds.

This is a conditional result on the fixed assumed q-only path. It does not establish an optimal capacitance, real rectifier performance, native PMIC startup, a mission outcome or device feasibility.

## Four cells

| Case | Final Vs (V) | Final capacitor energy (µJ) | Max energy residual (J) | Wall time (s) |
|---|---:|---:|---:|---:|
'''+ '\n'.join(cell_lines)+'''

The two fine trajectories differ in q by up to 27.47665 µm on the common sampled path. Thus the circuit intervention is coupled back into mechanical motion; it is not a postprocessed capacitor charging calculation. All raw states, dense polynomial segments, primitive forces/torques, driver pose derivatives and energy/work rates are retained.

## Complete fine-resolution energy ledger

All numbers below are µJ. Signed mutual potential uses the source's zero-at-infinite-separation convention. Both cases begin at the same stable closed-door q0=−5.838454977 mm, qdot=0, Vp=Vs=0, Q0=theta*q0. The dynamic ledger uses the order-6 mutual potential; its tiny difference from the order-10 static initializer is retained rather than hidden.

| Energy term | 47 µF | 10 µF |
|---|---:|---:|
'''+ '\n'.join(energy_lines)+'''

The balance is final stored energy minus initial stored energy, plus damping and resistor losses, minus signed translational and rotational driver work. A separate composite-Simpson calculation using retained primitive powers reproduces the ODE work/loss integrals; its largest fine-run discrepancy is 4.45e−12 J. The maximum trajectory ledger residual is below 3.68e−11 J over all four cells.

Much of the prescribed-driver work raises the mutual magnetic potential as the magnets separate. Initial beam elastic energy is also released. The initial mechanical/magnetic preparation is explicit; its physical preparation/reset procedure and cost remain unqualified. Driver mechanism inertia/friction are outside the specified magnetic-work boundary.

## Numerical evidence and retained failure

Both time resolutions use the same order-6 direct force model. Independent order-10 checks at every accepted interval start/midpoint/end cover 48,342 retained path samples across four trajectories. The largest force, potential and driver-angle-potential-derivative differences are about 4.590e−10 N, 2.017e−12 J and 3.548e−10 J/rad. These are numerical refinements, not physical magnetic validation.

Every Jacobian call retains bounded h/h2 magnetic derivatives; the 946 derivative checks pass. All four rejected-evaluation files are null. The smallest conservative continuous numerical-path magnet separation bound is about 32.731 mm. This applies to the two magnets and the numerical cubic path, not a complete assembly or a physical safety limit.

The preceding automatic-Jacobian study is preserved separately: one attempt stopped at 1.06700226 s, the remaining three cells were unrun, and no comparison was admitted. Its failure occurred during an internal finite-difference probe; the exact rejected voltage was not retained. A synthetic algebraic demonstration reproduced the mechanism but was not a replay of that unknown value. The separately reviewed structured-Jacobian repair retained physical parameters and original thresholds, and then received fresh authorization for these four cells.

Across both versions there were **five attempted trajectories: four completed and one stopped**. The original cohort's three unrun slots were never attempted; they are not part of the repaired cohort, which completed all four of its separately authorized cells.

New-study execution cost is 344.675 s, 138,180 RHS calls and 197,580 direct force calls across the four bounded cells. Every per-cell budget and the 1,800 s overall cap passed. The 30-test preflight used 16 provider calls: 12 new bounded derivative calls plus four repeated static controls. Earlier stopped-run and preparation costs remain separately visible; no scientific retry was hidden.

## Smallest next decision

Keep 47 µF as the control and carry 10 µF forward as one explicitly conditional candidate. The fixed pair already establishes the model's storage sensitivity; it does not justify an automatic capacitance sweep or selecting a product design. The next useful decision is to require a verified real circuit/PMIC port and source-model applicability evidence before using this pair to ask a startup or mission question.

What is feasible here is complete retained-data verification, transparent source/initial-state accounting and reproducible delivery of this conditional comparison; those steps are done. The next native question is blocked on actual PZT tensor/ROM provenance and applicability, a verified native PMIC pin/port binding with rail/current/auxiliary-store evidence, and a defensible physical initial-state/reset and load model. Those facts require the corresponding native artifacts or measurements. They cannot be supplied by more runs of this passive benchmark. No new sweep or scientific trajectory is needed to package the present result.

The passive resistor benchmark is not a proven upper bound on the real feedback-coupled device. Comparing these µJ values with an LTC rail-capacitor energy would not by itself establish impossibility or predict startup because the actual circuit and load alter the coupled trajectory. No such threshold claim is made here.

The conditional material, uncalibrated zeta=.02, one-coordinate truncation, omitted force/voltage-dependent axial motion and bending modes, and physical equilibrium/reset unknowns remain. Numerical agreement cannot remove these assumptions. Independent retained-data review is recorded separately and bound by the final receipt.
'''
(ROOT/'reports/RESULT.md').write_text(report)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(11,7),sharex=True)
    for cid,color in [('cin47','#3366AA'),('cin10','#CB7028')]:
        data=rows[cid];t=data[:,0];q=data[:,1];vp=(data[:,3]-plan['mechanics']['theta_C_m']*q)/plan['mechanics']['Cp_ritz_F'];vs=data[:,4];cin=next(c['cin_F'] for c in plan['cases'] if c['id']==cid)
        label='47 µF' if cid=='cin47' else '10 µF'
        for ax,val in zip(axes.flat,[q*1e3,vp,vs,.5*cin*vs*vs*1e6]):ax.plot(t,val,label=label,color=color,lw=1.3)
    for ax,title,ylabel in zip(axes.flat,['Mechanical response','Piezo terminal voltage','Storage voltage','Storage capacitor energy'],['q (mm)','Vp (V)','Vs (V)','Energy (µJ)']):
        ax.set_title(title,loc='left',fontsize=11);ax.set_ylabel(ylabel);ax.grid(alpha=.2);ax.axvline(2,color='#777777',ls=':',lw=.8);ax.set_xlim(0,4)
    axes[1,0].set_xlabel('Time (s)');axes[1,1].set_xlabel('Time (s)');axes[0,0].legend(loc='lower right',frameon=False)
    fig.suptitle('Conditional passive storage comparison • fine-resolution trajectories',fontsize=15)
    fig.text(.5,.02,'Assumed q-only source · ideal bridge +100 kΩ · ζ=0.02 · 65° /2 s · no native-PMIC or hardware claim',ha='center',fontsize=9,color='#555555')
    fig.tight_layout(rect=[0,.04,1,.94]);fig.savefig(ROOT/'reports/TRAJECTORIES.png',dpi=180);plt.close(fig)
except ImportError:
    pass
print(json.dumps(summary,indent=2))
