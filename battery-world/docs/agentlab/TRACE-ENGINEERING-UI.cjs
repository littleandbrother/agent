// Local browser acceptance, no message submission or paid model request.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require('/Users/depengsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const home='/Users/depengsu/Documents/bf-agent-workbench';
 const out=path.join(home,'verification/trace-engineering-browser');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{sessionStorage.setItem('bf-chat-selected','pi-chat-48879f0893e33a22');localStorage.setItem('bf-studio-mode','developer');localStorage.setItem('bf-dev-module','trace')});
 await page.goto(fs.readFileSync(path.join(home,'state/launch-url.txt'),'utf8').trim());
 await page.locator('.trace-stat-grid').waitFor();
 await page.screenshot({path:path.join(out,'overview.png'),fullPage:true});
 await page.locator('[data-trace-tab="timeline"]').click();await page.locator('#trace-kind').selectOption('tool');
 assert(await page.locator('.trace-event').count()>0);
 await page.locator('.trace-event').first().click();await page.locator('#trace-detail').waitFor();
 assert((await page.locator('#trace-detail pre').textContent()).includes('input'));
 await page.getByRole('button',{name:'关闭 Trace 详情',exact:true}).click();
 await page.locator('#trace-kind').selectOption('skill');
 await page.locator('#trace-kind').selectOption('mcp');
 assert.equal(await page.locator('.trace-event').count(),0);
 await page.locator('#trace-kind').selectOption('all');
 await page.screenshot({path:path.join(out,'timeline.png'),fullPage:true});
 await page.locator('[data-trace-tab="compare"]').click();await page.locator('#trace-run-compare').click();
 await page.locator('#trace-comparison table').waitFor();
 assert((await page.locator('#trace-comparison').textContent()).includes('探索性差异'));
 await page.locator('[data-trace-tab="raw"]').click();await page.locator('#trace-export-raw').waitFor();
 const downloadPromise=page.waitForEvent('download');await page.locator('#trace-export-raw').click();
 const download=await downloadPromise;const exportFile=path.join(out,'trace.json');await download.saveAs(exportFile);
 const exported=JSON.parse(fs.readFileSync(exportFile));
 assert(Buffer.from(exported.raw_base64,'base64').equals(fs.readFileSync(path.join(home,'sessions',exported.session_id,'trace.jsonl'))));
 await page.locator('button[data-module="tools"]').click();await page.locator('[data-cap-tab="skills"]').waitFor();
 await page.screenshot({path:path.join(out,'tools.png'),fullPage:true});
 await page.locator('[data-cap-tab="tools"]').click();assert(await page.locator('.trace-table tbody tr').count()>0);
 await page.locator('[data-cap-tab="skills"]').click();assert((await page.locator('[data-cap-pane="skills"]').textContent()).includes('读取不等于执行'));
 await page.locator('[data-cap-tab="mcp"]').click();assert((await page.locator('[data-cap-pane="mcp"]').textContent()).includes('尚无已记录'));
 if(process.argv.includes('--run-templates')){
  await page.locator('#new-chat').click();await page.locator('#developer-mode').click();
  await page.locator('button[data-module="tools"]').click();
  await page.locator('[data-cap-tab="engines"]').click();
  for(const engine of ['blender','comsol']){
   await page.locator(`[data-engine-run="${engine}"]`).click();
   await page.waitForFunction(()=>document.querySelector('#engineering-notice')?.textContent.startsWith('已提交'));
   const notice=await page.locator('#engineering-notice').textContent();const job=notice.match(/eng-[a-f0-9]+/)[0];
   const card=page.locator('.engineering-job').filter({hasText:job});
   await card.filter({hasText:'SUCCEEDED'}).waitFor({timeout:185000});
   assert(await card.locator('a[download="'+(engine==='blender'?'model.blend':'model.mph')+'"]').count());
  }
  await page.screenshot({path:path.join(out,'engineering-results.png'),fullPage:false});
 }
 await page.locator('#runtime-mode').click();
 assert.equal(await page.locator('#developer-view').isVisible(),false);
 assert.equal(await page.locator('.trace-event:visible').count(),0);
 assert.deepEqual(errors,[]);
 const result={passed:true,scope:'isolated headless browser against live production localhost',native_template_buttons_tested:process.argv.includes('--run-templates'),views:['overview','timeline','tool-detail','skill-filter','mcp-filter','comparison','raw-byte-export','tools','skills','mcp','runtime'],console_errors:errors,model_requests_dispatched:0};
 fs.writeFileSync(path.join(out,'receipt.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
