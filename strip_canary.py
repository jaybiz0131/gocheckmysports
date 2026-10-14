#!/usr/bin/env python3
"""strip_canary.py: the conditions HUD on every card. S-2b item 1 built the strip; S-2c item 0
(Jack's approval of 14 October 2026, the Main artboard) made it the three-tile HUD.

Each check names the break it exists for and was seen red first (U-9).

  contrast   every text colour the shipped site.css gives the HUD, every stop of the temperature
             ink, and the green day tab, clear 4.5:1 on the HUD's lightest composite grounds in
             light and in dark: the Ticket's rgba(26,28,34,.88) over each theme's paper, under the
             brightest NFL or college team wash at the card's .24, under the HUD's own ground as
             site.css declares it, then a tile, then a flagged tile. Glow is never counted.
  tiles      a forecast HUD has three tiles in order: kickoff, wind, rain
  muted      an indoor game's HUD is one muted line with the roof icon and prints no number
  bright     a flag lights its tile and the card carries the amber border; no flag, no amber
  amber      site.css puts amber only on a selector that needs a flag (.on, .cx-flag)
  glow       site.css puts glow only on data (the big numbers, the arrow, the ring, the tab)
  ramp       the temperature is printed in the Weather site's ink for it
  ring       the ring is filled to the kickoff hour's chance and names the window's peak when
             that is higher, and no peak when it is not
  missing    a number the Worker did not give prints as missing
  alert      an alert puts the NWS's own word on a red rule
  unchecked  alerts null prints "Alerts not checked"
  credit     the credit is under the HUD, with the NWS time, linked to the Weather stadium page
  arrow      the compass arrow points the way the wind blows (arrow_true_deg); Calm draws none
  sprite     the compass, arrow, ring and roof are drawn once per page and placed with <use>
  final      a final's card keeps its HUD

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = (26, 28, 34, .88)
PAPERS = {"light": "#FBFAF6", "dark": "#131419"}
WASH = .24
ON_TINT = (255, 176, 61, .08)
TILE = (255, 255, 255, .035)
AMBER = ("#FFB03D", "#FFCF86", "#FFE1B3", "255,176,61")


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


def grounds():
    """The strip's grounds: for each theme, the card over the paper, then under the brightest
    team wash any NFL or college card can carry, then a flagged cell's tint on top."""
    tc = json.load(open(os.path.join(HERE, "site", "data", "team-colors.json"), encoding="utf-8"))
    teams = [v.get("color") for lg in ("nfl", "college-football") for v in (tc.get(lg) or {}).values()
             if re.match(r"^#[0-9a-fA-F]{6}$", v.get("color") or "")]
    brightest = max(teams, key=lambda h: _lum(_rgb(h)))
    css = open(os.path.join(HERE, "site", "assets", "site.css"), encoding="utf-8").read()
    m = re.search(r"\.cx\{[^}]*background:rgba\((\d+),(\d+),(\d+),([.\d]+)\)", css)
    scrim = (int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4))) if m else None
    t = re.search(r"\.cx-tile\.on\{background:rgba\((\d+),(\d+),(\d+),([.\d]+)\)", css)
    tint = (int(t.group(1)), int(t.group(2)), int(t.group(3)), float(t.group(4))) if t else ON_TINT
    u = re.search(r"\.cx-tile\{[^}]*background:rgba\((\d+),(\d+),(\d+),([.\d]+)\)", css)
    tile = (int(u.group(1)), int(u.group(2)), int(u.group(3)), float(u.group(4))) if u else TILE
    out = {}
    for theme, paper in PAPERS.items():
        base = _over(CARD, _rgb(paper))
        washed = _over(_rgb(brightest) + (WASH,), base)
        for name, g in ((f"{theme} card", base), (f"{theme} card under {brightest}", washed)):
            g = _over(scrim, g) if scrim else g
            out[name] = g
            out[f"{name}, a tile"] = _over(tile, g)
        out[f"{theme} flagged tile under {brightest}"] = _over(tint, out[f"{theme} card under {brightest}"])
    return out, brightest


def _cx_text_colours(css):
    """(selector, colour) for every `color:` the strip's rules declare."""
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        sel = sel.strip()
        if not any(p.strip().startswith(".cx") for p in sel.split(",")):
            continue
        for c in re.findall(r"(?:^|;)\s*color:\s*(#[0-9A-Fa-f]{6})", body):
            out.append((sel, c))
    return out


def check_contrast(css=None, ink=None):
    import site_build as sb
    css = css if css is not None else open(os.path.join(HERE, "site", "assets", "site.css"),
                                           encoding="utf-8").read()
    ink = ink if ink is not None else sb.CX_TEMP_INK
    fails = []
    gs, _b = grounds()
    pairs = _cx_text_colours(css)
    if len(pairs) < 6:
        fails.append(f"strip contrast: only {len(pairs)} strip text colours found in site.css")
    pairs += [(f"temperature ink {t}F", c) for t, c in ink]
    for sel, c in pairs:
        for gname, g in gs.items():
            r = contrast(_rgb(c), g)
            if r < 4.5:
                fails.append(f"strip contrast: {sel} {c} on the {gname} is {r:.2f}:1")
    # the active day tab: its green and its count on its own solid ground
    tab = re.search(r"\.wb-tabs \.tk-tab\.on\{background:(#[0-9A-Fa-f]{6});color:(#[0-9A-Fa-f]{6})", css)
    small = re.search(r"\.wb-tabs \.tk-tab\.on small\{[^}]*color:(#[0-9A-Fa-f]{6})", css)
    if not tab or not small:
        fails.append("strip contrast: the active day tab has no solid ground and colour in site.css")
    else:
        for what, c in (("tab", tab.group(2)), ("tab count", small.group(1))):
            r = contrast(_rgb(c), _rgb(tab.group(1)))
            if r < 4.5:
                fails.append(f"strip contrast: the active day {what} {c} on {tab.group(1)} is {r:.2f}:1")
    return fails


def _hud_rules(css):
    """(selectors, body) for every rule in site.css whose selector names the HUD or the hero."""
    out = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        sel = sel.strip()
        if re.search(r"\.(cx|cxh|cxc|cxf)[-a-z]*\b", sel) or ".wb-tabs" in sel:
            out.append((sel, body))
    return out


def check_rules(css=None):
    """Jack's rulings of 14 October, read from the shipped CSS: amber only where a flag is on,
    glow only on data."""
    css = css if css is not None else open(os.path.join(HERE, "site", "assets", "site.css"),
                                           encoding="utf-8").read()
    fails = []
    rules = _hud_rules(css)
    if len(rules) < 20:
        fails.append(f"strip rules: only {len(rules)} HUD rules found in site.css")
    for sel, body in rules:
        if any(a.lower() in body.lower().replace(" ", "") for a in AMBER):
            for part in sel.split(","):
                if ".on" not in part and ".cx-flag" not in part:
                    fails.append(f"strip rules: amber on '{part.strip()}', which needs no flag")
        if "text-shadow" in body or "drop-shadow" in body or ("box-shadow" in body and "rgba(61,220,132" in body):
            for part in sel.split(","):
                if not re.search(r"cx-glow|cx-arw|cx-ring svg|\.tk-tab\.on|cxc-line", part):
                    fails.append(f"strip rules: glow on '{part.strip()}', which is not data")
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
                   "feels": {"on": False},
                   "alert": {"on": False}, "any": True},
         "alerts": [], "stale": False,
         "credit": {"text": "Conditions by GoCheckMyWeather, NWS, 8:34 PM ET",
                    "url": "https://gocheckmyweather.com/stadiums/empower-field-at-mile-high.html"}}
    e.update(kw)
    import conditions as cx
    e["words"] = cx.words(e)
    return e


_QUIET = {"wind": {"on": False}, "precip": {"on": False, "max_pct": 33}, "feels": {"on": False},
          "alert": {"on": False}, "any": False}


def check_render():
    import site_build as sb
    fails = []
    was = sb.CX_DATA
    try:
        games = {
            "den": _entry(),
            "dome": {"status": "indoor", "venue": "Allegiant Stadium",
                     "words": {"line": "Indoor", "roof": "Indoor"}},
            "kc": _entry(alerts=[{"event": "Severe Thunderstorm Warning"}],
                         flags={"wind": {"on": False}, "precip": {"on": False},
                                "feels": {"on": False}, "alert": {"on": True}, "any": True}),
            "quiet": _entry(flags=_QUIET, alerts=None),
            "nyg": _entry(kickoff_hour={"temp_f": 54, "sky": "Sunny", "is_daytime": True, "wind_mph": 9,
                                        "pop_pct": 0, "wind_dir": "W",
                                        "wind": {"text": "9 mph from the W", "arrow_field_deg": None,
                                                 "arrow_true_deg": 90}}),
            "calm": _entry(kickoff_hour={"temp_f": 84, "sky": "Sunny", "is_daytime": True, "pop_pct": 0,
                                         "wind_mph": 0,
                                         "wind": {"text": "Calm", "arrow_field_deg": 30,
                                                  "arrow_true_deg": 30}}),
            "gap": _entry(kickoff_hour={"temp_f": None, "sky": "Sunny", "pop_pct": None, "wind_mph": None,
                                        "wind": {}}, flags=_QUIET),
        }
        sb.CX_DATA = {"games": games}
        den = sb.cx_strip({"id": "den"})
        # tiles
        tiles = re.findall(r'<div class="cx-tile (cx-[a-z])', den)
        if tiles != ["cx-t", "cx-w", "cx-p"]:
            fails.append(f"strip: the tiles are {tiles}, expected kickoff, wind, rain")
        for want in ("47°", "feels 42°", ">18</b>", "gust 23 mph", "18 mph across the field, gusting 23",
                     "Open air", "Empower Field at Mile High"):
            if want not in den:
                fails.append(f"strip: '{want}' is not printed")
        # ramp: the temperature in the Weather site's ink for it, glowing
        ink = sb.cx_temp_ink(47)
        if f'<b class="cx-big cx-glow" style="color:{ink}">47°</b>' not in den:
            fails.append(f"strip: the temperature is not in the Weather ramp's ink {ink}")
        # ring: filled to the kickoff hour, the peak when higher
        if 'stroke-dasharray="33 100"' not in den or "<b>33%</b>" not in den:
            fails.append("strip: the ring is not filled to the kickoff hour's chance")
        if "up to 45%" not in den:
            fails.append("strip: the ring does not name the window's higher peak")
        if "up to 19 mph" not in den:
            fails.append("strip: the flagged wind does not say the window's peak")
        q = sb.cx_strip({"id": "quiet"})
        if "up to 33%" in q:
            fails.append("strip: the ring names a peak that is not higher")
        # bright, and amber only with a flag
        if 'class="cx cx-hud cx-bright' not in den or 'class="cx-tile cx-w on"' not in den:
            fails.append("strip: the wind flag is on and the wind tile is not lit")
        if 'class="cx-words on"' not in den:
            fails.append("strip: the wind flag is on and the words line is not amber")
        if sb.cx_card_flag({"id": "den"}) != " cx-flag":
            fails.append("strip: a flagged card has no amber border")
        if "cx-bright" in q or ' on"' in q or sb.cx_card_flag({"id": "quiet"}):
            fails.append("strip: no flag is on and the card carries amber")
        if sb.cx_card_flag({"id": "kc"}):
            fails.append("strip: an alert alone turned the card amber")
        # muted
        dome = sb.cx_strip({"id": "dome"})
        if "cx-muted" not in dome or "Indoor" not in dome or '<use href="#cxs-roof"/>' not in dome \
                or re.search(r"\d", re.sub(r"<[^>]+>", "", dome)):
            fails.append(f"strip: the indoor HUD is not one muted, numberless line with the roof: {dome[:160]}")
        # missing
        gap = sb.cx_strip({"id": "gap"})
        if gap.count(">missing<") < 3 or re.search(r"cx-big[^>]*>\d", gap):
            fails.append("strip: a number the Worker did not give does not print as missing")
        # alert
        kc = sb.cx_strip({"id": "kc"})
        if 'class="cx cx-hud cx-alert' not in kc or '<span class="cx-aw">Severe Thunderstorm Warning</span>' not in kc:
            fails.append("strip: an alert does not put the NWS's word on a red rule")
        css = open(os.path.join(HERE, "site", "assets", "site.css"), encoding="utf-8").read()
        m = re.search(r"\.cx-alert\{border-left:3px solid (#[0-9A-Fa-f]{6})\}", css)
        if not m or not (lambda c: c[0] > 180 and c[1] < 120 and c[2] < 120)(_rgb(m.group(1))):
            fails.append("strip: the alert's rule is not red in site.css")
        # unchecked
        if "Alerts not checked" not in q:
            fails.append("strip: alerts null does not print 'Alerts not checked'")
        if "no alert" in (den + q + kc).lower():
            fails.append("strip: a HUD prints 'No alerts'")
        # credit
        cm = re.search(r'<p class="cx-credit"><a href="([^"]+)">([^<]+)</a></p></div>$', den)
        if not cm or cm.group(2) != "Conditions by GoCheckMyWeather, NWS, 8:34 PM ET" \
                or not cm.group(1).startswith("https://gocheckmyweather.com/stadiums/"):
            fails.append("strip: the credit is not under the HUD, linked to the stadium page")
        # arrow: the way the wind blows, true, on a compass
        if 'aria-label="Wind from the east-northeast"' not in den or 'rotate(255 15 15)' not in den:
            fails.append("strip: the compass arrow is not at arrow_true_deg")
        nyg = sb.cx_strip({"id": "nyg"})
        if 'rotate(90 15 15)' not in nyg or 'aria-label="Wind from the west"' not in nyg:
            fails.append("strip: a stadium with no orientation does not get its arrow at arrow_true_deg")
        calm = sb.cx_strip({"id": "calm"})
        if "cxs-arrow" in calm or "Calm" not in calm:
            fails.append("strip: Calm draws an arrow, or does not say Calm")
        # sprite: the drawings once per page, placed with <use>
        page = sb.cx_sprite(den + den + calm + dome)
        for n in ("compass", "arrow", "ring", "roof"):
            if page.count(f'<symbol id="cxs-{n}"') != 1:
                fails.append(f"strip: the page does not carry the {n} drawing exactly once")
        if "<path" in re.sub(r'<svg class="cx-sprite".*$', "", page, flags=re.S):
            fails.append("strip: a HUD draws a path inline instead of placing the sprite")
        # final + card
        g = {"id": "den", "league": "NFL", "state": "post", "start_utc": "2026-10-16T00:15Z",
             "away": {"abbr": "SEA", "score": "20"}, "home": {"abbr": "DEN", "score": "17"}}
        card = sb._tk_card(g, {}, buttons=False)
        if 'data-cx="forecast"' not in card:
            fails.append("strip: a final's card lost its HUD")
        g2 = dict(g, state="pre")
        c2 = sb._tk_card(g2, {}, buttons=False)
        if 'data-cx="forecast"' not in c2 or 'class="tk-c cx-flag"' not in c2:
            fails.append("strip: a pre-game card has no HUD, or a flagged card no amber border")
    finally:
        sb.CX_DATA = was
    return fails


def strip_canary():
    return check_contrast() + check_rules() + check_render()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    f = strip_canary()
    for x in f:
        print("FAIL", x)
    gs, b = grounds()
    print("grounds:", {k: "#%02X%02X%02X" % v for k, v in gs.items()}, "brightest wash", b)
    print("strip canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
