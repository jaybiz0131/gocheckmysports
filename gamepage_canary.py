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
            if blocks != ["indoor"] or "cxc-svg" in html or 'data-cx="forecast"' in html \
                    or re.search(r'<section class="bd-mod cx-block[^"]*"[^>]*>.*?\d+°', html, re.S):
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
        # Jack, 14 October 3:05 PM ET: the Ticket, the conditions hero, where to watch, then the
        # venue, designations and inactives; the Ticket itself carries no fact rows
        i_card = html.find('class="scoreband scoreband-page gp-head"')
        i_watch = html.find('class="bd-mod gp-watch"')
        i_cx = html.find('class="bd-mod cx-block')
        i_facts = html.find('class="tk-c gp-facts"')
        seq = [i for i in (i_card, i_cx, i_watch, i_facts) if i >= 0]
        if i_card < 0 or seq != sorted(seq):
            fails.append(f"game pages: {gid} is not Ticket, conditions, where to watch, then the facts")
        head = html[i_card:html.find("</article>", i_card)] if i_card >= 0 else ""
        if 'class="tk-spec"' in head:
            fails.append(f"game pages: {gid} still carries the venue and availability inside the Ticket")
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


def check_hero():
    """The hero on fixtures: the field, the arrows, the panels, the chart and the link."""
    import site_build as sb
    fails = []
    was = sb.CX_DATA
    g = {"id": "den", "away": {"color": "#002244"}, "home": {"color": "#FB4F14"}}
    quiet = {"wind": {"on": False, "max_mph": 12, "threshold_mph": 15}, "precip": {"on": False},
             "feels": {"on": False}, "alert": {"on": False}, "any": False}
    try:
        e = _hero_entry()
        noori = _hero_entry(stadium={"name": "Hard Rock Stadium", "orientation_deg": None}, flags=quiet)
        calm = _hero_entry(kickoff_hour=dict(e["kickoff_hour"], wind={"text": "Calm"}, wind_mph=0))
        gap = _hero_entry(kickoff_hour=dict(e["kickoff_hour"], temp_f=None, pop_pct=None))
        sb.CX_DATA = {"games": {"den": e, "mia": noori, "calm": calm, "gap": gap}}
        h = sb.cx_block(g)
        # field
        if 'data-cx-field="field"' not in h or 'rotate(20.0 ' not in h:
            fails.append("hero: the field is not drawn rotated to the stadium's orientation")
        if not re.search(r'<g class="cxf-n">.*?>N</text>', h):
            fails.append("hero: the field has no N mark")
        if 'fill="#002244"' not in h or 'fill="#FB4F14"' not in h:
            fails.append("hero: the end zones are not in the two teams' colours")
        # one family (Seattle and Denver navy): the home end zone takes the home alternate
        fam = {"away": {"color": "#002A5C", "alt_color": "#69BE28"}, "home": {"color": "#0A2343", "alt_color": "#FC4C02"}}
        if sb.cx_endzones(fam) != ("#002A5C", "#FC4C02"):
            fails.append(f"hero: one-family primaries do not take the home alternate: {sb.cx_endzones(fam)}")
        if sb.cx_endzones({"away": {"color": "#002244", "alt_color": "#69BE28"},
                           "home": {"color": "#FB4F14", "alt_color": "#0A2343"}}) != ("#002244", "#FB4F14"):
            fails.append("hero: distinct primaries were replaced by an alternate")
        if sb.cx_endzones({"away": {"color": "#002A5C"}, "home": {"color": "#0A2343"}}) != ("#002A5C", "#0A2343"):
            fails.append("hero: with no alternate in the feed the end zones are not left as the primaries")
        m = sb.cx_block(dict(g, id="mia"))
        if 'data-cx-field="compass"' not in m or "cxf-turf" in m or "cxf-yd" in m:
            fails.append("hero: a stadium with no orientation got a guessed field")
        # arrows
        a = re.search(r'<g class="cxf-arrows"[^>]*stroke="(#[0-9A-F]{6})"[^>]*rotate\((\d+) ', h)
        if not a or a.group(2) != "190" or len(re.findall(r"<path d=", h[h.find("cxf-arrows"):h.find("</g>", h.find("cxf-arrows"))])) != 3:
            fails.append("hero: the three arrows do not point the way the wind blows")
        elif a.group(1) != "#FFB03D":
            fails.append("hero: the wind flag is on and the arrows are not amber")
        ma = re.search(r'stroke="(#[0-9A-F]{6})"[^>]*transform="rotate\(190 66 66\)"', m)
        if not ma or ma.group(1) != "#EEF1F5":
            fails.append("hero: an unflagged compass arrow is not white at arrow_true_deg")
        c = sb.cx_block(dict(g, id="calm"))
        if "cxf-arrows" in c or "Calm" not in c:
            fails.append("hero: Calm draws arrows")
        # caption
        if '<span class="cxh-cap">Arrows point the way the wind blows</span>' not in h:
            fails.append("hero: the caption line is missing under the field")
        # panels
        ink = sb.cx_temp_ink(47)
        if f'<b class="cxh-big cx-glow" style="color:{ink}">47°</b>' not in h:
            fails.append("hero: the big temperature is not in the Weather ramp's ink")
        if "Down the field, gusting 23, up to 15 mph. From the north." not in h:
            fails.append("hero: the wind panel does not carry its words")
        if "up to 57% at 7 PM" not in h or 'class="cxh-tile cxh-w on"' not in h:
            fails.append("hero: the rain panel does not name its peak, or the wind panel is not lit")
        gp = sb.cx_block(dict(g, id="gap"))
        if gp.count(">missing<") < 2:
            fails.append("hero: a number the Worker did not give does not print as missing")
        # chart
        stops = re.findall(r'<stop offset="[.\d]+" stop-color="(#[0-9A-F]{6})"/>', h)
        if stops != [sb.cx_temp_ink(t) for t in (49, 47, 46, 45, 43, 42)]:
            fails.append("hero: the temperature line is not in each hour's ramp ink")
        if h.count('class="cxc-dot"') != 6:
            fails.append("hero: the chart does not draw a dot per hour")
        if 'class="cxc-win"' not in h or "Game window 8 PM to 12 AM" not in h:
            fails.append("hero: the game window is not a band over the game's hours")
        hot = re.findall(r'<text class="cxc-w on"[^>]*>(\d+)</text>', h)
        if hot != ["15", "12"]:
            fails.append(f"hero: the wind is amber at {hot}, not at or over the threshold")
        lab = re.search(r'<svg class="cxc-svg"[^>]*aria-label="([^"]+)"', h)
        if not lab or not all(f"{t} degrees, {p} percent rain, {w} mph" in lab.group(1)
                              for t, p, w in ((49, 57, 15), (42, 23, 5))) or lab.group(1).count("degrees") != 6:
            fails.append("hero: the chart's label does not carry every hour's numbers")
        # link
        lk = re.search(r'<a class="cxh-link" href="([^"]+)"><span>Full forecast for ([^<]+)<small>([^<]+)</small>', h)
        if not lk or not lk.group(1).startswith("https://gocheckmyweather.com/stadiums/") \
                or lk.group(3) != "Conditions by GoCheckMyWeather, NWS, 10:14 PM ET":
            fails.append("hero: the link card does not go to the stadium page with the credit and stamp")
        if 'class="bd-mod cx-block cx-hero cx-flag"' not in h:
            fails.append("hero: a flagged hero has no amber border")
        if "cx-flag" in m:
            fails.append("hero: an unflagged hero carries amber")
    finally:
        sb.CX_DATA = was
    return fails


def check_hero_css(css=None):
    """The desktop grid and the hero's contrast, from the shipped site.css."""
    import strip_canary as sc
    css = css if css is not None else open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                        "site", "assets", "site.css"), encoding="utf-8").read()
    fails = []
    if not re.search(r"@media \(min-width:900px\)\{[^@]*\.gp-grid\{display:grid;grid-template-columns:440px "
                     r"minmax\(0,1fr\)[^@]*\.gp-grid>\.cx-block\{grid-column:2;", css):
        fails.append("hero: the game page is not two columns with the hero on the right at 900px and up")
    # Jack, 14 October: the field column about 300px, the tiles the rest, the numerals at size
    if not re.search(r"@media \(min-width:900px\)\{[^@]*\.cx-hero\{grid-template-columns:minmax\(220px,300px\) "
                     r"minmax\(0,1fr\)", css):
        fails.append("hero: the desktop field column is not about 300px with the tiles taking the rest")
    nm = re.search(r"@media \(min-width:900px\)\{[^@]*\.cxh-big,\.cxh-t \.cxh-big\{font-size:clamp\(\d+px,[.\d]+vw,(\d+)px\)", css)
    if not nm or int(nm.group(1)) < 56:
        fails.append("hero: the desktop numerals are not at the design's size (56px or more)")
    hero = re.search(r"\.cx-hero\{background:(#[0-9A-Fa-f]{6})", css)
    if not hero:
        return fails + ["hero: the hero has no solid ground in site.css"]
    g0 = sc._rgb(hero.group(1))
    grounds = {"hero": g0, "a tile": sc._over((255, 255, 255, .035), g0),
               "a flagged tile": sc._over((255, 176, 61, .09), g0),
               "the rain panel": sc._over((142, 201, 232, .07), g0),
               "the game window": sc._over((61, 220, 132, .08), g0),
               "the link card": sc._over((121, 184, 190, .1), g0)}
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    n = 0
    for sel, decl in re.findall(r"([^{}]+)\{([^{}]*)\}", body):
        if not re.search(r"\.(cxh|cxc|cxf)-", sel):
            continue
        big = re.search(r"cxh-big", sel)
        texty = re.search(r"cxc-[thrw]\b|text", sel)
        for c in re.findall(r"(?:^|;)\s*(?:color|fill):\s*(#[0-9A-Fa-f]{6})" if texty
                            else r"(?:^|;)\s*color:\s*(#[0-9A-Fa-f]{6})", decl):
            n += 1
            for gname, g in grounds.items():
                r = sc.contrast(sc._rgb(c), g)
                if r < (3.0 if big else 4.5):
                    fails.append(f"hero contrast: {sel.strip()} {c} on {gname} is {r:.2f}:1")
    if n < 12:
        fails.append(f"hero contrast: only {n} hero text colours found in site.css")
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


def check_data_fresh(out):
    """W-45 (14 October 2026): the schedule and the scoreboard the build read are published at
    /data/, each with its own fetched_at, and neither is older than the build that published it
    (the manifest's started_utc). The repository's copies sat at Sunday night's poll for two days
    while the pages were fresh, because nothing but the inactives poller ever wrote them out."""
    import datetime as _d
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
        if t < t0:
            fails.append(f"data: /data/{name} was fetched {got}, before this build began at {started}")
    return fails


def gamepage_canary(out=None):
    if out is None:
        import verify_pipeline as vp
        out = vp._built_tree()
    if not out:
        return ["game pages: the gate's own build failed, so nothing was checked"]
    return check_data_fresh(out) + check_tree(out) + check_desk_tree(out) + check_verify() + check_hero() + check_hero_css() + check_desk()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("site", "publish")
    f = ((check_data_fresh(root) + check_tree(root) + check_desk_tree(root)) if root != "--fixtures" else []) + check_verify() \
        + check_hero() + check_hero_css() + check_desk()
    for x in f:
        print("FAIL", x)
    print("game page canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
