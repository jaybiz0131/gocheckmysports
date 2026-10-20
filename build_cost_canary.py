#!/usr/bin/env python3
"""build_cost_canary.py: S-5.4, the build's cost after S-3b.3.

Four things the build spent that it did not need to, and one heading a sticky label sat on. Each
check names the break it exists for and was seen red first (U-9).

  worker   a game whose state is post is not asked of the Worker: /game is called for the games not
           yet over and for no other, a dome still reads Indoor, a final keeps the strip the last
           build published, and a final with none prints "over". Break: the post branch removed
           from conditions.refresh (every final is asked again, as it was).
  oneread  one dated FBS read answers both consumers: scoreboard.py and where_to_watch.py ask the
           feed for each (group, day) once per build, a day that failed is asked again by the
           second consumer, and outside a build scope nothing is cached. Break: common.read_once reading through.
  pages    scores.html is paged by day: every page under 150,000 bytes, every game on exactly one
           page, /scores.html still answers, the day pages are linked from each other. A budget
           lowered to 60,000 splits a day into parts and each part holds to it. Break: the pager
           returning the one page.
  tree     no built page is at or over 150,000 bytes. There is no exemption list.
  archive  archive.html and bottom-line.html are paged by bytes like Scores: every page under the
           line, every story and every edition on exactly one page, /archive.html and
           /bottom-line.html answering with the newest. Break: the pager never cutting.
  counts   every count on a Scores page is the manifest's (slate.week.days, slate.week.by_league),
           and a day the manifest does not hold prints no count at all.
  urls     a URL the site has published keeps answering: the opening day is also at
           /scores/<date>.html, a registry of published Scores paths only grows, and a path in it
           the build did not make gets an honest page.
  scroll   at 390, a jump to a Sunday window heading lands it clear of the sticky day label and the
           sticky nav. Break: the scroll-margin-top rule removed from the stylesheet.

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import datetime as _d
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BUDGET = 150000


def worker_unit():
    import conditions_canary as cc
    fails = []
    fin = dict(cc._game("fin", "NFL", "3937", "Empower Field at Mile High", "Denver", "CO"), state="post")
    fin2 = dict(cc._game("fin2", "CFB", "", "Memorial Stadium (Bloomington, IN)", "Bloomington", "IN"),
                state="post")
    domefin = dict(cc._game("domefin", "NFL", "3727", "Ford Field", "Detroit", "MI"), state="post")
    pre = dict(cc._game("pre", "NFL", "3812", "Lucas Oil Stadium", "Indianapolis", "IN"), state="pre")
    live = dict(cc._game("live", "CFB", "", "Memorial Stadium (Lincoln, NE)", "Lincoln", "NE"), state="in")
    answers = {
        "3937": (200, cc._forecast()),
        "3727": (200, {"venue": "3727", "league": "nfl", "roof": "indoor", "stadium": {"slug": "ford-field"}}),
        "3812": (200, cc._forecast(roof="open")),
        "3830": (200, cc._forecast()),
        "3834": (200, cc._forecast()),
    }
    old = {"status": "forecast", "words": {"temp": "61°"}, "league": "NFL"}
    p, calls, log = cc._run([fin, fin2, domefin, pre, live], answers, published={"fin": old})
    asked = sorted(c.split("venue=")[1].split("&")[0] for c in calls if c.startswith("/game"))
    if asked != ["3812", "3834"]:
        fails.append(f"worker: /game was asked for venues {asked}, expected only the two games not yet over "
                     "(3812 scheduled, 3834 in play)")
    G = p["games"]
    f = G.get("fin") or {}
    if f.get("status") != "forecast" or not f.get("record") or (f.get("words") or {}).get("temp") != "61°":
        fails.append(f"worker: a final with a published strip is {f.get('status')!r} {f.get('words')!r}, "
                     "expected the strip carried with record set")
    f2 = G.get("fin2") or {}
    if f2.get("status") != "over":
        fails.append(f"worker: a final with no published strip is {f2.get('status')!r}, expected 'over'")
    if (G.get("domefin") or {}).get("status") != "indoor":
        fails.append(f"worker: a finished dome game is {(G.get('domefin') or {}).get('status')!r}, expected 'indoor'")
    for k in ("pre", "live"):
        if (G.get(k) or {}).get("status") not in ("forecast", "roofed"):
            fails.append(f"worker: the game {k} is {(G.get(k) or {}).get('status')!r}; a game not over is still read")
    return fails


def oneread_unit():
    import common
    import fbs_canary as fb
    import scoreboard as scb
    import where_to_watch as w
    fails = []
    by_day, default = fb._fixture()
    week = {"games": [{"kickoff_utc": "2026-10-22T20:00Z"}]}      # its Tuesday is 20 October: the board's week
    was = (scb._get, w._get, getattr(scb, "_board_days", None))

    def dated(asked):
        return [u for u in asked if "groups=80" in u and "dates=" in u]

    def both(asked, **kw):
        feed = fb._feed(by_day, default, asked=asked, **kw)
        scb._get = feed
        w._get = feed
        scb._board_days = lambda now=None: list(fb.DAYS)
        s = scb._events("CFB", fb.PATH)
        k = w._cfb_week(week)
        return s, k

    try:
        asked = []
        common.once_begin()
        try:
            s, k = both(asked)
        finally:
            common.once_end()
        d = dated(asked)
        if len(d) != len(fb.DAYS) or len(set(d)) != len(d):
            fails.append(f"oneread: two consumers asked the dated FBS feed {len(d)} times for "
                         f"{len(set(d))} distinct urls; once per day is {len(fb.DAYS)}")
        if len(s) < fb.FBS_WEEK or not k:
            fails.append(f"oneread: the shared read starved a consumer (scoreboard {len(s)} events, "
                         f"where to watch {len(k)} games)")
        # a day that failed is not asked again by the second consumer
        asked = []
        common.once_begin()
        try:
            s, k = both(asked, fail_days=(fb.DAYS[4],))
        finally:
            common.once_end()
        d = dated(asked)
        if len(d) != len(fb.DAYS) + 1:
            fails.append(f"oneread: with one day failing the feed was asked {len(d)} times, expected "
                         f"{len(fb.DAYS) + 1} (the day that failed is asked again by the second consumer, "
                         "which gets its own chance; the six that answered are read once)")
        # outside a build nothing is held over: two standalone runs read twice
        asked = []
        both(asked)
        both(asked)
        if len(dated(asked)) != 4 * len(fb.DAYS):
            fails.append(f"oneread: outside a build scope the feed was asked {len(dated(asked))} times for "
                         f"four reads of seven days; a cache must not outlive the build")
    except Exception as e:
        fails.append(f"oneread: the check raised {type(e).__name__}: {e}")
    finally:
        scb._get, w._get = was[0], was[1]
        if was[2] is None:
            if hasattr(scb, "_board_days"):
                del scb._board_days
        else:
            scb._board_days = was[2]
        common.once_end()
    return fails


def _scores_fixture():
    """The scoreboard data for Thursday 22 October 2026: a full NFL Sunday and the whole FBS week."""
    import build_manifest as bm
    import fbs_canary as fb
    import scoreboard as scb
    import site_build as sb
    by_day, default = fb._fixture()
    was = (scb._get, getattr(scb, "_board_days", None))
    scb._get = fb._feed(by_day, default)
    scb._board_days = lambda now=None: list(fb.DAYS)
    try:
        cfb = scb._league("CFB", fb.PATH, "college-football", {})
    finally:
        scb._get = was[0]
        if was[1] is None:
            if hasattr(scb, "_board_days"):
                del scb._board_days
        else:
            scb._board_days = was[1]
    scb._get = lambda url: {"events": fb._nfl_games()}
    scb._week_days = lambda: []
    try:
        nfl = scb._league("NFL", "football/nfl", "nfl", {})
    finally:
        scb._get = was[0]
        del scb._week_days
    sbd = {"fetched_at": "2026-10-22T12:00:00Z",
           "leagues": [{"league": "NFL", "games": nfl}, {"league": "CFB", "games": cfb}]}
    w2w = {"fetched_at": "2026-10-22T12:00:00Z",
           "weeks": [{"season": 2026, "week": 7, "cfb_games": [],
                      "games": [{"id": g["id"], "carriers": [], "kickoff_utc": g["start_utc"]} for g in nfl]}]}
    return sbd, w2w, nfl, cfb


def pages_unit():
    import fbs_canary as fb
    import build_manifest as bm
    import site_build as sb
    fails = []
    sbd, w2w, nfl, cfb = _scores_fixture()
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.WX_DATA,
           sb._carriage.load, sb.BOARD_IDS, sb.CR_REPORTS, sb.EDITION_HREF)
    budget = getattr(sb, "SCORES_BUDGET", None)
    try:
        sb._NOW_CACHE = fb._clock().astimezone(_d.timezone.utc)
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.WX_DATA = sbd, w2w, True, None
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        sb._carriage.load = lambda: {"schema": 1, "stale_days": 30, "rows": []}
        sb.CR_REPORTS, sb.EDITION_HREF = [], "/edition/2026-10-21.html"
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
        sb.BOARD_IDS = {str(g.get("id")) for _k, g in sb.board_games(sbd) if g.get("id")}
        want_ids = sorted(str(g["id"]) for g in nfl + cfb)

        def check(label, pages, limit):
            if "/scores.html" not in pages:
                fails.append(f"pages ({label}): /scores.html is not among the pages ({sorted(pages)[:3]})")
                return
            for path, html in sorted(pages.items()):
                n = len(html.encode("utf-8"))
                if n >= limit:
                    fails.append(f"pages ({label}): {path} is {n} bytes, over the {limit}-byte budget")
            # /scores.html repeats the opening day's first page, so it is left out of the tally
            got = sorted(i for p, h in pages.items() if p != "/scores.html"
                         for i in re.findall(r'<article class="tk-c[^"]*" data-gid="([^"]*)"', h))
            if got != want_ids:
                fails.append(f"pages ({label}): the pages hold {len(got)} game cards ({len(set(got))} distinct), "
                             f"expected {len(want_ids)} once each")
            for path in pages:
                if not re.fullmatch(r"/scores\.html|/scores/\d{4}-\d{2}-\d{2}(-\d+)?\.html", path):
                    fails.append(f"pages ({label}): {path} is not a scores URL")
            days = {}
            for path in pages:
                m = re.fullmatch(r"/scores/(\d{4}-\d{2}-\d{2})\.html", path)
                if m:
                    days[m.group(1)] = path
            for path, html in pages.items():
                for dpath in days.values():
                    if f'href="{dpath}"' not in html:
                        fails.append(f"pages ({label}): {path} does not link {dpath}")
                        break
            # the tabs of every page are exactly All, then the leagues whose sections the page holds
            for path, html in pages.items():
                tabs = re.findall(r'class="tk-tab[^"]*" data-league="([^"]*)"', html)
                secs = [x.upper() for x in re.findall(r'<section class="bd-mod" id="(\w+)">', html)]
                if tabs != ["All"] + secs:
                    fails.append(f"pages ({label}): {path} has tabs {tabs} over sections {secs}")

        pages = sb.render_scores_pages(sbd, {}, "")
        check("shipped budget", pages, BUDGET)
        if len(pages) < 3:
            fails.append(f"pages: the week is {len(pages)} page(s); a Saturday of 44 games and a Sunday of 16 "
                         f"are separate days")
        one = sb.render_scores_page(sbd, {}, "")
        if one != pages.get("/scores.html"):
            fails.append("pages: render_scores_page is not /scores.html of the paged set")
        if budget is None:
            fails.append("pages: site_build has no SCORES_BUDGET, so the pager's limit is not a constant a test can move")
        sb.SCORES_BUDGET = 60000
        small = sb.render_scores_pages(sbd, {}, "")
        check("60000", small, 60000)
        if len(small) <= len(pages):
            fails.append(f"pages: a 60,000-byte budget gave {len(small)} pages, no more than the {len(pages)} "
                         "of the shipped budget, so a day was not split")
    except Exception as e:
        fails.append(f"pages: the fixture raised {type(e).__name__}: {e}")
    finally:
        if budget is not None:
            sb.SCORES_BUDGET = budget
        elif hasattr(sb, "SCORES_BUDGET"):
            del sb.SCORES_BUDGET
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.WX_DATA,
         sb._carriage.load, sb.BOARD_IDS, sb.CR_REPORTS, sb.EDITION_HREF) = was
    return fails


def tree_unit(tree):
    fails = []
    if not tree or not os.path.isdir(tree):
        return ["tree: the gate built no tree, so no page size was read"]
    seen = 0
    for root, _dirs, files in os.walk(tree):
        for f in files:
            if f.endswith(".html"):
                fp = os.path.join(root, f)
                n = os.path.getsize(fp)
                seen += 1
                if n >= BUDGET:
                    fails.append(f"tree: {os.path.relpath(fp, tree)} is {n} bytes, at or over {BUDGET}")
    if seen < 100:
        fails.append(f"tree: only {seen} pages were read; the size check would mean nothing")
    if not os.path.exists(os.path.join(tree, "scores.html")):
        fails.append("tree: /scores.html is not in the built tree; the URL must keep answering")
    return fails


def _num(t):
    m = re.search(r"\d+", t or "")
    return int(m.group(0)) if m else None


def counts_unit():
    """Every count on a Scores page is the manifest's; a day the manifest does not hold prints none."""
    import fbs_canary as fb
    import build_manifest as bm
    import site_build as sb
    fails = []
    sbd, w2w, nfl, cfb = _scores_fixture()
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.WX_DATA,
           sb._carriage.load, sb.BOARD_IDS, sb.CR_REPORTS, sb.EDITION_HREF)
    try:
        sb._NOW_CACHE = fb._clock().astimezone(_d.timezone.utc)
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.WX_DATA = sbd, w2w, True, None
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        sb._carriage.load = lambda: {"schema": 1, "stale_days": 30, "rows": []}
        sb.CR_REPORTS, sb.EDITION_HREF = [], "/edition/2026-10-21.html"
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
        mf = sb.MANIFEST
        wk = mf["slate"]["week"]
        mdays = {dd["date"]: dd["by_league"] for dd in wk["days"]}
        pages = sb.render_scores_pages(sbd, {}, "")
        held = set()
        for path, html in sorted(pages.items()):
            cur = re.search(r'<a class="tk-tab on" href="/scores/(\d{4}-\d{2}-\d{2})(?:-\d+)?\.html" aria-current', html)
            iso = cur.group(1) if cur else None
            if not iso:
                fails.append(f"counts: {path} marks no current day")
                continue
            by = mdays.get(iso)
            held.add(iso in mdays)
            rows = re.findall(r'<section class="bd-mod" id="(\w+)"><div class="tk-lg"><span>[^<]*</span><i></i>(?:<span class="tk-lg-n">([^<]*)</span>)?', html)
            for lg_id, txt in rows:
                lg = lg_id.upper()
                if by is None:
                    if txt:
                        fails.append(f"counts: {path} prints {txt!r} for {iso}, a day the manifest does not hold")
                    continue
                want_n = by.get(lg, 0)
                want_wk = (wk["by_league"].get(lg) or {}).get("total", 0)
                nums = [int(x) for x in re.findall(r"\d+", txt or "")]
                if iso == mf["date"]:
                    ok = bool(nums) and nums[1:] == [want_wk]
                else:
                    ok = nums == [want_n, want_wk]
                if not ok:
                    fails.append(f"counts: {path} league row {lg} reads {txt!r}, the manifest says {want_n} on {iso}, {want_wk} this week")
            cnt = re.search(r'data-mf="count">([^<]*)<', html)
            if by is None and cnt and cnt.group(1):
                fails.append(f"counts: {path} prints the count {cnt.group(1)!r} for {iso}, a day the manifest does not hold")
            if by is not None and iso != mf["date"]:
                tot = sum(by.get(l, 0) for l in sb.BOARD_LEAGUES)
                if not cnt or _num(cnt.group(1)) != tot:
                    fails.append(f"counts: {path} count line {cnt.group(1) if cnt else None!r}, the manifest says {tot} on {iso}")
            for href, small in re.findall(r'<a class="tk-tab[^"]*" href="/scores/(\d{4}-\d{2}-\d{2})\.html"[^>]*>[^<]*(?:<small>([^<]*)</small>)?', html):
                b2 = mdays.get(href)
                if b2 is None and small:
                    fails.append(f"counts: {path} day tab {href} prints {small!r}; the manifest does not hold that day")
                elif b2 is not None and _num(small) != sum(b2.get(l, 0) for l in sb.BOARD_LEAGUES):
                    fails.append(f"counts: {path} day tab {href} prints {small!r}, the manifest says {sum(b2.get(l, 0) for l in sb.BOARD_LEAGUES)}")
        if held != {True, False}:
            fails.append(f"counts: the fixture must hold days the manifest has and days it lacks (saw {sorted(held)})")
    except Exception as e:
        fails.append(f"counts: the fixture raised {type(e).__name__}: {e}")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.WX_DATA,
         sb._carriage.load, sb.BOARD_IDS, sb.CR_REPORTS, sb.EDITION_HREF) = was
    return fails


def urls_unit():
    """A published URL keeps answering: every day has its own URL on its own day, and the registry."""
    import fbs_canary as fb
    import build_manifest as bm
    import site_build as sb
    fails = []
    sbd, w2w, nfl, cfb = _scores_fixture()
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.WX_DATA,
           sb._carriage.load, sb.BOARD_IDS, sb.CR_REPORTS, sb.EDITION_HREF)
    try:
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.WX_DATA = sbd, w2w, True, None
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        sb._carriage.load = lambda: {"schema": 1, "stale_days": 30, "rows": []}
        sb.CR_REPORTS, sb.EDITION_HREF = [], "/edition/2026-10-21.html"
        from zoneinfo import ZoneInfo
        sets = {}
        for day in (22, 23, 24):
            sb._NOW_CACHE = _d.datetime(2026, 10, day, 9, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(_d.timezone.utc)
            sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
            sets[day] = set(sb.render_scores_pages(sbd, {}, ""))
        every = sets[22] | sets[23] | sets[24]
        for day, got in sets.items():
            gone = sorted(p for p in every if p.startswith("/scores/") and p not in got)
            if gone:
                fails.append(f"urls: on 2026-10-{day} the build does not write {gone[:2]}, which another day's build writes")
        # the registry only grows, and a path it holds that the build did not make gets a page
        got = sb.scores_registry_union(["/scores/2026-10-15.html", "/scores/2026-10-24-2.html"],
                                       ["/scores/2026-10-24.html", "/scores.html"])
        if got != ["/scores/2026-10-15.html", "/scores/2026-10-24-2.html", "/scores/2026-10-24.html"]:
            fails.append(f"urls: the registry union is {got}; it must keep the old paths, add the new, and leave /scores.html out")
        ph = sb.scores_placeholder("/scores/2026-10-15.html", "")
        main = re.search(r"<main.*?</main>", ph or "", re.S)
        txt = re.sub(r"<[^>]+>", " ", main.group(0) if main else "")
        if not ph or "October 15" not in txt or 'href="/scores.html"' not in ph or "noindex" not in ph:
            fails.append("urls: the page for a published day the build no longer holds is missing its date, its link to /scores.html or its noindex")
        if re.search(r"\d+ (game|on)", txt):
            fails.append("urls: the page for a day with no data prints a count")
        # a registered day the feed did not return, and that has not happened yet, never says it rolled off
        sb._NOW_CACHE = _d.datetime(2026, 10, 20, 20, 0, tzinfo=_d.timezone.utc)
        fut = sb.scores_placeholder("/scores/2026-10-25.html", "") or ""
        fm = re.search(r"<main.*?</main>", fut, re.S)
        ft = re.sub(r"<[^>]+>", " ", fm.group(0) if fm else "")
        if "rolled off" in ft or "no longer" in ft:
            fails.append("urls: the page for October 25, read on October 20, says its games have rolled off the board")
        if "could not" not in ft or "October 25" not in ft or 'href="/scores.html"' not in fut or "noindex" not in fut:
            fails.append("urls: the page for a future day the feed did not return must say the games could not be read, with its date and a link to /scores.html")
        if "rolled off" not in re.sub(r"<[^>]+>", " ", (re.search(r"<main.*?</main>", sb.scores_placeholder("/scores/2026-10-15.html", "") or "", re.S) or re.search("", "")).group(0)):
            fails.append("urls: a past day's page no longer says its games rolled off")
        # a past day still inside the board's week (Tuesday 6:00 AM ET on) that the build did not return
        # says it could not be read; "rolled off" is only for a day before the week start
        sb._NOW_CACHE = _d.datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(_d.timezone.utc)
        wk = sb.scores_placeholder("/scores/2026-10-21.html", "") or ""
        wm = re.search(r"<main.*?</main>", wk, re.S)
        wt = re.sub(r"<[^>]+>", " ", wm.group(0) if wm else "")
        if "rolled off" in wt or "no longer" in wt:
            fails.append("urls: the page for October 21, read on October 23 (inside the board's week), says its games have rolled off the board")
        if "could not" not in wt or "October 21" not in wt or 'href="/scores.html"' not in wk or "noindex" not in wk:
            fails.append("urls: the page for a past day inside the board's week the feed did not return must say the games could not be read, with its date and a link to /scores.html")
    except Exception as e:
        fails.append(f"urls: the fixture raised {type(e).__name__}: {e}")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD, sb.WX_DATA,
         sb._carriage.load, sb.BOARD_IDS, sb.CR_REPORTS, sb.EDITION_HREF) = was
    return fails


def archive_unit():
    """archive.html and bottom-line.html, paged by bytes."""
    import site_build as sb
    fails = []
    budget = getattr(sb, "PAGE_BUDGET", None)
    try:
        items = sb.load_content()
        live = [i for i in items if not i.get("example") and not i.get("superseded_by")]
        wraps = [i for i in items if sb._is_wrap(i) and i.get("bottom_line") and not i.get("example")]
        if len(live) < 100 or len(wraps) < 5:
            return [f"archive: the committed content holds {len(live)} stories and {len(wraps)} editions; too few to prove paging"]
        sb.PAGE_BUDGET = BUDGET
        for label, limit in (("shipped", BUDGET), ("60000", 60000)):
            sb.PAGE_BUDGET = limit
            for name, fn, base, units, pat, key in (
                    ("archive", sb.render_archive_pages, "/archive.html", live,
                     r'<article class="card">.*?<h3><a href="/articles/([^"]+)\.html"', "slug"),
                    ("bottom-line", sb.render_bottom_line_pages, "/bottom-line.html", wraps,
                     r'<a href="/articles/([^"]+)\.html">The full edition', "slug")):
                pages = fn(items, "")
                if base not in pages:
                    fails.append(f"archive ({label}): {base} is not among the pages")
                    continue
                for path, html in pages.items():
                    n = len(html.encode("utf-8"))
                    if n >= limit:
                        fails.append(f"archive ({label}): {path} is {n} bytes, over {limit}")
                    if path != base and not re.fullmatch(base[:-5] + r"/page/\d+\.html", path):
                        fails.append(f"archive ({label}): {path} is not a page of {base}")
                got = sorted(x for h in pages.values() for x in re.findall(pat, h, re.S))
                want = sorted(i["slug"] for i in units)
                if got != want:
                    fails.append(f"archive ({label}): {name} pages hold {len(got)} entries ({len(set(got))} distinct), expected {len(want)} once each")
                if name == "archive" and label == "shipped" and len(pages) < 2:
                    fails.append(f"archive ({label}): {len(live)} stories fit on one page; the fixture proves nothing")
                if label == "60000" and len(pages) < 2:
                    fails.append(f"archive ({label}): {name} stayed one page under a 60,000-byte budget")
                newest = (pages.get(base) or "")
                if want and sorted(units, key=lambda i: i.get("published_utc") or i.get("date") or "", reverse=True)[0]["slug"] not in newest:
                    fails.append(f"archive ({label}): {base} does not carry the newest {name} entry")
        if budget is None:
            fails.append("archive: site_build has no PAGE_BUDGET constant a test can move")
    except Exception as e:
        fails.append(f"archive: the check raised {type(e).__name__}: {e}")
    finally:
        if budget is not None:
            sb.PAGE_BUDGET = budget
        elif hasattr(sb, "PAGE_BUDGET"):
            del sb.PAGE_BUDGET
    return fails


def scroll_unit():
    """The Sunday window headings under the sticky day label, at 390: scripts/heading-clear.mjs
    over a hand-made Sunday week, through the real reader and the real render."""
    import json
    import shutil
    import subprocess
    import tempfile
    import fbs_canary as fb
    node = shutil.which("node")
    if not node:
        return ["scroll: node is not installed, so the heading was not measured"]
    sun = [fb._ev("s1", "20261025", "1300"), fb._ev("s2", "20261025", "1625"), fb._ev("s3", "20261025", "2020")]
    html = fb._week_home([("NFL", "football/nfl", sun)])
    tmp = tempfile.mkdtemp(prefix="cost-scroll-")
    try:
        with open(os.path.join(tmp, "home.html"), "w", encoding="utf-8") as f:
            f.write(html)
        try:
            r = subprocess.run([node, os.path.join(HERE, "scripts", "heading-clear.mjs"), tmp],
                               capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired:
            return ["scroll: the browser measure timed out"]
        out = []
        for line in r.stdout.splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if "fail" in o:
                out.append("scroll: " + o["fail"])
        if r.returncode != 0 and not out:
            out.append("scroll: the browser measure exited %d: %s" % (r.returncode, r.stderr[-200:]))
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_cost_canary(tree=None):
    fails = []
    for name, fn in (("worker", worker_unit), ("oneread", oneread_unit), ("pages", pages_unit),
                     ("counts", counts_unit), ("urls", urls_unit), ("archive", archive_unit),
                     ("scroll", scroll_unit)):
        try:
            fails.extend(fn())
        except Exception as e:
            fails.append(f"{name}: raised {type(e).__name__}: {e}")
    if tree is not None:
        fails.extend(tree_unit(tree))
    return fails


if __name__ == "__main__":
    f = build_cost_canary()
    for x in f:
        print("FAIL", x)
    print("build cost canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
