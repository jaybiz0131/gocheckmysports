#!/usr/bin/env node
// scripts/oswald-fallback.mjs: S-5.7 round 5, the Oswald stand-in paints only before Oswald lands.
//
//   node scripts/oswald-fallback.mjs ASSETS_DIR
//
// Serves a probe page (site.css from ASSETS_DIR) from 127.0.0.1, waits for document.fonts.ready,
// and prints one JSON object per probe: the width of a lower-case string on an Oswald surface
// (var(--sbc-display), the stack with 'Oswald Fallback') against the same string in the stack
// without it. Oswald's subset holds no lower case, so after load those glyphs must fall exactly
// where they fell before the stand-in existed; a different width means they were drawn in the
// scaled face. A capitals probe confirms Oswald itself is the face that draws the capitals.
// Playwright is found through PLAYWRIGHT_NODE_MODULES, as in scripts/day-shift.mjs.
import { createRequire } from "node:module";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname, normalize } from "node:path";
import { createServer } from "node:http";

const [assets] = process.argv.slice(2);
const nm = process.env.PLAYWRIGHT_NODE_MODULES || "/opt/node-tools/node_modules";
let chromium;
try {
  ({ chromium } = createRequire(nm + "/")("playwright"));
} catch (e) {
  console.log(JSON.stringify({ fail: "no browser: playwright not found (set PLAYWRIGHT_NODE_MODULES)" }));
  process.exit(1);
}
const TYPES = { ".css": "text/css", ".woff2": "font/woff2", ".ttf": "font/ttf", ".svg": "image/svg+xml" };
const WITH = "var(--sbc-display)";
const WITHOUT = "'Oswald',Impact,'Arial Narrow',sans-serif";
const TEXTS = ["Time TBA", "ime", "abcdefghijklmnopqrstuvwxyz", "Doors at noon"];
const html = `<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/assets/site.css">
<body style="margin:0;font-weight:600;font-size:40px">
${TEXTS.map((t, i) => `<div><span id="w${i}" style="font-family:${WITH}">${t}</span></div>
<div><span id="o${i}" style="font-family:${WITHOUT}">${t}</span></div>`).join("\n")}
<div><span id="cw" style="font-family:${WITH}">TIME TBA 7:30 PM</span></div>
<div><span id="co" style="font-family:'Oswald'">TIME TBA 7:30 PM</span></div>
<div><span id="cf" style="font-family:'Oswald Fallback'">TIME TBA 7:30 PM</span></div>`;
const server = createServer((req, res) => {
  const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (p === "/" || p === "/index.html") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return res.end(html);
  }
  const f = p.startsWith("/assets/") ? normalize(join(assets, p.slice(8))) : "";
  if (f && f.startsWith(normalize(assets)) && existsSync(f) && statSync(f).isFile()) {
    res.writeHead(200, { "content-type": TYPES[extname(f)] || "application/octet-stream" });
    return res.end(readFileSync(f));
  }
  res.writeHead(404);
  res.end();
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const browser = await chromium.launch();
let code = 0;
try {
  const pg = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await pg.goto("http://127.0.0.1:" + server.address().port + "/index.html", { waitUntil: "load" });
  await pg.evaluate(() => Promise.all([document.fonts.load("600 40px Oswald", "TIME"), document.fonts.ready]));
  const r = await pg.evaluate(texts => {
    const w = id => document.getElementById(id).getBoundingClientRect().width;
    return { texts: texts.map((t, i) => ({ text: t, withFallback: w("w" + i), without: w("o" + i) })),
      oswaldLoaded: document.fonts.check("600 40px Oswald", "TIME"),
      caps: { display: w("cw"), oswald: w("co"), fallbackFace: w("cf") } };
  }, TEXTS);
  console.log(JSON.stringify(r));
} catch (e) {
  console.log(JSON.stringify({ fail: String(e) }));
  code = 1;
}
await browser.close();
server.close();
process.exit(code);
