"""Fixed bare-metal build apparatus, separate from participant application code."""
import struct

NRF_SOURCE = 'https://docs.nordicsemi.com/r/bundle/ps_nrf52832/page/memory.html'
NRF_LINKER = '''ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0, LENGTH = 512K
         RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 64K }
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
 .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
 .text : { *(.text*) *(.rodata*) } > FLASH
 .ARM.extab : { *(.ARM.extab*) } > FLASH
 .ARM.exidx : { *(.ARM.exidx*) } > FLASH
 .data : { _sdata = .; *(.data*) _edata = .; } > RAM AT > FLASH
 _sidata = LOADADDR(.data);
 .bss (NOLOAD) : { _sbss = .; *(.bss*) *(COMMON) _ebss = .; } > RAM
 . = ALIGN(8); _end = .;
 ASSERT(_end + 4096 <= _estack, "RAM_OVERFLOW_WITH_STACK")
}
'''


def prepare_nrf(root):
    """No implicit radio stack, peripheral configuration, or hardware qualification."""
    handlers = ['NMI_Handler','HardFault_Handler','MemManage_Handler','BusFault_Handler',
                'UsageFault_Handler','SVC_Handler','DebugMon_Handler','PendSV_Handler','SysTick_Handler']
    handlers += ['IRQ%d_Handler' % n for n in range(39)]
    prefix = '''#include <stdint.h>
extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern int main(void);
void Default_Handler(void) { for (;;) __asm volatile("wfi"); }
__attribute__((weak)) void SystemInit(void) {}
void Reset_Handler(void) {
 uint32_t *s=&_sidata; for (uint32_t *d=&_sdata;d<&_edata;) *d++=*s++;
 for (uint32_t *d=&_sbss;d<&_ebss;) *d++=0;
 *(volatile uint32_t*)0xE000ED08=0; SystemInit(); (void)main(); Default_Handler();
}
'''
    aliases = '\n'.join('void %s(void) __attribute__((weak, alias("Default_Handler")));' % n for n in handlers)
    # Reserved Cortex-M4 exceptions 7..10, then SVC/DebugMon/reserved/PendSV/SysTick.
    entries = ['(uintptr_t)&_estack','(uintptr_t)Reset_Handler'] + ['(uintptr_t)'+n for n in handlers[:5]]
    entries += ['0']*4 + ['(uintptr_t)SVC_Handler','(uintptr_t)DebugMon_Handler','0','(uintptr_t)PendSV_Handler','(uintptr_t)SysTick_Handler']
    entries += ['(uintptr_t)IRQ%d_Handler' % n for n in range(39)]
    source = prefix + aliases + '\n__attribute__((section(".isr_vector"),used)) const uintptr_t vectors[]={'+','.join(entries)+'};\n'
    (root/'nrf52832.ld').write_text(NRF_LINKER)
    (root/'startup_nrf52832.c').write_text(source)
    return root/'startup_nrf52832.c', root/'nrf52832.ld'


def inspect_nrf(elf, binary):
    """Read load addresses, vector and resources independently of application claims."""
    b=elf.read_bytes(); raw=binary.read_bytes()
    if b[:6] != b'\x7fELF\x01\x01':raise ValueError('NRF_ELF_FORMAT')
    h=struct.unpack_from('<HHIIIIIHHHHHH',b,16)
    if h[1]!=40:raise ValueError('NRF_ELF_MACHINE')
    loads=[];flash_end=0;ram_end=0x20000000
    for i in range(h[9]):
        p=struct.unpack_from('<8I',b,h[4]+i*h[8])
        typ,offset,vaddr,paddr,filesz,memsz,flags,align=p
        if typ!=1:continue
        if filesz:
            if not 0<=paddr<512*1024 or paddr+filesz>512*1024:raise ValueError('NRF_FLASH_OVERFLOW')
            flash_end=max(flash_end,paddr+filesz)
        if vaddr>=0x20000000:
            if vaddr+memsz>0x20010000:raise ValueError('NRF_RAM_OVERFLOW')
            ram_end=max(ram_end,vaddr+memsz)
        loads.append({'vaddr':vaddr,'load_address':paddr,'file_bytes':filesz,'memory_bytes':memsz})
    sp,reset=struct.unpack_from('<II',raw)
    if sp!=0x20010000 or not reset&1 or not 0<(reset&~1)<flash_end or h[3]!=reset:
        raise ValueError('NRF_VECTOR_INVALID')
    memory_fit=ram_end+4096<=0x20010000
    if not memory_fit:raise ValueError('NRF_STACK_OVERFLOW')
    return {'target':'nRF52832-QFAA','source':NRF_SOURCE,'flash_bytes':flash_end,
            'ram_static_bytes':ram_end-0x20000000,'reserved_stack_bytes':4096,'memory_fit':True,
            'initial_sp':sp,'reset_vector':reset,'load_segments':loads,'softdevice':False,
            'startup':'fixed bare-metal data/bss/vector; participant SystemInit and peripherals',
            'flashed':False,'boot_tested':False,'pin_binding_verified':False,
            'radio_verified':False,'power_model_equivalence_verified':False}
