#!/usr/bin/env python3
"""s60_canary.py: S-60, the scoreboard splits into Live, Upcoming and Final (21 November 2026).

Each case names the break it was seen red under (U-9); the breaks are in docs/REPORTS/S-60-REPORT.md.
The fixtures are the 20:43Z snapshot of Saturday 21 November (fixtures/s60-nov21-2043z.json, the
read behind the 3:43 PM ET page) and the conditions the published site held after it.

Called from verify_pipeline.layer1_canary(); returns a list of failure strings.
"""

import datetime as _d
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = _d.datetime(2026, 11, 21, 20, 43, 30, tzinfo=_d.timezone.utc)      # 3:43 PM ET
FETCHED = "2026-11-21T20:43:10Z"


def _g(i, st, short="", detail="0:00", per=0, kick="2026-11-21T17:00Z", lg="CFB", a="AAA", h="BBB",
       sa="0", sh="0", **kw):
    g = {"id": str(i), "league": lg, "state": st, "status_short": short, "detail": detail,
         "period": per, "start_utc": kick,
         "away": {"abbr": a, "name": a, "full": a, "score": sa, "rank": None},
         "home": {"abbr": h, "name": h, "full": h, "score": sh, "rank": None}}
    g.update(kw)
    return g


def _cases():
    import s60
    f = []

    def eq(name, got, want):
        if got != want:
            f.append(f"s60: {name}: got {got!r}, expected {want!r}")

    # part 2: one honest state word per card
    eq("live clock and period", s60.live_label(_g(1, "in", "5:53 - 2nd", "5:53", 2)), "5:53 2nd")
    eq("halftime", s60.live_label(_g(1, "in", "Halftime", "0:00", 2)), "Halftime")
    eq("end of quarter", s60.live_label(_g(1, "in", "End of 3rd", "0:00", 3)), "End 3rd")
    eq("overtime, no clock", s60.live_label(_g(1, "in", "OT", "0:00", 5)), "OT")
    eq("second overtime with a clock", s60.live_label(_g(1, "in", "2OT", "4:12", 6)), "2OT 4:12")
    eq("second overtime, the feed's no-clock card (BYU at Kansas)",
       s60.live_label(_g(1, "in", "2OT", "0:00", 6)), "2OT")
    eq("final", s60.final_label(_g(1, "post", "Final", per=4)), "Final")
    eq("final in two overtimes", s60.final_label(_g(1, "post", "Final/2OT", per=6)), "Final/2OT")
    eq("final with the time it was first seen", s60.final_label(
        _g(1, "post", "Final", per=4, final_seen_utc="2026-11-21T20:08:00Z")), "Final as of 3:08 PM ET")
    k = _g(1, "pre", "11/21 - 3:30 PM EST", kick="2026-11-21T20:30Z")
    eq("stale: kickoff 3:30, now 3:43, no state", s60.phase(k, NOW), "stale")
    eq("stale line", s60.card_line(k, NOW, "2026-11-21T20:11:00Z")[0],
       "No update since 3:11 PM ET, waiting for the feed")
    eq("not stale at nine minutes", s60.phase(_g(1, "pre", kick="2026-11-21T20:34:30Z"), NOW), "upcoming")
    eq("a kickoff to come is upcoming", s60.phase(_g(1, "pre", kick="2026-11-21T21:00Z"), NOW), "upcoming")

    # part 1: the order
    a = _g(1, "in", "10:00 - 3rd", "10:00", 3, kick="2026-11-21T17:00Z", a="AAA")
    b = _g(2, "in", "2:00 - 4th", "2:00", 4, kick="2026-11-21T20:00Z", a="BBB")
    c = _g(3, "in", "Halftime", "0:00", 2, kick="2026-11-21T17:30Z", a="CCC")
    got = [g["id"] for g in s60.order_live([a, b, c], NOW)]
    eq("live: least time remaining first (4th 2:00, 3rd 10:00, halftime)", got, ["2", "1", "3"])
    t1 = _g(4, "in", "9:00 - 3rd", "9:00", 3, kick="2026-11-21T19:00Z")
    t2 = _g(5, "in", "9:00 - 3rd", "9:00", 3, kick="2026-11-21T18:00Z")
    got = [g["id"] for g in s60.order_live([t1, t2], NOW, rank=lambda g: 1 if g["id"] == "4" else 30)]
    eq("live: a tie on time goes to the ranked team, then kickoff", got, ["4", "5"])
    got = [g["id"] for g in s60.order_live([t1, t2], NOW)]
    eq("live: no rank, a tie goes to the earlier kickoff", got, ["5", "4"])
    got = [g["id"] for g in s60.order_live([k, a], NOW)]
    eq("live: a stale game trails the games with clocks", got, [a["id"], k["id"]])
    p1, p2 = _g(6, "pre", kick="2026-11-21T23:00Z"), _g(7, "pre", kick="2026-11-21T21:00Z")
    eq("upcoming by kickoff", [g["id"] for g in s60.order_upcoming([p1, p2], NOW)], ["7", "6"])
    f1 = _g(8, "post", "Final", final_seen_utc="2026-11-21T19:00:00Z")
    f2 = _g(9, "post", "Final", final_seen_utc="2026-11-21T20:00:00Z")
    eq("final: newest first", [g["id"] for g in s60.order_final([f1, f2], NOW)], ["9", "8"])
    eq("default tab: a game on", s60.default_tab([a, p1, f1], NOW), "live")
    eq("default tab: before the first kickoff", s60.default_tab([p1, p2], NOW), "upcoming")
    eq("default tab: after the last final", s60.default_tab([f1, f2], NOW), "final")
    eq("default tab: only a stale game", s60.default_tab([k, f1], NOW), "live")

    # part 3: networks
    import networks
    eq("a bare feed code", networks.label("ERADM"), ("Check local listings", True))
    eq("the verify suffix", networks.label("ABCverify"), ("ABC", False))
    eq("a code with a mapping", networks.label("USA Net"), ("USA Network", False))
    eq("a name the table lacks prints as the feed gave it", networks.label("Big Ten Plus"),
       ("Big Ten Plus", False))
    import site_build as sb
    eq("network_name is the table", sb.network_name("ERADM"), "Check local listings")
    eq("network_name strips verify", sb.network_name("ABCverify"), "ABC")

    # part 5: weather absent
    far = _g(1, "pre", kick="2026-11-26T20:00Z")
    eq("weather, a dome", s60.weather_absent(_g(1, "pre", venue_indoor=True), None, NOW)[0], "Indoor")
    eq("weather, more than 48 hours out", s60.weather_absent(far, None, NOW)[0], "Conditions at kickoff")
    eq("weather, otherwise", s60.weather_absent(_g(1, "pre", kick="2026-11-21T21:00Z"), None, NOW),
       ("Conditions unavailable", "st-stale"))

    # a card with no entry, with an empty kickoff hour, and with one number missing: never "missing"
    sb._NOW_CACHE_KEEP = sb._NOW_CACHE
    sb._NOW_CACHE = NOW
    try:
        pre = _g(1, "pre", kick="2026-11-21T21:00Z")
        eq("no entry says why", "Conditions unavailable" in sb.sbc_weather(pre, None)[0], True)
        eq("a finished game with no entry prints nothing", sb.sbc_weather(_g(2, "post"), None)[0], "")
        empty = {"status": "forecast", "kickoff_hour": {}, "flags": {}, "words": {}}
        eq("an empty kickoff hour says why", "Conditions unavailable" in sb.sbc_weather(pre, empty)[0], True)
        part = {"status": "forecast", "kickoff_hour": {"temp_f": 61}, "flags": {}, "words": {}}
        h = sb.sbc_weather(pre, part)[0]
        eq("one number missing prints n/a, never the word missing", ("n/a" in h, "missing" in h.lower()), (True, False))
    finally:
        sb._NOW_CACHE = sb._NOW_CACHE_KEEP
        del sb._NOW_CACHE_KEEP

    # part 6: cadence
    import cadence
    eq("cadence on a Saturday", s60.cadence_line(5, cadence.EVERY_MIN), ", refreshed every 30 minutes")
    eq("cadence on a Tuesday", s60.cadence_line(1, cadence.EVERY_MIN), "")

    # the snapshot carries the time a game was first seen final
    prev = {"leagues": [{"league": "CFB", "games": [{"id": "1", "state": "post",
                                                    "final_seen_utc": "2026-11-21T19:00:00Z"}]}]}
    prev["leagues"][0]["games"].append({"id": "4", "state": "post"})
    cur = {"leagues": [{"league": "CFB", "games": [{"id": "1", "state": "post"}, {"id": "2", "state": "post"},
                                                  {"id": "3", "state": "in"}, {"id": "4", "state": "post"}]}]}
    s60.stamp_finals(cur, prev, "2026-11-21T20:43:10Z")
    gs = {x["id"]: x for x in cur["leagues"][0]["games"]}
    eq("stamp_finals keeps the first sight", gs["1"].get("final_seen_utc"), "2026-11-21T19:00:00Z")
    eq("stamp_finals stamps a new final", gs["2"].get("final_seen_utc"), "2026-11-21T20:43:10Z")
    eq("stamp_finals does not invent a time for a final it never saw finish", gs["4"].get("final_seen_utc"), None)
    eq("stamp_finals leaves a live game alone", gs["3"].get("final_seen_utc"), None)
    return f


def _render():
    """The Saturday page as the build renders it at 3:43 PM ET: (html, all pages)."""
    import site_build as sb
    sbd = json.load(open(os.path.join(HERE, "fixtures", "s60-nov21-2043z.json")))
    cx = json.load(open(os.path.join(HERE, "fixtures", "s60-nov21-conditions.json")))
    keep = (sb._NOW_CACHE, sb.SB_DATA, sb.CX_DATA, sb.MANIFEST)
    sb._NOW_CACHE, sb.SB_DATA, sb.CX_DATA, sb.MANIFEST = NOW, sbd, cx, None
    try:
        pages = sb.render_scores_pages(sbd, None, "Sat Nov 21")
    finally:
        sb._NOW_CACHE, sb.SB_DATA, sb.CX_DATA, sb.MANIFEST = keep
        sb._MF_PRIMED = None
    return pages


def _text(html):
    t = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def _page_cases():
    f = []
    pages = _render()
    day = pages.get("/scores/2026-11-21.html") or ""
    if not day:
        return ["s60: the Saturday page was not rendered"]
    if "/scores/2026-11-21-2.html" in pages or any(re.search(r"2026-11-21-\d", p) for p in pages):
        f.append("s60: the Saturday slate is still split into parts")
    if re.search(r"(?i)>\s*Part \d", day):
        f.append("s60: the page still carries a Part tab")
    # three state tabs with counts
    tabs = dict(re.findall(r'data-tab="(live|upcoming|final)"[^>]*>\s*[A-Za-z]+\s*<small>(\d+)</small>', day))
    want = {"live": "24", "upcoming": "23", "final": "11"}
    if tabs != want:
        f.append(f"s60: state tabs read {tabs}, expected {want} (23 on, LSU at Tennessee stale, 23 to come, 11 final)")
    # every game once, under its state
    panels = re.split(r'(?=<div class="sc-panel")', day)[1:]
    found = {}
    for p in panels:
        m = re.match(r'<div class="sc-panel"[^>]*data-panel="(\w+)"', p)
        if m:
            found[m.group(1)] = re.findall(r'<article[^>]*data-gid="(\d+)"', p)
    allg = [x for v in found.values() for x in v]
    if len(allg) != 58 or len(set(allg)) != 58:
        f.append(f"s60: the page renders {len(allg)} cards ({len(set(allg))} distinct), expected 58 once each")
    if {k: len(v) for k, v in found.items()} != {k: int(v) for k, v in want.items()}:
        f.append(f"s60: panel sizes {({k: len(v) for k, v in found.items()})} disagree with the tabs {want}")
    if not re.search(r'data-tab="live"[^>]*class="[^"]*\bon\b|class="[^"]*\bon\b[^"]*"[^>]*data-tab="live"', day):
        f.append("s60: Live is not the default tab with games on")
    # counts agree (part 4): All is the sum of the league tabs and the cards shown
    allc = re.search(r'data-league="All"[^>]*>\s*All\s*<small>(\d+)', day)
    lg = [int(n) for n in re.findall(r'class="tk-tab[^"]*"\s+data-league="(?:NFL|CFB)"[^>]*>[^<]*<small>(\d+)', day)]
    if not allc or int(allc.group(1)) != 58 or sum(lg) != 58:
        f.append(f"s60: All reads {allc and allc.group(1)}, league tabs sum to {sum(lg)}; 58 cards are shown (the feed holds 85 with NBA, NHL and Soccer)")
    # live ordering on the page: remaining time non-decreasing, stale last
    live = found.get("live") or []
    if not live or live[-1] != "401856754":
        f.append(f"s60: the stale game (LSU at Tennessee, 401856754) is not last in Live: {live[-3:]}")
    import s60
    byid = {str(g["id"]): g for L in json.load(open(os.path.join(HERE, "fixtures", "s60-nov21-2043z.json")))["leagues"]
            for g in L["games"]}
    rem = [s60.remaining(byid[i]) for i in live if not s60.is_stale(byid[i], NOW)]
    if rem != sorted(rem) or len(set(rem)) < 5:
        f.append(f"s60: Live is not ordered by least time remaining on the page: {rem[:8]}")
    txt = _text(day)
    if "No update since 3:43 PM ET, waiting for the feed" not in txt:
        f.append("s60: the stale card (LSU at Tennessee) does not read 'No update since 3:43 PM ET, waiting for the feed'")
    for bad in ("ERADM", "verify", "missing"):
        if re.search(bad, txt):
            f.append(f"s60: the rendered text of the Saturday page contains {bad!r}")
    if "Check local listings" not in txt:
        f.append("s60: ERADM is not rendered as Check local listings")
    if "Scores as of 3:43 PM ET, refreshed every 30 minutes" not in txt:
        f.append("s60: the stamp does not read 'Scores as of 3:43 PM ET, refreshed every 30 minutes'")
    if re.search(r"kickoff</", day) and re.search(r"Sat \d+:\d\d [AP]M ET kickoff", txt):
        f.append("s60: a final or live card still reads 'Sat 12:00 PM ET kickoff'")
    return f


def tree_scan(root):
    """The built site: no "verify" glued to or standing as a network chip, no bare feed code, no
    "missing" in a weather line. The word is read in visible text of the pages that print networks
    and weather (home, scores, week, where to watch, game pages)."""
    fails = []
    pages = 0
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            if not fn.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
            if not (rel in ("index.html", "scores.html", "where-to-watch.html") or rel.startswith(
                    ("scores/", "games/", "week/", "where-to-watch"))):
                continue
            pages += 1
            html = open(os.path.join(dp, fn), encoding="utf-8", errors="ignore").read()
            txt = _text(html)
            for m in re.finditer(r"(?i)\bverify\b|[A-Za-z+]verify\b", txt):
                fails.append(f"s60: {rel} prints 'verify' in reader text: ...{txt[max(0, m.start() - 30):m.end() + 20]!r}")
                break
            if re.search(r"\bERADM\b", txt):
                fails.append(f"s60: {rel} prints the bare feed code ERADM")
            for m in re.finditer(r'(?s)<[^>]*class="[^"]*(?:sbc-wx|sbc-wp|sbc-one|sbc-miss|cx-)[^"]*"[^>]*>.*?</', html):
                if re.search(r"(?i)\bmissing\b", m.group(0)):
                    fails.append(f"s60: {rel} prints 'missing' in a weather line")
                    break
    if pages < 3:
        fails.append(f"s60: the tree scan visited {pages} page(s), so it proves nothing")
    return fails


def s60_canary():
    fails = _cases()
    if not fails:
        fails.extend(_page_cases())
    return fails


if __name__ == "__main__":
    fs = s60_canary()
    for x in fs:
        print("::error::" + x)
    print("S-60 CANARY: " + ("FAIL" if fs else "PASS"), len(fs))
