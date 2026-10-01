"""Independent source-byte checks and static nodal algebra; no circuit integration."""
from pathlib import Path
import hashlib,json,struct,sys
import numpy as np
from xlrd.compdoc import CompDoc
P=Path('/workspace/shared/feasible-reference-advancement-20261001')
O=Path('/workspace/shared/next-stage-integration-review-20261001/outputs')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
acq=json.load(open(P/'sources/PUBLIC-ACQUISITION.json'))
tree=json.load(open(P/'sources/baseline/vipsn-tree.json'))
index={r['path']:r for r in tree['tree']}
blobs=[]
for r in acq['artifacts']:
 if r['status']!='read':continue
 file=P/'sources/ViPSN'/r['upstream_path'];data=file.read_bytes()
 gh=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
 ok=gh==index[r['upstream_path']]['sha'] and len(data)==index[r['upstream_path']]['size']
 assert ok
 blobs.append({'path':r['upstream_path'],'git_blob_sha1':gh,'sha256':sha(file),'bytes':len(data),'pass':ok})
def records(file):
 stream=CompDoc(file.read_bytes()).get_named_stream('FileHeader');rows=[];i=0
 while i<len(stream):
  n=int.from_bytes(stream[i:i+4],'little');i+=4
  assert n<0x1000000 and i+n<=len(stream)
  raw=stream[i:i+n];i+=n;row={}
  for field in raw.rstrip(b'\0').decode('latin1').split('|'):
   if '=' in field:k,v=field.split('=',1);row[k]=v
  rows.append(row)
 assert i==len(stream)
 return rows
selected={}
for rel in ['EEU/EEU_PSSHI/EEU_PSSHI.SchDoc','EMU/EMU_comparator/EMU_comp.SchDoc','ViPSN 1.0/EEU/circuit/SP-P-SSHI/EEU.SchDoc','ViPSN 1.0/EMU/circuit/EMU.SchDoc']:
 rows=records(P/'sources/ViPSN'/rel);parts=[]
 for i,r in enumerate(rows):
  if r.get('RECORD')!='1':continue
  children=[c for c in rows if c.get('OWNERINDEX')==str(i-1)]
  props={c.get('NAME'):c.get('TEXT') for c in children if c.get('RECORD') in ('34','41')}
  parts.append({'designator':props.get('Designator'),'comment':props.get('Comment'),'library':r.get('LIBREFERENCE'),'current_part':r.get('CURRENTPARTID','1'),'properties':props})
 selected[rel]=parts
new=selected['EEU/EEU_PSSHI/EEU_PSSHI.SchDoc']
diodes=[x for x in new if (x['designator'] or '').startswith('D')]
assert len(diodes)==6 and all(x['comment']=='NRS0240H' and x['library']=='Diode 1N4004' for x in diodes)
old=selected['ViPSN 1.0/EEU/circuit/SP-P-SSHI/EEU.SchDoc']
assert {x['comment'] for x in old if (x['designator'] or '').startswith('D')}=={'SS14','SS16'}
emu=selected['EMU/EMU_comparator/EMU_comp.SchDoc']
values={x['designator']:x['properties'] for x in emu}
R=[7.5e6,3.9e6,1.5e6]
# Independent nodal conductance matrix: nodes A=LTH and B=HTH.
G=np.array([[1/R[0]+1/R[1],-1/R[1]],[-1/R[1],1/R[1]+1/R[2]]])
gain=np.linalg.solve(G,np.array([1/R[0],0.]))
nominal={'low':1.24/gain[0],'high':1.24/gain[1]}
# Both independent input leakage currents vary across their signed corners.
shift=[]
for ia in [-10e-9,10e-9]:
 for ib in [-10e-9,10e-9]:
  dv=np.linalg.solve(G,-np.array([ia,ib]));shift.append(-dv/gain)
leak={'low':max(abs(s[0]) for s in shift),'high':max(abs(s[1]) for s in shift)}
reported=json.load(open(P/'outputs/STATIC-THRESHOLDS.json'))
assert np.isclose(nominal['high'],reported['high_V'],rtol=1e-13)
assert np.isclose(nominal['low'],reported['low_V'],rtol=1e-13)
assert np.isclose(leak['high'],reported['high_input_leakage_abs_bound_V'],rtol=1e-13)
assert np.isclose(leak['low'],reported['low_input_leakage_abs_bound_V'],rtol=1e-13)
# Assert the source component-value strings, not merely the copied threshold constants.
resistor_props={k:values[k] for k in ['Rc1','Rc2','Rc3']}
assert [resistor_props[k]['Value'] for k in ['Rc1','Rc2','Rc3']]==['7.5M','3.9M','1.5M']
out={'schema':'independent-reference-source-static-review-v1','acquired_commit':acq['commit'],'verified_public_blobs':blobs,'parsed_component_records':selected,'independent_nodal_divider':{'gain_LTH_HTH':gain.tolist(),'threshold_V':nominal,'worst_signed_input_leakage_shift_V':leak,'resistor_source_properties':resistor_props,'manufacturer_reference_range_V':[1.219,1.261],'vendor_resistor_total_recommendation_ohm':3e6,'source_total_ohm':sum(R)},'scope':'Byte identity, flat source labels and DC nodal algebra only. No board-to-paper binding, native Altium certification, part suffix identification or startup witness.','new_dynamic_runs':0,'commercial_execution':0}
(O/'REFERENCE-SOURCE-AND-NODAL-READBACK.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'blobs':len(blobs),'diodes_new_literal':'NRS0240H','diodes_new_library':'Diode 1N4004','threshold_V':nominal,'leakage_bound_V':leak,'passed':True},indent=2))
