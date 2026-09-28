/* Draft starters, not pre-verified designs. Selecting one never sends it. */
(() => {
  const root=document.querySelector('#case-suggestions');
  const ideas=[
    ['旋转设备','不换电池，也能知道设备有没有正常运转？','我想监测旋转设备是否正常运转，尽量不用更换电池。我不太了解技术细节，请先假设一个合理的现场，说明产品形态、安装方式和能量来源，再设计验证步骤。'],
    ['仓库门','用开关门的能量，记录一次开门事件','我想做一个靠开关门取能的仓库门状态提醒器。条件不清楚的地方请先作合理假设，考虑安装尺寸、机械取能、电路和事件送达，并说明哪些部分能计算验证。'],
    ['室内传感','光线很弱的室内，传感器能持续工作吗？','我想在低照度室内部署不用换电池的环境传感器。请先选择一种具体场景，提出可修改的工作频率和尺寸假设，计算能量收支；不满足时调整设计。'],
    ['管道安装','给现有管道加一个可拆卸的监测夹具','请探索一个可拆卸的管道监测节点。先假设管径和使用环境，考虑夹具尺寸、传感接触和供能条件，列出需要验证的机械和电气问题。'],
    ['户外监测','连续阴天时，户外节点怎样少漏报？','我想做一个户外免维护监测节点。请假设一个具体用途，考虑连续阴天的能量不足，设计采样、储能和无线发送策略，并提出验证方案。'],
    ['从想法开始','我只有一个想法，帮我把它变成产品方案','我还没有明确需求，请选一个适合免电池 AIoT 的具体场景，把用途、产品形态、安装方式、尺寸假设和验证步骤讲清楚，再逐步设计。']
  ];
  let mode=localStorage.getItem('bf-case-suggestions')||'compact';
  function update(){
    root.hidden=!!window.BF.getSelection();
    if(root.hidden)return;
    const {esc}=window.BF;
    root.innerHTML=mode==='hidden'?'<button class="case-toggle" data-case-mode="compact">显示一些想法</button>':
      `<div class="case-list">${ideas.slice(0,mode==='expanded'?ideas.length:3).map(([topic,title],i)=>`<button class="case-idea" data-case="${i}" title="填入输入框后可修改"><span class="case-topic">${esc(topic)}</span><span>${esc(title)}</span><svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 8h10m-4-4 4 4-4 4"/></svg></button>`).join('')}</div><div class="case-controls"><button class="case-toggle" data-case-mode="${mode==='expanded'?'compact':'expanded'}" aria-expanded="${mode==='expanded'}">${mode==='expanded'?'收起':'更多想法'}</button><button class="case-toggle" data-case-mode="hidden">隐藏建议</button></div>`;
    root.querySelectorAll('[data-case]').forEach(b=>b.onclick=()=>window.BF.setDraft(ideas[Number(b.dataset.case)][2]));
    root.querySelectorAll('[data-case-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.caseMode;localStorage.setItem('bf-case-suggestions',mode);update()});
  }
  window.Cases={update};
  window.addEventListener('bf-selection',update);
  update();
})();
