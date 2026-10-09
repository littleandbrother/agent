(function(root){
  'use strict';
  const roles=['mechanical','circuit','pcb','power','firmware'];
  const labels={mechanical:'机械',circuit:'电路',pcb:'PCB',power:'供能',firmware:'固件'};
  const active=new Set(['RUNNING','QUEUED','STARTING']);
  function classify(name,args={}){
    if(name==='bf_eda')return ['pcb','board'].includes(args.argv?.[0])?'pcb':['sch','bom','lib'].includes(args.argv?.[0])?'circuit':null;
    if(['mcu-firmware','tinyml-nas'].includes(args.engine))return 'firmware';
    if(['blender','comsol','product-model'].includes(args.engine))return 'mechanical';
    if(args.engine==='engineering-project')return String(args.project?.manifest?.kind||args.parameters?.kind||'').includes('firmware')?'firmware':null;
    if(['event-transient','beam-event','closed-simulation','door-system','door-selfpower'].includes(args.engine))return 'power';
    return null;
  }
  function create(owner){
    let cursor=0,status='IDLE',error=null,connected=true;
    const jobs=new Map(),calls=new Map();
    function hydrate(value){
      if(value.owner!==owner||value.cursor<cursor)return false;
      cursor=value.cursor;status=value.conversation.status;error=value.conversation.error;
      jobs.clear();if(!active.has(status)||value.tool_calls)calls.clear();for(const job of value.jobs||[])jobs.set(job.id,job);
      if(active.has(status))for(const call of value.tool_calls||[])calls.set(call.toolCallId,{domain:classify(call.toolName,call.args||{}),label:call.toolName,
        review:call.toolName==='bf_product'&&call.args?.action==='delivery_inspect'});
      return true;
    }
    function ingest(row){
      if((row.owner&&row.owner!==owner)||!Number.isInteger(row.seq)||row.seq<=cursor)return false;
      cursor=row.seq;const d=row.data||{};
      if(d.type==='conversation_status'){status=d.status;error=d.error;if(!active.has(status))calls.clear()}
      if(d.type==='tool_execution_start')calls.set(d.toolCallId,{domain:classify(d.toolName,d.args),label:d.toolName,
        review:d.toolName==='bf_product'&&d.args?.action==='delivery_inspect'});
      if(d.type==='tool_execution_end')calls.delete(d.toolCallId);
      if(d.type==='eda_cli_operation'){
        const previous=jobs.get(d.job_id)||{};
        jobs.set(d.job_id,{...previous,id:d.job_id,domain:classify('bf_eda',d),status:d.status,
          created:previous.created??row.time,ended:row.time,label:(d.argv||[]).slice(0,2).join(' '),outcome:d.outcome});
      }
      if(d.type==='engineering_job_wait'||d.type==='eda_job_wait'){
        const previous=jobs.get(d.job_id);if(previous)jobs.set(d.job_id,{...previous,status:d.status});
      }
      return true;
    }
    function view(){
      const agents=roles.map(id=>{
        const relevant=[...jobs.values()].filter(j=>j.domain===id);
        const running=relevant.filter(j=>active.has(j.status));
        const call=[...calls.values()].find(c=>c.domain===id);
        const latest=relevant.sort((a,b)=>(b.created||0)-(a.created||0))[0];
        const checks=new Map();
        for(const job of relevant)if(job.outcome&&['passed','failed'].includes(job.outcome.check_status)&&!checks.has(job.outcome.check_scope))checks.set(job.outcome.check_scope,job.outcome);
        const failedCheck=[...checks.values()].find(x=>x.check_status==='failed');
        if(running.length)return {id,status:'work',message:`${running.length} 项作业执行中`};
        if(call&&active.has(status))return {id,status:'work',message:call.label};
        if(latest?.status==='UNKNOWN')return {id,status:'blocked',message:'作业结果待核对'};
        if(latest?.status==='FAILED')return {id,status:'error',message:latest.label+' 执行失败'};
        if(failedCheck)return {id,status:'blocked',message:'检查未通过 · '+failedCheck.counts.map(x=>x.name+' '+x.count).join(' / ')};
        // A native check only covers this check; it cannot complete a whole professional domain.
        return {id,status:'waiting',message:latest?(latest.outcome?.check_status==='passed'?'本次检查通过':latest.label+' 已执行'):'等待'+labels[id]+'任务'};
      });
      const text=!connected?'运行事件连接中断':status==='PAUSED'?'Pi 已暂停 · '+(error==='CHAT_TURN_WALL_BUDGET'?'本轮时长已用完':error||'等待继续'):active.has(status)?'Pi 正在执行当前任务':error?'Pi 执行受阻 · '+error:'Pi 等待下一步';
      return {owner,cursor,status,agents,text,meeting:active.has(status)&&[...calls.values()].some(c=>c.review)?{participants:roles,topic:'Pi 正在核对跨专业交付'}:null,assembled:false};
    }
    return {hydrate,ingest,view,setConnected:value=>{connected=value}};
  }
  const api={create,classify,roles,labels};root.BFRuntimeStudioModel=api;
  if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
