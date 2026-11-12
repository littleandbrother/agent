"""Generate a standalone, inspectable explanation from the actual calibration files."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build():
    data = {"experiment_plan.json": json.loads((HERE / "experiment_plan.json").read_text())}
    # Show the current task definitions and acceptance records, not every scout.
    for name in ("summary.json", "e1_formal_tasks.json", "e1_formal_summary.json",
                 "e2_tasks.json", "e2_summary.json", "e2_axis_bands.json",
                 "e3_summary.json", "e3_local_controls.json", "e4_summary.json"):
        p = HERE / "outputs" / name
        if p.exists():
            data[name] = json.loads(p.read_text())
    template = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>四项正式实验：物理校准与代码地图</title>
<style>
:root{font:16px/1.8 system-ui,sans-serif;color:#213047;background:#edf1f5}body{max-width:1280px;margin:auto;padding:30px}h1{font-size:36px;line-height:1.4}h2{font-size:27px;border-bottom:2px solid #d5dfea;padding-bottom:8px}h3{color:#175b79}section{background:white;border-radius:14px;padding:24px 32px;margin:22px 0;box-shadow:0 2px 7px #1b365210}p{max-width:1000px}nav{position:sticky;top:0;background:#15334e;padding:12px;border-radius:8px;z-index:2}nav a{color:white;margin:0 14px;text-decoration:none}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.card{border:1px solid #cbd8e6;border-radius:10px;padding:16px}table{border-collapse:collapse;width:100%;font-size:15px}td,th{border-bottom:1px solid #d8e1e9;padding:10px;text-align:left;vertical-align:top}th{background:#edf4fa}code,pre{background:#eef3f7;border-radius:5px;font:14px/1.7 ui-monospace,monospace}code{padding:2px 5px}pre{padding:14px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:650px;overflow:auto}.note{border-left:5px solid #dd962c;background:#fff8e8;padding:12px 18px}.good{color:#137250}.bad{color:#a53726}button,select{padding:8px 14px;border:1px solid #94a9bd;border-radius:6px;background:white;cursor:pointer}summary{cursor:pointer;color:#175b79;font-weight:600}svg{width:100%;height:auto}.small{font-size:14px;color:#566b7c}a{color:#176690}@media(max-width:850px){.grid{grid-template-columns:1fr}body{padding:10px}section{padding:16px}nav a{margin:0 5px}}
</style><h1>一台真实瞬态模拟器，四个不同的科研问题</h1>
<p>本页是本地物理校准的可检查说明。没有运行新 Agent 实验，也没有填写预期的模型胜率。每组是否校验通过，直接看下方验收表与逐题记录。</p>
<nav><a href="#map">代码地图</a><a href="#physics">物理推导</a><a href="#experiments">四项实验</a><a href="#tasks">任务数据</a><a href="#limits">结论边界</a></nav>
<section><h2>四组题目的出厂验收</h2><div id="status"></div><p class="small">先检查题目是否满足指定条件；模型能否利用这些信息，要在正式Agent实验中另行测量。</p></section>
<section id="map"><h2>1. 最小架构：不再穿过旧平台</h2>
<svg viewBox="0 0 1160 310" role="img" aria-label="四实验共用一个物理内核与报告出口">
<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="#52728c"/></marker></defs>
<g fill="#e8f2fb" stroke="#7599b8"><rect x="20" y="25" width="220" height="55" rx="9"/><rect x="20" y="95" width="220" height="55" rx="9"/><rect x="20" y="165" width="220" height="55" rx="9"/><rect x="20" y="235" width="220" height="55" rx="9"/><rect x="360" y="90" width="270" height="120" rx="12"/><rect x="770" y="40" width="360" height="90" rx="12"/><rect x="770" y="185" width="360" height="90" rx="12"/></g>
<g text-anchor="middle" font-size="18" fill="#213047"><text x="130" y="60">feedback.py：看什么</text><text x="130" y="130">active.py：先测什么</text><text x="130" y="200">structure.py：改什么结构</text><text x="130" y="270">stopping.py：凭什么停止</text><text x="495" y="130">common.py → ../sim.py</text><text x="495" y="165">实际负载、波形、固件与记录</text><text x="495" y="192">同一个完整瞬态消费者</text><text x="950" y="75">outputs/*.json：输入与校准结果</text><text x="950" y="108">不保存重复波形，不做哈希门禁</text><text x="950" y="220">report.py：STEP / 波形 / PDF</text><text x="950" y="251">explain.py：当前可视化说明</text></g>
<g stroke="#52728c" fill="none" stroke-width="2" marker-end="url(#a)"><path d="M240 52L310 52L360 125"/><path d="M240 122L360 140"/><path d="M240 192L360 160"/><path d="M240 262L310 262L360 185"/><path d="M630 130L770 85"/><path d="M630 175L770 230"/></g></svg>
<p>任务文件只负责定义“要考哪件事”。<code>sim.py</code> 计算真正发生了什么；反馈投影只决定公开哪些已有测量，不能改变物理结果。报告直接读通过设计和实际轨迹，没有另外一个“报告版模拟器”。</p>
<div class="grid"><div class="card"><b>删除的活动依赖</b><p>旧批次循环、恢复脚本、按哈希缓存、全局锁、计费门控、重复接口与旧框架代码。它们不在新运行路径中；旧代码可从父提交恢复，历史结果不删。</p></div><div class="card"><b>保留的必要检查</b><p>4条按时记录、误报、掉电、机械应力、位移和能量账。它们就是研究对象和工程输出，不是审批或安全框架。</p></div></div>
</section>
<section id="physics"><h2>2. 每个物理量如何影响下一环</h2>
<svg viewBox="0 0 1160 240"><g fill="#edf6ed" stroke="#6a9c7b"><rect x="10" y="25" width="220" height="80" rx="10"/><rect x="305" y="25" width="220" height="80" rx="10"/><rect x="605" y="25" width="220" height="80" rx="10"/><rect x="910" y="25" width="240" height="80" rx="10"/></g><g text-anchor="middle" font-size="18"><text x="120" y="57">背景振动 → 主梁</text><text x="120" y="85">几何 / 质量 / 阻尼</text><text x="415" y="57">压电 → 整流 → 电容</text><text x="415" y="85">电压与真实受载充电</text><text x="715" y="57">唤醒 → 采样 → 分类</text><text x="715" y="85">瞬时负载与阈值</text><text x="1030" y="57">保存 → 发送 → ACK</text><text x="1030" y="85">最终4条按时到达</text><text x="550" y="175">异常 → 辅梁 → 包络电压 → 比较器 → 唤醒</text><text x="550" y="220">电路负载 / 分流会反过来改变梁的振幅、相位、应力和可采能量</text></g><g stroke="#52728c" stroke-width="2" marker-end="url(#a)" fill="none"><path d="M230 65H305"/><path d="M525 65H605"/><path d="M825 65H910"/><path d="M715 105V140H150V105"/></g></svg>
<table><tr><th>部分</th><th>实际方程 / 单位</th><th>大白话含义与耦合</th></tr>
<tr><td>梁</td><td>m q̈ + c q̇ + k q − θv = −mᶠ a(t)<br>Cₚ v̇ = −θq̇ − i_load</td><td>梁不是固定电源。接上的电路会拉电流，也会改变梁怎么振。主梁为储能供电；辅梁把目标频率转换成唤醒信号。</td></tr>
<tr><td>几何</td><td>k = 3EI/L³；f ≈ √(k/m)/(2π)<br>应力 = Eₚ(hₛ/2+hₚ)·3|q|/L²</td><td>长度、厚度、端部质量同时影响频率和应力。加长不只是“把频率调低”，还改变刚度、质量和应力换算。</td></tr>
<tr><td>整流与储能</td><td>i_rect = max((|vₕ|−Vₛ−2V_d)/R,0)<br>Cₛ V̇ₛ = i_rect − i_load − i_leak</td><td>电容电压越高，整流越难继续充电。大电容能撑久，却可能启动晚；开路电压最高不等于带真实负载时最快交付。</td></tr>
<tr><td>固件</td><td>BOOT → SAMPLE → INFER → SAVE → TX → ACK<br>采样128点 / 2048 Hz = 62.5 ms</td><td>每个阶段耗时、耗电。电压跌破1.8 V就掉电；必须保住整个服务链，不是只保住第一次唤醒。</td></tr>
<tr><td>分类</td><td>实际采样、量化、FFT；目标频带能量占比≥0.55，RMS≥0.12g</td><td>能唤醒不代表分清目标和干扰。本轮不靠缩短采样窗或取消分类来让任务容易。</td></tr>
<tr><td>分流D</td><td>i_shunt = max((|vₕ|−V_threshold)/R_shunt,0)</td><td>这是现有电阻分流支路，耗散能量并反作用于机械响应；不是已经实现的SSDI开关，也不预设能减应力50%。</td></tr>
<tr><td>面积</td><td>当前梁投影面积 = Lₕbₕ + L𝑤b𝑤<br>基础设计：30×10 + 18×6 = 408 mm²</td><td>300 mm²不能直接施加到原双梁设计再宣称任务公平。若缩宽、变布局或重定义面积，必须把改动明写进输入。</td></tr>
<tr><td>能量账</td><td>E_input = E_damping + E_rectifier + E_frontend + E_MCU + E_idle + E_clamp + E_stored + residual</td><td>残差由每次真实积分得到。残差小只说明数值账自洽，不证明材料参数或单模态模型已经被实物校准。</td></tr></table>
<p class="note">新版本修正：A/B/C/D的显式寄生功耗在直接整流和转换器两种支路都计入。旧结果不回填。其他默认任务仍是30秒、四次目标、两次干扰、0.25秒交付期限、40 MPa和1.5 mm安全上限。</p>
</section>
<section id="experiments"><h2>3. 四组题目怎样构造、怎样验收</h2>
<table><tr><th>实验</th><th>要成立的物理条件</th><th>将来比较什么</th><th>什么结果会推翻预期</th></tr>
<tr><td>E1：反馈阶梯<br>目标20题</td><td>同一隐含偏差、同一设计域；初态0/4，公开域内有全PASS见证；F0⊂F1⊂F2⊂F3。</td><td>每题同模型同预算，L/A/Pi分别比较4种反馈。不能把Pi的自由工具和普通组的受限工具差异全归到“运行器”。</td><td>更多诊断没有提高成功率；或F0靠主动设计探针也达到同样水平。20题是实例数，不等于20种独立物理机制。</td></tr>
<tr><td>E2：主动测量<br>目标32对 / 64半题</td><td>初态公开信息逐字段相同；只开放指定电容轴或质量轴。两轮错位扫描、边界二分与更细积分复算，校验两半题通过带不交。</td><td>Blind / 自选0.2成本诊断 / 免费给诊断。完整评价次数、总成本、最终成功同时报告。</td><td>盲试可选一个共同可行点；或改其他变量绕过方向；或诊断成本没有带来净收益。初态相同不意味着多步探索仍无信息。</td></tr>
<tr><td>E3：结构 / 代理<br>目标16+16题</td><td>8道单梁控制题满足面积约束；8道结构题按声明域进行独立混合变量全域反例搜索与逐题复查；16道代理题实跑开路最优FAIL、受载见证PASS。</td><td>开路电压信息与受载整机诊断；结构切换是否必要，不能只看有没有启用模块。</td><td>开路最优也PASS；关闭目标结构仍找到同域全PASS；或结构增加了零件却没有改善完整服务。</td></tr>
<tr><td>E4：可靠停止<br>目标48题</td><td>S1当前分支有解；S2其他分支有解且当前被有效界排除；S3所有分支被界排除，并真实出现3/4近可行点。</td><td>仅点历史 / 当前分支界 / 全分支界。分别衡量找解、误报无解、识别真无解。</td><td>界并未覆盖全域；测试点被当成全局上界；上界太松不能排除；模型只复述证书却没改善寻找S1/S2解的能力。</td></tr></table>
<h3>反馈阶梯可以点击检查</h3><select id="level" onchange="showLevel()"><option value="0">F0：仅网关交付与安全合规</option><option value="1">F1：再看固件阶段计数</option><option value="2">F2：再看峰值电压与就绪时刻</option><option value="3">F3：再看实际幅相和逐事件窗口</option></select><pre id="fields"></pre>
<h3>“无解”的推导范围</h3><p>一个可验证的保守能量上界是：对每根梁，−c q̇²−Fq̇ ≤ F²/(4c)。从零初始能量出发，截止时刻前能够存下或花掉的能量，不可能超过 ∫a(t)² Σ(mᶠ)²/(4c) dt。将它与最小启动/服务能量比较，才可能排除指定设计域。上界大于需求只说明“不能排除”，绝不表示一定有解。</p>
<h3>另一种真正覆盖整支路的界：安全应力限制了直接整流能有多高的电压</h3><p>从压电端最近一次电压过零开始，电荷关系给出 <code>Cp·|v| ≤ |θ|·|q(t)−q(t₀)| ≤ 2|θ|q_max</code>。因此，不能一边要求梁始终安全，一边任意假设它能输出更高电压。新薄膜任务采用3.5µm压电层，40MPa应力限制对应端口上界约1.728V，经过二极管后储能至多约1.628V，低于原允许的最低启动电压1.9V。改变电容、质量、长度、输入电阻都绕不过这条直接支路的界；已有65%效率升压支路能完成4/4，转换损失也真实计入。</p><p>这条结论来自同一个模型中的电荷与应力方程，不是“随机搜了很多次没有找到”。薄膜厚度是公开的制造平台规格；启动电压和电容保留原1.9–3.2V、80–1000µF范围。</p>
<p>50%盲试上限只适用于对称先验、互不相交的可行域、且首提之前没有其他辨识信息的限定问题。不能从两条0/4记录推出整个Agent有50%的能力上限。F0接近0%、F3超过80%、诊断调用率90%都不是本轮已经得到的事实。</p>
</section>
<section id="tasks"><h2>4. 查看每道题的输入、见证与验收结果</h2><p>以下内容直接来自本轮JSON文件，不是手工填的成绩表。含隐藏偏差与见证的文件是<strong>开发者校准资料</strong>，将来不能整份发给被测Agent。</p><select id="files" onchange="showFile()"></select><pre id="payload"></pre></section>
<section id="limits"><h2>5. 报告、清理与使用方法</h2><p>工程PDF是同一消费者的工程结果展示。正式Agent实验尚未运行，因此本轮生成的设计称为“本地校准工程示例”；没有的Agent修正实录不虚构。报告中的工作包络是固定设计、有限网格的运行图，不是整个设计空间的可行性证明。CAD是单模态尺寸对应的实体示意，不冒充完整封装、走线PCB或制造资格。</p>
<pre>cd agent
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 -B wakeup/formal/calibrate.py --experiment e1
PYTHONDONTWRITEBYTECODE=1 python3 -B wakeup/formal/report.py --help
PYTHONDONTWRITEBYTECODE=1 python3 -B wakeup/formal/explain.py</pre>
<p>历史版本：<a href="https://github.com/littleandbrother/agent/tree/5c9569ba14fbba378210842f0453e1d69dd3b4f4">原统一分支固定提交</a>。新活动分支：<code>codex/formal-calibration-20261112</code>。本轮没有启动供应商请求，也没有恢复旧自动化。</p></section>
<script>const DATA=__DATA__;const ff=document.getElementById('files');Object.keys(DATA).forEach(k=>{let o=document.createElement('option');o.text=k;ff.add(o)});function showFile(){document.getElementById('payload').textContent=JSON.stringify(DATA[ff.value],null,2)};function showLevel(){const l=+document.getElementById('level').value;let s={F0:['PASS/FAIL','按时交付数 / 期望数','误报数','应力合规布尔值','位移合规布尔值']};if(l>=1)s.F1=['WAKE','CONFIRM','REJECT','BROWNOUT'];if(l>=2)s.F2=['首事件前电容电压 V','主梁/辅梁/包络峰值电压 V','首次就绪时刻 s'];if(l>=3)s.F3=['实际受载电压正弦拟合的幅值 V 与相位 deg','每个事件的前后电压和真实状态转换时间戳'];document.getElementById('fields').textContent=JSON.stringify(s,null,2)};const acceptance=(DATA['summary.json']||{}).task_acceptance||[];let table='<table><tr><th>实验</th><th>题目数量</th><th>出厂状态</th><th>已核对的物理条件</th></tr>';acceptance.forEach(row=>{table+='<tr>'+[row.experiment,row.count,row.status,row.checks].map(v=>'<td>'+v+'</td>').join('')+'</tr>'});document.getElementById('status').innerHTML=table+'</table>';showFile();showLevel();</script></html>'''
    target = HERE / "outputs" / "Architecture.html"
    target.write_text(template.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    return target


if __name__ == "__main__":
    print(build())
