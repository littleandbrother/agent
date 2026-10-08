"""D5 physical application change; legacy source and D4 artifacts stay sealed."""
import shutil
from pathlib import Path
from ..door_system import native as d4
from ..simulation_chain.native import command, GCC
from ..simulation_chain.contracts import file_hash, write_json


def build(directory,design):
    base=design['base_design']
    receipt=d4.firmware(directory,base)
    shutil.copy2(Path(__file__).with_name('program.c'),directory/'program.c')
    with (directory/'policy.h').open('a') as f:
        f.write('#define BEACON_MODE '+str(int(design['application']['packet_policy']=='beacon'))+'\n')
    command(['cc','-O2','-shared','-fPIC','program.c','-o','program.dylib'],directory,'d5-host-build',30)
    command([GCC,'-mcpu=cortex-m4','-mthumb','-O2','-ffreestanding','-c','program.c','-o','program-arm.o'],directory,'d5-arm-build',30)
    receipt.update(design_id=design['design_id'],source=file_hash(directory/'program.c'),
        policy=file_hash(directory/'policy.h'),host_shared_library=file_hash(directory/'program.dylib'),
        arm_policy_object=file_hash(directory/'program-arm.o'),application_source_version='D5-pgood-start-integer-us-v2',
        packet_policy=design['application']['packet_policy'],brownout_V=1.8,
        clock_unit='integer microseconds; frozen 100us SIL tick',
        source_bound_change='PGOOD entry qualification, actual supply reset; one-shot/beacon is compiled application behavior. Integer clock fixes spurious floating accumulation ticks; declared stage durations/currents unchanged.')
    write_json(directory/'build-receipt.json',receipt)
    return receipt
