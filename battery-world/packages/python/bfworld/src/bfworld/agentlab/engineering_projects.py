"""Participant-authored projects in immutable, bounded macOS workers.

No participant build scripts, environment variables or verdicts are accepted.
CAD Python runs in an OS sandbox; readback is a separate trusted process.
"""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import resource
import signal
import struct
import subprocess
import time

from .runtime_config import CAD, SPICE, GCC, CMSIS
from .store import identity, canonical
from . import product_build, deployment, firmware_targets, nordic_sdk, stm32_l432

SCOPE = '参与者源码快照 → 隔离构建 → 独立原生读回；不等于产品功能、板级兼容或实测通过。'
SKILL = '''# 可修改工程项目
bf_engineering run engine=engineering-project parameters={assembly_revision:当前版本,project_path:"project/project.json"}。
project.json: {schema_version:"bf-engineering-project-v1",kind:"cadquery"|"spice"|"firmware-stm32l031"|"firmware-nrf52832",entrypoint:"main.py",files:["main.py"],interfaces:{units:"mm"}}。
文件路径相对 project.json 的目录，最多32个UTF-8源文件，总计2MB，禁止符号链接。源码在提交时固定，修改后使用新 operation_id。不会执行自定义 shell/build 脚本。
cadquery: units 必须 mm；Python 可 import cadquery，将 assembly.step 写到当前工作目录。原生 STEP 由另一个固定读回器检查有效实体/体积/尺寸，不采信自己的 PASS。
spice: units=SI；entrypoint 为 .cir，完整自包含网表，使用 .tran/.ac/.dc/.op。禁止 .control/.include/.lib 和外部命令。求解器生成 trace.raw，独立读取数值。此入口不保证电路工作域或机电校准，使用 event-transient 做有定义的联合模型。
firmware-stm32l031: units=SI，entrypoint为main.c，可包含项目内.h；清单中的所有.c一起编译，固定STM32L031K6、CMSIS和链接脚本。提供 Reset_Handler 所需 main；引脚/板时钟为显式工程责任，编译不能证明PCB兼容。平台独立读ELF资源，导出BIN/HEX/MAP，绝不烧录。
firmware-nrf52832: 同样接收C/H，固定nRF52832-QFAA 512KiB Flash/64KiB RAM、Cortex-M4 soft-float、4KiB栈，输出ELF/HEX/BIN/MAP和独立向量/内存读回。interfaces必须明确target="nRF52832-QFAA",softdevice=false,units="SI"。固定启动代码初始化data/bss；参与者提供int main(void)及需要的SystemInit、SysTick_Handler、IRQ0_Handler..IRQ38_Handler（实际IRQ映射参考原厂手册），自行提供外设/无线驱动。没有隐含SoftDevice、CMSIS外设头文件或无线成功声明。可将同一program.c和policy.h用于主机测试与目标构建，必须明确负载模型与目标驱动尚未实测等价；HEX存在不表示真实烧录、无线通信或功耗通过。
接口至少声明单位；项目可补充 frame、polarity、pins、clock_hz、events、load_source。它们是待验证声明，不是已验证接口。读取 job 和独立readback，失败据实修改源文件。'''
SKILL += '''\n新增公共能力（工程资源1.1.0；旧作业和旧验收不改写）：
bf_product action=assembly_schema 只读返回当前装配字段/角色/几何约束。真实薄膜尺寸保留在CAD源码；工作区包络近似显式注明。
SPICE成功作业提供project-numeric-observations.json：各plot/通道的单位、实部/虚部、最小/最大/首/末样本。只描述实际数值，不判断电路通过；读取该作业的artifact_view，不必自行猜raw格式或重复求解。
firmware-nrf52832-s132: units=SI,target="nRF52832-QFAA",sdk="17.1.0_ddde560",softdevice="S132-7.2.0",board="CUSTOM"或"PCA10040"。固定官方SDK17.1.0与GCC9.3.1、S1327.2.0、Flash0x26000、RAM0x20002ad8、8KiB栈/8KiB堆；项目需main.c、sdk_config.h，CUSTOM还需custom_board.h。固定供应商源列表和驱动、头文件由执行器提供；应用C/H由Pi提供。不执行自定义Makefile，不反汇编S132。提供应用HEX、SoftDevice HEX、合并HEX、ELF/BIN/MAP及许可证。直接ELF烧录未验证；目标构建不证明无线、传感器、引脚或功耗。
firmware-stm32l432: units=SI,target="STM32L432KCU6"，main.c可include stm32l4xx.h。固定ST官方CMSIS/启动/系统文件和Cortex-M4 soft-float，Flash256KiB，SRAM1 48KiB加SRAM2 16KiB的连续别名，4KiB栈。外设寄存器/时钟/中断由应用负责，不隐含HAL或无线栈。供应商依赖有固定源码与编译器摘要；变更时拒绝构建。
'''
KINDS = {'cadquery': CAD, 'spice': SPICE, 'firmware-stm32l031': GCC, 'firmware-nrf52832': GCC,
         'firmware-nrf52832-s132': nordic_sdk.GCC9,'firmware-stm32l432': stm32_l432.GCC}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(parameters):
    if not isinstance(parameters, dict) or set(parameters) != {'assembly_revision', 'project_path'}:
        raise ValueError('PROJECT_PARAMETERS_REQUIRED: supply exactly parameters={"assembly_revision":current_integer_revision,"project_path":"project/project.json"}; read assembly_inspect for the revision. The project kind belongs inside project.json, not parameters. No build was started.')
    if type(parameters['assembly_revision']) is not int or parameters['assembly_revision'] < 1 or not isinstance(parameters['project_path'], str):
        raise ValueError('PROJECT_PARAMETERS_INVALID')
    return parameters


def relative_file(root, name):
    if not isinstance(name, str) or not name or len(name)>200 or Path(name).is_absolute() or any(x in ('..', '.') or x.startswith('.') for x in Path(name).parts):
        raise ValueError('PROJECT_PATH_DENIED')
    p = root / name
    if not p.resolve().is_relative_to(root.resolve()) or any(x.is_symlink() for x in [p, *p.parents] if x != root.parent):
        raise ValueError('PROJECT_PATH_DENIED')
    if not p.is_file():
        raise ValueError('PROJECT_FILE_MISSING')
    return p


def request(app, owner, parameters):
    value = product_build.request(app, owner, {'assembly_revision': parameters['assembly_revision']})
    workspace = app.store.root.parent / 'participants' / owner
    path = relative_file(workspace, parameters['project_path'])
    if path.stat().st_size > 65536:
        raise ValueError('PROJECT_MANIFEST_TOO_LARGE')
    spec = json.loads(path.read_text())
    if not isinstance(spec, dict) or set(spec) != {'schema_version', 'kind', 'entrypoint', 'files', 'interfaces'} or spec['schema_version'] != 'bf-engineering-project-v1' or spec['kind'] not in KINDS:
        raise ValueError('PROJECT_SCHEMA')
    names = spec['files']
    if not isinstance(names, list) or not 1 <= len(names) <= 32 or any(not isinstance(n, str) for n in names) or len(names)!=len(set(names)) or spec['entrypoint'] not in names:
        raise ValueError('PROJECT_FILES_INVALID')
    interfaces = spec['interfaces']
    if not isinstance(interfaces, dict) or interfaces.get('units') != ('mm' if spec['kind']=='cadquery' else 'SI') or len(canonical(interfaces))>16000:
        raise ValueError('PROJECT_INTERFACE_UNITS')
    extensions={'cadquery':{'.py','.json'}, 'spice':{'.cir'}}.get(spec['kind'],{'.c','.h'})
    if spec['kind']=='firmware-nrf52832' and (interfaces.get('target')!='nRF52832-QFAA' or interfaces.get('softdevice') is not False):
        raise ValueError('PROJECT_NRF_TARGET_REQUIRED')
    if spec['kind']=='firmware-nrf52832-s132':nordic_sdk.validate_interface(interfaces)
    if spec['kind']=='firmware-stm32l432':stm32_l432.validate_interface(interfaces)
    if Path(spec['entrypoint']).suffix != {'cadquery':'.py','spice':'.cir'}.get(spec['kind'],'.c'):
        raise ValueError('PROJECT_ENTRYPOINT_TYPE')
    contents = {}; total = 0
    for name in names:
        source = relative_file(path.parent, name)
        if source.suffix not in extensions:
            raise ValueError('PROJECT_SOURCE_TYPE')
        total += source.stat().st_size
        if total > 2_000_000:
            raise ValueError('PROJECT_SOURCE_BUDGET')
        contents[name] = source.read_text()
    if spec['kind']=='spice':
        text=contents[spec['entrypoint']]
        allowed={'.param','.model','.subckt','.ends','.tran','.ac','.dc','.op','.ic','.nodeset','.options','.save','.print','.end','.temp','.func'}
        for line in text.splitlines():
            if line.strip().startswith('.') and line.strip().split()[0].lower() not in allowed:
                raise ValueError('PROJECT_SPICE_DIRECTIVE_DENIED')
    project = {'manifest':spec, 'sources':contents}
    value.update(project=project, project_sha256=identity(project), input_dimensions={k:value['assembly_hashes'][k] for k in ('physical_hash',)})
    return value


def sandbox(reads, output):
    if platform.system() != 'Darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        raise ValueError('PROJECT_SANDBOX_UNAVAILABLE')
    q=lambda p: json.dumps(str(Path(p).resolve()))
    return ('(version 1)(allow default)(deny network*) '
            '(deny file-read* (require-all (require-any (subpath "/Users") (subpath "/private") (subpath "/Volumes")) '
            '(require-not (require-any '+ ' '.join('(subpath '+q(p)+')' for p in reads)+')))) '
            '(allow file-read-metadata)(deny file-write* (require-not (require-any (subpath '+q(output)+') (subpath "/dev"))))')


def run_process(engineering, job, args, directory, output, reads, deadline):
    argv=['/usr/bin/sandbox-exec','-p',sandbox(reads,output),*map(str,args)]
    env={'PATH':str(GCC.parent)+':/usr/bin:/bin', 'HOME':str(output),'TMPDIR':str(output), 'LANG':'C', 'PYTHONDONTWRITEBYTECODE':'1', 'SPICE_ASCIIRAWFILE':'1'}
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    engineering.event(job['owner'],job['id'],'project_process_start',{'argv':list(map(str,args)), 'sandbox':'macOS-deny-network-scoped-files', 'environment':'allowlist', 'cpu_seconds':120, 'file_bytes':64*1024*1024})
    with (directory/'process.log').open('ab') as log:
        proc=subprocess.Popen(argv,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
        engineering.event(job['owner'],job['id'],'process_spawned',{'pid':proc.pid,'transport':'sandboxed-project'})
        try:
            code=proc.wait(timeout=max(1,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            raise RuntimeError('ENGINEERING_TIMEOUT')
        finally:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait()
    if code:
        raise RuntimeError('PROJECT_PROCESS_EXIT_'+str(code))


def raw_readback(path):
    """Validate every ngspice plot, including files containing .op + .tran.

    Numeric bodies have exact sizes. Metadata from a following plot is never
    interpreted as a sample, and a good first plot cannot hide a bad last one.
    """
    import io
    data=path.read_bytes()
    if not data or len(data)>64*1024*1024:raise ValueError('SPICE_RAW_SIZE')
    stream=io.BytesIO(data);plots=[]
    while stream.tell()<len(data):
        first=stream.readline()
        if not first.strip():continue
        if not first.startswith(b'Title:'):raise ValueError('SPICE_RAW_FORMAT')
        lines=[first];header_bytes=len(first)
        while True:
            line=stream.readline();header_bytes+=len(line)
            if not line or header_bytes>131072:raise ValueError('SPICE_RAW_HEADER')
            if line.strip() in (b'Values:',b'Binary:'):
                binary=line.strip()==b'Binary:';break
            lines.append(line)
        try:
            h=b''.join(lines).decode('utf-8')
            def field(name):
                found=re.findall(r'^'+re.escape(name)+r':\s*([^\r\n]*)',h,re.M)
                if len(found)!=1:raise ValueError('SPICE_RAW_HEADER')
                return found[0].strip()
            n=int(field('No. Variables'));count=int(field('No. Points'))
            flags=field('Flags').split();name=field('Plotname')
            if ('real' in flags)==('complex' in flags):raise ValueError('SPICE_RAW_FLAGS')
            complex_values='complex' in flags
            if not 0<n<1024 or not 0<count<2_000_000:raise ValueError('SPICE_RAW_SIZE')
            table=h.split('Variables:\n',1)[1] if 'Variables:\n' in h else h.split('Variables:\r\n',1)[1]
            variables=[x.split() for x in table.splitlines() if x.strip()]
            if len(variables)!=n or any(len(v)!=3 or int(v[0])!=i for i,v in enumerate(variables)):
                raise ValueError('SPICE_RAW_VARIABLES')
        except (UnicodeDecodeError,IndexError) as exc:raise ValueError('SPICE_RAW_HEADER') from exc
        factor=2 if complex_values else 1;expected=n*count*factor
        if binary:
            body=stream.read(expected*8)
            if len(body)!=expected*8:raise ValueError('SPICE_RAW_NONFINITE_OR_INCOMPLETE')
            if not all(math.isfinite(v[0]) for v in struct.iter_unpack('=d',body)):
                raise ValueError('SPICE_RAW_NONFINITE_OR_INCOMPLETE')
        else:
            for point in range(count):
                for variable in range(n):
                    line=stream.readline()
                    if not line:raise ValueError('SPICE_RAW_NONFINITE_OR_INCOMPLETE')
                    try:
                        value=line.decode('ascii').strip()
                        if variable==0:
                            index,value=value.split(None,1)
                            if int(index)!=point:raise ValueError('SPICE_RAW_POINT_INDEX')
                        parts=value.split(',')
                        if len(parts)!=factor or not all(math.isfinite(float(x)) for x in parts):
                            raise ValueError('SPICE_RAW_NONFINITE_OR_INCOMPLETE')
                    except (UnicodeDecodeError,ValueError) as exc:
                        if str(exc).startswith('SPICE_RAW_'):raise
                        raise ValueError('SPICE_RAW_NONFINITE_OR_INCOMPLETE') from exc
        plots.append({'plot_name':name,'points':count,'variables':n,
                      'complex':complex_values,'encoding':'binary' if binary else 'ascii','finite_values':True})
        if len(plots)>64:raise ValueError('SPICE_RAW_SIZE')
    if not plots:raise ValueError('SPICE_RAW_FORMAT')
    return {'points':plots[-1]['points'],'variables':plots[-1]['variables'],'plots':plots,
            'finite_values':True,'raw_sha256':digest(path),
            'scope':'Solver output integrity only; no circuit acceptance or calibration.'}


CAD_READBACK_SOURCE = 'import cadquery as cq,json,math,hashlib\nfrom pathlib import Path\np=Path("assembly.step")\nsource_sha=hashlib.sha256(p.read_bytes()).hexdigest()\ns=cq.importers.importStep(str(p)).val()\nb=s.BoundingBox()\ndimensions=[b.xlen,b.ylen,b.zlen,s.Volume()]\nassert len(s.Solids())>0 and s.isValid() and all(math.isfinite(x) and x>0 for x in dimensions)\nreport={"solid_count":len(s.Solids()),"bounds_mm":dimensions[:3],"volume_mm3":dimensions[3],"native_valid":True,"native_source_sha256":source_sha}\npreview={"available":False,"triangle_limit":200000,"source_sha256":source_sha,"attempts":[],"scope":"Visualization only; exact STEP geometry remains authoritative."}\nfor linear,angular in ((0.15,0.1),(0.3,0.2),(0.6,0.3),(1.2,0.5)):\n    # Import afresh: CadQuery/OCC retains a previous finer triangulation on the same object.\n    assert hashlib.sha256(p.read_bytes()).hexdigest()==source_sha\n    shape=cq.importers.importStep(str(p)).val()\n    try:\n        vertices,triangles=shape.tessellate(linear,angular)\n        preview["attempts"].append({"linear_tolerance_mm":linear,"angular_tolerance_rad":angular,"triangles":len(triangles)})\n        if not vertices or not triangles or len(triangles)>preview["triangle_limit"]:\n            continue\n        points=[[v.x,v.y,v.z] for v in vertices]\n        assert all(math.isfinite(x) for point in points for x in point)\n        assert all(len(face)==3 and all(isinstance(i,int) and 0<=i<len(points) for i in face) for face in triangles)\n        preview.update(available=True,linear_tolerance_mm=linear,angular_tolerance_rad=angular,triangles=len(triangles))\n        Path("preview-mesh.json").write_text(json.dumps({"vertices":points,"triangles":triangles,"units":"mm","source_sha256":source_sha,"preview_quality":preview}))\n        break\n    except Exception as error:\n        preview["attempts"].append({"linear_tolerance_mm":linear,"angular_tolerance_rad":angular,"error":str(error)[:200]})\nassert hashlib.sha256(p.read_bytes()).hexdigest()==source_sha\nreport["preview"]=preview\nPath("readback.json").write_text(json.dumps(report))\n'


def run(engineering, job, root, deadline):
    project=job['project']
    if identity(project)!=job['project_sha256']:raise ValueError('PROJECT_SNAPSHOT_TAMPER')
    src=root/'source';src.mkdir();out=root/'output';out.mkdir()
    for name,text in project['sources'].items():
        p=src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    (src/'project.json').write_text(canonical(project['manifest']))
    kind=project['manifest']['kind'];exe=KINDS[kind];entry=src/project['manifest']['entrypoint']
    reads=[root,exe.parent,exe.resolve().parent]
    if kind=='cadquery':reads+=[CAD.parent.parent, Path('/Library/Frameworks/Python.framework')]
    command=lambda args:run_process(engineering,job,args,root,out,reads,deadline)
    if kind=='cadquery':
        command([exe,entry])
        step=relative_file(out,'assembly.step')
        reader=root/'trusted_readback.py'
        reader.write_text(CAD_READBACK_SOURCE)
        command([exe,reader]);report=json.loads(relative_file(out,'readback.json').read_text())
    elif kind=='spice':
        command([exe,'-b','-r',out/'trace.raw',entry]);report=raw_readback(relative_file(out,'trace.raw'))
        from .spice_observation import observe
        (out/'numeric-observations.json').write_text(canonical(observe(out/'trace.raw')))
    elif kind in ('firmware-nrf52832-s132','firmware-stm32l432'):
        adapter=nordic_sdk if kind=='firmware-nrf52832-s132' else stm32_l432
        prepared=adapter.prepare_build(project,src,out,root)
        commands,dependencies,metadata=prepared[:3];reads+=dependencies
        for argv in commands:command(argv)
        if kind=='firmware-nrf52832-s132':
            stack,notices=prepared[3:];(out/'softdevice.hex').write_bytes(stack.read_bytes())
            report=adapter.inspect(out/'firmware.elf',out/'firmware.hex',out/'softdevice.hex')
            adapter.merged_hex(adapter.ihex(out/'firmware.hex'),adapter.ihex(out/'softdevice.hex'),out/'combined.hex')
            (src/'nrf52832_s132.ld').write_bytes((root/'nrf52832_s132.ld').read_bytes())
        else:
            notices=prepared[3];report=adapter.inspect(out/'firmware.elf',out/'firmware.hex')
            (src/'stm32l432.ld').write_bytes((root/'stm32l432.ld').read_bytes())
        (out/'vendor-license.txt').write_bytes(notices.read_bytes())
        (src/'build-apparatus.json').write_text(canonical(metadata))
        (out/'readback.json').write_text(canonical(report))
    elif kind=='firmware-nrf52832':
        startup,linker=firmware_targets.prepare_nrf(root)
        sources=[src/name for name in project['manifest']['files'] if Path(name).suffix=='.c']
        command([exe,'-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft','-Os','-std=c11',
                 '-ffreestanding','-fno-builtin','-ffunction-sections','-fdata-sections','-nostdlib',
                 '-Wl,--gc-sections','-Wl,-Map='+str(out/'firmware.map'),'-I'+str(src),
                 '-T'+str(linker),startup,*sources,'-lgcc','-o',out/'firmware.elf'])
        for fmt,name in [('binary','firmware.bin'),('ihex','firmware.hex')]:
            command([str(exe).replace('gcc','objcopy'),'-O',fmt,out/'firmware.elf',out/name])
        report=firmware_targets.inspect_nrf(out/'firmware.elf',out/'firmware.bin')
        (out/'readback.json').write_text(canonical(report))
        (src/'build-apparatus.json').write_text(canonical({'target':'nRF52832-QFAA','startup_sha256':digest(startup),
            'linker_sha256':digest(linker),'compiler':str(exe),'source':firmware_targets.NRF_SOURCE}))
        # Preserve trusted build inputs alongside participant sources for rebuild.
        (src/'startup_nrf52832.c').write_bytes(startup.read_bytes());(src/'nrf52832.ld').write_bytes(linker.read_bytes())
    else:
        # Fixed target and linker; participant controls C/H, never build commands.
        deployment.prepare(root);reads += [CMSIS]
        (root/'runtime.c').write_text('__attribute__((weak)) void __libc_init_array(void) {}\n')
        # prepare copies SDK bytes into the immutable job source area.
        sources=[src/name for name in project['manifest']['files'] if Path(name).suffix=='.c']
        command([exe,'-mcpu=cortex-m0plus','-mthumb','-Os','-std=c11','-DSTM32L031xx','-ffunction-sections','-fdata-sections','-nostdlib','-Wl,--gc-sections','-Wl,-Map='+str(out/'firmware.map'),'-I'+str(root/'cmsis'),'-I'+str(src),'-T'+str(root/'companion.ld'),*sources,root/'cmsis/system_stm32l0xx.c',root/'cmsis/startup_stm32l031xx.s',root/'runtime.c','-lgcc','-o',out/'firmware.elf'])
        for fmt,name in [('binary','firmware.bin'),('ihex','firmware.hex')]:command([str(exe).replace('gcc','objcopy'),'-O',fmt,out/'firmware.elf',out/name])
        # ELF section resource readback is independent of participant reports.
        reader=root/'elf_sizes.py'
        reader.write_text('import struct,json\nfrom pathlib import Path\nb=Path("firmware.elf").read_bytes()\nassert b[:6]==b"\\x7fELF\\x01\\x01"\nh=struct.unpack_from("<HHIIIIIHHHHHH",b,16)\nassert h[1]==40\ns=[struct.unpack_from("<10I",b,h[5]+i*h[10]) for i in range(h[11])]\nflash=sum(x[5] for x in s if x[2]&2 and x[1]!=8)\nram=sum(x[5] for x in s if x[2]&2 and x[3]>=0x20000000 and x[3]<0x30000000)\nPath("readback.json").write_text(json.dumps({"target":"STM32L031K6T6","flash_bytes":flash,"ram_static_bytes":ram,"reserved_stack_bytes":1024,"memory_fit":flash<=32768 and ram+1024<=8192,"flashed":False,"pin_binding_verified":False}))\n')
        import sys
        reads += [Path(sys.executable).resolve().parent.parent]
        command([str(Path(sys.executable).resolve()),"-S",reader]);report=json.loads(relative_file(out,'readback.json').read_text())
        if not report['memory_fit']:raise ValueError('PROJECT_MCU_MEMORY_OVERFLOW')
    # Reject symlinks and persist a complete source ZIP for reproducibility.
    import zipfile
    with zipfile.ZipFile(root/'project-source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in src.rglob('*'):
            if p.is_file():z.write(p,str(p.relative_to(src)))
    outputs=[]
    for p in out.iterdir():
        if p.is_symlink():raise ValueError('PROJECT_OUTPUT_SYMLINK')
        if p.is_file() and p.suffix in ('.step','.raw','.elf','.hex','.bin','.map','.json','.csv','.svg','.png','.txt'):
            destination=root/('project-'+p.name)
            if destination.exists():raise ValueError('PROJECT_OUTPUT_CONFLICT')
            destination.write_bytes(p.read_bytes());outputs.append({'name':destination.name,'sha256':digest(destination)})
    result={'engine':'engineering-project','kind':kind,'scope':SCOPE,'project_sha256':job['project_sha256'],
            'independent_readback':report,'outputs':outputs,'source_interfaces':project['manifest']['interfaces'],
            'interface_validation':'declared-not-verified','readback_passed':True,'product_verified':False,'hardware_verified':False}
    (root/'result.json').write_text(canonical(result))
    return result
