#!/usr/bin/env python3
"""conditions_canary.py: Sprint S-2b, the conditions intake (item 0).

Every case runs conditions.refresh() against a stubbed Worker, so it calls no network, and
reads the entry and the words a page would print. Each check names the break it exists for and
was seen red first (U-9).

  indoor        a fixed roof gets "Indoor" and no forecast fields at all
  retractable   a retractable roof gets the forecast and "Retractable roof"
  range         a kickoff past the NWS product prints "Forecast from <day>", the day in ET
  international a venue outside the U.S. prints "Outside NWS coverage" and the Worker is not asked
  missing       a venue with no row prints nothing and is in the build log's list
  alerts        `alerts: null` prints "Alerts not checked", never "No alerts"; an alert that ends
                before the game's window prints nothing and sets no flag
  college       a college game matches ESPN's venue name exactly, and a near name does not match
  final         a game the Worker calls over keeps the strip the last build published

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import json
import os
import shutil
import tempfile

ROWS = [
    {"slug": "empower-field-at-mile-high", "espn_venue_id": "3937", "alt_venue_ids": [],
     "name": "Empower Field at Mile High", "city": "Denver", "state": "CO", "roof": "open",
     "orientation_deg": 0},
    {"slug": "ford-field", "espn_venue_id": "3727", "alt_venue_ids": [], "name": "Ford Field",
     "city": "Detroit", "state": "MI", "roof": "indoor", "orientation_deg": None},
    {"slug": "lucas-oil-stadium", "espn_venue_id": "3812", "alt_venue_ids": [],
     "name": "Lucas Oil Stadium", "city": "Indianapolis", "state": "IN", "roof": "retractable",
     "orientation_deg": None},
    {"slug": "memorial-stadium-bloomington-in", "espn_venue_id": "3830", "alt_venue_ids": [],
     "name": "Memorial Stadium (Bloomington, IN)", "city": "Bloomington", "state": "IN",
     "roof": "open", "orientation_deg": 0},
    {"slug": "memorial-stadium-lincoln-ne", "espn_venue_id": "3834", "alt_venue_ids": [],
     "name": "Memorial Stadium (Lincoln, NE)", "city": "Lincoln", "state": "NE",
     "roof": "open", "orientation_deg": 0},
]


def _hour(t=52, feels=42, wind=10, pop=33, ptype="rain showers"):
    return {"start": "2026-10-15T18:00:00-06:00", "end": "2026-10-15T19:00:00-06:00",
            "temp_f": t, "feels_like_f": feels, "feels_like_kind": "wind chill",
            "wind_mph": wind, "gust_mph": 23, "wind_dir": "SSW", "wind_from_deg": 210,
            "pop_pct": pop, "precip_type": ptype, "sky": "Chance Rain Showers",
            "is_daytime": False}


def _forecast(roof="open", alerts=(), flags_any=False):
    k = dict(_hour(), wind={"text": "10 mph down the field, gusting 23", "relative": True,
                            "arrow_field_deg": 30, "arrow_true_deg": 30})
    return {"roof": roof, "in_range": True, "hours": [_hour(), _hour(50)], "kickoff_hour": k,
            "window": {"kickoff": "2026-10-16T00:15:00Z", "from": "2026-10-15T23:15:00Z",
                       "complete": True},
            "flags": {"wind": {"on": False, "max_mph": 12}, "precip": {"on": False, "max_pct": 33},
                      "feels": {"on": False}, "alert": {"on": None if alerts is None else bool(alerts),
                                                       "count": len(alerts or [])},
                      "any": flags_any},
            "alerts": None if alerts is None else list(alerts),
            "alerts_status": "unavailable" if alerts is None else "ok",
            "stale": False,
            "nws": {"generated_at": "2026-10-15T13:11:57+00:00",
                    "generated_et": "Thu, Oct 15, 9:11 AM ET", "read_at": "2026-10-15T13:20:00Z"},
            "credit": {"text": "Conditions by GoCheckMyWeather, NWS, 9:11 AM ET",
                       "url": "https://gocheckmyweather.com/stadiums/x.html"},
            "worker_at": {"utc": "2026-10-15T13:21:00Z"}}


def _game(gid, league, venue_id, venue, city="", state="", country="USA",
          kick="2026-10-16T00:15Z"):
    return {"id": gid, "league": league, "start_utc": kick, "venue_id": venue_id,
            "venue": venue, "venue_city": city, "venue_state": state, "venue_country": country,
            "away": {"abbr": "A" + gid}, "home": {"abbr": "H" + gid}}


def _run(games, answers, published=None):
    """Run refresh() with a stub Worker. `answers` maps a venue id to (code, body).
    Returns (payload, calls, log)."""
    import conditions as cx
    calls, log = [], []

    def get(path):
        calls.append(path)
        if path == "/stadiums":
            return 200, {"rows": ROWS, "built": "2026-10-13T19:20:00Z"}
        from urllib.parse import parse_qs, urlparse
        v = parse_qs(urlparse(path).query).get("venue", [""])[0]
        return answers.get(v, (404, {"error": "unknown_venue", "reason": "x"}))

    tmp = tempfile.mkdtemp()
    was = cx.OUT
    cx.OUT = os.path.join(tmp, "conditions.json")
    try:
        p = cx.refresh(games, get=get, published=lambda: published or {}, log=log.append)
        on_disk = json.load(open(cx.OUT))
        if on_disk != p:
            log.append("FILE DIFFERS")
        return p, calls, log
    finally:
        cx.OUT = was
        shutil.rmtree(tmp, ignore_errors=True)


def _printed(e):
    return " | ".join(str(v) for v in (e.get("words") or {}).values())


def conditions_canary():
    fails = []
    games = [
        _game("thu", "NFL", "3937", "Empower Field at Mile High", "Denver", "CO"),
        _game("dome", "NFL", "3727", "Ford Field", "Detroit", "MI"),
        _game("retr", "NFL", "3812", "Lucas Oil Stadium", "Indianapolis", "IN"),
        _game("far", "NFL", "3937", "Empower Field at Mile High", "Denver", "CO",
              kick="2026-10-23T00:15Z"),
        _game("lon", "NFL", "2455", "Wembley Stadium", "London", "", country="England"),
        _game("gone", "NFL", "9999", "Nowhere Field", "Somewhere", "KS"),
        _game("iu", "CFB", "", "Memorial Stadium (Bloomington, IN)", "Bloomington", "IN"),
        _game("near", "CFB", "", "Memorial Stadium (Bloomington)", "Bloomington", "IN"),
        _game("lnk", "CFB", "", "Memorial Stadium (Lincoln, NE)", "Lincoln", "NE"),
    ]
    answers = {
        "3937": (200, _forecast(alerts=None)),
        "3727": (200, {"venue": "3727", "league": "nfl", "roof": "indoor",
                       "stadium": {"slug": "ford-field"}}),
        "3812": (200, _forecast(roof="retractable", alerts=[
            {"event": "Severe Thunderstorm Watch", "ends": "2026-10-14T03:00:00Z"}])),
        "3830": (200, _forecast(alerts=[{"event": "Wind Advisory", "headline": "h"}])),
        # S-3a: the alert that ended before the window sits on an open-air game now, since a roofed
        # game carries no alert at all
        "3834": (200, _forecast(roof="open", alerts=[
            {"event": "Severe Thunderstorm Watch", "ends": "2026-10-14T03:00:00Z"}])),
    }
    out_of_range = (200, {"venue": "3937", "league": "nfl", "roof": "open", "in_range": False,
                          "in_range_from": "2026-10-17T03:00:00Z", "reason": "past"})

    def get_answers(path_answers):
        return path_answers

    p, calls, log = _run(games, answers)
    G = p["games"]
    # the far game shares a venue with Thursday's: answer it from its kickoff instead
    p2, _c2, _l2 = _run([games[3]], {"3937": out_of_range})
    far = p2["games"].get("far") or {}

    # indoor
    d = G.get("dome") or {}
    if d.get("status") != "indoor" or (d.get("words") or {}).get("line") != "Indoor":
        fails.append(f"conditions: the dome is {d.get('status')!r} {d.get('words')!r}, not Indoor")
    if any(k in d for k in ("kickoff_hour", "hours", "flags")) or "°" in _printed(d):
        fails.append("conditions: the dome carries a forecast")
    # retractable
    r0 = G.get("retr") or {}
    if r0.get("status") != "roofed" or (r0.get("words") or {}).get("line") != "Roof \u00b7 usually closed" \
            or (r0.get("words") or {}).get("roof") != "Retractable roof":
        fails.append(f"conditions: the retractable is {r0.get('status')!r} {r0.get('words')!r}, expected a roofed "
                     "entry that says 'Roof \u00b7 usually closed'")
    if any(k in r0 for k in ("kickoff_hour", "hours", "flags", "alerts")) or "temp" in (r0.get("words") or {}):
        fails.append("conditions: a roofed game carries a forecast, a flag or an alert")
    r = G.get("lnk") or {}
    # range
    if far.get("status") != "out_of_range" or (far.get("words") or {}).get("line") != "Forecast from Fri, Oct 16":
        fails.append(f"conditions: out of range reads {(far.get('words') or {}).get('line')!r}, "
                     "expected 'Forecast from Fri, Oct 16' (03:00Z Saturday is Friday 11 PM ET)")
    if "temp" in (far.get("words") or {}):
        fails.append("conditions: an out-of-range game prints a temperature")
    # international
    lon = G.get("lon") or {}
    if (lon.get("words") or {}).get("line") != "Outside NWS coverage":
        fails.append(f"conditions: Wembley reads {lon.get('words')!r}, not 'Outside NWS coverage'")
    if any("venue=2455" in c for c in calls):
        fails.append("conditions: the Worker was asked about Wembley")
    # missing
    gone = G.get("gone") or {}
    if gone.get("status") != "missing" or _printed(gone):
        fails.append(f"conditions: a missing venue is {gone.get('status')!r} and prints {_printed(gone)!r}")
    if not any("Nowhere Field" in m for m in p.get("missing") or []):
        fails.append("conditions: the missing venue is not in the payload's missing list")
    if not any("missing venue" in m and "Nowhere Field" in m for m in log):
        fails.append("conditions: the missing venue is not in the build log")
    # alerts
    t = G.get("thu") or {}
    tw = _printed(t)
    if (t.get("words") or {}).get("alert") != "Alerts not checked":
        fails.append(f"conditions: alerts null reads {(t.get('words') or {}).get('alert')!r}")
    if "no alert" in tw.lower() or "no alerts" in json.dumps(p).lower():
        fails.append("conditions: alerts null printed as 'No alerts'")
    if t.get("alerts") is not None:
        fails.append("conditions: alerts null was written as a list")
    if "alert" in (r.get("words") or {}):
        fails.append("conditions: an alert that ends before the window printed an alert word")
    if ((r.get("flags") or {}).get("alert") or {}).get("on") is not False or (r.get("flags") or {}).get("any"):
        fails.append("conditions: an alert that ends before the window still sets the flag")
    # college
    iu = G.get("iu") or {}
    if iu.get("status") != "forecast" or (iu.get("stadium") or {}).get("espn_venue_id") != "3830":
        fails.append(f"conditions: Indiana's exact venue name did not match ({iu.get('status')!r})")
    if (iu.get("words") or {}).get("alert") != "Wind Advisory":
        fails.append("conditions: an alert is not worded in the NWS's own event name")
    if (G.get("near") or {}).get("status") != "missing":
        fails.append("conditions: a near venue name matched a row")
    # final
    old = dict(t, status="forecast", words={"temp": "61°"})
    over = {"3937": (200, {"venue": "3937", "roof": "open", "in_range": False,
                           "in_range_from": None, "reason": "over"})}
    p3, _c3, _l3 = _run([games[0]], over, published={"thu": old})
    f = p3["games"].get("thu") or {}
    if f.get("status") != "forecast" or (f.get("words") or {}).get("temp") != "61°" or not f.get("record"):
        fails.append(f"conditions: a final lost its strip ({f.get('status')!r}, {f.get('words')!r})")
    if any(l == "FILE DIFFERS" for l in log):
        fails.append("conditions: the file on disk is not the payload")
    return fails


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    f = conditions_canary()
    for x in f:
        print("FAIL", x)
    print("conditions canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
