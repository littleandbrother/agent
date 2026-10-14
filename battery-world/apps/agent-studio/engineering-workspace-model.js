/* Read-only projection. Sections organize artifacts; they never certify a design. */
(function (root) {
  const sections = [
    ['overview', '概览', '项目内容与最近结果'],
    ['schematic', '原理图', '电路图纸与原生工程'],
    ['pcb', 'PCB', '布线、层视图与制造资料'],
    ['mechanical', '结构', '模型、尺寸图纸与动作演示'],
    ['simulation', '仿真', '实际波形、计算结果与检查'],
    ['firmware', '固件', '构建产物、源码与测试记录'],
    ['bom', 'BOM', '已归档的元器件与材料清单'],
    ['documents', '文档', '报告与设计记录']
  ].map(([id, label, description]) => ({id, label, description}));
  const path = f => [f.name, f.source_path, f.path].filter(Boolean).join(' ').toLowerCase();
  function belongs(f, id) {
    if(id==='runtime')return false;
    if (Array.isArray(f.sections) && id !== 'overview') return f.sections.includes(id);
    const p = path(f), ext = (f.name || '').split('.').pop().toLowerCase();
    if (id === 'schematic') return /schematic|原理图|\.schdoc\b|\.sch\b|\.esch2\b|\.kicad_sch\b/.test(p);
    if (id === 'pcb') return f.domain !== 'mechanical' && !belongs(f, 'schematic') && !belongs(f, 'bom') && (/pcb|布线|gerber|drill|pick.?place|routing|\.brd\b|\.kicad_pcb\b/.test(p) || ['gbr','gbl','gtl','gbs','gts','drl','epro2','epru','epcb2'].includes(ext));
    if (id === 'mechanical') return f.domain === 'mechanical' || ['step','stp','stl','glb','blend','dxf'].includes(ext);
    if (id === 'simulation') return f.role === 'data' && f.domain !== 'firmware' && !belongs(f, 'bom') || /waveform|transient|simulation|simulat|\.raw\b|\.mph\b|\.cir\b|force.table|energy.balance|仿真|云图/.test(p);
    if (id === 'bom') return /\bbom\b|bill.of.material|元器件清单|材料清单|物料/.test(p);
    if (id === 'firmware') return f.domain==='firmware'||['elf','hex','bin'].includes(ext);
    if (id === 'documents') return ['pdf','tex','md','c','h','cpp','py','ts','elf','hex','bin'].includes(ext) || f.domain === 'firmware' || f.role === 'report';
    return true;
  }
  function files(snapshot, id) { return (snapshot.files || []).filter(f => belongs(f, id)); }
  function results(snapshot, id) {
    if (id === 'overview') return [...(snapshot.results || [])];
    const ids = new Set(files(snapshot, id).map(f => f.id));
    return (snapshot.results || []).filter(r => (r.files || []).some(f => ids.has(f.id)) ||
      id === 'mechanical' && r.domain === 'mechanical' ||
      id === 'firmware' && r.domain === 'firmware' || r.kind==='easyeda-'+id ||
      id === 'simulation' && ['door-selfpower','closed-simulation','door-system','spice','comsol','beam-event','event-transient','benchmark'].includes(r.kind));
  }
  function views(snapshot, id) {
    const allowed = new Set(files(snapshot, id).map(f => f.id));
    const seen = new Set(), out = [];
    for (const r of results(snapshot, id)) for (const v of r.presentations || []) {
      const f = (r.files || []).find(f => f.id === v.file_id);
      if (f?.integrity && allowed.has(f.id) && !seen.has(f.id)) { seen.add(f.id); out.push({r,v,f}); }
    }
    // Older records can have images/PDFs without a presentation declaration.
    for (const f of files(snapshot, id)) if (f.integrity && !seen.has(f.id)) {
      const ext = (f.name || '').split('.').pop().toLowerCase();
      const kind = ['png','jpg','jpeg','svg','webp'].includes(ext) ? 'image' : ext === 'pdf' ? 'pdf' : ext === 'mp4' ? 'video' : ext === 'glb' ? 'model' : ['simulation','bom'].includes(id) && ['csv','tsv','raw'].includes(ext) ? 'series' : null;
      if (kind) out.push({r: (snapshot.results || []).find(r => (r.files || []).some(x => x.id === f.id)), v:{kind,file_id:f.id}, f});
    }
    const curated=out.filter(x=>x.f.sections?.includes(id));
    const visible=curated.length && ['mechanical','pcb'].includes(id)?curated:out;
    const rank = x => (id==='mechanical'&&['model','mesh'].includes(x.v.kind)?-2:({image:0,series:1,model:2,mesh:2,video:3,pdf:4,text:5}[x.v.kind] ?? 5)) + (/combined|overview|installation|waveform|first-version-report|\/main\.c/.test(path(x.f)) ? -.1 : 0);
    return visible.sort((a,b) => rank(a)-rank(b));
  }
  function series(data) {
    if (data.table) return {table:true,headers:data.headers || [],rows:data.rows || []};
    const rows = (data.rows || []).filter(r => typeof r[0] === 'number' && Number.isFinite(r[0]));
    const namedUnits={time_s:'s',tip_m:'m',velocity_m_s:'m/s',piezo_V:'V',storage_V:'V',supply_V:'V',pgood_V:'V'};
    const columns = (data.headers || []).slice(1).map((name,i) => ({name,unit:namedUnits[name] || data.units?.[i+1] || '',index:i+1}))
      .filter(c => rows.some(r => typeof r[c.index] === 'number' && Number.isFinite(r[c.index])));
    return {table:false,headers:data.headers || [],rows,columns,lo:rows.length?Math.min(...rows.map(r=>r[0])):null,hi:rows.length?Math.max(...rows.map(r=>r[0])):null};
  }
  const labels = {minimum_clearance_mm:'最小铜间距 (mm)',minimum_trace_width_mm:'最窄走线 (mm)',unique_parts:'料号种数',fitted_parts:'装配件数','summary.maximum_storage_v':'最高储能电压 (V)','summary.minimum_input_v':'最低输入电压 (V)','energy_ledger.boot':'启动能量 (J)','energy_ledger.harvest':'采集能量 (J)','energy_ledger.dump':'钳位耗散 (J)','energy_ledger.esr_loss':'内阻损耗 (J)',peak_tip_mm:'梁端峰值 (mm)',peak_piezo_V:'压电峰值 (V)',peak_storage_V:'储能峰值 (V)',peak_supply_V:'供电峰值 (V)',VIN_peak_V:'输入峰值 (V)',tx_completed:'完整发送',received_events:'虚拟接收事件',displacement_mm:'位移 (mm)',max_von_mises_mpa:'等效应力 (MPa)',pads:'焊盘',tracks:'走线',vias:'过孔',flash_bytes:'Flash (bytes)',ram_static_bytes:'静态 RAM (bytes)',latency_ms:'延迟 (ms)',parameters:'模型参数量',power_mw:'功耗 (mW)',minimum_sampled_clearance_mm:'采样最小间距 (mm)',parts:'零件数量'};
  const api = {sections,belongs,files,results,views,series,metricLabel:name=>labels[name] || name};
  if (typeof module !== 'undefined') module.exports=api; else root.EngineeringWorkspaceModel=api;
})(typeof window !== 'undefined' ? window : this);
