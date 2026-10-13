#!/usr/bin/env node
// scripts/prod-read.mjs: a production read by stamp (U-10) and a screenshot harness (U-7).
//
//   node scripts/prod-read.mjs --commit <short> [--base https://gocheckmysports.com]
//        [--widths 375,1440] [--paths /,/scores.html,...] [--shots DIR] [--themes light,dark]
//
// Reads /stamp.txt first and fails if the deployed commit is not the one meant. Then, for each
// path and width: the build-commit meta, every data-mf stamp and count, the nav and tab bar
// links, the games on the page, whether the page scrolls sideways, and whether the word "live"
// is in its visible text. The browser is launched with a timeout and closed in a finally
// block (U-7). Prints one JSON object per read.
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";

// playwright is not a dependency of this repo; the cloud image has it under /opt/node-tools,
// and PLAYWRIGHT_NODE_MODULES points elsewhere on another machine.
const req = createRequire((process.env.PLAYWRIGHT_NODE_MODULES || "/opt/node-tools/node_modules") + "/");
const { chromium } = req("playwright");

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const BASE = opt("--base", "https://gocheckmysports.com");
const WANT = opt("--commit", "");
const WIDTHS = opt("--widths", "375,1440").split(",").map(Number);
const PATHS = opt("--paths", "/,/scores.html,/where-to-watch,/fantasy/index").split(",");
const SHOTS = opt("--shots", "");
const THEMES = opt("--themes", "light").split(",");

const stamp = await (await fetch(`${BASE}/stamp.txt`, { cache: "no-store" })).text();
const got = (stamp.match(/commit ([0-9a-f]{7,40})/) || [])[1] || "";
console.log(JSON.stringify({ stamp: stamp.trim().split("\n"), want: WANT, ok: !WANT || got.startsWith(WANT) }));
if (WANT && !got.startsWith(WANT)) { console.error(`deployed ${got.slice(0, 7)}, wanted ${WANT}`); process.exit(2); }

if (SHOTS) mkdirSync(SHOTS, { recursive: true });
let browser;
try {
  browser = await chromium.launch({ timeout: 60000 });
  for (const theme of THEMES) {
    for (const w of WIDTHS) {
      const ctx = await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: theme });
      for (const path of PATHS) {
        const page = await ctx.newPage();
        try {
          await page.goto(BASE + path, { waitUntil: "load", timeout: 45000 });
          await page.evaluate(() => document.fonts && document.fonts.ready);
          const r = await page.evaluate(() => {
            const vis = (document.body.innerText || "");
            const mf = [...document.querySelectorAll("[data-mf]")].map(e => [e.dataset.mf, e.textContent.trim()]);
            const link = s => [...document.querySelectorAll(s)].map(a => a.textContent.trim() + " > " + a.getAttribute("href"));
            const units = [...document.querySelectorAll("[data-gid]")]
              .filter(e => !e.closest(".tk-open") && !(e.closest(".tk-pair") && e !== e.closest(".tk-pair")))
              .map(e => e.getAttribute("data-gid"));
            return {
              build: (document.querySelector('meta[name="build-commit"]') || {}).content || "",
              mf, nav: link("nav a"), bar: link(".tabbar a, .tb a, nav.tabs a"),
              games: units.length, uniqueGames: new Set(units).size,
              liveWord: /\blive\b/i.test(vis),
              scrollsSideways: document.documentElement.scrollWidth > window.innerWidth + 1,
              h1: (document.querySelector("h1") || {}).textContent || ""
            };
          });
          const { nav, bar, ...rest } = r;
          const full = argv.includes("--nav");
          console.log(JSON.stringify({ path, width: w, theme, ...rest, navCount: nav.length, barCount: bar.length,
            ...(full ? { nav, bar } : {}), buildOk: !WANT || r.build.startsWith(WANT) }));
          if (SHOTS && (path === "/" || path === "/scores.html")) {
            const name = `${path === "/" ? "home" : "scores"}-${w}-${theme}.png`;
            await page.screenshot({ path: `${SHOTS}/${name}`, fullPage: true });
          }
        } finally { await page.close(); }
      }
      await ctx.close();
    }
  }
} finally {
  if (browser) await browser.close();
}
