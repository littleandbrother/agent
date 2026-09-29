#!/usr/bin/env python3
"""Build a separate nRF52832 derivative against pinned ViPSN SDK. Never flash."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
PIN='5a6b13f85c9ee8dfa40e231bae94218f9b562ac4'

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    repo=a.home/'upstream';sdk=repo/'EUU/software/beacon_version'
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    if actual!=PIN:raise ValueError('UPSTREAM_PIN_MISMATCH')
    out=a.output or a.home/'firmware';out.mkdir(parents=True,exist_ok=False)
    example=sdk/'examples/ble_peripheral/ble_app_beacon/pca10040/s132'
    shutil.copytree(example/'config',out/'config')
    shutil.copy2(example/'armgcc/ble_app_beacon_gcc_nrf52.ld',out)
    shutil.copy2(ROOT/'configs/reference_cases/door-magnetic-v1/main.c',out)
    text=(example/'armgcc/Makefile').read_text()
    text=text.replace('SDK_ROOT := ../../../../../..','SDK_ROOT := '+str(sdk)).replace('PROJ_DIR := ../../..','PROJ_DIR := .').replace('../config','config')
    # Remove unused board, button, timer and GPIO support. The actual beacon only
    # initializes the SoftDevice and enters the radio event wait loop.
    omit=['app_button.c','app_timer.c','boards.c','nrf_drv_gpiote.c','bsp.c','bsp_nfc.c','ble_conn_params.c']
    text='\n'.join(line for line in text.splitlines() if not any('/'+name in line for name in omit))+'\n'
    text=re.sub(r'(CFLAGS\s*\+=\s*)-Wall',r'\1-fstack-usage -Wall',text)
    (out/'Makefile').write_text(text)
    shutil.copy2(__file__,out/'build_pluck_firmware.py')
    compiler=shutil.which('arm-none-eabi-gcc') or '/opt/ST/STM32CubeCLT_1.19.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc'
    if not Path(compiler).is_file():raise RuntimeError('ARM_GCC_MISSING')
    gcc=Path(compiler).parent.parent
    command=['make','-j4','GNU_INSTALL_ROOT='+str(gcc)]
    r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=120)
    (out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('BUILD_FAILED: '+str(out/'build.log'))
    soft=sdk/'components/softdevice/s132/hex/s132_nrf52_3.0.0_softdevice.hex'
    shutil.copy2(soft,out/soft.name)
    elf=next((out/'_build').glob('*.out'))
    shutil.copy2(elf,out/'firmware.elf')
    nm=subprocess.check_output([str(gcc/'bin/arm-none-eabi-nm'),str(elf)],text=True)
    (out/'symbols.txt').write_text(nm)
    symbols={row[2]:int(row[0],16) for line in nm.splitlines() if len(row:=line.split())==3 and re.fullmatch('[0-9a-fA-F]+',row[0])}
    size=subprocess.check_output([str(gcc/'bin/arm-none-eabi-size'),str(elf)],text=True)
    (out/'size.txt').write_text(size)
    txt,data,bss=map(int,size.splitlines()[1].split()[:3])
    stack=symbols['__StackTop']-symbols['__StackLimit'];heap=symbols['__HeapLimit']-symbols['__HeapBase']
    frames=[]
    for su in out.rglob('*.su'):
        for line in su.read_text().splitlines():
            location,amount,kind=line.rsplit('\t',2)
            frames.append({'function':location.rsplit(':',1)[-1],'bytes':int(amount),'kind':kind})
    if not frames:raise RuntimeError('STACK_USAGE_OUTPUT_MISSING')
    resources={'text_bytes':txt,'data_bytes':data,'bss_bytes':bss,'flash_bytes':txt+data,'static_ram_bytes':data+bss,
        'stack_reserved_bytes':stack,'heap_reserved_bytes':heap,'ram_total_reserved_bytes':data+bss+stack+heap,
        'application_ram_bytes':0xcd10,'application_flash_bytes':0x61000,'linker_memory_fit':symbols['__StackLimit']>=symbols['__HeapLimit'],
        'compiler_stack_frames':sorted(frames,key=lambda x:-x['bytes']),
        'stack_scope':'Per-function compiler frames, not transitive worst-case call depth or ISR/SoftDevice high-water.',
        'runtime_peak_stack_bytes':None,'mcu_latency_ms':None,'mcu_power_mw':None,'hardware_measured':False}
    (out/'resources.json').write_text(json.dumps(resources,indent=2))
    before={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (out/'_build').glob('*') if f.suffix in ('.bin','.hex')}
    r=subprocess.run(['make','clean','GNU_INSTALL_ROOT='+str(gcc)],cwd=out,capture_output=True,text=True,timeout=30)
    if r.returncode:raise RuntimeError('REBUILD_CLEAN_FAILED')
    r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=120)
    (out/'rebuild.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('REBUILD_FAILED')
    after={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in before}
    (out/'reproducibility.json').write_text(json.dumps({'first':before,'second':after,'identical_binary':bool(before) and before==after,'scope':'clean rebuild, same pinned SDK and compiler'},indent=2))
    if not before or before!=after:raise RuntimeError('BINARY_NOT_REPRODUCIBLE')
    shutil.copy2(ROOT/'scripts/flash_pluck_firmware.py',out/'flash_pluck_firmware.py')
    (out/'pluck_receiver.py').write_text((ROOT/'scripts/pluck_receiver.py').read_text().replace('BFP1','BFD2'))
    (out/'FLASH.md').write_text('''# nRF52832 数字烧录准备（未实际烧录）

目标 nRF52832 xxAA，S132 3.0.0；应用 FLASH 起点 0x1f000，RAM 起点 0x200032f0。
使用内部 LF RC 时钟（4 秒校准，500 ppm），不要求外部 32.768kHz 晶振。PGOOD 输入为 P0.11；调试时序输出为 P0.12。必须对照原理图和实物核验；未实际烧录。
J-Link: SWDIO、SWDCLK、GND、VTref 接被测板对应引脚；VTref 是电压参考。不得从调试器反灌采能供电或把储能高压接 MCU。
1. 稳压电源/限流、极性、实物引脚和 MCU 型号核对后，再连接调试器。
2. `python flash_pluck_firmware.py --serial <J-Link序列号>` 只打印烧录计划。
3. 人工准备完成后加 `--execute`：先读取 FICR.PART 核对 0x52832，再写入协议栈和应用、逐一校验、复位。
   脚本只擦除待写扇区，不执行 eraseall/recover；原有区域冲突或读保护应停下审查。
4. 使用 pluck_receiver.py 实际接收 BFD2，分别记录启动、发包、接收；同步量测电源和掉电恢复。

ELF/BIN/HEX 构建成功不等于实际烧录成功，编译栈帧不能代替中断/协议栈动态栈峰值。
load-model.csv 来自论文阶段能量，未对本二进制测量；100ms广播含随机延迟，不能承诺精确周期。
Nordic SDK 与 SoftDevice 使用其原有许可，固定来源见 receipt.json。
''')
    (out/'load-model.csv').write_text('stage,energy_uJ,duration_ms,origin\nMCU_INIT,72.70,53.8,ViPSN paper; not binary measurement\nRADIO_INIT,68.47,13,ViPSN paper; not binary measurement\nBEACON,60.37,5,ViPSN paper; not binary measurement\n')
    files={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file() and f.suffix in ('.c','.ld','.out','.hex','.bin')}
    receipt={'target':'nRF52832 / S132 3.0.0','sdk_upstream_commit':PIN,'command':command,'compiler':subprocess.check_output([str(gcc/'bin/arm-none-eabi-gcc'),'--version'],text=True).splitlines()[0],'files':files,'flashed':False,'power_measured':False,'status':'COMPILED','receiver_contract':'0xffff manufacturer; BFD2 + 8-byte FICR device ID; 100ms ADV_NONCONN_IND; burst grouping','limitations':['Internal LF RC configured; P0.11 PGOOD and P0.12 debug need PCB binding. RF and cold-start not hardware validated.','No brownout-persistent event ID; packets may split/merge under silence grouping.','Energy surrogate comes from paper, not this binary.','Nordic SDK/SoftDevice license retained in upstream, not relicensed.']}
    receipt['resource_report']='resources.json';receipt['repeat_binary_identical']=True
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()
