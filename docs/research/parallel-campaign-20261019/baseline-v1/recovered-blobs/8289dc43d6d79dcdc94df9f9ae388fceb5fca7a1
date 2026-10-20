// Render the frozen native SVG itself. No app UI, network, or engineering mutation.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

const deps = process.env.BF_REPORT_NODE_MODULES ||
  '/Users/depengsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const { chromium } = await import(pathToFileURL(path.join(deps, 'playwright/index.mjs')));
const src = path.resolve(process.argv[2]);
const out = path.resolve(process.argv[3]);
await fs.mkdir(out, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.BF_REPORT_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true, args: ['--disable-background-networking', '--no-first-run', '--disable-gpu'],
});
const context = await browser.newContext({ deviceScaleFactor: 2 });
await context.route(/^https?:/, route => route.abort());
const items = [];
try {
  for (const name of ['schematic.svg', 'pcb-top.svg', 'pcb-bottom.svg', 'pcb-combined.svg']) {
    const file = path.join(src, name);
    const page = await context.newPage();
    // HTML embedding avoids the standalone SVG viewer's tiled screenshot path.
    await page.setContent('<body style="margin:0;background:white">' +
      await fs.readFile(file, 'utf8') + '</body>', { waitUntil: 'load' });
    const size = await page.locator('svg').evaluate(svg => {
      const box = svg.viewBox.baseVal;
      const scale = 2400 / Math.max(box.width, box.height);
      const width = Math.ceil(box.width * scale), height = Math.ceil(box.height * scale);
      svg.style.width = width + 'px';
      svg.style.height = height + 'px';
      return { width, height };
    });
    await page.setViewportSize({ width: size.width, height: size.height });
    const target = path.join(out, name.replace('.svg', '.png'));
    await page.locator('svg').screenshot({ path: target, omitBackground: false, animations: 'disabled' });
    const hash = value => crypto.createHash('sha256').update(value).digest('hex');
    items.push({ source: name, source_sha256: hash(await fs.readFile(file)),
      output: path.basename(target), output_sha256: hash(await fs.readFile(target)),
      width: size.width * 2, height: size.height * 2 });
    await page.close();
  }
  await fs.writeFile(path.join(out, 'native-previews.json'), JSON.stringify({
    engine: 'Chromium native SVG renderer', version: browser.version(), scale: 2, items,
  }, null, 2) + '\n');
  console.log(JSON.stringify({ rendered: items.length, engine: browser.version() }));
} finally {
  await browser.close();
}
