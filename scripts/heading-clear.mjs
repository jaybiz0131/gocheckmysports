#!/usr/bin/env node
// scripts/heading-clear.mjs: a jump to a window heading lands it clear of the sticky chrome (S-5.4).
//
//   node scripts/heading-clear.mjs DIR [id ...]   DIR holds home.html, rendered by the build
//
// Loads home.html with the repository's own site.css and fonts at 390 wide, follows #id for each
// window heading (default win-1pm, win-late, win-night), and measures where the heading lands against
// the bottom of the sticky day label and the sticky nav above it. A heading that lands under either
// fails. Fails when it measured nothing or when the browser is missing, so it cannot pass by not
// running (U-9). The browser is closed in a finally (U-7). Prints one JSON object per heading;
// exit 1 on a failure.
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const dir = process.argv[2];
const ids = process.argv.length > 3 ? process.argv.slice(3) : ["win-1pm", "win-late", "win-night"];
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

const READ = (id) => {
  const h = document.getElementById(id);
  if (!h) return null;
  const day = h.closest(".wb-day");
  const lg = day && day.querySelector(".tk-lg");
  const nav = document.querySelector(".mh-nav");
  const sticky = (e) => e && getComputedStyle(e).position === "sticky";
  return { top: h.getBoundingClientRect().top,
    lg: sticky(lg) ? lg.getBoundingClientRect().bottom : 0,
    nav: sticky(nav) ? nav.getBoundingClientRect().bottom : 0,
    margin: getComputedStyle(h).scrollMarginTop };
};

const fails = [];
let measured = 0, browser;
try {
  browser = await chromium.launch({ timeout: 60000 });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await ctx.route("http://canary.test/**", route => {
    const p = new URL(route.request().url()).pathname;
    const file = p.endsWith(".html") ? join(dir, p) : join(ROOT, "site", p);
    if (!existsSync(file)) return route.fulfill({ status: 404, body: "" });
    route.fulfill({ status: 200, contentType: TYPES[extname(file)] || "application/octet-stream",
      body: readFileSync(file) });
  });
  for (const id of ids) {
    const pg = await ctx.newPage();
    try {
      await pg.goto("http://canary.test/home.html#" + id, { waitUntil: "load", timeout: 30000 });
      await pg.evaluate(() => document.fonts.ready);
      await pg.waitForTimeout(400);
      const r = await pg.evaluate(READ, id);
      if (!r) { fails.push(`no heading #${id} on the page`); continue; }
      measured++;
      const clear = Math.max(r.lg, r.nav);
      console.log(JSON.stringify({ id, top: r.top, clear, margin: r.margin }));
      if (r.top < clear - 0.5) {
        fails.push(`at 390 a jump to #${id} lands the heading at ${r.top.toFixed(0)}px, under the sticky chrome that ends at ${clear.toFixed(0)}px (scroll-margin-top ${r.margin})`);
      }
    } finally {
      await pg.close();
    }
  }
  if (!measured) fails.push("nothing was measured");
} catch (e) {
  fails.push("the browser read raised " + e.message);
} finally {
  if (browser) await browser.close();
}
for (const f of fails) console.log(JSON.stringify({ fail: f }));
process.exit(fails.length ? 1 : 0);
