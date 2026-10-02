// Dependency-free syntax transformation, not a TypeScript project typecheck.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripTypeScriptTypes } from 'node:module';
import { createHash } from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.join(root,'validation-build');
fs.mkdirSync(output,{recursive:true});
const entries=[
 ['bf-harness','method.ts'],['bf-harness','solver.ts'],
 ['bf-agent','method-activation.ts'],['bf-agent','main.ts'],
];
const rows=[];
for(const [pkg,name] of entries){
 const source=path.join(root,'changed/pi-overlay/packages',pkg,'src',name);
 const text=fs.readFileSync(source,'utf8');
 const js=stripTypeScriptTypes(text,{mode:'strip'});
 const target=path.join(output,pkg,name.replace(/\.ts$/,'.js'));
 fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,js);
 fs.writeFileSync(path.join(path.dirname(target),'package.json'),'{"type":"module"}\n');
 const sha=x=>createHash('sha256').update(x).digest('hex');
 rows.push({source:path.relative(root,source),source_sha256:sha(text),output:path.relative(root,target),output_sha256:sha(js)});
}
fs.writeFileSync(path.join(root,'reports/syntax-transform.json'),JSON.stringify({status:'syntax_transformation_passed',project_typecheck:false,full_pi_build:false,entries:rows},null,2)+'\n');
console.log(JSON.stringify({files:rows.length,project_typecheck:false,full_pi_build:false}));
