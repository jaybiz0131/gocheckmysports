#!/usr/bin/env python3
"""report_canary.py: Sprint S-2b item 3, the conditions report and its share card.

Fixtures only: no Worker, no feed, no model. Each check names the break it exists for and was
seen red first (U-9).

  shape      a flagged game is written up; a game with no flags is one line; indoor, outside NWS
             coverage and not-yet-in-range games are listed by name; a missing venue is absent
  means      the write-up says what the numbers usually mean: wind and the passing game, rain and
             the ball, cold and the kicking
  stamp      the report carries the NWS stamp with the forecasts' issued times in ET
  gate       the gate goes red on an em dash, a pick or betting word, a mention of AI, a number the
             game's own data does not hold, and a quiet game written up; the clean report is green
  card       the share card is a square image carrying both marks and a row per NFL game
  freeze     a run inside the Sunday freeze publishes nothing; Sunday morning and Saturday do
  slot       the home's slot holds this week's newest report and is empty with only last week's

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import copy
import datetime
import os
import tempfile

UTC = datetime.timezone.utc


def _e(status="forecast", flags=None, alerts=(), roof="open", temp=47, feels=42, wind="12 mph down the field, gusting 23",
       wind_mph=12, pop=23, ptype="rain showers", sky="Slight Chance Rain Showers", gen="2026-10-15T11:02:00+00:00"):
    import conditions as cx
    f = {"wind": {"on": False, "max_mph": wind_mph}, "precip": {"on": False, "max_pct": pop},
         "feels": {"on": False, "below_f": 32, "above_f": 90, "min_f": feels, "max_f": temp},
         "alert": {"on": bool(alerts), "count": len(alerts or [])}}
    for k, v in (flags or {}).items():
        f[k].update(v)
    f["any"] = any(f[k]["on"] for k in ("wind", "precip", "feels", "alert"))
    e = {"status": status, "roof": roof, "stadium": {"name": "Field X", "orientation_deg": 0},
         "kickoff_hour": {"temp_f": temp, "feels_like_f": feels, "wind_mph": wind_mph, "pop_pct": pop,
                          "precip_type": ptype, "sky": sky,
                          "wind": {"text": wind, "arrow_true_deg": 200, "arrow_field_deg": 20}},
         "hours": [], "flags": f, "alerts": list(alerts) if alerts is not None else None,
         "nws": {"generated_at": gen}}
    if status != "forecast":
        e = {"status": status, "roof": roof, "stadium": {"name": "Dome Y"},
             "in_range_from": "2026-10-17T03:00:00Z"}
    e["words"] = cx.words(e)
    return e


def _g(gid, a, h, kick, league="NFL", venue="Field X"):
    return {"id": gid, "league": league, "start_utc": kick, "venue": venue,
            "away": {"abbr": a, "name": a.title()}, "home": {"abbr": h, "name": h.title()}}


def fixture():
    games = [_g("1", "SEA", "DEN", "2026-10-16T00:15Z"),
             _g("2", "PIT", "TB", "2026-10-18T17:00Z"),
             _g("3", "BUF", "LV", "2026-10-18T20:25Z", venue="Dome Y"),
             _g("4", "HOU", "JAX", "2026-10-18T13:30Z", venue="Wembley Stadium"),
             _g("5", "DAL", "GB", "2026-10-19T00:20Z"),
             _g("6", "NYG", "CHI", "2026-10-22T00:15Z"),
             _g("7", "OSU", "IU", "2026-10-17T16:00Z", league="CFB"),
             _g("8", "MIA", "BUF", "2026-10-19T17:00Z")]
    data = {"games": {
        "1": _e(flags={"wind": {"on": True, "max_mph": 17}, "precip": {"on": True, "max_pct": 57}},
                gen="2026-10-15T11:02:00+00:00"),
        "2": _e(flags={"feels": {"on": True, "min_f": 28}}, temp=34, feels=29, wind="Calm", wind_mph=3, pop=0,
                ptype=None, alerts=[{"event": "Wind Chill Advisory", "ends": "2026-10-18T22:00:00Z"}],
                gen="2026-10-15T11:40:00+00:00"),
        "3": _e(status="indoor"),
        "4": _e(status="outside_nws"),
        "5": _e(),
        "6": _e(status="out_of_range"),
        "7": _e(flags={"wind": {"on": True, "max_mph": 22}}, wind="20 mph across the field", wind_mph=20, pop=5),
        "8": {"status": "missing", "words": {}},
    }}
    return games, data


def check():
    import conditions_report as cr
    import site_build as sb
    fails = []
    games, data = fixture()
    now = datetime.datetime(2026, 10, 15, 11, 17, tzinfo=UTC)
    rep = cr.write(games, data, now)
    # shape
    heads = [f["head"] for f in rep["flagged"]]
    if [f["id"] for f in rep["flagged"]] != ["1", "2", "7"]:
        fails.append(f"report: the written-up games are {[f['id'] for f in rep['flagged']]}, expected 1, 2, 7 "
                     "(the flagged games, in board order)")
    if [q["id"] for q in rep["quiet"]] != ["5"]:
        fails.append(f"report: the one-line games are {[q['id'] for q in rep['quiet']]}, expected 5")
    if not any("Buf at Lv" in x for x in rep["indoor"]) or not any("Wembley" in x for x in rep["outside"]) \
            or not any("Forecast from" in x for x in rep["later"]):
        fails.append("report: indoor, outside NWS coverage or not-yet-in-range is not listed")
    whole = cr.as_text(rep)
    if "Mia at Buf" in whole:
        fails.append("report: a missing venue is printed")
    if rep["id"] != "2026-10-15-thu" or "Thursday Oct 15" not in rep["title"]:
        fails.append(f"report: the Thursday run is {rep['id']!r} / {rep['title']!r}")
    # means
    b1 = rep["flagged"][0]["body"] if rep["flagged"] else ""
    b2 = next((f["body"] for f in rep["flagged"] if f["id"] == "2"), "")
    if "passing game" not in b1 or "ball slick" not in b1 or "17 mph" not in b1 or "57 percent" not in b1:
        fails.append("report: the wind and rain write-up lacks its numbers or what they usually mean")
    if "kicks shorter" not in b2 or "28 degrees" not in b2 or "Wind Chill Advisory" not in b2:
        fails.append("report: the cold write-up lacks its number, the kicking, or the alert")
    # stamp
    if rep["stamp"] != ("Conditions by GoCheckMyWeather, from the National Weather Service. Forecasts issued "
                        "7:02 AM to 7:40 AM ET Thursday, Oct 15."):
        fails.append(f"report: the stamp reads {rep['stamp']!r}")
    # gate
    g0 = cr.gate(rep)
    if g0:
        fails.append(f"report: the clean report fails its own gate: {g0[:2]}")

    def bad(mut, name):
        r = copy.deepcopy(rep)
        try:
            mut(r)
        except (IndexError, KeyError) as ex:
            fails.append(f"report gate: the {name} case could not be built ({type(ex).__name__}), "
                         "so the report's shape is wrong")
            return
        if not cr.gate(r):
            fails.append(f"report gate: {name} passed")
    bad(lambda r: r["flagged"][0].update(body=r["flagged"][0]["body"] + " Wind — strong."), "an em dash")
    bad(lambda r: r["flagged"][0].update(body=r["flagged"][0]["body"] + " Take the under."), "a pick")
    bad(lambda r: r.update(lead=r["lead"] + " Written by AI."), "a mention of AI")
    bad(lambda r: r["flagged"][0].update(body=r["flagged"][0]["body"].replace("17 mph", "27 mph")), "a smuggled number")
    bad(lambda r: r["quiet"][0].update(line=r["quiet"][0]["line"] + " Rain is likely. Kicks shorten."),
        "a quiet game written up")
    bad(lambda r: r.update(stamp="Conditions by GoCheckMyWeather."), "a missing NWS stamp")
    # card
    tmp = tempfile.mkdtemp()
    try:
        from PIL import Image
        p = cr.share_card(rep, os.path.join(tmp, "c.png"))
        im = Image.open(p).convert("RGB")
        if im.size[0] != im.size[1]:
            fails.append(f"report card: {im.size} is not square")
        W = im.size[0]
        def ink(box):
            cols = im.crop(box).getcolors(maxcolors=1 << 20) or []
            return sum(n for n, c in cols if c[0] + c[1] + c[2] > 300)
        if ink((40, 30, W // 2, 100)) < 200 or ink((W // 2, 30, W - 40, 100)) < 200:
            fails.append("report card: a mark is missing (GoCheckMySports left, GoCheckMyWeather right)")
        if len(rep.get("board") or []) != 7:
            fails.append(f"report card: {len(rep.get('board') or [])} rows, expected the 7 NFL games with an entry")
        # S-2d item 2: the wall's look. A green panel in a darker green frame; one row per game with a
        # bulb lit exactly where a flag is on; the wind yellow exactly where the wind flag is on.
        if im.getpixel((W // 2, 210)) != (14, 59, 42) or im.getpixel((29, W // 2)) != (7, 38, 25):
            fails.append("report card: the card is not a green panel in a darker green frame")
        rows = rep.get("board") or []
        rh = min(54, (W - 150 - 220) // max(1, len(rows)))
        yellow = lambda px: px[0] > 230 and px[1] > 190 and px[2] < 120
        for i, r in enumerate(rows):
            cy = 220 + i * rh + (rh - 8) // 2
            lit = bool(r.get("any") or r.get("alert"))
            if yellow(im.getpixel((74, cy))) != lit:
                fails.append(f"report card: {r['away']} at {r['home']}'s bulb is {'off' if lit else 'lit'}, "
                             f"its flags say {'lit' if lit else 'off'}")
            wind = im.crop((722, cy - 14, 862, cy + 14)).getcolors(maxcolors=1 << 16) or []
            has_y = sum(n for n, c in wind if yellow(c)) > 20
            if r.get("status") == "forecast" and has_y != bool(r.get("wind_on")):
                fails.append(f"report card: {r['away']} at {r['home']}'s wind is "
                             f"{'yellow' if has_y else 'cream'} and its wind flag is {'on' if r.get('wind_on') else 'off'}")
    except ImportError:
        fails.append("report card: Pillow is not installed, so the card was not drawn")
    # freeze
    sun1 = datetime.datetime(2026, 10, 18, 17, 0, tzinfo=UTC)    # 1:00 PM EDT
    sun6 = datetime.datetime(2026, 10, 18, 10, 17, tzinfo=UTC)   # 6:17 AM EDT
    sat1 = datetime.datetime(2026, 10, 17, 17, 0, tzinfo=UTC)
    if not cr.in_freeze(sun1) or cr.in_freeze(sun6) or cr.in_freeze(sat1):
        fails.append("report: the Sunday freeze is not 12:30 to 8:30 PM ET on Sundays only")
    # slot
    was = (sb.CR_REPORTS, sb._NOW_CACHE)
    try:
        sb._NOW_CACHE = datetime.datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
        old = dict(rep, id="2026-10-10-sat", written_at="2026-10-10T21:17:00Z", title="Old one")
        sb.CR_REPORTS = [old]
        if sb.cr_slot(sb.cr_latest()):
            fails.append("report slot: last week's report fills this week's slot")
        sb.CR_REPORTS = [old, rep]
        html = sb.cr_slot(sb.cr_latest())
        if rep["title"] not in html or f'/conditions/{rep["id"]}.html' not in html:
            fails.append("report slot: this week's report is not in the slot with its link")
    finally:
        sb.CR_REPORTS, sb._NOW_CACHE = was
    return fails


def report_canary():
    return check()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    f = report_canary()
    for x in f:
        print("FAIL", x)
    print("report canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
