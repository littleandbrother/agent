import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
const root=path.dirname(fileURLToPath(import.meta.url));
const dependencies=process.env.BF_STUDIO_DEPENDENCIES||path.join(root,'node_modules');
const require=createRequire(path.join(dependencies,'_scene_build.cjs'));
for(const [name,version] of Object.entries({three:'0.185.1',esbuild:'0.28.2'})){
  const actual=JSON.parse(await readFile(path.join(dependencies,name,'package.json'),'utf8')).version;
  if(actual!==version)throw new Error(`${name}: expected ${version}, received ${actual}`);
}
await require('esbuild').build({entryPoints:[path.join(root,'src/studio.js')],outfile:path.join(root,'studio.js'),bundle:true,format:'esm',platform:'browser',target:'es2022',minify:true,legalComments:'eof',nodePaths:[dependencies]});
const manifest=JSON.parse(await readFile(path.join(root,'source-manifest.json'),'utf8'));
manifest.mode='live-default-with-labeled-demo-preview';
const hash=async file=>createHash('sha256').update(await readFile(path.join(root,file))).digest('hex');
for(const item of manifest.files){
  const digest=await hash(item.path);
  if(digest!==item.sha256){item.upstream_sha256??=item.sha256;item.sha256=digest;}
}
manifest.host_adaptation={
  description:'Full-pane host scene; compact Inter 4.1 vector-outline station titles, pixel ratio up to 2, no duplicate specialist tags or floating Dot label/bubble.',
  build:'BF_STUDIO_DEPENDENCIES=/path/to/node_modules node build.mjs',
  dependencies:{three:'0.185.1',esbuild:'0.28.2'},
  sources:await Promise.all(['src/studio.js','src/details.js','src/screens.js','src/fonts/inter-titles.json','../../../scripts/generate_runtime_title_font.py','build.mjs','package.json'].map(async file=>({path:file,sha256:await hash(file)})))
};
await writeFile(path.join(root,'source-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log('Built host scene; source and bundle hashes recorded.');
