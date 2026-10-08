"""Isolated E2 analyses. Existing sealed runs and evaluation semantics stay intact.

Resistive ROM controls and uniform-hard-magnet potential are diagnostic model
studies. New native PMIC runs use the same ROM/table and actual C SIL program.
"""
import argparse,copy,csv,hashlib,json,shutil,time
from pathlib import Path
import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import cumulative_trapezoid
from bfworld.agentlab.mechanical_review import ForceTable,control
from bfworld.agentlab.simulation_chain import native,solver

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def csvfile(p,rows):
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def potential(dx,dz,angle=0,br=1.25,n=6,polarity=1):
 """Magnetic interaction energy for the same uniform-charge cuboids, SI units.

 No hysteresis/recoil/steel. Absolute energy gauge is infinity; derivatives are
 meaningful within this nominal model, not a FEM physical confirmation.
 """
 g,w=leggauss(n);yy,zz=np.meshgrid(g,g);ww=np.outer(w,w).ravel()
 tip=np.column_stack([np.zeros(n*n),yy.ravel()*.005,zz.ravel()*.005])
 drv=np.column_stack([np.zeros(n*n),yy.ravel()*.01,zz.ravel()*.01])
 rot=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
 total=0
 for a in (-1,1):
  ta=tip.copy();ta[:,0]=a*.005
  for b in (-1,1):
   db=drv.copy();db[:,0]=b*.01;db=db@rot.T+[dx,0,dz]
   distance=np.linalg.norm(ta[:,None,:]-db[None,:,:],axis=2)
   if (distance<1e-5).any():raise ValueError('MAGNET_CONTACT')
   total+=a*b*np.sum(ww[:,None]*ww[None,:]/distance)
 return polarity*total*native.MU0/(4*np.pi)*(br/native.MU0)**2*.005**2*.01**2

def run(inputs,out,run_native=True):
 inputs,out=Path(inputs),Path(out);out.mkdir(parents=True,exist_ok=True);start=time.time()
 spec=json.loads((inputs/'review/frozen-baseline/design-spec.json').read_text())
 receipt=json.loads((inputs/'review/orientation-v3/receipt.json').read_text())
 sources={}
 for p,expected in receipt['source_files'].items():
  path=Path(p)
  if path.name not in ('rom.json','force-table.npz'):continue
  if sha(path)!=expected:raise ValueError('SEALED_SOURCE_CHANGED')
  target=out/path.name
  if not target.exists():shutil.copyfile(path,target)
  sources[path.name]={'original_path':p,'sha256':sha(target)}
 rom=json.loads((out/'rom.json').read_text());f=np.load(out/'force-table.npz')
 controls=[]
 for polarity in (1,-1):
  table=ForceTable(f['angles'],f['qs'],f['values']*polarity)
  for opening in (.25,2.):
   for resistance in (1e5,1e6,1e7):
    name=f'rom-p{polarity}-t{opening:g}-r{resistance:g}'
    case=copy.deepcopy(spec);case['mechanical']['opening_s']=opening
    path=out/(name+'.json')
    if path.exists():result=json.loads(path.read_text())
    else:
     result,wave=control(rom,table,case,'rotary_path',resistor=resistance)
     np.savetxt(out/(name+'.csv'),wave,delimiter=',',header='time_s,tip_m,velocity_m_s,piezo_V,resistor_J,damping_J,magnetic_work_J,stored_J',comments='')
     result.update(name=name,polarity=polarity,opening_s=opening,resistance_ohm=resistance,operator_assisted=True,product_verified=False)
     dump(path,result)
    controls.append(result);print(name+' '+result['status'],flush=True)
 csvfile(out/'control-summary.csv',[{k:r[k] for k in ('name','polarity','opening_s','resistance_ohm','status','peak_tip_mm','peak_voltage_V','resistor_energy_J','magnetic_work_on_beam_J','damping_loss_J','relative_energy_residual')} for r in controls])
 # Static force and equilibria at all angles. Endpoints are not extrapolated.
 rows=[];eq=[]
 for a,row in zip(f['angles'],f['values']):
  for q,value in zip(f['qs'],row):rows.append({'angle_deg':np.rad2deg(a),'tip_mm':q*1000,'force_N':value})
  for polarity in (1,-1):
   roots=ForceTable(f['angles'],f['qs'],f['values']*polarity).equilibria(a,rom['k'])
   for root in roots:eq.append({'angle_deg':np.rad2deg(a),'polarity':polarity,'q_mm':root['q_m']*1000,'effective_stiffness_N_m':root['effective_stiffness_N_m'],'stable':int(root['stable'])})
 csvfile(out/'force-grid.csv',rows);csvfile(out/'equilibria.csv',eq)
 # A full prescribed closing/holding/opening path with reaction-energy audit.
 # The reaction is derived from the same potential; never call this measured work.
 table=ForceTable(f['angles'],f['qs'],-f['values'])
 cycle,wave=control(rom,table,spec,'close_hold_open')
 times=np.linspace(wave[0,0],wave[-1,0],8001);q=np.interp(times,wave[:,0],wave[:,1]);u=np.interp(times,wave[:,0],wave[:,2])
 opening=spec['mechanical']['opening_s'];amax=np.deg2rad(spec['mechanical']['angle_deg'])
 angles=np.where(times<=opening,amax*(1-times/opening),amax*np.clip((times-opening-.5)/opening,0,1))
 def energy(a,tip):
  dx,dz=native.coordinates(a,spec['mechanical']['gap_mm'])
  return potential(dx,dz-tip,a,polarity=-1)
 energies=np.array([energy(a,tip) for a,tip in zip(angles,q)])
 eps=1e-5
 torque=np.array([-(energy(a+eps,tip)-energy(a-eps,tip))/(2*eps) for a,tip in zip(angles,q)])
 angular_velocity=np.where(times<opening,-amax/opening,np.where(times>opening+.5,amax/opening,0))
 driver_work=cumulative_trapezoid(torque*angular_velocity,times,initial=0)
 beam_force=np.array([-native.force(*np.array(native.coordinates(a,spec['mechanical']['gap_mm']))-[0,tip],a)[2] for a,tip in zip(angles,q)])
 beam_work=cumulative_trapezoid(beam_force*u,times,initial=0)
 residual=energies-energies[0]+driver_work+beam_work
 checks=[]
 for a,tip in [(0,0),(.03,.003),(.13,-.002),(.6,.001)]:
  derived=-(energy(a,tip+1e-7)-energy(a,tip-1e-7))/(2e-7)
  dx,dz=native.coordinates(a,spec['mechanical']['gap_mm']);expected=-native.force(dx,dz-tip,a)[2]
  checks.append({'angle_rad':a,'tip_m':tip,'potential_gradient_N':derived,'force_N':expected,'relative_error':abs(derived-expected)/max(abs(expected),1e-12)})
 if max(c['relative_error'] for c in checks)>1e-4:raise ValueError('POTENTIAL_FORCE_RECIPROCITY_FAILED')
 csvfile(out/'loading-cycle.csv',[{'time_s':t,'angle_deg':np.rad2deg(a),'tip_m':tip,'piezo_V':np.interp(t,wave[:,0],wave[:,3]),'potential_J':e,'driver_work_J':dw,'beam_work_J':bw,'energy_residual_J':r} for t,a,tip,e,dw,bw,r in zip(times,angles,q,energies,driver_work,beam_work,residual)])
 dump(out/'loading-cycle.json',{'model':cycle,'gradient_checks':checks,'sampled_energy_relative_residual':float(max(abs(residual))/max(max(abs(driver_work)),1e-12)),
   'scope':'Nominal uniform-magnet potential and resistive ROM. Prescribed driver reaction work, not measured door input or certified PMIC efficiency.',
   'new_native_solver_calls':0,'physical_qualification':False})
 # Ideal energy needed at threshold includes large capacitors as references.
 csvfile(out/'capacitor-bounds.csv',[{'capacitance_uF':c,'uvlo_3_77_J':.5*c*1e-6*3.77**2,'uvlo_5_05_J':.5*c*1e-6*5.05**2} for c in (10,22,47,100,220,330,1000,2200,4700)])
 native_runs=[]
 if run_native:
  fw=out/'firmware';fw.mkdir(exist_ok=True)
  for p,expected in receipt['source_files'].items():
   if '/firmware/' not in p:continue
   if sha(p)!=expected:raise ValueError('FIRMWARE_SOURCE_CHANGED')
   if not (fw/Path(p).name).exists():shutil.copyfile(p,fw/Path(p).name)
  reversed_path=out/'force-reversed.npz';np.savez(reversed_path,angles=f['angles'],qs=f['qs'],values=-f['values'])
  for cap in (22,47,100,220):
   d=out/f'native-cin-{cap}';d.mkdir(exist_ok=True);candidate=copy.deepcopy(spec);candidate['circuit']['cin_uF']=cap
   if not (d/'receipt.json').exists():
    dump(d/'candidate.json',candidate)
    try:metrics=solver.solve(d,candidate,rom,reversed_path,fw);record={'status':'completed','metrics':metrics}
    except Exception as e:record={'status':getattr(e,'status','failed'),'error':str(e)}
    record.update(candidate_sha256=sha(d/'candidate.json'),source_rom_sha256=sha(out/'rom.json'),source_force_sha256=sha(reversed_path),operator_assisted=True,product_verified=False,scope='Native LTspice PMIC + C SIL; unqualified shared magnetic model; cold cache calculation.')
    dump(d/'receipt.json',record)
   record=json.loads((d/'receipt.json').read_text());native_runs.append({'cin_uF':cap,**record});print('Native '+str(cap)+' '+record['status'],flush=True)
  csvfile(out/'native-cap-summary.csv',[{'cin_uF':r['cin_uF'],'status':r['status'],**{k:r.get('metrics',{}).get(k,0) for k in ('peak_tip_mm','peak_piezo_V','peak_storage_V','peak_supply_V','tx_completed','received_events')}} for r in native_runs])
 result={'schema_version':'bf-door-figure-analysis-v1','sources':sources,'controls':controls,'native_runs':native_runs,'operator_assisted':True,'model_calls':0,'elapsed_s':time.time()-start,
   'limitations':['Resistive controls do not prove PMIC/application behavior.','Uniform-charge potential shares magnetic assumptions; mesh/trajectory sufficiency not established.','Positive initial mechanical preload is explicit; no free-energy inference.','All new studies preserve unknowns and failures; finite controls do not prove global infeasibility.']}
 dump(out/'analysis-receipt.json',result);return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',required=True);p.add_argument('--out',required=True);p.add_argument('--no-native',action='store_true');a=p.parse_args();run(a.inputs,a.out,not a.no_native)
