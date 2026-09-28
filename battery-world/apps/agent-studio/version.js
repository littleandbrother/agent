/* Open tabs keep their original JS until reloaded. Offer a real reload, never submit. */
(()=>{
  const build=document.querySelector('meta[name="bf-ui-build"]')?.content;
  if(!build)return;
  let busy=false;
  async function check(){
    if(busy||document.hidden)return;busy=true;
    try{
      const response=await fetch('/api/ui-version',{cache:'no-store'});
      if(!response.ok)return;
      const value=await response.json();
      if(value.build===build||document.getElementById('ui-update'))return;
      const button=document.createElement('button');button.id='ui-update';button.textContent='更新界面';
      button.title='加载新版界面，保留当前会话和输入草稿';button.onclick=()=>location.reload();
      document.querySelector('.topbar')?.append(button);
    }catch{/* A disconnected service is handled by the existing connection indicator. */}
    finally{busy=false}
  }
  window.addEventListener('focus',check);document.addEventListener('visibilitychange',check);
  setInterval(check,30000);check();
})();
