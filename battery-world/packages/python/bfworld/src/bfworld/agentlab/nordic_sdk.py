"""Pinned Nordic SDK build support; no participant build scripts or radio verdict.

The legacy SDK was selected for the declared nRF52832 paper tasks. Its official
GCC9 example is calibrated separately. The provided S132 is never disassembled.
"""
import hashlib
import json
import re
import struct
from pathlib import Path

VENDOR=Path('/Users/depengsu/.local/share/bf-agent-runtime/reference-cases/literature-rsi-20261008/vendor')
SDK=VENDOR/'nordic-nrf5-sdk-17.1.0/source/nRF5_SDK_17.1.0_ddde560'
GCC9=VENDOR/'gcc9-source/gcc-arm-none-eabi-9-2020-q2-update/bin/arm-none-eabi-gcc'
EXAMPLE=SDK/'examples/ble_peripheral/ble_app_uart/pca10040/s132/armgcc'
FLASH_START=0x26000
RAM_START=0x20002ad8
STACK=8192
HEAP=8192


def verify_vendor_pin(path):
    """Reject dependency mutation without ever executing vendor build scripts."""
    path=Path(path);pin=json.loads(path.read_text());root=Path(pin['root']).resolve()
    for name,expected in pin['files'].items():
        p=root/name
        if p.is_symlink() or not p.resolve().is_relative_to(root) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError('FIRMWARE_VENDOR_PIN_MISMATCH')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_interface(value):
    if (value.get('target')!='nRF52832-QFAA' or value.get('softdevice')!='S132-7.2.0' or
        value.get('sdk')!='17.1.0_ddde560' or value.get('board') not in ('CUSTOM','PCA10040')):
        raise ValueError('PROJECT_NORDIC_SDK_IDENTITY_REQUIRED')


def ihex(path):
    """Strict structured HEX read; not instruction decoding or disassembly."""
    data=Path(path).read_bytes()
    if not data or len(data)>2_000_000:raise ValueError('NRF_HEX_SIZE')
    values={};upper=0;ended=False;start=None
    try:
        for line in data.decode('ascii').splitlines():
            if not line or ended or not line.startswith(':'):raise ValueError('NRF_HEX_RECORD')
            q=bytes.fromhex(line[1:])
            if len(q)<5 or len(q)!=q[0]+5 or sum(q)&255:raise ValueError('NRF_HEX_CHECKSUM_OR_SIZE')
            addr=int.from_bytes(q[1:3],'big');kind=q[3];body=q[4:-1]
            if kind==0:
                if addr+len(body)>0x10000:raise ValueError('NRF_HEX_ADDRESS')
                for i,b in enumerate(body):
                    address=upper+addr+i
                    if address in values and values[address]!=b:raise ValueError('NRF_HEX_CONFLICT')
                    values[address]=b
            elif kind==1:
                if body or addr:raise ValueError('NRF_HEX_EOF')
                ended=True
            elif kind in (2,4):
                if len(body)!=2 or addr:raise ValueError('NRF_HEX_EXTENDED_ADDRESS')
                upper=int.from_bytes(body,'big')<<(4 if kind==2 else 16)
            elif kind in (3,5):
                if len(body)!=4 or addr or start is not None:raise ValueError('NRF_HEX_START_ADDRESS')
                start=(int.from_bytes(body[:2],'big')<<4)+int.from_bytes(body[2:],'big') if kind==3 else int.from_bytes(body,'big')
            else:raise ValueError('NRF_HEX_TYPE')
    except (UnicodeError,ValueError) as exc:
        if str(exc).startswith('NRF_HEX_'):raise
        raise ValueError('NRF_HEX_FORMAT') from exc
    if not ended or not values:raise ValueError('NRF_HEX_INCOMPLETE')
    return values


def validate_memory(app,soft):
    if any(not FLASH_START<=a<0x80000 for a in app):raise ValueError('NRF_APP_FLASH_REGION')
    if min(app)!=FLASH_START or any(FLASH_START+i not in app for i in range(8)):
        raise ValueError('NRF_APP_VECTOR_MISSING')
    if any(not (0<=a<FLASH_START or 0x10001000<=a<0x10001400) for a in soft):
        raise ValueError('NRF_SOFTDEVICE_REGION')
    if set(app)&set(soft):raise ValueError('NRF_APP_STACK_OVERLAP')
    sp,reset=struct.unpack('<II',bytes(app[FLASH_START+i] for i in range(8)))
    if sp!=0x20010000 or not reset&1 or (reset&~1) not in app:raise ValueError('NRF_APP_VECTOR')
    return sp,reset


def merged_hex(app,soft,path):
    validate_memory(app,soft);data={**soft,**app};lines=[];upper=None;addresses=sorted(data);i=0
    def record(address,kind,values):
        b=bytes([len(values)])+address.to_bytes(2,'big')+bytes([kind])+bytes(values)
        lines.append(':'+(b+bytes([-sum(b)&255])).hex().upper())
    while i<len(addresses):
        address=addresses[i];high=address>>16
        if high!=upper:record(0,4,high.to_bytes(2,'big'));upper=high
        block=[data[address]];i+=1
        while i<len(addresses) and addresses[i]==address+len(block) and len(block)<16 and addresses[i]>>16==high:
            block.append(data[addresses[i]]);i+=1
        record(address&0xffff,0,block)
    record(0,1,[]);Path(path).write_text('\n'.join(lines)+'\n')
    if ihex(path)!=data:raise ValueError('NRF_MERGE_READBACK')


def inspect(elf,app_hex,stack_hex):
    app=ihex(app_hex);soft=ihex(stack_hex);sp,reset=validate_memory(app,soft)
    b=Path(elf).read_bytes()
    if len(b)<52 or b[:6]!=b'\x7fELF\x01\x01':raise ValueError('NRF_SDK_ELF_FORMAT')
    h=struct.unpack_from('<HHIIIIIHHHHHH',b,16)
    if h[1]!=40 or h[3]!=reset or h[10]!=40 or not 0<h[11]<=1024 or not 0<=h[12]<h[11] or h[5]+h[10]*h[11]>len(b):
        raise ValueError('NRF_SDK_ELF_HEADER')
    sections=[struct.unpack_from('<10I',b,h[5]+i*h[10]) for i in range(h[11])]
    strings=sections[h[12]]
    if strings[4]+strings[5]>len(b):raise ValueError('NRF_SDK_ELF_SECTIONS')
    strings=b[strings[4]:strings[4]+strings[5]];allocated=[];ram_end=RAM_START
    for s in sections:
        if not s[2]&2 or not s[5]:continue
        if s[0]>=len(strings):raise ValueError('NRF_SDK_ELF_SECTIONS')
        name=strings[s[0]:].split(b'\0',1)[0].decode('ascii')
        if s[3]>=0x20000000:
            if not RAM_START<=s[3] or s[3]+s[5]>0x20010000:raise ValueError('NRF_SDK_RAM_OVERFLOW')
            if name not in ('.stack','.heap'):ram_end=max(ram_end,s[3]+s[5])
        elif not FLASH_START<=s[3] or s[3]+s[5]>0x80000:raise ValueError('NRF_SDK_FLASH_OVERFLOW')
        allocated.append({'name':name,'address':s[3],'bytes':s[5]})
    if ram_end+STACK+HEAP>0x20010000:raise ValueError('NRF_SDK_STACK_HEAP_OVERFLOW')
    return {'target':'nRF52832-QFAA','sdk':'17.1.0_ddde560','softdevice':'S132-7.2.0',
        'memory_fit':True,'application_flash_origin':FLASH_START,'application_ram_origin':RAM_START,
        'flash_bytes':max(app)+1-FLASH_START,'ram_static_bytes':ram_end-RAM_START,
        'reserved_stack_bytes':STACK,'reserved_heap_bytes':HEAP,'initial_sp':sp,'reset_vector':reset,'allocated_sections':allocated,
        'load_format':'Intel HEX only; ELF PT_LOAD header-alignment prefix is not qualified for direct flashing',
        'radio_verified':False,'pin_binding_verified':False,'boot_tested':False,'flashed':False,
        'power_model_equivalence_verified':False,'scope':'Native SDK target build/map only'}


def lists():
    """Parse fixed vendor data, never a participant Makefile."""
    text=(EXAMPLE/'Makefile').read_text()
    def block(name):
        match=re.search(r'^'+name+r'\s*\+=\s*(.*?)(?=\n\s*\n)',text,re.M|re.S)
        if not match:raise ValueError('NRF_SDK_VENDOR_LIST')
        return [x for x in re.sub(r'\\\n',' ',match.group(1)).split() if x!='\\']
    def resolve(name):
        if not name.startswith('$(SDK_ROOT)/'):raise ValueError('NRF_SDK_VENDOR_PATH')
        p=SDK/name[len('$(SDK_ROOT)/'):]
        if '..' in p.relative_to(SDK).parts or not p.exists():raise ValueError('NRF_SDK_VENDOR_PATH')
        return p
    sources=[resolve(n) for n in block('SRC_FILES') if n!='$(PROJ_DIR)/main.c']
    # Common peripheral drivers; macros in the immutable sdk_config enable them.
    for name in ['modules/nrfx/drivers/src/nrfx_twim.c','modules/nrfx/drivers/src/nrfx_twi.c',
                 'integration/nrfx/legacy/nrf_drv_twi.c','modules/nrfx/drivers/src/nrfx_saadc.c',
                 'modules/nrfx/drivers/src/nrfx_timer.c','modules/nrfx/drivers/src/nrfx_spim.c',
                 'integration/nrfx/legacy/nrf_drv_spi.c','modules/nrfx/drivers/src/nrfx_spi.c']:
        p=SDK/name
        if not p.is_file():raise ValueError('NRF_SDK_DRIVER_MISSING')
        if p not in sources:sources.append(p)
    includes=[resolve(n) for n in block('INC_FOLDERS') if n not in ('$(PROJ_DIR)','../config')]
    return sources,includes


def prepare_build(project,src,out,root):
    """Return fixed argv lists for the existing bounded OS worker."""
    manifest=project['manifest'];validate_interface(manifest['interfaces'])
    if 'sdk_config.h' not in project['sources'] or (manifest['interfaces']['board']=='CUSTOM' and 'custom_board.h' not in project['sources']):
        raise ValueError('NRF_SDK_CONFIG_OR_CUSTOM_BOARD_REQUIRED')
    calibration=VENDOR/'nordic-nrf5-sdk-17.1.0/calibration-gcc9-complete-layout/result.json'
    q=json.loads(calibration.read_text())
    if q['status']!='PASS' or not GCC9.is_file():raise ValueError('NRF_SDK_CALIBRATION_REQUIRED')
    sources,includes=lists();sources+=[src/name for name in manifest['files'] if Path(name).suffix=='.c']
    linker=root/'nrf52832_s132.ld';linker.write_bytes((EXAMPLE/'ble_app_uart_gcc_nrf52.ld').read_bytes())
    objects=out/'objects';objects.mkdir();commands=[];names=[]
    defines=['APP_TIMER_V2','APP_TIMER_V2_RTC1_ENABLED','BOARD_'+manifest['interfaces']['board'],'CONFIG_GPIO_AS_PINRESET',
             'FLOAT_ABI_HARD','NRF52','NRF52832_XXAA','NRF52_PAN_74','NRF_SD_BLE_API_VERSION=7','S132','SOFTDEVICE_PRESENT',
             '__HEAP_SIZE=8192','__STACK_SIZE=8192']
    flags=['-mcpu=cortex-m4','-mthumb','-mabi=aapcs','-mfloat-abi=hard','-mfpu=fpv4-sp-d16','-Os','-g',
           '-Wall','-Werror','-ffunction-sections','-fdata-sections','-fno-strict-aliasing','-fno-builtin','-fshort-enums']
    for i,source in enumerate(sources):
        obj=objects/(str(i)+'.o');names.append(obj)
        commands.append([GCC9,*flags,*['-D'+n for n in defines],*['-I'+str(n) for n in [src,*includes]],'-c',source,'-o',obj])
    commands.append([GCC9,*flags,'-L'+str(SDK/'modules/nrfx/mdk'),'-L'+str(root),'-T'+str(linker),
        '-Wl,--gc-sections','-Wl,-Map='+str(out/'firmware.map'),'--specs=nano.specs',*names,'-lc','-lnosys','-lm','-lgcc','-o',out/'firmware.elf'])
    for fmt,name in [('binary','firmware.bin'),('ihex','firmware.hex')]:
        commands.append([GCC9.with_name('arm-none-eabi-objcopy'),'-O',fmt,out/'firmware.elf',out/name])
    stack=SDK/'components/softdevice/s132/hex/s132_nrf52_7.2.0_softdevice.hex'
    notices=SDK/'documentation/nRF5_Nordic_license.txt'
    metadata={'target':'nRF52832-QFAA','sdk':'17.1.0_ddde560','softdevice':'S132-7.2.0','compiler':str(GCC9),
        'board':manifest['interfaces']['board'],'fixed_flags':flags,'vendor_inputs_sha256':{str(p.relative_to(SDK)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources if p.is_relative_to(SDK)},
        'linker_sha256':hashlib.sha256(linker.read_bytes()).hexdigest(),'calibration_sha256':hashlib.sha256(calibration.read_bytes()).hexdigest(),
        'stack_sha256':hashlib.sha256(stack.read_bytes()).hexdigest(),'license_notice_sha256':hashlib.sha256(notices.read_bytes()).hexdigest()}
    metadata['vendor_pin_sha256']=verify_vendor_pin(VENDOR/'nordic-source-pin.json')
    metadata['compiler_sha256']=hashlib.sha256(GCC9.read_bytes()).hexdigest()
    return commands,[SDK,GCC9.parent.parent],metadata,stack,notices
