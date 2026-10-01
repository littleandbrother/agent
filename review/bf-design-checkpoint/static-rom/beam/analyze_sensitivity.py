"""Static model-form comparisons and local derivatives, not calibrated intervals."""
import copy
import json
import math
from pathlib import Path
import numpy as np
from beam_rom import load_inputs,derive,ROOT

def main():
    p=load_inputs();base=derive(p)
    metrics=['k_N_m','mass_kg','theta_C_m','Cp_ritz_F','f_SC_ritz_Hz']
    branches=[]
    for label,a in [('rigid_overlap_at_proximal_edge',p['magnet_start']),('flexible_overlap_point_attachment_at_centroid',p['copper_length'])]:
        z=copy.deepcopy(p);z['rigid_attachment_start']=a;r=derive(z)
        branches.append({'name':label,'attachment_m':a,'values':{k:r[k] for k in metrics},'relative_to_rigid':{k:r[k]/base[k]-1 for k in metrics},'magnet_pitch_slope_per_m':r['magnet_pitch_slope_per_m'],'magnet_axial_shape':r['magnet_axial_shape']})
    # This sweep bounds this explicitly parameterized family only, not the device.
    samples=[]
    for a in np.linspace(p['magnet_start'],p['copper_length'],101):
        z=copy.deepcopy(p);z['rigid_attachment_start']=float(a);samples.append(derive(z))
    envelope={k:{'min':min(r[k] for r in samples),'max':max(r[k] for r in samples)} for k in metrics}
    derivatives={}
    for name in ['copper_young','copper_density','pzt_young_E1','pzt_density','pzt_d31','pzt_epsilon_T33_relative','magnet_density']:
        rows=[]
        for h in [1e-4,5e-5]:
            plus=copy.deepcopy(p);minus=copy.deepcopy(p);plus[name]*=1+h;minus[name]*=1-h
            rp,rm=derive(plus),derive(minus)
            rows.append({k:(rp[k]-rm[k])/(2*h*base[k]) for k in metrics})
        derivatives[name]={'elasticities':rows[-1],'finite_difference_h':5e-5,'h_halving_max_absolute_change':max(abs(rows[0][k]-rows[1][k]) for k in metrics),'interpretation':'local d ln|output| / d ln|parameter|; step is numerical, not a material tolerance'}
    omitted=base['mass_terms_kg']['magnet_axial_eccentric']+base['mass_terms_kg']['magnet_centroid_pitch']
    data={
      'schema':'bf-static-beam-sensitivity-v1','new_dynamic_runs':0,
      'physical_uncertainty_bounds':None,
      'physical_uncertainty_reason':'Source constants are assumptions or typical values; no verified joint material, adhesive, manufacturing or clamp tolerances. Do not invent confidence intervals.',
      'attachment_model_form_branches':branches,
      'attachment_model_family_sampled_envelope':{'scope':'only a in [91,96] mm with all other assumptions fixed; not guaranteed physical bounds','grid_points':101,'metrics':envelope},
      'capacitance_model_form':{
        k:base[k] for k in ['Cp_scalar_S1_fixed_Tother0_F','Cp_ritz_F','Cp_static_q_condensed_F','Cfree_ritz_F','Cfree_continuum_static_F','Cp_free_material_T_fixed_F']},
      'static_bending_relaxation_omitted_relative_to_Cp_Ritz':base['Cp_static_q_condensed_F']/base['Cp_ritz_F']-1,
      'wrong_free_material_capacitance_excess_relative_to_Cp_Ritz':base['Cp_free_material_T_fixed_F']/base['Cp_ritz_F']-1,
      'magnet_point_mass_omission':{'omitted_generalized_mass_kg':omitted,'relative_mass_error':omitted/base['mass_kg'],'frequency_increase_if_omitted':math.sqrt(base['mass_kg']/(base['mass_kg']-omitted))-1},
      'beam_axial_rotary_mass_omission':{'omitted_generalized_mass_kg':base['omitted_beam_axial_rotary_mass_diagnostic_kg'],'relative_mass_error':base['omitted_beam_axial_rotary_mass_diagnostic_kg']/base['mass_kg']},
      'local_parameter_elasticities':derivatives,
      'damping':{'value':None,'range':None,'reason':'No measured assembled-device damping. Manufacturer ceramic Qm=80 is not its modal damping ratio.'},
      'polarity':{'physical_sign_known':False,'conditional_sign':'+z poling, Vtop−Vbottom','opposite_poling_changes':'theta sign only; Cp, k, m unchanged'},
      'inherited_q_support_audit':base['inherited_support_diagnostic_only'],
      'published_primitive_inconsistency':{'derived_k31':base['material_k31_from_selected_primitives'],'published_k31':.35,'relative_difference':base['material_k31_from_selected_primitives']/.35-1,'treatment':'Y1E,d31,epsilon33T are declared independent primitives; published k31 is not simultaneously imposed or used as calibration'},
    }
    (ROOT/'outputs'/'sensitivity.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')

if __name__=='__main__':main()
