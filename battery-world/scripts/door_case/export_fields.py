"""Read solved native MPH with the normal COMSOL client API and export plot nodes.
Does not change COMSOL security preferences or rerun a solver.
"""
import argparse,json,hashlib
from pathlib import Path
import mph
p=argparse.ArgumentParser();p.add_argument('model');p.add_argument('--plots',nargs='+',required=True);a=p.parse_args()
path=Path(a.model).resolve();client=mph.start(cores=2);model=client.load(path);j=model.java
records=[]
for plot in a.plots:
 for kind,suffix in [('png','png'),('gltf','glb')]:
  tag='delivery_'+plot+'_'+kind
  if tag in list(j.result().export().tags()):j.result().export().remove(tag)
  j.result().export().create(tag,plot,'Image');e=j.result().export(tag);e.set('imagetype',kind);dst=path.parent/(plot+'.'+suffix)
  e.set('pngfilename' if kind=='png' else 'gltffilename',str(dst));e.set('size','manualweb');e.set('unit','px');e.set('width','1600');e.set('height','1000');e.set('zoomextents','on');e.set('options3d','on');e.set('legend3d','on');e.set('title3d','on');e.set('imagetype',kind);print('export type',e.getString('imagetype'),flush=True);e.run()
  if not dst.exists() or dst.stat().st_size<100:raise RuntimeError('EXPORT_EMPTY: '+str(dst))
  records.append({'plot':plot,'file':dst.name,'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'bytes':dst.stat().st_size});print(dst,flush=True)
model.save(path.parent/'model-with-plots.mph');(path.parent/'plot-receipt.json').write_text(json.dumps({'source_mph_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'exports':records,'native_export':True},indent=2))
client.remove(model)
