"""E3 six-group,70-panel evidence from sealed D4 and declared historical sources.

No new physics is generated here. Gaps and independent FEM disagreement stay
visible; paper task progress is not computed from image availability.
"""
import argparse,csv,json,hashlib,shutil
import numpy as np
from pathlib import Path
from bfworld.agentlab.scientific_figures import validate_plan
from bfworld.agentlab.scientific_renderer import render
from bfworld.agentlab.simulation_chain.contracts import file_hash,write_json

def build(system,old):
    system,old=Path(system),Path(old);out=system/'presentation';data=out/'figure-inputs';data.mkdir(parents=True,exist_ok=True)
    plan=json.loads((old/'report/reproduce-plan.json').read_text());sources={s['id']:s for s in plan['sources']}
    for s in sources.values():
        origin=old/'report'/s['path'];target=data/(s['id']+origin.suffix);shutil.copy2(origin,target)
        s['path']=target.name;s.pop('archive_file',None)
    def source(sid,path,columns=None,origin='native-simulation',scope='D4 nominal native result; not hardware or model qualification.'):
        path=Path(path);target=data/(sid+path.suffix);shutil.copy2(path,target)
        sources[sid]={'id':sid,'path':target.name,'sha256':file_hash(target),'columns':columns or {},'origin':origin,'scope':scope}
        return sid
    def derived(sid,rows,columns=None,scope='Derived from bound native JSONs; no added physical evidence.'):
        path=data/(sid+'.csv')
        with path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        sources[sid]={'id':sid,'path':path.name,'sha256':file_hash(path),'columns':columns or {},'origin':'derived-analysis','scope':scope};return sid
    panels={p['id']:p for g in plan['groups'] for p in g['panels']};updated=set()
    def panel(pid,title,caption,kind,deps,**kwargs):
        updated.add(pid)
        refs=panels[pid].get('reference_panels',[])
        panels[pid].clear();panels[pid].update(id=pid,label=pid[1],title=title,question=title+'回答了什么工程问题？',caption=caption,
            evidence_kind='engineering-view' if kind=='image' else 'numeric-result',dependencies=deps,status='available',type=kind,reference_panels=refs,**kwargs)
    def line(pid,title,caption,series,xlabel,ylabel,**kwargs):
        panel(pid,title,caption,'line',list(dict.fromkeys(s['source'] for s in series)),series=series,x_label=xlabel,y_label=ylabel,**kwargs)
    def series(sid,x,y,xu,yu,label=None):return {'source':sid,'x':x,'y':y,'x_unit':xu,'y_unit':yu,**({'label':label} if label else {})}
    def table(pid,title,caption,sid,cols,deps=None):panel(pid,title,caption,'table',deps or [sid],source=sid,columns=cols)
    def bar(pid,title,caption,sid,x,y,unit,label):panel(pid,title,caption,'bar',[sid],source=sid,x=x,y=y,y_unit=unit,y_label=label)
    ref=system/'sealed-reference-v2';result=json.loads((ref/'result.json').read_text());design=json.loads((ref/'design-spec.json').read_text())
    source('d4_design',ref/'design-spec.json',origin='engineering-geometry',scope='Frozen D4 design/task/model identity; no physical metrology.')
    source('d4_result',ref/'result.json');source('d4_manifest',ref/'system-manifest.json');source('d4_cad',ref/'cad/d4-cad-receipt.json',origin='engineering-geometry')
    receipt=json.loads((out/'mechanics/render-receipt.json').read_text())
    if receipt['design_id']!=design['design_id']:raise ValueError('D4_RENDER_IDENTITY')
    source('render_receipt',out/'mechanics/render-receipt.json',origin='engineering-geometry',scope='D4 exact CAD/trajectory rendering; cut/explosion and first-mode shape are presentation transforms.')
    views={v['name']:v for v in receipt['views']}
    def labels(pid,name,items,scale_mm=20):
        view=views[name+'.png'];p=panels[pid];p['annotations']=[]
        for key,text,x,y in items:
            point=view['landmarks'].get(key)
            if point and all(0<=v<=1 for v in point):p['annotations'].append({'label':text,'x':x,'y':y,'to':point})
        p['scale_bar']={'fraction':scale_mm/1000/view['ortho_width_m'],'label':f'{scale_mm:g} mm'}
    for pid,name in zip(['1a','1b','1c','1d','1e','1f','1g','1h'],['installation','installation-detail','section','exploded','clamp','pzt','side','top']):
        source(name,out/'mechanics'/(name+'.png'),origin='engineering-geometry')
        panel(pid,panels[pid]['title'],'D4原生CAD；尺寸和支架位置进入同一设计身份。剖切/爆炸为展示变换，非实物照片。','image',[name,'render_receipt'],source=name)
        if name not in ('installation','installation-detail'):
            labels(pid,name,[('clamp_upper','Clamp',.03,.12),('pzt','PZT',.37,.07),('tip_magnet','Tip magnet',.65,.13),('main_pcb','PCB geometry',.03,.90),('driver_magnet','Driver magnet',.73,.70)],10 if name in ('pzt','clamp') else 20)
    for i,t in enumerate((0,1.9,2.543125,3.)):
        name='state-'+str(i);source(name,out/'mechanics'/(name+'.png'),origin='engineering-geometry')
        panel('2'+chr(97+i),f'{t:g}s 同视角状态',f'D4完整周期t={t:g}s；磁体为真实刚体位置，梁形状是解算位移的第一模态投影，非3D FEM。0s驱动磁体在局部视野外，未自动缩放隐藏移动。','image',[name,'render_receipt'],source=name)
        labels('2'+chr(97+i),name,[('clamp_upper','Fixed',.03,.1),('tip_magnet','Tip',.50,.10),('driver_magnet','Driver',.74,.78)])
    rb=json.loads((ref/'cad/cad-readback.json').read_text())
    part_names={'beam':'梁','pzt':'压电片','driver_magnet':'驱动磁体','driver_bracket_shelf':'支架','main_pcb':'PCB'}
    dims=derived('d4_dimensions',[{'part_id':p['id'],'部件':part_names[p['id']],'X(mm)':p['size_mm'][0],'Y(mm)':p['size_mm'][1],'Z(mm)':p['size_mm'][2]} for p in rb['parts'] if p['id'] in part_names],{'X(mm)':'mm','Y(mm)':'mm','Z(mm)':'mm'})
    table('1k','D4几何读回','OCCT独立读回；支架长度反映横向位置。',dims,['部件','X(mm)','Y(mm)','Z(mm)'],[dims,'d4_cad','d4_design'])
    table('1j','当前机械尺寸','尺寸来自当前CAD独立读回；不是实物测量。',dims,['部件','X(mm)','Y(mm)','Z(mm)'],[dims,'d4_cad','d4_design'])
    panels['1i']['dependencies']=['d4_design'];updated.add('1i')
    panels['1i']['caption']='D4规定门动作、机械采能、原厂PMIC、C软件在环与虚拟通知；示意图不是物理验收。'
    revisions=derived('d4_revisions',[{'对象':'机械/联合D4','变化':'完整加载/实际支架','状态':'同design_id'}, {'对象':'电子D3.3','变化':'采购模块/布线','状态':'历史草案，未回装'}, {'对象':'C SIL D4','变化':'受控应用包络','状态':'主机库+ARM对象'}, {'对象':'目标HEX D2','变化':'独立S132工程','状态':'非同源D4镜像'}])
    table('1l','当前工程边界','这些工程不能被合并宣称为一件已验证产品。',revisions,['对象','变化','状态'])
    wu={'time_s':'s','tip_m':'m','velocity_m_s':'m/s','piezo_V':'V','storage_V':'V','supply_V':'V','pgood_V':'V'}
    source('d4_wave',ref/'waveform.csv',wu)
    source('d4_drive',ref/'drive-ledger.csv',{'time_s':'s','angle_rad':'rad','tip_m':'m','magnetic_potential_J':'J','actuator_power_W':'W','actuator_work_J':'J','beam_work_J':'J','pmic_port_J':'J','damping_J':'J','total_residual_J':'J'})
    source('d4_ledger',ref/'drive-ledger.json')
    line('2e','完整门动作输入','65°远场平衡起始；关门2s、保持0.5s、开门2s、衰减2s，初始电储能为0。',[series('d4_drive','time_s','angle_rad','s','deg')],'时间','门角')
    for pid,title,y,unit in [('2f','联合梁位移','tip_m','mm'),('2g','联合梁速度','velocity_m_s','m/s'),('2h','压电端电压','piezo_V','V')]:
        line(pid,title,'同一个完整周期的LTspice联合求解，不省略加载，也不加入初始压电电压。',[series('d4_wave','time_s',y,'s',unit)],'时间',title)
    line('2k','加载、返还能量与端口','驱动功取完整转动/平移磁势梯度；净功与正输入/返还能量分开，不当成测量效率。',[series('d4_drive','time_s','actuator_work_J','s','mJ','驱动净功'),series('d4_drive','time_s','pmic_port_J','s','mJ','电端口')],'时间','累计能量')
    grid=np.load(ref/'force/force-table.npz')
    rows=[{'angle_deg':float(np.rad2deg(a)),'tip_mm':float(q*1000),'force_N':float(grid['values'][i,j])} for i,a in enumerate(grid['angles']) for j,q in enumerate(grid['qs'])]
    sid=derived('d4_force_grid',rows,{'angle_deg':'deg','tip_mm':'mm','force_N':'N'},'D4 full prescribed angle/ROM-domain force table; interpolation check separate from finite FEM anchors.')
    source('d4_force_domain',ref/'force/force-domain.json')
    panel('2i','当前完整角度力表','0–65°与±8mm域；高梯度区加密。只是名义模型力表，非全FEM域确认。','heatmap',[sid,'d4_force_domain','d4_design'],source=sid,x='angle_deg',y='tip_mm',z='force_N',x_unit='deg',y_unit='mm',z_unit='N')
    fem=json.loads((system/'trajectory-fem-v1/trajectory-anchors.json').read_text())
    source('d4_fem_receipt',system/'trajectory-fem-v1/trajectory-anchors.json')
    source('d4_field',out/'fem/magnetic-flux.png')
    source('d4_field_export',out/'fem/field-export-receipt.json',origin='native-simulation',scope='Already solved corrected peak-q anchor; image export without solver rerun or source MPH modification.')
    panel('2l','旋转磁场原生云图','实际轨迹位移峰值姿态，扩大空气域后已求解模型的COMSOL原生场图。原域失败和修正复核在第6组分列；7个有限锚点不等于全轨迹校准。','image',['d4_field','d4_field_export','d4_fem_receipt'],source='d4_field')
    panels['2l']['annotations']=[{'label':'Neutral tip probe (10 mm)','x':.05,'y':.68,'to':[.22,.45]}, {'label':'Rotated driver (20 mm)','x':.75,'y':.74,'to':[.695,.27]}]
    screens=[];screen_deps=[]
    for folder,name in [('screen-v2','screen-summary.json'),('fine-screen-v1','summary.json')]:
        sid=source('d4_'+folder.replace('-','_'),system/folder/name,origin='derived-analysis',scope='Disclosed operator resistive screening, including out-of-domain candidates; not a successful PMIC application.')
        screen_deps.append(sid)
        for r in json.loads((system/folder/name).read_text())['records']:
            d=r['candidate']['mechanical']
            screens.append({'gap_mm':d['gap_mm'],'offset_mm':d['closed_dz_mm'],'polarity':d['polarity'],'status':r['status'],'energy_J':r['resistor_energy_J'],'peak_mm':r['peak_tip_mm']})
    if len(screens)!=20:raise ValueError('SCREEN_RECORDS_NOT_20')
    summary=derived('d4_screen_table',screens,{'gap_mm':'mm','offset_mm':'mm','polarity':'1','energy_J':'J','peak_mm':'mm'})
    table('3a','20个筛选候选','电阻控制仅摸底；15个越界、5个域内，不推导器件不可行。',summary,list(screens[0]),[summary,*screen_deps])
    panels['3a']['compact']={'rows':4,'columns':['gap_mm','offset_mm','status']}
    native_rows=[]
    for label,folder in [('居中D4','sealed-reference-v2'),('偏置探索','native-smaller-storage-v1')]:
        p=system/folder;v=json.loads((p/'result.json' if (p/'result.json').exists() else p/'receipt.json').read_text());m=v.get('metrics',v)
        native_rows.append({'候选':label,'VIN_V':m['peak_storage_V'],'端口_J':m['drive_ledger']['pmic_port_J'],'净驱动_J':m['drive_ledger']['actuator_net_input_J'],'残差':m['drive_ledger']['total_relative_residual'],'TX':m['tx_completed'],'RX':m['received_events']})
    comparisons=derived('d4_native_table',native_rows,{'VIN_V':'V','端口_J':'J','净驱动_J':'J','残差':'1','TX':'1','RX':'1'},'Two operator-chosen native runs; exploratory offset executor source not sealed at start, excluded from formal method comparison.')
    source('d4_offset_receipt',system/'native-smaller-storage-v1/receipt.json',origin='native-simulation',scope='Operator exploratory offset control, source captured at end only; not a formal equal-executor comparison.')
    for pid,title,y,unit in [('3d','原生储能峰值','VIN_V','V'),('3e','端口电能','端口_J','uJ'),('3i','驱动净功','净驱动_J','mJ'),('3k','完整接收事件','RX','1')]:bar(pid,title,'完整周期原生结果；探索记录与封存参考分列，均未启动。',comparisons,'候选',y,unit,title)
    line('3f','完整周期能量去向','驱动输入大部分没有进入PMIC端口；阻尼、电端口与磁势不能混写为收集效率。',[series('d4_drive','time_s','damping_J','s','mJ','阻尼'),series('d4_drive','time_s','beam_work_J','s','mJ','梁功'),series('d4_drive','time_s','pmic_port_J','s','mJ','端口')],'时间','累计能量')
    line('3g','当前储能轨迹','10µF输入/10µF输出，原厂PMIC；名义完整周期仍不冷启动。',[series('d4_wave','time_s','storage_V','s','V')],'时间','VIN')
    pilot=system/'pilot/trajectory-summary.json'
    if pilot.exists():
        src=source('d4_pilot',pilot,origin='derived-analysis',scope='Real Pi trajectories with raw trace, observed usage and independent task submission; retrieval hints/interventions recorded separately.')
        pv=json.loads(pilot.read_text());rows=[{'轨迹':t['trial'],'候选数':len(t['jobs']),'提交':t.get('submitted_job') or '未提交','人工改参数':t.get('human_candidate_edits',0)} for t in pv['trials']]
        sid=derived('d4_agent_table',rows);table('3h','Pi实际修订','实际派发才计入候选；提交失败不等于产品成功。',sid,['轨迹','候选数','提交','人工改参数'],[sid,src])
        panels['3h']['compact']={'columns':['轨迹','候选数','人工改参数']}
    else:raise ValueError('REAL_PI_RECEIPT_REQUIRED_BEFORE_E3')
    for pid in ['4e','4f']:
        y='storage_V' if pid=='4e' else 'pgood_V';line(pid,'当前联合'+('储能' if pid=='4e' else 'PGOOD'),'对应D4同一联合计算；D3.3 PCB电源图是独立历史诊断，不混成同一候选。',[series('d4_wave','time_s',y,'s','V')],'时间',y,**({'ylim':[0,3.3]} if pid=='4f' else {}))
    table('4j','电子工程未闭合','D3.3铜线与D4计算器件/负载仍未回装同一目标工程；禁止投板。',revisions,['对象','变化','状态'])
    source('d4_program',ref/'program.csv',{'time_s':'s','supply_V':'V','pgood_V':'V','state':'1','current_A':'A'},'software-in-loop')
    for pid,title,y,unit in [('5c','当前程序状态','state','1'),('5d','当前程序模型电流','current_A','uA')]:line(pid,title,'实际C软件在环输出；状态0为RESET，包络电流非测量。',[series('d4_program','time_s',y,'s',unit)],'时间',title,**({'drawstyle':'steps-post','ylim':[-.1,5.1]} if pid=='5c' else {}))
    bar('5h','当前完整发送','两个操作者原生条件均未启动；不是电阻筛选的应用结果。',comparisons,'候选','TX','1','TX')
    bar('5i','当前虚拟接收','只有完整TX才进入接收器；当前均为0。',comparisons,'候选','RX','1','RX')
    bar('6a','完整周期账本残差','同一名义模型残差，阈值1%；不包含加密PMIC内部损耗或实物误差。',comparisons,'候选','残差','%','相对残差')
    line('6c','加载账本逐时残差','逐时驱动功、梁功和磁势一致性；没有省略负功或返还能量。',[series('d4_drive','time_s','total_residual_J','s','uJ')],'时间','能量账差')
    correction=json.loads((system/'verification/corrected-fem-anchors.json').read_text())
    source('d4_fem_correction',system/'verification/corrected-fem-anchors.json',origin='native-simulation',scope='Operator finite-anchor confirmation with larger air domain; original failure records preserved, not full FEM domain or physical acceptance.')
    femrows=[{'anchor_id':r['name'],'锚点':'峰位移' if r['name']=='peak_q' else '近'+r['name'].removeprefix('angle_')+'°','角度_deg':r['angle_deg'],'网格差(%)':r['mesh_delta']*100,'参考差(%)':r['reference_error']*100,'状态':'通过' if r['passed'] else '未通过'} for r in correction['anchors']]
    if len(femrows)!=7:raise ValueError('FEM_RECORDS_NOT_7')
    sid=derived('d4_fem_table',femrows,{'角度_deg':'deg','网格差(%)':'%','参考差(%)':'%'})
    diff=derived('d4_fem_boundary_compare',[{'条件':r['name'].removeprefix('angle_')+'°'+label,'参考差':r[k]} for r in correction['anchors'] if r['name'] in ('angle_15','angle_35','angle_65') for label,k in [('原','original_reference_error'),('扩','reference_error')]],{'参考差':'1'})
    bar('6f','空气边界导致的远场误差','原=原域、扩=扩大域。原域约28/58/62%；扩大空气域并保持三个探针网格后均<0.45%。不是靠放宽5%门槛获得通过。',diff,'条件','参考差','%','参考相对差')
    panels['6f']['thresholds']=[{'value':5,'label':'5%'}]
    panels['6f']['dependencies']+=[ 'd4_fem_correction','d4_fem_receipt']
    table('6g','有限轨迹锚点复核','7个预选实际姿态，各3档局部网格；扩大域后全部通过5%门槛，仍未确认完整设计域。',sid,['锚点','角度_deg','网格差(%)','参考差(%)','状态'],[sid,'d4_fem_correction','d4_fem_receipt'])
    panels['6g']['compact']={'columns':['锚点','参考差(%)','状态']}
    panels['6g']['column_labels']={'角度_deg':'角度(°)'}
    source('d4_repeat',system/'verification/cold-repeat.json',origin='derived-analysis')
    rv=json.loads((system/'verification/cold-repeat.json').read_text());sid=derived('d4_repeat_table',[{'指标':k,'相对差':v} for k,v in rv['peak_relative_differences'].items()],{'相对差':'1'})
    table('3i','同执行器冷缓存复算','两次独立原生启动，同一执行器/任务/源；峰值一致、TX/RX一致，非缓存回读。',sid,['指标','相对差'],[sid,'d4_repeat'])
    progress=system/'paper/progress.json'
    if progress.exists():
        v=json.loads(progress.read_text());source('d4_progress',progress,origin='derived-analysis')
        rows=[{'项目':t['title'],'状态':t['record']['status'],'自主通过':int(t['record'].get('autonomous_qualified',False))} for t in v['tasks'] if t['eligible']]
        sid=derived('d4_progress_table',rows);table('6h','20项复现任务进度','绘图前不可变快照；分母在新Pi试验前声明，图数、操作者通过与Agent自主通过分开。绘图验收另存final-progress.json，避免循环哈希。',sid,['项目','状态','自主通过'],[sid,'d4_progress'])
    else:raise ValueError('TASK_PROGRESS_REQUIRED_BEFORE_E3')
    for pid,p in panels.items():
        if pid not in updated and p['status']=='available':
            p['title']='历史 · '+p['title']
            p['caption']='保留E2的来源和条件，不代表当前D4同一候选。'+p['caption']
        if pid in updated and p['status']=='available':
            # The numeric CSV also carries its producing design/execution identity.
            if 'd4_wave' in p['dependencies'] or 'd4_program' in p['dependencies'] or 'd4_drive' in p['dependencies']:
                p['dependencies']+=['d4_design','d4_result','d4_manifest']
            if 'd4_native_table' in p['dependencies']:
                p['dependencies']+=['d4_result','d4_offset_receipt']
            p['dependencies']=list(dict.fromkeys(p['dependencies']))
    plan.update(title='门动作磁耦合压电节点 · 加载释放与真实Pi证据 E3',version='E3',
        conclusion='完整周期原生计算、实际支架修订、独立旋转FEM与真实Pi轨迹已进入同一证据阅读路径；七个有限FEM锚点已通过，名义自供能、完整模型域与电子/目标程序一致性仍有缺口。',
        limitations=['无实物、烧录或射频测量。','D4机械/SIL与D3.3电子/独立D2目标HEX不等价。','扩大空气域后7个有限FEM锚点通过，完整设计域仍未确认；不得自动晋升物理设计排名。','Pi检索与操作者来源提示/工具修复分别留痕；不能按图数声称80%自主复现。'])
    narratives={1:('当前实际设计','D4支架与磁极进入CAD/联合模型；电子和目标HEX边界可见。'),2:('加载与释放的完整周期','从远场开始计算关门加载，随后开放/返还能量，不赠送初始储能。'),3:('候选与真实Agent修订','筛选、操作者原生控制和Pi决策分列；未找到合法自供能正例。'),4:('电路与PCB的工程边界','保留真实原理图、铜线和BOM；D4联合仿真与历史D3.3诊断不混同。'),5:('供电、程序和事件服务','C软件在环真实执行；未启动、未发送、未接收保持原样。'),6:('模型确认与复现进度','空气边界错误已定位，7个有限锚点修正后通过。20项任务不能由70张图代替。')}
    for g in plan['groups']:
        g['title'],g['conclusion']=narratives[g['order']];g['limitations']=plan['limitations'][:3]
    used={d for g in plan['groups'] for p in g['panels'] for d in p['dependencies']}
    plan['sources']=[s for sid,s in sources.items() if sid in used];validate_plan(plan)
    write_json(data/'plan.json',plan)
    rendered=render(data/'plan.json',out/'report');write_json(out/'build-receipt.json',{'design_id':design['design_id'],'native_result_sha256':file_hash(ref/'result.json'),'figure_input_plan_sha256':file_hash(data/'plan.json'),'counts':rendered['counts'],'historical_sources_disclosed':True,'product_accepted':False})
    return rendered

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--system',type=Path,required=True);p.add_argument('--old',type=Path,required=True);a=p.parse_args();v=build(a.system,a.old);print(json.dumps({'counts':v['counts'],'source_identity':v['source_identity']}))
