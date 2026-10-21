#!/usr/bin/env node
// scripts/look-sweep.mjs: what a converted page RENDERS, read in a browser (S-5.5 round 2).
//
//   node scripts/look-sweep.mjs TREE CONFIG.json
//
// TREE is the built site. CONFIG.json holds { pages: ["scores.html", ...], allowed: ["#0e3b2a", ...],
// oswald: "ABC..." }. For each page it loads the page from TREE (assets from TREE/assets) at 390
// wide in the light and the dark scheme and reads, inside <main> and only what is displayed:
//
//   oswald   every element whose computed font is Oswald: its text as the browser draws it (after
//            text-transform, so an uppercase rule counts as upper and a rule that does not uppercase
//            counts as the text it is) and its ::before and ::after content, against the subset
//   colors   the computed color of every element that prints text, and the background and border
//            colors of every element, against the allowed set (alpha is ignored; a fully
//            transparent color is no color)
//
// The Oswald selectors are never listed here: the computed font says which element is in Oswald.
// Fails when it measured nothing or when the browser is missing, so it cannot pass by not running
// (U-9). The browser is closed in a finally (U-7). Prints one JSON object per finding and one
// summary; exit 1 on a finding.
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { join, extname } from "node:path";

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
  const seenC = new Set(), seenO = new Set();
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
  const col = (e, prop, v) => {
    const h = hex(v);
    if (!h || OK.has(h)) return;
    const k = id(e) + prop + h;
    if (!seenC.has(k)) { seenC.add(k); out.push({ kind: "color", el: id(e), prop, color: h, text: (e.textContent || "").trim().slice(0, 30) }); }
  };
  for (const e of [main, ...main.querySelectorAll("*")]) {
    if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(e.tagName)) continue;
    if (e.closest("svg") && e.tagName !== "svg") continue;
    if (!shown(e)) continue;
    n++;
    const cs = getComputedStyle(e);
    const own = [...e.childNodes].filter((c) => c.nodeType === 3 && c.textContent.trim()).map((c) => c.textContent).join(" ");
    if (own) col(e, "color", cs.color);
    col(e, "background-color", cs.backgroundColor);
    for (const side of ["Top", "Right", "Bottom", "Left"]) {
      if (cs["border" + side + "Style"] !== "none" && parseFloat(cs["border" + side + "Width"]) > 0) {
        col(e, "border-" + side.toLowerCase() + "-color", cs["border" + side + "Color"]);
      }
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
  return { n, out };
};

const fails = [];
let measured = 0, browser;
try {
  browser = await chromium.launch({ timeout: 60000 });
  for (const scheme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: scheme });
    await ctx.route("http://canary.test/**", (route) => {
      let p = new URL(route.request().url()).pathname;
      if (p.endsWith("/")) p += "index.html";
      const file = join(tree, p);
      if (!existsSync(file)) return route.fulfill({ status: 404, body: "" });
      route.fulfill({ status: 200, contentType: TYPES[extname(file)] || "application/octet-stream",
        body: readFileSync(file) });
    });
    for (const page of cfg.pages) {
      const pg = await ctx.newPage();
      try {
        await pg.goto("http://canary.test/" + page, { waitUntil: "load", timeout: 30000 });
        await pg.evaluate(() => document.fonts.ready);
        const r = await pg.evaluate(READ, { allowed: cfg.allowed, oswald: cfg.oswald });
        measured += r.n;
        for (const o of r.out) {
          const line = Object.assign({ page: "/" + page, scheme }, o);
          console.log(JSON.stringify(line));
          fails.push(line);
        }
      } finally {
        await pg.close();
      }
    }
    await ctx.close();
  }
  if (!measured) { console.log(JSON.stringify({ fail: "nothing was measured" })); process.exitCode = 1; }
} catch (e) {
  console.log(JSON.stringify({ fail: "the browser read raised " + e.message }));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
console.log(JSON.stringify({ summary: { measured, findings: fails.length } }));
if (fails.length) process.exitCode = 1;
