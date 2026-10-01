"""Saved-data illustration only; no model solve or production-code import."""
from pathlib import Path
import hashlib,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];D=R/'passive-source-storage-jacobian-20261001';O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
raw={c:np.load(D/'outputs'/f'{c}-fine/raw.npz')['sample'] for c in ['cin47','cin10']}
s=json.loads((D/'reports/RESULT-SUMMARY.json').read_text());l=s['fine_energy_ledgers_J'];assert np.array_equal(raw['cin47'][:,0],raw['cin10'][:,0]);t=raw['cin47'][:,0];dq=1e6*(raw['cin10'][:,1]-raw['cin47'][:,1])
np.savetxt(O/'traces.csv',np.column_stack([t,raw['cin47'][:,4],raw['cin10'][:,4],dq]),delimiter=',',header='t_s,Vs47_V,Vs10_V,q10_minus_q47_um',comments='',fmt='%.17g')
(O/'ledger.json').write_text(json.dumps(l,indent=2)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.spines.top':False,'axes.spines.right':False})
fig=plt.figure(figsize=(13,12),facecolor='white');gs=fig.add_gridspec(2,2,height_ratios=[1,1.65],left=.07,right=.96,top=.84,bottom=.10,hspace=.31,wspace=.28)
ax=fig.add_subplot(gs[0,0]);colors=['#24598c','#b75129']
for c,label,color in zip(['cin47','cin10'],['47 µF','10 µF'],colors):ax.plot(t,raw[c][:,4],label=label,color=color,lw=2)
ax.set(title='A  Storage voltage, fine traces',xlabel='Time (s)',ylabel='Storage voltage (V)',xlim=(0,4),ylim=(0,.65));ax.grid(alpha=.16);ax.legend(frameon=False,loc='center right');ax.axvline(2,color='#666',lw=.8,ls=':');ax.text(3.9,.601,'0.591839203 V',ha='right',color=colors[1],fontsize=11);ax.text(3.9,.156,'0.142364316 V',ha='right',color=colors[0],fontsize=11)
ax=fig.add_subplot(gs[0,1]);ax.plot(t,dq,color='#49586b',lw=1.2);ax.set(title='B  Coupled mechanical response difference',xlabel='Time (s)',ylabel='q(10 µF) − q(47 µF) (µm)',xlim=(0,4));ax.grid(alpha=.16);ax.axvline(2,color='#666',lw=.8,ls=':');ax.text(.98,.92,f'Max |difference| = {max(abs(dq)):.5f} µm',transform=ax.transAxes,ha='right',fontsize=11)
ax=fig.add_subplot(gs[1,:]);ax.axis('off');ax.set_title('C  Fine-run energy / loss ledger (all values in µJ)',loc='left',pad=14)
items=[('Initial beam elastic','initial_elastic'),('Initial mutual magnetic (signed)','initial_mutual_magnetic'),('Initial kinetic / piezo / storage',None),('Driver translation work (signed)','driver_translation'),('Driver rotation work (signed)','driver_rotation'),('Driver total work (signed)','driver_total'),('Mechanical damping loss','damping_loss'),('100 kΩ resistor loss','benchmark_resistor_loss'),('Final storage capacitor','final_storage'),('Final mutual magnetic (signed)','final_mutual_magnetic'),('Final kinetic','final_kinetic'),('Final beam elastic','final_elastic'),('Final piezo','final_piezo'),('Final balance residual','final_balance_residual')]
rows=[]
for name,key in items:rows.append([name,*[('0' if key is None else f'{l[c][key]*1e6:+.9g}' if key in ['initial_mutual_magnetic','driver_translation','driver_rotation','driver_total','final_mutual_magnetic','final_balance_residual'] else f'{l[c][key]*1e6:.9g}') for c in ['cin47','cin10']]])
tab=ax.table(cellText=rows,colLabels=['Energy term (µJ)','47 µF','10 µF'],cellLoc='right',colLoc='right',colWidths=[.52,.24,.24],bbox=[0,0,1,.99]);tab.auto_set_font_size(False);tab.set_fontsize(11.5)
for (i,j),cell in tab.get_celld().items():
 cell.set_edgecolor('#dde1e5');cell.set_linewidth(.4)
 if j==0:cell.get_text().set_ha('left')
 if i==0:cell.set_facecolor('#eaf0f6');cell.get_text().set_weight('bold')
 elif i in [2,9]:cell.set_facecolor('#f2f5f8');cell.get_text().set_weight('bold')
fig.text(.07,.95,'Conditional passive storage comparison',fontsize=22,weight='medium')
fig.text(.07,.91,'Ideal full-wave bridge + fixed 100 kΩ benchmark · uncalibrated ζ = 0.02 · assumed q-only ROM',fontsize=12)
fig.text(.07,.878,'Same prescribed driver angle: 0→65° over 2 s, then hold to 4 s. External work differs between cases.',fontsize=11,color='#444')
fig.text(.07,.065,'Balance: E(final) − E(initial) + damping + resistor loss − translation work − rotation work = residual.',fontsize=11)
fig.text(.07,.041,'Mutual magnetic zero is at infinite separation. Initial preparation / reset and driver inertia / friction are unqualified.',fontsize=10.5,color='#444')
fig.text(.07,.019,'Saved-data illustration only; raw numerical reports are authoritative. No PMIC, startup, real-device bound or Agent-benefit claim.',fontsize=10.2,color='#444')
fig.savefig(O/'PASSIVE-COMPARISON.png',dpi=160);plt.close(fig)
bind={'source_files':{str(p.relative_to(R)):sha(p) for p in [D/'outputs/cin47-fine/raw.npz',D/'outputs/cin10-fine/raw.npz',D/'reports/RESULT-SUMMARY.json',Path(__file__).resolve()]},'output_files':{p.name:sha(p) for p in [O/'traces.csv',O/'ledger.json',O/'PASSIVE-COMPARISON.png']},'new_solves':0,'source_reports_authoritative':True,'identical_external_work_claim':False}
(O/'FIGURE-BINDINGS.json').write_text(json.dumps(bind,indent=2)+'\n')
