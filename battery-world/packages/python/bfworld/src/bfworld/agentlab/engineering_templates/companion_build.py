"""Rebuild the source-bound STM32L031 digital firmware; never flashes a device."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent
cmsis=root/'cmsis'
out=root/'build';out.mkdir(exist_ok=True)
default='/opt/ST/STM32CubeCLT_1.19.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc'
gcc=os.environ.get('ARM_GCC') or shutil.which('arm-none-eabi-gcc') or default
config=json.loads((root/'firmware-config.json').read_text()) if (root/'firmware-config.json').exists() else {'pulse_ms':100}
pulse=config['pulse_ms']
if type(pulse) is not int or not 1<=pulse<=1000:raise ValueError('FIRMWARE_PULSE_INVALID')
flags=['-DCOMPANION_PULSE_MS='+str(pulse)]
receipts=[]
def run(argv):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=60)
    receipts.append({'argv':argv,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    (out/'build-receipt.json').write_text(json.dumps(receipts,indent=2))
    result.check_returncode()
    return result.stdout
run([shutil.which('clang') or 'cc',*flags,'-std=c11','-Wall','-Wextra','-Werror',str(root/'companion_test.c'),'-o',str(out/'logic-test')])
run([str(out/'logic-test')])
run([gcc,*flags,'-mcpu=cortex-m0plus','-mthumb','-Os','-std=c11','-Wall','-Wextra','-Werror','-DSTM32L031xx',
     '-I'+str(cmsis),'-I'+str(root),'-ffunction-sections','-fdata-sections','-nostdlib','-Wl,--gc-sections',
     '-Wl,-Map='+str(out/'firmware.map'),'-T'+str(root/'companion.ld'),str(root/'companion_main.c'),
     str(cmsis/'system_stm32l0xx.c'),str(cmsis/'startup_stm32l031xx.s'),'-lgcc','-o',str(out/'firmware.elf')])
run([gcc.replace('gcc','objcopy'),'-O','binary',str(out/'firmware.elf'),str(out/'firmware.bin')])
size=run([gcc.replace('gcc','size'),str(out/'firmware.elf')])
values=[int(x) for x in size.splitlines()[-1].split()[:3]]
report={'target':'STM32L031K6T6','flash_bytes':values[0]+values[1],'ram_static_bytes':values[1]+values[2],
        'flash_limit_bytes':32768,'ram_limit_bytes':8192,'reserved_stack_bytes':1024,
        'pulse_ms':pulse,'target_compiled':True,'host_state_machine_tests_passed':True,'flashed':False,'hardware_verified':False,
        'compiler':run([gcc,'--version']).splitlines()[0],
        'sources':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and 'build' not in p.relative_to(root).parts and p.name not in ('process.log','input.json','deployment.zip')}}
report['memory_fit']=report['flash_bytes']<=32768 and report['ram_static_bytes']+1024<=8192
(out/'firmware-check.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='sources'},indent=2))
assert report['memory_fit']
