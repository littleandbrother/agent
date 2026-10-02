"""Native model builders. Source, tool identity and raw outputs are retained."""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
import numpy as np
from numpy.polynomial.legendre import leggauss
from .contracts import ChainError,file_hash,write_json
from ..runtime_config import REPO,HOME_ROOT,COMSOL,CAD,GCC

LTROOT=HOME_ROOT/'toolchains/ltspice-26/Package.pkg/Payload/Applications/LTspice.app/Contents/SharedSupport/ltspice'
WINE=LTROOT/'bin/wine'
PMIC=LTROOT/'support/ltspice/drive_c/users/crossover/AppData/Local/LTspice/lib/sub/LTC3588-1.sub'

def command(argv,directory,name,timeout=240):
    try:
        with (directory/(name+'.log')).open('w') as log:
            p=subprocess.run([str(v) for v in argv],cwd=directory,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        if p.returncode:raise ChainError('tool_fail',name+' exited '+str(p.returncode))
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ChainError('tool_fail',name+': '+str(exc)) from exc

def comsol(source,directory):
    java=directory/source.name;java.write_text(source.read_text().replace('__OUTPUT__',str(directory)))
    return solve_java(java,directory)

def solve_java(java,directory):
    command([COMSOL,'compile',java],directory,'compile',120)
    command([COMSOL,'-np','2','batch','-inputfile',java.with_suffix('.class'),
             '-outputfile',directory/'model.mph','-batchlog',directory/'solver.log'],directory,'solve',1200)
    log=(directory/'solve.log').read_text(errors='replace')
    if 'BF_COMPLETE' not in log or not list(directory.glob('*.mph')):
        raise ChainError('tool_fail','COMSOL did not finish native model')
    return log

def beam(directory):
    log=comsol(REPO/'configs/reference_cases/door-magnetic-v1/DoorBeam.java',directory)
    rows={}
    for line in log.splitlines():
        if line.startswith('BF_DATA,'):
            a=line.split(',');rows.setdefault(a[1],[]).append([float(x) for x in a[2:]])
    k=.3/rows['tip3'][0][0];f=rows['eigen'][0][0]
    theta=-k*rows['actuation'][0][0];cp=rows['actuation'][0][1]-theta**2/k
    if min(k,f,theta,cp)<=0:raise ChainError('numerical_fail','Non-passive ROM extraction')
    value={'k':k,'mass':k/(2*np.pi*f)**2,'frequency_Hz':f,'theta':theta,'cp':cp,
           'mesh_delta':abs(rows['tip3'][0][0]-rows['tip4'][0][0])/rows['tip3'][0][0],
           'scope':'static-condensed first-mode ROM; PZT-5A perfect bond; small deflection <=8mm; no contact/fatigue',
           'calibration':'fresh native COMSOL stiffness/eigen/reciprocal actuation; not hardware calibration'}
    write_json(directory/'rom.json',value);return value

def cad(directory,gap):
    design=json.loads((REPO/'configs/reference_cases/door-magnetic-v1/design.json').read_text())
    design['revision']='D2-closed-simulation';design['magnets']['nominal_center_separation_x_mm']=gap
    design['door']['driver_closed_world_mm'][0]=904-gap
    write_json(directory/'source-design.json',design)
    command([CAD,REPO/'scripts/door_case/build_cad.py',directory,'--design',directory/'source-design.json'],directory,'cad',300)
    data=json.loads((directory/'input.json').read_text())['assembly']['payload']
    centers={p['id']:p['geometry']['center_mm'] for p in data['parts']}
    actual=centers['driver_magnet'][0]-centers['tip_magnet'][0]
    if abs(actual-gap)>1e-8:raise ChainError('input_error','CAD / magnetic coordinates disagree')
    return {'gap_mm':actual,'parts':len(data['parts']),'step_sha256':file_hash(directory/'assembly.step') if (directory/'assembly.step').exists() else None,
            'driver_closed_world_mm':design['door']['driver_closed_world_mm'],'tip_center_mm':centers['tip_magnet'],
            'scope':'native CAD/readback; dynamic clearance and manufacturing release not certified'}

MU0=4e-7*np.pi
def force(dx,dz,angle=0,br=1.25,n=6):
    """Finite cuboids, uniform hard magnetization, recoil permeability exactly one."""
    g,w=leggauss(n);yy,zz=np.meshgrid(g,g);ww=np.outer(w,w).ravel()
    tip=np.column_stack([np.zeros(n*n),yy.ravel()*.005,zz.ravel()*.005])
    drv=np.column_stack([np.zeros(n*n),yy.ravel()*.01,zz.ravel()*.01])
    rot=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
    ans=np.zeros(3)
    for a in (-1,1):
        ta=tip.copy();ta[:,0]=a*.005
        for b in (-1,1):
            db=drv.copy();db[:,0]=b*.01;db=db@rot.T+[dx,0,dz]
            r=ta[:,None,:]-db[None,:,:];r3=np.linalg.norm(r,axis=2)**3
            if (r3<1e-15).any():raise ChainError('out_of_domain','Magnet contact/singular force')
            ans+=a*b*np.sum((ww[:,None]*ww[None,:]/r3)[:,:,None]*r,axis=(0,1))
    return ans*MU0/(4*np.pi)*(br/MU0)**2*.005**2*.01**2

def coordinates(angle,gap):
    driver_x=(904-gap)/1000
    return .904-(driver_x*np.cos(angle)-.045*np.sin(angle)), driver_x*np.sin(angle)+.045*np.cos(angle)-.075265

def force_table(directory,mechanical):
    angles=np.unique(np.r_[np.linspace(0,5,21),np.linspace(5,15,21),np.linspace(15,65,26)])*np.pi/180
    qs=np.linspace(-.008,.008,17);br=mechanical['remanence_T'];gap=mechanical['gap_mm']
    values=np.array([[force(*np.array(coordinates(a,gap))-[0,q],a,br)[2] for q in qs] for a in angles])
    np.savez(directory/'force-table.npz',angles=angles,qs=qs,values=values)
    np.savetxt(directory/'force-table.csv',[(a,q,v) for a,row in zip(angles,values) for q,v in zip(qs,row)],delimiter=',',header='angle_rad,tip_m,force_N',comments='')
    from scipy.interpolate import RegularGridInterpolator
    interp=RegularGridInterpolator((angles,qs),values,bounds_error=True)
    rng=np.random.default_rng(17);checks=[];quad=[]
    for _ in range(48):
        a=rng.uniform(0,np.deg2rad(15));q=rng.uniform(-.008,.008);dx,dz=coordinates(a,gap)
        expected=force(dx,dz-q,a,br,10)[2];computed=float(interp([[a,q]])[0]);checks.append(abs(expected-computed))
        quad.append(abs(force(dx,dz-q,a,br,6)[2]-expected))
    scale=max(abs(values).max(),1e-9)
    result={'angle_rad':[0,float(angles[-1])],'tip_m':[-.008,.008],
        'max_interpolation_error_over_peak':max(checks)/scale,'quadrature_error_over_peak':max(quad)/scale,
        'recoil_permeability':1.,'model':'finite uniform cuboid surface-charge v1',
        'outside_domain':'reject; LTspice clamps only to permit detection and returns out_of_domain afterward',
        'native_confirmation':'separate COMSOL anchors; table is not a full FEM grid'}
    write_json(directory/'force-domain.json',result);return result

def magnetic_confirmation(directory,mechanical):
    """Independent field-gradient anchors with the SAME unity-permeability assumptions.

    This sparse check is deliberately not called a complete force-table calibration.
    """
    source=(REPO/'configs/reference_cases/door-magnetic-v1/DoorMagnetic.java').read_text()
    gap=mechanical['gap_mm'];br=mechanical['remanence_T']
    source=source.replace('"48[mm]"',f'"{gap}[mm]"').replace('1.05);','1);').replace('"1.25[T]"',f'"{br}[T]"').replace('1.25[T]/mu0_const',f'{br}[T]/mu0_const')
    # A larger far-field domain and retained mesh comparison, not threshold relaxation.
    source=source.replace('"150[mm]"','"220[mm]"')
    (directory/'DoorMagnetic.java').write_text(source.replace('__OUTPUT__',str(directory)))
    log=solve_java(directory/'DoorMagnetic.java',directory);rows=[]
    for line in log.splitlines():
        if line.startswith('BF_DATA,force,'):
            _,_,mesh,z,fx,fz=line.split(',');expected=force(gap/1000,float(z)/1000,0,br,12)
            computed=np.array([float(fx),float(fz)]);ref=expected[[0,2]]
            rows.append({'mesh':int(mesh),'dz_mm':float(z),'force_N':computed.tolist(),'reference_N':ref.tolist(),
                         'relative_error':float(np.linalg.norm(computed-ref)/max(np.linalg.norm(ref),1e-9))})
    if len(rows)!=6:raise ChainError('tool_fail','Missing COMSOL force rows')
    delta=max(np.linalg.norm(np.array(rows[i]['force_N'])-rows[i+3]['force_N'])/max(np.linalg.norm(rows[i+3]['force_N']),1e-9) for i in range(3))
    value={'rows':rows,'mesh_delta':float(delta),'mesh_target':.05,'max_reference_error':max(r['relative_error'] for r in rows[3:]),
           'coverage':'three unrotated anchors, not full door trajectory confirmation','coverage_complete':False,
           'model':'uniform Br, recoil permeability one, rigid-tip gradient integral'}
    write_json(directory/'magnetic-confirmation.json',value);return value

def firmware(directory,config):
    mapping={'INTERVAL_MS':'interval_ms','BOOT_MS':'boot_ms','INIT_MS':'init_ms','TX_MS':'tx_ms',
             'BOOT_MA':'boot_mA','INIT_MA':'init_mA','TX_MA':'tx_mA'}
    header='\n'.join('#define '+k+' '+str(config[v]) for k,v in mapping.items())
    header+='\n#define SLEEP_MA '+str(config['sleep_uA']/1000)+'\n#define RESET_MA '+str(config['reset_uA']/1000)+'\n'
    (directory/'policy.h').write_text(header);shutil.copy2(Path(__file__).with_name('program.c'),directory/'program.c')
    command(['cc','-O2','-shared','-fPIC','program.c','-o','program.dylib'],directory,'host-build',30)
    command([GCC,'-mcpu=cortex-m4','-mthumb','-O2','-ffreestanding','-c','program.c','-o','program-arm.o'],directory,'arm-build',30)
    command([GCC,'--version'],directory,'compiler',15)
    receiver=(REPO/'scripts/pluck_receiver.py').read_text().replace('BFP1','BFD2')
    (directory/'receiver.py').write_text(receiver)
    result={'host_shared_library':file_hash(directory/'program.dylib'),'arm_policy_object':file_hash(directory/'program-arm.o'),
            'source':file_hash(directory/'program.c'),'policy':file_hash(directory/'policy.h'),'receiver':file_hash(directory/'receiver.py'),
            'scope':'same C application state logic compiled for host and Cortex-M4; ARM object is not a flashable image or executed SoC binary',
            'load_origin':'ViPSN stage-energy envelopes converted at 3.3V, configurable assumptions; not this binary measured power',
            'pgood':'status input only; reset/startup/sleep current included'}
    write_json(directory/'build-receipt.json',result);return result
