# Independent generalized-force review

Result: the five-state conditional static interface and retained evidence pass the reviewed source, frame, work-projection and arithmetic checks. No new magnetic evaluation, equilibrium or time integration was run by this reviewer.

All 26 package files verify and all 26 source/domain/retained-data tests pass. Independent readback checks 15 nominal force/torque projections, 45 energy derivatives from retained U(q+h)/U(q-h), 105 original/replay equalities and the saved nominal/perturbed magnet-box separation conditions. Maximum energy-gradient/projection difference is 1.664e-9 N; maximum order-6-to-10 Q change is 3.350e-10 N. These are sampled numerical checks, not physical or whole-domain validation. The evidence-completion replay is a repeated execution, not an independent sample.

## What the comparison means

Both old and new q normalize magnet-COM vertical displacement. The old path translates only; the new path also translates axially and rotates. Their virtual tangents differ. Therefore Qnew versus old Fz compares different kinematic models, even when the q=0 poses coincide.

At closed q=0 the old/new force vectors match within about 9.1e-15 N in vector norm. New axial and torque work terms are -0.00966217 N and -0.09612888 N, giving Q=-0.42122165 N versus old Fz=-0.31543060 N. This is not an old-force numerical error.

At 15 degrees and q=4 mm, the new Fz remains negative (-0.000435032 N), while torque and axial projection give Q=+0.000856892 N; legacy Fz is -0.000533073 N. The correct conclusion is that the old transverse-only table cannot be transferred to the new mode unchanged.

## Limit

The checked pose is V=0/q-only. Axial load and general torque can excite discarded coordinates, and voltage-induced axial translation is omitted. The uniform-hard-magnet, unity-recoil-permeability model is conditional. No native model, dynamic trajectory, PMIC, mission, hardware or Agent conclusion follows.

The accompanying next-step recommendation distinguishes a bounded passive source/storage model-sensitivity experiment from a genuinely feasible native reference. The former can be useful after connected-runner gates and explicit authorization; the latter remains blocked by missing native/physical evidence.
