/* Public conversation projection. Raw input/output stays in developer Trace. */
(function(root){
  const time=e=>typeof e.data.time==='number'?e.data.time:typeof e.time==='number'?e.time:null;
  const errorCode=value=>{const text=String(value||'');return text.match(/^(?:\d{3}\s+)?["']?([A-Z][A-Z0-9_]+)["']?$/)?.[1]||text};
  function project(events,{legacy=false,live=false}={}){
    const records=[],partials=new Map(),calls=[],withdrawn=events.filter(e=>e.data.type==='message_withdrawn').map(e=>e.data);
    const failures=[];
    function failure(key,raw,time){const code=errorCode(raw);if(records.at(-1)?.kind==='error'&&records.at(-1).code===code)return;const rec={kind:'error',key,code,text:raw,time,historical:false};records.push(rec);failures.push(rec)}
    for(const event of events){
      if(withdrawn.some(w=>event.seq>=w.from_seq&&event.seq<=w.to_seq))continue;
      const d=event.data,key='e'+event.seq,t=time(event);
      if(d.type==='user_message')records.push({kind:'user',key,text:d.text,id:d.id,time:t});
      else if(d.type==='input_accepted'&&d.delivery!=='steer')records.push({kind:'start',key,time:t});
      else if(d.type==='assistant_start'){const rec={kind:'assistant',key,id:d.id,text:'',pending:true,complete:false,time:t};records.push(rec);partials.set(String(d.id),rec)}
      else if(d.type==='text_delta'){const rec=partials.get(String(d.id));if(rec)rec.text+=d.delta}
      else if(d.type==='tool_execution_start'){
        const rec={kind:'activity',key,name:d.toolName,args:d.args||{},id:d.toolCallId,state:'running',time:t};calls.push(rec);records.push(rec);
      }else if(d.type==='message'){
        const m=d.message||{};
        if(m.role==='assistant'){
          const text=Array.isArray(m.content)?m.content.filter(c=>c.type==='text').map(c=>c.text).join('\n'):'';
          let rec=partials.get(String(d.id));if(!rec){rec={kind:'assistant',key,text:'',time:t};records.push(rec)}
          Object.assign(rec,{text:text||rec.text,pending:false,complete:true,usage:m.usage,truncated:m.stopReason==='length',failed:m.stopReason==='error',hasTools:m.content?.some?.(c=>c.type==='toolCall')||m.stopReason==='toolUse',endTime:t});
          // Queued input or RUNNING alone does not establish recovery.
          if(!rec.failed&&!rec.truncated&&['stop','toolUse'].includes(m.stopReason)&&(rec.text||rec.hasTools))for(const f of failures)f.historical=true;
          if(rec.failed)failure(key+'err',m.errorMessage||'模型请求中断',t);
          if(rec.truncated)failure(key+'length','MODEL_OUTPUT_TRUNCATED',t);
        }else if(m.role==='user'&&legacy)records.push({kind:'user',key,time:t,text:typeof m.content==='string'?m.content:m.content?.filter(c=>c.type==='text').map(c=>c.text).join('\n')});
      }else if(['turn_error','command_error'].includes(d.type)){failure(key,d.error,t)}
      else if(d.type==='conversation_status'&&d.error&&['BLOCKED','FAILED','INTERRUPTED','PAUSED'].includes(d.status)){failure(key,d.error,t)}
      else if(d.type==='runtime_restored')records.push({kind:'status',key,text:d.text});
      else if(d.type==='product_record')records.push({kind:'product',key,revision:d.revision});
      else if(d.type==='message_withdrawn')records.push({kind:'status',key,text:'已撤回并返回输入框 · 已完成的实验和文件变更保留'});
      else if(d.type==='turn_stopped')records.push({kind:'status',key,text:'当前执行已停止'});
      const result=d.type==='tool_execution_end'?d:d.type==='message'&&d.message?.role==='toolResult'?d.message:null;
      if(result){
        let matches=calls.filter(c=>result.toolCallId&&c.id===result.toolCallId&&c.name===result.toolName);
        if(!matches.length)matches=calls.filter(c=>!c.id&&c.name===result.toolName&&c.state==='running');
        if(matches.length===1){matches[0].state=result.isError?'error':'done';if(result.toolCallId)matches[0].id=result.toolCallId;matches[0].endTime=t}
      }
      if(['turn_complete','turn_stopped','turn_error','chat_idle','session_complete'].includes(d.type)){
        for(const rec of partials.values())rec.pending=false;
        for(const call of calls)if(call.state==='running')call.state='unknown';
        records.push({kind:'end',key:key+'end',time:t});
      }
    }
    if(!live){for(const r of records){if(r.pending)r.pending=false;if(r.kind==='activity'&&r.state==='running')r.state='unknown'}}
    const groups=[];let progress=null,start=null,extras=[],turnProgress=null;
    function flush(end=null){if(progress){progress.end=end;groups.push(progress);turnProgress=progress;progress=null}}
    function extra(){groups.push(...extras);extras=[]}
    function add(r){if(!progress)progress={kind:'progress',key:'progress-'+r.key,items:[],start,active:false};progress.items.push(r)}
    for(const r of records){
      if(r.kind==='start'){flush();extra();start=r.time;turnProgress=null;continue}
      if(r.kind==='end'){flush(r.time);extra();if(turnProgress&&turnProgress.end==null)turnProgress.end=r.time;start=null;turnProgress=null;continue}
      if(r.kind==='product'){extras.push(r);continue}
      if(r.kind==='activity'||r.kind==='assistant'&&(r.pending||r.hasTools||!r.complete||r.failed)){add(r);continue}
      if(r.kind==='assistant'&&!r.text)continue;
      flush(r.endTime??r.time);groups.push(r);extra();if(r.kind==='user')start=null;
    }
    if(progress){progress.active=live;flush()}extra();
    return {records,groups};
  }
  function label(r){
    const file=String(r.args?.path||r.args?.file_path||'').split('/').filter(Boolean).at(-1);
    const names={read:'读取文件',write:'写入文件',edit:'编辑文件',bash:'运行命令',bf_experiment:'提交计算实验',bf_job:'查看实验进度',bf_inspect_run:'检查实验结果',bf_submit:'核对提交快照',bf_memory:r.args?.action==='write'?'保存共享笔记':'读取共享笔记',bf_product:({inspect:'查看方案',propose:'更新方案',bind:'选择计算环境',ask:'整理待确认事项'})[r.args?.action]||'整理方案'};
    const action=(names[r.name]||'执行步骤')+(file&&['read','write','edit'].includes(r.name)?' '+file:'');
    return r.state==='done'?'已'+action:r.state==='error'?action+' · 失败':r.state==='unknown'?action+' · 未收到返回':'正在'+action;
  }
  const paths={file:'<path d="M5 2h5l3 3v9H5zM10 2v4h3M2 5v9"/>',terminal:'<rect x="2" y="3" width="12" height="10" rx="2"/><path d="m5 6 2 2-2 2m4 0h2"/>',step:'<circle cx="8" cy="8" r="5.5"/><path d="m5.5 8 1.7 1.7 3.5-3.5"/>'};
  const icon=r=>`<svg viewBox="0 0 16 16" fill="none" aria-hidden="true">${paths[['read','write','edit'].includes(r.name)?'file':r.name==='bash'?'terminal':'step']}</svg>`;
  function render(group,{esc,markdown,states}){
    const activities=group.items.filter(r=>r.kind==='activity'),failed=activities.some(r=>r.state==='error');
    const duration=typeof group.start==='number'&&typeof group.end==='number'&&group.end>=group.start?` · 用时 ${Math.max(1,Math.round(group.end-group.start))} 秒`:'';
    const title=group.active?'正在执行':failed?'执行过程 · 含失败记录':'执行过程';
    const opened=states.has(group.key)?states.get(group.key):group.active;
    let html='',batch=[];
    const flush=()=>{
      if(!batch.length)return;
      if(batch.length===1){const r=batch[0];html+=`<div class="activity-group"><button class="activity-row ${r.state}" data-open-trace title="在开发者 Trace 查看详情">${icon(r)}<span>${esc(label(r))}</span><span aria-hidden="true">↗</span></button></div>`;batch=[];return}
      const key='steps-'+batch[0].key,working=batch.some(r=>r.state==='running');
      const open=states.has(key)?states.get(key):false;
      const summary=batch.length===1?label(batch[0]):`${working?'正在执行':'已记录'} ${batch.length} 个步骤${batch.some(r=>r.state==='error')?' · 含失败记录':''}`;
      html+=`<details class="activity-group" data-key="${esc(key)}" ${open?'open':''}><summary>${icon(batch[0])}<span>${esc(summary)}</span><span class="flow-chevron"></span></summary><div class="activity-list">${batch.map(r=>`<button class="activity-row ${r.state}" data-open-trace title="在开发者 Trace 查看详情">${icon(r)}<span>${esc(label(r))}</span><span aria-hidden="true">↗</span></button>`).join('')}</div></details>`;batch=[];
    };
    for(const r of group.items){if(r.kind==='activity'){batch.push(r);continue}if(!r.text)continue;flush();html+=`<div class="progress-text">${markdown(r.text)}${r.pending?'<span class="stream-caret">▍</span>':''}</div>`}flush();
    if(!html)return '';
    return `<details class="response-progress" data-key="${esc(group.key)}" ${opened?'open':''}><summary><svg class="progress-icon ${group.active?'active':''}" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 2c4 0 7 4 5 8s-7 6-10 3S3 4 7 3s10 3 10 7-5 8-9 6-6-7-3-10"/></svg><span>${esc(title+duration)}</span><span class="flow-chevron"></span></summary><div class="progress-body">${html}<button class="trace-link" data-open-trace>查看完整 Trace <span aria-hidden="true">↗</span></button></div></details>`;
  }
  function renderError(record,{esc,errors,states}){
    const text=errors[errorCode(record.code||record.text)]||record.text;
    if(record.historical)return `<details class="historical-error" data-key="${esc(record.key)}" ${states.get(record.key)?'open':''}><summary>先前执行中断 · 后续已收到模型回复<span class="flow-chevron"></span></summary><p>${esc(text)}</p><button class="trace-link" data-open-trace>查看当时的 Trace ↗</button></details>`;
    return `<article class="message error"><div class="message-bubble"><div class="message-label">执行中断</div><div class="message-text">${esc(text)}</div></div></article>`;
  }
  const api={project,label,render,renderError,errorCode};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ConversationFlow=api;
})(globalThis);
