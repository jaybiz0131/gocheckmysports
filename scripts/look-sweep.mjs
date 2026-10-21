#!/usr/bin/env node
// scripts/look-sweep.mjs: what a converted page RENDERS, read in a browser (S-5.5 round 2).
//
//   node scripts/look-sweep.mjs TREE CONFIG.json
//
// TREE is the built site. CONFIG.json holds { pages: ["scores.html", ...], allowed: ["#0e3b2a", ...],
// oswald: "ABC..." }. For EVERY page listed (round 3: the canary lists every converted page, not a
// sample) it loads the page from TREE (assets from TREE/assets, served by a local http server) at
// 390 wide in the light and the dark scheme, four pages at a time in one browser, and reads, inside
// <main> and only what is displayed:
//
//   oswald   every element whose computed font is Oswald: its text as the browser draws it (after
//            text-transform, so an uppercase rule counts as upper and a rule that does not uppercase
//            counts as the text it is) and its ::before and ::after content, against the subset
//   colors   the computed color of every element that prints text, and the background and border
//            colors of every element and of its ::before and ::after, against the allowed set (alpha
//            is ignored; a fully transparent color is no color)
//
// The summary carries the pages read in each scheme, so the caller can fail when a page was skipped,
// and the distinct tag+class signatures rendered inside main.
//
// The Oswald selectors are never listed here: the computed font says which element is in Oswald.
// Fails when it measured nothing or when the browser is missing, so it cannot pass by not running
// (U-9). The browser is closed in a finally (U-7). Prints one JSON object per finding and one
// summary; exit 1 on a finding.
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
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
const READ = ({ allowed, oswald }) => {
  const OK = new Set(allowed);
  const OSW = new Set([...oswald]);
  const hex = (c) => {
    const m = c.match(/rgba?\(([^)]*)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean);
    const a = p.length > 3 ? parseFloat(p[3]) : 1;
    if (a === 0) return null;
    return "#" + p.slice(0, 3).map((x) => Math.round(parseFloat(x)).toString(16).padStart(2, "0")).join("");
  };
  const main = document.querySelector("main");
  const out = [];
  if (!main) return { n: 0, out: [{ kind: "page", what: "no main landmark" }] };
  const own1 = (e) => e.tagName.toLowerCase() + (e.className && typeof e.className === "string"
    ? "." + e.className.trim().split(/\s+/).join(".") : "");
  // an element with no class of its own is named with the parent it sits in
  const id = (e) => (own1(e).includes(".") || !e.parentElement || e.parentElement === main)
    ? own1(e) : own1(e.parentElement) + " > " + own1(e);
  const shown = (e) => e.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true });
  const seenC = new Set(), seenO = new Set(), sigs = new Set();
  let n = 0;
  const xform = (s, t) => t === "uppercase" ? s.toUpperCase() : t === "lowercase" ? s.toLowerCase() : s;
  const oswaldIn = (cs) => /^\s*["']?oswald/i.test(cs.fontFamily);
  const checkText = (e, cs, text, where) => {
    const t = xform(text.replace(/\s+/g, " "), cs.textTransform);
    const odd = [...new Set([...t].filter((ch) => !OSW.has(ch)))];
    if (odd.length) {
      const k = id(e) + where + t;
      if (!seenO.has(k)) { seenO.add(k); out.push({ kind: "oswald", el: id(e) + where, text: t.slice(0, 40), odd: odd.slice(0, 6), transform: cs.textTransform }); }
    }
  };
  const col = (e, prop, v, where = "") => {
    const h = hex(v);
    if (!h || OK.has(h)) return;
    const k = id(e) + where + prop + h;
    if (!seenC.has(k)) { seenC.add(k); out.push({ kind: "color", el: id(e) + where, prop, color: h, text: (e.textContent || "").trim().slice(0, 30) }); }
  };
  const borders = (e, cs, where) => {
    for (const side of ["Top", "Right", "Bottom", "Left"]) {
      if (cs["border" + side + "Style"] !== "none" && parseFloat(cs["border" + side + "Width"]) > 0) {
        col(e, "border-" + side.toLowerCase() + "-color", cs["border" + side + "Color"], where);
      }
    }
  };
  for (const e of [main, ...main.querySelectorAll("*")]) {
    if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(e.tagName)) continue;
    if (e.closest("svg") && e.tagName !== "svg") continue;
    if (!shown(e)) continue;
    n++;
    sigs.add(own1(e));
    const cs = getComputedStyle(e);
    const own = [...e.childNodes].filter((c) => c.nodeType === 3 && c.textContent.trim()).map((c) => c.textContent).join(" ");
    if (own) col(e, "color", cs.color);
    col(e, "background-color", cs.backgroundColor);
    borders(e, cs, "");
    for (const ps of ["::before", "::after"]) {
      const pc = getComputedStyle(e, ps);
      const c = pc.content;
      if (!c || c === "none" || c === "normal") continue;
      if (/^["']/.test(c) && c.length > 2) col(e, "color", pc.color, ps);
      col(e, "background-color", pc.backgroundColor, ps);
      borders(e, pc, ps);
    }
    if (oswaldIn(cs)) {
      if (own) checkText(e, cs, own, "");
      for (const ps of ["::before", "::after"]) {
        const pc = getComputedStyle(e, ps);
        const c = pc.content;
        if (c && c !== "none" && c !== "normal" && /^["']/.test(c)) checkText(e, pc, c.slice(1, -1), ps);
      }
    }
  }
  return { n, out, sigs: [...sigs] };
};

const fails = [];
const WORKERS = 4;
let measured = 0, browser, server;
const sigAll = new Set();
const read = {};
const t0 = Date.now();
try {
  // one local server for the tree: faster than intercepting every request, and the browser caches
  // the stylesheet and the fonts across pages
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
  for (const scheme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: scheme });
    await ctx.route(/\.(png|jpe?g|webp|gif|ico)(\?.*)?$/, (route) => route.abort());
    read[scheme] = 0;
    let next = 0;
    const work = async () => {
      const pg = await ctx.newPage();
      try {
        while (next < cfg.pages.length) {
          const page = cfg.pages[next++];
          try {
            await pg.goto(base + page, { waitUntil: "load", timeout: 30000 });
            await pg.evaluate(() => document.fonts.ready);
            const r = await pg.evaluate(READ, { allowed: cfg.allowed, oswald: cfg.oswald });
            measured += r.n;
            read[scheme]++;
            for (const g of r.sigs || []) sigAll.add(g);
            for (const o of r.out) {
              const line = Object.assign({ page: "/" + page, scheme }, o);
              console.log(JSON.stringify(line));
              fails.push(line);
            }
          } catch (e) {
            const line = { fail: "page /" + page + " (" + scheme + ") was not read: " + e.message.split("\n")[0] };
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
  if (browser) await browser.close();
  if (server) server.close();
}
console.log(JSON.stringify({ summary: { measured, findings: fails.length, pages: cfg.pages.length,
  read_light: read.light || 0, read_dark: read.dark || 0, signatures: sigAll.size,
  seconds: Math.round((Date.now() - t0) / 100) / 10 } }));
if (fails.length) process.exitCode = 1;
