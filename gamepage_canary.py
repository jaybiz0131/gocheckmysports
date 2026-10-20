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

S-5.1 (the played game's page):
  played     once the game is Final the title, og:title, twitter:title and description are the
             result with the feed's real score, "<Away> <n>, <Home> <n>: final score. <Weekday>,
             <Month> <d>.", with no kickoff time, no conditions and no where to watch; a
             scheduled, live or postponed game's title is unchanged
  stamp      every game page carries exactly one "Updated" stamp, in the dateline's place

S-2c item 1 (the SportsGamePhone and SportsGameDesktop artboards, approved 14 October 2026):
  field      with an orientation, the field is drawn rotated to it, north up with an N mark, its
             end zones in the two teams' colours; with none, a compass rose and never a field
  arrows     three arrows (one on the compass) point the way the wind blows (arrow_true_deg),
             amber when the wind flag is on and white otherwise; Calm draws none
  caption    one line under the graphic: "Arrows point the way the wind blows"
  panels     the big temperature in the Weather ramp's ink, the wind with its words, the rain
             with its peak; a missing number prints as missing
  chart      the temperature line in each hour's ramp ink with a dot per hour, the game window
             as a green band, the wind amber at or over the Worker's threshold and only there,
             and an accessible label carrying every hour's numbers
  link       the link card goes to the Weather site's stadium page with the credit and stamp
  desktop    at 900px and up the page is two columns with the hero filling the right (CSS)
  contrast   every hero text colour clears 4.5:1 (3:1 at 24px and up) on the hero's grounds

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
# S-5.1: the played game's title, "Georgia 21, Auburn 17: final score. Saturday, October 17."
TITLE_FINAL = re.compile(r"^[^<>]+ \d+, [^<>]+ \d+: final score\. "
                         r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
                         r"(January|February|March|April|May|June|July|August|September|October|"
                         r"November|December) \d{1,2}\.$")


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
    try:
        scores = open(os.path.join(out, "scores.html"), encoding="utf-8").read()
    except OSError:
        scores = ""
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
        printable = e.get("status") in ("forecast", "indoor", "roofed", "outside_nws", "out_of_range")
        if printable and len(blocks) != 1:
            fails.append(f"game pages: {gid} ({e.get('status')}) has {len(blocks)} conditions blocks, not one")
        if not printable and blocks:
            fails.append(f"game pages: {gid} ({e.get('status')}) prints a conditions block")
        if len(re.findall(r'data-cx="', html)) > 1:
            fails.append(f"game pages: {gid} carries a second strip beside its block")
        if e.get("status") == "roofed":
            # S-3a (Jack, 15 October): a roofed stadium reads like a dome, with its own words
            if blocks != ["roofed"] or "sbg-hgrid" in html or 'data-cx-block="forecast"' in html \
                    or re.search(r'class="sbg-big">\d', html) or "Roof \u00b7" not in html:
                fails.append(f"game pages: {gid} has a roof and prints a forecast or no roof line")
        if e.get("status") == "indoor":
            if blocks != ["indoor"] or "sbg-hgrid" in html or 'data-cx-block="forecast"' in html \
                    or re.search(r'class="sbg-big">\d', html):
                fails.append(f"game pages: {gid} is indoor and prints a forecast")
        bad = runtime_hosts(html) - ALLOWED_HOSTS
        if bad:
            fails.append(f"game pages: {gid} reads {sorted(bad)} at runtime")
        t = re.search(r"<title>([^<]*)</title>", html)
        title = (t.group(1) if t else "").replace("&amp;", "&").replace("&#x27;", "'")
        played = "final score." in title
        if played:
            if not TITLE_FINAL.match(title):
                fails.append(f"game pages: {gid} title {title!r} is not the result")
        elif not TITLE.match(title):
            fails.append(f"game pages: {gid} title {title!r} is not the search")
        elif (e.get("league") == "NFL") != ("inactives" in title):
            fails.append(f"game pages: {gid} title names inactives wrongly for {e.get('league')}")
        if len(re.findall(r"Updated ", re.sub(r"<script.*?</script>", "", html, flags=re.S))) != 1:
            fails.append(f"game pages: {gid} does not carry exactly one Updated stamp")
        # S-2d item 1 (and Jack's S-2c order): the title, the one board with the weather right under
        # the matchup, the watch buttons and the Weather link, then where to watch, then the venue,
        # designations and inactives. The Ticket has left the page; no S-2c amber is on it.
        i_h1 = html.find('class="lx-h1 sbg-h1"')
        i_board = html.find('class="bd-mod sbc sbg')
        i_watch = html.find('class="bd-mod gp-watch"')
        i_facts = html.find('class="tk-c gp-facts"')
        seq = [i for i in (i_h1, i_board, i_watch, i_facts) if i >= 0]
        if i_h1 < 0 or i_board < 0 or seq != sorted(seq):
            fails.append(f"game pages: {gid} is not the title, the board, where to watch, then the facts")
        if 'class="scoreband scoreband-page gp-head"' in html or "cx-hero" in html:
            fails.append(f"game pages: {gid} still carries S-2c's Ticket or hero")
        if any(a in html.lower() for a in ("#ffb03d", "#ffcf86", "#ffe1b3")):
            fails.append(f"game pages: {gid} carries S-2c's amber")
        if html.count('class="bd-mod sbc sbg') != 1:
            fails.append(f"game pages: {gid} does not carry exactly one board")
        if f'href="/games/{gid}.html"' not in home:
            # S-3b.3: the home draws every NFL game and the FBS games that fit its byte budget
            # (site_build.HOME_BUDGET). A college game it left out is counted under its day, with
            # a link to Scores, and Scores must link its page. An NFL game is never left out.
            # The excuse is tied to the game's own day: that day's section carries a "more" line
            # (its count is at least the one game) and Scores links the page.
            kick = re.search(r'"startDate":"(\d{4}-\d\d-\d\d)T', html)
            sec = re.search(r'<section class="bd-mod wb-day"[^>]*data-date="%s">(.*?)</section>'
                            % re.escape(kick.group(1) if kick else "none"), home, re.S)
            more = re.search(r'<p class="bd-src wb-more">(\d+) more college game', sec.group(1)) if sec else None
            left_out = (e.get("league") == "CFB" and bool(more) and int(more.group(1)) >= 1
                        and f'href="/games/{gid}.html"' in scores)
            if not left_out:
                fails.append(f"game pages: the home's card for {gid} does not link its page, "
                             f"and the home does not say it left the game to Scores")
        if f"/games/{gid}.html" not in prio and f"/games/{gid}<" not in prio:
            fails.append(f"game pages: {gid} is not in the priority sitemap")
    for u in re.findall(r"<loc>[^<]*/games/([^<.]+)(?:\.html)?</loc>", every):
        if u not in games:
            fails.append(f"game pages: /games/{u} is in a sitemap and not on the board")
    if "CFB" not in leagues:
        print("::warning::game pages: no FBS game on this build's board")
    return fails


def _meta(html, attr, name):
    m = re.search(r'<meta %s="%s" content="([^"]*)"' % (attr, re.escape(name)), html)
    return (m.group(1) if m else "").replace("&amp;", "&").replace("&#x27;", "'")


def check_played():
    """S-5.1 on fixtures: a Final game's page leads with the result and a played or unplayed
    game's does not change; one Updated stamp per page, the later of the two times."""
    import datetime as _d
    import site_build as sb
    fails = []
    was = (sb.CX_DATA, sb._carriage.load, sb.W2W_DATA, sb.MANIFEST, sb._NOW_CACHE, sb.IA_DESIG,
           sb.IA_BOARD, sb.SB_DATA)
    pre = {"id": "pl1", "league": "CFB", "state": "pre", "start_utc": "2026-10-17T19:30Z",
           "venue": "Jordan-Hare Stadium", "network": "ESPN",
           "away": {"abbr": "UGA", "name": "Georgia", "record": "6-1"},
           "home": {"abbr": "AUB", "name": "Auburn", "record": "4-3"}}
    fin = dict(pre, state="post", status_short="Final",
               away=dict(pre["away"], score="21", periods=["7", "7", "0", "7"]),
               home=dict(pre["home"], score="17", periods=["3", "7", "0", "7"]))
    ppd = dict(pre, state="post", status_short="Postponed")
    noscore = dict(pre, state="post", status_short="Final")
    try:
        sb._NOW_CACHE = _d.datetime(2026, 10, 18, 13, 0, tzinfo=_d.timezone.utc)
        sb.MANIFEST = None
        sb.SB_DATA = {"fetched_at": "2026-10-18T12:00:00Z", "leagues": {}}
        sb.CX_DATA = {"games": {}}
        sb.W2W_DATA = {"weeks": []}
        sb.IA_BOARD = {"teams": [], "last_change": ""}
        want = "Georgia 21, Auburn 17: final score. Saturday, October 17."
        if sb.gp_page_title(fin) != want:
            fails.append(f"played: a Final game's title is {sb.gp_page_title(fin)!r}, not {want!r}")
        t = sb.gp_page_title(fin)
        if re.search(r"\d{1,2}:\d{2}|weather|where to watch|inactives| at ", t):
            fails.append(f"played: a Final game's title still names a kickoff time, conditions or where to watch: {t!r}")
        old = "Georgia at Auburn: weather, where to watch. Saturday 3:30 PM ET."
        if sb.gp_title(fin) != old:
            fails.append("played: a card's or a row's label (gp_title) changed for a Final game; only the page's title does")
        if sb.gp_page_title(pre) != old:
            fails.append(f"played: a scheduled game's title changed to {sb.gp_page_title(pre)!r}")
        if sb.gp_page_title(dict(pre, state="in")) != old:
            fails.append("played: a game in progress got the result title")
        if sb.gp_page_title(ppd) != old:
            fails.append("played: a postponed game got the result title")
        if sb.gp_page_title(noscore) != old:
            fails.append("played: a Final game with no score in the feed got a result title, a score made up")
        # the page: title, og:title, twitter:title and description agree; one Updated stamp
        later = "2026-10-18T14:00:00Z"
        for label, g, desig in (("final", fin, {"groups": {}, "last_poll": later}),
                                ("scheduled", pre, {"groups": {}, "last_poll": "2026-10-18T10:00:00Z"})):
            sb.IA_DESIG = desig
            html = sb.render_game_page(g, {}, {"teams": []}, None, [], "")
            title = (re.search(r"<title>([^<]*)</title>", html) or [None, ""])[1].replace("&amp;", "&")
            og, tw = _meta(html, "property", "og:title"), _meta(html, "name", "twitter:title")
            desc = _meta(html, "name", "description")
            if not (title == og == tw):
                fails.append(f"played: the {label} page's title, og:title and twitter:title differ: {title!r} {og!r} {tw!r}")
            if label == "final":
                if title != want:
                    fails.append(f"played: the Final page's title is {title!r}, not the result")
                if desc != want or _meta(html, "property", "og:description") != want \
                        or _meta(html, "name", "twitter:description") != want:
                    fails.append(f"played: the Final page's description does not match its title: {desc!r}")
                if re.search(r"weather|where to watch|forecast|kickoff", desc, re.I):
                    fails.append(f"played: the Final page's description promises conditions or where to watch: {desc!r}")
            else:
                if title != old or "where to watch" not in desc:
                    fails.append(f"played: the scheduled page's title or description changed: {title!r} {desc!r}")
            n = len(re.findall(r"Updated ", re.sub(r"<script.*?</script>", "", html, flags=re.S)))
            if n != 1:
                fails.append(f"played: the {label} page carries {n} Updated stamps, not one")
            if 'class="fx-asof"' in html:
                fails.append(f"played: the {label} page still carries the second stamp at the foot")
        # the one stamp is the later of the two times
        sb.IA_DESIG = {"groups": {}, "last_poll": later}
        html = sb.render_game_page(fin, {}, {"teams": []}, None, [], "")
        st = re.search(r'class="sb-stamp sbg-stamp"[^>]*>(Updated [^<]*)<', html)
        if not st or st.group(1) != "Updated Oct 18, 10:00 AM ET":
            fails.append(f"played: the one stamp is {st.group(1) if st else None!r}, not the later time, Oct 18, 10:00 AM ET")
        sb.IA_DESIG = {"groups": {}, "last_poll": "2020-01-01T00:00:00Z"}
        html = sb.render_game_page(fin, {}, {"teams": []}, None, [], "")
        st = re.search(r'class="sb-stamp sbg-stamp"[^>]*>(Updated [^<]*)<', html)
        if not st or st.group(1) != "Updated Oct 18, 8:00 AM ET":
            fails.append(f"played: with an older designations time the one stamp is {st.group(1) if st else None!r}, "
                         f"not the feed's Oct 18, 8:00 AM ET")
    finally:
        (sb.CX_DATA, sb._carriage.load, sb.W2W_DATA, sb.MANIFEST, sb._NOW_CACHE, sb.IA_DESIG,
         sb.IA_BOARD, sb.SB_DATA) = was
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


def _hero_entry(**kw):
    import conditions as cx
    hours = []
    for i, (t, p, w) in enumerate(((49, 57, 15), (47, 23, 12), (46, 23, 9), (45, 23, 7), (43, 23, 6), (42, 23, 5))):
        hours.append({"start": f"2026-10-15T{17 + i}:00:00-06:00", "end": f"2026-10-15T{18 + i}:00:00-06:00",
                      "temp_f": t, "pop_pct": p, "wind_mph": w, "is_daytime": False})
    e = {"status": "forecast", "roof": "open", "venue": "Empower Field at Mile High",
         "stadium": {"name": "Empower Field at Mile High", "orientation_deg": 20},
         "window": {"kickoff": "2026-10-16T00:15:00Z", "expected_end": "2026-10-16T03:30:00Z"},
         "kickoff_hour": dict(hours[1], feels_like_f=42, sky="Rain Showers", gust_mph=23, wind_dir="N",
                              precip_type="rain showers",
                              wind={"text": "12 mph down the field, gusting 23", "arrow_field_deg": 170,
                                    "arrow_true_deg": 190}),
         "hours": hours,
         "flags": {"wind": {"on": True, "max_mph": 15, "threshold_mph": 12},
                   "precip": {"on": False, "max_pct": 57, "threshold_pct": 60},
                   "feels": {"on": False}, "alert": {"on": False}, "any": True},
         "alerts": [], "stale": False,
         "credit": {"text": "Conditions by GoCheckMyWeather, NWS, 10:14 PM ET",
                    "url": "https://gocheckmyweather.com/stadiums/empower-field-at-mile-high.html"}}
    e.update(kw)
    e["words"] = cx.words(e)
    return e


def check_board():
    """S-2d item 1, the board on fixtures: the line score, the field, the plates, the words, the
    hours, the edge, the buttons and the Weather link."""
    import site_build as sb
    fails = []
    was = (sb.CX_DATA, sb._carriage.load, sb.W2W_DATA, sb.MANIFEST, sb._NOW_CACHE)
    g = {"id": "den", "league": "NFL", "state": "pre", "start_utc": "2026-10-16T00:15Z", "network": "Prime Video",
         "venue": "Empower Field at Mile High",
         "away": {"abbr": "SEA", "name": "Seahawks", "record": "3-2", "color": "#002244"},
         "home": {"abbr": "DEN", "name": "Broncos", "record": "3-2", "color": "#FB4F14"}}
    quiet = {"wind": {"on": False, "max_mph": 12, "threshold_mph": 15}, "precip": {"on": False},
             "feels": {"on": False}, "alert": {"on": False}, "any": False}
    try:
        import datetime as _d
        sb._NOW_CACHE = _d.datetime(2026, 10, 15, 13, 0, tzinfo=_d.timezone.utc)
        sb.MANIFEST = None
        e = _hero_entry()
        noori = _hero_entry(stadium={"name": "Hard Rock Stadium", "orientation_deg": None}, flags=quiet)
        calm = _hero_entry(kickoff_hour=dict(e["kickoff_hour"], wind={"text": "Calm"}, wind_mph=0), flags=quiet)
        gap = _hero_entry(kickoff_hour=dict(e["kickoff_hour"], temp_f=None, pop_pct=None))
        dome = {"status": "indoor", "venue": "Allegiant Stadium", "words": {"line": "Indoor", "roof": "Indoor"}}
        sb.CX_DATA = {"games": {"den": e, "mia": noori, "calm": calm, "gap": gap, "dome": dome}}
        h = sb.sbg_board(g)
        # the line score: the full form with an OT column, the abbreviations, empty before kickoff
        heads = re.findall(r'<span class="sbc-h( sbc-th)?">([^<]*)</span>', h)
        if [x for _c, x in heads] != ["", "1", "2", "3", "4", "OT", "T"]:
            fails.append(f"board: the line score heads are {[x for _c, x in heads]}, not 1 to 4, OT and T")
        if ">SEA</b>" not in h or ">DEN</b>" not in h or "3-2" not in h:
            fails.append("board: the line score does not name the teams by abbreviation with the record")
        if re.search(r'class="sbc-pl[^"]*">(?:<span class="tk-sc">)?\d', h):
            fails.append("board: a plate is filled before kickoff")
        fin = dict(g, state="post", status_short="Final",
                   away=dict(g["away"], score="20", periods=["7", "3", "0", "10"]),
                   home=dict(g["home"], score="17", periods=["0", "7", "7", "3"]))
        fh = sb.sbg_board(fin)
        vals = [v for v in re.findall(r'class="sbc-pl[^"]*"[^>]*>(?:<span class="tk-sc">)?([^<]*)<', fh)]
        if vals != ["7", "3", "0", "10", "", "20", "0", "7", "7", "3", "", "17"]:
            fails.append(f"board: a final's plates do not fill from the feed with OT empty: {vals}")
        # the meta row: the line with its provider (the 20 September law) and the network
        if 'class="sbg-meta"' not in h or 'class="sbg-net">Prime Video<' not in h:
            fails.append("board: the line and network row is missing")
        # the field
        if 'data-cx-field="field"' not in h or "rotate(20.0 " not in h:
            fails.append("board: the field is not drawn rotated to the stadium's orientation")
        if not re.search(r'<g class="cxf-n">.*?>N</text>', h):
            fails.append("board: the field has no N mark")
        if 'fill="#002244"' not in h or 'fill="#FB4F14"' not in h:
            fails.append("board: the end zones are not in the two teams' colours")
        fam = {"away": {"color": "#002A5C", "alt_color": "#69BE28"}, "home": {"color": "#0A2343", "alt_color": "#FC4C02"}}
        if sb.cx_endzones(fam) != ("#002A5C", "#FC4C02"):
            fails.append("board: one-family primaries do not take the home alternate")
        if sb.cx_endzones({"away": {"color": "#002244", "alt_color": "#69BE28"},
                           "home": {"color": "#FB4F14", "alt_color": "#0A2343"}}) != ("#002244", "#FB4F14"):
            fails.append("board: distinct primaries were replaced by an alternate")
        m = sb.sbg_board(dict(g, id="mia"))
        if 'data-cx-field="compass"' not in m or "cxf-turf" in m:
            fails.append("board: a stadium with no orientation got a guessed field")
        # the arrows: three, glowing yellow, the way the wind blows
        a = re.search(r'<g class="cxf-arrows"[^>]*stroke="(#[0-9A-F]{6})"[^>]*rotate\((\d+) ', h)
        seg = h[h.find("cxf-arrows"):h.find("</g>", h.find("cxf-arrows"))]
        if not a or a.group(2) != "190" or len(re.findall(r"<path d=", seg)) != 3 or a.group(1) != "#FFD23F" \
                or 'filter="url(#cxglow)"' not in seg[:200]:
            fails.append("board: the three glowing yellow arrows do not point the way the wind blows")
        if not re.search(r'stroke="#FFD23F"[^>]*transform="rotate\(190 66 66\)"', m):
            fails.append("board: the compass arrow is not yellow at arrow_true_deg")
        c = sb.sbg_board(dict(g, id="calm"))
        if "cxf-arrows" in c or 'class="sbg-big">Calm<' not in c:
            fails.append("board: Calm draws arrows or does not say Calm")
        if '<span class="cxh-cap">Arrows point the way the wind blows</span>' not in h:
            fails.append("board: the caption line is missing under the field")
        # the four plates
        keys = re.findall(r'<div class="sbg-p sbg-([twgr])( on)?"><span class="sbc-k">([A-Za-z]+)</span>'
                          r'<span class="sbg-big">([^<]*)', h)
        if [(k, l, v) for k, _o, l, v in keys] != [("t", "Temp", "47°"), ("w", "Wind", "12"), ("g", "Gust", "23"),
                                                     ("r", "Rain", "23%")]:
            fails.append(f"board: the plates are {keys}, not TEMP, WIND, GUST, RAIN with the kickoff numbers")
        if [o for _k, o, _l, _v in keys] != ["", " on", " on", ""]:
            fails.append("board: the wind flag does not light exactly the WIND and GUST plates")
        if "sbc-lit" not in h[:80] or "sbc-lit" in sb.sbg_board(dict(g, id="calm"))[:80]:
            fails.append("board: the edge is not yellow exactly when a flag is on")
        gp = sb.sbg_board(dict(g, id="gap"))
        if gp.count(">missing<") < 2 or re.search(r'class="sbg-big">0', gp):
            fails.append("board: a number the Worker did not give does not print as missing")
        # the words
        wd = re.search(r'<p class="sbg-words( on)?">([^<]+)</p>', h)
        if not wd or wd.group(1) != " on" or wd.group(2) != ("12 mph down the field, gusting 23, up to 15 mph. "
                                                            "Feels 42°, rain showers, rain up to 57% at 7 PM."):
            fails.append(f"board: the words line is {wd.groups() if wd else None}")
        if 'class="sbg-words on"' in c:
            fails.append("board: the words line is yellow with no wind flag")
        # by the hour
        hh = re.findall(r'<span class="sbg-hh( on)?">([^<]+)</span>', h)
        if [x for _o, x in hh] != ["7P", "8P", "9P", "10P", "11P", "12A"] or [o for o, _x in hh] != ["", " on", " on", " on", " on", ""]:
            fails.append(f"board: the hours are {hh}, not 7P to 12A with the game's hours lit")
        if h.count("sbg-hp sbg-g") != 12:
            fails.append("board: the game's hours are not framed in yellow on every row")
        hot = re.findall(r'<span class="sbg-hp[^"]*? on">(\d+)</span>', h)
        if hot != ["15", "12"]:
            fails.append(f"board: the wind is yellow at {hot}, not at or over the threshold")
        lab = re.search(r'class="sbg-hgrid" role="img" aria-label="([^"]+)"', h)
        if not lab or lab.group(1).count("degrees") != 6 or "49 degrees, 15 mph, 57 percent rain" not in lab.group(1):
            fails.append("board: the hours' label does not carry every hour's numbers")
        # a dome: one plate, no field, no hours, no numbers
        dm = sb.sbg_board(dict(g, id="dome"))
        if "Dome · No weather" not in dm or "cxf-svg" in dm or "sbg-hgrid" in dm or 'data-cx-block="indoor"' not in dm:
            fails.append("board: a dome is not one plate with no field and no hours")
        # under the board: the buttons and the Weather link
        doc = {"stale_days": 30, "rows": [
            {"id": "a", "service": "Prime Video", "label": "Prime Video", "leagues": ["NFL"],
             "match": {"networks": ["Prime Video"]}, "status": "ok", "verified": "2026-10-12", "source": "https://www.amazon.com/x"},
            {"id": "b", "service": "NFL+", "label": "NFL+ on a phone", "leagues": ["NFL"],
             "match": {"networks": ["*"]}, "status": "ok", "verified": "2026-10-12", "source": "https://www.nfl.com/plus/"},
            {"id": "c", "service": "Fubo", "label": "Fubo", "leagues": ["NFL"],
             "match": {"networks": ["Prime Video"]}, "status": "verify", "verified": "2026-08-01", "source": "https://fubo.tv/"}]}
        sb._carriage.load = lambda: doc
        sb.W2W_DATA = {"weeks": [{"games": [{"id": "den", "carriers": [{"name": "Prime Video"}]}]}]}
        u = sb.sbg_under(g)
        if '<a class="sbg-btn" href="https://www.amazon.com/x" rel="noopener">Watch on Prime Video</a>' not in u \
                or '<a class="sbg-btn sbg-btn2" href="https://www.nfl.com/plus/" rel="noopener">NFL+ on a phone</a>' not in u \
                or "Fubo" in u:
            fails.append("board: the yellow Watch button and the outlined second stream are not the table's in-date rows")
        doc["rows"] = [r for r in doc["rows"] if r["id"] != "b"]
        u1 = sb.sbg_under(g)
        if "Fubo" in u1 or "sbg-btn2" in u1:
            fails.append("board: a carriage row past its date became the second stream's button")
        lk = re.search(r'<a class="sbg-link" href="([^"]+)">Full forecast for ([^<]+) on GoCheckMyWeather<small>([^<]+)</small>', u)
        if not lk or not lk.group(1).startswith("https://gocheckmyweather.com/stadiums/") \
                or lk.group(3) != "Conditions by GoCheckMyWeather, NWS, 10:14 PM ET":
            fails.append("board: the Weather link does not go to the stadium page with the credit and stamp")
    finally:
        sb.CX_DATA, sb._carriage.load, sb.W2W_DATA, sb.MANIFEST, sb._NOW_CACHE = was
    return fails


def check_board_css(css=None):
    """The board's contrast on its own grounds, the kicker on each theme's paper, and the desktop
    grid, from the shipped site.css."""
    import strip_canary as sc
    css = css if css is not None else open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                        "site", "assets", "site.css"), encoding="utf-8").read()
    fails = []
    if not re.search(r"@media \(min-width:900px\)\{[^@]*\.gp-grid\{display:grid;grid-template-columns:minmax\(0,1fr\) "
                     r"\d+px;[^@]*\.gp-grid>\.sbg-col\{grid-column:1;", css):
        fails.append("board: at 900px and up the board does not fill the left column")
    on_plate = re.compile(r"sbg-big|sbg-hp|sbc-pl\b|sbc-team|sbc-one|sbc-miss")
    grounds = {"the panel": sc._rgb(sc.PANEL), "a plate": sc._rgb(sc.PLATE)}
    n = 0
    for sel, decl in sc._rules(css, r"\.sbg(?!-top|-stamp|-under|-btn|-link|-col|-kicker|-h1)"):
        if re.search(r"sbg-top|sbg-kicker|sbg-h1", sel):
            continue        # on the page's own paper; the kicker is measured per theme below
        texty = re.search(r"text", sel)     # a fill is a colour of text only on <text>; else a shape
        for c in re.findall(r"(?:^|;)\s*(?:color|fill):\s*(#[0-9A-Fa-f]{6})" if texty
                            else r"(?:^|;)\s*color:\s*(#[0-9A-Fa-f]{6})", decl):
            n += 1
            size = re.search(r"font-size:(\d+)px", decl)
            big = bool(size and int(size.group(1)) >= 24) or "sbg-big" in sel
            gs = {"a plate": grounds["a plate"]} if all(on_plate.search(p) for p in sel.split(",")) else grounds
            for gname, gr in gs.items():
                r = sc.contrast(sc._rgb(c), gr)
                if r < (3.0 if big else 4.5):
                    fails.append(f"board contrast: {sel} {c} on {gname} is {r:.2f}:1")
    if n < 10:
        fails.append(f"board contrast: only {n} board text colours found in site.css")
    papers = {"light": "#FBFAF6", "dark": "#131419"}
    lk = re.search(r"\.sbg-top p\.sbg-kicker\{[^}]*color:(#[0-9A-Fa-f]{6})", css)
    dk = re.search(r':root\[data-theme="dark"\] \.sbg-top p\.sbg-kicker\{color:(#[0-9A-Fa-f]{6})', css)
    if not lk or not dk:
        fails.append("board: the kicker has no colour for each theme")
    else:
        for theme, col in (("light", lk.group(1)), ("dark", dk.group(1))):
            r = sc.contrast(sc._rgb(col), sc._rgb(papers[theme]))
            if r < 4.5:
                fails.append(f"board contrast: the kicker {col} on the {theme} paper is {r:.2f}:1")
    btn = re.search(r"\.sbg-btn\{[^}]*background:var\(--sbc-yellow\);color:(#[0-9A-Fa-f]{6})", css)
    if not btn or sc.contrast(sc._rgb(btn.group(1)), sc._rgb("#FFD23F")) < 4.5:
        fails.append("board contrast: the Watch button's text does not clear 4.5:1 on yellow")
    return fails


def check_desk():
    """S-2c item 2: "From the desk" carries stories from the last seven days that name either
    team, and nothing when there are none."""
    import datetime as _d
    import site_build as sb
    fails = []
    was = sb._NOW_CACHE
    try:
        now = _d.datetime(2026, 10, 15, 13, 0, tzinfo=_d.timezone.utc)
        sb._NOW_CACHE = now
        z = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        g = {"league": "NFL", "away": {"name": "Seahawks"}, "home": {"name": "Broncos"}}
        old = {"slug": "s2c-desk-old", "league": "NFL", "published_utc": "2026-09-16T23:43:00Z",
               "title": "Seahawks rule out Sam Darnold for Week 2"}
        new = {"slug": "s2c-desk-new", "league": "NFL", "published_utc": z(now - _d.timedelta(days=2)),
               "title": "Broncos sign a kicker before Seahawks visit"}
        edge = {"slug": "s2c-desk-edge", "league": "NFL", "published_utc": z(now - _d.timedelta(days=8)),
                "title": "Broncos open the week with a walkthrough"}
        other = {"slug": "s2c-desk-other", "league": "NFL", "published_utc": z(now - _d.timedelta(days=1)),
                 "title": "Chiefs hold a closed practice"}
        got = [i["slug"] for i in sb.gp_desk_stories(g, [old, new, edge, other])]
        if got != ["s2c-desk-new"]:
            fails.append(f"game pages: From the desk carries {got}, not only the last week's story naming a team")
        if sb.gp_desk_stories(g, [old, edge, other]):
            fails.append("game pages: From the desk is not empty with no story from the last seven days")
    finally:
        sb._NOW_CACHE = was
    return fails


def check_desk_tree(out):
    """On the built tree: every From the desk row on a board page is dated within seven days of
    the build."""
    import datetime as _d
    fails = []
    cxp = os.path.join(out, "data", "conditions.json")
    if not os.path.exists(cxp):
        return ["game pages: the build published no /data/conditions.json, so From the desk was not checked"]
    d = json.load(open(cxp, encoding="utf-8"))
    built = _d.datetime.strptime(d["built_at"], "%Y-%m-%dT%H:%M:%SZ").date()
    for gid in sorted((d.get("games") or {})):
        fp = os.path.join(out, "games", f"{gid}.html")
        if not os.path.exists(fp):
            continue
        html = open(fp, encoding="utf-8").read()
        i = html.find('<span class="bd-eyebrow">From the desk</span>')
        if i < 0:
            continue
        sec = html[i:html.find("</section>", i)]
        for m in re.findall(r'<span class="bd-stamp">([A-Z][a-z]+ \d{1,2}, \d{4})', sec):
            day = _d.datetime.strptime(m, "%B %d, %Y").date()
            if (built - day).days > 7:
                fails.append(f"game pages: {gid} carries a From the desk story dated {m}, more than seven days old")
    return fails


FRESH_DATA = ("where-to-watch.json", "scoreboard.json")


def _refetch(name):
    """The gate's one retry of a feed (Jack, 14 October 2026): fetch again without writing the
    committed file. Returns the payload, or None when the feed fails again."""
    try:
        if name == "where-to-watch.json":
            import where_to_watch as m
        else:
            import scoreboard as m
        return m.refresh(check=True)
    except Exception as e:
        print(f"data: the gate's retry of {name} raised {type(e).__name__}")
        return None


def check_data_fresh(out, refetch=None):
    """W-45 (14 October 2026): the schedule and the scoreboard the build read are published at
    /data/, each with its own fetched_at, and neither is older than the build that published it
    (the manifest's started_utc). The repository's copies sat at Sunday night's poll for two days
    while the pages were fresh, because nothing but the inactives poller ever wrote them out.

    Jack, 14 October, 9:50 PM ET: a file older than the build is first read as the feed failing
    during the gate's own build (ESPN dropped one fetch on the night it shipped), so the gate
    fetches that feed once more. If the retry gets it, the check passes with a warning naming the
    first failure; if the retry fails too, it is red. It stays a hard check: a file the build did
    not publish, or a manifest with no started_utc, is red at once, because no retry explains it."""
    import datetime as _d
    refetch = refetch or _refetch
    fails = []
    mf = os.path.join(out, "build-manifest.json")
    started = (json.load(open(mf, encoding="utf-8")) if os.path.exists(mf) else {}).get("started_utc")
    if not started:
        return ["data: the manifest carries no started_utc, so the published data's age was not checked"]
    t0 = _d.datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ")
    for name in FRESH_DATA:
        fp = os.path.join(out, "data", name)
        if not os.path.exists(fp):
            fails.append(f"data: the build published no /data/{name}")
            continue
        got = (json.load(open(fp, encoding="utf-8")) or {}).get("fetched_at") or ""
        try:
            t = _d.datetime.strptime(got, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            fails.append(f"data: /data/{name} carries no readable fetched_at ({got!r})")
            continue
        if t >= t0:
            continue
        again = refetch(name) or {}
        try:
            t2 = _d.datetime.strptime(again.get("fetched_at") or "", "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            t2 = None
        if t2 and t2 >= t0:
            print(f"::warning::data: /data/{name} was fetched {got}, before this build began at {started}; "
                  f"the gate's one retry fetched it at {again.get('fetched_at')}, so the feed failed during the "
                  f"build and the build did not")
            continue
        fails.append(f"data: /data/{name} was fetched {got}, before this build began at {started}, "
                     f"and the gate's one retry failed too")
    return fails


def check_data_fresh_retry():
    """The retry on a fixture tree, with the feed stubbed: a stale file whose retry fails is red, a
    stale file whose retry succeeds is green, and a file the build did not publish is red even
    when a retry would succeed."""
    import shutil
    import tempfile
    fails = []
    t = tempfile.mkdtemp(prefix="w45-retry-")
    try:
        os.makedirs(os.path.join(t, "data"))
        json.dump({"started_utc": "2026-10-15T01:00:00Z"}, open(os.path.join(t, "build-manifest.json"), "w"))
        fresh = {"fetched_at": "2026-10-15T01:00:02Z"}
        stale = {"fetched_at": "2026-10-13T00:05:27Z"}
        json.dump(fresh, open(os.path.join(t, "data", "scoreboard.json"), "w"))
        json.dump(stale, open(os.path.join(t, "data", "where-to-watch.json"), "w"))
        later = {"fetched_at": "2026-10-15T01:04:00Z"}
        import contextlib
        import io
        # the fixture's own warning is not an annotation on a real run (CLAUDE.md: advisory
        # checks warn; deliberate fixture cases post nothing)
        with contextlib.redirect_stdout(io.StringIO()):
            return fails + _retry_cases(t, stale, later)
    finally:
        shutil.rmtree(t, ignore_errors=True)


def _retry_cases(t, stale, later):
    """The four retry cases on the fixture tree `t`."""
    fails = []
    if not check_data_fresh(t, refetch=lambda n: None):
        fails.append("data retry: a stale file whose retry failed passed")
    if not check_data_fresh(t, refetch=lambda n: stale):
        fails.append("data retry: a stale file whose retry came back stale passed")
    if check_data_fresh(t, refetch=lambda n: later):
        fails.append("data retry: a stale file whose retry succeeded is still red")
    os.remove(os.path.join(t, "data", "where-to-watch.json"))
    if not check_data_fresh(t, refetch=lambda n: later):
        fails.append("data retry: a file the build did not publish was excused by a retry")
    return fails


def gamepage_canary(out=None):
    if out is None:
        import verify_pipeline as vp
        out = vp._built_tree()
    if not out:
        return ["game pages: the gate's own build failed, so nothing was checked"]
    return check_data_fresh(out) + check_data_fresh_retry() + check_tree(out) + check_desk_tree(out) + check_verify() + check_played() + check_board() + check_board_css() + check_desk()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("site", "publish")
    f = ((check_data_fresh(root) + check_tree(root) + check_desk_tree(root)) if root != "--fixtures" else []) \
        + check_data_fresh_retry() + check_verify() + check_played() \
        + check_board() + check_board_css() + check_desk()
    for x in f:
        print("FAIL", x)
    print("game page canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
