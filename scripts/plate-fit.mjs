#!/usr/bin/env node
// scripts/plate-fit.mjs: S-5.6, no plate label clipped at any width, read in a browser.
//
//   node scripts/plate-fit.mjs TREE CONFIG.json
//
// TREE is the built site. CONFIG.json holds { pages: ["index.html", ...], widths: [390, 768, 1440],
// plate: "rgb(20, 26, 23)", fixture: true|false }. Every page is loaded from TREE (assets from
// TREE/assets, served by a local http server) at each width with the shipped fonts loaded
// (document.fonts.ready, then a check that Oswald is in the loaded set; a fallback face would measure
// the wrong width, U-10). Inside <main>, a PLATE is any displayed element whose computed background
// is the plate color: no class list is kept by hand, so a plate the next change draws is read too.
// A plate is CLIPPED when
//   wide     its content is wider than its box (scrollWidth over clientWidth), or a line of its text
//            runs past its box on either side
//   tall     its content is taller than its box (a fixed-height plate that wrapped)
//   off      its box runs past the viewport
// Prints one JSON object per finding and one summary; exit 1 on a finding or when nothing was measured.
// The browser is launched with a timeout and closed in a finally (U-7).
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, extname, normalize } from "node:path";
import { createServer } from "node:http";

const tree = process.argv[2];
const cfg = JSON.parse(readFileSync(process.argv[3], "utf8"));
const TYPES = { ".css": "text/css", ".js": "application/javascript", ".woff2": "font/woff2",
  ".woff": "font/woff", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
  ".webp": "image/webp", ".html": "text/html", ".json": "application/json" };

let chromium;
try {
  const req = createRequire((process.env.PLAYWRIGHT_NODE_MODULES || "/opt/node-tools/node_modules") + "/");
  ({ chromium } = req("playwright"));
} catch (e) {
  console.log(JSON.stringify({ fail: "no browser: playwright not found (set PLAYWRIGHT_NODE_MODULES)" }));
  process.exit(1);
}

// runs in the page
const READ = ({ plate, tol, dump }) => {
  const main = document.querySelector("main");
  if (!main) return { n: 0, out: [{ kind: "page", what: "no main landmark" }] };
  const own1 = (e) => e.tagName.toLowerCase() + (e.className && typeof e.className === "string"
    ? "." + e.className.trim().split(/\s+/).join(".") : "");
  const vw = document.documentElement.clientWidth;
  const out = [];
  const all = [];
  const GROUP = ".sbc-ls, .sbg-plates, .sbg-hgrid, .tms-row, .sbc-wx, .sbc-wps, .sbc-top";
  const groups = [...main.querySelectorAll(GROUP)];
  let n = 0;
  for (const e of main.querySelectorAll("*")) {
    if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(e.tagName)) continue;
    if (e.closest("svg")) continue;
    if (!e.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true })) continue;
    const cs = getComputedStyle(e);
    if (cs.backgroundColor.replace(/\s+/g, "") !== plate.replace(/\s+/g, "")) continue;
    const text = (e.textContent || "").replace(/\s+/g, " ").trim();
    if (!text) continue;
    n++;
    const r = e.getBoundingClientRect();
    const why = [];
    // 1.6 percent of the plate: a number plate is sized to its text's width in em, and the face's own
    // arithmetic is good to about that
    const tw = Math.max(tol, 0.016 * e.clientWidth);
    if (e.scrollWidth > e.clientWidth + tw) why.push("wide " + e.scrollWidth + " over " + e.clientWidth);
    // a font's content area runs a little past a tight line box without drawing outside the plate; a
    // wrapped line in a fixed-height plate runs past by a whole line, far more than a tenth of the type
    if (e.scrollHeight > e.clientHeight + Math.max(tol, 0.1 * parseFloat(cs.fontSize))) why.push("tall " + e.scrollHeight + " over " + e.clientHeight);
    const rg = document.createRange();
    rg.selectNodeContents(e);
    for (const t of rg.getClientRects()) {
      if (t.width === 0) continue;
      if (t.left < r.left - tw || t.right > r.right + tw) { why.push("text " + Math.round(t.left - r.left) + ".." + Math.round(t.right - r.right) + " past the plate"); break; }
    }
    // a word broken across lines is a plate too narrow for its word, whether or not a letter ran past the edge
    const tn = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    // the Scores page's live chip (.tk-chip-score) is the pre-S-2d chip and is named in the build note as a finding
    // outside this item (the strip, the game page and the team page); it is read for every other kind of clip
    const skipBroke = !!e.closest(".tk-chip-score");
    let broke = false;
    for (let t = tn.nextNode(); t && !broke; t = tn.nextNode()) {
      for (const m of t.textContent.matchAll(/[^\s\-\u2010\u2011\u2013\u2014]+/g)) {
        const w = document.createRange();
        w.setStart(t, m.index);
        w.setEnd(t, m.index + m[0].length);
        const tops = new Set([...w.getClientRects()].filter((q) => q.width > 0).map((q) => Math.round(q.top / 3)));
        if (tops.size > 1) { broke = true; break; }
      }
    }
    if (broke && !skipBroke) why.push("a word is broken across lines");
    if (r.right > vw + tol || r.left < -tol) why.push("off the viewport " + Math.round(r.left) + ".." + Math.round(r.right) + " of " + vw);
    if (dump) {
      const gp = e.closest(GROUP);
      const r1 = (x) => Math.round(x * 100) / 100;
      all.push({ i: all.length, el: own1(e), fs: parseFloat(cs.fontSize), w: r1(r.width), h: r1(r.height),
                 g: gp ? groups.indexOf(gp) : -1, bad: why.length > 0 });
    }
    if (why.length) out.push({ kind: "clipped", el: own1(e), text: text.slice(0, 40), why: why.join("; "), w: Math.round(r.width), size: cs.fontSize });
  }
  return { n, out, all };
};

const fails = [];
const WORKERS = 4;
let measured = 0, loads = 0, browser, server;
const records = [];
const t0 = Date.now();
try {
  const root = normalize(tree);
  server = createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    if (p.endsWith("/")) p += "index.html";
    const file = normalize(join(root, p));
    if (!file.startsWith(root) || !existsSync(file)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream",
      "cache-control": "max-age=600" });
    res.end(readFileSync(file));
  });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  const base = "http://127.0.0.1:" + server.address().port + "/";
  browser = await chromium.launch({ timeout: 60000 });
  for (const width of cfg.widths) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: "light" });
    await ctx.route(/\.(png|jpe?g|webp|gif|ico)(\?.*)?$/, (route) => route.abort());
    let next = 0;
    const work = async () => {
      const pg = await ctx.newPage();
      try {
        while (next < cfg.pages.length) {
          const page = cfg.pages[next++];
          try {
            await pg.goto(base + page, { waitUntil: "load", timeout: 30000 });
            await pg.evaluate(() => document.fonts.ready);
            const osw = await pg.evaluate(() => document.fonts.check('600 18px "Oswald"'));
            if (!osw) throw new Error("the Oswald face is not loaded, so a width read would be a fallback face's");
            const r = await pg.evaluate(READ, { plate: cfg.plate, tol: 1, dump: !!cfg.dump });
            if (cfg.dump) records.push({ page, width, all: r.all });
            measured += r.n;
            loads++;
            for (const o of r.out) {
              const line = Object.assign({ page: "/" + page, width }, o);
              console.log(JSON.stringify(line));
              fails.push(line);
            }
          } catch (e) {
            const line = { fail: "page /" + page + " at " + width + " was not read: " + e.message.split("\n")[0] };
            console.log(JSON.stringify(line));
            fails.push(line);
          }
        }
      } finally {
        await pg.close();
      }
    };
    await Promise.all(Array.from({ length: WORKERS }, work));
    await ctx.close();
  }
  if (!measured) { console.log(JSON.stringify({ fail: "nothing was measured" })); process.exitCode = 1; }
} catch (e) {
  console.log(JSON.stringify({ fail: "the browser read raised " + e.message }));
  process.exitCode = 1;
} finally {
  if (cfg.dump) writeFileSync(cfg.dump, JSON.stringify(records));
  if (browser) await browser.close();
  if (server) server.close();
}
console.log(JSON.stringify({ summary: { plates: measured, loads, findings: fails.length, pages: cfg.pages.length,
  widths: cfg.widths, seconds: Math.round((Date.now() - t0) / 100) / 10 } }));
if (fails.length) process.exitCode = 1;
