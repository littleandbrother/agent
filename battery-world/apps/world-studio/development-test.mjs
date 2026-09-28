import {chromium} from '@playwright/test';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'../..'),out=path.join(root,'docs/b2-development');
await mkdir(out,{recursive:true});
const dossier=JSON.parse(await readFile(path.join(out,'report.json'),'utf8'));
const profiled=JSON.parse(await readFile(path.join(out,'profiled-report.json'),'utf8'));
const measured=JSON.parse(await readFile(path.join(out,'measured-import.json'),'utf8')).report;
const executionControls=JSON.parse(await readFile(path.join(out,'execution-controls.json'),'utf8'));
const workflowUse=JSON.parse(await readFile(path.join(out,'workflow-use-controls.json'),'utf8'));
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1512,height:1120}}),errors=[],network=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route(/^https?:/,async r=>{network.push(r.request().url());await r.abort()});
try{
 const html=path.join(root,'apps/world-studio/dist/index.html');
 await page.goto(pathToFileURL(html).href+'?view=campaign#b2-development');
 await page.getByRole('heading',{name:'What the program erased.'}).waitFor();
 const counterRows=page.locator('.development-lab > .development-table-wrap tbody tr');
 assert.equal(await counterRows.count(),8);
 await page.getByLabel('只看反例').check();
 assert.equal(await counterRows.count(),dossier.g2.residuals.false_reject_region.filter(r=>r.task_id==='qualification-6').length);
 await page.getByLabel('Counterexample task').selectOption('qualification-7');
 assert.equal(await counterRows.count(),dossier.g2.residuals.false_reject_region.filter(r=>r.task_id==='qualification-7').length);
 await page.getByLabel('只看反例').uncheck();
 assert.equal(await counterRows.count(),8);
 for(const run of dossier.episode.runs){
  await page.getByRole('button',{name:new RegExp(run.id.toUpperCase())}).click();
  await page.getByLabel('Counterexample replay time').fill('0.383');
  assert.equal(await page.locator('.development-sample:not(.semantic-sample)').getAttribute('data-run-hash'),run.run_hash);
  const point=run.trace.find(r=>r.time_s===.383);
  assert((await page.locator('.development-sample:not(.semantic-sample)').textContent()).includes(point.input_voltage_v.toFixed(3)+' V'));
 }
 await page.getByRole('button',{name:/CAPACITY-ONLY/}).click();
 await page.getByRole('button',{name:'Jump to baseline brownout'}).click();
 assert.equal(await page.getByLabel('Counterexample replay time').inputValue(),'0.383');
 await page.locator('.development-lab > .development-trace').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(out,'controlled-transient.png')});
 await page.locator('.development-title').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(out,'counterexample-workbench.png')});
 assert.equal(await page.locator('.development-compiler details').count(),3);
 await page.locator('.development-compiler summary').first().click();
 assert((await page.locator('.development-compiler').textContent()).includes('missing_program'));
 assert.equal(await page.locator('.execution-recovery').getAttribute('data-controls-hash'),executionControls.content_hash);
 await page.locator('.execution-recovery summary').click();
 assert((await page.locator('.execution-recovery').textContent()).includes('test_real_process_exit_after_settlement'));
 await page.locator('.execution-recovery').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(out,'repair-recovery-controls.png')});
 await page.locator('.execution-recovery summary').click();
 assert.equal(await page.locator('.workflow-use').getAttribute('data-workflow-hash'),workflowUse.content_hash);
 for(const v of workflowUse.variants){
  const row=page.locator(`.workflow-use tr[data-policy="${v.name}"]`);
  assert.equal(await row.getAttribute('data-report-hash'),v.report.content_hash);
  assert.equal(await row.locator('td').nth(2).textContent(),String(v.report.metrics.candidate_policy_probes));
  assert((await row.textContent()).includes('NOT FORMALLY QUALIFIED'));
 }
 await page.locator('.workflow-use').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(out,'workflow-use-controls.png')});
 await page.getByLabel('Explicit development task').selectOption('public-long-tx');
 await page.getByLabel('Profiled candidate').selectOption('medium');
 await page.getByRole('button',{name:'Jump to selected failure'}).click();
 const run=profiled.runs.find(r=>r.task_id==='public-long-tx'&&r.candidate_id==='medium');
 assert.equal(await page.locator('.semantic-sample').getAttribute('data-run-hash'),run.run_hash);
 assert.equal(+await page.getByLabel('Profiled replay time').inputValue(),run.summary.first_brownout_s);
 assert((await page.locator('.semantic-sample').textContent()).includes('brownout'));
 await page.locator('#semantic-development').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(out,'semantic-negative-result.png')});
 await page.getByRole('button',{name:'Jump to measured peak'}).click();
 assert.equal(await page.locator('.measured-sample').getAttribute('data-manifest-hash'),measured.manifest_hash);
 assert((await page.locator('.measured-sample').textContent()).includes((measured.observations.current.peak_a*1000).toFixed(4)+' mA'));
 await page.locator('#measured-replay').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(out,'measured-replay.png')});
 await page.setViewportSize({width:390,height:844});
 await page.locator('.development-title').scrollIntoViewIfNeeded();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
 await page.screenshot({path:path.join(out,'mobile.png')});
 await page.locator('#semantic-development').scrollIntoViewIfNeeded();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
 await page.screenshot({path:path.join(out,'semantic-mobile.png')});
 assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
 await writeFile(path.join(out,'browser-validation.json'),JSON.stringify({status:'pass',dossier_hash:dossier.content_hash,
  portable_html_sha256:createHash('sha256').update(await readFile(html)).digest('hex'),errors,network,
  controls:['false-rejection filter','task selection','five factor interventions','source-bound sample','threshold jump','compiler errors','receipt-bound recovery and scientific gates','independent workflow use without learned-knowledge claim','explicit load profile','semantic-negative-result','measured peak and provenance','offline','mobile'],profiled_hash:profiled.content_hash,execution_controls_hash:executionControls.content_hash,workflow_use_hash:workflowUse.content_hash,measured_manifest_hash:measured.manifest_hash,captured_at:new Date().toISOString()},null,2));
 console.log('Counterexamples, single-factor traces, immutable identities, compiler errors and offline/mobile controls passed.');
}finally{await browser.close()}
