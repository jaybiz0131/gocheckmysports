#!/usr/bin/env python3
"""strip_canary.py: the conditions on every card. S-2b item 1 built the strip, S-2c item 0 made it
the three-tile HUD, and S-2d item 0 (Jack's ruling of 14 October 2026, 3:11 PM ET, the scoreboard
row of the "Game Day Weather Looks" canvas, ScoreboardBoard.dc.html) makes every card on the week
board a small scoreboard.

Each check names the break it exists for and was seen red first (U-9).

  contrast   every text colour the shipped site.css gives the scoreboard (.sbc*, the day tabs)
             clears 4.5:1, or 3:1 at 24px and up, on the panel, the frame and a plate. The boards
             are solid green in both themes, so these are the only grounds. Glow is never counted.
  yellow     the yellow-bulb rule, which replaces S-2c's amber rule: a yellow glow, or yellow on a
             number, a bulb or the words line, only on a selector that needs a flag (.on,
             .sbc-lit) or on the active day (.tk-tab.on); S-2c's amber appears on no card rule
  linescore  the day's first card (the Ticket) carries quarters 1 to 4 and a yellow T; the rest the
             total only; OT only when the feed says overtime
  empty      a plate is empty until the feed has its number: no score before kickoff, no quarter
             from a half-filled feed, never a 0 the feed did not give
  final      a final's plates fill from the feed's periods and score; the loser's total dims and
             the winner's stays cream; the weather plates stay as the record
  plates     the weather plates are TEMP, WIND, RAIN in that order, labelled, with the feel, the
             gust and the window's peak under each (the peak only when higher)
  bulbs      four bulbs, WIND, RAIN, COLD or HEAT, ALERT; each lit by its own flag and no other;
             COLD under a 60°F kickoff feel, HEAT at 60 and over
  edge       a lit bulb lights the plate that matters and the board's yellow edge; no flag, no
             yellow
  words      the words line is yellow only with the wind flag, and carries the credit, linked to
             the Weather stadium page
  arrow      the wind arrow points the way the wind blows (arrow_true_deg); Calm draws none
  missing    a number the Worker did not give prints as missing
  unchecked  alerts null prints "Alerts not checked"
  single     a dome is one plate, "Dome · No weather", with no number; a retractable roof keeps
             the plates and adds a ROOF plate; outside NWS coverage is one plate with the city
  sprite     the arrow is drawn once per page and placed with <use>
  font       Oswald is self-hosted woff2, weights 500 to 700, and is the file the subset script
             made from OSWALD_TEXT
  tree       on the gate's own build: every board card is a scoreboard, each day's first card the
             Ticket and the rest compact; no S-2c amber anywhere on the home; every character set
             in Oswald on the home is one the subset carries

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import hashlib
import importlib.util
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL, FRAME, PLATE = "#0E3B2A", "#072619", "#141A17"
YELLOW = ("#ffd23f", "#ffe680", "255,210,63")
AMBER = ("#ffb03d", "#ffcf86", "#ffe1b3", "255,176,61")


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _over(top, ground):
    *c, a = top
    return tuple(round(x * a + y * (1 - a)) for x, y in zip(c, ground))


def _lum(c):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _css():
    return open(os.path.join(HERE, "site", "assets", "site.css"), encoding="utf-8").read()


def _rules(css, rx=r"\.sbc|\.wb-tabs"):
    """(selector, body, root vars) for every rule naming the scoreboard."""
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    root = {}
    for b in re.findall(r":root\{([^{}]*)\}", body):
        for k, v in re.findall(r"(--[a-z-]+):\s*([^;]+)", b):
            root[k] = v.strip()
    out = []
    for sel, decl in re.findall(r"([^{}@]+)\{([^{}]*)\}", body):
        sel = sel.strip()
        if re.search(rx, sel):
            decl = re.sub(r"var\((--[a-z-]+)\)", lambda m: root.get(m.group(1), m.group(0)), decl)
            out.append((sel, decl))
    return out


def check_contrast(css=None):
    css = css if css is not None else _css()
    fails = []
    grounds = {"the panel": _rgb(PANEL), "the frame": _rgb(FRAME), "a plate": _rgb(PLATE)}
    on_plate = re.compile(r"sbc-pl\b|sbc-big|sbc-chip|sbc-one|sbc-team|wb-tabs \.tk-tab|sbc-miss")
    n = 0
    for sel, decl in _rules(css):
        for c in re.findall(r"(?:^|;)\s*color:\s*(#[0-9A-Fa-f]{6})", decl):
            n += 1
            size = re.search(r"font-size:(\d+)px", decl)
            big = bool(size and int(size.group(1)) >= 24) or re.search(r"sbc-big", sel)
            # a plate's own text sits on the plate and nowhere else; the rest on all three
            gs = {"a plate": grounds["a plate"]} if all(on_plate.search(p) for p in sel.split(",")) else grounds
            for gname, g in gs.items():
                r = contrast(_rgb(c), g)
                if r < (3.0 if big else 4.5):
                    fails.append(f"strip contrast: {sel} {c} on {gname} is {r:.2f}:1")
    if n < 14:
        fails.append(f"strip contrast: only {n} scoreboard text colours found in site.css")
    return fails


def check_rules(css=None):
    """The yellow-bulb rule, read from the shipped CSS."""
    css = css if css is not None else _css()
    fails = []
    rules = _rules(css)
    if len(rules) < 30:
        fails.append(f"strip rules: only {len(rules)} scoreboard rules found in site.css")
    for sel, decl in rules:
        low = decl.lower().replace(" ", "")
        if any(a in low for a in AMBER):
            fails.append(f"strip rules: S-2c amber on '{sel}', which retired with the scoreboard look")
        glow = re.findall(r"(?:text-shadow|box-shadow|filter):([^;]+)", low)
        lit_glow = any(any(y in g for y in YELLOW) for g in glow) or ("drop-shadow" in low and ".on" in sel)
        yellow_ink = re.search(r"(?:^|;)color:(#ffd23f|#ffe680)", low)
        for part in sel.split(","):
            part = part.strip()
            needs_flag = re.search(r"sbc-big|sbc-bulb|sbc-words|sbc-pl|sbc-arw|sbc-wp", part)
            flagged = re.search(r"\.on\b|\.sbc-lit|\.tk-tab\.on|:hover", part)
            if lit_glow and not flagged:
                fails.append(f"strip rules: a yellow glow on '{part}', which needs a flag")
            if yellow_ink and needs_flag and not flagged:
                fails.append(f"strip rules: yellow on '{part}', which needs a flag")
    return fails


def _font_script():
    spec = importlib.util.spec_from_file_location("oswald_subset", os.path.join(HERE, "scripts", "oswald_subset.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def check_font(css=None):
    css = css if css is not None else _css()
    fails = []
    m = re.search(r"@font-face\{font-family:'Oswald';font-style:normal;font-weight:(\d+) (\d+);\s*"
                  r"font-display:swap;src:url\('(/assets/fonts/[a-z0-9-]+\.woff2)'\) format\('woff2'\)\}", css)
    if not m:
        return ["font: no self-hosted woff2 @font-face for Oswald in site.css"]
    if (m.group(1), m.group(2)) != ("500", "700"):
        fails.append(f"font: Oswald is declared at weights {m.group(1)} to {m.group(2)}, not 500 to 700")
    fp = os.path.join(HERE, "site", m.group(3).lstrip("/"))
    if not os.path.exists(fp):
        return fails + [f"font: {m.group(3)} is not in the tree"]
    sha = hashlib.sha256(open(fp, "rb").read()).hexdigest()
    sc = _font_script()
    if sha != sc.OSWALD_SHA256:
        fails.append(f"font: {m.group(3)} is not the file scripts/oswald_subset.py made (sha {sha[:12]})")
    if "fonts.googleapis.com" in css or "fonts.gstatic.com" in css:
        fails.append("font: site.css loads a font from Google")
    return fails


def _entry(**kw):
    e = {"status": "forecast", "roof": "open",
         "stadium": {"name": "Empower Field at Mile High"},
         "kickoff_hour": {"temp_f": 47, "feels_like_f": 42, "sky": "Slight Chance Rain Showers",
                          "pop_pct": 33, "precip_type": "rain showers", "wind_mph": 18,
                          "gust_mph": 23, "wind_dir": "ENE", "is_daytime": False,
                          "wind": {"text": "18 mph across the field, gusting 23",
                                   "arrow_field_deg": 75, "arrow_true_deg": 255}},
         "flags": {"wind": {"on": True, "max_mph": 19}, "precip": {"on": False, "max_pct": 45},
                   "feels": {"on": False}, "alert": {"on": False}, "any": True},
         "alerts": [], "stale": False,
         "credit": {"text": "Conditions by GoCheckMyWeather, NWS, 8:34 PM ET",
                    "url": "https://gocheckmyweather.com/stadiums/empower-field-at-mile-high.html"}}
    e.update(kw)
    import conditions as cx
    e["words"] = cx.words(e)
    return e


_QUIET = {"wind": {"on": False}, "precip": {"on": False, "max_pct": 33}, "feels": {"on": False},
          "alert": {"on": False}, "any": False}


def _flags(**on):
    f = {k: {"on": False} for k in ("wind", "precip", "feels", "alert")}
    for k, v in on.items():
        f[k] = dict(v, on=True) if isinstance(v, dict) else {"on": bool(v)}
    f["any"] = any(x["on"] for x in f.values())
    return f


def _bulbs(html):
    return [(n, "on" in c) for c, n in re.findall(r'<span class="sbc-bulb([^"]*)" data-bulb="([a-z]+)"', html)]


def _game(gid, state="pre", **kw):
    g = {"id": gid, "league": "NFL", "state": state, "start_utc": "2026-10-16T00:15Z", "network": "Prime Video",
         "venue": "Empower Field at Mile High",
         "away": {"abbr": "SEA", "name": "Seahawks", "full": "Seattle Seahawks", "record": "3-2"},
         "home": {"abbr": "DEN", "name": "Broncos", "full": "Denver Broncos", "record": "3-2"}}
    g.update(kw)
    return g


def check_render():
    import site_build as sb
    fails = []
    was = (sb.CX_DATA, sb._NOW_CACHE)
    try:
        import datetime as _d
        sb._NOW_CACHE = _d.datetime(2026, 10, 15, 13, 0, tzinfo=_d.timezone.utc)
        k = lambda t, f=None: {"temp_f": t, "feels_like_f": f, "pop_pct": 0, "wind_mph": 5, "wind_dir": "N",
                               "wind": {"text": "5 mph down the field", "arrow_true_deg": 180}}
        games = {
            "den": _entry(),
            "dome": {"status": "indoor", "venue": "Allegiant Stadium", "words": {"line": "Indoor", "roof": "Indoor"}},
            "lon": {"status": "outside_nws", "venue": "Wembley Stadium", "words": {"line": "Outside NWS coverage"}},
            "roof": _entry(roof="retractable", flags=_QUIET),
            "kc": _entry(alerts=[{"event": "Severe Thunderstorm Warning"}], flags=_flags(alert=True)),
            "rain": _entry(flags=_flags(precip={"max_pct": 70})),
            "cold": _entry(kickoff_hour=k(50, 28), flags=_flags(feels={"min_f": 28, "below_f": 32})),
            "f59": _entry(kickoff_hour=k(61, 59), flags=_QUIET),
            "f60": _entry(kickoff_hour=k(58, 60), flags=_QUIET),
            "quiet": _entry(flags=_QUIET, alerts=None),
            "calm": _entry(kickoff_hour={"temp_f": 84, "sky": "Sunny", "pop_pct": 0, "wind_mph": 0,
                                         "wind": {"text": "Calm", "arrow_true_deg": 30}}, flags=_QUIET),
            "gap": _entry(kickoff_hour={"temp_f": None, "sky": "Sunny", "pop_pct": None, "wind_mph": None,
                                        "wind": {}}, flags=_QUIET),
        }
        sb.CX_DATA = {"games": games}
        card = lambda gid, ticket=False, **kw: sb.sbc_card(_game(gid, **kw), {}, ticket=ticket)
        den = card("den", ticket=True)
        # linescore: the Ticket's quarters and yellow T; compact is the total only
        heads = re.findall(r'<span class="sbc-h( sbc-th)?">([^<]*)</span>', den)
        if [h for _c, h in heads] != ["", "1", "2", "3", "4", "T"] or heads[-1][0] != " sbc-th":
            fails.append(f"strip: the Ticket's line score heads are {heads}, not 1 to 4 and a yellow T")
        if 'data-sbc="ticket"' not in den:
            fails.append("strip: the Ticket card does not say it is the Ticket")
        q = card("quiet")
        if "sbc-h" in q or 'class="sbc-ls sbc-compact"' not in q or q.count("sbc-pl") != 2:
            fails.append("strip: a compact card is not the total only")
        # empty: before kickoff every score plate is empty
        if re.search(r'class="sbc-pl[^"]*">(?:<span class="tk-sc">)?\d', den) or den.count("sbc-empty") != 10:
            fails.append("strip: a pre-game plate is not empty")
        # final: the plates fill from the feed, the loser's total dims, the weather stays
        fin = dict(state="post", status_short="Final")
        fa = {"abbr": "SEA", "name": "Seahawks", "record": "4-2", "score": "20", "periods": ["7", "3", "0", "10"]}
        fh = {"abbr": "DEN", "name": "Broncos", "record": "3-3", "score": "17", "periods": ["0", "7", "7", "3"]}
        f = card("den", ticket=True, away=fa, home=fh, **fin)
        plates = re.findall(r'<span class="sbc-pl( sbc-tot)?[^"]*"[^>]*>(?:<span class="tk-sc">)?([^<]*)<', f)
        if [v for _c, v in plates] != ["7", "3", "0", "10", "20", "0", "7", "7", "3", "17"]:
            fails.append(f"strip: a final's plates do not fill from the feed: {[v for _c, v in plates]}")
        if not re.search(r'sbc-tot sbc-lose" data-side="home"', f) or re.search(r'sbc-lose" data-side="away"', f):
            fails.append("strip: the loser's total does not dim, or the winner's does")
        if 'data-cx="forecast"' not in f:
            fails.append("strip: a final lost its weather plates")
        if "Final" not in f:
            fails.append("strip: a final's kicker does not say Final")
        ot = card("den", ticket=True, away=dict(fa, periods=fa["periods"] + ["3"], score="23"),
                  home=dict(fh, periods=fh["periods"] + ["0"], score="20", ), state="post", status_short="Final/OT")
        if ">OT</span>" not in ot or ">OT</span>" in f:
            fails.append("strip: OT is not a column only when the game went to overtime")
        five = card("den", ticket=True, away=dict(fa, periods=fa["periods"] + ["0"]),
                    home=dict(fh, periods=fh["periods"] + ["0"]), **fin)
        if ">OT</span>" in five or five.count('class="sbc-h"') != 5:
            fails.append("strip: a fifth period the feed carries without OT in its status made a column")
        half = card("den", ticket=True, away=dict(fa, periods=["7", "3"]), home=fh, **fin)
        if re.findall(r'<span class="sbc-pl">(\d+)</span>', half):
            fails.append("strip: a half-filled feed printed quarters")
        noscore = card("den", away=dict(fa, score=""), home=dict(fh, score=""), **fin)
        if re.search(r'tk-sc">0<', noscore):
            fails.append("strip: a final with no score in the feed printed 0")
        # plates
        keys = re.findall(r'<div class="sbc-wp sbc-([twr])', den)
        labels = re.findall(r'<span class="sbc-k">([^<]+)</span>', den)
        if keys != ["t", "w", "r"] or labels != ["Temp", "Wind", "Rain"]:
            fails.append(f"strip: the weather plates are {keys} {labels}, not TEMP, WIND, RAIN")
        for want in ("47°", "feels 42°", "gust 23 mph", "up to 45%", "33%", "18 mph across the field, gusting 23"):
            if want not in den:
                fails.append(f"strip: '{want}' is not printed")
        if "up to 33%" in q:
            fails.append("strip: the rain plate names a peak that is not higher")
        # bulbs: each lit by its own flag
        want = {"den": [("wind", True), ("rain", False), ("cold", False), ("alert", False)],
                "rain": [("wind", False), ("rain", True), ("cold", False), ("alert", False)],
                "cold": [("wind", False), ("rain", False), ("cold", True), ("alert", False)],
                "kc": [("wind", False), ("rain", False), ("cold", False), ("alert", True)],
                "quiet": [("wind", False), ("rain", False), ("cold", False), ("alert", False)],
                "f59": [("wind", False), ("rain", False), ("cold", False), ("alert", False)],
                "f60": [("wind", False), ("rain", False), ("heat", False), ("alert", False)]}
        for gid, w in want.items():
            got = _bulbs(card(gid))
            if got != w:
                fails.append(f"strip: {gid}'s bulbs are {got}, not {w}")
        # edge: a lit bulb lights the board and the plate that matters; no flag, no yellow
        for gid in ("den", "rain", "cold", "kc"):
            if 'class="tk-c sbc sbc-lit"' not in card(gid):
                fails.append(f"strip: {gid} has a lit bulb and no yellow edge")
        if 'class="sbc-wp sbc-w on"' not in den or 'class="sbc-wp sbc-r on"' not in card("rain") \
                or 'class="sbc-wp sbc-t on"' not in card("cold"):
            fails.append("strip: a flag does not light the plate that matters")
        if "sbc-lit" in q or ' on"' in q:
            fails.append("strip: no flag is on and the card carries yellow")
        if 'sbc-wp sbc-w on' in card("kc"):
            fails.append("strip: an alert lit the wind plate")
        # words
        if 'class="sbc-words on"' not in den or 'class="sbc-words on"' in card("rain"):
            fails.append("strip: the words line is not yellow exactly when the wind flag is on")
        cm = re.search(r'<span class="sbc-credit"><a href="([^"]+)">([^<]+)</a></span></p>', den)
        if not cm or cm.group(2) != "Conditions by GoCheckMyWeather, NWS, 8:34 PM ET" \
                or not cm.group(1).startswith("https://gocheckmyweather.com/stadiums/"):
            fails.append("strip: the credit is not on the words line, linked to the stadium page")
        # arrow
        if 'aria-label="Wind from the east-northeast"' not in den or "rotate(255 15 15)" not in den:
            fails.append("strip: the wind arrow is not at arrow_true_deg")
        c = card("calm")
        if "cxs-arrow" in c or '<span class="sbc-big">Calm</span>' not in c:
            fails.append("strip: Calm draws an arrow, or does not say Calm")
        # missing
        gp = card("gap")
        if gp.count(">missing<") != 3 or re.search(r'class="sbc-big">\d', gp):
            fails.append("strip: a number the Worker did not give does not print as missing")
        # unchecked, and the alert's own word
        if "Alerts not checked" not in q:
            fails.append("strip: alerts null does not print 'Alerts not checked'")
        if "Severe Thunderstorm Warning" not in card("kc"):
            fails.append("strip: an alert does not print the NWS's own word")
        # single plates
        dome = card("dome")
        wxd = dome[dome.find('class="sbc-wx"'):dome.find("</div>", dome.find('class="sbc-wx"'))]
        if '<p class="sbc-one">Dome · No weather</p>' not in wxd or re.search(
                r"\d", re.sub(r"<[^>]+>", "", wxd)) or "sbc-bulb" in dome:
            fails.append("strip: a dome is not one numberless plate")
        lon = sb.sbc_card(_game("lon", venue="Wembley Stadium", venue_city="London"), {})
        if '<p class="sbc-one">London · Outside NWS coverage</p>' not in lon:
            fails.append("strip: outside NWS coverage is not one plate with the city")
        rf = card("roof")
        if '<span class="sbc-chip sbc-roof">Roof</span>' not in rf or 'data-cx="forecast"' not in rf:
            fails.append("strip: a retractable roof does not keep the plates and add a ROOF plate")
        # the kicker
        if '<span class="sbc-kick" data-role="kicker">Thu Oct 15 · 8:15 PM ET · Empower Field</span>' not in den:
            fails.append("strip: the kicker is not the kickoff in ET and the stadium's short name")
        # sprite
        page = sb.cx_sprite(den + den + c)
        if page.count('<symbol id="cxs-arrow"') != 1 or "<path" in re.sub(r'<svg class="cx-sprite".*$', "", page, flags=re.S):
            fails.append("strip: the arrow is not drawn once per page and placed with <use>")
    finally:
        sb.CX_DATA, sb._NOW_CACHE = was
    return fails


def check_tree(out):
    fails = []
    fp = os.path.join(out, "index.html")
    if not os.path.exists(fp):
        return ["strip tree: the gate's build has no home page"]
    home = open(fp, encoding="utf-8").read()
    days = re.findall(r'<section class="bd-mod wb-day"[^>]*>(.*?)</section>', home, re.S)
    if not days:
        print("::warning::strip tree: the board holds no games this build; tree checks not run")
        return fails
    for d in days:
        cards = re.findall(r'<article class="tk-c[^"]*"[^>]*data-sbc="([a-z]+)"', d)
        allc = re.findall(r'<article class="tk-c', d)
        if len(cards) != len(allc):
            fails.append(f"strip tree: {len(allc) - len(cards)} board card(s) are not scoreboards")
        if cards and (cards[0] != "ticket" or any(c != "compact" for c in cards[1:])):
            fails.append(f"strip tree: a day's cards are {cards}, not the Ticket then compact")
    low = home.lower()
    if any(a in low for a in AMBER) or "cx-flag" in home or "cx-hud" in home:
        fails.append("strip tree: S-2c amber is still on the home")
    sc = _font_script()
    allowed = set(sc.OSWALD_TEXT)
    texts = re.findall(r'class="sbc-team"[^>]*>(.*?)</span>(?=<span class="sbc-pl)', home, re.S)
    texts += re.findall(r'<p class="sbc-one">([^<]*)</p>', home)
    texts += re.findall(r'<span class="sbc-big">(.*?)</span>(?=<span class="sbc-s)', home)
    texts += re.findall(r'class="tk-tab wb-t[^"]*"[^>]*>([^<]*)', home)
    plain = set()
    for t in texts:
        t = re.sub(r"<small.*?</small>|<span class=\"sbc-miss\">.*?</span>|<svg.*?</svg>", "", t, flags=re.S)
        t = re.sub(r"<[^>]+>", "", t).replace("&amp;", "&").replace("&#x27;", "'")
        plain |= set(t.upper())
    bad = sorted(plain - allowed)
    if not texts:
        fails.append("strip tree: no Oswald text found on the home, so the subset was not checked")
    if bad:
        fails.append(f"strip tree: the home sets {bad} in Oswald and the subset cannot draw them")
    return fails


def strip_canary(out=None):
    f = check_contrast() + check_rules() + check_font() + check_render()
    if out:
        f += check_tree(out)
    return f


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    root = sys.argv[1] if len(sys.argv) > 1 else None
    f = strip_canary(root)
    for x in f:
        print("FAIL", x)
    print("strip canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
