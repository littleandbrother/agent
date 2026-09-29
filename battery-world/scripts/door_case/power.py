"""Run genuine vendor LTspice PMIC with source traced to mechanical ROM.

This is explicitly one-way co-simulation. A native pass alone is not sufficient
for coupled mission acceptance. No ideal voltage source is allowed at VIN.
"""
import argparse,hashlib,json,re,subprocess,shutil
from pathlib import Path
import numpy as np

def main():
 p=argparse.ArgumentParser();p.add_argument('case',type=Path);a=p.parse_args();root=a.case
 out=root/'circuit'/'ltspice-D2';out.mkdir(exist_ok=True)
 tool=root.parents[1]/'toolchains/ltspice-26/Package.pkg/Payload/Applications/LTspice.app/Contents/SharedSupport/ltspice'
 model=tool/'support/ltspice/drive_c/users/crossover/AppData/Local/LTspice/lib/sub/LTC3588-1.sub'
 rom=root/'simulation/coupled-D2';params=json.loads((rom/'parameters.json').read_text())
 results={}
 for label,csv in [('nominal','nominal-100000-0.0005.csv'),('weak-slow','weak-slow-100000-0.001.csv'),('no-motion','no-motion-100000-0.001.csv')]:
  d=out/label;d.mkdir(exist_ok=True);data=np.genfromtxt(rom/csv,delimiter=',',names=True)
  np.savetxt(d/'current.pwl',np.column_stack([data['t_s'],params['theta_N_V']*data['velocity_m_s']]),fmt='%.10g')
  shutil.copy2(model,d/'LTC3588-1.sub')
  deck=d/'power.cir';duration=float(data['t_s'][-1])
  deck.write_text(f'''* D2 one-way ROM Norton source, vendor LTC3588-1, zero initial energy
XU1 pz1 pz2 cap vin sw out vin2 vin2 0 pgood 0 LTC3588-1
Ipiezo pz2 pz1 PWL FILE="current.pwl"
Cpiezo pz1 pz2 {params['blocked_capacitance_F']}
Rleak pz2 0 1G
Cstorage vin 0 47u
Ccap vin cap 1u
Cvin2 vin2 0 4.7u
L1 sw out 10u Rser=0.4
Cout out 0 100u Rser=0.02
Roff out 0 10Meg
Bload out 0 I=if(V(pgood)>2.5,0.002,0)
.lib LTC3588-1.sub
.tran 0 {duration} 0 50u uic
.options plotwinsize=0
.save V(vin) V(out) V(pgood) V(pz1,pz2) I(Bload)
.meas TRAN output_peak MAX V(out)
.meas TRAN storage_peak MAX V(vin)
.meas TRAN pgood_peak MAX V(pgood)
.meas TRAN startup WHEN V(out)=3.2 RISE=1
.meas TRAN load_energy INTEG (V(out)*I(Bload)) FROM=0 TO={duration}
.end
''')
  cmd=[str(tool/'bin/wine'),'--enable-alt-loader=macdrv','--bottle','default','--no-gui','--workdir','C:/Program Files/ADI/LTspice','LTspice.exe','-b',str(deck)]
  run=subprocess.run(cmd,stdout=(d/'launcher.log').open('w'),stderr=subprocess.STDOUT,timeout=240)
  log=(d/'power.log').read_text(errors='replace')
  if run.returncode or 'Total elapsed time:' not in log:raise RuntimeError('LTSPICE_INCOMPLETE: '+label)
  r={}
  for key in ['output_peak','storage_peak','pgood_peak','startup','load_energy']:
   pattern=r'^startup:.*?\bAT\s+([-+\d.eE]+)' if key=='startup' else r'^'+key+r':.*?=\s*([-+\d.eE]+)'
   match=re.search(pattern,log,re.M);r[key]=float(match[1]) if match else None
  r['native_raw_sha256']=hashlib.sha256((d/'power.raw').read_bytes()).hexdigest();r['source_csv_sha256']=hashlib.sha256((rom/csv).read_bytes()).hexdigest()
  r['cold_start']=r['startup'] is not None;r['native_solver_completed']=True;results[label]=r;print(label,r,flush=True)
 (out/'report.json').write_text(json.dumps({'engine':'ADI LTspice 26.0.2, native vendor macro-model','model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
  'coupling':'ONE-WAY. Norton current theta*qdot from coupled 100kohm ROM + its Cp. PMIC back-action is not fed back into beam; cannot qualify a positive mission result.',
  'load':'2mA demand when PGOOD>2.5V, an explicit design envelope; not binary-measured MCU energy.',
  'initial_V':0,'cin_uF':47,'cout_uF':100,'vin2_bypass_uF':4.7,'cases':results,'hardware_calibrated':False},indent=2))
if __name__=='__main__':main()
