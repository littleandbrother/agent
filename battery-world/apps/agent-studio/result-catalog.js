/* One owner/revision cache for Studio surfaces. A change token is not acceptance. */
(function(root){
  function create(api,emit=()=>{},now=Date.now){
    const entries=new Map();
    const entry=(owner,revision='')=>{const key=JSON.stringify([owner,revision||'']);if(!entries.has(key))entries.set(key,{owner,revision:revision||'',epoch:0,at:0});return entries.get(key)};
    async function get(owner,revision='',force=false){
      const e=entry(owner,revision);
      if(e.flight)return e.flight;
      if(!force&&e.value&&now()-e.at<30000)return e.value;
      const epoch=e.epoch;
      e.flight=(async()=>{
        const token=await api('/api/results/version?'+new URLSearchParams({session:owner}));
        const value=await api('/api/results?'+new URLSearchParams({session:owner,revision:revision||''}));
        const changed=e.value?.snapshot_sha256!==value.snapshot_sha256;
        e.value=value;e.version=token.version;e.at=now();
        if(changed)emit('bf-results-updated',{owner,revision:e.revision,catalog:value,checkedAt:e.at});
        emit('bf-results-status',{owner,checkedAt:e.at,connected:true});
        return value;
      })().catch(error=>{emit('bf-results-status',{owner,connected:false,error:error.message});throw error}).finally(()=>{
        e.flight=null;
        if(epoch!==e.epoch)void get(owner,e.revision,true).catch(()=>{});
      });
      return e.flight;
    }
    function invalidate(owner){
      for(const e of entries.values())if(e.owner===owner){e.epoch++;e.at=0}
    }
    async function poll(owner){
      if(!owner)return;
      const list=[...entries.values()].filter(e=>e.owner===owner);
      if(!list.length)return get(owner);
      const token=await api('/api/results/version?'+new URLSearchParams({session:owner}));
      await Promise.all(list.map(e=>!e.flight&&(token.version!==e.version||now()-e.at>=30000)?get(owner,e.revision,true):e.flight));
      emit('bf-results-status',{owner,checkedAt:now(),connected:true});
    }
    return {get,poll,invalidate,peek:(owner,revision='')=>entry(owner,revision).value};
  }
  if(typeof module!=='undefined'){module.exports={create};return}
  const emit=(name,detail)=>root.dispatchEvent(new CustomEvent(name,{detail}));
  const cache=create((url)=>root.BF.api(url,undefined,{signal:AbortSignal.timeout(45000)}),emit);
  root.ResultCatalog=cache;
  let timer=null,polling=false;
  async function poll(){
    if(document.hidden||polling)return;const owner=root.BF.getSelection();if(!owner)return;
    polling=true;try{await cache.poll(owner)}catch(error){emit('bf-results-status',{owner,connected:false,error:error.message})}finally{polling=false}
  }
  root.addEventListener('bf-runtime-events',event=>{
    const {owner,events}=event.detail;
    if(!events.some(row=>/tool_execution_end|engineering|eda_cli|assembly|product_record|conversation_status|artifact|job|design_|candidate_|task_submitted|preview_/.test(row.data?.type||row.type||'')))return;
    cache.invalidate(owner);clearTimeout(timer);
    timer=setTimeout(()=>{if(owner===root.BF.getSelection())void cache.get(owner,'',true).catch(()=>{})},200);
  });
  root.addEventListener('bf-selection',()=>void poll());
  document.querySelector('#refresh')?.addEventListener('click',()=>{const owner=root.BF.getSelection();if(owner){cache.invalidate(owner);void cache.get(owner,'',true).catch(()=>{})}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)void poll()});
  setInterval(poll,2000);
})(typeof window!=='undefined'?window:this);
