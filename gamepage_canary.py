#!/usr/bin/env python3
"""gamepage_canary.py: Sprint S-2b item 2, the game pages (Program 7, section 3).

Read from the gate's own throwaway tree (verify_pipeline._built_tree), never from a tree this
process did not build. The board's games are the keys of the tree's /data/conditions.json,
which the build writes for exactly the week board. Each check names the break it exists for and
was seen red first (U-9).

  built      every game on the week board has a page, NFL and FBS
  block      every board game page has exactly one conditions block (a forecast, or one
             "Indoor", "Outside NWS coverage" or "Forecast from" line), or none where the
             build holds nothing printable for the game (a missing venue)
  indoor     no page prints a forecast for an indoor venue: no strip numbers, no hourly line
  hosts      the only runtime hosts on a game page are the site's own and the conditions Worker
  title      the title is the search: "<Away> at <Home>: weather, where to watch[, inactives].
             <Weekday> <h:mm AM/PM> ET."
  order      above the fold: the Ticket, where to watch, the conditions, in that order
  linked     every card on the home links its game page
  sitemap    the board's game pages are in the priority sitemap; no other game page is in any
  verify     a carriage row past its date prints "verify" in the watch block, never the service

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import json
import os
import re

ALLOWED_HOSTS = {"gocheckmysports.com", "www.gocheckmysports.com",
                 "conditions.gocheckmybrands.workers.dev",
                 # Cloudflare Web Analytics, on every page of both sites since before 17 September
                 # (docs/HANDOFF-2026-09-17-to-22.md), rendered only when the Netlify environment
                 # carries its token. It reads no data for the page. The S-2b brief names only the
                 # site and the Worker; whether the beacon stays on game pages is Jack's call, put
                 # to him in the S-2b report. Named here so any OTHER host is still a red.
                 "static.cloudflareinsights.com"}
_RUNTIME = [
    re.compile(r'<script[^>]+src="(https?://[^"]+)"', re.I),
    re.compile(r'<img[^>]+src="(https?://[^"]+)"', re.I),
    re.compile(r'<iframe[^>]+src="(https?://[^"]+)"', re.I),
    re.compile(r'<link[^>]+rel="(?:stylesheet|preload|preconnect|dns-prefetch|modulepreload)"[^>]+href="(https?://[^"]+)"', re.I),
    re.compile(r'<link[^>]+href="(https?://[^"]+)"[^>]+rel="(?:stylesheet|preload|preconnect|dns-prefetch|modulepreload)"', re.I),
    re.compile(r'''fetch\(\s*["'`](https?://[^"'`]+)''', re.I),
    re.compile(r'''new\s+(?:EventSource|WebSocket)\(\s*["'`]((?:https?|wss?)://[^"'`]+)''', re.I),
    re.compile(r'''url\(\s*["']?(https?://[^"')]+)''', re.I),
]
TITLE = re.compile(r"^[^<>]+ at [^<>]+: weather, where to watch(, inactives)?\. "
                   r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) "
                   r"\d{1,2}:\d{2} (AM|PM) ET\.$")


def runtime_hosts(html):
    hosts = set()
    for rx in _RUNTIME:
        for u in rx.findall(html):
            m = re.match(r"^[a-z]+://([^/:]+)", u, re.I)
            if m:
                hosts.add(m.group(1).lower())
    return hosts


def check_tree(out):
    fails = []
    cxp = os.path.join(out, "data", "conditions.json")
    if not os.path.exists(cxp):
        return ["game pages: the build published no /data/conditions.json, so nothing below was checked"]
    games = (json.load(open(cxp, encoding="utf-8")) or {}).get("games") or {}
    if not games:
        print("::warning::game pages: the board holds no games this build; per-page checks not run")
        return fails
    home = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    prio = open(os.path.join(out, "sitemap-priority.xml"), encoding="utf-8").read()
    every = ""
    for n in ("sitemap-priority.xml", "sitemap-archive.xml", "news-sitemap.xml"):
        fp = os.path.join(out, n)
        every += open(fp, encoding="utf-8").read() if os.path.exists(fp) else ""
    leagues = set()
    for gid, e in sorted(games.items()):
        fp = os.path.join(out, "games", f"{gid}.html")
        if not os.path.exists(fp):
            fails.append(f"game pages: board game {gid} ({e.get('league')}) has no page")
            continue
        leagues.add(e.get("league"))
        html = open(fp, encoding="utf-8").read()
        blocks = re.findall(r'data-cx-block="([a-z]+)"', html)
        printable = e.get("status") in ("forecast", "indoor", "outside_nws", "out_of_range")
        if printable and len(blocks) != 1:
            fails.append(f"game pages: {gid} ({e.get('status')}) has {len(blocks)} conditions blocks, not one")
        if not printable and blocks:
            fails.append(f"game pages: {gid} ({e.get('status')}) prints a conditions block")
        if len(re.findall(r'data-cx="', html)) > 1:
            fails.append(f"game pages: {gid} carries a second strip beside its block")
        if e.get("status") == "indoor":
            if blocks != ["indoor"] or "hs-svg" in html or 'data-cx="forecast"' in html \
                    or re.search(r'<section class="bd-mod cx-block"[^>]*>.*?\d+°', html, re.S):
                fails.append(f"game pages: {gid} is indoor and prints a forecast")
        bad = runtime_hosts(html) - ALLOWED_HOSTS
        if bad:
            fails.append(f"game pages: {gid} reads {sorted(bad)} at runtime")
        t = re.search(r"<title>([^<]*)</title>", html)
        title = (t.group(1) if t else "").replace("&amp;", "&").replace("&#x27;", "'")
        if not TITLE.match(title):
            fails.append(f"game pages: {gid} title {title!r} is not the search")
        elif (e.get("league") == "NFL") != ("inactives" in title):
            fails.append(f"game pages: {gid} title names inactives wrongly for {e.get('league')}")
        i_card = html.find('class="scoreband scoreband-page gp-head"')
        i_watch = html.find('class="bd-mod gp-watch"')
        i_cx = html.find('class="bd-mod cx-block"')
        if i_card < 0 or (i_watch >= 0 and i_watch < i_card) or (i_cx >= 0 and i_watch >= 0 and i_cx < i_watch):
            fails.append(f"game pages: {gid} is not Ticket, where to watch, conditions")
        if f'href="/games/{gid}.html"' not in home:
            fails.append(f"game pages: the home's card for {gid} does not link its page")
        if f"/games/{gid}.html" not in prio and f"/games/{gid}<" not in prio:
            fails.append(f"game pages: {gid} is not in the priority sitemap")
    for u in re.findall(r"<loc>[^<]*/games/([^<.]+)(?:\.html)?</loc>", every):
        if u not in games:
            fails.append(f"game pages: /games/{u} is in a sitemap and not on the board")
    if "CFB" not in leagues:
        print("::warning::game pages: no FBS game on this build's board")
    return fails


def check_verify():
    """The watch block on a fixture: an ok row prints its service, a stale row prints verify."""
    import datetime as _d
    import site_build as sb
    fails = []
    doc = {"stale_days": 30, "rows": [
        {"id": "a", "service": "Prime Video", "label": "Prime Video", "leagues": ["NFL"],
         "match": {"networks": ["Prime Video"]}, "status": "ok", "verified": "2026-10-12",
         "source": "https://www.aboutamazon.com/x"},
        {"id": "b", "service": "Fubo", "label": "Fubo", "leagues": ["NFL"],
         "match": {"networks": ["Prime Video"]}, "status": "verify", "verified": "2026-10-12",
         "source": "https://help.fubo.tv/"}]}
    was = (sb._carriage.load, sb.W2W_DATA, sb.MANIFEST, sb._NOW_CACHE)
    try:
        sb._carriage.load = lambda: doc
        sb.W2W_DATA = {"weeks": [{"games": [{"id": "v1", "carriers": [{"name": "Prime Video"}]}]}]}
        sb.MANIFEST = None
        sb._NOW_CACHE = _d.datetime(2026, 10, 15, 13, 0, tzinfo=_d.timezone.utc)
        html = sb.gp_watch_block({"id": "v1", "league": "NFL", "start_utc": "2026-10-16T00:15Z",
                                  "network": "Prime Video"})
        if "Fubo" in html or '<span class="tk-chip tk-verify">verify</span>' not in html:
            fails.append("game pages: a verify row printed its service, or no verify chip")
        if 'href="https://www.aboutamazon.com/x"' not in html:
            fails.append("game pages: an ok row is not a button to its service's page")
    finally:
        sb._carriage.load, sb.W2W_DATA, sb.MANIFEST, sb._NOW_CACHE = was
    return fails


def gamepage_canary(out=None):
    if out is None:
        import verify_pipeline as vp
        out = vp._built_tree()
    if not out:
        return ["game pages: the gate's own build failed, so nothing was checked"]
    return check_tree(out) + check_verify()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("site", "publish")
    f = check_tree(root) + check_verify()
    for x in f:
        print("FAIL", x)
    print("game page canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
