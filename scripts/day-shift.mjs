#!/usr/bin/env node
// scripts/day-shift.mjs: S-5.7, the home's layout shift read in a browser.
//
//   node scripts/day-shift.mjs PAGE.html ASSETS_DIR
//
// Serves PAGE.html as /index.html and ASSETS_DIR as /assets/ from 127.0.0.1, loads the page at 390
// and at 1440 wide, waits for it to settle, and prints one JSON object per width: the cumulative
// layout shift (the sum of the page's layout-shift entries with no recent input, the figure
// Lighthouse reports) and the day sections that were visible at the first frame the page painted.
// With DAY_FONT_DELAY=ms every font response (or those matching DAY_FONT_MATCH) is held that long (a slow runner); with DAY_HASH set the page is loaded at that hash; with DAY_NOJS set it is loaded without script and
// the days showing are printed. Playwright is found through PLAYWRIGHT_NODE_MODULES, as in scripts/page-measure.mjs.
import { createRequire } from "node:module";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname, normalize } from "node:path";
import { createServer } from "node:http";

const [page, assets] = process.argv.slice(2);
const nm = process.env.PLAYWRIGHT_NODE_MODULES || "/opt/node-tools/node_modules";
let chromium;
try {
  ({ chromium } = createRequire(nm + "/")("playwright"));
} catch (e) {
  console.log(JSON.stringify({ fail: "no browser: playwright not found (set PLAYWRIGHT_NODE_MODULES)" }));
  process.exit(1);
}
const TYPES = { ".css": "text/css", ".js": "application/javascript", ".svg": "image/svg+xml",
  ".woff2": "font/woff2", ".ttf": "font/ttf", ".png": "image/png", ".json": "application/json" };
const server = createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (p === "/" || p === "/index.html") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return res.end(readFileSync(page));
  }
  const f = p.startsWith("/assets/") ? normalize(join(assets, p.slice(8))) : "";
  if (f && f.startsWith(normalize(assets)) && existsSync(f) && statSync(f).isFile()) {
    const send = () => { res.writeHead(200, { "content-type": TYPES[extname(f)] || "application/octet-stream" });
      res.end(readFileSync(f)); };
    // DAY_FONT_DELAY=ms holds every font response that long, a slow runner's font arrival
    if (process.env.DAY_FONT_DELAY && /\.(woff2|ttf)$/.test(f) && new RegExp(process.env.DAY_FONT_MATCH || ".").test(f)) return setTimeout(send, +process.env.DAY_FONT_DELAY);
    return send();
  }
  res.writeHead(404);
  res.end();
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const base = "http://127.0.0.1:" + server.address().port + "/index.html";
const browser = await chromium.launch();
let code = 0;
try {
  for (const w of [390, 1440]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w === 390 ? 844 : 900 },
      javaScriptEnabled: !process.env.DAY_NOJS });
    const pg = await ctx.newPage();
    if (process.env.DAY_NOJS) {
      await pg.goto(base, { waitUntil: "load" });
      const days = await pg.$$eval(".wb-day", ss => ss.filter(s => getComputedStyle(s).display !== "none").map(s => s.dataset.day));
      console.log(JSON.stringify({ width: w, noScriptDays: days }));
      await ctx.close();
      continue;
    }
    await pg.addInitScript(() => {
      window.__cls = 0; window.__shifts = []; window.__first = null;
      new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) {
        window.__cls += e.value;
        window.__shifts.push({ v: e.value, at: (e.sources || []).map(s => (s.node ? (s.node.tagName + "." + (s.node.id || (s.node.className && s.node.className.baseVal === undefined ? s.node.className : "") || "")) : "gone") + " " + JSON.stringify(s.previousRect) + ">" + JSON.stringify(s.currentRect)) });
      } }).observe({ type: "layout-shift", buffered: true });
      new PerformanceObserver((l, o) => {
        if (window.__first) return;
        window.__first = [...document.querySelectorAll(".wb-day")].filter(s => getComputedStyle(s).display !== "none").map(s => s.dataset.day);
      }).observe({ type: "paint", buffered: true });
    });
    await pg.goto(base + (process.env.DAY_HASH || ""), { waitUntil: "load" });
    await pg.waitForTimeout(2500);
    const r = await pg.evaluate(() => ({ cls: window.__cls, shifts: window.__shifts, first: window.__first,
      after: [...document.querySelectorAll(".wb-day")].filter(s => getComputedStyle(s).display !== "none").map(s => s.dataset.day) }));
    console.log(JSON.stringify({ width: w, cls: Math.round(r.cls * 10000) / 10000, shifts: r.shifts, firstPaintDays: r.first, settledDays: r.after }));
    await ctx.close();
  }
} catch (e) {
  console.log(JSON.stringify({ fail: String(e) }));
  code = 1;
} finally {
  await browser.close();
  server.close();
}
process.exit(code);
