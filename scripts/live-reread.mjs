#!/usr/bin/env node
// scripts/live-reread.mjs: S-DONE, the board re-read in place, proved in a browser on the built pages.
//
//   node scripts/live-reread.mjs TREE CASES.json
//
// TREE is a built site (the gate's fixture slate). CASES.json is a list of
//   { name, path, doc, gone: GID|null, click: SELECTOR|null, doc2: DOC|null }
// For each case the page at `path` is loaded from TREE with every request to its data-live-src
// answered by `doc` (null answers 404; no network is touched). With `click`, that element is then
// clicked, the answer becomes `doc2`, and the page is told it is visible again, which makes it
// re-read. After the script has had time to read, the page is read back: the stamp's text and data-asof, whether the card `gone` is still drawn, the counts
// the state tabs print against the cards in each panel, the day the home shows, and any console
// error. Prints one JSON line per case and exits 1 when a case was not read.
// The browser is launched with a timeout and closed in a finally (U-7).
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { join, extname, normalize } from "node:path";
import { createServer } from "node:http";

const tree = process.argv[2];
const cases = JSON.parse(readFileSync(process.argv[3], "utf8"));
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

const server = createServer((req, res) => {
  let p = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^(\.\.[/\\])+/, "");
  if (p.endsWith("/")) p += "index.html";
  let f = join(tree, p);
  if (!existsSync(f) && existsSync(f + ".html")) f += ".html";
  if (!existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": TYPES[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});

// runs in the page
function read(gone) {
  const st = document.querySelector('[data-mf="stamp"]');
  const tabs = {};
  document.querySelectorAll(".sc-states [data-tab]").forEach(a => {
    const t = a.getAttribute("data-tab"), s = a.querySelector("small");
    const panel = document.querySelector('.sc-panel[data-panel="' + t + '"]');
    tabs[t] = { says: s ? Number(s.textContent) : null,
      cards: panel ? panel.querySelectorAll(".tk-c[data-gid]").length : null,
      on: a.classList.contains("on"), shown: panel ? !panel.hidden : null };
  });
  const days = [...document.querySelectorAll(".wb-day")];
  return {
    stamp: st ? st.textContent.trim() : null,
    asof: st ? st.getAttribute("data-asof") : null,
    gone_present: gone ? !!document.querySelector('[data-gid="' + gone + '"]') : null,
    tabs,
    days: days.length, days_shown: days.filter(d => !d.hidden).map(d => d.getAttribute("data-day")),
    day_tab_on: [...document.querySelectorAll(".wb-tabs [data-day].on")].map(a => a.getAttribute("data-day")),
    events: window.__gcmLive || 0,
  };
}

let browser, bad = 0;
try {
  await new Promise(r => server.listen(0, "127.0.0.1", r));
  const origin = "http://127.0.0.1:" + server.address().port;
  browser = await chromium.launch({ timeout: 60000 });
  for (const c of cases) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const errors = [];
    let asked = 0, current = c.doc;
    try {
      await ctx.route(u => !u.href.startsWith(origin), route => {
        const url = route.request().url();
        if (url.includes("/site/data/live/")) {
          asked++;
          if (current === null) return route.fulfill({ status: 404, body: "" });
          return route.fulfill({ status: 200, contentType: "text/plain; charset=utf-8",
            headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(current) });
        }
        route.fulfill({ status: 200, contentType: "application/javascript", body: "" });
      });
      const pg = await ctx.newPage();
      pg.on("console", m => { if (m.type() === "error" && c.doc !== null) errors.push(m.text().slice(0, 200)); });
      pg.on("pageerror", e => errors.push("uncaught: " + String(e.message || e).slice(0, 200)));
      await pg.addInitScript(() => { document.addEventListener("gcm:live", () => { window.__gcmLive = (window.__gcmLive || 0) + 1; }); });
      await pg.goto(origin + c.path, { waitUntil: "load", timeout: 30000 });
      await pg.waitForTimeout(1200);
      if (c.click) {
        await pg.click(c.click);
        current = c.doc2 === undefined ? current : c.doc2;
        await pg.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
        await pg.waitForTimeout(1200);
      }
      const got = await pg.evaluate(read, c.gone || null);
      console.log(JSON.stringify({ name: c.name, path: c.path, asked, errors, ...got }));
    } catch (e) {
      bad++;
      console.log(JSON.stringify({ name: c.name, fail: String(e.message || e).slice(0, 300) }));
    } finally {
      await ctx.close();
    }
  }
} finally {
  if (browser) await browser.close();
  server.close();
}
process.exit(bad ? 1 : 0);
