#!/usr/bin/env node
// scripts/page-measure.mjs: S-5.2, scorecard lines 4 and 10 measured on the built pages.
//
//   node scripts/page-measure.mjs SPEC.json
//
// SPEC is {"root": DIR, "lighthouse": [[PATH, RUNS], ...], "console": [PATH, ...], "inline": {PATH: HTML}},
// where DIR is a built publish tree and each PATH a page in it ("/index.html"). An inline page is
// served from the spec in place of a file: the canary's fixtures, each a built page with one thing
// added.
//
// The tree is served from 127.0.0.1 by this script, gzipped as the host serves it, so the pages
// load the build's own stylesheet, fonts and images. Two reads, both in the Chromium that CI
// installs for Playwright (no browser of its own is fetched):
//
//   lighthouse  Lighthouse's default mobile run (Moto G Power screen, simulated slow 4G and 4x
//               CPU), performance category only, RUNS runs per page; the score printed is the
//               median run, since a single run varies. Every host but this server is
//               blocked, so the figure is the site's own bytes: the one third host on these
//               pages, the Cloudflare beacon the October 14 ruling allows, is deferred and
//               not in it.
//   console     every console message of type error and every uncaught page error while the
//               page loads and settles, at 390 wide. A request to a third host is answered
//               with an empty 200 here, the gate being offline, and is named in the output.
//
// Prints one JSON object per read and the page's build-commit and loaded font count, so the
// caller can prove it measured the tree it built (U-10). Fails (exit 1) when it could not
// measure: no Playwright, no Lighthouse, a page that is not 200, no score. Thresholds are the
// caller's (measure_canary.py), so a figure is always printed before it is judged.
import { createRequire } from "node:module";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname, normalize } from "node:path";
import { pathToFileURL } from "node:url";
import { createServer } from "node:http";
import { gzipSync } from "node:zlib";

const spec = JSON.parse(readFileSync(process.argv[2], "utf8"));
const ROOT = spec.root;
const INLINE = spec.inline || {};
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript",
  ".mjs": "application/javascript", ".json": "application/json", ".webmanifest": "application/manifest+json",
  ".xml": "application/xml", ".txt": "text/plain", ".svg": "image/svg+xml", ".woff2": "font/woff2",
  ".woff": "font/woff", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".webp": "image/webp", ".avif": "image/avif", ".ico": "image/x-icon", ".mp4": "video/mp4",
  ".webm": "video/webm" };
const ZIP = new Set([".html", ".css", ".js", ".mjs", ".json", ".webmanifest", ".xml", ".txt", ".svg"]);

const fails = [];
const out = o => console.log(JSON.stringify(o));
const nm = process.env.PLAYWRIGHT_NODE_MODULES || "/opt/node-tools/node_modules";
let chromium;
try {
  ({ chromium } = createRequire(nm + "/")("playwright"));
} catch (e) {
  out({ fail: "no browser: playwright not found (set PLAYWRIGHT_NODE_MODULES)" });
  process.exit(1);
}

const server = createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (p.endsWith("/")) p += "index.html";
  if (Object.prototype.hasOwnProperty.call(INLINE, p)) {
    const z = /\bgzip\b/.test(req.headers["accept-encoding"] || "");
    const b = z ? gzipSync(Buffer.from(INLINE[p])) : Buffer.from(INLINE[p]);
    res.writeHead(200, { "content-type": TYPES[".html"], "cache-control": "no-cache", "content-length": b.length,
      ...(z ? { "content-encoding": "gzip" } : {}) });
    return res.end(b);
  }
  const file = normalize(join(ROOT, p));
  if (!file.startsWith(normalize(ROOT)) || !existsSync(file) || !statSync(file).isFile()) {
    res.writeHead(404, { "content-type": "text/plain" });
    return res.end("not found");
  }
  const ext = extname(file).toLowerCase();
  let body = readFileSync(file);
  const head = { "content-type": TYPES[ext] || "application/octet-stream", "cache-control": "no-cache" };
  if (ZIP.has(ext) && /\bgzip\b/.test(req.headers["accept-encoding"] || "")) {
    body = gzipSync(body);
    head["content-encoding"] = "gzip";
  }
  head["content-length"] = body.length;
  res.writeHead(200, head);
  res.end(body);
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const ORIGIN = `http://127.0.0.1:${server.address().port}`;

const freePort = () => new Promise(r => {
  const s = createServer();
  s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => r(p)); });
});
const median = a => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };

let browser;
try {
  const cdp = await freePort();
  // Every name but this server's resolves to nothing, and no proxy (Chromium on Linux reads one
  // from the environment and would resolve the name itself), so Lighthouse cannot reach a third host.
  browser = await chromium.launch({ timeout: 60000,
    args: [`--remote-debugging-port=${cdp}`, "--no-proxy-server",
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"] });

  // CONSOLE: errors while each page loads and settles.
  for (const path of spec.console || []) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3,
      isMobile: true, hasTouch: true });
    const third = new Set();
    await ctx.route(u => !u.href.startsWith(ORIGIN), route => {
      third.add(new URL(route.request().url()).host);
      route.fulfill({ status: 200, contentType: "application/javascript", body: "" });
    });
    const pg = await ctx.newPage();
    const errors = [];
    pg.on("console", m => { if (m.type() === "error") errors.push("console: " + m.text().slice(0, 240)); });
    pg.on("pageerror", e => errors.push("uncaught: " + String(e.message || e).slice(0, 240)));
    try {
      const resp = await pg.goto(ORIGIN + path, { waitUntil: "load", timeout: 30000 });
      if (!resp || resp.status() !== 200) {
        fails.push(`console ${path}: the page answered ${resp ? resp.status() : "nothing"}, not 200`);
        continue;
      }
      await pg.evaluate(() => document.fonts.ready);
      // Settle: the scripts that wait for load, the service worker's register, a timer or two.
      await pg.waitForTimeout(1500);
      const r = await pg.evaluate(() => ({
        stamp: (document.querySelector('meta[name="build-commit"]') || {}).content || "",
        fonts: [...document.fonts].filter(f => f.status === "loaded").length }));
      out({ kind: "console", path, errors, stamp: r.stamp, fonts: r.fonts, third: [...third].sort() });
    } finally {
      await pg.close();
      await ctx.close();
    }
  }

  // LIGHTHOUSE: mobile performance, the median of RUNS.
  if ((spec.lighthouse || []).length) {
    let lighthouse;
    try {
      const lhPkg = createRequire(nm + "/").resolve("lighthouse/package.json");
      ({ default: lighthouse } = await import(pathToFileURL(join(lhPkg, "..", "core", "index.js")).href));
    } catch (e) {
      throw new Error("lighthouse not found beside playwright (" + e.message.slice(0, 120) + ")");
    }
    for (const [path, n] of spec.lighthouse) {
      const runs = [];
      for (let i = 0; i < Math.max(1, n || 1); i++) {
        const rr = await lighthouse(ORIGIN + path, { port: cdp, output: "json", logLevel: "error",
          onlyCategories: ["performance"] });
        const lhr = rr && rr.lhr;
        if (!lhr || lhr.runtimeError) {
          throw new Error(`lighthouse ${path}: ${lhr && lhr.runtimeError ? lhr.runtimeError.message : "no result"}`);
        }
        const score = lhr.categories.performance.score;
        if (typeof score !== "number") throw new Error(`lighthouse ${path}: no performance score`);
        const a = lhr.audits;
        const ms = id => Math.round((a[id] && a[id].numericValue) || 0);
        runs.push({ score: Math.round(score * 100), fcp: ms("first-contentful-paint"),
          lcp: ms("largest-contentful-paint"), tbt: ms("total-blocking-time"),
          cls: Math.round(((a["cumulative-layout-shift"] || {}).numericValue || 0) * 1000) / 1000,
          si: ms("speed-index"), final: lhr.finalDisplayedUrl || lhr.finalUrl,
          version: lhr.lighthouseVersion, formFactor: lhr.configSettings.formFactor,
          throttling: lhr.configSettings.throttlingMethod });
      }
      const m = median(runs.map(r => r.score));
      const pick = runs.find(r => r.score === m);
      out({ kind: "lighthouse", path, score: m, runs: runs.map(r => r.score), median: pick });
    }
  }
} catch (e) {
  fails.push("page-measure could not run: " + String(e.message || e).slice(0, 300));
} finally {
  if (browser) await browser.close().catch(() => {});
  server.close();
}
for (const f of fails) out({ fail: f });
process.exit(fails.length ? 1 : 0);
