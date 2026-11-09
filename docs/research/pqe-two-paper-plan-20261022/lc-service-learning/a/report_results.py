"""Present saved evidence; no scientific consumer execution."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
A=Path(__file__).resolve().parent
ROOT=A.parents[4]
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p).resolve();b=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def save(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
x=read(A/'ENGINEERING-RESULTS.json');dev=read(A/'DEVELOPMENT-TASKS.json');resources=read(A/'RESOURCE-RECEIPT.json')
# One global algebraic audit: endpoint coverage can use719 interior samples for
#43200s/60s. Avoid phase-boundary costs entirely with a background-only bound.
for entry in dev['entries']:
 task=read(entry['host_task']['path']);profile=read(entry['public']['path'])['Profile']
 assert task['service']['dark_interval_s'][1]-task['service']['dark_interval_s'][0]==43200
 assert profile['load']['powered_background_w']==2e-6
 assert profile['pmic']['maximum_voltage_v']==4.2
background=43200*2e-6
lower=2*background/(4.2**2-2.2**2)
assert abs(lower-.0135)<1e-12
save(A/'NECESSARY-BOUND-CORRECTION.json',{'package':x['package'],'at_utc':datetime.now(timezone.utc).isoformat(),
 'original':ref(A/'NECESSARY-BOUNDS.json'),'original_preserved':True,
 'issue':'floor(T/60)=720 was not a justified minimum count for the original endpoint-coverage evaluator;719 interior acquisitions can cover43200s with endpoint intervals of60s. Thus the0.09J lower bound is withdrawn.',
 'replacement':'Use only powered background for a conservative necessary bound; omit all positive acquisition, SAVE, TX, ACK, synchronization, conversion, ESR and leakage costs.',
 'dark_duration_s':43200,'powered_background_w':2e-6,'dark_background_only_minimum_j':background,
 'maximum_voltage_v':4.2,'brownout_v':2.2,'background_only_capacitance_lower_f':lower,
 'scope':'Fixed12h zero-light interval with continuous powered operation at these voltages/background. Not a global impossibility theorem; passing remains UNKNOWN.',
 'parent_maximum_usable_dark_j':.5*.012*(4.2**2-2.2**2),
 'parent_still_excluded_under_scope':.012<lower,
 'three_frozen_candidates_still_not_excluded':all(c['design']['capacitance_f']>=lower for c in read(A/'ENGINEERING-FREEZE.json')['cases'][1:]),
 'unchanged':'Cold upper-bound calculation, all frozen designs, scientific inputs, consumer, independent evaluator and all full results.',
 'additional_cheap_checks':1,'additional_full_inputs':0,
 'frozen_helper_status':'engineering.necessary_bounds retains its historical pre-run code binding; do not use its dark0.09J figure. This correction is authoritative for the report.'})
labels={'original-parent':'原父','energy-start-dark':'能源/启动/暗期','time-record-continuity':'时间/记录连续性','recovery-service':'恢复服务'}
lines=['# LC整体服务工程结果','',
'三套事前冻结的整体配置，在BOLD LC和原stage3-e3lc两个固定开发条件均通过全部11个原服务门；原父两格均失败。八格中六格为新完整仿真，两格精确复用原父结果。本结果来自已合格的构造模型，物理/硬件资格仍未建立。','',
'## 方案和结果','',
'同一单储能消费者、固定同步/采样/TX优先级、原FIFO、时钟、收费与服务。四套方案在新结果前一次冻结，无新RTC、split或调度分支。原父面积25cm²、C=12mF、ESR=8Ω、启动2.5V、棕断2.2V、NVM2048、采样60s、ACK间隔0.25s、重试45s。新方案均持久记录、ESR0.1Ω、启动2.3V、棕断2.2V、NVM4096、ACK间隔0；其余配置如下。','',
'|方案|面积cm²|C mF|采样s|重试s|BOLD|e3lc|','|---|---:|---:|---:|---:|---|---|']
frozen=read(A/'ENGINEERING-FREEZE.json')
for c in frozen['cases']:
 d=c['design'];rs=[r['verdict'] for r in x['cells'] if r['case_id']==c['id']]
 lines.append(f"|{labels[c['id']]}|{d['area_cm2']:g}|{d['capacitance_f']*1000:g}|{d['sample_period_s']:g}|{d['retry_s']:g}|{rs[0]}|{rs[1]}|")
lines += ['', '完整服务按原门合取，不按接收数量排序。不同采样周期自然产生不同记录数，因此这些数量只用于覆盖、收费和队列核对。','',
'## 服务、时间与恢复证据','',
'|方案/条件|首接收s|最大采样间隔s|暗期最大间隔s|掉电数|记录/接收|旧历史逾期|新样逾期|旧历史清空距恢复s|',
'|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for c in x['cells']:
 f=c['service_facts'];en=next(e for e in dev['entries'] if e['id']==c['entry_id']);task=read(en['host_task']['path'])
 delay=f['latest_old_history_receive_s']-task['service']['recovery_at_s']
 lines.append(f"|{labels[c['case_id']]}/{c['entry_id'].replace('development-','')}|{f['first_receive_s']:.3f}|{f['maximum_sampling_gap_s']:.3f}|{f['maximum_dark_sampling_gap_s']:.3f}|{f['brownouts']}|{f['samples']}/{f['unique_accepted_samples']}|{f['old_history_late_or_missing']}|{f['fresh_late_or_missing']}|{delay:.3f}|")
lines += ['',
'新方案首接收851.029–1269.029s，均在1800s冷启动期限内；后续及暗期最大间隔为59、55或45s，均满足60s门。零brownout使采样和已同步时钟贯穿暗期。八格已生成记录的无效/未知时间均为0；原父仍有约4.3小时的实际无采样区间，已生成记录的时间正确不能补回缺失区间。',
'',
'新方案恢复时有824–1120条旧记录待交付，全部在恢复后3.299–4.483s内交付，满足120s历史截止；新样按实际采集时间计算的10s期限全部通过。严格FIFO、无重复逻辑接收、全部采集提交、提交记录保留或接收均通过。温度误差在新方案中为0.178153–0.197625°C，原温度门和记录时间门全部通过。',
'',
'较大源面积、适中的储能与低支路损耗支持暗期持续供电；零ACK间隔使固定FIFO迅速排空。这是整套配置的联合结果，没有单因素消融，不能把收益单独归因于某个参数。最密采样配置还增加了TX与采样费用，未以免费活动换服务。','',
'## 能量与独立读回','',
'单位J；全部是原独立评估器从保存能量账本逐段求和的事实。','',
'|方案/条件|采能入储能|背景|采样+保存|TX+ACK|转换损失|ESR|溢出|',
'|---|---:|---:|---:|---:|---:|---:|---:|']
for c in x['cells']:
 e=c['independent_checks']['energy_totals_j']
 lines.append(f"|{labels[c['case_id']]}/{c['entry_id'].replace('development-','')}|{e['harvest_j']:.6f}|{e['background_j']:.6f}|{e['sense_j']+e['save_j']:.6f}|{e['tx_j']+e['ack_j']:.6f}|{e['load_conversion_j']:.6f}|{e['esr_j']:.8f}|{e['spill_j']:.6f}|")
maxclosure=max(c['independent_checks']['energy_closure_max_residual_j'] for c in x['cells'])
maxiv=max(c['independent_checks']['loaded_iv_checkpoint_max_residual_a'] for c in x['cells'])
lines += ['',f'原stdlib独立评估逐次执行CRC/接收重放、队列与最终内存重放、时钟重放、付费阶段时间、能量账本、受载IV检查与探头解析重建。八格最大逐段能量闭合残差{maxclosure:.3g}J，最大IV检查点残差{maxiv:.3g}A。每个新输入保存input/raw/assessment/public-result/readback；原父用其原始输入与原结果，另重放独立评估并逐项相等。',
'',
'## 必要界修正及适用域','',
'冻结前辅助界将43200/60=720误作最低区间内采集数；原端点覆盖规则容许719个内点，因此原0.09J下界撤回。保存原文件，另见NECESSARY-BOUND-CORRECTION.json。采用只计持续供电背景的保守下界：43200×2µW=0.0864J。给定4.2V上限与2.2V棕断，C至少0.0135F；原0.012F最多可用0.0768J，仍被这个有条件必要界排除。三套配置仍未被此界排除。',
'',
'该界限于所声明单储能、12h零光、持续供电、背景和电压假设；不覆盖整个合法域。冷启动上界使用该设计在原OFF输入电压下逐段PV计算，没有借用旧受载轨迹。辅助界不参与消费者或独立评估，修正没有改变方案、输入或任何PASS/FAIL，无补跑。',
'',
'## 使用与复现','',
'公共训练入口是public-tasks/与public-results/。原历史allowed_for_learning字段保留；当前工单明确授权两个已见开发条件。新隔离条件与初态只在a/host，形成/训练/选择不得读取，工程报告不含其任务参数和结果。',
'',
'本次可复现命令（实际已执行；运行器拒绝覆盖冻结、重复派发或重试。审计使用保存文件，若要新复跑需独立授权包）：','',
'```sh',
'rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B docs/research/pqe-two-paper-plan-20261022/lc-service-learning/a/run_engineering.py freeze',
'rtk proxy env PYTHONDONTWRITEBYTECODE=1 /Users/depengsu/.local/share/bf-agent-runtime/product-cad/bin/python -B docs/research/pqe-two-paper-plan-20261022/lc-service-learning/a/run_engineering.py engineering',
'```',
'',
'工作目录为仓库根。全部输入与源绑定见ENGINEERING-FREEZE.json，原始结果引用与逐门事实见ENGINEERING-RESULTS.json。工程新增6full，复用2，工程/两个初态合计8新full；必要界与原父复核10cheap，另加本次全局代数纠错1cheap，累计11cheap；0模型请求。两格节省工程额度退休。无新环境、工作树、备份、commit/push或全init。',
'',
'后续依赖：S0/B使用这些公共材料完成有限自动编辑/训练，冻结方法后才打开隔离评价；A在S0提供最终出口时做一次独立读回。工程通过本身尚不证明自动方法改善、迁移优势或硬件合格。']
with (A/'ENGINEERING-REPORT.md').open('x') as f:f.write('\n'.join(lines)+'\n')
# These receipts are immutable; the final receipt records the one added audit.
manifest=[]
for p in sorted(A.rglob('*')):
 if p.is_file():manifest.append(ref(p))
save(A/'A-FILE-INVENTORY.json',{'at_utc':datetime.now(timezone.utc).isoformat(),'files':manifest,
 'scope':'A-owned output only; host entries are A/S0 private; file byte totals are current resident files.'})
free=shutil.disk_usage(ROOT).free
size=sum(p.stat().st_size for p in A.rglob('*') if p.is_file())
assert free>=11_000_000_000 and size<100_000_000
save(A/'FINAL-A-RECEIPT.json',{'package':x['package'],'at_utc':datetime.now(timezone.utc).isoformat(),
 'stage':'Engineering and isolated initials complete; final method/test exit readback pending S0',
 'engineering':ref(A/'ENGINEERING-RESULTS.json'),'report':ref(A/'ENGINEERING-REPORT.md'),
 'original_resource_receipt':ref(A/'RESOURCE-RECEIPT.json'),'bound_correction':ref(A/'NECESSARY-BOUND-CORRECTION.json'),
 'new_full_inputs':resources['new_full_inputs'],'reused_prior_full':2,'cheap_checks_total':11,
 'cheap_checks_added':1,'models':0,'full_wall_s':resources['new_full_wall_s'],
 'generated_inventory':ref(A/'A-FILE-INVENTORY.json'),
 'retained_bytes_before_final_receipt':size,'A_cap_bytes':100_000_000,'free_bytes':free,
 'no_repeat_or_extra_parameter_search':True,'unused_engineering_quota_retired':2,
 'scope':'A owned engineering.py and a/** only; S0 owns root feature/progress/handoff; no root-health claim.'})
print(json.dumps({'report':ref(A/'ENGINEERING-REPORT.md'),'receipt':ref(A/'FINAL-A-RECEIPT.json'),
 'bound_correction':ref(A/'NECESSARY-BOUND-CORRECTION.json'),'storage_bytes':size,'free_bytes':free}))
