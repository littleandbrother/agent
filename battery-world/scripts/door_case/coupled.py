"""Dimension-bound magnet/beam ROM; explicit numerical and physical claim limits."""
import argparse, json, csv, math, hashlib
from pathlib import Path
import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import solve_ivp, cumulative_trapezoid
from scipy.optimize import brentq
from scipy.interpolate import RegularGridInterpolator

MU0=4e-7*np.pi
def force(dx,dz,angle=0,n=6):
    """Coulomb surface charge of two uniformly magnetized finite cuboids, SI.
    Returns force on tip. Ideal hard magnets, recoil permeability unity.
    Both pole faces are integrated; no point-dipole approximation.
    """
    g,w=leggauss(n); yy,zz=np.meshgrid(g,g); ww=np.outer(w,w).ravel()
    tip=np.column_stack([np.zeros(n*n),yy.ravel()*.005,zz.ravel()*.005])
    drv=np.column_stack([np.zeros(n*n),yy.ravel()*.01,zz.ravel()*.01])
    R=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
    ans=np.zeros(3)
    for a in [-1,1]:
      ta=tip.copy();ta[:,0]=a*.005
      for b in [-1,1]:
        db=drv.copy();db[:,0]=b*.01;db=db@R.T+np.array([dx,0,dz])
        r=ta[:,None,:]-db[None,:,:]; r3=np.linalg.norm(r,axis=2)**3
        ans+=a*b*np.sum((ww[:,None]*ww[None,:]/r3)[:,:,None]*r,axis=(0,1))
    return ans*MU0/(4*np.pi)*(1.25/MU0)**2*.005**2*.01**2

def main():
    p=argparse.ArgumentParser();p.add_argument('case',type=Path);a=p.parse_args();root=a.case
    out=root/'simulation'/'coupled-D2';out.mkdir(exist_ok=True)
    k=.3/.0034403062781818306; f=15.9152427488183; mass=k/(2*np.pi*f)**2
    theta=k*2.4862056721220446e-6; cp=1.7773565412243214e-8-theta**2/k
    params=dict(k_N_m=k,modal_mass_kg=mass,f_Hz=f,theta_N_V=theta,blocked_capacitance_F=cp,
      zeta=.02,source='COMSOL beam-v4, mesh 3, static force / 1V reciprocity / first bending eigenmode',
      validity='small-deflection single-mode ROM; constant magnetization; ideal finite cuboid force; damping assumed, no hardware calibration')
    (out/'parameters.json').write_text(json.dumps(params,indent=2))
    checks=[]
    for dx,dz in [(.048,0),(.048,.02),(.048,.03),(.026,.015)]:
      vals=[force(dx,dz,n=n) for n in [4,6,8,12]]
      checks.append({'dx_m':dx,'dz_m':dz,'force_N':[v.tolist() for v in vals],'quadrature':[4,6,8,12],
        'relative_delta_8_12':float(np.linalg.norm(vals[-1]-vals[-2])/np.linalg.norm(vals[-1]))})
    (out/'force-quadrature.json').write_text(json.dumps(checks,indent=2))
    allresults={}
    for label,opening,scale,zeta in [('nominal',2,1,.02),('weak-slow',8,1,.02),('high-damping',2,1,.05),('no-motion',0,1,.02),('no-magnet',2,0,.02)]:
      duration=opening+2 if opening else 4
      angles=np.linspace(0,np.deg2rad(65),181); qgrid=np.linspace(-.012,.012,49)
      grid=np.empty((len(angles),len(qgrid)))
      for i,ang in enumerate(angles):
        dx=(1004-(856*np.cos(ang)-45*np.sin(ang))-100)/1000
        dz=(856*np.sin(ang)+45*np.cos(ang)-70-5.265)/1000
        for j,q in enumerate(qgrid):grid[i,j]=force(dx,dz-q,ang)[2]*scale
      interp=RegularGridInterpolator((angles,qgrid),grid,bounds_error=False,fill_value=None)
      def F(ang,q):return float(interp([[ang,q]])[0])
      q0=brentq(lambda q:k*q-F(0,q),-.012,.012) if scale else 0
      damp=2*zeta*np.sqrt(k*mass)
      # Passive resistor is a reproducible electrical load, not a PMIC substitute.
      for resistance in ([100000,1000000] if label=='nominal' else [100000]):
       for dt in ([.001,.0005] if label=='nominal' and resistance==100000 else [.001]):
        def rhs(t,y):
          q,vel,v=y;ang=min(t/opening,1)*np.deg2rad(65) if opening else 0
          return [vel,(F(ang,q)-k*q-damp*vel-theta*v)/mass,(theta*vel-v/resistance)/cp]
        ts=np.arange(0,duration+dt/2,dt)
        sol=solve_ivp(rhs,[0,duration],[q0,0,0],t_eval=ts,method='Radau',max_step=dt,rtol=1e-7,atol=1e-10)
        if not sol.success:raise RuntimeError(sol.message)
        q,vel,v=sol.y;angle=np.minimum(ts/opening,1)*np.deg2rad(65) if opening else np.zeros_like(ts)
        forces=np.array([F(ang,qq) for ang,qq in zip(angle,q)])
        load=cumulative_trapezoid(v*v/resistance,ts,initial=0);diss=cumulative_trapezoid(damp*vel*vel,ts,initial=0)
        work=cumulative_trapezoid(forces*vel,ts,initial=0);stored=.5*mass*vel*vel+.5*k*q*q+.5*cp*v*v
        resid=stored-stored[0]+load+diss-work
        name=f'{label}-{resistance}-{dt:g}'
        np.savetxt(out/(name+'.csv'),np.column_stack([ts,angle,q,vel,v,forces,load,diss,work,stored,resid]),delimiter=',',
          header='t_s,angle_rad,tip_m,velocity_m_s,piezo_V,force_N,load_J,damping_J,force_work_J,stored_J,residual_J',comments='')
        allresults[name]={'initial_static_tip_mm':q0*1000,'peak_tip_mm':float(np.max(np.abs(q))*1000),'peak_voltage_V':float(np.max(np.abs(v))),
          'resistor_energy_uJ':float(load[-1]*1e6),'max_energy_residual_J':float(max(abs(resid))),
          'relative_energy_residual':float(max(abs(resid))/max(max(abs(work)),stored[0],1e-12)),
          'within_8mm_ROM_limit':bool(max(abs(q))<=.008),'PMIC_cold_start_proven':False}
        if label=='nominal' and resistance==100000 and dt==.0005:
          np.savetxt(out/'piezo-current.pwl',np.column_stack([ts,theta*vel]),fmt='%.10g')
          np.savetxt(out/'door-force.pwl',np.column_stack([ts,forces]),fmt='%.10g')
    (out/'report.json').write_text(json.dumps({'cases':allresults,'claim':'Load-dependent ROM, not measured calibration; force_work includes work from prescribed magnet trajectory; initial closed-door preload explicitly counted.'},indent=2));print(json.dumps(allresults),flush=True)
if __name__=='__main__':main()
