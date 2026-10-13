#!/usr/bin/env node
// scripts/record-gap.mjs: a team's record never touches the score (13 October 2026).
//
//   node scripts/record-gap.mjs DIR   DIR holds home.html and scores.html, rendered by the build
//
// Loads each page with the repository's own site.css and fonts, at seven widths in light and
// dark, and measures the box of every score (.tk-sc) against the box of the record (.tk-trec)
// on the same chip. A record beside its score needs a clear gap (8px or more); a record under
// it needs to sit below it; a record that overlaps the score, or leaves its chip, fails.
// Fails when it measured nothing, when no font loaded, or when the browser is missing, so
// it cannot pass by not running (U-9). Prints one JSON object per read; exit 1 on a failure.
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const dir = process.argv[2];
const MIN_GAP = 8;
const WIDTHS = [320, 360, 390, 430, 768, 1024, 1440];
const TYPES = { ".css": "text/css", ".js": "application/javascript", ".woff2": "font/woff2",
  ".woff": "font/woff", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
  ".webp": "image/webp", ".html": "text/html" };

let chromium;
try {
  const req = createRequire((process.env.PLAYWRIGHT_NODE_MODULES || "/opt/node-tools/node_modules") + "/");
  ({ chromium } = req("playwright"));
} catch (e) {
  console.log(JSON.stringify({ fail: "no browser: playwright not found (set PLAYWRIGHT_NODE_MODULES)" }));
  process.exit(1);
}

const fails = [];
let measured = 0, fontsSeen = 0, browser;
try {
  browser = await chromium.launch({ timeout: 60000 });
  for (const theme of ["light", "dark"]) for (const w of WIDTHS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: theme });
    await ctx.route("http://canary.test/**", route => {
      const p = new URL(route.request().url()).pathname;
      const file = p.endsWith(".html") ? join(dir, p) : join(ROOT, "site", p);
      if (!existsSync(file)) return route.fulfill({ status: 404, body: "" });
      route.fulfill({ status: 200, contentType: TYPES[extname(file)] || "application/octet-stream",
        body: readFileSync(file) });
    });
    for (const page of ["home.html", "scores.html"]) {
      const pg = await ctx.newPage();
      try {
        await pg.goto("http://canary.test/" + page, { waitUntil: "load", timeout: 30000 });
        await pg.evaluate(() => document.fonts.ready);
        const r = await pg.evaluate(() => {
          const faces = [...document.fonts].filter(f => f.status === "loaded").length;
          const pairs = [];
          document.querySelectorAll(".tk-chip-score").forEach(chip => {
            const sc = chip.querySelector(".tk-sc"), rec = chip.querySelector(".tk-trec");
            if (!sc || !rec) return;
            const a = sc.getBoundingClientRect(), b = rec.getBoundingClientRect(), c = chip.getBoundingClientRect();
            const beside = b.left >= a.right - 0.5, below = b.top >= a.bottom - 0.5;
            const gap = beside ? b.left - a.right : below ? b.top - a.bottom : -Math.min(a.right - b.left, a.bottom - b.top);
            pairs.push({ gap: Math.round(gap * 10) / 10, beside, below,
              out: b.right > c.right + 0.5 || b.left < c.left - 0.5,
              text: chip.textContent.replace(/\s+/g, " ").trim().slice(0, 40) });
          });
          return { faces, pairs };
        });
        fontsSeen += r.faces;
        for (const p of r.pairs) {
          measured++;
          if (!p.beside && !p.below) fails.push(`${page} ${w} ${theme}: record overlaps the score (${p.text})`);
          else if (p.beside && p.gap < MIN_GAP) fails.push(`${page} ${w} ${theme}: score and record are ${p.gap}px apart, under ${MIN_GAP}px (${p.text})`);
          if (p.out) fails.push(`${page} ${w} ${theme}: record leaves its chip (${p.text})`);
        }
        console.log(JSON.stringify({ page, width: w, theme, pairs: r.pairs.length,
          minGap: r.pairs.length ? Math.min(...r.pairs.map(p => p.gap)) : null }));
      } finally { await pg.close(); }
    }
    await ctx.close();
  }
} catch (e) {
  fails.push("record-gap could not run: " + e.message);
} finally {
  if (browser) await browser.close();
}
if (!measured) fails.push("record-gap measured no score and record pair, so it proves nothing");
if (!fontsSeen) fails.push("record-gap loaded no font, so it measured a stand-in (U-10)");
for (const f of fails.slice(0, 12)) console.log(JSON.stringify({ fail: f }));
process.exit(fails.length ? 1 : 0);
