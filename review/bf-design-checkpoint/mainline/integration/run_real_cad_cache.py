import json,sys,pathlib
from bfworld.agentlab.simulation_chain import native
from bfworld.agentlab.simulation_chain.cache import Cache
from bfworld.agentlab.simulation_chain.contracts import file_hash,write_json
root=pathlib.Path('/workspace/shared/current-cache-integration-20261001/real-cad-cache')
cache=Cache(root/'cache');records=[]
for gap in [48,48,50]:
 p,value,key,hit=cache.stage('cad',{'gap_mm':gap,'builder_sha256':file_hash(pathlib.Path(native.__file__))},lambda d:native.cad(d,gap))
 records.append({'gap_mm':gap,'value':value,'key':key,'cache_hit':hit,'path':str(p),'step_sha256':file_hash(p/'assembly.step')})
assert [r['cache_hit'] for r in records]==[False,True,False]
assert records[0]['value']==records[1]['value'] and records[0]['step_sha256']==records[1]['step_sha256']
assert records[0]['key']!=records[2]['key']
write_json(root/'result.json',{'status':'passed','native_CAD':True,'commercial_solver_calls':0,'records':records})
print(json.dumps({'status':'passed','cases':len(records),'parts':[r['value']['parts'] for r in records],'cache_hit':[r['cache_hit'] for r in records]}))
