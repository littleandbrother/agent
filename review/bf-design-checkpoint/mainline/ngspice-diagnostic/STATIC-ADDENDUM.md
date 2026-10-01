# Unchanged ngspice coupling gate: static interpretation

2026-10-01. Addendum to the frozen cache-v2 integration, pinned to GitHub
`338d60384d5805abf1e02252a4513860066a2c39`. The integration package remains unchanged.

## Finding

The strict `> 1e-7 m` assertion is a hand-selected **minimum effect-size check**.
The inspected source provides no analytical expected response, physical lower
bound, uncertainty budget, or cited rationale for that magnitude. It is not a
numerical-error tolerance. The comment only requires electrical loading to
change the mechanical response. “Undocumented” does not prove the author chose
the number randomly.

Baseline and cache-patched aggregate logs report the identical difference,
`9.750000000072201e-8 m`: approximately 97.5 nm against a 100 nm minimum, a
2.5 nm (2.5%) shortfall. All prior assertions in this test were reached and
passed; its final assertion remains failed. Static inspection does not show
that this shortfall is a model inconsistency or quantify how much is numerical.

## Equations and SI units

`event_design.py` lines 180–189 implement the analogous circuit states
`v(q) = displacement q [m]`, `v(u) = velocity u [m/s]`, and `v(p) = piezo voltage V [V]`:

    dq/dt = u
    m du/dt + c u + k q + theta V = F(t)
    Cp dV/dt + i_bridge = theta u

The coefficient theta has units N/V = C/m. Thus theta*V is force and theta*u
is current. Multiplying the mechanical equation by u and the electrical
equation by V cancels reciprocal transfer power theta*V*u:

    d/dt(0.5*m*u^2 + 0.5*k*q^2 + 0.5*Cp*V^2)
      = F*u - c*u^2 - V*i_bridge

The coupling signs and unit conversion are internally consistent. This checks
the declared ideal reciprocal ROM, not physical parameter calibration or every
behavioral element in the model.

For the fixture m=0.001 kg, k=100 N/m, c=0.01 N*s/m, theta=0.0005 N/V,
Cp=1e-7 F. Ideal open circuit adds theta^2/Cp=2.5 N/m, giving a period of
0.0196254 s; ideal short circuit gives 0.0198692 s. This is a useful analytical
coupling check, but the two tested diode/storage/PMIC configurations are neither
those open/short limits nor guaranteed to differ in maximum displacement by
100 nm. Electrical feedback can alter a trajectory or later motion without
necessarily moving its global peak by a specified minimum.

## Why the existing assertion cannot separate causes

- The original strong case is solved at 10 us and 5 us; the comparison uses its
  5 us result. The feedback case is solved only at 10 us. Thus the final
  difference mixes configuration and numerical-setting changes.
- Baseline coarse/fine acceptance is less than 3% relative change of peak
  displacement and peak storage voltage, plus agreement on receiver presence.
  It does not certify the 100 nm difference. At the nominal static scale
  F/k=0.02 m, 3% is 0.0006 m, whereas this effect floor is 5 ppm of that scale.
  F/k is a scale estimate, not the observed dynamic peak.
- The test changes start/stop/output voltages 4/3.4/3.3 V to 0.8/0.5/0.4 V and
  idle current 1 uA to 10 mA. Boot/tx stage currents stay unchanged. Lower
  output voltage reduces their specified regulated power; the post-stage idle
  power increases. It is not a single-variable, uniformly higher-load control.
- `peak_deflection_m` is the maximum absolute displacement among output rows,
  with no interpolation or common-time comparison. It is a scalar peak metric,
  not the maximum pointwise difference of the two trajectories.
- The deck uses Gear, reltol=1e-5, abstol=1e-11, vntol=1e-8, duration 0.25 s,
  `.tran step duration 0 step uic`. Convergence tolerances are not certified
  bounds on a difference of peaks. For illustration, the voltage iteration
  criterion reltol*|q|+vntol is 2.1e-7 in this analogous state at q=0.02; this
  does NOT establish an actual 210 nm solution error.
- `Btimer` uses an off-state reset time constant of step/10. Refinement also
  changes this mathematical state parameter from 1 us to 0.5 us; therefore a
  coarse/fine difference is not a pure time-discretization estimate.
- The export does not explicitly set `numdgt`; full internal precision is not
  explicitly requested. Actual export precision must be inspected before
  attributing nanometre-scale differences to solver behavior.

## Scope and next evidence

This static addendum runs no solver or participant. It changes neither test,
threshold, production code, nor sealed evidence. The remaining classification
is: **unsupported effect-size gate with unresolved numerical sensitivity**;
there is no static evidence of a reciprocal-coupling sign/unit inconsistency.

A separately authorized four-run diagnostic can compare the original two
configurations at matched 10 us and 5 us, report signed/absolute peak differences
and each configuration's refinement change, and preserve all raw files. It
cannot alone prove asymptotic convergence, physical correctness, or qualification.
The original failed assertion must remain failed regardless of those results.

## Source references

- `battery-world/tests/agentlab/test_reference_event.py`: fixture lines 22–34;
  original test lines 138–158; SHA256
  `0b6602d354a038cc9c4b544803c7237e26cb53a4c5147b579ce141462a24664a`
- `battery-world/packages/python/bfworld/src/bfworld/agentlab/event_design.py`:
  netlist lines 166–221; summary lines 239–286; refinement lines 289–308;
  SHA256 `e7c6b978f4afb43d09cf0f9beeb83dd04d9412e74a84b5607c974016c3d8083d`
- `battery-world/docs/agentlab/REFERENCE-EVENT-DESIGN.md` and
  `project/features/BFA-021-reference-event-design/feature.yaml`: claim boundaries;
  neither supplies a derivation of the 100 nm threshold
- Retained aggregate baseline-v4 log line 1019 and integrated-v4 line 1030
- [Official ngspice manual: convergence criterion, section 1.4.1](https://ngspice.sourceforge.io/docs/ngspice-42-manual.pdf)
- [Official ngspice manual: wrdata export precision](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf)

Frozen integration ZIP SHA256 rechecked unchanged:
`f030702388a79336c75289775e8886bb28a2082f895f23d5ebf49a0c7a44dda4`
