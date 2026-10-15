// Native SVG filters, text and wires are rendered together without network access.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import { pathToFileURL } from 'node:url';
const modules=process.env.BF_REPORT_NODE_MODULES || path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const {chromium}=await import(pathToFileURL(path.join(modules,'playwright/index.mjs')));
const [source,out]=process.argv.slice(2).map(x=>path.resolve(x));
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.BF_REPORT_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--no-first-run','--disable-gpu']});
const items=[];const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
try {
 const context=await browser.newContext({deviceScaleFactor:2});
 await context.route(/^https?:/,route=>route.abort());
 for(const name of (await fs.readdir(source)).filter(x=>x.endsWith('.svg')).sort()) {
  const content=await fs.readFile(path.join(source,name));const page=await context.newPage();
  await page.setContent('<body style="margin:0;background:white">'+content.toString('utf8')+'</body>');
  const size=await page.locator('svg').evaluate(svg=>{const b=svg.viewBox.baseVal;const scale=2400/Math.max(b.width,b.height);const width=Math.ceil(b.width*scale),height=Math.ceil(b.height*scale);svg.style.width=width+'px';svg.style.height=height+'px';return {width,height};});
  await page.setViewportSize(size);const target=name.replace(/\.svg$/,'.png');
  await page.locator('svg').screenshot({path:path.join(out,target),animations:'disabled'});
  items.push({source:name,source_sha256:hash(content),output:target,output_sha256:hash(await fs.readFile(path.join(out,target))),width:size.width*2,height:size.height*2});
  await page.close();
 }
 await fs.writeFile(path.join(out,'native-previews.json'),JSON.stringify({engine:'Chromium',version:browser.version(),items},null,2)+'\n');
} finally {await browser.close();}
