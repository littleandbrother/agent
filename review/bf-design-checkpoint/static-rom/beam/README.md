# Conditional beam ROM: static-only package

Read `DERIVATION.md` first. This is a new conditional PSI-5A4E, perfect-bond, Euler–Bernoulli, one-term Ritz branch, not the unknown native COMSOL material/model and not an admitted dynamic provider.

## Key artifacts

- `parameters.json`: every numeric primitive with SI unit and provenance identifier
- `provenance.json`: source roles, source byte hashes, known material inconsistency and unknowns
- `beam_rom.py`: transparent polynomial derivation, static reciprocal port, explicit magnet pose/Jacobian and force projection; dynamic export fails closed
- `outputs/canonical-static-rom.json`: versioned parameters, full mass/section/charge decomposition and input-file hashes
- `outputs/sensitivity.json`: model-form comparisons and local derivatives, no fabricated physical confidence intervals
- `tests/test_rom.py`: 26 positive, negative, dimensional, reciprocity and virtual-work checks
- `independent/`: separate closed-form/quadrature implementation and byte-bound comparison
- `MANIFEST.json`: all retained package bytes, including source snapshots
- `RECEIPT.json`: scope, test and blocker summary

## Reproduce without modifying frozen results

From this directory, with Python 3.11+ and NumPy available:

```sh
python -B verify_package.py
python -B -m unittest discover -s tests -v
python -B beam_rom.py | cmp - outputs/canonical-static-rom.json
```

The independent implementation can be rerun in a copy of the package. It currently verifies the original upstream source path retained in its provenance; that source hash is also represented by `sources/DoorBeam.java`. `analyze_sensitivity.py` likewise writes its output and should be rerun in a copy after sealing. Do not overwrite accepted or sealed evidence to explore a change; create a new version/branch.

The full vendor PDF, HTML and rendered page are local provenance snapshots. Exclude them from a user-facing bundle; distribute original-source URLs, hashes and concise factual parameter records instead. This package is presently internal development work, not a Library delivery.

## Critical integration blocker

A deforming beam pitches and axially shifts the eccentric magnet. The old fixed-orientation, transverse-only magnetic table cannot be treated as its exact generalized force. Use the new q-to-pose/Jacobian contract and energy-consistent force-plus-COM-torque projection, or explicitly review a quantified neglect approximation. Damping, physical validity and dynamic PMIC prerequisites also remain unresolved. No time-domain solver is present and no four-cell run is authorized by this package.
