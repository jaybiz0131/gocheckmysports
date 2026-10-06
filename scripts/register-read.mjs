#!/usr/bin/env node
// scripts/register-read.mjs: the register read for the first Search Console export (S-6).
//
// Reads the two exports Search Console gives, against the deep-URL register
// (/data/deep-urls.json) and the sitemaps, and prints the day-14 report. Node 18+, no
// packages. The read itself is the owner's; this makes it ten minutes.
//
//   node scripts/register-read.mjs --performance Pages.csv --indexed Indexed.csv \
//        --not-indexed Reason1.csv [--not-indexed Reason2.csv ...]
//
//   --performance FILE   Performance, Pages, as CSV (columns: page, Clicks, Impressions)
//   --indexed FILE       Indexing, Pages, the indexed list, as CSV (column: URL)
//   --not-indexed FILE   Indexing, Pages, one not-indexed reason, as CSV; repeat per reason.
//                        The reason is the file's name unless the CSV has a Reason column.
//   --register SRC       the register: a file or a URL (default: the live /data/deep-urls.json)
//   --sitemaps SRC       a sitemap or sitemap index, file or URL (default: the live sitemap.xml);
//                        these are the pages the site ASKED to have indexed, the "linked" class
//   --out FILE           write the report to FILE (default: docs/SEARCH-READ-<ET date>.md)
//   --stdout             print the report instead of writing a file
//   --json               print the structured result instead of the report
//   --now ISO            the clock, for tests
//
// A register page with no row in an export is ABSENT, never zero. A URL matches its page
// after the host, the query string, the fragment, a trailing slash and a .html suffix are
// dropped; two rows that match one page add.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ORIGIN = "https://gocheckmysports.com";

const HELP = `register-read: the register read for the first Search Console export.

The two exports to make (Search Console, property gocheckmysports.com):
  1. Performance, Pages: Performance > Search results > the Pages tab > Export > Download CSV
     (the Pages.csv, or the Pages sheet saved as CSV). Pass it as --performance.
  2. Indexing, Pages: Indexing > Pages. For the indexed list, "View data about indexed pages",
     then Export > Download CSV, passed as --indexed. For each reason under "Why pages aren't
     indexed", open the row, Export > Download CSV, and pass each as --not-indexed.
Menus move; the columns are what matter (a URL column; Clicks and Impressions).

  node scripts/register-read.mjs --performance Pages.csv --indexed Indexed.csv \\
       --not-indexed Reason1.csv --not-indexed Reason2.csv
`;

function parseArgs(argv) {
  const a = { notIndexed: [] };
  if (argv.includes("--help") || argv.includes("-h")) { console.log(HELP); process.exit(0); }
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === "--performance") a.performance = v();
    else if (k === "--indexed") a.indexed = v();
    else if (k === "--not-indexed") a.notIndexed.push(v());
    else if (k === "--register") a.register = v();
    else if (k === "--sitemaps") a.sitemaps = v();
    else if (k === "--out") a.out = v();
    else if (k === "--now") a.now = v();
    else if (k === "--stdout") a.stdout = true;
    else if (k === "--json") a.json = true;
    else { console.error(`register-read: unknown argument ${k}`); process.exit(2); }
  }
  return a;
}

async function read(src) {
  if (/^https?:\/\//.test(src)) {
    const r = await fetch(src, { headers: { "user-agent": "gocheckmysports-register-read" } });
    if (!r.ok) throw new Error(`${src} answered ${r.status}`);
    return await r.text();
  }
  return readFileSync(src, "utf8");
}

// ---- CSV: quotes, commas inside quotes, CRLF, a BOM -------------------------------
export function parseCsv(text) {
  text = text.replace(/^﻿/, "");
  const rows = [];
  let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); cell = "";
      if (row.some((x) => x !== "")) rows.push(row);
      row = [];
    } else cell += c;
  }
  row.push(cell);
  if (row.some((x) => x !== "")) rows.push(row);
  return rows;
}

const num = (s) => {
  const n = Number(String(s ?? "").replace(/[,\s]/g, ""));
  return Number.isFinite(n) && String(s ?? "").trim() !== "" ? n : null;
};

function table(text) {
  const rows = parseCsv(text);
  if (!rows.length) return { head: [], body: [] };
  const head = rows[0].map((h) => h.trim().toLowerCase());
  return { head, body: rows.slice(1) };
}

// ---- URL -> the page it is ----------------------------------------------------------
// The path, with the query, fragment, trailing slash and .html dropped. A URL on another
// host keeps its host so it cannot collide with a page of ours.
export function pageKey(u) {
  let url;
  try { url = new URL(u.trim(), ORIGIN); } catch { return null; }
  const host = url.hostname.toLowerCase().replace(/^www\./, "");
  let p = url.pathname.replace(/\.html$/, "");
  if (p.length > 1) p = p.replace(/\/+$/, "");
  if (p === "") p = "/";
  return host === "gocheckmysports.com" ? p : `${host}${p}`;
}

// ---- sitemaps -------------------------------------------------------------------------
async function sitemapPaths(src, seen = new Set()) {
  if (seen.has(src)) return [];
  seen.add(src);
  const xml = await read(src);
  const out = [];
  if (/<sitemapindex/.test(xml)) {
    for (const m of xml.matchAll(/<sitemap>\s*<loc>([^<]*)<\/loc>/g)) {
      const loc = m[1].trim();
      // an index in a directory names its children by URL; a local run reads them beside it
      const child = /^https?:\/\//.test(src) ? loc : join(dirname(src), basename(loc));
      out.push(...(await sitemapPaths(child, seen)));
    }
  } else {
    for (const m of xml.matchAll(/<loc>([^<]*)<\/loc>/g)) out.push(pageKey(m[1]));
  }
  return out.filter(Boolean);
}

// ---- the read ---------------------------------------------------------------------------
export async function compute(a) {
  const register = JSON.parse(await read(a.register || `${ORIGIN}/data/deep-urls.json`));
  const deep = new Map();
  for (const e of register.entries || []) deep.set(pageKey(e.url), e);

  let listedNote = "";
  let listed = new Set();
  try {
    listed = new Set(await sitemapPaths(a.sitemaps || `${ORIGIN}/sitemap.xml`));
  } catch (e) {
    listedNote = `The sitemaps could not be read (${e.message}), so the "linked" class is empty and every URL outside the register reads as unknown.`;
  }

  // performance: rows that match one page add
  const perf = new Map();
  let perfRows = 0;
  if (a.performance) {
    const t = table(await read(a.performance));
    const ci = t.head.findIndex((h) => h === "clicks");
    const ii = t.head.findIndex((h) => h === "impressions");
    for (const r of t.body) {
      const k = pageKey(r[0] || "");
      if (!k) continue;
      perfRows++;
      const cur = perf.get(k) || { clicks: 0, impressions: 0 };
      cur.clicks += num(r[ci]) ?? 0;
      cur.impressions += num(r[ii]) ?? 0;
      perf.set(k, cur);
    }
  }

  // indexing: indexed, or not indexed with a reason; a page in neither is absent
  const status = new Map();
  const counts = { indexed: 0, notIndexed: 0 };
  const urlCol = (t) => {
    const i = t.head.findIndex((h) => h === "url" || h === "page");
    return i >= 0 ? i : 0;
  };
  if (a.indexed) {
    const t = table(await read(a.indexed));
    const u = urlCol(t);
    for (const r of t.body) {
      const k = pageKey(r[u] || "");
      if (k) { status.set(k, "indexed"); counts.indexed++; }
    }
  }
  for (const f of a.notIndexed) {
    const t = table(await read(f));
    const u = urlCol(t);
    const ri = t.head.findIndex((h) => h === "reason");
    const fallback = basename(f).replace(/\.csv$/i, "").replace(/^not-indexed[-_ ]?/i, "").replace(/[-_]+/g, " ").trim() || "not indexed";
    for (const r of t.body) {
      const k = pageKey(r[u] || "");
      if (!k) continue;
      counts.notIndexed++;
      if (status.get(k) !== "indexed") status.set(k, `not indexed: ${(ri >= 0 && r[ri]) || fallback}`);
    }
  }

  const known = new Set([...deep.keys(), ...listed]);
  const pages = [];
  for (const k of known) {
    const p = perf.get(k) || null;
    pages.push({
      path: k,
      class: deep.has(k) ? "deep" : "linked",
      kind: deep.get(k)?.kind || null,
      linkedFrom: deep.get(k)?.linked_from ?? null,
      inbound: deep.get(k)?.inbound ?? null,
      indexed: status.get(k) || "absent",
      clicks: p ? p.clicks : null,
      impressions: p ? p.impressions : null,
    });
  }
  pages.sort((x, y) => (x.class === y.class ? (y.impressions ?? -1) - (x.impressions ?? -1) || x.path.localeCompare(y.path) : x.class === "deep" ? -1 : 1));

  const seenUnknown = new Map();
  for (const k of new Set([...perf.keys(), ...status.keys()])) {
    if (known.has(k)) continue;
    if (!seenUnknown.has(k)) {
      const p = perf.get(k) || null;
      seenUnknown.set(k, { path: k, indexed: status.get(k) || "absent",
        clicks: p ? p.clicks : null, impressions: p ? p.impressions : null,
        inPerformance: !!p });
    }
  }
  const unknowns = [...seenUnknown.values()].sort((x, y) => (y.impressions ?? -1) - (x.impressions ?? -1) || x.path.localeCompare(y.path));
  const deepIndexed = pages.filter((p) => p.class === "deep" && p.indexed === "indexed");
  const linkedMissing = pages.filter((p) => p.class === "linked" && p.indexed !== "indexed");
  return { registerStamp: register.stamp || null, registerCount: (register.entries || []).length,
           listedCount: listed.size, listedNote, perfRows, counts, pages, unknowns,
           deepIndexed, linkedMissing };
}

// ---- the report, in the day-14 shape ------------------------------------------------------
const etStamp = (d) => {
  const f = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "numeric", minute: "2-digit", hour12: true });
  const p = Object.fromEntries(f.formatToParts(d).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, text: `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} ${p.dayPeriod} ET` };
};
const cell = (v) => (v === null || v === undefined ? "no row" : String(v));

export function report(r, now, a) {
  const t = etStamp(now);
  const L = [];
  L.push(`# Search read, day 14: the first Search Console export`, ``);
  L.push(`Generated ${t.text} by scripts/register-read.mjs. The read itself is the owner's; this file is what the export says against the register.`, ``);
  L.push(`## Inputs`, ``);
  L.push(`- Register: ${r.registerCount} deep pages${r.registerStamp ? `, built ${r.registerStamp.built} at ${String(r.registerStamp.commit).slice(0, 12)}` : ""}.`);
  L.push(`- Sitemaps: ${r.listedCount} pages the site asked to have indexed (class "linked").${r.listedNote ? " " + r.listedNote : ""}`);
  L.push(`- Performance, Pages: ${a.performance ? `${a.performance}, ${r.perfRows} rows` : "not given"}.`);
  L.push(`- Indexing, Pages: ${a.indexed ? `${a.indexed}, ${r.counts.indexed} indexed` : "indexed list not given"}; ${a.notIndexed.length ? `${r.counts.notIndexed} not indexed across ${a.notIndexed.length} reason file(s)` : "no not-indexed files given"}.`);
  L.push(`- A page with no row in an export is "absent" or "no row", never zero. Rows that match one page add.`, ``);
  L.push(`## Unknown to the site (${r.unknowns.length})`, ``);
  L.push(`URLs in the exports that are in neither the register nor the sitemaps. Look at these first.`, ``);
  if (r.unknowns.length) {
    L.push(`| Page | Indexing | Clicks | Impressions |`, `|---|---|---|---|`);
    for (const u of r.unknowns) L.push(`| ${u.path} | ${u.indexed} | ${cell(u.clicks)} | ${cell(u.impressions)} |`);
  } else L.push(`None.`);
  L.push(``, `## Deep pages indexed anyway (${r.deepIndexed.length})`, ``);
  L.push(`In the register, so left out of every sitemap on purpose, and indexed all the same.`, ``);
  if (r.deepIndexed.length) {
    L.push(`| Page | Kind | Clicks | Impressions |`, `|---|---|---|---|`);
    for (const p of r.deepIndexed) L.push(`| ${p.path} | ${p.kind} | ${cell(p.clicks)} | ${cell(p.impressions)} |`);
  } else L.push(`None.`);
  L.push(``, `## Linked pages missing from the index (${r.linkedMissing.length})`, ``);
  L.push(`In the sitemaps, so the site asked for them, and not indexed. "absent" means neither export has a row.`, ``);
  if (r.linkedMissing.length) {
    L.push(`| Page | Indexing | Clicks | Impressions |`, `|---|---|---|---|`);
    for (const p of r.linkedMissing) L.push(`| ${p.path} | ${p.indexed} | ${cell(p.clicks)} | ${cell(p.impressions)} |`);
  } else L.push(`None.`);
  L.push(``, `## Every register page, with its class (${r.pages.length})`, ``);
  L.push(`Class "deep" is deep by design (in the register); "linked" is a page the sitemaps list.`, ``);
  L.push(`| Page | Class | Kind | Indexing | Clicks | Impressions |`, `|---|---|---|---|---|---|`);
  for (const p of r.pages) L.push(`| ${p.path} | ${p.class} | ${p.kind || ""} | ${p.indexed} | ${cell(p.clicks)} | ${cell(p.impressions)} |`);
  L.push(``);
  return L.join("\n");
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  const now = a.now ? new Date(a.now) : new Date();
  const r = await compute(a);
  if (a.json) { console.log(JSON.stringify(r)); return; }
  const md = report(r, now, a);
  if (a.stdout) { process.stdout.write(md); return; }
  const out = a.out || join(HERE, "..", "docs", `SEARCH-READ-${etStamp(now).date}.md`);
  writeFileSync(out, md);
  console.log(`register-read: wrote ${out} (${r.unknowns.length} unknown, ${r.deepIndexed.length} deep indexed, ${r.linkedMissing.length} linked missing)`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch((e) => { console.error(`register-read: ${e.message}`); process.exit(1); });
}
