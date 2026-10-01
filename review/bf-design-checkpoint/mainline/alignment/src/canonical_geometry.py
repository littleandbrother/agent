"""Canonical physical coordinates, not a renamed gap parameter.

World axes follow the upstream CAD declaration. Force-frame x=-worldX,
y=worldZ, z=worldY; positive beam q is +worldY. The stored geometry is explicit
for one design. It does not imply that two gap-variation design families match.
"""
import copy,json,math,pathlib,sys
import numpy as np
import jsonschema
from adapters import digest,cloud_power,upstream_native,cloud_coordinates,write
from cad_source_check import declared_centers
ROOT=pathlib.Path(__file__).resolve().parents[1]

def schema():
    number={'type':'number'};vec={'type':'array','items':number,'minItems':3,'maxItems':3}
    physical={'type':'object','additionalProperties':False,'required':['pivot_world_m','tip_center_world_m','driver_closed_center_world_m','rotation_axis_world','force_from_world','positive_q_world','tip_size_m','driver_size_m','initial_magnetization_force_axis','opening_s','opening_angle_rad'], 'properties':{'pivot_world_m':vec,'tip_center_world_m':vec,'driver_closed_center_world_m':vec,'rotation_axis_world':{'const':[0,0,1]},'force_from_world':{'const':[[-1,0,0],[0,0,1],[0,1,0]]},'positive_q_world':{'const':[0,1,0]},'tip_size_m':{'const':[.01,.01,.01]},'driver_size_m':{'const':[.02,.02,.02]},'initial_magnetization_force_axis':{'const':[1,0,0]},'opening_s':{'type':'number','exclusiveMinimum':0},'opening_angle_rad':{'type':'number','minimum':0,'maximum':float(np.deg2rad(65))}}}
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','additionalProperties':False,'required':['schema_version','fixture_id','source_design_family','gap_label_mm','physical','physical_coordinate_sha256','provenance'], 'properties':{'schema_version':{'const':'canonical-door-geometry-fixture-v1'},'fixture_id':{'type':'string'},'source_design_family':{'enum':['upstream-moving-driver','cloud-moving-product']},'gap_label_mm':number,'physical':physical,'physical_coordinate_sha256':{'type':'string'},'provenance':{'type':'string'}}}

def validate(fixture):
    jsonschema.validate(fixture,schema())
    if fixture['physical_coordinate_sha256']!=digest(fixture['physical']):raise ValueError('PHYSICAL_COORDINATE_HASH_MISMATCH')
    def finite(v):
        if isinstance(v,(int,float)) and not math.isfinite(v):raise ValueError('NONFINITE_GEOMETRY')
        if isinstance(v,list):
            for x in v:finite(x)
        if isinstance(v,dict):
            for x in v.values():finite(x)
    finite(fixture['physical']);return fixture

def make(side,gap):
    if side=='upstream':
        c=declared_centers(gap)['world_mm'];tip=np.array(c['tip_magnet'])/1000;driver=np.array(c['driver_magnet'])/1000
        family='upstream-moving-driver';provenance='Pinned source CAD part-center edits and declared transform; native solids not executed'
    elif side=='cloud':
        ref,_,_,_=cloud_power.normalize({'mechanics':{'installation_gap_mm':gap}});o=ref['door']['product_origin_world_mm'];q=ref['magnets']['tip_center_mm']
        tip=np.array([o[0]-q[0],o[1]+q[2],o[2]+q[1]])/1000;driver=np.array(ref['door']['driver_closed_world_mm'])/1000
        family='cloud-moving-product';provenance='Original cloud normalize/reference design coordinates; magnetic orientation remains declared force-model assumption'
    else:raise ValueError('UNKNOWN_SOURCE')
    p={'pivot_world_m':[0,0,0],'tip_center_world_m':tip.tolist(),'driver_closed_center_world_m':driver.tolist(),'rotation_axis_world':[0,0,1],'force_from_world':[[-1,0,0],[0,0,1],[0,1,0]],'positive_q_world':[0,1,0],'tip_size_m':[.01]*3,'driver_size_m':[.02]*3,'initial_magnetization_force_axis':[1,0,0],'opening_s':2.,'opening_angle_rad':float(np.deg2rad(65))}
    return validate({'schema_version':'canonical-door-geometry-fixture-v1','fixture_id':family+'-gap'+str(gap),'source_design_family':family,'gap_label_mm':gap,'physical':p,'physical_coordinate_sha256':digest(p),'provenance':provenance})

def separation(fixture,angle,q=0.):
    validate(fixture);p=fixture['physical'];pivot=np.array(p['pivot_world_m']);c,s=np.cos(angle),np.sin(angle);R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
    driver=pivot+R@(np.array(p['driver_closed_center_world_m'])-pivot);tip=np.array(p['tip_center_world_m'])+q*np.array(p['positive_q_world'])
    return np.array(p['force_from_world'])@(driver-tip)

if __name__=='__main__':
    fixtures=[];checks=[]
    for gap in (40,48,60):
        for side in ('upstream','cloud'):
            fixture=make(side,gap);fixtures.append(fixture)
            for deg in (0,5,30,65):
                for q in (-.004,0,.004):
                    angle=np.deg2rad(deg);actual=separation(fixture,angle,q);xy=upstream_native.coordinates(angle,gap) if side=='upstream' else cloud_coordinates(angle,gap)
                    expected=np.array([xy[0],0,xy[1]-q]);delta=float(np.max(abs(actual-expected)))
                    assert delta<3e-16,(side,gap,deg,q,delta)
                    checks.append({'source':side,'gap_mm':gap,'angle_deg':deg,'q_m':q,'max_abs_difference_m':delta})
    by={(f['source_design_family'],f['gap_label_mm']):f for f in fixtures}
    assert by['upstream-moving-driver',48]['physical_coordinate_sha256']==by['cloud-moving-product',48]['physical_coordinate_sha256']
    for gap in (40,60):assert by['upstream-moving-driver',gap]['physical_coordinate_sha256']!=by['cloud-moving-product',gap]['physical_coordinate_sha256']
    write(ROOT/'contracts/canonical-geometry.schema.json',schema());write(ROOT/'contracts/canonical-geometry-fixtures.json',fixtures)
    write(ROOT/'CANONICAL-GEOMETRY-RECEIPT.json',{'schema_version':'canonical-geometry-check-v1','numeric_checks':len(checks),'passed':True,'checks':checks,'matched_nominal_physical_hash':by['upstream-moving-driver',48]['physical_coordinate_sha256'],'nonnominal_families_remain_distinct':True,'magnetic_orientation':'Declared source force-model assumption; no physical magnet polarity observation','scope':'Explicit coordinate/frame/q-sign fixtures only, not complete design/native execution'})
    print(json.dumps({'numeric_checks':len(checks),'passed':True,'source_families_distinct':True}))
