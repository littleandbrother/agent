"""Seal the approved bounded static experiment before any magnetic evaluation."""
from pathlib import Path
import hashlib,json,shutil,datetime
ROOT=Path(__file__).resolve().parent
sources={
 'world-v1.json':Path('/workspace/shared/authoritative-world-20261001/contracts/world-v1.json'),
 'upstream_build_cad.py':Path('/workspace/shared/authoritative-world-20261001/sources/upstream_build_cad.py'),
 'upstream_native.py':Path('/workspace/shared/current-cache-integration-20261001/working/battery-world/packages/python/bfworld/src/bfworld/agentlab/simulation_chain/native.py'),
 'source-design.json':Path('/workspace/shared/current-cache-integration-20261001/working/battery-world/configs/reference_cases/door-magnetic-v1/design.json'),
 'beam_rom.py':Path('/workspace/shared/canonical-beam-rom-20261001/beam_rom.py'),
 'beam-parameters.json':Path('/workspace/shared/canonical-beam-rom-20261001/parameters.json'),
 'beam-static-rom.json':Path('/workspace/shared/canonical-beam-rom-20261001/outputs/canonical-static-rom.json'),
 'DoorBeam.java':Path('/workspace/shared/canonical-beam-rom-20261001/sources/DoorBeam.java'),
}
lock={}
for name,source in sources.items():
 target=ROOT/'sources'/name
 if target.exists():raise RuntimeError('Refuse to replace source snapshot '+str(target))
 shutil.copyfile(source,target)
 lock[name]={'original_path':str(source),'snapshot_path':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
plan={
 'schema':'bf-static-magnetic-interface-plan-v1',
 'provider_version':'bf-conditional-psi5a4e-cuboid-generalized-force-v1',
 'approved_scope':'Root approved exactly this five-state static plan at 2026-10-01 11:41 UTC; no table, extra physical state, equilibrium or time integration.',
 'gap_m':0.048,
 'states':[{'id':i,'angle_deg':a,'q_m':q} for i,a,q in [('closed_zero',0,0),('early_negative',2,-.004),('early_positive',2,.004),('rotated_positive',15,.004),('open_zero',65,0)]],
 'quadrature_orders':[4,6,10],
 'q_central_difference_steps_m':[2e-6,1e-6,5e-7],
 'predeclared_numeric_checks':{
  'virtual_work_abs_plus_relative_N':[1e-9,1e-6],
  'quadrature_6_to_10_abs_plus_relative_Q_N':[1e-9,1e-4],
  'interpretation':'Engineering implementation tolerances only; not physical uncertainty or whole-domain qualification. Order4-to6 retained, no pass claim from two levels alone.',
 },
 'negative_controls':['nonfinite and out-of-support inputs rejected before evaluation','rotation orthogonality/determinant and frame-polarity controls','synthetic overlapping/touching OBBs rejected without force evaluation'],
 'source_bindings':lock,
 'mu0':'Inherited computational constant 4*pi*1e-7 H/m from upstream_native; not claimed exact post-2019 SI',
 'material_identity':'Uniform hard-magnet M=Br/mu0 fixed in material frame, mu_rec=1, ambient mu0, no field-induced magnetization, hysteresis, steel, eddy currents or demagnetization qualification',
 'sealed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
p=ROOT/'STATIC-PLAN.json'
if p.exists():raise RuntimeError('Refuse to overwrite sealed plan')
p.write_text(json.dumps(plan,indent=2)+'\n')
receipt={'plan_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_count':len(lock),'evaluations_before_seal':0}
(ROOT/'PLAN-SEAL.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
