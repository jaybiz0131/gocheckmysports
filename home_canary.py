#!/usr/bin/env python3
"""home_canary.py: Sprint S-1 item 2, the home reduced (12 October 2026).

The home is the week board, the report slot and the footer, and nothing else. Each check
names the break it exists for and was seen red first (U-9).

  parts       the home renders the board, the report slot and the footer and nothing else
  removed     Storylines, From the desk, the Record and the Edition are absent before the footer
  nav         the header reads Week, Scores, Watch, Fantasy, Archive, About; the bar reads
              Week, Scores, Watch, Fantasy, More
  board       NFL and CFB only, once each, in kickoff order, tabs and windows from the manifest
  chips       the network chip and the first stream chip, finals in place of kickoffs
  scores      the Scores page keeps the NFL and CFB tabs and loses the rest
  archive     the Archive page lists the sections that left
  report      with this week's report written, the slot holds that report section and nothing
              else (S-2b item 3); with none, the slot is empty

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import datetime as _d
import os
import re

from truth_canary import read, visible


def _fixture(sb):
    ET = sb._ET

    def u(et):
        return _d.datetime.fromisoformat(et).replace(tzinfo=ET).astimezone(_d.timezone.utc)

    def g(lg, a, h, kick, st, net, sa=None, sh=None):
        return {"league": lg, "id": a + h, "state": st, "period": None, "status_short": "",
                "network": net,
                "start_utc": u(kick).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "away": {"abbr": a, "score": sa, "name": a, "full": a},
                "home": {"abbr": h, "score": sh, "name": h, "full": h}}
    nfl = [g("NFL", "DEN", "SEA", "2026-10-15T20:15", "pre", "Prime Video"),
           g("NFL", "LON", "PAR", "2026-10-18T09:30", "pre", "NFL Net"),
           g("NFL", "CHI", "GB", "2026-10-18T13:00", "pre", "FOX"),
           g("NFL", "LV", "NE", "2026-10-18T13:00", "pre", "CBS"),
           g("NFL", "LAC", "KC", "2026-10-18T16:25", "pre", "CBS"),
           g("NFL", "DAL", "PHI", "2026-10-18T20:20", "pre", "NBC"),
           g("NFL", "BUF", "MIA", "2026-10-19T20:15", "pre", "ESPN"),
           g("NFL", "MIN", "DET", "2026-10-13T20:15", "post", "FOX", "24", "16")]
    # kickoff order and id order disagree on purpose: the noon game sorts last by id
    cfb = [g("CFB", "TEX", "OKL", "2026-10-17T12:00", "pre", "ESPN"),
           g("CFB", "ALA", "LSU", "2026-10-17T19:30", "pre", "CBS")]
    nhl = [g("NHL", "BOS", "NYR", "2026-10-18T19:00", "pre", "ESPN+"),
           g("NBA", "LAL", "BOS", "2026-10-18T19:00", "pre", "TNT")]
    sbd = {"fetched_at": "2026-10-18T12:00:00Z",
           "leagues": [{"league": "NFL", "games": nfl}, {"league": "CFB", "games": cfb},
                       {"league": "NHL", "games": nhl[:1]}, {"league": "NBA", "games": nhl[1:]}]}
    nfl[-1]["away"]["record"], nfl[-1]["home"]["record"] = "1-4", "4-1"   # a finished game
    carr = lambda *n: [{"name": x, "market": "National", "type": "TV"} for x in n]
    w2w_games = [{"id": x["id"], "carriers": carr(x["network"]), "kickoff_utc": x["start_utc"]}
                 for x in nfl]
    w2w = {"fetched_at": "2026-10-18T12:00:00Z",
           "weeks": [{"season": 2026, "week": 6, "games": w2w_games,
                      "cfb_games": [{"id": x["id"], "carriers": carr(x["network"]),
                                     "kickoff_utc": x["start_utc"]} for x in cfb]}]}
    doc = {"schema": 1, "stale_days": 30, "rows": [
        {"id": "yt", "service": "YouTube TV", "leagues": ["NFL"],
         "match": {"networks": ["CBS", "FOX", "NBC"], "days": ["*"], "windows": ["*"]},
         "status": "ok", "verified": "2026-10-12"},
        {"id": "fubo", "service": "Fubo", "leagues": ["NFL"],
         "match": {"networks": ["ESPN"], "days": ["*"], "windows": ["*"]},
         "status": "verify", "verified": "2026-10-12"}]}
    return u, sbd, w2w, doc


def _intake_canary():
    """The Thursday game reaches the board (13 October 2026). The feed's default NFL slate
    still served week 5 at noon on Tuesday, so Seahawks at Broncos on Thursday night was in
    Where to Watch (which asks by day) and missing from the board (which asked once, for the
    default). The NFL read asks for each of the next seven days as well. A stub stands in for
    the feed: a default slate of week 5 and a dated answer for Thursday only."""
    import scoreboard as scb
    fails = []

    def ev(i, a, h, iso):
        return {"id": i, "date": iso, "status": {"type": {"state": "pre"}},
                "competitions": [{"competitors": [
                    {"homeAway": "home", "team": {"abbreviation": h, "id": "1"}},
                    {"homeAway": "away", "team": {"abbreviation": a, "id": "2"}}]}]}
    week5 = {"events": [ev("w5a", "BUF", "LAR", "2026-10-13T00:15Z")]}
    thu = {"events": [ev("w6a", "SEA", "DEN", "2026-10-16T00:15Z")]}
    asked = []

    def fake(url):
        asked.append(url)
        if "dates=20261015" in url:
            return thu
        if "dates=" in url:
            return {"events": []}
        return week5
    was = (scb._get, getattr(scb, "_week_days", None))
    try:
        scb._get = fake
        scb._week_days = lambda: ["20261013", "20261014", "20261015", "20261016",
                                  "20261017", "20261018", "20261019"]
        got = scb._league("NFL", "football/nfl", "nfl", {})
        ids = [g["id"] for g in got]
        if "w6a" not in ids:
            fails.append(f"intake: the Thursday game is not in the NFL read (got {ids}); "
                         "the default slate is not the week")
        if "w5a" not in ids:
            fails.append("intake: the default slate's own game was dropped")
        if len(ids) != len(set(ids)):
            fails.append(f"intake: a game id is read twice ({ids})")
        asked.clear()
        scb._get = lambda url: (_ for _ in ()).throw(OSError("down")) if "dates=" in url else week5
        ids = [g["id"] for g in scb._league("NFL", "football/nfl", "nfl", {})]
        if ids != ["w5a"]:
            fails.append("intake: a failed day read lost the default slate")
    finally:
        scb._get = was[0]
        if was[1] is None:
            if hasattr(scb, "_week_days"):
                del scb._week_days
        else:
            scb._week_days = was[1]
    return fails


def _record_gap(pages):
    """Run scripts/record-gap.mjs over rendered pages; its failures come back as strings."""
    import json
    import shutil
    import subprocess
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    node = shutil.which("node")
    if not node:
        return ["records: node is not installed, so the score and record gap was not measured"]
    tmp = tempfile.mkdtemp(prefix="record-gap-")
    try:
        for name, html in pages.items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                f.write(html)
        try:
            r = subprocess.run([node, os.path.join(here, "scripts", "record-gap.mjs"), tmp],
                               capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired:
            return ["records: the browser measure timed out"]
        out = []
        for line in r.stdout.splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if "fail" in o:
                out.append("records: " + o["fail"])
        if r.returncode != 0 and not out:
            out.append("records: the browser measure exited %d: %s" % (r.returncode, r.stderr[-200:]))
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _fade_canary(css=None):
    """S-2c item 2: the band's fade ends on the theme's paper. Every .sb-fade background in the
    shipped site.css ends on var(--paper); a fixed colour there ends it on one theme's paper in
    both, and the light one made a white bar across the dark home at 1440 (production 4f026ed)."""
    css = css if css is not None else open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                        "site", "assets", "site.css"), encoding="utf-8").read()
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    fails, n = [], 0
    for sel, decl in re.findall(r"([^{}]+)\{([^{}]*)\}", body):
        if ".sb-fade" not in sel or "gradient" not in decl:
            continue
        n += 1
        g = re.search(r"gradient\((.*)\)", decl, re.S)
        last = re.split(r",(?![^(]*\))", g.group(1))[-1].strip() if g else ""
        if not last.startswith("var(--paper)"):
            fails.append(f"home: the band's fade ({sel.strip()}) ends on {last!r}, not the theme's paper")
    if not n:
        fails.append("home: no .sb-fade gradient found in site.css")
    return fails


def home_canary():
    import build_manifest as bm
    import site_build as sb
    fails = []
    fails.extend(_intake_canary())
    fails.extend(_fade_canary())
    u, sbd, w2w, doc = _fixture(sb)
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD,
           sb.WX_DATA, sb._carriage.load, sb.EDITION_HREF, sb.CR_REPORTS)
    try:
        # S-2b item 3: the slot is empty with no report this week; a report is checked below
        sb.CR_REPORTS = []
        # Thursday 15 October 2026, 9:00 AM ET: the week board for week 6
        sb._NOW_CACHE = u("2026-10-15T09:00")
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.WX_DATA = sbd, w2w, True, None
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        sb.EDITION_HREF = "/edition/2026-10-14.html"
        sb._carriage.load = lambda: doc
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
        m = sb.MANIFEST
        home = sb.render_home([], "")
        scores = sb.render_scores_page(sbd, {}, "")
        archive = sb.render_archive([], "")

        # parts: the main holds the board and the empty slot, and nothing else
        main = re.search(r'<main[^>]*class="wrap"><section class="page">(.*?)</section></main>', home, re.S)
        if not main:
            fails.append("home: no main section found")
            return fails
        kids = re.findall(r'<div class="([^"]*)"', main.group(1))
        top = [k for k in kids if k.startswith(("scoreband scoreband-page wb-board", "cr-slot"))]
        if top != ["scoreband scoreband-page wb-board", "cr-slot"]:
            fails.append(f"home: the page body is {top}, expected the board then the report slot")
        slot = re.search(r'<div class="cr-slot"[^>]*id="conditions-report"[^>]*>(.*?)</div>', main.group(1), re.S)
        if not slot:
            fails.append("home: no empty slot named conditions-report")
        elif slot.group(1).strip():
            fails.append("home: the conditions report slot is not empty")
        if '<footer class="site">' not in home:
            fails.append("home: no footer")
        for cls in ("sp-lead", "bd-sec", "tracking", "lane-card", "sp-deskcard", "bd-card"):
            if f'class="{cls}' in main.group(1) or f' {cls} ' in main.group(1):
                fails.append(f"home: a {cls} block is still in the page body")

        # removed: before the footer, none of these appear
        before = home.split('<footer class="site">')[0]
        vis = visible(before)
        for word in ("From the desk", "Storylines", "The Record", "The Edition", "Edition",
                     "Tracking", "Read tonight"):
            if word in vis:
                fails.append(f"home: {word!r} is still on the page before the footer")
        foot = home.split('<footer class="site">')[1]
        for label in ("Storylines", "The Record", "The Edition"):
            if f">{label}</a>" not in foot:
                fails.append(f"home: the footer does not link {label}")

        # nav and bar as named
        nav = re.search(r'<nav class="mh-nav">(.*?)</nav>', home, re.S).group(1)
        labels = re.findall(r"<a [^>]*>([^<]*)</a>", nav)
        if labels != ["Week", "Scores", "Watch", "Fantasy", "Archive", "About"]:
            fails.append(f"home: the header reads {labels}")
        if "<details" in nav:
            fails.append("home: the header still has a More menu")
        bar = re.search(r'<nav class="tabbar"[^>]*>(.*?)</nav>', home, re.S).group(1)
        blabels = re.findall(r"<span>([^<]*)</span></a>", bar)
        if blabels != ["Week", "Scores", "Watch", "Fantasy", "More"]:
            fails.append(f"home: the phone bar reads {blabels}")

        # board: NFL and CFB only, once each, in kickoff order
        d = read(home)
        gids = d.units
        want = ["MINDET", "DENSEA", "TEXOKL", "ALALSU", "LONPAR", "CHIGB", "LVNE", "LACKC",
                "DALPHI", "BUFMIA"]
        if gids != want:
            fails.append(f"home: the board reads {gids}, expected {want}")
        if re.search(r'data-league="(NHL|NBA|MLB)"', home):
            fails.append("home: a card from a league the home no longer carries")
        # the tabs and windows come from the manifest
        tabs = re.findall(r'class="tk-tab wb-t[^"]*" data-day="([^"]*)"[^>]*>[^<]*(?:<small>(\d+)</small>)?', home)
        exp = [("all", ""), ("tue", "1"), ("thu", "1"), ("sat", "2"), ("sun", "5"), ("mon", "1")]
        # Tuesday's game (the finished MINDET) sits on Tuesday 13 Oct, before the Thursday
        if tabs != exp:
            fails.append(f"home: the day tabs read {tabs}, expected {exp} from the manifest")
        wins = re.findall(r'class="tk-tab" href="#win-([^"]*)">[^<]*<small>(\d+)</small>', home)
        if wins != [("early", "1"), ("1pm", "2"), ("late", "1"), ("night", "1")]:
            fails.append(f"home: the Sunday windows read {wins}")
        heads = re.findall(r'<h3 class="wb-wl" id="win-([^"]*)">', home)
        if heads != ["early", "1pm", "late", "night"]:
            fails.append(f"home: the Sunday window headings read {heads}")

        # chips: network, then the first stream; a final shows its score in place of a kickoff
        def card(gid):
            mm = re.search(r'<article[^>]*data-gid="%s".*?</article>' % gid, home, re.S)
            return mm.group(0) if mm else ""
        c = card("CHIGB")
        if "tk-stream" not in c or "YouTube TV" not in c:
            fails.append("home: the CHI at GB card has no first stream chip (YouTube TV)")
        if ">FOX<" not in c:
            fails.append("home: the CHI at GB card has no network chip")
        c = card("BUFMIA")
        if "tk-verify" not in c:
            fails.append("home: a game that matches only a verify row has no verify chip")
        c = card("MINDET")
        if "Final" not in visible(c) or "24" not in visible(c):
            fails.append("home: the finished game does not show Final and its score")
        c = card("LONPAR")
        if "tk-stream" in c:
            fails.append("home: a game that matches no carriage row shows a stream chip")

        # count and stamp are the manifest's
        mf = d.marks
        if ("count", bm.count_line(m, ["NFL", "CFB"])) not in mf:
            fails.append(f"home: the count reads {[x for x in mf if x[0] == 'count']}")

        # scores: NFL and CFB tabs only
        stabs = re.findall(r'class="tk-tab[^"]*" data-league="([^"]*)"', scores or "")
        if stabs != ["All", "NFL", "CFB"]:
            fails.append(f"scores: the tabs read {stabs}, expected All, NFL, CFB")
        if re.search(r'data-league="(NHL|NBA|MLB)"', scores or ""):
            fails.append("scores: a card from a league the page no longer carries")

        # records: a team's record is its own muted element with a clear gap from the score
        # (13 October 2026: "Buccaneers 241-4" at 390 was a score and a record run together)
        chips = re.findall(r'<span class="tk-sc">\d+</span></span><span class="tk-trec">[^<]+</span>', home)
        if not chips:
            fails.append("home: no finished card carries a record outside its score element")
        css = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "assets", "site.css"),
                   encoding="utf-8").read()
        rule = re.search(r"\.tk-chip-score \.tk-trec\{([^}]*)\}", css)
        if not rule:
            fails.append("home: no .tk-chip-score .tk-trec rule, so the record has no gap and no style of its own")
        else:
            body = rule.group(1)
            ml = re.search(r"margin-left:\s*(\d+(?:\.\d+)?)px", body)
            fs = re.search(r"font-size:\s*(\d+(?:\.\d+)?)px", body)
            al = re.search(r"color:\s*rgba\(255,\s*255,\s*255,\s*(0?\.\d+)\)", body)
            if not ml or float(ml.group(1)) < 8:
                fails.append(f"home: the record's gap from the score is {ml.group(1) + 'px' if ml else 'none'}, under 8px")
            if not fs or float(fs.group(1)) > 11:
                fails.append("home: the record is not set smaller than the score line (11px or less)")
            if not al or float(al.group(1)) > 0.7:
                fails.append("home: the record is not muted (white at 70 percent or less)")

        # records, measured: the same pages in a browser at seven widths in both modes, so a later
        # rule that shrinks the gap fails here and not in a reader's phone
        fails.extend(_record_gap({"home.html": home, "scores.html": scores}))

        # archive: the sections that left the home
        left = sb.archive_left_home()
        if left not in archive:
            fails.append("archive: the page does not carry the block of sections that left the home")
        archive = left       # the footer links Storylines too; only the block itself counts here
        for href in ("/news.html", "/keepers.html", "/edition/2026-10-14.html",
                     "/sections/nba.html", "/sections/nhl.html", "/sections/mlb.html",
                     "/sections/soccer.html", "/sections/wnba.html", "/sections/tennis.html",
                     "/sections/college-basketball.html", "/sections/more-sports.html",
                     "/sections/injuries.html", "/sections/transactions.html",
                     "/standings/nfl.html"):
            if f'href="{href}"' not in archive:
                fails.append(f"archive: no link to {href}")
    except Exception as e:
        import traceback
        fails.append(f"home: the fixture page raised {type(e).__name__}: {e} "
                     f"({traceback.format_exc().splitlines()[-3].strip()})")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD,
         sb.WX_DATA, sb._carriage.load, sb.EDITION_HREF, sb.CR_REPORTS) = was
    fails.extend(_report_slot_canary())
    return fails


def _report_slot_canary():
    """S-2b item 3: with this week's report written, the slot holds the report section and
    nothing else, and the body still holds the board and the slot only."""
    import build_manifest as bm
    import site_build as sb
    fails = []
    u, sbd, w2w, doc = _fixture(sb)
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD,
           sb.WX_DATA, sb._carriage.load, sb.EDITION_HREF, sb.CR_REPORTS)
    try:
        sb._NOW_CACHE = u("2026-10-15T09:00")
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.WX_DATA = sbd, w2w, True, None
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        sb.EDITION_HREF = "/edition/2026-10-14.html"
        sb._carriage.load = lambda: doc
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
        sb.CR_REPORTS = [{"id": "2026-10-15-thu", "title": "Conditions report, Thursday Oct 15",
                          "lead": "The weather touches 1 of the 6 games with a forecast.",
                          "written_at": "2026-10-15T11:17:00Z", "written_et": "Thu, Oct 15, 7:17 AM ET",
                          "flagged": [{"head": "Den at Sea, Thu 8:15 PM ET, Field.",
                                       "href": "/games/DENSEA.html"}],
                          "stamp": "Conditions by GoCheckMyWeather, from the National Weather Service."}]
        home = sb.render_home([], "")
        m = re.search(r'<div class="cr-slot"[^>]*id="conditions-report"[^>]*>(.*?)</div>\s*</section></main>',
                      home, re.S)
        inner = m.group(1).strip() if m else ""
        if not re.fullmatch(r'<section class="cr">.*</section>', inner, re.S) or inner.count("<section") != 1:
            fails.append("home: with this week's report, the slot does not hold exactly the report section")
        if "/conditions/2026-10-15-thu.html" not in inner or "Conditions report, Thursday Oct 15" not in inner:
            fails.append("home: the report in the slot has no title or no link to its page")
        before = home.split('<footer class="site">')[0]
        for word in ("From the desk", "Storylines", "The Record", "Read tonight"):
            if word in visible(before):
                fails.append(f"home: with a report, {word!r} is on the page before the footer")
    finally:
        (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.IA_BOARD,
         sb.WX_DATA, sb._carriage.load, sb.EDITION_HREF, sb.CR_REPORTS) = was
    return fails


def nav_consistency_scan(root):
    """The built tree: the header and the phone bar are the same on every page the build
    writes. 13 October 2026: Where to Watch was built before the inactives board loaded, so
    its header and bar had no Fantasy link while every other page had one."""
    import os
    fails = []
    pages = ["index.html", "scores.html", "where-to-watch.html", "fantasy/index.html",
             "archive.html", "about.html"]

    def nav(html):
        m = re.search(r'<nav class="mh-nav">(.*?)</nav>', html, re.S)
        b = re.search(r'<nav class="tabbar"[^>]*>(.*?)</nav>', html, re.S)
        return (re.findall(r"<a [^>]*>([^<]*)</a>", m.group(1)) if m else None,
                re.findall(r"<span>([^<]*)</span></a>", b.group(1)) if b else None)
    want = None
    for rel in pages:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            fails.append(f"nav: the built tree has no {rel}")
            continue
        got = nav(open(path, encoding="utf-8").read())
        if want is None:
            want = got
        elif got != want:
            fails.append(f"nav: {rel} has header {got[0]} and bar {got[1]}, the home has {want[0]} and {want[1]}")
    wk = [f for f in os.listdir(os.path.join(root, "where-to-watch")) if f.endswith(".html")] \
        if os.path.isdir(os.path.join(root, "where-to-watch")) else []
    for f in wk:
        got = nav(open(os.path.join(root, "where-to-watch", f), encoding="utf-8").read())
        if want is not None and got != want:
            fails.append(f"nav: where-to-watch/{f} has header {got[0]}, the home has {want[0]}")
    return fails


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    fs = home_canary()
    for f in fs:
        print("::error::" + f)
    print("HOME CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
