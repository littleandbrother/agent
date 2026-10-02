ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 32K
         RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 8K }
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
 .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
 .text : { *(.text*) *(.rodata*) . = ALIGN(4); } > FLASH
 .ARM.exidx : { *(.ARM.exidx*) } > FLASH
 .data : { . = ALIGN(4); _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT> FLASH
 _sidata = LOADADDR(.data);
 .bss (NOLOAD) : { . = ALIGN(4); _sbss = .; *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; } > RAM
 /DISCARD/ : { *(.comment) *(.note*) }
}
ASSERT(_ebss + 1024 < _estack, "Need at least 1 KiB stack reserve")
