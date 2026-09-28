import { build } from 'esbuild';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import {gzipSync} from 'node:zlib';
const root = path.dirname(fileURLToPath(import.meta.url));
const result = await build({entryPoints:[path.join(root,'src/main.tsx')],bundle:true,write:false,
  minify:true,format:'iife',target:'es2022',jsx:'automatic',legalComments:'inline',
  define:{'process.env.NODE_ENV':'"production"'},outfile:'app.js'});
const script = result.outputFiles.find(f=>f.path.endsWith('.js')).text.replaceAll('</script','<\\/script');
const css = result.outputFiles.find(f=>f.path.endsWith('.css'))?.text ?? '';
const payload=await readFile(path.join(root,'generated/payload.json'),'utf8');
const encoded=gzipSync(Buffer.from(payload),{level:9}).toString('base64');
const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#111817"><title>Battery World Studio · From experiments to expertise</title><style>${css}</style></head><body><div id="root" style="min-height:100vh">Opening sealed laboratory traces…</div><noscript>JavaScript is required to replay the interactive laboratory.</noscript><script id="studio-data" type="application/gzip">${encoded}</script><script>(async()=>{const el=document.getElementById('studio-data');const bytes=Uint8Array.from(atob(el.textContent.trim()),c=>c.charCodeAt(0));const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));el.textContent=await new Response(stream).text();el.type='application/json';${script}})().catch(e=>{document.getElementById('root').textContent='This browser could not open the compressed offline traces. Please use a current browser. '+e.message;});</script></body></html>`;
await mkdir(path.join(root,'dist'),{recursive:true});
await writeFile(path.join(root,'dist/index.html'),html);
console.log(`Studio built: ${(Buffer.byteLength(html)/1024/1024).toFixed(2)} MB, self-contained, no CDN.`);
