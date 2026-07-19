#!/usr/bin/env python3
"""
aggregate.py: Stage 1, the intake.

Pull sports news from many sources on a schedule, normalize to one shape, dedupe
near-identical stories across outlets into clusters, and run the deterministic shill
pre-pass. Same pattern as the Storm ingest and the recall cross-reference: fetch, normalize,
write JSON; never runs in a browser.

SOURCES (config.json): keyless RSS feeds (official/primary + major outlets) always; the
legacy aggregator and X/Twitter gatherers only when their env token is set (absence is
documented, never a failure; both are dormant with no config keys). Official/primary
sources (league offices, official league data feeds) carry the highest source_tier and the
editor weights them most.

OUTPUT  out/items.json
  {
    "_meta": {...},
    "clusters": [
      { "id", "headline", "source", "source_tier", "url", "timestamp", "snippet",
        "reputation_weight", "shill_score", "shill_flags", "shill_rejected",
        "corroboration": [{name, tier, url}, ...] },
      ...
    ]
  }

FAIL POSTURE  A single feed that errors is a soft warning (::warning::) and is skipped; the
run continues on the feeds that resolved. If ZERO sources resolve, aggregate fails hard
(exit 2) so the orchestrator flags a human and nothing downstream runs on an empty intake.

USAGE
  python3 aggregate.py                 # fetch live feeds -> out/items.json
  python3 aggregate.py --fixture F     # read a saved RSS file instead of the network (tests)
  python3 aggregate.py --out PATH      # write somewhere other than out/items.json
"""

import json
import os
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import common
import shill

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
OUT_DIR = os.path.join(HERE, "out")
DEFAULT_OUT = os.path.join(OUT_DIR, "items.json")
UA = "GoCheckMySports-Aggregator/1.0 (+news pipeline)"

STOPWORDS = set(("the a an and or of to in on for with at by from as is are be into over "
                 "after amid its it new news says say will has have how why what when who "
                 "this that up down out plus vs more than about could would may can").split())


def gh(level, msg):
    """GitHub Actions annotation, also readable in a plain terminal."""
    print(f"::{level}::{msg}")


def load_config():
    return json.load(open(CONFIG, encoding="utf-8"))


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def norm_tokens(headline):
    words = re.sub(r"[^a-z0-9 ]+", " ", (headline or "").lower()).split()
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def _kw_re(keywords):
    """Word-boundary matcher for a keyword list ('fed' must not match 'federated')."""
    return re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keywords) + r")\b", re.I)


def narrative_watchlist(cfg):
    """[(name, compiled_regex), ...] for the ongoing-storyline watchlist (config.narratives)."""
    out = []
    for n in (cfg.get("narratives") or {}).get("watchlist", []):
        if n.get("keywords"):
            out.append((n.get("name", "?"), _kw_re(n["keywords"])))
    return out


def apply_keyword_gate(items, feed, watchlist):
    """Per-feed relevance gate for broad high-volume feeds (a whole-wire aggregator, all top
    stories): keep only items matching the feed's keywords in headline+snippet. A watchlist
    (narratives) match ALWAYS passes -- an ongoing desk storyline outranks the gate."""
    if not feed.get("keywords"):
        return items, 0
    rx = _kw_re(feed["keywords"])
    kept = []
    for it in items:
        text = f'{it.get("headline", "")} {it.get("snippet", "")}'
        if rx.search(text) or any(nrx.search(text) for _, nrx in watchlist):
            kept.append(it)
    return kept, len(items) - len(kept)


def parse_ts(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)  # RFC 822 (RSS pubDate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def _tag(el):
    return el.tag.split("}", 1)[-1].lower()


def parse_feed(xml_bytes, source_name, tier):
    """Parse an RSS 2.0 or Atom document into normalized items (best-effort, stdlib only)."""
    items = []
    root = ET.fromstring(xml_bytes)
    entries = [e for e in root.iter() if _tag(e) in ("item", "entry")]
    for e in entries:
        title = link = summary = pub = ""
        for child in e:
            t = _tag(child)
            if t == "title":
                title = strip_html("".join(child.itertext()))
            elif t == "link":
                link = (child.get("href") or child.text or "").strip()
            elif t in ("description", "summary", "content"):
                if not summary:
                    summary = strip_html("".join(child.itertext()))
            elif t in ("pubdate", "published", "updated", "date"):
                if not pub:
                    pub = (child.text or "").strip()
        if not title:
            continue
        ts = parse_ts(pub)
        items.append({
            "headline": title,
            "source": source_name,
            "source_tier": tier,
            "url": link,
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else "",
            "_ts": ts,
            "snippet": summary[:400],
        })
    return items


def fetch(url, is_json=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json" if is_json else "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = resp.read()
    return json.loads(data) if is_json else data


def gather_rss(cfg, fixture=None):
    items, ok_sources = [], 0
    feeds = cfg["sources"]["rss"]
    watchlist = narrative_watchlist(cfg)
    if fixture:
        # Offline test hook: run every configured feed's parser over one saved document,
        # so the dedupe/shill/gate wiring is exercised without the network.
        xml = open(fixture, "rb").read()
        for f in feeds:
            try:
                got = parse_feed(xml, f["name"], f["tier"])
                got, _ = apply_keyword_gate(got, f, watchlist)
                items += got
                ok_sources += 1
            except Exception as e:
                gh("warning", f"aggregate: fixture parse failed for {f['name']}: {e}")
        return items, ok_sources, len(feeds)
    for f in feeds:
        try:
            xml = fetch(f["url"])
            got = parse_feed(xml, f["name"], f["tier"])
            got, gated = apply_keyword_gate(got, f, watchlist)
            # Per-feed cap: one prolific outlet must not flood the editor (some feeds
            # return 100 items). Feeds are newest-first, so the cap keeps the newest.
            cap = cfg["sources"].get("max_items_per_feed", 40)
            trimmed = f" (capped from {len(got)})" if len(got) > cap else ""
            gate_note = f", {gated} gated off-topic" if gated else ""
            got = got[:cap]
            items += got
            ok_sources += 1
            print(f"  {f['name']:20s} [{f['tier']:8s}] -> {len(got)} item(s){trimmed}{gate_note}")
        except Exception as e:
            gh("warning", f"aggregate: source '{f['name']}' failed ({f['url']}): {e} -- skipped, run continues")
    return items, ok_sources, len(feeds)


def gather_cryptopanic(cfg):
    cp = cfg["sources"].get("cryptopanic", {})
    token = os.environ.get(cp.get("enabled_if_env", "CRYPTOPANIC_TOKEN"), "")
    if not token:
        print("  CryptoPanic          [aggregator] -> skipped (no CRYPTOPANIC_TOKEN; documented, not a failure)")
        return []
    params = dict(cp.get("params", {}))
    params["auth_token"] = token
    url = cp["url"] + "?" + urllib.parse.urlencode(params)
    try:
        data = fetch(url, is_json=True)
    except Exception as e:
        gh("warning", f"aggregate: CryptoPanic fetch failed: {e} -- skipped")
        return []
    out = []
    for p in data.get("results", []):
        ts = parse_ts(p.get("published_at", ""))
        out.append({
            "headline": strip_html(p.get("title", "")),
            "source": (p.get("source", {}) or {}).get("title", "CryptoPanic"),
            "source_tier": cp.get("tier", "aggregator"),
            "url": p.get("url", ""),
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else "",
            "_ts": ts,
            "snippet": "",
        })
    print(f"  CryptoPanic          [aggregator] -> {len(out)} item(s)")
    return out


def gather_x(cfg):
    """X / Twitter (breaking). Paid API; off unless X_BEARER_TOKEN is set. Not live-tested here."""
    x = cfg["sources"].get("x_twitter", {})
    token = os.environ.get(x.get("enabled_if_env", "X_BEARER_TOKEN"), "")
    if not token:
        print("  X / Twitter          [breaking  ] -> skipped (no X_BEARER_TOKEN; documented, not a failure)")
        return []
    params = {"query": x.get("query", "crypto -is:retweet lang:en"),
              "max_results": str(x.get("max_results", 25)),
              "tweet.fields": "created_at", "expansions": "author_id", "user.fields": "username"}
    url = x["url"] + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                   "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as e:
        gh("warning", f"aggregate: X fetch failed: {e} -- skipped")
        return []
    users = {u["id"]: u.get("username", "") for u in (data.get("includes", {}) or {}).get("users", [])}
    out = []
    for t in data.get("data", []):
        handle = users.get(t.get("author_id"), "")
        ts = parse_ts(t.get("created_at", ""))
        out.append({
            "headline": strip_html(t.get("text", ""))[:180],
            "source": f"X / @{handle}" if handle else "X",
            "source_tier": x.get("tier", "breaking"),
            "url": f"https://x.com/i/web/status/{t.get('id','')}",
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else "",
            "_ts": ts, "snippet": "",
        })
    print(f"  X / Twitter          [breaking  ] -> {len(out)} item(s)")
    return out


def within_lookback(items, hours):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    kept = []
    for it in items:
        ts = it.get("_ts")
        # Keep undated items (some feeds omit dates); the editor can weigh recency itself.
        if ts is None or ts >= cutoff:
            kept.append(it)
    return kept


def dedupe(items, cfg):
    """Greedy cluster of near-identical stories. Same URL, or headline-token Jaccard over the
    configured threshold, collapses into one cluster. The highest source_tier becomes the
    cluster's primary; the rest are corroboration (more corroboration -> more editorial weight)."""
    thr = cfg["dedupe"]["jaccard_threshold"]
    min_tok = cfg["dedupe"]["min_significant_tokens"]
    tier_rank = {"primary": 0, "breaking": 1, "major": 2, "onchain": 3, "aggregator": 4, "mixed": 5, "unknown": 6}

    for it in items:
        it["_tokens"] = norm_tokens(it["headline"])
    clusters = []  # each: {"members": [...], "urls": set()}
    for it in items:
        placed = False
        for cl in clusters:
            same_url = it["url"] and it["url"] in cl["urls"]
            sim = 0.0
            if len(it["_tokens"]) >= min_tok:
                base = cl["members"][0]["_tokens"]
                inter = len(it["_tokens"] & base)
                union = len(it["_tokens"] | base) or 1
                sim = inter / union
            if same_url or sim >= thr:
                cl["members"].append(it)
                if it["url"]:
                    cl["urls"].add(it["url"])
                placed = True
                break
        if not placed:
            clusters.append({"members": [it], "urls": {it["url"]} if it["url"] else set()})

    watchlist = narrative_watchlist(cfg)
    out = []
    for i, cl in enumerate(clusters):
        members = sorted(cl["members"], key=lambda m: (tier_rank.get(m["source_tier"], 9),
                                                       m.get("_ts") or datetime.min.replace(tzinfo=timezone.utc)))
        head = members[0]
        corro = [{"name": m["source"], "tier": m["source_tier"], "url": m["url"]} for m in members[1:]]
        c = {
            "id": f"c{i:03d}",
            "headline": head["headline"],
            "source": head["source"],
            "source_tier": head["source_tier"],
            "url": head["url"],
            "timestamp": head["timestamp"],
            "snippet": head["snippet"],
            "corroboration": corro,
            "corroboration_count": len(corro),
        }
        # Ongoing-storyline tag: any member matching a watchlist narrative marks the whole
        # cluster; the editor treats a tagged development as presumptively rank-worthy.
        text = " ".join(f'{m.get("headline", "")} {m.get("snippet", "")}' for m in members)
        tags = [name for name, rx in watchlist if rx.search(text)]
        if tags:
            c["narratives"] = tags
        out.append(c)
    return out


def run(fixture=None, out_path=DEFAULT_OUT):
    cfg = load_config()
    print(f"Aggregating (lookback {cfg['lookback_hours']}h)...")
    raw, ok, total = gather_rss(cfg, fixture=fixture)
    if not fixture:
        raw += gather_cryptopanic(cfg)
        raw += gather_x(cfg)

    if ok == 0 and not raw:
        gh("error", "aggregate: ZERO sources resolved -> failing hard (exit 2); nothing downstream runs on an empty intake.")
        return 2

    # Fixtures are wiring/canary inputs, not a live window: keep every item so the test is
    # deterministic regardless of the current date. Live runs apply the recency window.
    fresh = raw if fixture else within_lookback(raw, cfg["lookback_hours"])
    clusters = dedupe(fresh, cfg)
    rules = shill.load_rules()
    shill.annotate(clusters, rules)

    flagged = sum(1 for c in clusters if c["shill_score"] >= rules["thresholds"]["flag_score"])
    rejected = sum(1 for c in clusters if c["shill_rejected"])

    out = {
        "_meta": {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lookback_hours": cfg["lookback_hours"],
            "sources_ok": ok, "sources_total": total,
            "raw_items": len(raw), "fresh_items": len(fresh),
            "clusters": len(clusters), "shill_flagged": flagged, "shill_rejected": rejected,
            "stage": "1-aggregate",
            "note": "Rolling intake, not a complete archive. Deduped into clusters; shill pre-pass is a deterministic belt, the editor AI is the primary de-shill.",
        },
        "clusters": clusters,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {os.path.relpath(out_path)}  "
          f"({len(clusters)} clusters from {len(fresh)} fresh items; "
          f"{flagged} shill-flagged, {rejected} shill-rejected)")
    return 0


def main():
    args = sys.argv[1:]
    fixture = args[args.index("--fixture") + 1] if "--fixture" in args else None
    out_path = args[args.index("--out") + 1] if "--out" in args else DEFAULT_OUT
    sys.exit(run(fixture=fixture, out_path=out_path))


if __name__ == "__main__":
    main()
