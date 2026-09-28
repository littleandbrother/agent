import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'../..'),out=path.join(root,'docs/deployments');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1512,height:1120}}),errors=[],network=[];
page.on('pageerror',e=>errors.push(e.message));await page.route(/^https?:/,async r=>{network.push(r.request().url());await r.abort()});
try{
 await page.goto(pathToFileURL(path.join(root,'apps/world-studio/dist/index.html')).href+'?view=deployments');
 await page.getByRole('heading',{name:'Intelligence, in context.'}).waitFor();
 const buttons=page.locator('.deployment-scenes button');assert.equal(await buttons.count(),6);
 for(let i=0;i<6;i++){
  await buttons.nth(i).click();await page.getByLabel('Deployment time',{exact:true}).fill('0.42');
  await page.waitForTimeout(500);await page.screenshot({path:path.join(out,`scene-${i+1}.png`),fullPage:false});
 }
 await page.getByRole('button',{name:'Top view',exact:true}).click();
 await page.getByLabel('Toggle deployment context').click();await page.getByLabel('Toggle deployment context').click();
 await buttons.nth(2).click();await page.getByLabel('Deployment variant').selectOption('small-storage');
 assert((await page.locator('.deployment-kpis').textContent()).includes('PHYSICAL FAIL'));
 await page.getByLabel('Deployment variant').selectOption('distant-receiver');
 assert((await page.locator('.deployment-requests').textContent()).includes('RECEIVER-LOST'));
 await page.getByLabel('Deployment variant').selectOption('reference');await buttons.nth(5).click();
 await page.getByLabel('Play deployment',{exact:true}).click();await page.waitForTimeout(160);await page.getByLabel('Pause deployment',{exact:true}).click();
 assert(Number(await page.getByLabel('Deployment time',{exact:true}).inputValue())>.42);
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
 assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
 await writeFile(path.join(out,'browser-validation.json'),JSON.stringify({status:'pass',scenes:6,offline_network_requests:network,errors,controls:['scene','variant','time','play','top-camera','context','mobile'],captured_at:new Date().toISOString()},null,2));
 console.log('Six deployment scenes, offline replay, failure controls and mobile layout passed.');
}finally{await browser.close()}
