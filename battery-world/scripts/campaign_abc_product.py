#!/usr/bin/env python3
"""Derive a bounded packaging source from an actual BF-submitted A/R design.

This creates no mesh, simulator environment, manufactured PCB or backup.
"""
import argparse
import json
from pathlib import Path

from bfworld.agentlab.campaign20261019.phase1 import file_hash, seal


def package(episode, output):
    episode, output = Path(episode), Path(output)
    subpath = episode/'product/submission.json'
    sub = json.loads(subpath.read_text())
    data = json.loads((episode/'product/input-contract.json').read_text())
    cat = data['catalogue']
    candidate = sub['candidate']
    n = candidate['storage']['modules']
    length, width = cat['fixed_installation']['source_module_footprint_mm']
    cap = cat['parts']['GA209F']['size_mm']
    # Explicit construction dimensions are fit hypotheses; part body sizes are
    # sourced. XY never extends beyond the original source-module footprint.
    parameters = {'schema_version':'bf-abc-ar-packaging-v1','source_candidate':str(subpath),'source_candidate_file_sha256':file_hash(subpath),
        'outer_xy_mm':[length,width],'active_window_mm':cat['fixed_installation']['active_window_nominal_mm'],
        'part_bodies_mm':{k:cat['parts'][k]['size_mm'] for k in ('GA209F','MSP430FR2433','BQ25570','TMP117')},
        'storage_modules':n,'storage_centres_xy_mm':[[15+22*i,12] for i in range(n)],
        'mcu_centre_xy_mm':[52,12],'pmic_centre_xy_mm':[60,12],'sensor_centre_xy_mm':[63,31],
        'mount_hole_centres_xy_mm':[[4,4],[length-4,4],[4,width-4],[length-4,width-4]],
        'mount_hole_diameter_mm':2,'wall_mm':1,'pcb_nominal_mm':1,'cavity_nominal_mm':4.5,
        'unverified_parameters':['PV thickness and tab clearance','support passives, antenna and crystal keepouts','thermal contact and sample-response lag','mount substrate and installation thickness','manufacturing tolerance and assembly sequence'],
        'mechanical_qualification':'NOT_CALIBRATED; parametric placement/clearance concept, no routed PCB or fabrication acceptance'}
    for x,y in parameters['storage_centres_xy_mm']:
        if not (0<=x-cap[0]/2 and x+cap[0]/2<=length and 0<=y-cap[1]/2 and y+cap[1]/2<=width):raise ValueError('PART_OUTSIDE_FIXED_XY')
    output.mkdir(parents=True,exist_ok=True)
    seal(output/'packaging-parameters.json',parameters)
    scad=f'''// Actual BF candidate; uncalibrated packaging hypothesis. Units mm.
// XY is bounded by the original source-module footprint. Default Z is assumed.
length={length}; width={width}; wall=1; pcb=1; cavity=4.5;
window=[50,30]; mount_d=2; cap=[{cap[0]},{cap[1]},{cap[2]}];
cap_centres={json.dumps(parameters['storage_centres_xy_mm'])};
mounts={json.dumps(parameters['mount_hole_centres_xy_mm'])};
module lower_tray() {{
 difference() {{
  cube([length,width,cavity+wall]);
  translate([wall,wall,wall]) cube([length-2*wall,width-2*wall,cavity+1]);
  for(p=mounts) translate([p[0],p[1],-1]) cylinder(h=wall+2,d=mount_d,$fn=24);
 }}
}}
module body(x,y,dx,dy,dz) {{translate([x-dx/2,y-dy/2,wall+pcb]) cube([dx,dy,dz]);}}
lower_tray();
color("darkgreen") translate([wall,wall,wall]) cube([length-2*wall,width-2*wall,pcb]);
for(p=cap_centres) color("silver") body(p[0],p[1],cap[0],cap[1],cap[2]);
color("black") body(52,12,4,4,1); // MSP430 VQFN nominal XY; Z assumed
color("black") body(60,12,3.5,3.5,1); // BQ25570 nominal XY; Z assumed
color("red") body(63,31,2,2,1); // TMP117 WSON nominal XY; Z assumed
// The window is an alignment plane, not an asserted installed irradiance gain.
%translate([(length-window[0])/2,(width-window[1])/2,cavity+wall]) cube([window[0],window[1],0.2]);
'''
    target=output/'card-fit.scad'
    if target.exists() and target.read_text()!=scad:raise ValueError('PACKAGING_SOURCE_ALREADY_EXISTS')
    target.write_text(scad)
    return parameters


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--episode',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    print(json.dumps(package(a.episode,a.output),ensure_ascii=False))
