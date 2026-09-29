const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={window:{BF:{esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')},ProductDeliverables:{}}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../apps/agent-studio/product-deliverables-view.js'),'utf8'),context);
const render=context.window.ProductDeliveryView.renderMarkdown;
test('engineering report tables, dimensions and emphasis are readable',()=>{
 const html=render('# Product\n| Part | mm |\n|---|---|\n| Beam | **40** x 24 |\n\n- Source STEP');
 assert.match(html,/<table>/);assert.match(html,/<th>mm<\/th>/);assert.match(html,/<strong>40<\/strong>/);assert.match(html,/<li>Source STEP<\/li>/);
});
test('untrusted report cannot insert HTML or execute a URL',()=>{
 const html=render('# <img src=x onerror=alert(1)>\n<script>alert(1)</script>\n[run](javascript:alert(1))\n![remote](https://example.invalid/secret)');
 assert.doesNotMatch(html,/<img|<script|<a|<iframe/);assert.match(html,/&lt;script&gt;/);
});
test('code stays literal even when it contains table or bold syntax',()=>{
 const html=render('```c\nif (a < b) { // **not bold**\n|x|y|\n```');
 assert.match(html,/&lt; b/);assert.match(html,/\*\*not bold\*\*/);assert.doesNotMatch(html,/<table>|<strong>/);
});
