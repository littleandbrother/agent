# Passive source/storage study: independent review scope

This is a new review directory. Earlier core, ROM and generalized-force reviews remain sealed and unchanged.

The parent requested prospective review of the initial state, passive bridge, total-energy ledger and frozen numerical/domain/budget gates before deciding whether to authorize the proposed four trajectories. After authorized runs, this review may audit retained outputs without running extra trajectories. Review itself does not authorize dynamics or new magnetic evaluations.

Owned tests may read retained JSON/CSV records and verify mathematical identities with synthetic algebraic inputs. They must not call the magnetic provider, solve a new equilibrium or time-integrate. Producer software tests require inspection first to ensure they do not launch scientific cases.

## Mathematical acceptance target

For state (q,u,Q,Vs), piezo voltage Vp=(Q-theta*q)/Cp_Ritz. The passive full-wave bridge and series resistance give I=max(|Vp|-Vs,0)/R, terminal outflow i=sign(Vp)*I, Qdot=-i and Cin*Vsdot=I. Mechanical force is m*udot=Qmag-c*u-k*q+theta*Vp.

Total stored energy is 0.5*m*u² + 0.5*k*q² + (Q-theta*q)²/(2*Cp_Ritz) + 0.5*Cin*Vs² + Umag(q,angle). The exact rate is external prescribed-driver power minus c*u² minus R*I². External driver power is the negative of magnetic force/torque power on the prescribed driver. Translational and rotational terms are both required.

This model has a conditional one-mode path, material branch, damping assumption and ideal passive circuit. It does not replace the native PZT/PMIC reference, establish a startup or mission result, or qualify actual initial preparation/reset. Numerical checks must remain distinct from those physical evidence gaps.
