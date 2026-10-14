#!/usr/bin/env python3
"""strip_canary.py: Sprint S-2b item 1, the conditions strip on every card (Program 7, section 3).

Each check names the break it exists for and was seen red first (U-9).

  contrast   every text colour the shipped site.css gives the strip, and every stop of the
             temperature ink, clears 4.5:1 on the card's lightest composite ground in light and
             in dark: the Ticket's rgba(26,28,34,.88) over each theme's paper, under the brightest
             NFL or college team wash at the card's .24, under the strip's own scrim as site.css
             declares it, and under a flagged cell's tint
  cells      a forecast strip has the four cells: temperature with the feel, wind with the words,
             precipitation with its type, the venue flag
  muted      an indoor game's strip is muted and prints no number
  bright     the strip is bright when the Worker's flags say so, and the flagged cell is lit
  peak       a lit cell names the window's peak when it is above the kickoff hour's number
  alert      an alert turns the edge rule red with the NWS's own word on it
  unchecked  alerts null prints "Alerts not checked"
  credit     the credit is under the strip, with the NWS time, linked to the Weather stadium page
  arrow      the field graphic is drawn where the stadium has an orientation, the arrow rotated by
             arrow_field_deg; with none, a compass and arrow_true_deg; Calm draws no arrow
  final      a final's card keeps its strip

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = (26, 28, 34, .88)
PAPERS = {"light": "#FBFAF6", "dark": "#131419"}
WASH = .24
ON_TINT = (245, 184, 63, .12)


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
    t = re.search(r"\.cx-c\.on\{background:rgba\((\d+),(\d+),(\d+),([.\d]+)\)", css)
    tint = (int(t.group(1)), int(t.group(2)), int(t.group(3)), float(t.group(4))) if t else ON_TINT
    out = {}
    for theme, paper in PAPERS.items():
        base = _over(CARD, _rgb(paper))
        washed = _over(_rgb(brightest) + (WASH,), base)
        for name, g in ((f"{theme} card", base), (f"{theme} card under {brightest}", washed)):
            g = _over(scrim, g) if scrim else g
            out[name] = g
        out[f"{theme} flagged cell under {brightest}"] = _over(tint, out[f"{theme} card under {brightest}"])
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
    return fails


def _entry(**kw):
    e = {"status": "forecast", "roof": "open",
         "kickoff_hour": {"temp_f": 47, "feels_like_f": 42, "sky": "Slight Chance Rain Showers",
                          "pop_pct": 33, "precip_type": "rain showers", "wind_mph": 18,
                          "is_daytime": False,
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


def check_render():
    import site_build as sb
    fails = []
    was = sb.CX_DATA
    try:
        games = {
            "den": _entry(),
            "dome": {"status": "indoor", "words": {"line": "Indoor", "roof": "Indoor"}},
            "kc": _entry(alerts=[{"event": "Severe Thunderstorm Warning"}],
                         flags={"wind": {"on": False}, "precip": {"on": False},
                                "feels": {"on": False}, "alert": {"on": True}, "any": True}),
            "quiet": _entry(flags={"wind": {"on": False}, "precip": {"on": False},
                                   "feels": {"on": False}, "alert": {"on": False}, "any": False},
                            alerts=None),
            "nyg": _entry(kickoff_hour={"temp_f": 54, "sky": "Sunny", "is_daytime": True,
                                        "wind": {"text": "9 mph from the W", "arrow_field_deg": None,
                                                 "arrow_true_deg": 90}}),
            "calm": _entry(kickoff_hour={"temp_f": 84, "sky": "Sunny", "is_daytime": True,
                                         "wind": {"text": "Calm", "arrow_field_deg": 30,
                                                  "arrow_true_deg": 30}}),
        }
        sb.CX_DATA = {"games": games}
        den = sb.cx_strip({"id": "den"})
        # cells
        cells = re.findall(r'<span class="cx-c (cx-[a-z])', den)
        if cells != ["cx-t", "cx-w", "cx-p", "cx-r"]:
            fails.append(f"strip: the cells are {cells}, expected temperature, wind, precipitation, venue")
        for want in ("47°", "feels 42°", "18 mph", "across the field, gusting 23",
                     "rain showers", "Open air"):
            if want not in den:
                fails.append(f"strip: '{want}' is not printed")
        # peak: a lit cell says the window's peak when it is above the kickoff hour's number
        if "up to 19 mph" not in den:
            fails.append("strip: the lit wind cell does not say the window's peak")
        if "up to 45%" in den:
            fails.append("strip: an unlit cell prints a peak")
        # bright
        if 'class="cx cx-bright' not in den:
            fails.append("strip: flags.any is true and the strip is not bright")
        if 'class="cx-c cx-w on"' not in den:
            fails.append("strip: the wind flag is on and the wind cell is not lit")
        q = sb.cx_strip({"id": "quiet"})
        if "cx-bright" in q or " on\"" in q:
            fails.append("strip: no flag is on and the strip is bright")
        # muted
        dome = sb.cx_strip({"id": "dome"})
        if "cx-muted" not in dome or "Indoor" not in dome or re.search(r"\d", re.sub(r"<[^>]+>", "", dome)):
            fails.append(f"strip: the indoor strip is not muted, wordless or numberless: {dome[:160]}")
        # alert
        kc = sb.cx_strip({"id": "kc"})
        if 'class="cx cx-alert' not in kc or '<span class="cx-aw">Severe Thunderstorm Warning</span>' not in kc:
            fails.append("strip: an alert does not turn the edge red with the NWS's word")
        css = open(os.path.join(HERE, "site", "assets", "site.css"), encoding="utf-8").read()
        m = re.search(r"\.cx-alert\{border-left-color:(#[0-9A-Fa-f]{6})\}", css)
        if not m or not (lambda c: c[0] > 180 and c[1] < 120 and c[2] < 120)(_rgb(m.group(1))):
            fails.append("strip: the alert's edge rule is not red in site.css")
        # unchecked
        if "Alerts not checked" not in q:
            fails.append("strip: alerts null does not print 'Alerts not checked'")
        if "no alert" in (den + q + kc).lower():
            fails.append("strip: a strip prints 'No alerts'")
        # credit
        cm = re.search(r'<p class="cx-credit"><a href="([^"]+)">([^<]+)</a></p></div>$', den)
        if not cm or cm.group(2) != "Conditions by GoCheckMyWeather, NWS, 8:34 PM ET" \
                or not cm.group(1).startswith("https://gocheckmyweather.com/stadiums/"):
            fails.append("strip: the credit is not under the strip, linked to the stadium page")
        # arrow
        if 'aria-label="Wind against the field"' not in den or 'rotate(75 15 15)' not in den:
            fails.append("strip: the oriented field does not carry the arrow at arrow_field_deg")
        nyg = sb.cx_strip({"id": "nyg"})
        if 'aria-label="Wind direction, north up"' not in nyg or 'rotate(90 15 15)' not in nyg:
            fails.append("strip: a stadium with no orientation does not get the compass at arrow_true_deg")
        calm = sb.cx_strip({"id": "calm"})
        if "cx-arr" in calm:
            fails.append("strip: Calm draws an arrow")
        # glyphs: by reference, and the page carries each drawing once
        page = sb.cx_sprite(den + den + calm)
        for n in set(re.findall(r'href="#wxg-([a-z-]+)"', den + calm)):
            if page.count(f'<symbol id="wxg-{n}"') != 1:
                fails.append(f"strip: the page does not carry the {n} glyph exactly once")
        # final + card
        g = {"id": "den", "league": "NFL", "state": "post", "start_utc": "2026-10-16T00:15Z",
             "away": {"abbr": "SEA", "score": "20"}, "home": {"abbr": "DEN", "score": "17"}}
        card = sb._tk_card(g, {}, buttons=False)
        if 'data-cx="forecast"' not in card:
            fails.append("strip: a final's card lost its strip")
        g2 = dict(g, state="pre")
        if 'data-cx="forecast"' not in sb._tk_card(g2, {}, buttons=False):
            fails.append("strip: a pre-game card has no strip")
    finally:
        sb.CX_DATA = was
    return fails


def strip_canary():
    return check_contrast() + check_render()


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
