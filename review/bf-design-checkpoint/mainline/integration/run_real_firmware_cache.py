import json,subprocess,pathlib,numpy as np
from bfworld.agentlab.simulation_chain import native,solver
from bfworld.agentlab.simulation_chain.cache import Cache
from bfworld.agentlab.simulation_chain.contracts import DEFAULT,file_hash,write_json
root=pathlib.Path('/workspace/shared/current-cache-integration-20261001/real-firmware-cache');cache=Cache(root/'cache')
inputs={'config':DEFAULT['firmware'],'source_sha256':file_hash(pathlib.Path(native.__file__).with_name('program.c')),'arm_compiler':file_hash(native.GCC)}
p,v,key,hit=cache.stage('firmware',inputs,lambda d:native.firmware(d,DEFAULT['firmware']))
p2,v2,k2,hit2=cache.stage('firmware',inputs,lambda d:(_ for _ in ()).throw(AssertionError('cache missed')))
assert not hit and hit2 and v==v2 and key==k2
T=np.linspace(0,.4,4001);Z=np.zeros(len(T));V=Z+3.3
_,_,noevents=solver.execute_program(p,T,Z,Z)
_,_,events=solver.execute_program(p,T,V,V)
receiver=solver.receive(p,events,DEFAULT['link'])
assert not noevents and len(events)>0 and receiver['events']
arm=subprocess.check_output(['readelf','-h',str(p/'program-arm.o')],text=True)
assert 'ARM' in arm
(root/'arm-object-header.txt').write_text(arm)
write_json(root/'result.json',{'status':'passed','source':str(p/'program.c'),'source_sha256':file_hash(p/'program.c'),'policy_sha256':file_hash(p/'policy.h'),'arm_object_sha256':file_hash(p/'program-arm.o'),'host_library_sha256':file_hash(p/'program.dylib'),'cache_hit_second_run':hit2,'source_built_twice':'same program.c and generated policy.h built for host and Cortex-M4','arm_command':[str(native.GCC),'-mcpu=cortex-m4','-mthumb','-O2','-ffreestanding','-c','program.c','-o','program-arm.o'],'host_command':['cc','-O2','-shared','-fPIC','program.c','-o','program.dylib'],'executed_target':'Linux x86_64 host shared library, through ctypes','arm_binary_executed':False,'nrf52832_or_s132_emulation':False,'no_supply_packets':len(noevents),'powered_tx_completed':len(events),'virtual_received':len(receiver['events']),'hardware_result':False,'commercial_solver_calls':0})
print(json.dumps({'status':'passed','second_cache_hit':hit2,'no_supply_packets':len(noevents),'powered_tx_completed':len(events),'virtual_received':len(receiver['events']),'arm_executed':False}))
