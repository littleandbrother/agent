#!/usr/bin/env python3
"""Read completed provider JSON, never import implementation; record differences."""
import hashlib,json
from pathlib import Path
base=Path(__file__).resolve().parent.parent
ip=base/'independent/results.json'; cp=base/'outputs/canonical-static-rom.json'
i=json.loads(ip.read_text()); c=json.loads(cp.read_text()); r=i['rigid_overlap']
mapping={'k_N_m':'k_N_per_m','mass_kg':'mass_kg','theta_C_m':'theta_C_per_m','Cp_ritz_F':'Cp_fixed_shape_F','Cfree_ritz_F':'C_free_ROM_F','Cfree_continuum_static_F':'C_free_continuum_F','Cp_static_q_condensed_F':'C_fixed_endpoint_continuum_F','f_SC_ritz_Hz':'f_short_Hz','f_OC_ritz_Hz':'f_open_Hz','voltage_actuation_q_m_per_V':'static_q_per_v_m_per_V','magnet_pitch_slope_per_m':'magnet_slope_per_q_per_m','magnet_axial_shape':'magnet_uxCOM_per_q','omitted_beam_axial_rotary_mass_diagnostic_kg':'omitted_beam_axial_rotary_mass_kg'}
comparisons=[]
for key,ikey in mapping.items():
    v=r[ikey]; cv=c[key]
    comparisons.append(dict(quantity=key,independent=v,provider=cv,difference=cv-v,relative_difference=(cv-v)/v if v else None))
report={'scope':'Independent algebra and polynomial quadrature comparison; no acceptance criterion or native-equivalence claim.', 'epsilon0_F_per_m':8.8541878188e-12,'inputs_note':'Independent literals trace to supplied geometry/material values; epsilon0 harmonized to parent pin after independent preliminary calculation. No parent implementation imported.', 'source_sha256':i['source_sha256'],'provider_output_sha256':hashlib.sha256(cp.read_bytes()).hexdigest(),'independent_script_sha256':hashlib.sha256((base/'independent/crosscheck.py').read_bytes()).hexdigest(),'comparisons':comparisons,'max_abs_relative_difference':max(abs(x['relative_difference']) for x in comparisons)}
(base/'independent/comparison_receipt.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
