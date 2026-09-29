"""Generate source-bound engineering figures, tables and a local TeX report."""
import argparse, csv, hashlib, json, re, shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import cairosvg

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    r=a.root;out=r/'report';fig=out/'figures';fig.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
    inputs=[]
    def copy(src,name):
        src=r/src;shutil.copy2(src,fig/name);inputs.append({'source':str(src.relative_to(r)),'sha256':sha(src),'figure':name})
    for src,name in [
        ('animation-D2/installation.png','installation.png'),
        ('animation-D2/mechanism.png','mechanism.png'),
        ('animation-D2/mechanism-door-open.png','open.png'),
        ('simulation/beam-v4/stress.png','stress.png'),
        ('simulation/beam-v4/displacement.png','displacement.png'),
        ('simulation/magnetic-D2-final/field.png','field.png'),
        ('pcb/D2/pcb-combined.png','pcb.png')]:copy(src,name)
    s=r/'pcb/D2/schematic.svg'
    cairosvg.svg2png(url=str(s),write_to=str(r/'pcb/D2/schematic.png'))
    cairosvg.svg2pdf(url=str(s),write_to=str(r/'pcb/D2/schematic.pdf'))
    copy('pcb/D2/schematic.png','schematic.png')
    f,ax=plt.subplots(4,1,figsize=(9,9),sharex=True)
    for fname,label in [('nominal-100000-0.0005.csv','Normal opening / 2 s'),('weak-slow-100000-0.001.csv','Slow opening / 8 s')]:
        src=r/'simulation/coupled-D2'/fname;d=np.genfromtxt(src,delimiter=',',names=True)
        for axis,key,scale in zip(ax,['angle_rad','tip_m','piezo_V','load_J'],[180/np.pi,1e3,1,1e6]):axis.plot(d['t_s'],d[key]*scale,label=label)
        inputs.append({'source':str(src.relative_to(r)),'sha256':sha(src),'figure':'coupled.png'})
    for axis,label in zip(ax,['Door angle (deg)','Tip displacement (mm)','Resistor voltage (V)','Resistor energy (uJ)']):axis.set_ylabel(label);axis.grid(alpha=.2)
    ax[0].legend();ax[-1].set_xlabel('Time (s)');f.tight_layout();f.savefig(fig/'coupled.png');plt.close(f)
    f,ax=plt.subplots(3,1,figsize=(9,7),sharex=True);power={}
    for case in ['nominal','weak-slow','no-motion']:
        src=r/'circuit/ltspice-D2'/case/'power.raw';b=src.read_bytes();marker='Binary:\n'.encode('utf-16le')
        at=b.index(marker)+len(marker);head=b[:at].decode('utf-16le')
        n=int(re.search(r'No. Points:\s*(\d+)',head).group(1));nv=int(re.search(r'No. Variables:\s*(\d+)',head).group(1))
        if nv!=7:raise ValueError('LTSPICE_VARIABLE_ORDER_CHANGED')
        data=np.frombuffer(b,offset=at,count=n,dtype=np.dtype([('time','<f8'),('v','<f4',(nv-1,))]))
        t=np.abs(data['time']);v=data['v'];csvpath=src.with_suffix('.csv')
        np.savetxt(csvpath,np.column_stack([t,v]),delimiter=',',header='time_s,VOUT_V,PGOOD_V,PZ1_V,PZ2_V,VIN_V,Iload_A',comments='')
        power[case]={'VIN_peak_V':float(v[:,4].max()),'VOUT_peak_V':float(v[:,0].max()),'PGOOD_peak_V':float(v[:,1].max()),'startup':bool(np.any(v[:,1]>2.5))}
        for axis,k,scale in zip(ax,[4,0,1],[1,1e6,1]):axis.plot(t,v[:,k]*scale,label=case)
        inputs.append({'source':str(src.relative_to(r)),'sha256':sha(src),'figure':'power.png'})
    for axis,label in zip(ax,['VIN (V)','VOUT (uV)','PGOOD (V)']):axis.set_ylabel(label);axis.grid(alpha=.2)
    ax[0].legend();ax[-1].set_xlabel('Time (s)');f.tight_layout();f.savefig(fig/'power.png');plt.close(f)
    (out/'power-summary.json').write_text(json.dumps(power,indent=2))
    f,ax=plt.subplots(figsize=(10,3.4));ax.axis('off')
    labels=['PGOOD = 0\nSYSTEMOFF','PGOOD rising\nRC clock / stack','PGOOD = 1\nBLE advertising','PGOOD falling\nStop / SYSTEMOFF']
    for i,label in enumerate(labels):
        x=.025+i*.25
        ax.text(x+.1,.65,label,ha='center',va='center',bbox=dict(boxstyle='round,pad=.7',facecolor='#edf2f6',edgecolor='#60758a'),transform=ax.transAxes)
        if i<3:ax.annotate('',xy=(x+.24,.65),xytext=(x+.205,.65),xycoords='axes fraction',arrowprops={'arrowstyle':'->'})
    ax.text(.5,.15,'Control sequence only. 100 ms advertising interval + random delay.\nBoot latency, current, radio reception and brownout behavior are NOT measured.',ha='center',transform=ax.transAxes)
    f.savefig(fig/'firmware-sequence.png',bbox_inches='tight');plt.close(f)
    drawings=[]
    for s in sorted((r/'mechanical-D2/drawings').glob('*.svg')):
        pdf=s.with_suffix('.pdf');cairosvg.svg2pdf(url=str(s),write_to=str(pdf));drawings.append(pdf)
    # Portable .tex references sibling case directories, not a particular user's home.
    template=Path(__file__).with_name('report-template.tex').read_text()
    appendix='\n'.join(r'\includepdf[pages=-,fitpaper=true]{../mechanical-D2/drawings/'+p.name+'}' for p in drawings)
    (out/'door-case.tex').write_text(template.replace('%%DRAWING_APPENDIX%%',appendix))
    (out/'figure-provenance.json').write_text(json.dumps(inputs,indent=2))
    verification={
        'design':'D2','hardware_verified':False,'autonomous_agent_verified':False,
        'overall':'NOT_ACCEPTED_SINGLE_OPENING_COLD_START_FAILED',
        'passed':['CAD solids/readback','rigid sampled motion clearance','ROM timestep energy convergence','no-motion/no-magnet negative controls','independent PCB connectivity and clearance','repeat target firmware binary'],
        'failed':['single-opening PMIC cold start','magnetic force mesh convergence at 5 percent'],
        'not_performed':['native EasyEDA ERC/DRC','hardware calibration','actual flash and radio reception','fatigue and manufacturing qualification','bidirectional PMIC-mechanical co-simulation'],
        'power':power}
    (out/'verification.json').write_text(json.dumps(verification,indent=2))
    print(json.dumps({'report_source':str(out/'door-case.tex'),'drawings':len(drawings),'power':power}))
if __name__=='__main__':main()
