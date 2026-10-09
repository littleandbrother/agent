"""Pinned STM32L432KCU6 CMSIS apparatus; no board or sensing qualification."""
import hashlib
import json
import struct
from pathlib import Path

from .nordic_sdk import ihex,verify_vendor_pin

VENDOR=Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/vendor')
DEVICE=VENDOR/'stm32l4-device/STMicroelectronics-cmsis-device-l4-dc04e41'
CORE=VENDOR/'stm32-core/STMicroelectronics-cmsis-core-be0e91f/Core/Include'
GCC=Path('/opt/ST/STM32CubeCLT_1.19.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc')
SOURCE='https://www.st.com/resource/en/datasheet/stm32l432kc.pdf'
FLASH=0x08000000
FLASH_END=FLASH+256*1024
RAM=0x20000000
RAM_END=RAM+64*1024
STACK=4096
# Datasheet section 3.4: SRAM1 48 KiB plus SRAM2 16 KiB alias at 0x2000c000.
# No duplicate allocation of SRAM2 through its 0x10000000 alias is permitted.
LINKER='''ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 256K
         RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 64K }
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
 .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
 .text : { *(.text*) *(.rodata*) KEEP(*(.init)) KEEP(*(.fini)) } > FLASH
 .ARM.extab : { *(.ARM.extab*) } > FLASH
 .ARM.exidx : { __exidx_start = .; *(.ARM.exidx*) __exidx_end = .; } > FLASH
 .preinit_array : { PROVIDE_HIDDEN(__preinit_array_start = .); KEEP(*(.preinit_array*)) PROVIDE_HIDDEN(__preinit_array_end = .); } > FLASH
 .init_array : { PROVIDE_HIDDEN(__init_array_start = .); KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array)) PROVIDE_HIDDEN(__init_array_end = .); } > FLASH
 .fini_array : { PROVIDE_HIDDEN(__fini_array_start = .); KEEP(*(SORT(.fini_array.*))) KEEP(*(.fini_array)) PROVIDE_HIDDEN(__fini_array_end = .); } > FLASH
 .data : { . = ALIGN(4); _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
 _sidata = LOADADDR(.data);
 .bss (NOLOAD) : { . = ALIGN(4); _sbss = .; *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; } > RAM
 . = ALIGN(8); _end = .; PROVIDE(end = .);
 ASSERT(_end + 4096 <= _estack, "RAM_OVERFLOW_WITH_STACK")
}
'''


def validate_interface(value):
    if value.get('target')!='STM32L432KCU6' or value.get('units')!='SI':
        raise ValueError('PROJECT_STM32L432_TARGET_REQUIRED')


def validate_hex(values):
    if not values or any(not FLASH<=a<FLASH_END for a in values):raise ValueError('STM32L432_FLASH_REGION')
    if min(values)!=FLASH or any(FLASH+i not in values for i in range(8)):raise ValueError('STM32L432_VECTOR_MISSING')
    sp,reset=struct.unpack('<II',bytes(values[FLASH+i] for i in range(8)))
    if sp!=RAM_END or not reset&1 or (reset&~1) not in values:raise ValueError('STM32L432_VECTOR_INVALID')
    return sp,reset


def inspect(elf,hex_path):
    values=ihex(hex_path);sp,reset=validate_hex(values);b=Path(elf).read_bytes()
    if len(b)<52 or b[:6]!=b'\x7fELF\x01\x01':raise ValueError('STM32L432_ELF_FORMAT')
    h=struct.unpack_from('<HHIIIIIHHHHHH',b,16)
    if h[1]!=40 or h[3]!=reset or h[10]!=40 or not 0<h[11]<=1024 or h[5]+h[10]*h[11]>len(b):
        raise ValueError('STM32L432_ELF_HEADER')
    allocated=[];ram_end=RAM
    for i in range(h[11]):
        s=struct.unpack_from('<10I',b,h[5]+i*h[10])
        if not s[2]&2 or not s[5]:continue
        address,size=s[3],s[5]
        if RAM<=address<RAM_END:
            if address+size>RAM_END:raise ValueError('STM32L432_RAM_OVERFLOW')
            ram_end=max(ram_end,address+size)
        elif not FLASH<=address or address+size>FLASH_END:raise ValueError('STM32L432_ALLOCATED_REGION')
        if s[1]!=8 and s[4]+size>len(b):raise ValueError('STM32L432_ELF_SECTION_SIZE')
        allocated.append({'address':address,'bytes':size})
    if ram_end+STACK>RAM_END:raise ValueError('STM32L432_STACK_OVERFLOW')
    return {'target':'STM32L432KCU6','source':SOURCE,'memory_fit':True,
        'flash_origin':FLASH,'flash_bytes':max(values)+1-FLASH,'ram_static_bytes':ram_end-RAM,
        'ram_layout':'SRAM1 48KiB and SRAM2 16KiB contiguous alias; other alias not allocated',
        'reserved_stack_bytes':STACK,'initial_sp':sp,'reset_vector':reset,'allocated_sections':allocated,
        'flashed':False,'boot_tested':False,'pin_binding_verified':False,'radio_verified':False,
        'power_model_equivalence_verified':False,'scope':'Native Cortex-M4 target build, vector and memory integrity only'}


def prepare_build(project,src,out,root):
    validate_interface(project['manifest']['interfaces'])
    acquisition=json.loads((VENDOR/'stm32l4-acquisition.json').read_text())
    if acquisition['commit']!='dc04e41afbd7c204cd09f2fa5dd29658efbaff6c' or acquisition['core']['commit']!='be0e91fb4ba19a2ee427ba8b6b75b43eb02b2810':
        raise ValueError('STM32L432_VENDOR_IDENTITY')
    sources=[DEVICE/'Source/Templates/gcc/startup_stm32l432xx.s',DEVICE/'Source/Templates/system_stm32l4xx.c']
    sources += [src/name for name in project['manifest']['files'] if Path(name).suffix=='.c']
    linker=root/'stm32l432.ld';linker.write_text(LINKER)
    runtime=root/'libc_init.c';runtime.write_text('void _init(void) {}\nvoid _fini(void) {}\n')
    flags=['-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft','-Os','-std=c11','-Wall','-Werror',
        '-DSTM32L432xx','-ffunction-sections','-fdata-sections','-fno-common',
        '-I'+str(CORE),'-I'+str(DEVICE/'Include'),'-I'+str(src)]
    commands=[[GCC,*flags,'-nostartfiles','--specs=nano.specs','--specs=nosys.specs',
        '-Wl,--gc-sections','-Wl,-Map='+str(out/'firmware.map'),'-T'+str(linker),*sources,runtime,
        '-lc','-lnosys','-lgcc','-o',out/'firmware.elf']]
    for fmt,name in [('binary','firmware.bin'),('ihex','firmware.hex')]:
        commands.append([GCC.with_name('arm-none-eabi-objcopy'),'-O',fmt,out/'firmware.elf',out/name])
    notices=DEVICE/'LICENSE.md'
    pins=[*sources[:2],DEVICE/'Include/stm32l432xx.h',DEVICE/'Include/stm32l4xx.h',
          DEVICE/'Include/system_stm32l4xx.h',CORE/'core_cm4.h',CORE/'cmsis_gcc.h',notices]
    metadata={'target':'STM32L432KCU6','device_commit':acquisition['commit'],'core_commit':acquisition['core']['commit'],
        'compiler':str(GCC),'linker_sha256':hashlib.sha256(linker.read_bytes()).hexdigest(),
        'source':SOURCE,'fixed_flags':flags,'vendor_inputs_sha256':{str(p.relative_to(VENDOR)):hashlib.sha256(p.read_bytes()).hexdigest() for p in pins}}
    metadata['vendor_pin_sha256']={key:verify_vendor_pin(VENDOR/(key+'-source-pin.json')) for key in ['stm32-device','stm32-core']}
    metadata['compiler_sha256']=hashlib.sha256(GCC.read_bytes()).hexdigest()
    return commands,[DEVICE,CORE,GCC.parent.parent],metadata,notices
