# Independent conditional static ROM review

Result: the declared conditional static provider passes source, energy, coordinate and numerical consistency review. It is not a native COMSOL reconstruction, physical calibration, dynamic provider or feasible mission witness.

- All 23 frozen base files and six composite-seal entries verify; 26 producer tests pass in a reviewer-owned copy
- Independent cubic-Hermite stiffness/consistent-mass assembly and axial/endpoint Schur reduction reproduce 15 quantities within 1.14 × 10^-15 relative difference; no provider math was imported
- Fixed-shape Cp is 18.75197 nF; endpoint-static condensed Cp is 19.47940 nF. Their 0.72743 nF difference is discarded bending relaxation, not interchangeable bookkeeping
- A separate three-element axial-bar calculation verifies alpha=1.37766 × 10^-7 m/N, beta=6.76558 × 10^-9 m/V and fixed-eta Cp=18.41972 nF. The load-induced stored-energy increment includes beta*N*V and can be signed; it is not dissipation
- The material values are an explicitly new PSI-5A4E branch. Unknown native tensor, damping, physical polarity and validity bounds remain unknown

The force projection is work-consistent on its stated short-circuit q-only path. Later axial force/torque can excite discarded coordinates, and nonzero voltage adds axial translation omitted by that pose. The existing fixed-orientation force table cannot silently substitute for this generalized force. Source-code frame registration has now been identified separately; physical installation remains unqualified.

No new time integration, equilibrium, magnetic evaluation, licensed-tool execution or physical qualification was performed by this reviewer. Actual force/voltage/gradient bounds, loss models and dynamic reference evidence are still missing, so no dynamic run is admitted by this review.

The detailed source/equation note and machine-readable readbacks accompany this report. Full third-party source documents are retained only in the local test snapshot and are excluded from the review delivery manifest.
