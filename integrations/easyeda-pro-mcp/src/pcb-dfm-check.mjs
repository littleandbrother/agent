/**
 * pcb-dfm-check.mjs — EDA 域的连锡/撞件预检,补 EasyEDA DRC 的三个结构性盲区。
 *
 * ⛔ 这【不是】嘉立创 DFM 的替代品。下单前仍然必须跑一次 https://www.jlc-dfm.com/
 *    ——它是 Gerber 域、由真正造板的厂维护,阈值才是工厂的实际能力;本脚本的阈值只是
 *    观测/反推值(见下方 mask 一节),会过期。冲突时以 JLC DFM / 工厂回复为准。
 *
 * 那为什么还要这个脚本?因为有两样东西 Gerber 里【根本不存在】,JLC DFM 结构上给不了:
 *
 *   ① 网表语义 —— Gerber 只有铜/阻焊/丝印/钻孔,没有网络。所以 JLC DFM 能告诉你
 *      "这两个焊盘的阻焊桥只有 0.05mm",但不能告诉你"它俩同网,桥了无害"还是
 *      "异网,桥了就是电源对地短"。⭐ 而这恰恰是唯一要紧的判断。
 *      更要紧的是【邻缝分诊】:同网≠安全,锡不会精确停在那条缝上 —— 本脚本对每个
 *      同网告警都回答"往外串几格才碰到异网、那格离多远"。
 *   ② 器件体包络 —— Gerber 里没有器件本体,CPL 只有坐标没有尺寸。"封装体大于焊盘、
 *      回流时撞件"这类只能在 EDA 域算(3D Model Transform 前两字段 = 真实器件体 XY)。
 *
 * 还有一个工作流差异(不是能力差异):本脚本【画的时候就能跑】,不用先导 Gerber,
 * 所以能进下单前必跑项 / 让 agent 直接调。JLC DFM 是下单前的权威闸门。
 *
 * ⇒ 分工:本脚本 = 早期预警 + 网表分诊;JLC DFM = 下单前终审。两个都要跑。
 *
 * 缘起:某批产线 QC 实测出三处连锡,而当时 `pcb_Drc.check(strict)` = **0 违规**。根因是 DRC 三个盲区:
 *   - 没有「同网最小间距」概念(Safe Spacing 是 clearance 语义,只管异网),而这三处全同网
 *   - 没有「阻焊桥宽度」检查(那是 Gerber 域的量,规则引擎在网表/铜层域)
 *   - 没有「焊盘内过孔(via-in-pad)」检查(Via↔SMD Pad 那格同网豁免)
 * 
 *
 * 三查:
 *   mask  阻焊桥净宽 = 铜边间距 − 2×阻焊开窗 < 阈值(⭐含同网;异网 DRC 已经管了)
 *         ⭐⭐ 这一项【不是】纯重复:JLC DFM 的对应检查叫「相邻两阻焊开窗平行边缘
 *         间距」—— 顾名思义要有【两个开窗】才测得到。一旦两个开窗已经重叠合并成
 *         一个,它就【没有对象可报】。实证(某批投板):工厂 DFM 报的 50 条里最小
 *         值是 0.03mm、**无一负数**,而本脚本在同一块板上查出 **−0.018mm 与 −0.008mm**
 *         两处(一对晶振↔电容焊盘、一对相邻电容)—— 全板最糟的几处工厂 DFM 一条都没报。⇒ 负值区是它的结构盲区,
 *         恰恰是"必连"的那一档。
 *         ⚠ 阈值:帮助文档写 0.075mm,但实测 JLC 报到 0.1mm 且全标"危险"
 *         ⇒ 默认已改为 0.1mm。这仍是观测值,以工厂当次回复为准。
 *   via   过孔落进焊盘开窗 / 到焊盘边过近(⭐含同网)。⚠ 过孔即使全局盖油,
 *         只要压在焊盘上就会被焊盘自己的开窗露出来 —— 盖油救不了 via-in-pad
 *   body  器件体 3D 包络重叠(撞件)。DRC 的 device2device 顶不上:它量器件体时
 *         晶振这类「本体小于焊盘伸展」的会漏(实测某对器件:器件体间距 0.583mm 而焊盘间距仅 0.084mm)
 *   pour  铺铜「灌没灌过」:有边框但没有对应填充 = 从没灌过。
 *         ⚠ **只答在场,不答新鲜度** —— EasyEDA API 既没有脏标记/时间戳,也**没有任何
 *         「重新灌注」入口**(2026-08-05 三步实测:文档 / 运行时枚举 / `String(fn)` 验空壳,
 *         `pcb_PrimitivePoured.create`、`.modify` 都是 `(){}`)。⇒ 动过走线之后重灌**只能靠人**,
 *         这条检查抓的是「画了铜皮却一次都没灌」这种最粗的错。
 *
 * Usage:
 *   node src/pcb-dfm-check.mjs                    三查全跑,人读报告
 *   node src/pcb-dfm-check.mjs --json             机读
 *   node src/pcb-dfm-check.mjs --only mask,via    只跑指定项
 *   node src/pcb-dfm-check.mjs --mask-min 0.09    改阻焊桥下限(mm,默认 0.1;见上方阈值说明)
 *   node src/pcb-dfm-check.mjs --via-margin 0.08  改过孔到焊盘边下限(mm,默认 0.05)
 *   node src/pcb-dfm-check.mjs --triage-span 3    邻缝分诊往外看几格(默认 3)
 *   node src/pcb-dfm-check.mjs --window <id>      指定 EDA 窗口(id 见 GET /eda-windows 或
 *                                             eda_windows;env EDA_WINDOW_ID 同效)。
 *                                             不给 = 用 bridge 的"活动窗口",而它会在
 *                                             两次运行之间自己飘走 —— 同开两个窗口时
 *                                             务必显式给,别只靠核对报告第一行。
 *
 * Exit: 0 = 无告警 · 1 = 有告警 · 2 = 基础设施错误(桥/EDA 不在)
 *
 * 前置:EasyEDA Pro 开着 + bridge 在跑(见 README)。
 */
// 找桥 / 发 HTTP / 解析 --window 全在这一份共享底座里(此前四个脚本各抄一份)
import { findBridge, exec as bridgeExec, parseWindowArg, windowTag } from './bridge-client.mjs';

const MM = 0.0254; // 1 mil = 0.0254 mm

// 目标窗口:null = bridge 当前的"活动窗口"(会飘,见文件头 --window)。
let WINDOW_ID = null;

// 整板分析是一次阻塞调用,socket 超时给到 90s(eext 侧仍是它自己的默认执行超时)
const exec = (port, code) => bridgeExec(port, code, { windowId: WINDOW_ID, httpTimeoutMs: 90000 });

// ------------------------------------------------------- 在 EDA 里跑的分析核心
// 放在 EDA 内做,是因为 834 焊盘 / 412 过孔 / 212 器件全量传回来是几百 KB,
// 而算完只剩几十条 finding。几何用 AABB —— 本板旋转恒为 90° 整数倍,精确。
const ANALYSIS = (opt) => `
const OPT = ${JSON.stringify(opt)};
const MM = 0.0254;
const mm = v => Math.round(v * MM * 1000) / 1000;

const pads  = await eda.pcb_PrimitivePad.getAll();
const vias  = await eda.pcb_PrimitiveVia.getAll();
const comps = await eda.pcb_PrimitiveComponent.getAll();

// ---- 阻焊开窗:优先用规则值(权威),per-pad 覆盖值单位与规则差 10 倍,做一次标定
let ruleExp = null;
try {
  const cfg = await eda.pcb_Drc.getCurrentRuleConfiguration();
  ruleExp = cfg?.config?.Expansion?.['Solder Mask Expansion']
               ?.solderMaskExpansion?.form?.padToplayerExpansion ?? null;
} catch (e) { /* 读不到就退回默认 */ }
const DEFAULT_EXP = 2.0079;                    // mil,EasyEDA/JLC 常见默认 0.051mm
const baseExp = (typeof ruleExp === 'number' && ruleExp > 0) ? ruleExp : DEFAULT_EXP;
// per-pad 值的众数,用来求 scale(实测 per-pad 0.20079 ↔ 规则 2.0079 ⇒ scale=10)
const tally = {};
for (const p of pads) {
  const v = p.solderMaskAndPasteMaskExpansion?.topSolderMask;
  if (typeof v === 'number') tally[v] = (tally[v] || 0) + 1;
}
let mode = null, mc = -1;
for (const k in tally) if (tally[k] > mc) { mc = tally[k]; mode = Number(k); }
let scale = 1;
if (mode != null && mode > 0) {
  const r = baseExp / mode;
  for (const cand of [0.1, 1, 10, 100]) if (Math.abs(r - cand) / cand < 0.05) scale = cand;
}
const expOf = p => {
  const v = p.solderMaskAndPasteMaskExpansion?.topSolderMask;
  return (typeof v === 'number' && v > 0) ? v * scale : baseExp;
};

// ---- 几何:AABB 半宽/半高(旋转为 90° 整数倍时精确)
const halfOf = (shape, rot) => {
  if (!shape || !shape.length) return null;
  const r = Math.abs(rot || 0);
  const swap = Math.abs(r - Math.PI / 2) < 0.01 || Math.abs(r - 3 * Math.PI / 2) < 0.01;
  let w, h;
  if (shape[0] === 'ELLIPSE') { w = shape[1]; h = shape[2] ?? shape[1]; }
  else { w = shape[1]; h = shape[2]; }
  if (w == null || h == null) return null;
  if (swap) { const t = w; w = h; h = t; }
  return [w / 2, h / 2];
};

// 只看顶层(layer 1)与全层(12);底层本板无贴装件
const P = [];
for (const p of pads) {
  if (p.layer !== 1 && p.layer !== 12) continue;
  const hf = halfOf(p.pad, p.rotation);
  if (!hf) continue;
  P.push({ p, hw: hf[0], hh: hf[1], exp: expOf(p) });
}

// ---- 焊盘 → 器件归属:按 (padNumber,net) 建索引再取最近中心
const idx = new Map();
for (const c of comps) for (const q of (c.pads || [])) {
  const k = q.padNumber + '|' + q.net;
  if (!idx.has(k)) idx.set(k, []);
  idx.get(k).push(c);
}
const ownerOf = (p) => {
  const cands = idx.get(p.padNumber + '|' + p.net);
  if (!cands) return null;
  let best = null, bd = 1e9;
  for (const c of cands) { const d = Math.hypot(c.x - p.x, c.y - p.y); if (d < bd) { bd = d; best = c; } }
  return (best && bd < 250) ? best.designator : null;
};
for (const o of P) o.des = ownerOf(o.p);
const label = o => (o.des ? o.des + '.' : '?') + o.p.padNumber;

// 铜边到铜边(AABB)
const copperGap = (A, B) => {
  const dx = Math.abs(A.p.x - B.p.x) - (A.hw + B.hw);
  const dy = Math.abs(A.p.y - B.p.y) - (A.hh + B.hh);
  return Math.hypot(Math.max(0, dx), Math.max(0, dy));
};
const damOf = (A, B) => copperGap(A, B) - A.exp - B.exp;

// ================================================ ① 阻焊桥净宽(含同网)
const MASK_MIN = OPT.maskMinMm / MM;
const SPAN = OPT.triageSpanMm / MM;
const maskFindings = [];
if (OPT.checks.includes('mask')) {
  for (let i = 0; i < P.length; i++) for (let j = i + 1; j < P.length; j++) {
    const A = P[i], B = P[j];
    if (Math.abs(A.p.x - B.p.x) > 200 || Math.abs(A.p.y - B.p.y) > 200) continue;
    const dam = damOf(A, B);
    if (dam >= MASK_MIN) continue;
    const sameNet = A.p.net === B.p.net;
    // ⭐ 邻缝分诊:同网告警时,往外找最近的异网焊盘,答"串几格才出事"
    let triage = null;
    if (sameNet) {
      let bestGap = Infinity, bestPad = null;
      for (const C of P) {
        if (C === A || C === B || C.p.net === A.p.net) continue;
        const g = Math.min(copperGap(A, C), copperGap(B, C));
        if (g < bestGap) { bestGap = g; bestPad = C; }
      }
      if (bestPad && bestGap <= SPAN) {
        triage = { 最近异网: label(bestPad), 网络: bestPad.p.net,
                   铜间距_mm: mm(bestGap), 阻焊桥_mm: mm(bestGap - A.exp - bestPad.exp) };
      }
    }
    maskFindings.push({
      对: label(A) + ' ↔ ' + label(B),
      网络: A.p.net + (sameNet ? ' (同网)' : ' | ' + B.p.net + ' ⛔异网'),
      sameNet,
      铜间距_mm: mm(copperGap(A, B)),
      阻焊桥_mm: mm(dam),
      xy: '(' + Math.round((A.p.x + B.p.x) / 2) + ',' + Math.round((A.p.y + B.p.y) / 2) + ')',
      邻缝分诊: triage,
    });
  }
  maskFindings.sort((a, b) => a.阻焊桥_mm - b.阻焊桥_mm);
}

// ================================================ ② 过孔 vs 焊盘(含同网)
const VIA_MARGIN = OPT.viaMarginMm / MM;
const viaFindings = [];
if (OPT.checks.includes('via')) {
  for (const v of vias) {
    const R = (v.diameter ?? 0) / 2;
    if (!R) continue;
    const hits = [];
    for (const A of P) {
      const dx = Math.max(0, Math.abs(v.x - A.p.x) - A.hw);
      const dy = Math.max(0, Math.abs(v.y - A.p.y) - A.hh);
      const gap = Math.hypot(dx, dy) - R;      // 负 = 过孔压在焊盘上
      if (gap < VIA_MARGIN) hits.push({ A, gap });
    }
    if (!hits.length) continue;
    hits.sort((a, b) => a.gap - b.gap);
    const inPad = hits.filter(h => h.gap < 0);
    const cross = hits.filter(h => h.A.p.net !== v.net);
    // 只有能同时够到 ≥2 个焊盘才可能"连"起来;或够到异网焊盘
    if (hits.length < 2 && !cross.length) continue;
    viaFindings.push({
      过孔: v.net + ' @(' + Math.round(v.x) + ',' + Math.round(v.y) + ') Ø' + v.diameter + '/孔' + v.holeDiameter,
      压在焊盘上: inPad.map(h => label(h.A) + ' ' + h.A.p.net + ' 重叠' + mm(-h.gap) + 'mm'),
      过近: hits.filter(h => h.gap >= 0).map(h => label(h.A) + ' ' + h.A.p.net + ' ' + mm(h.gap) + 'mm'),
      判定: cross.length ? ('⛔异网:' + cross.map(h => label(h.A) + ' ' + h.A.p.net).join(','))
                         : (inPad.length ? '⚠ via-in-pad(全同网,但会供锡把两焊盘连起来)' : '全同网'),
      hasCross: cross.length > 0,
      hasInPad: inPad.length > 0,
    });
  }
  viaFindings.sort((a, b) => (b.压在焊盘上.length - a.压在焊盘上.length));
}

// ================================================ ③ 器件体包络重叠(撞件)
// ⭐ 2026-08-05:'3D Model Transform' 的字段映射【已实证定死】,原先记的"歧义"是本脚本
//    自己【字段错位一格】造成的假象。正确映射 = [sizeX, sizeY, ?, rotZ, ?, ?, offX, offY, offZ]
//    ⇒ offX = t[6] · offY = t[7](本脚本原先读的是 t[7]/t[8],把 Y 偏移当成了 X 偏移)。
//    ⚠ 本段在 ANALYSIS 模板字符串(第 111–325 行)内,注释里【不能出现反引号,也不能出现 $ 加大括号】。
//
//    三条独立验证(把 offY 叠上去后算"器件体探出板框多少",与 pcb-3d-envelope.json 的 over
//    实测值对比;那份 envelope 来自 EasyEDA 导出的 OBJ 真网格,与本字段完全独立):
//      J2          t[7]=−89.567mil → 探边 1.137mm   vs envelope over 1.13  ✔
//      USB_DATA_1  t[7]=−47.244mil → 探边 0.672mm   vs envelope over 0.68  ✔
//      USB_PWR_1   同上            → 探边 0.545mm   vs envelope over 0.56  ✔
//    错位读法(t[7]/t[8])在这三个上分别给 2.162 / 0.372 / 0.245mm,全错。
//    H1/H2 的 t[6]=t[7]=0(只有 t[8]=−118.11 的 Z 偏移)⇒ 正确映射下它们本来就不平移,
//    这正是原注释里"不叠加 H1 才对"的真相 —— 不是"不该叠",是"它的 XY 偏移本来就是 0"。
//
//    ⚠ 由此翻案:C90 / C92 ↔ U5 那条不是干涉。U5 的 t[7]=−78.74mil=−2.0mm 是【Y】偏移,
//    模块本体落在 y_up 29.64…47.64,而两颗 0402 在 49.91 ⇒ 净空 1.77mm。错位读法把这 2mm
//    推到了 X 上,而 C90/C92 在 U5 的 X 跨度之内,所以"叠不叠都重叠" —— 两种解释同错。
//    (rotZ = 第 4 字段仍然确定要用:R40↔R41 不用 rotZ 读作 −0.169mm,用了是 +0.64mm。)
const bodyFindings = { confident: [], ambiguous: [] };
if (OPT.checks.includes('body')) {
  const boxOf = (c) => {
    const t = (c.otherProperty?.['3D Model Transform'] || '').split(',').map(Number);
    if (!t.length || !t[0] || !t[1]) return null;
    let w = t[0], h = t[1];
    const tot = (((c.rotation + (t[3] || 0)) % 180) + 180) % 180;   // 器件旋转 + 模型 rotZ
    if (Math.abs(tot - 90) < 1) { const s = w; w = h; h = s; }
    const a = (c.rotation || 0) * Math.PI / 180, ux = t[6] || 0, uy = t[7] || 0;
    const ox = ux * Math.cos(a) - uy * Math.sin(a);
    const oy = ux * Math.sin(a) + uy * Math.cos(a);
    return { d: c.designator, x1: c.x + ox - w / 2, x2: c.x + ox + w / 2,
                              y1: c.y + oy - h / 2, y2: c.y + oy + h / 2 };
  };
  const bgap = (A, B) => {
    const dx = Math.max(A.x1 - B.x2, B.x1 - A.x2);
    const dy = Math.max(A.y1 - B.y2, B.y1 - A.y2);
    return (dx > 0 || dy > 0) ? Math.hypot(Math.max(0, dx), Math.max(0, dy))
                              : -Math.min(-dx, -dy);              // 负 = 真重叠
  };
  const bs = comps.map(c => boxOf(c)).filter(Boolean);
  for (let i = 0; i < bs.length; i++) for (let j = i + 1; j < bs.length; j++) {
    const g = bgap(bs[i], bs[j]);
    if (g >= OPT.bodyMinMm / MM) continue;
    const rec = { 对: [bs[i].d, bs[j].d].sort().join(' ↔ '), 间隙_mm: mm(g) };
    // 负 = 真重叠(必须处理);正 = 只是靠得近(贴装风险,目视即可)
    (g < 0 ? bodyFindings.confident : bodyFindings.ambiguous).push(rec);
  }
  bodyFindings.confident.sort((a, b) => a.间隙_mm - b.间隙_mm);
  bodyFindings.ambiguous.sort((a, b) => a.间隙_mm - b.间隙_mm);
}

// ⚠ 必报「读的是哪块板」。曾经踩过:同时开着两个 EasyEDA 窗口时,bridge 的 active window
//    会在两次调用之间飘走,于是本脚本静默地把【另一个工程的另一块板】当成结果报了出来
//    (那次把另一个工程的一对连接器当成了本板的撞件)。位号在各板独立编号 ⇒ 光看
//    报告完全分辨不出来。⇒ 结果里必须带 scope,人和 agent 都要先核一眼板名再采信。
let _scope = {};
let _pourMeta = {};
try {
  const pi = await eda.dmt_Project.getCurrentProjectInfo();
  const bi = await eda.dmt_Board.getCurrentBoardInfo().catch(() => null);
  _scope = { 工程: pi?.name ?? '?', 板: bi?.name ?? '?' };
} catch (e) { _scope = { 工程: '?', 板: '?', err: JSON.stringify(e) }; }

// ④ 铺铜「灌没灌过」—— 只能查在场,查不了新鲜度(见下面 report 里的诚实声明)。
// 为什么值得单列一条:EasyEDA 的 API **没有任何"重新灌注"入口**(2026-08-05 三步实测:
// 文档 / 运行时枚举 / String(fn) 验空壳 —— pcb_PrimitivePoured 的 create/modify 都是空函数体),
// 所以「动过走线要重灌」这条 checklist 项 agent 做不了,只能靠人点。那至少要能抓住最粗的一种错:
// **画了铺铜边框但一次都没灌**(或某一层的边框全是空的)。
let pourFindings = [];
try {
  const pours = await eda.pcb_PrimitivePour.getAll();
  const poured = await eda.pcb_PrimitivePoured.getAll();
  // poured 图元通过 getState_PourPrimitiveId() 指回它属于哪个边框
  const filled = new Set();
  for (const pd of (poured || [])) {
    try { const id = pd.getState_PourPrimitiveId(); if (id) filled.add(id); } catch (e) {}
  }
  for (const p of (pours || [])) {
    let id = '', net = '', layer = '', name = '';
    try { id = p.getState_PrimitiveId(); } catch (e) {}
    try { net = p.getState_Net(); } catch (e) {}
    try { layer = String(p.getState_Layer()); } catch (e) {}
    try { name = p.getState_PourName() || ''; } catch (e) {}
    if (!filled.has(id)) pourFindings.push({ 铺铜: name || id, 网络: net || '(无网)', 层: layer, 状态: '未灌注' });
  }
  _pourMeta = { 边框数: (pours || []).length, 已灌注边框数: filled.size, 填充图元数: (poured || []).length };
} catch (e) { _pourMeta = { err: JSON.stringify(e) }; }

return {
  meta: {
    scope: _scope,
    铺铜: _pourMeta,
    焊盘数: P.length, 过孔数: vias.length, 器件数: comps.length,
    阻焊开窗_mm: mm(baseExp), 开窗来源: (typeof ruleExp === 'number' ? '规则实读' : '默认值(规则读不到)'),
    perPadScale: scale,
    阈值: { 阻焊桥_mm: OPT.maskMinMm, 过孔到焊盘_mm: OPT.viaMarginMm, 器件体_mm: OPT.bodyMinMm },
  },
  mask: maskFindings, via: viaFindings, body: bodyFindings, pour: pourFindings,
};
`;

// ------------------------------------------------------------------ CLI / 报告
function parseArgs(argv) {
  const o = { json: false, maskMinMm: 0.1, viaMarginMm: 0.05, bodyMinMm: 0.0,
              triageSpanMm: 3 * 0.0254 * 10, checks: ['mask', 'via', 'body', 'pour'] };
  o.triageSpanMm = 0.3; // 默认往外看 0.3mm(≈0.5mm pitch 连接器的两三格)
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') o.json = true;
    else if (a === '--mask-min') o.maskMinMm = Number(argv[++i]);
    else if (a === '--via-margin') o.viaMarginMm = Number(argv[++i]);
    else if (a === '--body-min') o.bodyMinMm = Number(argv[++i]);
    else if (a === '--triage-span') o.triageSpanMm = Number(argv[++i]);
    else if (a === '--only') o.checks = argv[++i].split(',').map(s => s.trim());
    else if (a === '-h' || a === '--help') { o.help = true; }
  }
  return o;
}

const HELP = `pcb-dfm-check.mjs — EDA 域连锡/撞件预检(补 DRC 盲区)

  ⛔ 不是嘉立创 DFM 的替代品,下单前仍须跑 https://www.jlc-dfm.com/
     本脚本的独有价值 = 网表分诊(同网/异网 + 邻缝) + 器件体包络,这两样 Gerber 里没有。

  --json                 机读输出
  --only mask,via,body,pour  只跑指定项(默认全跑)
  --mask-min <mm>        阻焊桥下限,默认 0.1(实测 JLC 报到 0.1 且全标"危险";帮助文档写 0.075)
  --via-margin <mm>      过孔到焊盘边下限,默认 0.05
  --body-min <mm>        器件体最小间距,默认 0(即只报真重叠)
  --triage-span <mm>     邻缝分诊往外看多远,默认 0.3
  --window <id>          指定 EDA 窗口(eda_windows / GET /eda-windows;env EDA_WINDOW_ID 同效)
                         不给 = bridge 的活动窗口,而它会自己飘走

  exit 0=无告警 1=有告警 2=桥/EDA 不在`;

function report(r, opt) {
  const L = [];
  const m = r.meta;
  L.push(`[pcb-dfm-check] ⚠ 读的是: 工程 ${m.scope?.工程 ?? '?'} / 板 ${m.scope?.板 ?? '?'}`
    + `  ·  窗口 ${windowTag(WINDOW_ID)}  ← 先核这一行,不对就用 --window 钉死`);
  L.push(`  焊盘 ${m.焊盘数} · 过孔 ${m.过孔数} · 器件 ${m.器件数}`);
  L.push(`  阻焊开窗 ${m.阻焊开窗_mm}mm/单边 (${m.开窗来源})  阈值: 阻焊桥<${m.阈值.阻焊桥_mm}mm · 过孔<${m.阈值.过孔到焊盘_mm}mm · 器件体<${m.阈值.器件体_mm}mm`);
  L.push('');

  if (opt.checks.includes('mask')) {
    const cross = r.mask.filter(f => !f.sameNet);
    const risky = r.mask.filter(f => f.sameNet && f.邻缝分诊);
    L.push(`── ① 阻焊桥净宽 < ${m.阈值.阻焊桥_mm}mm ── ${r.mask.length} 处 (异网 ${cross.length} · 同网 ${r.mask.length - cross.length})`);
    if (!r.mask.length) L.push('   ✅ 无');
    for (const f of r.mask) {
      const flag = f.sameNet ? '  ' : '⛔';
      L.push(`${flag} ${f.对.padEnd(22)} ${String(f.阻焊桥_mm).padStart(7)}mm  铜间距 ${f.铜间距_mm}mm  ${f.网络}  ${f.xy}`);
      if (f.阻焊桥_mm < 0) L.push(`     ↳ 负值 = 两个开窗直接连通,没有绿油坝,必连`);
      if (f.邻缝分诊) {
        const t = f.邻缝分诊;
        L.push(`     ↳ ⚠ 邻缝分诊: 最近异网 ${t.最近异网} (${t.网络}) 铜间距 ${t.铜间距_mm}mm / 阻焊桥 ${t.阻焊桥_mm}mm —— 锡再串一点就是真短路`);
      } else if (f.sameNet) {
        L.push(`     ↳ 同网,且 ${opt.triageSpanMm}mm 内无异网焊盘 ⇒ 桥了电气等价`);
      }
    }
    L.push('');
  }

  if (opt.checks.includes('via')) {
    const bad = r.via.filter(f => f.hasCross);
    L.push(`── ② 过孔 vs 焊盘(含同网) ── ${r.via.length} 处 (异网 ${bad.length})`);
    if (!r.via.length) L.push('   ✅ 无');
    for (const f of r.via) {
      L.push(`${f.hasCross ? '⛔' : (f.hasInPad ? '⚠ ' : '  ')} ${f.过孔}`);
      if (f.压在焊盘上.length) L.push(`     压在焊盘上: ${f.压在焊盘上.join(' · ')}`);
      if (f.过近.length)       L.push(`     过近:       ${f.过近.join(' · ')}`);
      L.push(`     ${f.判定}`);
    }
    L.push('');
  }

  if (opt.checks.includes('body')) {
    const cf = r.body.confident, am = r.body.ambiguous;
    L.push(`── ③ 器件体包络(撞件) ── 真重叠 ${cf.length} · 靠太近 ${am.length}`);
    if (!cf.length) L.push('   ✅ 真重叠:无');
    for (const f of cf) L.push(`⛔ ${f.对.padEnd(24)} ${String(f.间隙_mm).padStart(7)}mm  ← 器件体真重叠`);
    if (am.length) {
      L.push(`   ── 未重叠但间隙 < ${mm(OPT.bodyMinMm / MM)}mm(贴装风险,目视即可)`);
      for (const f of am) L.push(`   ? ${f.对.padEnd(24)} ${String(f.间隙_mm).padStart(7)}mm`);
    }
    L.push('');
  }

  if (opt.checks.includes('pour')) {
    const pm = m.铺铜 || {};
    const bad = r.pour || [];
    L.push(`── ④ 铺铜灌注 ── 边框 ${pm.边框数 ?? '?'} · 已灌注 ${pm.已灌注边框数 ?? '?'} · 填充图元 ${pm.填充图元数 ?? '?'}`);
    if (pm.err) L.push(`   ⚠ 读不到铺铜信息: ${pm.err}`);
    else if (!pm.边框数) L.push('   — 本板没有铺铜边框(不适用)');
    else if (!bad.length) L.push('   ✅ 每个铺铜边框都有对应的灌注填充');
    for (const f of bad) L.push(`⛔ ${String(f.铺铜).padEnd(24)} 网络 ${f.网络}  层 ${f.层}  ← 有边框、无填充 = 从没灌过`);
    // ⚠ 诚实边界:这条只能证明"灌过",不能证明"是最新的"。
    // EasyEDA 的 API 里既没有"重新灌注"入口(pcb_PrimitivePoured.create/modify 是空壳),
    // 也没有脏标记/时间戳 ⇒ 改完走线不重灌,填充照样在那儿、这条照样过。
    L.push('   ⚠ 本项只答「灌没灌过」,**答不了「是不是最新的」** —— API 没有脏标记/时间戳,');
    L.push('     且**没有任何"重新灌注"接口**(实测:`pcb_PrimitivePoured.create/modify` 是空壳)。');
    L.push('     ⇒ 动过走线/器件/板框之后,**必须由人在 EDA 里手动重灌**,这条检查不能替代那一步。');
    L.push('');
  }

  L.push('⚠ 本脚本是【早期预警 + 网表分诊】,不是可制造性闸门。');
  L.push('  下单前仍须跑嘉立创 DFM(https://www.jlc-dfm.com/) —— 阻焊桥/孔径/线宽的');
  L.push('  权威阈值以工厂为准;本脚本的 0.1mm 是实测反推的观测值,会过期。');
  return L.join('\n');
}

(async () => {
  // parseWindowArg 先摘掉 --window 及其取值(parseArgs 从 index 2 起读,所以把头两项还回去)
  const { windowId, rest } = parseWindowArg(process.argv.slice(2));
  WINDOW_ID = windowId;
  const opt = parseArgs([process.argv[0], process.argv[1], ...rest]);
  if (opt.help) { console.log(HELP); process.exit(0); }

  const br = await findBridge();
  if (!br) {
    console.error('[pcb-dfm-check] 没找到 easyeda-bridge (49620-49629)。先起桥 / 开 EasyEDA。');
    console.error('  见 README');
    process.exit(2);
  }
  if (!br.health.edaConnected) {
    console.error(`[pcb-dfm-check] 桥在 :${br.port} 但没有 EDA 窗口连上。打开 EasyEDA Pro 并载入 PCB。`);
    process.exit(2);
  }

  let r;
  try {
    r = await exec(br.port, ANALYSIS(opt));
  } catch (e) {
    console.error('[pcb-dfm-check] 分析失败:', e && e.message ? e.message : String(e));
    console.error('  提示:当前活动文档必须是 PCB(不是原理图)。');
    process.exit(2);
  }

  if (opt.json) { console.log(JSON.stringify(r, null, 2)); }
  else { console.log(report(r, opt)); }

  const n = (r.mask?.length || 0) + (r.via?.length || 0) + (r.body?.length || 0);
  process.exit(n ? 1 : 0);
})();
