"""UNADMITTED numerical repair proposal; algebra only, no solver/provider calls.

Physical parameters, charge state and RHS are unchanged. Magnetic q derivatives
must be provided by a separately reviewed bounded-difference adapter. This file
does not implement or authorize that adapter or any new dynamic trajectory.
"""
import numpy as np

class RecordedGuardError(ValueError):
    def __init__(self,record):
        self.record=record;super().__init__(record['reason'])

def guarded_voltage(y,*,t,theta,cp,phase,last_accepted_t,limit=500.):
    """Proposed immutable rejection telemetry, supplied before any provider call."""
    vp=(y[2]-theta*y[0])/cp;vs=y[3]
    if abs(vp)>limit or vs>limit:
        raise RecordedGuardError({'reason':'numerical voltage guard','phase':phase,'t_s':float(t),'last_accepted_t_s':float(last_accepted_t),'rejected_state':list(map(float,y)),'Vp_V':float(vp),'Vs_V':float(vs),'Vp_guard_failed':bool(abs(vp)>limit),'Vs_guard_failed':bool(vs>limit),'limit_V':limit,'accepted_state':False})
    return vp,vs

def bounded_q_step(q,limit=.008,nominal=1e-7):
    margin=limit-abs(q)
    if not np.isfinite(q) or margin<=0:raise ValueError('no in-domain derivative interval')
    h=min(nominal,.25*margin)
    if h<1e-12:raise ValueError('derivative interval numerically unresolved')
    return h

def branch_jacobian(y,*,m,k,c,theta,cp,cin,R,dF_dq,dPtrans_dq,dProt_dq):
    q,u,Q,vs=y[:4];vp=(Q-theta*q)/cp
    J=np.zeros((8,8));J[0,1]=1
    J[1,0]=(dF_dq-k-theta*theta/cp)/m;J[1,1]=-c/m;J[1,2]=theta/(m*cp)
    if abs(vp)>vs:
        s=float(np.sign(vp));I=(abs(vp)-vs)/R
        dv=np.array([-theta/cp,0.,1/cp,0.])
        dI=s*dv/R;dI[3]=-1/R
        di=dv/R;di[3]=-s/R
        J[2,:4]=-di;J[3,:4]=dI/cin;J[5,:4]=2*R*I*dI
    # At bridge equality choose the inactive branch of a nonsmooth generalized
    # Jacobian. This is a declared solver convention, not a smoothed diode law.
    J[4,1]=2*c*u;J[6,0]=dPtrans_dq;J[7,0]=dProt_dq
    return J
