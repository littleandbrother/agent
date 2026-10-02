"""Version-bound small NAS, actual integer C parity, and MCU profile binary."""
import json,shutil
from pathlib import Path
from . import deployment,product_build
SCOPE='有界 MLP 架构搜索、INT8 权重/C 整数推理、主机一致性与 STM32L031 目标编译；MCU 延迟、功耗和产品识别效果须实测。'
SKILL='''# TinyML 模型、NAS 与指标
bf_engineering run engine=tinyml-nas parameters={assembly_revision:整数,dataset_path:"data/button.json",seed:7,epochs:200,architectures:[[4],[8],[16],[8,4],[16,8]]}。
JSON 数据约定：X[N,F] 数值，y[N] 整数标签，groups[N] 原始采集会话ID，labels 类名，features 特征名，feature_scale 正数缩放，source_kind=measured/public-dataset/synthetic-fixture，source 真实来源说明。24<=N<=20000，1<=F<=16，2..8类，至少6组，各划分必须覆盖类别。按组拆分 train/validation/test，跨划分重复样本会拒绝。原数据 SHA 与划分索引永久保存；不能伪造采集来源。
没有数据时可显式 demo=true 代替 dataset_path，只验证按键节奏流程，测试分数不代表真实识别效果。默认假设单击/双击/长按，四特征 press_1_ms,gap_ms,press_2_ms,total_ms，缩放2000。该可选任务不改变原无NN产品的验收条件。
读取 nas-candidates.json 看每个候选、参数量、MAC、权重/激活估算、验证分数、Pareto；读取 model.json/architecture.json 看实际选中结构；metrics.json含测试分数、主机时间、目标链接Flash/RAM、模型与数据哈希。只用validation选网络，test仅报告。编译的 profile.c 是板上测试向量固件，不是自动接入传感器的产品固件。
latency_ms_mcu、power_mw_mcu、energy_uj_per_inference 未测时为 null。不得把主机计时、MAC或估算标为板上实测。下载deployment.zip和测量约定；工程成功后使用publish_file明确装配revision与file_kind发布。搜索限时120秒，有限候选，不代表全局最优或正式NAS论文实验。
'''
def validate(p):
    allowed={'assembly_revision','dataset_path','demo','seed','epochs','architectures'}
    if set(p)-allowed or type(p.get('assembly_revision')) is not int or p['assembly_revision']<1:raise ValueError('TINYML_PARAMETERS_INVALID')
    if bool(p.get('demo'))==bool(p.get('dataset_path')) or ('demo' in p and type(p['demo']) is not bool):raise ValueError('TINYML_DATASET_PATH_OR_EXPLICIT_DEMO_REQUIRED')
    seed=p.get('seed',7);epochs=p.get('epochs',200);arch=p.get('architectures',[[4],[8],[16],[8,4],[16,8]])
    if type(seed) is not int or not 0<=seed<2**31 or type(epochs) is not int or not 10<=epochs<=300:raise ValueError('NAS_BUDGET_INVALID')
    if not isinstance(arch,list) or not 1<=len(arch)<=8 or any(not isinstance(a,list) or not 1<=len(a)<=2 or any(type(w) is not int or w not in (4,8,16,32) for w in a) for a in arch):raise ValueError('NAS_SEARCH_SPACE_INVALID')
    return {**p,'seed':seed,'epochs':epochs,'architectures':arch}

def request(app,owner,p):
    binding=product_build.request(app,owner,{'assembly_revision':p['assembly_revision']})
    if p.get('demo'):return {**binding,'dataset':{'demo':True}}
    base=app.store.root.parent/'participants'/owner;rel=p['dataset_path']
    if not isinstance(rel,str) or Path(rel).is_absolute() or '..' in Path(rel).parts or any(x.startswith('.') for x in Path(rel).parts):raise ValueError('DATASET_PATH_DENIED')
    path=base/rel
    if not path.resolve().is_relative_to(base.resolve()) or path.is_symlink() or not path.is_file():raise ValueError('DATASET_PATH_DENIED')
    if path.stat().st_size>4_000_000:raise ValueError('DATASET_SIZE_LIMIT')
    return {**binding,'dataset':json.loads(path.read_bytes()),'dataset_source_sha256':deployment.sha(path)}


def run(engineering,job,root,deadline):
    if deployment.template_hash()!=job['template_sha256']:raise ValueError('ENGINEERING_TEMPLATE_CHANGED')
    deployment.prepare(root);shutil.copy2(deployment.TEMPLATES/'tinyml_search.py',root/'tinyml_search.py')
    cmd=lambda args:deployment.command(engineering,job,root,deadline,args)
    cmd([product_build.CAD,root/'tinyml_search.py',root])
    model=json.loads((root/'model.json').read_text());vectors=json.loads((root/'test-vectors.json').read_text())
    x=vectors['input_q10'];y=vectors['logits_q10'];n=len(x)
    array=lambda a:'{'+','.join('{'+','.join(map(str,row))+'}' for row in a)+'}'
    (root/'parity.c').write_text('#include "model.h"\n#include <stdio.h>\n#include <time.h>\nstatic const int16_t x[%d][MODEL_INPUTS]=%s;\nstatic const int32_t expected[%d][MODEL_CLASSES]=%s;\nvolatile int sum;\nint main(void){int32_t y[MODEL_CLASSES];for(int i=0;i<%d;i++){model_logits(x[i],y);for(int j=0;j<MODEL_CLASSES;j++)if(y[j]!=expected[i][j])return 2;}clock_t start=clock();for(int i=0;i<10000;i++)sum+=model_predict(x[i%%%d]);double elapsed=(double)(clock()-start)/CLOCKS_PER_SEC;FILE*f=fopen("host-profile.json","w");if(!f)return 3;fprintf(f,"{\\"parity_vectors\\":%d,\\"parity_passed\\":true,\\"host_latency_ms\\":%%.9f,\\"scope\\":\\"host CPU process time, not MCU\\"}",elapsed*1000/10000);fclose(f);return 0;}\n'%(n,array(x),n,array(y),n,n,n))
    profile='''#include "stm32l0xx.h"
#include "model.h"
void __libc_init_array(void){}
static const int16_t samples[%d][MODEL_INPUTS]=%s;
volatile uint32_t profile_clock_hz, profile_cycles[%d], profile_done;
volatile int32_t profile_predictions[%d];
int main(void){SystemCoreClockUpdate();profile_clock_hz=SystemCoreClock;SysTick->LOAD=0xffffff;SysTick->VAL=0;SysTick->CTRL=SysTick_CTRL_ENABLE_Msk|SysTick_CTRL_CLKSOURCE_Msk;
 for(int i=0;i<%d;i++){while(SysTick->VAL==0){} uint32_t start=SysTick->VAL;profile_predictions[i]=model_predict(samples[i]);profile_cycles[i]=(start-SysTick->VAL)&0xffffff;}
 profile_done=1;for(;;){__WFI();}}
'''%(n,array(x),n,n,n)
    (root/'profile.c').write_text(profile)
    (root/'support.c').write_text('#include <stddef.h>\nvoid *memcpy(void *d,const void *s,size_t n){unsigned char *a=d;const unsigned char *b=s;while(n--)*a++=*b++;return d;}\n')
    # This exported script rebuilds the exact C model and runs host integer parity.
    build='''import json,os,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent
os.chdir(r)
gcc=os.environ.get('ARM_GCC',%r)
logs=[]
def run(argv):
 p=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=60);logs.append(dict(argv=list(map(str,argv)),exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr));(r/'build-receipt.json').write_text(json.dumps(logs,indent=2));p.check_returncode();return p.stdout
run([shutil.which('clang') or 'cc','-O2','-std=c11','-Wall','-Wextra','-Werror','model.c','parity.c','-o','model-host'])
run([r/'model-host'])
run([gcc,'-mcpu=cortex-m0plus','-mthumb','-Os','-std=c11','-Wall','-Wextra','-Werror','-DSTM32L031xx','-Icmsis','-I.','-ffunction-sections','-fdata-sections','-nostdlib','-ffreestanding','-fno-builtin','-Wl,--gc-sections','-Wl,-Map=firmware.map','-Tcompanion.ld','model.c','profile.c','support.c','cmsis/system_stm32l0xx.c','cmsis/startup_stm32l031xx.s','-lgcc','-o','firmware.elf'])
run([gcc.replace('gcc','objcopy'),'-O','binary','firmware.elf','firmware.bin'])
size=run([gcc.replace('gcc','size'),'firmware.elf']);v=[int(x) for x in size.splitlines()[-1].split()[:3]]
report=dict(target='STM32L031K6T6',target_compiled=True,flash_bytes=v[0]+v[1],ram_static_bytes=v[1]+v[2],reserved_stack_bytes=1024,flash_limit_bytes=32768,ram_limit_bytes=8192,memory_fit=v[0]+v[1]<=32768 and v[1]+v[2]+1024<=8192,flashed=False,hardware_verified=False,kind='test-vector-profile-firmware',compiler=run([gcc,'--version']).splitlines()[0])
(r/'firmware-check.json').write_text(json.dumps(report,indent=2));assert report['memory_fit']
'''%str(deployment.GCC)
    (root/'build.py').write_text(build)
    cmd([product_build.CAD,root/'build.py'])
    report=json.loads((root/'firmware-check.json').read_text());metrics=json.loads((root/'metrics.json').read_text())
    metrics.update(target_build=report,host_profile=json.loads((root/'host-profile.json').read_text()))
    metrics['firmware_sha256']=deployment.sha(root/'firmware.bin');deployment.dump(root/'metrics.json',metrics)
    deployment.dump(root/'measurement-contract.json',dict(schema_version='bf-mcu-measurement-contract-v1',model_sha256=metrics['model_sha256'],firmware_sha256=metrics['firmware_sha256'],required=['board_id','clock_hz','firmware_sha256','model_sha256','raw synchronized voltage/current and inference marker CSV','measurement equipment and calibration','repeat count','latency distribution','idle power and event integration boundary'],missing_values_are=None,scope='No measurements have been taken; template specifies required provenance.'))
    result=deployment.finalize(root,job,{**report,'model_sha256':metrics['model_sha256']},'tinyml-profile-firmware')
    result.update(metrics=metrics,nas=json.loads((root/'nas-candidates.json').read_text()),architecture=json.loads((root/'architecture.json').read_text()),scope=SCOPE)
    return result
