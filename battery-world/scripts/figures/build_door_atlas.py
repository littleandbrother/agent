"""E2 source-bound 70-panel plan and immutable publication for the door case.

This script assembles existing/native-new data; it never changes a verdict.
The generic Agent renderer consumes exactly the same declarative figure plan.
"""
import argparse,csv,hashlib,json,shutil,sys
from pathlib import Path
import numpy as np
from bfworld.agentlab.scientific_figures import SCHEMA,validate_plan
from bfworld.agentlab.scientific_renderer import render
from scripts.door_case.build_evidence_dossier import verify_inputs

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def writecsv(p,rows):
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def build(e1,root,reference):
 e1,root,reference=map(Path,(e1,root,reference));verify_inputs(e1/'inputs')
 root.mkdir(parents=True,exist_ok=True);data=root/'figure-inputs';data.mkdir(exist_ok=True)
 plan={'schema_version':SCHEMA,'title':'门动作磁耦合压电节点 · 六组学术证据 E2','version':'E2',
  'conclusion':'已形成可追溯的设计与仿真图组；基线、方向修改和新电容候选均未完成冷启动。图像供应、数值检查、产品验收和 Agent 自主复现分别记录。',
  'limitations':['无实物或烧录测量。','D2 机械与 D3.3 电子采购修订未完成整机回装；SIL 与目标固件能耗未证等价。','磁场网格与旋转域确认仍不充分。','参考文献只用于表达组织，未将参考照片和数据作为本产品结果。'],
  'sources':[],'groups':[]}
 sourcepaths={};allorigins={}
 def source(sid,p,units=None,origin='derived-analysis',scope='Derived from preserved source; no new physical qualification.'):
  p=Path(p);name=sid+p.suffix;target=data/name
  if target.exists() and sha(target)!=sha(p):target.unlink()
  shutil.copyfile(p,target);entry={'id':sid,'path':name,'sha256':sha(target),'columns':units or {},'origin':origin,'scope':scope}
  plan['sources'].append(entry);sourcepaths[sid]=target;allorigins[sid]=str(p);return sid
 def generated(sid,rows,units=None,scope='Computed from specified source values; not measured.'):
  p=root/'analysis'/(sid+'.csv');writecsv(p,rows);return source(sid,p,units,scope=scope)
 inputs=e1/'inputs';mech=inputs/'engineering/mechanical-D2';electronics=inputs/'engineering/electronics-D3'
 design=json.loads((mech/'design.json').read_text());spec=json.loads((inputs/'review/frozen-baseline/design-spec.json').read_text())
 source('design',mech/'design.json',origin='engineering-geometry',scope='D2 design assumptions, original input values; no dimensional metrology.')
 source('render_receipt',root/'mechanics/render-receipt.json',origin='engineering-geometry',scope='Exact native CAD source hashes and declared presentation transformations.')
 views={v['name'][:-4]:v for v in json.loads((root/'mechanics/render-receipt.json').read_text())['views']}
 landmark={k:v.get('landmarks',{}) for k,v in views.items()}
 for p in sorted((root/'mechanics').glob('*.png')):source(p.stem,p,origin='engineering-geometry',scope='Exact CAD geometry. Cut/explosion are display transforms; dynamic shape is first-mode projection, not FEM.')
 waveunits={'time_s':'s','tip_m':'m','velocity_m_s':'m/s','piezo_V':'V','storage_V':'V','supply_V':'V','pgood_V':'V'}
 for sid,p in [('baseline',inputs/'review/frozen-baseline/waveform.csv'),('orientation',inputs/'review/orientation-v3/joint/waveform.csv')]:source(sid,p,waveunits,'native-simulation','Native LTspice joint calculation with unqualified magnetic ROM; source run receipt is preserved.')
 source('program',inputs/'review/orientation-v3/joint/program.csv',{'time_s':'s','supply_V':'V','pgood_V':'V','state':'1','current_A':'A'},'software-in-loop','Actual C SIL driven by failed power waveform. Program state numbers follow program.c; not a measured MCU trace.')
 source('program_definition',inputs/'review/orientation-v3/firmware/build-receipt.json',origin='software-in-loop',scope='Host and ARM object compilation receipt; not a flashable SIL firmware or measured current.')
 source('target_resources',inputs/'engineering/firmware-D2-final/resources.json',origin='software-in-loop',scope='Separate D2 target build resource report; not evidence that SIL load equals hardware firmware load.')
 source('analysis_receipt',root/'analysis/analysis-receipt.json',scope='Operator-controlled analyses; 0 external model calls; frozen apparatus unchanged.')
 source('control_summary',root/'analysis/control-summary.csv',{'polarity':'1','opening_s':'s','resistance_ohm':'ohm','peak_tip_mm':'mm','peak_voltage_V':'V','resistor_energy_J':'J','relative_energy_residual':'1'})
 summary=list(csv.DictReader((root/'analysis/control-summary.csv').open()))
 for polarity in (1,-1):
  for opening in (.25,2.):
   sub=[r for r in summary if int(r['polarity'])==polarity and float(r['opening_s'])==opening]
   generated(f'sweep_p{polarity}_t{opening:g}'.replace('-','n').replace('.','_'),sub,{'resistance_ohm':'ohm','resistor_energy_J':'J','peak_voltage_V':'V','peak_tip_mm':'mm'})
   for resistance in (1e5,1e6):
    name=f'rom-p{polarity}-t{opening:g}-r{resistance:g}';sid=f'control_p{polarity}_t{opening:g}_r'+('1e05' if resistance==1e5 else '1e06');sid=sid.replace('-','n').replace('.','_')
    source(sid,root/'analysis'/(name+'.csv'),{'time_s':'s','tip_m':'m','velocity_m_s':'m/s','piezo_V':'V','resistor_J':'J','damping_J':'J','magnetic_work_J':'J','stored_J':'J'},scope='SciPy resistive ROM control. Shared nominal magnetic model; no PMIC or application verdict.')
 source('force_grid',root/'analysis/force-grid.csv',{'angle_deg':'deg','tip_mm':'mm','force_N':'N'},scope='Nominal uniform-charge magnetic table, no full trajectory FEM confirmation.')
 source('cycle',root/'analysis/loading-cycle.csv',{'time_s':'s','angle_deg':'deg','tip_m':'m','piezo_V':'V','potential_J':'J','driver_work_J':'J','beam_work_J':'J','energy_residual_J':'J'},scope='Prescribed closing/opening cycle, nominal potential reaction work. Not measured input or converter efficiency.')
 source('cycle_receipt',root/'analysis/loading-cycle.json',scope='Potential-gradient reciprocal checks and sampled reaction-energy residual. Same assumptions, not independent physical validation.')
 for pol in (1,-1):
  rows=[r for r in csv.DictReader((root/'analysis/equilibria.csv').open()) if int(r['polarity'])==pol]
  generated('eq_'+('same' if pol==1 else 'reversed'),rows,{'angle_deg':'deg','q_mm':'mm','effective_stiffness_N_m':'N/m'},scope='Sampled static ROM equilibria inside ±8mm; no global bistability claim.')
 source('cap_bounds',root/'analysis/capacitor-bounds.csv',{'capacitance_uF':'uF','uvlo_3_77_J':'J','uvlo_5_05_J':'J'},scope='Ideal 1/2 C V² at stated thresholds. Omits ESR, conversion and load losses; not a component recommendation.')
 source('native_caps',root/'analysis/native-cap-summary.csv',{'cin_uF':'uF','peak_tip_mm':'mm','peak_piezo_V':'V','peak_storage_V':'V','peak_supply_V':'V','tx_completed':'1','received_events':'1'},'native-simulation','Four fresh LTspice + C SIL runs; all zero initial electrical storage, no diagnostic input, same unqualified magnetic model.')
 native=[]
 for c in (22,47,100,220):
  d=root/'analysis'/f'native-cin-{c}';r=json.loads((d/'receipt.json').read_text());native.append(r)
  if r['status']!='completed':raise ValueError('NATIVE_CANDIDATE_NOT_COMPLETED:'+str(c))
  source('cap'+str(c),d/'waveform.csv',waveunits,'native-simulation','Fresh nominal joint run, cold cache, 180° driver polarization, no initial electrical charge. Not hardware.')
 # Derived facts link both primary JSONs rather than relabeling controls as native.
 baseline=json.loads((inputs/'review/frozen-baseline/result.json').read_text())
 reverse=json.loads((inputs/'review/orientation-v3/native-result.json').read_text())
 generated('polarity_comparison',[{'candidate':name,**{k:value['metrics'][k] for k in ('peak_tip_mm','peak_piezo_V','peak_storage_V','peak_supply_V','tx_completed','received_events')}} for name,value in [('原方向',baseline),('驱动反向',reverse)]],{'peak_tip_mm':'mm','peak_piezo_V':'V','peak_storage_V':'V','peak_supply_V':'V','tx_completed':'1','received_events':'1'},'Preserved native results; operator exploratory intervention, not Pi decision.')
 generated('recompute',[{'candidate':'保存 47 µF','VIN_V':reverse['metrics']['peak_storage_V'],'VOUT_V':reverse['metrics']['peak_supply_V']},{'candidate':'新算 47 µF','VIN_V':native[1]['metrics']['peak_storage_V'],'VOUT_V':native[1]['metrics']['peak_supply_V']}],{'VIN_V':'V','VOUT_V':'V'},'Cold native re-execution versus preserved same candidate; two runs, no statistical distribution.')
 energies=[]
 for name,p in [('原方向',inputs/'review/frozen-baseline/energy.json'),('驱动反向',inputs/'review/orientation-v3/joint/energy.json')]:
  e=json.loads(p.read_text())
  for k,label in [('initial_mechanical_piezo_J','初始储能'),('external_force_work_J','磁力净功'),('mechanical_loss_J','阻尼耗散'),('pmic_port_energy_J','PMIC 端口'),('final_mechanical_piezo_J','末态储能')]:energies.append({'candidate':name,'term':label,'energy_J':e[k]})
 generated('energy_terms',energies,{'energy_J':'J'},'Signed mechanical/piezo ledger; missing internal PMIC loss prevents whole-system efficiency claim.')
 for sid,p in [('schematic',electronics/'pcb/schematic.png'),('pcb_combined',electronics/'pcb/pcb-combined.png'),('pcb_top',electronics/'pcb/pcb-top.png'),('pcb_bottom',electronics/'pcb/pcb-bottom.png'),('pinmap',electronics/'pcb/pin-map.png')]:
  if p.exists():source(sid,p,origin='schematic',scope='D3.3 sourced package/netlist/SES copper drawing; independent checks, no native ERC/DRC or RF qualification.')
 for kind in ('nominal','weak-slow','no-motion'):
  source('d3_'+kind.replace('-','_'),electronics/'power'/kind/'waveform.csv',{'time_s':'s','storage_voltage_V':'V','supply_voltage_V':'V','pgood_V':'V','load_current_A':'A'},'native-simulation','Separate D3.3 one-way Norton PMIC calculation; not the coupled closed-loop candidate.')
 source('power_receipt',electronics/'power/report.json',origin='native-simulation',scope='Preserved D3.3 raw hashes, inductor DCR and failed startup; not mechanical back-action validation.')
 pcb=json.loads((electronics/'pcb/routing-checks.json').read_text())
 generated('routing_checks',[{'check':'断网','result':str(len(pcb['unconnected'])),'scope':'独立二维检查'},{'check':'铜间距违规','result':str(len(pcb['clearance_violations'])),'scope':'独立二维检查'},{'check':'最小间距','result':f"{pcb['minimum_clearance_mm']:.4f} mm",'scope':'未做原生 DRC'},{'check':'最窄铜线','result':f"{pcb['minimum_trace_width_mm']:.4f} mm",'scope':'未做射频验证'}],scope='Independent 2D copper/net checks from source report. Native ERC/DRC remain unknown.')
 procurement=json.loads((electronics/'bom/procurement-receipt.json').read_text())
 source('procurement',electronics/'bom/procurement-receipt.json',origin='schematic',scope='JLC catalogue snapshot checked 2026-10-03. Stock may change; assembly qualification and purchase are false.')
 generated('bom_table',[{'LCSC':r['code'],'型号':r['mpn'],'用量':r['quantity'],'库存快照':r['stock']} for r in procurement['records']],scope='JLC available catalogue snapshot; no purchase or manufacturing release.')
 generated('dimensions',[{'部件':name,'尺寸 (mm)':value,'依据':scope} for name,value,scope in [('门','900 × 2100 × 40','输入假设'),('铜梁','100 × 10 × 0.53','原生 CAD'),('PZT','50 × 8 × 0.30','原生 CAD'),('梁端磁体','10 × 10 × 10','原生 CAD'),('驱动磁体','20 × 20 × 20','原生 CAD'),('PCB','80 × 30 × 1.6','原生 CAD')]],scope='Original D2 source dimensions. No dimensional measurement.')
 rb=json.loads((mech/'cad-readback.json').read_text())
 generated('cad_dimensions',[{'部件':p['id'],'X (mm)':f"{p['size_mm'][0]:.2f}",'Y (mm)':f"{p['size_mm'][1]:.2f}",'Z (mm)':f"{p['size_mm'][2]:.2f}"} for p in rb['parts'] if p['id'] in ('housing','lid','beam','pzt','tip_magnet','driver_magnet','main_pcb')],scope='Independent OCCT readback; housing extent includes mounting flange and differs from envelope dimensions.')
 generated('revision_gaps',[{'对象':'机械 D2','变化':'旧无线占位','状态':'原生 CAD 可读'},{'对象':'电子 D3.3','变化':'E73 无线模块','状态':'未回装验证'},{'对象':'SIL','变化':'主机状态程序','状态':'对象编译完成'},{'对象':'目标固件 D2','变化':'nRF52832 / S132','状态':'未烧录或测功耗'}],scope='Revision boundaries are intentional; no assembled-device equivalence claim.')
 resource=json.loads((inputs/'engineering/firmware-D2-final/resources.json').read_text())
 generated('firmware_resources',[{'项':'应用 Flash','字节':resource['flash_bytes']},{'项':'静态 RAM','字节':resource['static_ram_bytes']},{'项':'栈预留','字节':resource['stack_reserved_bytes']},{'项':'堆预留','字节':resource['heap_reserved_bytes']}],{'字节':'B'},'Actual target resource report; linker fit is not worst-case runtime RAM or power validation.')
 generated('firmware_builds',[{'工程':'主机 SIL','文件':'program.dylib','范围':'供電行为模型'},{'工程':'ARM SIL','文件':'program-arm.o','范围':'仅对象文件'},{'工程':'目标应用 D2','文件':'nrf52832_xxaa.hex','范围':'可烧录文件未烧录'},{'工程':'目标应用 D2','文件':'main.c / sdk_config.h','范围':'独立目标源码'}],scope='Build paths from immutable source receipts; target HEX and SIL object are different engineering products.')
 f=spec['firmware'];generated('stage_energy',[{'阶段':name,'包络能量_J':3.3*f[time]*f[current]*1e-6} for name,time,current in [('BOOT','boot_ms','boot_mA'),('INIT','init_ms','init_mA'),('TX','tx_ms','tx_mA')]],{'包络能量_J':'J'},'Declared constant stage-current envelope at 3.3 V; not measurement or arbitrary firmware energy.')
 diagnostic=Path('/Users/depengsu/Documents/bf-agent-workbench/simulation-chain/runs/diagnostic-01')
 dr=json.loads((diagnostic/'result.json').read_text());ds=json.loads((diagnostic/'design-spec.json').read_text())
 if not ds['circuit']['diagnostic_input_A'] or not dr['metrics']['diagnostic_only']:raise ValueError('DIAGNOSTIC_NOT_IDENTIFIED')
 for name in ('program.csv','receiver.json','waveform.csv','design-spec.json','result.json'):
  expected=next((a['sha256'] for a in dr['artifacts'] if a['name']==name),None)
  if expected and sha(diagnostic/name)!=expected:raise ValueError('DIAGNOSTIC_SOURCE_CHANGED')
 source('diagnostic_program',diagnostic/'program.csv',{'time_s':'s','state':'1','current_A':'A','supply_V':'V','pgood_V':'V'},'software-in-loop','External 1mA supply diagnostic from preserved run; cannot count as self-powered success.')
 rx=json.loads((diagnostic/'receiver.json').read_text());times=np.linspace(0,4,801)
 generated('diagnostic_events',[{'time_s':t,'TX':sum(e['time_s']<=t for e in rx['transmitted']),'RX':sum(e['first_packet_s']<=t for e in rx['events'])} for t in times],{'time_s':'s','TX':'1','RX':'1'},'External-supply virtual RX control; first packet time of post-hoc silence group, not online recognition time. No cross-reboot identity validation.')
 generated('zero_events',[{'time_s':t,'TX':0,'RX':0} for t in [0,1,2,3,4]],{'time_s':'s','TX':'1','RX':'1'},'Orientation native receiver.json and result both contain zero completed TX and zero events.')
 generated('native_residual',[{'电容 (µF)':str(c),'残差':r['metrics']['energy_ledger']['relative_residual']} for c,r in zip((22,47,100,220),native)],{'残差':'1'},'Actual mechanical/piezo residual, not full PMIC energy balance.')
 cr=json.loads((root/'analysis/loading-cycle.json').read_text());generated('gradient_checks',[{'样点':str(i+1),'相对误差':r['relative_error']} for i,r in enumerate(cr['gradient_checks'])],{'相对误差':'1'},'Numerical derivative of the same potential against charge-force model, not independent FEM.')
 for sid,p in [('field',inputs/'engineering/simulation/magnetic-D2-final/field.png'),('stress',inputs/'engineering/simulation/beam-v4/stress.png'),('displacement',inputs/'engineering/simulation/beam-v4/displacement.png')]:
  source(sid,p,origin='native-simulation',scope='Existing native COMSOL export. Fixed 0° magnet anchor or 0.3N linear static beam; not actual whole-door transient field.')
 # The joint baseline owns the precise confirmation result, not a visually guessed field tolerance.
 confirmation=next((r for r in (inputs/'review').rglob('magnetic-confirmation.json')),None)
 if confirmation is None:
  confirmation=Path('/Users/depengsu/.local/share/bf-agent-runtime/studies/door-integration-pilot-20261002/mapping-cache/simulation-cache-v2/magnetic-confirmation/abde94f5c494c728147f88330e7ea6a8c8a9cea2558ecf333dcdb63936fc3e49/magnetic-confirmation.json')
 mc=json.loads(confirmation.read_text())
 dump(root/'analysis/magnetic-confirmation.json',mc);source('magnetic_confirmation',root/'analysis/magnetic-confirmation.json',origin='native-simulation',scope='Frozen native confirmation result; failed mesh criterion cannot be relabelled as pass.')
 meshchange=mc.get('mesh_relative_change',mc.get('mesh_delta',mc.get('mesh_force_relative_change')))
 if meshchange is None:
  numbers=[v for k,v in mc.items() if 'mesh' in k and isinstance(v,(float,int))]
  if len(numbers)!=1:raise ValueError('MAGNETIC_MESH_METRIC_AMBIGUOUS')
  meshchange=numbers[0]
 generated('magnetic_mesh',[{'确认':'固定锚点','相对变化':meshchange}],{'相对变化':'1'},'Two native mesh anchors; criterion5%, not full rotation-domain qualification.')
 generated('control_domain',[{'候选':str(i+1),'peak_tip_mm':r['peak_tip_mm'],'status':r['status']} for i,r in enumerate(summary)],{'peak_tip_mm':'mm'},'Finite resistive controls; >=8mm denotes model boundary, not device impossibility.')
 generated('requirements',[{'条件':'门角 / 开门时间','固定值':'65° / 2s'},{'条件':'初始电储能','固定值':'0 V'},{'条件':'外加诊断电流','固定值':'0 A（诊断单列）'},{'条件':'任务结果','固定值':'至少一个完整接收事件'},{'条件':'磁场 / 梁范围','固定值':'0–65° / ±8 mm'}],scope='Frozen nominal task; rendering never relaxes requirements or numerical settings.')
 references=json.loads((reference/'atlas-index.json').read_text());dump(root/'analysis/reference-logic.json',{'counts':references['counts'],'papers':[{k:v for k,v in p.items() if k in ('id','title','doi','url')} for p in references['papers']],
  'organization':['场景 → 功能装配 → 内部机制','结构改变 → 对照输入 → 性能','储能 → 电源 → 程序 → 应用','可信度 → 适用范围 → 可复算档案'],'reference_only':True})
 source('reference_logic',root/'analysis/reference-logic.json',origin='reference-literature',scope='Local 250-panel reference index; literature expression only, no transplanted TENG results.')
 # Figure construction helpers keep every panel a question with provenance.
 def group(order,title,question,conclusion,limitations):
  g={'order':order,'title':title,'question':question,'conclusion':conclusion,'limitations':limitations,'columns':2,'panels':[]};plan['groups'].append(g);return g
 def panel(g,title,question,caption,kind,deps,**extra):
  label=chr(97+len(g['panels']));p={'id':str(g['order'])+label,'label':label,'title':title,'question':question,'caption':caption,'evidence_kind':kind,'dependencies':deps,'status':'available',**extra};g['panels'].append(p);return p
 def image(g,title,sid,caption,annotate=False):
  p=panel(g,title,'这个视图怎样解释 '+title+'？',caption,'native-render' if sid in ('field','stress','displacement') else 'engineering-view',[sid,'render_receipt'] if sid in landmark else [sid],type='image',source=sid)
  if annotate and sid in landmark:
   tags=[('clamp_upper','Clamp',.03,.12),('pzt','PZT',.37,.07),('tip_magnet','Tip magnet',.65,.13),('main_pcb','PCB D2',.05,.89),('driver_magnet','Driver',.72,.62)]
   if sid=='pzt':tags=[('clamp_upper','Clamp',.02,.11),('pzt','PZT: 50 × 8 mm',.31,.08)]
   if sid.startswith('state-'):tags=[('clamp_upper','Fixed',.03,.10),('tip_magnet','Tip',.51,.10),('driver_magnet','Driver',.75,.75)]
   p['annotations']=[{'label':label,'x':x,'y':y,'to':landmark[sid][name]} for name,label,x,y in tags if all(0<v<1 for v in landmark[sid].get(name,[]))]
  if sid in views and views[sid].get('ortho_width_m'):
   length_mm=200 if sid=='installation' else 10 if sid in ('clamp','pzt') else 20
   p['scale_bar']={'fraction':length_mm/1000/views[sid]['ortho_width_m'],'label':str(length_mm)+' mm'}
  return p
 def line(g,title,series,xlabel,ylabel,caption,**extra):
  return panel(g,title,'在共同条件下，'+ylabel+'怎样随'+xlabel+'变化？',caption,'numeric-result',list(dict.fromkeys(s['source'] for s in series)),type='line',series=series,x_label=xlabel,y_label=ylabel,**extra)
 def ser(sid,x,y,xu,yu,label=None):return {'source':sid,'x':x,'y':y,'x_unit':xu,'y_unit':yu,**({'label':label} if label else {})}
 def bar(g,title,sid,x,y,unit,caption,**extra):return panel(g,title,'这些条件是否得到不同的真实计算结果？',caption,'numeric-result',[sid],type='bar',source=sid,x=x,y=y,y_unit=unit,y_label={'peak_piezo_V':'压电幅值','VIN_V':'储能峰值','received_events':'接收事件数','字节':'资源','包络能量_J':'包络能量','残差':'相对残差','相对误差':'相对误差','相对变化':'网格差','peak_tip_mm':'最大梁端位移','已有':'已有子图数'}.get(y,y),**extra)
 def table(g,title,sid,columns,caption):
  compact={'dimensions':{'columns':['部件','尺寸 (mm)'],'rows':4},'cad_dimensions':{'columns':['部件','X (mm)','Y (mm)'],'rows':4},'revision_gaps':{'columns':['对象','状态'],'rows':4},'routing_checks':{'columns':['check','result'],'rows':4},'bom_table':{'columns':['LCSC','型号'],'rows':3},'firmware_builds':{'columns':['工程','范围'],'rows':4}}
  labels={'check':'检查','result':'结果','scope':'范围','X (mm)':'X/mm','Y (mm)':'Y/mm','Z (mm)':'Z/mm','尺寸 (mm)':'尺寸/mm'}
  return panel(g,title,'哪些输入、检查与版本信息支持这个结论？',caption,'engineering-record',[sid],type='table',source=sid,columns=columns,column_labels=labels,compact=compact.get(sid,{'columns':columns,'rows':4}))
 def diagram(g,title,labels,caption,deps):
  nodes=[{'id':str(i),'label':label,'x':.04+(i%2)*.5,'y':.70-(i//2)*.34,'width':.40,'height':.22} for i,label in enumerate(labels)]
  return panel(g,title,'功能和信息沿什么路径传递？',caption,'illustration',deps,type='diagram',nodes=nodes,edges=[{'from':str(i),'to':str(i+1)} for i in range(len(nodes)-1)])
 def missing(g,title,reason,deps):return panel(g,title,'什么证据尚不足以支持这项结论？',reason,'gap',deps,status='missing',reason=reason)
 g=group(1,'产品、安装与功能装配','产品装在哪里，真实尺寸怎样约束内部设计？','D2 CAD 已有可打开装配和尺寸；D3.3 电路没有完成整机回装。',['所有尺寸为设计值。','爆炸与剖切仅用于说明，板上元件不得由空白 CAD 板推断。'])
 for title,sid,caption,anno in [('门上安装','installation','真实门和节点 CAD；门尺寸900×2100×40mm，视图为规定闭合姿态。',False),('安装局部','installation-detail','节点固定于门楣；驱动磁体随门运动，夹具和位置按 D2 坐标。',False),('功能剖切','section','壳体沿 y=0 做显示剖切；铜梁、PZT、端部磁体、PCB 可分辨。',True),('功能爆炸','exploded','仅分离原生 CAD 部件以解释装配；展示间距不属于设计尺寸。',True),('固定端细节','clamp','夹具和螺钉来自原生 CAD；约束模型仍是理想固支。',False),('PZT 布局','pzt','50×8×0.3mm PZT 贴于100×10×0.53mm铜梁；黏接尚无测试。',True),('正交侧视','side','同一原生装配侧视，磁体驱动与梁端高差不是随意摆放。',False),('正交俯视','top','80×30mm PCB、夹具和梁的安装关系；板上为 D2 几何占位。',False)]:image(g,title,sid,caption,anno)
 diagram(g,'功能与资源路径',['门动作 / 磁力','梁 / 压电端口','储能 / PMIC','程序 / 接收'], '功能路径示意；最后一环是任务目标，不是已实现自供能结果。',['design'])
 table(g,'输入尺寸','dimensions',['部件','尺寸 (mm)','依据'],'尺寸来自设计源，不写成实测尺寸。')
 table(g,'原生几何回读','cad_dimensions',['部件','X (mm)','Y (mm)','Z (mm)'],'实际壳体Y外廓含安装法兰，不能只沿用62mm盒体宽度。')
 table(g,'整机修订边界','revision_gaps',['对象','变化','状态'],'电子、机械、SIL和目标固件分开列出；未证整机等价。')
 g=group(2,'加载、释放与机电转换','一次门动作怎样改变磁力、梁响应和压电端口？','有真实返回轨迹和名义磁力分析；加载效率与全旋转 FEM 仍未充分确认。',['动态梁形为一阶投影，不是三维瞬态 FEM。','磁相互作用与电阻控制共享未充分确认的模型。'])
 for i,t in enumerate((0,.05,.12,.25)):image(g,f'{t:g}s 同视角状态','state-'+str(i),f'规定门角和该时刻返回的梁端位移；形状为一阶投影，时间和比例在所有状态一致。',i==0)
 generated('door_angle',[{'time_s':t,'angle_deg':65*min(t/2,1)} for t in np.linspace(0,4,401)],{'time_s':'s','angle_deg':'deg'},'Prescribed input, not returned measurement.')
 line(g,'规定门输入',[ser('door_angle','time_s','angle_deg','s','deg')],'时间','门角','规定0–65°、2s开门，随后保持；不是优化变量。')
 line(g,'联合求解位移',[ser('orientation','time_s','tip_m','s','mm')],'时间','梁端位移','方向修改后的原生联合求解，零初始电储能。')
 line(g,'联合求解速度',[ser('orientation','time_s','velocity_m_s','s','m/s')],'时间','梁端速度','与位移、电压取自同一次求解；时间轴0–4s。')
 line(g,'压电端电压',[ser('orientation','time_s','piezo_V','s','V')],'时间','压电电压','压电端电压尚不能直接证明输出端启动。')
 panel(g,'名义磁力工作域','输入角度和梁位移怎样共同改变磁力？','均匀磁化电荷表的原方向 Fz；不是FEM场图。','numeric-result',['force_grid'],type='heatmap',source='force_grid',x='angle_deg',y='tip_mm',z='force_N',x_unit='deg',y_unit='mm',z_unit='N',x_label='门角',y_label='梁端位移',z_label='磁力')
 line(g,'静态平衡路径',[ser('eq_same','angle_deg','q_mm','deg','mm','原方向'),ser('eq_reversed','angle_deg','q_mm','deg','mm','驱动反向')],'门角','平衡位移','采样静态ROM根；无采样折叠不证明全球无多稳态。')
 line(g,'完整加载循环功',[ser('cycle','time_s','driver_work_J','s','uJ','驱动磁体'),ser('cycle','time_s','beam_work_J','s','uJ','作用于梁')],'时间','累计功','闭门、保持、开门的规定轨迹；驱动反力功来自同一势能模型，非测得门输入。')
 image(g,'原生磁场锚点','field','COMSOL固定姿态磁场；仅对应保存模型，不代表所有旋转角或磁力已校准。')
 g=group(3,'受控修改与设计比较','哪些可实现修改进入了计算，哪些仍只是未建模设想？','方向和电容修改改变返回值；新4个电容候选仍均无完整TX/RX。',['电阻控制不等于PMIC全链路。','不将最高储能电压作为唯一成功指标；有限扫描不证明全局不可行。'])
 bar(g,'磁方向与压电幅值','polarity_comparison','candidate','peak_piezo_V','V','相同用户动作、储能和程序配置；方向修改由操作者执行，不是Pi自主选择。')
 line(g,'电阻控制的能量',[ser('sweep_p1_t2','resistance_ohm','resistor_energy_J','Mohm','uJ','原方向'),ser('sweep_pn1_t2','resistance_ohm','resistor_energy_J','Mohm','uJ','驱动反向')],'电阻','电阻吸收能量','3档阻值，开门2s；明确的电阻端能量，非DC可用能量。',x_scale='log')
 line(g,'原方向控制波形',[ser('control_p1_t2_r1e05','time_s','piezo_V','s','V','0.1 MΩ'),ser('control_p1_t2_r1e06','time_s','piezo_V','s','V','1 MΩ')],'时间','压电电压','同一原方向ROM，改变真实电阻负载；不更改阻尼参数。')
 line(g,'反向控制波形',[ser('control_pn1_t2_r1e05','time_s','piezo_V','s','V','0.1 MΩ'),ser('control_pn1_t2_r1e06','time_s','piezo_V','s','V','1 MΩ')],'时间','压电电压','对应反向磁化名义模型，实际数据决定是否越界。')
 line(g,'输入时间敏感性',[ser('sweep_pn1_t0_25','resistance_ohm','resistor_energy_J','Mohm','uJ','0.25s'),ser('sweep_pn1_t2','resistance_ohm','resistor_energy_J','Mohm','uJ','2s')],'电阻','控制端能量','0.25s仅作环境敏感性控制；不能由Agent改变正式2s要求来获分。',x_scale='log')
 line(g,'方向与静态储能',[ser('baseline','time_s','tip_m','s','mm','原方向'),ser('orientation','time_s','tip_m','s','mm','驱动反向')],'时间','梁端位移','分别来自两次原生计算，初始预载也随方向改变；不能假定输入能量相同。')
 line(g,'原生电容波形',[ser('cap'+str(c),'time_s','storage_V','s','V',str(c)+' µF') for c in (22,47,100,220)],'时间','储能电压','相同2s门动作，4次冷缓存重算；Cout100µF，初始0V，无外加源。')
 line(g,'电容与供电峰值',[ser('native_caps','cin_uF','peak_supply_V','uF','uV')],'输入电容','MCU供电峰值','µV级输出尚未跨过3.2V冷启动；不把VIN变化当任务成功。')
 bar(g,'保存与冷缓存重算','recompute','candidate','VIN_V','V','同一47µF候选保存与新算一致；仅2次结果，不添加虚构误差条。')
 line(g,'储能阈值的理想下界',[ser('cap_bounds','capacitance_uF','uvlo_3_77_J','uF','uJ','3.77V'),ser('cap_bounds','capacitance_uF','uvlo_5_05_J','uF','uJ','5.05V')],'电容','理想储能需求','覆盖10–4700µF；E=½CV²。不把文献大电容直接当成当前器件推荐。',x_scale='log',y_scale='log')
 bar(g,'真实应用结果','polarity_comparison','candidate','received_events','1','两次方向候选均0个接收事件，保留零轴；未实现产品目标。')
 missing(g,'新释放结构的正例','尚无锁扣/撞击/多稳态等新结构的原生工程与校准结果；不把瞬间撤去磁力的诊断写成可制造机构。',['design','analysis_receipt'])
 g=group(4,'电路、PCB 与供电','采能、电容、电源与无线模块如何实际连接？','已有有依据的D3.3连接和铜线；原生ERC/DRC、射频与整机回装没有通过记录。',['D3.3电源图是单向Norton诊断，与联合运行严格分开。','库存为2026-10-03快照，不等于当前可下单或可装配。'])
 for title,sid in [('完整原理图','schematic'),('PCB 真实铜线','pcb_combined'),('PCB 顶层','pcb_top'),('PCB 底层','pcb_bottom')]:image(g,title,sid,'D3.3源器件、网络、封装和SES铜线的绘图；不是原生EDA验收。')
 line(g,'闭环储能与启动',[ser('orientation','time_s','storage_V','s','V')],'时间','输入储能电压','同一联合候选；5.05V标作该模型阈值参考，不改变判定。',thresholds=[{'value':5.05,'label':'UVLO参考'}])
 line(g,'闭环 PGOOD',[ser('orientation','time_s','pgood_V','s','V')],'时间','PGOOD','来自原生联合模型；未置高，不虚构启动时刻。数值漏电保持原值，在0–3.3V逻辑范围显示。',ylim=[0,3.3])
 line(g,'D3.3 独立电源诊断',[ser('d3_nominal','time_s','storage_voltage_V','s','V','名义'),ser('d3_weak_slow','time_s','storage_voltage_V','s','V','弱慢'),ser('d3_no_motion','time_s','storage_voltage_V','s','V','无动作')],'时间','储能电压','三次真实LTspice单向诊断，含0.18Ω电感DCR；不与闭环波形合并为同一计算。')
 table(g,'独立铜线检查','routing_checks',['check','result','scope'],'二维网表/铜线审查通过项原样记录；不能推导原生DRC与制造通过。')
 table(g,'JLC 器件快照','bom_table',['LCSC','型号','用量','库存快照'],'11种器件、14件用量；保留LCSC编号和实际MPN，库存时间2026-10-03。')
 table(g,'电子与机械变化','revision_gaps',['对象','变化','状态'],'80×30板框保留，但无线封装变化需回装、射频与热检查。')
 diagram(g,'电源与事件接口',['压电 / PZ1,PZ2','LTC3588 / 储能','VOUT / PGOOD','MCU / 无线'], '从实际源网表归纳的接口图，箭头不表示已经完成启动。',['power_receipt','design'])
 missing(g,'原生 EDA 与射频验收','原生ERC/DRC未记录，PCB制造与射频性能未验证；零飞线及二维铜线检查不能替代。',['procurement','power_receipt'])
 g=group(5,'程序、能耗与事件服务','电源何时允许程序执行，最终是否产生正确接收事件？','失败供电下程序保持RESET、TX/RX为0；外加电流诊断验证独立程序链，不是自供能成功。',['阶段电流来自假设包络；不是新二进制的实测能耗。','SIL与独立目标工程不是同一可烧录镜像；接收分组不证明跨重启事件语义。'])
 diagram(g,'SIL 状态与门控',['RESET / 掉电','BOOT / 启动','WAIT → INIT','TX → SLEEP'],'C状态逻辑的公开示意；实际电压门限与PGOOD参与转移。',['program_definition'])
 diagram(g,'目标固件路径',['电源/PGOOD输入','nRF52 / S132','BLE 广播事件','休眠 / 等待'], '独立D2目标源工程的组织，未烧录；门磁任务无需虚构训练数据或NAS结果。',['target_resources'])
 line(g,'失败候选程序状态',[ser('program','time_s','state','s','1')],'时间','SIL 状态','0=RESET；无启动。与同一候选波形逐时对应，不展开虚构后续时序。',ylim=[-.1,5.1],yticks=[{'value':0,'label':'RESET'},{'value':3,'label':'INIT'},{'value':5,'label':'SLEEP'}],drawstyle='steps-post')
 line(g,'失败候选负载',[ser('program','time_s','current_A','s','uA')],'时间','SIL 电流','实际C状态输出的模型负载，RESET也耗电；不称实测MCU电流。')
 bar(g,'目标构建资源','firmware_resources','项','字节','KiB','来自目标HEX的资源记录；静态RAM与栈/堆预留分列，非运行高水位。')
 table(g,'两个构建边界','firmware_builds',['工程','文件','范围'],'可烧录HEX属于D2目标固件，ARM SIL只是对象文件；保持区分。')
 bar(g,'阶段能耗假设','stage_energy','阶段','包络能量_J','uJ','3.3V×声明的电流×阶段时间，只用于负载模型；不是测功耗或latency证据。')
 line(g,'电容与完整发送',[ser('native_caps','cin_uF','tx_completed','uF','1')],'输入电容','完整 TX 数','4次新联合计算均0完整TX，按真实零值绘制。',ylim=[0,1],yticks=[{'value':0,'label':'0'},{'value':1,'label':'1'}])
 line(g,'候选发送与接收',[ser('zero_events','time_s','TX','s','1','TX'),ser('zero_events','time_s','RX','s','1','RX')],'时间','累计事件数','方向候选返回零事件；不生成无线波形来冒充接收证据。',ylim=[0,1],yticks=[{'value':0,'label':'0'},{'value':1,'label':'1'}],drawstyle='steps-post')
 line(g,'外加源诊断状态',[ser('diagnostic_program','time_s','state','s','1')],'时间','SIL 状态','明确外加1mA的独立诊断，验证状态链可达；与自供能候选分开。',ylim=[-.1,5.1],yticks=[{'value':0,'label':'RESET'},{'value':3,'label':'INIT'},{'value':5,'label':'SLEEP'}],drawstyle='steps-post')
 line(g,'外加源虚拟接收',[ser('diagnostic_events','time_s','TX','s','1','TX'),ser('diagnostic_events','time_s','RX','s','1','RX')],'时间','累计事件数','完整TX才能产生报文；外加源控制和静默分组接收，不能当产品通过。')
 missing(g,'跨重启正确事件语义','尚无物理门动作真值、跨重启事件身份、重复动作和时限完整检查；有一个接收组不足以证明正确且唯一的服务。',['program_definition'])
 g=group(6,'数值可信度、范围与交付','这些图的来源、可计算范围和复算边界能否逐项审查？','来源和数据可追溯；数值一致性不自动证明物理充分性，原生磁场确认仍未过门槛。',['本轮新增0模型调用，属于工程/表达工作，不是自主复现成绩。','静态场与动态ROM、主机程序与目标固件、来源完整性与产品可用性均分开。'])
 bar(g,'机电能量残差','native_residual','电容 (µF)','残差','1','4次真实机械/压电能量账残差；PMIC内部损耗不可独立观察，不能声称全系统闭账。')
 bar(g,'势能导数互核','gradient_checks','样点','相对误差','1','4个规定样点：势能导数与磁力同模型一致；不构成独立物理确认。',y_scale='log')
 line(g,'加载循环账差',[ser('cycle','time_s','energy_residual_J','s','uJ')],'时间','势能与功的账差',f'8001采样点，归一化残差{cr["sampled_energy_relative_residual"]:.3%}。仍是同名义磁体模型的数值核查。')
 image(g,'原生静力应力','stress','COMSOL0.3N静载和理想固支，保存结果；根部奇异峰值不能直接做强度认证。')
 image(g,'原生静力位移','displacement','同一静载场，不冒充真实门瞬态；变形显示倍率和单位以原生图图例为准。')
 bar(g,'磁场网格未达标','magnetic_mesh','确认','相对变化','%','固定姿态网格差超过5%门槛；不因图像漂亮而宣称已校准。',thresholds=[{'value':5,'label':'5%门槛'}])
 bar(g,'控制工作域','control_domain','候选','peak_tip_mm','mm','12个规定电阻控制，对照±8mm边界；越界不等于器件不可行。',thresholds=[{'value':8,'label':'ROM边界'}],tick_rotation=90)
 # Counts below are finalized after the two last panels are declared.
 bar(g,'子图供应与缺项','coverage','图组','已有','1','这里只统计预先声明的70张子图中是否有对应来源；不等于复现、设计或硬件成功率。')
 diagram(g,'可审查交付链',['输入 / 哈希','逐图 / 记录','图 / 数据','原生工程 / 缺项'],'所有图组、PDF/SVG/CSV、报告和数据绑定同一档案；原生大文件回执与复算范围另记。',['analysis_receipt','reference_logic'])
 missing(g,'实物与寿命确认','没有已连接实物，尚缺电流/电压测量、真实广播接收、制造公差、疲劳和环境寿命数据；不可生成假实拍或误差条。',['design','analysis_receipt'])
 generated('coverage',[{'图组':str(g['order']),'已有':sum(p['status']=='available' for p in g['panels']),'缺项':sum(p['status']=='missing' for p in g['panels'])} for g in plan['groups']],{'已有':'1','缺项':'1'},'Predeclared source-panel supply only; no reproduction-success inference.')
 for g in plan['groups']:
  refs={1:['abyss-1a','rattle-1e','pump-1d'],2:['road-3b','rattle-4a','abyss-1f'],3:['pump-4b','mo-4j','road-2j'],4:['mo-4g','abyss-5c','pump-3h'],5:['mo-5e','ids-2g','road-4l'],6:['mo-4d','abyss-4g','road-4i']}[g['order']]
  g['reference_panels']=refs
  for p in g['panels']:p['reference_panels']=refs
 validate_plan(plan)
 if sum(len(g['panels']) for g in plan['groups'])!=70:raise ValueError('PANEL_PLAN_EXPECTED_70')
 dump(data/'plan.json',plan);dump(root/'origin-map.json',allorigins)
 out=root/'report';out.mkdir(exist_ok=True);shutil.copyfile(Path(__file__).parents[2]/'packages/python/bfworld/src/bfworld/agentlab/scientific_renderer.py',out/'scientific_renderer.py')
 result=render(data/'plan.json',out)
 print(json.dumps(result['counts']),flush=True);return result

def publish(root,owner,state,version='E2',complete_archive=False,publication_output=None):
 from types import SimpleNamespace
 from bfworld.agentlab.store import Store
 from bfworld.agentlab.product_results import ProductResults
 from scripts.figures.verify_scientific_atlas import verify
 root=Path(root);verify(root);catalog=ProductResults(SimpleNamespace(store=Store(Path(state))))
 index=json.loads((root/'report/figure-index.json').read_text());sources=json.loads((root/'report/figure-sources.json').read_text());lookup={s['id']:s for s in sources}
 def file(path):return {'path':path,'sha256':sha(root/path),'name':path.replace('/','--')}
 groups=[]
 for g in index['groups']:
  panels=[];paths={'report/'+g[k] for k in ('figure','pdf','vector')};paths.add(f"report/figure-{g['order']}-sources.zip")
  for p in g['panels']:
   copies={'figure':'report/'+p['figure'],'pdf':'report/'+p['pdf'],'svg':'report/'+p['vector'],'provenance':'report/'+p['provenance']}
   records=[{**{k:v for k,v in lookup[s].items() if k!='archive_file'},'published_path':'report/'+lookup[s]['archive_file']} for s in p['dependencies']]
   deps=[s['published_path'] for s in records];paths.update(copies.values());paths.update(deps)
   panels.append({**{k:v for k,v in p.items() if k not in ('vector','figure','pdf','provenance','dependencies')},**copies,'dependencies':deps,'source_records':records})
  story={k:g[k] for k in ('order','title','question','conclusion','limitations','reference_panels')}
  story.update(baseline_id='door-product-evidence',baseline_version=version,baseline_source_identity=index['source_identity'],source_identity=index['source_identity'],figure='report/'+g['figure'],
   baseline_conclusion=index['conclusion'],component_summary='D2 CAD / D3.3 electronics / separate target firmware / joint SIL; no product or hardware acceptance.',dependencies=sorted(paths),panels=panels)
  groups.append({'id':'figure-'+str(g['order']),'domain':{1:'mechanical',2:'mechanical',3:'system',4:'circuit',5:'firmware',6:'system'}[g['order']],
   'title':g['title'],'kind':'scientific-figures','scope':'Source-bound figure story; product not verified.','design_status':'insufficient_evidence','metrics':{'panels_available':sum(p['status']=='available' for p in panels),'panels_missing':sum(p['status']=='missing' for p in panels)},'evidence_story':story,'files':[file(p) for p in sorted(paths)]})
 for domain,folders in [('mechanical',['inputs/engineering/mechanical-D2','inputs/engineering/animation-D2','inputs/engineering/simulation','mechanics']),('circuit',['inputs/engineering/electronics-D3']),('firmware',['inputs/engineering/firmware-D2-final']),('system',['inputs/review','analysis'])]:
  paths=sorted({str(p.relative_to(root)) for folder in folders for p in (root/folder).rglob('*') if p.is_file()})
  groups.append({'id':domain+'-sources','domain':domain,'title':{'mechanical':'原生CAD、Blender与COMSOL','circuit':'D3.3原理图、铜线、BOM和电源','firmware':'目标固件源码与构建','system':'本轮控制与原生联合计算记录'}[domain],'kind':'engineering-source','scope':'原生文件和数据快照；未证明物理充分性或修订间整机等价。','files':[file(p) for p in paths]})
 used={f['path'] for g in groups for f in g['files']}
 extras=[p for folder in ('report','reproduce') for p in (root/folder).rglob('*') if p.is_file() and str(p.relative_to(root)) not in used]
 extras.extend([root/'inputs/source-index.json',root/'seal.json',root/'origin-map.json'])
 if complete_archive:
  # Preserve every sealed relative path, including the figure-only input plan.
  # Hash-identical report copies do not make missing original paths portable.
  seal=json.loads((root/'seal.json').read_text())
  extras.extend(root/f['path'] for f in seal['files'] if f['path'] not in used)
  extras=list({str(p.relative_to(root)):p for p in extras}.values())
 groups.append({'id':'report','domain':'system','title':'完整图组报告、逐图来源与再生成程序','kind':'documentation','scope':'70个预声明子图和完整数据/工程档案；绘图复算独立于原生求解和产品验收。','files':[file(str(p.relative_to(root))) for p in extras]})
 manifest={'schema_version':'bf-engineering-case-v1','id':'door-product-evidence','version':version,'title':index['title'] if version=='E2' else index['title'].removesuffix(' E2'),'authority':'operator-assisted','hardware_verified':False,'autonomous_agent_verified':False,'design_sha256':index['source_identity'],'groups':groups}
 if version!='E2' and publication_output is None:raise ValueError('NEW_PUBLICATION_REQUIRES_SEPARATE_OUTPUT')
 publication=Path(publication_output) if publication_output else root/'publication.json'
 dump(publication,manifest);catalog.cases.publish(owner,root,manifest)
 _,files,_=catalog.cases.collect(owner);own=[f for f in files if f.get('case_id')==manifest['id'] and f.get('case_version')==version]
 if not all(f['integrity'] for f in own):raise ValueError('E2_PUBLICATION_READBACK_FAILED')
 receipt={'owner':owner,'version':version,'files':len(own),'unique_paths':len({f['source_path'] for f in own}),'groups':6,'panels':70,'integrity':True,'complete_archive':complete_archive,'source_identity':index['source_identity'],'product_accepted':False}
 dump(publication.with_name(publication.stem+'-receipt.json') if publication_output else root/'publication-receipt.json',receipt);print(json.dumps(receipt),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--e1',required=True);p.add_argument('--root',required=True);p.add_argument('--reference',required=True);p.add_argument('--publish-owner');p.add_argument('--state');p.add_argument('--publish-only',action='store_true');p.add_argument('--version',default='E2');p.add_argument('--complete-archive',action='store_true');p.add_argument('--publication-output');a=p.parse_args()
 if not a.publish_only:build(a.e1,a.root,a.reference)
 if a.publish_owner:publish(a.root,a.publish_owner,a.state,a.version,a.complete_archive,a.publication_output)
