"""Fixed target build adapters: no arbitrary participant scripts and no automatic flashing."""
import hashlib,json,shutil,sys,zipfile
from pathlib import Path
from .store import identity
from . import product_build
TEMPLATES=Path(__file__).with_name('engineering_templates')
from .runtime_config import GCC, CMSIS
SCOPE='STM32L031 目标编译与可审查烧录包；构建通过不代表已烧录、实物功能或功耗/延迟实测。'
SKILL='''# MCU 固件与 TinyML 部署
使用 bf_engineering run engine=mcu-firmware parameters={assembly_revision:整数}，生成现有按键/双LED功能的 STM32L031K6 C 源码、ELF/BIN/MAP、引脚说明、构建脚本与 flash_mcu.py。仅适用于记录的 PA0 按键与 PB0/PB1 LED 接线；仍需核对当前 PCB，不能假称兼容另一块板。读取 result.json 与 firmware-check.json。烧录脚本默认只输出计划，Agent 不能自动写板。
神经网络使用 tinyml-nas Skill。所有 jobs 绑定装配版本。工程成功、当前版本文件登记、板上烧录和测量必须分别确认。下载 engineering artifact 后，用 bf_product publish_file 显式提供 revision,file_path,file_kind；源码或ZIP存在不等于已经发布。
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def template_hash():
    names=['companion_build.py','companion_main.c','companion_logic.h','companion_test.c','companion.ld','flash_mcu.py','tinyml_search.py']
    return identity({**{n:sha(TEMPLATES/n) for n in names},'deployment.py':sha(Path(__file__)),'tinyml.py':sha(Path(__file__).with_name('tinyml.py')),'cmsis':sha(CMSIS/'toolchain-sources.json')})
def validate(p):
    if set(p)!={'assembly_revision'} or type(p.get('assembly_revision')) is not int or p['assembly_revision']<1:raise ValueError('ASSEMBLY_REVISION_REQUIRED')
    return p

def prepare(root):
    manifest=json.loads((CMSIS/'toolchain-sources.json').read_text());dest=root/'cmsis';dest.mkdir()
    for name,digest in manifest['files'].items():
        source=CMSIS/name
        if sha(source)!=digest:raise ValueError('CMSIS_SOURCE_HASH_MISMATCH')
        shutil.copy2(source,dest/name)
    shutil.copy2(CMSIS/'toolchain-sources.json',dest/'toolchain-sources.json')
    for name in ['companion.ld','flash_mcu.py']:shutil.copy2(TEMPLATES/name,root/name)

def command(engineering,job,root,deadline,argv):return engineering.command(job['id'],job['owner'],list(map(str,argv)),root,deadline)

def finalize(root,job,report,kind):
    manifest=dict(schema_version='bf-deployment-manifest-v1',target='STM32L031K6T6',assembly_revision=job['assembly']['revision'],assembly_hashes=job['assembly_hashes'],kind=kind,
                  model_sha256=report.get('model_sha256'),target_compiled=True,flashed=False,hardware_verified=False,
                  pin_contract={'PA0':'active-low button','PB0':'LED L','PB1':'LED R','PA13':'SWDIO','PA14':'SWCLK'},
                  source='https://www.st.com/en/microcontrollers-microprocessors/stm32l031k6.html',
                  files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name not in ('process.log','input.json','result.json','deployment-manifest.json','deployment.zip','model-host')})
    dump(root/'deployment-manifest.json',manifest)
    (root/'README.md').write_text('目标：STM32L031K6T6。当前为 '+kind+'。\n\npython3 build.py 重新构建；python3 flash_mcu.py 查看烧录计划；--list 列出探针。烧录必须明确探针序列号、目标 Device ID 和接线，使用 --execute --serial ... --expected-device-id ...。默认不写板。\n\nGPIO/PCB 接口需单独复核。Flash/RAM 是实际目标链接结果；模型延迟、功耗、单次能量未经板上测量时为空，不能用主机数据代替。\n\nTinyML 包若存在 model.c/h，为量化整数推理；profile.c 仅为测试向量板上计时固件，不是现有产品功能固件。SysTick 周期记录通过调试器读取，测量要求一次推理少于一个24位计数周期；功耗另用同步采集。\n')
    manifest['files']['README.md']=sha(root/'README.md')
    dump(root/'deployment-manifest.json',manifest)
    with zipfile.ZipFile(root/'deployment.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.name not in ('deployment.zip','process.log','model-host'):z.write(p,str(p.relative_to(root)))
    return dict(engine=kind,scope=SCOPE,assembly_revision=job['assembly']['revision'],assembly_hashes=job['assembly_hashes'],target='STM32L031K6T6',
                build=report,flashed=False,hardware_verified=False,product_verified=False,measurement_status='not_measured')

def run(engineering,job,root,deadline):
    if template_hash()!=job['template_sha256']:raise ValueError('ENGINEERING_TEMPLATE_CHANGED')
    prepare(root)
    for name in ['companion_build.py','companion_main.c','companion_logic.h','companion_test.c']:shutil.copy2(TEMPLATES/name,root/name)
    (root/'build.py').write_text('import runpy\nfrom pathlib import Path\nrunpy.run_path(str(Path(__file__).with_name("companion_build.py")),run_name="__main__")\n')
    pulse=job['assembly']['payload'].get('energy',{}).get('pulse_ms',100)
    if not isinstance(pulse,(int,float)) or not float(pulse).is_integer() or not 1<=pulse<=1000:raise ValueError('FIRMWARE_PULSE_INVALID')
    dump(root/'firmware-config.json',{'pulse_ms':int(pulse),'assembly_revision':job['assembly']['revision'],'pin_binding_verified':False})
    command(engineering,job,root,deadline,[sys.executable,root/'build.py'])
    report=json.loads((root/'build/firmware-check.json').read_text())
    for name in ['firmware.bin','firmware.elf','firmware.map','firmware-check.json','build-receipt.json']:shutil.copy2(root/'build'/name,root/name)
    return finalize(root,job,report,'product-firmware')
