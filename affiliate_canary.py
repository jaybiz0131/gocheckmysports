#!/usr/bin/env python3
"""affiliate_canary.py: S-3b item 2, the affiliate links and the line that says so.

Fixtures only: no network, no model. The fixture host is example.invalid, a name that cannot
resolve. Each check names the break it exists for and was seen red first (U-9).

  empty     an empty slot prints the service's plain link and the page carries no money line and
            no rel="sponsored"
  filled    a filled fixture slot prints its url on every renderer that prints a service (the
            where-to-watch page, the week board's stream chip, the game page's button and its watch
            block) with rel carrying sponsored and nofollow, and that page carries the money line
            exactly once
  other     on the same render, a service with no slot keeps its plain link and no sponsored rel,
            and a page that prints no affiliate link carries no money line
  file      data/affiliates.json holds the slots Fubo, Sling and Philo, every slot empty; no em dash
  tree      the gate's own build, while the file is empty: no page carries rel="sponsored", the money
            line, or the fixture host

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FIX = "https://example.invalid/aff/fubo?a=1&b=2"      # the ampersand proves the url is escaped
FIX_ESC = "https://example.invalid/aff/fubo?a=1&amp;b=2"
FIX_SLING = "https://example.invalid/aff/sling"
LINE = "How we make money"


def _fx_doc(aff_url):
    return {"schema": 1, "slots": [
        {"id": "fubo", "service": "Fubo", "names": ["Fubo"], "network": "Impact", "url": aff_url},
        {"id": "sling", "service": "Sling TV", "names": ["Sling TV", "Sling"], "network": "Impact",
         "url": FIX_SLING if aff_url else ""},
        {"id": "philo", "service": "Philo", "names": ["Philo"], "network": "Impact", "url": ""}]}


def _anchors(html):
    return re.findall(r"<a\b[^>]*>", html)


def _rel(tag):
    m = re.search(r'rel="([^"]*)"', tag)
    return set((m.group(1) if m else "").split())


def _spons(html):
    return [t for t in _anchors(html) if "sponsored" in _rel(t)]


def _renders(aff_url):
    """Render each service surface from fixtures with the given Fubo slot url."""
    import watch_canary as wc
    import strip_canary as st
    import site_build as sb
    import affiliates
    import build_manifest as bm
    u, week, doc = wc._fixture(sb)
    for r in doc["rows"]:
        r["source"] = "https://plain.example.invalid/" + r["id"]
        if r["id"] == "fubo":
            r["status"] = "ok"
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.MANIFEST, sb._carriage.load, sb.WX_DATA,
           sb.CX_DATA, affiliates.load)
    out = {}
    try:
        affiliates.load = lambda path=None: _fx_doc(aff_url)
        sb.SB_DATA, sb.W2W_DATA, sb.WX_DATA = None, {"weeks": [week]}, None
        sb._carriage.load = lambda: doc
        sb._NOW_CACHE = u("2026-10-13T09:00")
        sb.MANIFEST = bm.build(sb._build_now(), None, None)
        sb.CX_DATA = {"games": {}}
        out["w2w"] = sb.render_where_to_watch(week, [week], "", current=True)
        g = st._game("fox", network="FOX", start_utc="2026-10-18T17:00Z")
        out["game"] = sb.render_game_page(g, None, {}, {}, [], "Sunday")
        fubo_only = dict(doc, rows=[r for r in doc["rows"] if r["id"] == "fubo"])
        chip = sb._first_stream_chip(g, {"fox": [{"name": "FOX", "market": "National"}]}, fubo_only,
                                     datetime.date(2026, 10, 13))
        out["chip"] = chip
        out["chip_page"] = sb.shell("T", "d", "Home", "<main>" + chip + "</main>", "Sunday", path="/x.html")
        out["plain_page"] = sb.shell("T", "d", "Home", "<main><p>no service here</p></main>", "Sunday",
                                     path="/y.html")
        g2 = st._game("cbs", network="CBS", start_utc="2026-10-18T17:00Z")   # Paramount+ and YouTube TV
        out["nogame"] = sb.render_game_page(g2, None, {}, {}, [], "Sunday")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.MANIFEST, sb._carriage.load, sb.WX_DATA,
         sb.CX_DATA, affiliates.load) = was
    return out


def check_empty():
    fails = []
    r = _renders("")
    if "plain.example.invalid/fubo" not in r["game"]:
        fails.append("affiliates empty: the game page lost Fubo's plain link when its slot is empty")
    if "Fubo" not in r["w2w"] or "Fubo" not in r["chip"]:
        fails.append("affiliates empty: the where-to-watch page or the week board chip lost Fubo")
    for name in ("w2w", "game", "chip_page", "nogame"):
        h = r[name]
        if _spons(h):
            fails.append(f"affiliates empty: {name} carries rel sponsored with every slot empty")
        if LINE in h:
            fails.append(f"affiliates empty: {name} carries the money line with every slot empty")
        if "example.invalid/aff" in h:
            fails.append(f"affiliates empty: {name} prints an affiliate url with every slot empty")
    return fails


def check_filled():
    import affiliates
    fails = []
    r = _renders(FIX)
    for name in ("w2w", "game", "chip_page"):
        h = r[name]
        tags = [t for t in _anchors(h) if FIX_ESC in t]
        if not tags:
            fails.append(f"affiliates filled: {name} does not print the affiliate url on an anchor")
        for t in tags:
            if not {"sponsored", "nofollow"} <= _rel(t):
                fails.append(f"affiliates filled: {name} anchor lacks rel sponsored nofollow: {t}")
        if FIX in h:
            fails.append(f"affiliates filled: {name} prints the affiliate url unescaped")
        if affiliates.MONEY_LINE not in h:
            fails.append(f"affiliates filled: {name} prints an affiliate link and no money line")
        if h.count(LINE) != 1:
            fails.append(f"affiliates filled: {name} carries the money line {h.count(LINE)} times, not once")
    # the game page has two renderers: the Watch on buttons (the first two streams, Sling TV second,
    # whose label carries a parenthetical in the row) and the watch block (all three)
    sb_ = [t for t in _anchors(r["game"]) if "sbg-btn" in t]
    if not any(FIX_SLING in t and "sponsored" in _rel(t) for t in sb_):
        fails.append("affiliates filled: the game page's Watch on buttons do not carry the Sling TV affiliate url with rel sponsored")
    gs_ = [t for t in _anchors(r["game"]) if "gp-svc" in t]
    if not (any(FIX_ESC in t for t in gs_) and any(FIX_SLING in t for t in gs_)):
        fails.append("affiliates filled: the game page's watch block does not carry both affiliate urls")
    # other: every anchor that is not an affiliate one stays plain
    for name in ("w2w", "game", "chip_page"):
        for t in _spons(r[name]):
            if FIX_ESC not in t and FIX_SLING not in t:
                fails.append(f"affiliates other: {name} marks a non-affiliate anchor sponsored: {t}")
    if "plain.example.invalid/yt" not in r["game"]:
        fails.append("affiliates other: the game page lost YouTube TV's plain link")
    if LINE in r["plain_page"]:
        fails.append("affiliates other: a page with no affiliate link carries the money line")
    if _spons(r["nogame"]) or LINE in r["nogame"]:
        fails.append("affiliates other: a game with no affiliate service carries the money line or rel sponsored")
    return fails


def check_file():
    fails = []
    import affiliates
    raw = open(affiliates.PATH, encoding="utf-8").read()
    if chr(0x2014) in raw:
        fails.append("affiliates file: an em dash is in data/affiliates.json")
    try:
        doc = json.loads(raw)
    except ValueError:
        return fails + ["affiliates file: data/affiliates.json does not parse"]
    slots = {s.get("id"): s for s in doc.get("slots") or []}
    for want in ("fubo", "sling", "philo"):
        if want not in slots:
            fails.append(f"affiliates file: no slot for {want}")
    for i, s in slots.items():
        if "url" not in s or not s.get("names"):
            fails.append(f"affiliates file: slot {i} lacks url or names")
        if (s.get("url") or "") != "":
            fails.append(f"affiliates file: slot {i} is filled; Jack fills the file by ruling (J-3), "
                         f"and the tree check holds only while it is empty")
    return fails


def check_tree(out):
    import affiliates
    fails = []
    if any((s.get("url") or "") for s in (affiliates.load() or {}).get("slots") or []):
        return fails       # a filled file is check_file's failure, not a tree to scan
    for root, _d, files in os.walk(out):
        for f in files:
            if not f.endswith(".html"):
                continue
            h = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
            rel = os.path.relpath(os.path.join(root, f), out)
            if _spons(h):
                fails.append(f"affiliates tree: {rel} carries rel sponsored with every slot empty")
            if LINE in h:
                fails.append(f"affiliates tree: {rel} carries the money line with every slot empty")
            if "example.invalid" in h:
                fails.append(f"affiliates tree: {rel} carries the fixture host")
    return fails


def affiliate_canary(out=None):
    f = check_empty() + check_filled() + check_file()
    if out:
        f += check_tree(out)
    return f


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else None
    f = affiliate_canary(root)
    for x in f:
        print("FAIL", x)
    print("affiliate canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
