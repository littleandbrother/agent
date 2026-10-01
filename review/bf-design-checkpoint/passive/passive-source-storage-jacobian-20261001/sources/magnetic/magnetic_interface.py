"""Static-only finite-cuboid mutual potential and beam generalized magnetic force.

A new conditional model identity. No table, interpolator, equilibrium or ODE.
The permanent magnetization is material-fixed and mu_rec=1 everywhere. Only
mutual energy is needed: rigid-body self energies do not depend on q.
"""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import numpy as np
from numpy.polynomial.legendre import leggauss

ROOT=Path(__file__).resolve().parent
VERSION='bf-conditional-psi5a4e-cuboid-generalized-force-v1'
LEGACY_VERSION='source-fixed-tip-transverse-force-native-a2e2937a'
MU0=4e-7*np.pi  # Inherited computational source constant, H/m.

class DomainError(ValueError):
    pass


def checked_float(x,name):
    if isinstance(x,(bool,np.bool_)) or not np.isscalar(x):
        raise DomainError(name+' must be a finite scalar')
    try:x=float(x)
    except (ValueError,TypeError,OverflowError) as e:raise DomainError(name+' must be a finite scalar') from e
    if not math.isfinite(x):raise DomainError(name+' must be finite')
    return x


def proper_rotation(rotation):
    r=np.asarray(rotation,dtype=float)
    if r.shape!=(3,3) or not np.isfinite(r).all() or not np.allclose(r.T@r,np.eye(3),atol=2e-13,rtol=0) or abs(np.linalg.det(r)-1)>2e-13:
        raise DomainError('rotation must be a finite proper orthogonal matrix')
    return r


def ry(angle):
    c,s=math.cos(angle),math.sin(angle)
    return np.array([[c,0,s],[0,1,0],[-s,0,c]])


def rz(angle):
    c,s=math.cos(angle),math.sin(angle)
    return np.array([[c,-s,0],[s,c,0],[0,0,1]])


@dataclass(frozen=True)
class Cuboid:
    center:np.ndarray
    rotation:np.ndarray
    size:np.ndarray
    br_T:float

    def __post_init__(self):
        c=np.asarray(self.center,dtype=float)
        s=np.asarray(self.size,dtype=float)
        if c.shape!=(3,) or not np.isfinite(c).all():raise DomainError('invalid cuboid center')
        if s.shape!=(3,) or not np.isfinite(s).all() or min(s)<=0:raise DomainError('invalid cuboid size')
        object.__setattr__(self,'center',c)
        object.__setattr__(self,'size',s)
        object.__setattr__(self,'rotation',proper_rotation(self.rotation))
        br=checked_float(self.br_T,'remanence')
        if br<=0:raise DomainError('remanence must be positive; polarity is defined by orientation')
        object.__setattr__(self,'br_T',br)


def separation_diagnostic(a:Cuboid,b:Cuboid):
    """15-axis SAT: reject contact/overlap, report a conservative distance bound.

    A positive projection gap proves separation; maximum positive projection
    gap is a lower bound on true surface distance, NOT exact clearance.
    For touching/overlap all gaps are <=0. Axes with norm<1e-12 are redundant.
    """
    axes=[*a.rotation.T,*b.rotation.T]
    axes += [np.cross(x,y) for x in a.rotation.T for y in b.rotation.T]
    gaps=[]
    for axis in axes:
        norm=np.linalg.norm(axis)
        if norm<1e-12:continue
        u=axis/norm
        ra=np.abs(a.rotation.T@u)@(a.size/2)
        rb=np.abs(b.rotation.T@u)@(b.size/2)
        gaps.append(float(abs((b.center-a.center)@u)-ra-rb))
    gap=max(gaps)
    return {'obb_separated':gap>1e-12,'surface_distance_lower_bound_m':max(gap,0.),
            'maximum_sat_projection_gap_m':gap,'contact_rejection_tolerance_m':1e-12,
            'scope':'magnet-to-magnet OBBs only; no surrounding assembly or continuous-path clearance'}


@lru_cache(maxsize=24)
def local_charges(size_tuple,br_T,n):
    """Body +x magnetization; signed integrated charge sigma*dA has units A m."""
    if isinstance(n,bool) or not isinstance(n,(int,np.integer)) or n<2 or n>24:
        raise DomainError('quadrature order must be an integer from 2 to 24')
    size=np.array(size_tuple)
    x,w=leggauss(n)
    yy,zz=np.meshgrid(x,x,indexing='ij')
    ww=np.outer(w,w).ravel()
    points=[];charges=[]
    for sign in (-1,1):
        points.append(np.column_stack([np.full(n*n,sign*size[0]/2),yy.ravel()*size[1]/2,zz.ravel()*size[2]/2]))
        charges.append(sign*(br_T/MU0)*(size[1]*size[2]/4)*ww)
    return np.concatenate(points),np.concatenate(charges)


def potential_force_torque(tip:Cuboid,driver:Cuboid,n:int):
    """Return mutual U[J], force[N], and tip COM torque[N m].

    U=mu0/(4*pi) sum(c_i*c_j/|r_i-r_j|).
    f_ij=mu0/(4*pi)c_i*c_j (r_i-r_j)/|r_i-r_j|^3.
    tau=sum((r_i-r_tipCOM) cross f_ij). Material-fixed charges mean this
    torque includes magnetic orientation effects; do not add m cross B again.
    """
    contact=separation_diagnostic(tip,driver)
    if not contact['obb_separated']:raise DomainError('magnet contact/overlap (SAT), force evaluation refused')
    tp,tq=local_charges(tuple(tip.size),tip.br_T,n)
    dp,dq=local_charges(tuple(driver.size),driver.br_T,n)
    lever=tp@tip.rotation.T
    dlever=dp@driver.rotation.T
    r=(tip.center-driver.center)+lever[:,None,:]-dlever[None,:,:]
    dist=np.linalg.norm(r,axis=2)
    if np.min(dist)<=1e-12:raise DomainError('singular quadrature pair')
    coefficient=MU0/(4*np.pi)*tq[:,None]*dq[None,:]
    u=float(np.sum(coefficient/dist))
    pair_force=(coefficient/dist**3)[:,:,None]*r
    node_force=pair_force.sum(axis=1)
    force=node_force.sum(axis=0)
    torque=np.cross(lever,node_force).sum(axis=0)
    # Retained balance check, using forces on the same charge pairs.
    torque_driver=np.cross(dlever,-pair_force.sum(axis=0)).sum(axis=0)
    balance=torque+torque_driver+np.cross(tip.center-driver.center,force)
    return {'mutual_potential_J':u,'force_beam_N':force,'tip_torque_about_COM_beam_N_m':torque,
            'driver_torque_about_COM_beam_N_m':torque_driver,'internal_moment_balance_N_m':balance,
            'contact':contact,'minimum_quadrature_pair_distance_m':float(np.min(dist))}


class StaticMagneticInterface:
    def __init__(self,root=ROOT):
        self.root=Path(root)
        self.plan=json.loads((self.root/'STATIC-PLAN.json').read_text())
        seal=json.loads((self.root/'PLAN-SEAL.json').read_text())
        if hashlib.sha256((self.root/'STATIC-PLAN.json').read_bytes()).hexdigest()!=seal['plan_sha256']:
            raise ValueError('plan hash mismatch')
        for binding in self.plan['source_bindings'].values():
            if hashlib.sha256((self.root/binding['snapshot_path']).read_bytes()).hexdigest()!=binding['sha256']:
                raise ValueError('source hash mismatch: '+binding['snapshot_path'])
        src=self.root/'sources'
        self.world=json.loads((src/'world-v1.json').read_text())
        self.design=json.loads((src/'source-design.json').read_text())
        spec=importlib.util.spec_from_file_location('frozen_static_beam',src/'beam_rom.py')
        self.beam=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.beam)
        self.parameters=self.beam.load_inputs(src/'beam-parameters.json')
        self.rom=self.beam.derive(self.parameters)
        self.A=proper_rotation(self.world['geometry']['force_from_world'])
        product_origin=np.array(self.design['door']['product_origin_world_mm'])/1000
        self.beam_origin_world=product_origin+self.A.T@np.array([self.design['beam']['clamp_end_x']/1000,0,0])
        self.tip_rest=np.array([self.rom['magnet_center_x_m'],0,self.parameters['copper_thickness']/2+self.parameters['magnet_height']/2])
        self.nominal_tip_world=np.array(self.world['geometry']['nominal_tip_world_m'])
        if not np.allclose(self.beam_origin_world+self.A.T@self.tip_rest,self.nominal_tip_world,atol=1e-14,rtol=0):
            raise ValueError('beam/CAD rest center registration mismatch')
        if self.world['force']['recoil_permeability']!=1:raise ValueError('surface-charge model requires mur1')
        for key in ('tip_size_m','driver_size_m'):
            if not np.allclose(self.world['geometry'][key],np.array(self.design['magnets'][key.replace('_size_m','_mm')])/1000,atol=1e-15,rtol=0):
                raise ValueError('source cube size mismatch')
        if not np.array_equal(self.world['geometry']['initial_magnetization_force_axis'],[1,0,0]):
            raise ValueError('unsupported magnetization polarity')
        if not np.array_equal(self.A@self.world['geometry']['positive_q_world'],[0,0,1]):raise ValueError('q sign mismatch')
        if not np.array_equal(self.A@self.world['geometry']['rotation_axis_world'],[0,1,0]):raise ValueError('door rotation axis mismatch')

    def pose(self,angle_rad,q_m,gap_m=None):
        a=checked_float(angle_rad,'angle');q=checked_float(q_m,'q')
        gap=checked_float(self.plan['gap_m'] if gap_m is None else gap_m,'gap')
        g=self.world['geometry']
        if not 0<=a<=self.world['input']['opening_angle_rad']:raise DomainError('angle outside inherited support')
        if abs(q)>g['rom_absolute_deflection_limit_m']:raise DomainError('q outside inherited support')
        if not g['parameter_support_gap_m'][0]<=gap<=g['parameter_support_gap_m'][1]:raise DomainError('gap outside inherited support')
        pose=self.beam.pose_and_jacobian(self.rom,q,self.tip_rest[2])
        dc=np.array(g['nominal_driver_world_m']);dc[0]=self.nominal_tip_world[0]-gap
        pivot=np.array(g['pivot_world_m'])
        driver_world=pivot+rz(a)@(dc-pivot)
        driver_center=self.A@(driver_world-self.beam_origin_world)
        rd=proper_rotation(self.A@rz(a)@self.A.T)
        if not np.allclose(rd,ry(a),atol=1e-14,rtol=0):raise ValueError('driver rotation mapping mismatch')
        br=self.world['force']['remanence_T']
        tip=Cuboid(np.array(pose['center_m']),np.array(pose['rotation_from_reference']),np.array(g['tip_size_m']),br)
        driver=Cuboid(driver_center,rd,np.array(g['driver_size_m']),br)
        return tip,driver,pose

    def evaluate(self,angle_rad,q_m,n=6,gap_m=None):
        tip,driver,pose=self.pose(angle_rad,q_m,gap_m)
        result=potential_force_torque(tip,driver,n)
        f=result['force_beam_N'];t=result['tip_torque_about_COM_beam_N_m']
        pieces={'transverse_Fz_N':float(f[2]),'axial_virtual_work_N':float(f[0]*pose['dcenter_dq'][0]),
                'rotational_virtual_work_N':float(t@pose['angular_velocity_per_qdot'])}
        qforce=float(f@pose['dcenter_dq']+t@pose['angular_velocity_per_qdot'])
        if not np.isclose(qforce,self.beam.project_force(self.rom,f,t),rtol=1e-14,atol=1e-15):raise ValueError('projection contract disagreement')
        result.update({'generalized_force_N':qforce,'projection_terms':pieces,'pose':pose,
                       'tip_center_beam_m':tip.center,'driver_center_beam_m':driver.center,
                       'driver_minus_tip_beam_m':driver.center-tip.center,
                       'tip_rotation':tip.rotation,'driver_rotation':driver.rotation,
                       'tip_magnetization_unit_beam':tip.rotation[:,0],'driver_magnetization_unit_beam':driver.rotation[:,0],
                       'provider_version':VERSION,'quadrature_order':n})
        return result

    def legacy_force(self,angle_rad,q_m,n):
        # Exact AST extraction of existing source functions. Not relabelled as
        # generalized force and never used by the new interface evaluation.
        tree=ast.parse((self.root/'sources'/'upstream_native.py').read_text())
        nodes=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in ('force','coordinates')]
        namespace={'np':np,'leggauss':leggauss,'MU0':MU0,'ChainError':DomainError}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<source-bound-legacy-force>','exec'),namespace)
        dx,dz=namespace['coordinates'](angle_rad,self.plan['gap_m']*1000)
        return namespace['force'](dx,dz-q_m,angle_rad,self.world['force']['remanence_T'],n)


def jsonable(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,(np.integer,np.floating)):return x.item()
    if isinstance(x,dict):return {k:jsonable(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [jsonable(v) for v in x]
    return x
