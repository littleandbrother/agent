"""Local report: python3 -B report.py input.json. Designs are as-built geometry; no Agent calls."""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sim import TASK, acceleration, beam, simulate

FONT = os.environ.get("REPORT_FONT", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
CAD_PYTHON = os.environ.get("CAD_PYTHON", sys.executable)
BLUE, GREEN, ORANGE, INK = "#164E7D", "#237B64", "#B85929", "#172B3A"


def cad(design, output):
    import cadquery as cq
    solids = []
    aux = design.get("connections",{}).get("aux_resonator",design.get("modules",{}).get("A",True))
    for i, name in enumerate(("harvester", "trigger_beam") if aux else ("harvester",)):
        b = design[name]
        L, w, hs, hp = [b[k] for k in ("length_mm", "width_mm", "substrate_mm", "piezo_layer_mm")]
        y = i * 18
        solids.append(cq.Workplane("XY").box(L, w, hs).translate((L/2, y, 0)).val())
        for sign in (-1, 1):
            solids.append(cq.Workplane("XY").box(L, w, hp).translate((L/2, y, sign*(hs+hp)/2)).val())
        tip_length = b["tip_mass_g"] / (.0193*w*2)
        solids.append(cq.Workplane("XY").box(tip_length, w, 2).translate((L-tip_length/2, y, (hs+2*hp)/2+1)).val())
        solids.append(cq.Workplane("XY").box(5, w+4, 4).translate((-2.5, y, 0)).val())
    compound = cq.Compound.makeCompound(solids)
    cq.exporters.export(compound, str(output / "node.step"))
    cq.exporters.export(compound, str(output / "cad_isometric.svg"), opt={"width":900,"height":500,"projectionDir":(1,-1,1),"showAxes":False})
    info={"solids":len(solids),"cadquery":cq.__version__,"tip_mass_material":"tungsten illustration, density 19.3 g/cm3", "model_scope":"Beam and proof-mass geometry only; no PCB manufacturing model."}
    (output/"cad_manifest.json").write_text(json.dumps(info,indent=2)+"\n")
    return info


def data(case, output, name):
    path = output / (name + ".json")
    tracepath = output / (name + "_trace.npz")
    if path.exists() and tracepath.exists():
        saved = json.loads(path.read_text())
        if saved["design"] == case["design"] and saved["task"] == case["task"]:
            return saved, dict(np.load(tracepath))
    result = simulate(case["design"], case["task"])
    trace = result.pop("trace")
    arrays = {"t":np.asarray(trace["t"]),"y":np.asarray(trace["y"]),"phase":np.asarray(trace["phase"])}
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    np.savez_compressed(tracepath,**arrays)
    return result, arrays


def figures(cases, results, traces, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family":"Arial","font.size":10,"axes.spines.top":False,"axes.spines.right":False,"svg.fonttype":"none","figure.dpi":120})
    for n, (case,result,trace) in enumerate(zip(cases,results,traces),1):
        t,y = trace["t"], trace["y"]
        fig, axes = plt.subplots(4,1,figsize=(9,8),sharex=True,layout="constrained")
        axes[0].plot(t,[acceleration(v,case["task"])/9.80665 for v in t],lw=.6,color="#64748B")
        axes[0].set_ylabel("Excitation (g)")
        axes[1].plot(t,y[:,6],label="Storage",lw=1.2,color=BLUE)
        axes[1].plot(t,y[:,7],label="Envelope",lw=.8,color=ORANGE)
        axes[1].axhline(case["design"]["circuit"]["start_V"],ls=":",color=BLUE)
        axes[1].axhline(case["design"]["circuit"]["brownout_V"],ls="--",color="#B64342")
        axes[1].set_ylabel("Voltage (V)"); axes[1].legend(ncol=2,loc="upper right")
        axes[2].plot(t,y[:,0]*1e3,label="Harvester",color=BLUE,lw=.8)
        axes[2].plot(t,y[:,3]*1e3,label="Trigger",color=GREEN,lw=.8)
        axes[2].set_ylabel("Tip travel (mm)")
        for start in case["task"]["fault_starts_s"]:
            for ax in axes: ax.axvspan(start,start+case["task"]["fault_duration_s"],color=ORANGE,alpha=.12)
        for r in result["records"]: axes[3].plot(r["received_s"],1,"o",color=GREEN)
        axes[3].set(yticks=[1],yticklabels=["Received"],ylim=(.5,1.5),xlabel="Time (s)")
        fig.suptitle(f"Case {n} | {result['verdict']} | full transient, actual program loads",color=INK)
        fig.savefig(output/f"case{n}_waveforms.svg"); fig.savefig(output/f"case{n}_waveforms.png",dpi=220);plt.close(fig)
    d = cases[0]["design"]
    fig = plt.figure(figsize=(9,6)); ax=fig.add_subplot(111,projection="3d")
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    def box(x,y,z,L,w,h,color):
        p=np.array([[x,y,z],[x+L,y,z],[x+L,y+w,z],[x,y+w,z],[x,y,z+h],[x+L,y,z+h],[x+L,y+w,z+h],[x,y+w,z+h]])
        faces=[[p[j] for j in ids] for ids in [[0,1,2,3],[4,5,6,7],[0,1,5,4],[2,3,7,6],[1,2,6,5],[0,3,7,4]]]
        ax.add_collection3d(Poly3DCollection(faces,facecolors=color,edgecolors="#335566",linewidths=.4,alpha=.95))
    for i,name in enumerate(("harvester","trigger_beam")):
        b=d[name];L,w,hs,hp=[b[k] for k in ("length_mm","width_mm","substrate_mm","piezo_layer_mm")];y=i*18
        box(0,y-w/2,-hs/2,L,w,hs,"#AAB6C3")
        box(0,y-w/2,hs/2,L,w,hp,"#73BDB6")
        box(0,y-w/2,-hs/2-hp,L,w,hp,"#73BDB6")
        tl=b["tip_mass_g"]/(.0193*w*2);box(L-tl,y-w/2,hs/2+hp,tl,w,2,"#E1B85A")
        box(-5,y-w/2-2,-2,5,w+4,4,"#4C6378")
    ax.set(xlim=(-7,35),ylim=(-9,26),zlim=(-3,5),xlabel="x (mm)",ylabel="y (mm)",zlabel="z (mm)")
    ax.set_box_aspect((42,35,8));ax.view_init(22,-65)
    fig.tight_layout();fig.savefig(output/"cad_isometric.png",dpi=240);plt.close(fig)
    fig,axes=plt.subplots(3,1,figsize=(9,7),layout="constrained")
    for i,name in enumerate(("harvester","trigger_beam")):
        b=d[name];L,w,hs,hp=[b[k] for k in ("length_mm","width_mm","substrate_mm","piezo_layer_mm")]; yy=i*18
        axes[0].add_patch(plt.Rectangle((0,yy-w/2),L,w,fc=(BLUE if i==0 else GREEN),alpha=.4))
        axes[0].annotate("",(0,yy+w/2+3),(L,yy+w/2+3),arrowprops={"arrowstyle":"<->","color":INK})
        axes[0].text(L/2,yy+w/2+4,f"{L:.2f} mm",ha="center")
        axes[1].add_patch(plt.Rectangle((0,i*3),L,hs+2*hp,fc=(BLUE if i==0 else GREEN),alpha=.6))
        axes[1].text(L+1,i*3,f"thickness {hs+2*hp:.3f} mm")
        axes[2].add_patch(plt.Rectangle((yy-w/2,0),w,hs+2*hp,fc=(BLUE if i==0 else GREEN),alpha=.6))
        axes[2].text(yy,1.1,f"width {w:.2f} mm",ha="center")
    axes[0].set(xlim=(-6,43),ylim=(-10,31),title="Top view | full active span, dimensions in mm",aspect="equal")
    axes[1].set(xlim=(-6,43),ylim=(-1,6),title="Side view | layer stack",aspect="equal")
    axes[2].set(xlim=(-10,30),ylim=(-1,3),title="Front view | beam separation is assembly illustration",aspect="equal")
    fig.savefig(output/"orthographic.svg");fig.savefig(output/"orthographic.png",dpi=240);plt.close(fig)


def envelope(case, output):
    path=output/"operating_envelope.json"
    if path.exists():
        saved=json.loads(path.read_text())
        if saved["design"]==case["design"] and saved["base_task"]==case["task"]:return saved
    # Local engineering map, same nuisance events; not a global certificate.
    rows=[]
    for g in (.10,.15,.20):
        for interval in (3.,5.,6.):
            task=deepcopy(case["task"]);task["background_peak_g"]=g
            task["fault_starts_s"]=[case["task"]["fault_starts_s"][0]+interval*i for i in range(4)]
            task["duration_s"]=max(30.,task["fault_starts_s"][-1]+2)
            r=simulate(case["design"],task)
            rows.append({"background_g":g,"fault_interval_s":interval,"task":task,"verdict":r["verdict"],"metrics":r["metrics"],"checks":r["checks"]})
            print(f"envelope {g}g/{interval}s: {r['verdict']} {r['metrics']['delivered_on_time']}/4",flush=True)
    path.write_text(json.dumps({"scope":"Local 3x3 engineering screen, original first event and nuisance events; no global proof", "design":case["design"], "base_task":case["task"], "rows":rows},ensure_ascii=False,indent=2)+"\n")
    return json.loads(path.read_text())


def make_pdf(cases, results, env, output, cad_info):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import HexColor
    pdfmetrics.registerFont(TTFont("CN",FONT))
    W,H=595.276,841.89; c=canvas.Canvas(str(output/"Engineering_Design_Report.pdf"),pagesize=(W,H))
    c.setTitle("双梁唤醒与冲击分流节点 - 全瞬态工程设计报告")
    c.setAuthor("BF Design")
    c.setCreator("wakeup/formal/report.py")
    y=0
    def text(s,size=10,color=INK,x=42,width=511,leading=None):
        nonlocal y
        c.setFont("CN",size);c.setFillColor(HexColor(color))
        # Keep Chinese wrapping deterministic without depending on a browser.
        line=""
        for char in str(s):
            if char=="\n" or pdfmetrics.stringWidth(line+char,"CN",size)>width:
                c.drawString(x,y,line);y-=leading or size*1.55;line="" if char=="\n" else char
            else:line+=char
        if line:c.drawString(x,y,line);y-=leading or size*1.55
        y-=5
    def start(page,chapter,title):
        nonlocal y
        c.setFillColor(HexColor(BLUE));c.rect(0,H-98,W,98,fill=1,stroke=0)
        c.setFillColor(HexColor("#B8D9EC"));c.setFont("CN",10);c.drawString(42,H-30,"BF DESIGN / ENGINEERING CALIBRATION / "+date.today().isoformat())
        c.setFillColor(HexColor("#FFFFFF"));c.setFont("CN",19);c.drawString(42,H-63,title)
        c.setFont("CN",10);c.drawString(42,H-83,chapter)
        c.setStrokeColor(HexColor("#D9E4EA"));c.line(42,38,W-42,38)
        c.setFillColor(HexColor("#64748B"));c.setFont("CN",8)
        c.drawString(42,24,"本地物理校准示例 | 正式 Agent 对比尚未运行 | 单模态代表材料模型")
        c.drawRightString(W-42,24,f"{page:02d} / 15")
        if page in (1,4,7,10,13):
            c.bookmarkPage(f"chapter{page}");c.addOutlineEntry(chapter,f"chapter{page}")
        y=H-125
    def end():c.showPage()
    def image(name,height):
        nonlocal y
        if name.endswith(".svg"):
            from svglib.svglib import svg2rlg
            from reportlab.graphics import renderPDF
            drawing=svg2rlg(str(output/name));w,h=drawing.width,drawing.height
            scale=min(511/w,height/h);drawing.scale(scale,scale)
            renderPDF.draw(drawing,c,42+(511-w*scale)/2,y-height+(height-h*scale)/2)
        else:
            c.drawImage(str(output/name),42,y-height,width=511,height=height,preserveAspectRatio=True,anchor="c",mask="auto")
        y-=height+12
    def table(rows,widths=(240,240)):
        nonlocal y
        for n,row in enumerate(rows):
            h=26
            c.setFillColor(HexColor("#EDF4F8" if n%2==0 else "#FFFFFF"));c.rect(42,y-h,511,h,fill=1,stroke=0)
            x=49;c.setFont("CN",9);c.setFillColor(HexColor(INK))
            for val,w in zip(row,widths):c.drawString(x,y-17,str(val));x+=w
            y-=h
        y-=12
    r=results[0];m=r["metrics"];e=r["energy_J"];d=cases[0]["design"];t=cases[0]["task"]
    relative=100*abs(e["balance_residual"])/max(abs(e["mechanical_input"]),1e-30)
    start(1,"第1章 / 任务书与合规矩阵","机械-模拟唤醒与数字确认节点")
    text("验收对象：可计算、可追溯的工程设计",21,BLUE)
    text("这份报告把几何结构、机电耦合、电源充电、事件触发、数字识别与无线交付放进同一条30秒瞬态轨迹。数值和图表直接来自实际模拟，不使用预设通过率，也不把漂亮的结构图当作物理验证。",12)
    image("cad_isometric.png",255)
    table([("报告状态","本地校准工程示例，非正式Agent实验"),("Case 1 完整服务",f"{r['verdict']} / {m['delivered_on_time']}/{m['faults']} 按时交付"),("Case 2 完整服务",results[1]["verdict"] if len(results)>1 else "待建立已验证设计，未作通过声明"),("能量闭合相对残差",f"{relative:.6g}%（实际计算）")])
    text("正式实验一/三完成后，以其最终 design.json 和原始演化轨迹替换本报告输入即可自动重新生成。当前没有把未来的Agent排障过程编写成事实。",10)
    end()
    start(2,"第1章 / 输入和任务条件","什么信号必须被发现，什么信号必须被拒绝")
    table([("仿真时长",f"{t['duration_s']} s"),("背景激励",f"{t['background_Hz']} Hz / 峰值 {t['background_peak_g']} g"),("目标异常",f"{t['fault_Hz']} Hz / 峰值 {t['fault_peak_g']} g"),("目标持续时间",f"{t['fault_duration_s']} s"),("目标起始时刻",str(t['fault_starts_s'])+" s"),("干扰信号",f"{t['nuisance_Hz']} Hz / {t['nuisance_peak_g']} g"),("干扰起始时刻",str(t['nuisance_starts_s'])+" s"),("交付死线",f"异常开始后 {t['delivery_deadline_s']} s")])
    text("大白话：背景振动负责慢慢充电，目标故障负责敲门。辅梁和包络电路先判断有没有值得叫醒MCU的信号；MCU再采样、识别、保存并发包。只有在每次死线前收到的独立报警才记为成功。",12)
    text("激励不是MCU的未来提示。异常时刻只由评价器用于对照，不进入控制决策。模拟中能看见内部状态，不等于实际设备已经配置这些测量探头。",10)
    end()
    start(3,"第1章 / 实际结果","五项服务条件必须同时通过")
    rows=[("按时交付",f"{m['delivered_on_time']}/{m['faults']}"),("误报",str(m['false_reports'])),("掉电",str(m['brownouts'])),("峰值应力",f"{m['peak_stress_MPa']:.4f} MPa / 限 {t['stress_limit_MPa']}"),("峰值位移",f"{m['peak_tip_mm']:.5f} mm / 限 {t['tip_travel_limit_mm']}"),("最大交付延迟",f"{m['max_latency_s']:.6f} s" if m['max_latency_s'] else "无按时记录"),("首达启动门限",f"{m['cold_charge_ready_s']:.5f} s" if m['cold_charge_ready_s'] else "未达到")]
    table(rows)
    for key,value in r['checks'].items():text(f"{'PASS' if value else 'FAIL'}  {key}",10,GREEN if value else ORANGE)
    text("能量闭合是一项数值一致性检查，单独列出，不与五项任务服务混为同一指标。PASS表示当前模型、当前输入和当前设计下满足要求，不代表已完成实物测试或所有环境的认证。",11)
    end()
    start(4,"第2章 / 实体与图纸","两根梁分别负责取能与唤醒")
    image("cad_isometric.svg",330)
    text("实体投影显示主梁、辅梁、上下压电层、端部质量块与固定夹持端。主梁接整流与储能；辅梁接高阻输入和包络检测。",11)
    text("STEP是实际CadQuery实体导出，不是图片改后缀。质量块以钨密度19.3 g/cm³示意配重体积；模拟把质量集中在梁端，CAD有限钨块的重心则在末段，两者并非已验证等价结构。粘接层、焊点、PCB装配未校准，实体只作尺寸沟通，不直接当制造图。",10)
    text(f"CadQuery {cad_info.get('cadquery','-')} / 实体数 {cad_info.get('solids','-')} / 文件 node.step",10,BLUE)
    end()
    start(5,"第2章 / 三视与尺寸","从参数表到可检查的几何尺寸")
    image("orthographic.png",445)
    text("上下压电层厚度分别取 piezo_layer_mm；梁总厚度=基底厚度+2×压电层厚度。有效梁长从夹持截面到自由端，未把固定夹块计入活动长度。",10)
    text("投影仅展示梁体及配重。图中梁间距是排布示意，不作为物理有效面积约束的替代。面积限制必须按实验任务独立定义。",10)
    end()
    start(6,"第2章 / 参数和作用","调哪一项，会牵动哪一项")
    rows=[("参数","主梁 / 辅梁")]
    for k in ("length_mm","width_mm","substrate_mm","piezo_layer_mm","tip_mass_g","damping_ratio"):rows.append((k,f"{d['harvester'][k]:.5g} / {d['trigger_beam'][k]:.5g}"))
    rows.extend([("短路固有频率 Hz",f"{r['beam_parameters']['harvester']['short_circuit_Hz']:.3f} / {r['beam_parameters']['trigger']['short_circuit_Hz']:.3f}"),("开路固有频率 Hz",f"{r['beam_parameters']['harvester']['open_circuit_Hz']:.3f} / {r['beam_parameters']['trigger']['open_circuit_Hz']:.3f}")]);rows.extend([("弹性模量：基底 / 压电", "200 / 60 GPa"),("密度：基底 / 压电", "7800 / 7500 kg/m3"),("相对介电常数 / e31", "1700 / 11.4 C/m2")]);table(rows)
    cc,ff=d["circuit"],d["firmware"]
    text(f"Case1供电与触发：储能{cc['storage_uF']}μF，启动{cc['start_V']}V，掉电{cc['brownout_V']}V；包络唤醒/重置{cc['wake_high_V']}/{cc['wake_low_V']}V。",11)
    text(f"Case1数字确认：{ff['sample_count']}点/{ff['sample_Hz']}Hz，即{1000*ff['sample_count']/ff['sample_Hz']:.1f}ms采样；目标频带{ff['target_band_Hz']}Hz，最低频带占比{ff['minimum_band_fraction']}，最低RMS {ff['minimum_target_rms_g']}g。",10)
    text("梁更长或配重更重，固有频率一般降低，但应力、位移、压电电容和机电反馈也随之变化。因此不能把梁长当成独立旋钮，只看开路峰值就宣布整机最优。",11)
    text("采用单个弯曲模态和代表材料常数。高阶模态、非线性大位移、粘接损耗和实际材料离散性没有通过实验标定。",10)
    end()
    start(7,"第3章 / 完整瞬态","30秒：从振动到实际报警接收")
    image("case1_waveforms.png",470)
    text("橙色阴影是目标事件。曲线按1ms导出，安全峰值另取LSODA接纳的内部积分节点。电压包含待机、采样与发射的真实负载；接收取自TX/ACK完成时刻。有电不保证来得及启动，启动也不保证发射不掉电。",10)
    end()
    start(8,"第3章 / 能量账本","每一微焦耳去了哪里")
    names={"mechanical_input":"机械输入","mechanical_damping":"机械阻尼耗散","rectifier_loss":"整流与分流损耗","trigger_front_end_loss":"触发前端耗散","MCU_input":"MCU/稳压输入","idle":"静态、漏电及模块负载","clamp_loss":"钳位损耗","final_stored_all_domains":"结束时所有域储能","balance_residual":"闭合残差"}
    if len(results)>1:
        table([("能量去向","Case 1 / μJ","Case 2 / μJ")]+[(names[k],f"{e[k]*1e6:.4f}",f"{results[1]['energy_J'][k]*1e6:.4f}") for k in names],widths=(220,130,130))
    else:
        table([(names[k],f"{e[k]*1e6:.6f} μJ") for k in names])
    text("账本关系：机械输入 = 机械阻尼 + 整流/分流 + 触发前端 + MCU输入 + 待机漏电 + 钳位 + 结束储能 + 数值残差。",11)
    text(f"相对残差 = |残差| / |机械输入| ×100% = {relative:.6g}%。它反映数值积分与账本闭合，不是仿真对实物误差。",11)
    text("rectified_to_storage 是经过储能节点的流量，已含在上述去向中，因此不重复加总。负的瞬时机械输入代表能量回馈，不应擅自裁成零后拿来造好看的守恒表。",10)
    ff=d["firmware"];one=sum(ff[f"{k}_s"]*ff[f"{k}_mW"] for k in ("boot","infer","save","tx","ack"))+ff["sample_count"]/ff["sample_Hz"]*ff["sample_mW"]
    text(f"可以手算的核对：一次完整确认约需{one*1000:.3f}μJ负载能量；除以稳压效率{d['circuit']['regulator_efficiency']}后，4次至少{4*one*1000/d['circuit']['regulator_efficiency']:.3f}μJ储能输入。额外唤醒或拒绝会在此基础上继续耗能。",10)
    cc=d["circuit"];window=.5*cc["storage_uF"]*(cc["start_V"]**2-cc["brownout_V"]**2)
    text(f"储能和程序的连接点：忽略工作期间继续取能，电容从启动门限放到掉电门限可释放 {window:.3f}μJ。它必须覆盖单次工作负载；加大电容有助扛住负载，也会拖慢从零开始的充电。完整瞬态负责同时核算这两面。",10)
    end()
    start(9,"第3章 / 冲击保护节点","Case 2 的状态与真实边界")
    if len(results)>1:
        image("case2_waveforms.png",370)
        text(f"实际完整服务：{results[1]['verdict']}。分流支路通过压电电压改变机械负载和能量耗散；它不是理想的任意阻尼开关。",10)
        text(cases[1].get("provenance",""),10)
        m2=results[1]["metrics"]
        text(f"Case2实测：{m2['delivered_on_time']}/4，误报{m2['false_reports']}、掉电{m2['brownouts']}，应力{m2['peak_stress_MPa']:.4f}MPa，位移{m2['peak_tip_mm']:.5f}mm。",10)
        c2=cases[1]["design"]["circuit"];t2=cases[1]["task"]
        text(f"独立Case2任务：背景{t2['background_Hz']}Hz/{t2['background_peak_g']}g，目标{t2['fault_Hz']}Hz/{t2['fault_peak_g']}g；C={c2['storage_uF']}μF，分流R={c2.get('shunt_ohm',0)}Ω，阈值{c2.get('shunt_threshold_V',0)}V。详见case2.json。",9)
        if cases[1].get("implementation_note"):text(cases[1]["implementation_note"],9,ORANGE)
    else:
        text("本轮尚无达到全部服务条件的Case 2设计，因此这一页不伪造4/4波形。报告生成器支持第二个实际输入；其求解通过后自动填入此处。",16,ORANGE)
        text("已有内核支持的是电压阈值触发的电阻分流。它会分走可采集能量，也可能改变机械响应。不能直接称为SSDI，不能预先宣称应力降低50%，更不能把仅应力通过、但丢包或掉电的设计当作整机通过。",12)
    end()
    start(10,"第4章 / 排障实录","把真实改动与解释放在一起")
    history=cases[0].get("evolution",[])
    text(cases[0].get("provenance","本地校准示例，没有新Agent实验轨迹。"),11,BLUE)
    if history:
        for i,row in enumerate(history,1):
            text(f"{i}. {row.get('label','历史节点')}",12,BLUE)
            text(json.dumps(row,ensure_ascii=False),9)
    else:
        text("当前输入只有最终工程设计，尚未提供逐步Agent行动记录。此处保留为空，不用人工编造的‘先诊断、后修复’故事替代实验事实。",13)
        text("输入演化记录应包含：当时设计、当时可见反馈、实际参数修改、完整消费者结果，以及动作来自Agent还是开发者。程序不会根据最终成功倒推出一个看似合理的历史。",11)
    if len(cases)>1 and cases[1].get("evolution"):
        text("真实工程反事实：只切换分流D",13,BLUE)
        text("以下来自本地开发者校准，不是Agent诊断实录。两次使用相同任务和其余设计参数。",10)
        for row in cases[1]["evolution"]:
            text(f"{row['label']}：{row['delivery']}/4，应力 {row['stress_MPa']:.4f} MPa，掉电 {row['brownouts']}，{row['verdict']}。",11)
    end()
    start(11,"第4章 / 信息如何帮助定位","同样是0/4，问题可能在不同地方")
    for title,body in [("F0：只见最终交付","知道未完成任务，但不能直接区分没充上电、没触发、识别拒绝或发射掉电。"),("F1：增加阶段次数","WAKE/CONFIRM/REJECT/BROWNOUT将失败定位到部分程序阶段，但没有给出所有连续参数方向。"),("F2：增加内部电压与时刻","主梁、辅梁、包络与储能电压能区分供能与触发支路；t_ready指出启动是否赶得上。"),("F3：增加幅相和事件窗口","相位提供共振峰左右侧信息，逐事件窗口区分事件前能量不足和工作后能量耗尽。")]:
        text(title,13,BLUE);text(body,11)
    text("以上是信息内容的区别，不是预先承诺的通过率。信息更多并不保证某个有限预算Agent每次都单调提高；正式实验才测量这种效应。",11,ORANGE)
    end()
    start(12,"第4章 / 实际程序链","唤醒以后，仍需完成整个服务")
    counts=Counter(x['event'] for x in r['events'])
    table([(name,str(counts[name])) for name in ("WAKE","BOOT","SAMPLE","INFER","CONFIRM","REJECT","SAVE","TX","ACK","RECEIVED","BROWNOUT")])
    text("模拟中的依次执行：WAKE → BOOT → SAMPLE → INFER → CONFIRM/REJECT → SAVE → TX → ACK。任一步骤负载都从同一储能节点扣除，低于掉电电压会中断当前尝试。",11)
    text("数字分类使用实际瞬态加速度采样、量化和FFT频带占比，不是看到目标时刻便直接判正确。误报也按未匹配目标事件的真实接收记录计算。",11)
    end()
    start(13,"第5章 / 工作包络","固定设计在不同激励与事件间隔下会怎样")
    rows=[("背景 g / 间隔 s","3 / 5 / 6")]
    for g in (.10,.15,.20):
        matches=[v for v in env['rows'] if v['background_g']==g]
        rows.append((str(g)," / ".join(f"{v['metrics']['delivered_on_time']}/4 {v['verdict']}" for v in matches)))
    image("operating_envelope.png",235)
    text("这张3×3图保持设计不变，只改变背景幅值与目标事件间隔。保留原11/23秒的干扰事件。间隔变化也会改变目标与干扰的重叠，因此失败不能全部归因于充电。每点均跑完整瞬态，点之间不作全域保证。",11)
    text("较大背景可能加快充电，也可能增加非目标触发；间隔过短可能来不及恢复储能。因此不能把单轴的‘越大越好’当成普遍规律。",11)
    text("operating_envelope.json 保存全部点的检查项和物理量。安全指标取自求解器内部节点。正式设计边界需要按真实部署激励范围进一步确定，当前局部图不等于场景穷举。",10)
    end()
    start(14,"第5章 / 不可行边界","什么可以证明，什么还不能证明")
    text("当前尚未取得覆盖全部合法结构和连续范围的全域不可行证书；本章界定结论范围，不以有限搜索替代证明。",11,ORANGE)
    text("1. 一个通过设计是存在性见证。",13,BLUE);text("同一个设计在完整消费者中通过，可说明该给定工况至少存在一个可行点。",11)
    text("2. 零命中不是全域无解证明。",13,BLUE);text("有限随机采样或优化器没有找到解，只能说明这次搜索失败。除非有覆盖整个合法域的安全上界，否则不能写‘物理必死’。",11)
    text("3. 分支上界与全域上界不能互换。",13,BLUE);text("关闭某个模块时的能量上界，不能排除开启模块后出现的解。停止实验必须说明证书覆盖哪些结构、哪些连续范围和哪些服务条件。",11)
    text("4. 有限时长不等于无限时长。",13,BLUE);text("平均功率赤字能支持长期不可持续结论，但如果初始储能和有限观察窗口允许短时运行，不能据此推导当前30秒任务必然失败。",11)
    text("5. 当前模型的真实限制。",13,BLUE);text("代表材料、单弯曲模态、理想化电路和有限固件语义均会限制对实物的外推。能源账本闭合只能确认这套数学模型内部一致。",11)
    if len(cases)>1 and cases[1].get("resolution_note"):
        text(cases[1]["resolution_note"],10)
    end()
    start(15,"第5章 / 交付与结论","可复算的设计，而不是包装过的通过标签")
    table([("主报告","Engineering_Design_Report.pdf"),("实体模型","node.step / cad_manifest.json"),("工程三视图","orthographic.svg"),("完整瞬态图","case1_waveforms.svg / case2_waveforms.svg"),("原始设计与结果","case1.json / case1_trace.npz"),("工作包络","operating_envelope.json"),("重新生成","python3 -B report.py [input.json]")])
    text(f"已验证结论：Case 1 在输入定义的当前任务中 {m['delivered_on_time']}/{m['faults']} 按时交付，误报 {m['false_reports']}，掉电 {m['brownouts']}，完整检查 {r['verdict']}。",12,GREEN if r['verdict']=='PASS' else ORANGE)
    if len(results)>1:
        m2=results[1]["metrics"]
        text(f"Case2同样在其独立任务中{results[1]['verdict']}：{m2['delivered_on_time']}/4，误报{m2['false_reports']}、掉电{m2['brownouts']}，峰应力{m2['peak_stress_MPa']:.4f}MPa、峰位移{m2['peak_tip_mm']:.5f}mm。",12,GREEN)
    text("尚未完成的结论：正式实验一与三的Agent性能、不同反馈的因果增益、多模型结果、工程样机和实际环境鲁棒性。报告生成代码已经具备替换正式结果的入口。",11)
    text("本轮只做本地物理校准与文档生成，没有调用任何新的实验模型。",11,BLUE)
    end();c.save()


def main():
    parser=argparse.ArgumentParser();parser.add_argument("input",nargs="?");parser.add_argument("--cad-only",nargs=2,metavar=("DESIGN","OUT"));args=parser.parse_args()
    if args.cad_only:
        d=json.loads(Path(args.cad_only[0]).read_text());o=Path(args.cad_only[1]);print(json.dumps(cad(d,o)));return
    output=HERE/"outputs"/"report";output.mkdir(parents=True,exist_ok=True)
    cases=json.loads(Path(args.input).read_text())["cases"] if args.input else [{"name":"Case 1","design":json.loads((HERE.parent/"design.json").read_text()),"task":deepcopy(TASK),"provenance":"原唤醒节点设计的本地完整瞬态复算；不是正式实验一/三的Agent运行。"}]
    results,traces=zip(*(data(case,output,f"case{i}") for i,case in enumerate(cases,1)))
    figures(cases,results,traces,output)
    cad_design=output/"design.json"
    same=cad_design.exists() and json.loads(cad_design.read_text())==cases[0]["design"] and (output/"node.step").exists()
    if not same:
        cad_design.write_text(json.dumps(cases[0]['design'],ensure_ascii=False,indent=2)+"\n")
        subprocess.run([CAD_PYTHON,"-B",str(Path(__file__).resolve()),"--cad-only",str(cad_design),str(output)],capture_output=True,text=True,check=True)
    info=json.loads((output/"cad_manifest.json").read_text())
    if len(cases)>1:
        cad2=output/"case2_cad";cad2.mkdir(exist_ok=True)
        dp=cad2/"design.json"
        if not (dp.exists() and json.loads(dp.read_text())==cases[1]["design"] and (cad2/"node.step").exists()):
            dp.write_text(json.dumps(cases[1]["design"],ensure_ascii=False,indent=2)+"\n")
            subprocess.run([CAD_PYTHON,"-B",str(Path(__file__).resolve()),"--cad-only",str(dp),str(cad2)],capture_output=True,text=True,check=True)
    env=envelope(cases[0],output)
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4),layout="constrained")
    values=np.array([[int(v["verdict"]=="PASS") for v in env["rows"][i:i+3]] for i in (0,3,6)])
    from matplotlib.colors import ListedColormap
    ax.imshow(values,cmap=ListedColormap(["#F4D9CC","#C5E3D4"]),vmin=0,vmax=1,origin="lower",aspect="auto")
    for index,v in enumerate(env["rows"]):ax.text(index%3,index//3,f"{v['metrics']['delivered_on_time']}/4 {v['verdict']}",ha="center",va="center",color=INK)
    ax.set(xticks=range(3),xticklabels=[3,5,6],yticks=range(3),yticklabels=[.10,.15,.20],xlabel="Fault interval (s)",ylabel="Background peak (g)",title="Fixed design | local full-transient screen (not interpolated)")
    fig.savefig(output/"operating_envelope.svg");fig.savefig(output/"operating_envelope.png",dpi=240);plt.close(fig)
    make_pdf(cases,results,env,output,info)
    print(json.dumps({"pdf":str(output/"Engineering_Design_Report.pdf"),"cases":[r['verdict'] for r in results],"pages":15,"cad":info,"new_model_calls":0},ensure_ascii=False))

if __name__=="__main__":main()
