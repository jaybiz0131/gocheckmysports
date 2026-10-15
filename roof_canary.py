#!/usr/bin/env python3
"""roof_canary.py: Sprint S-3a, Jack's ruling of 15 October 2026 (evening) on roofed stadiums.

A game at a stadium with a roof (Mercedes-Benz Stadium and every venue the stadium table marks
retractable or fixed) is played under a roof the team decides about. The weather outside is not the
game's weather, so it never lights a bulb and never colours a wind plate yellow, on the card, the
schedule row, the wall, the share card and the conditions log. Its plates read like the dome rows,
"Roof . usually closed", or the venue's published state when the data carries one.

THE ROOF FIELD DRIVES IT, NOT A NAME LIST. Each check below plants the same stadium name with a
different roof value, so a name list passes the first and fails the second.

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
UTC = datetime.timezone.utc
USUALLY = "Roof · usually closed"


def _flags(wind=False, alert=False):
    f = {"wind": {"on": wind, "max_mph": 22, "threshold_mph": 15}, "precip": {"on": False, "max_pct": 5},
         "feels": {"on": False, "min_f": 50, "max_f": 60, "below_f": 32, "above_f": 90},
         "alert": {"on": alert, "count": 1 if alert else 0}}
    f["any"] = wind or alert
    return f


def _forecast(roof, name="Mercedes-Benz Stadium", wind=True, alert=False, **extra):
    e = {"status": "forecast", "roof": roof, "league": "NFL", "venue": name,
         "stadium": {"name": name, "roof": roof, "slug": "x", "orientation_deg": None},
         "kickoff_hour": {"temp_f": 58, "feels_like_f": 58, "pop_pct": 0, "wind_mph": 22, "gust_mph": 30, "wind_dir": "E",
                          "sky": "Sunny", "precip_type": None,
                          "wind": {"text": "22 mph from the E", "arrow_true_deg": 90, "arrow_field_deg": 0}},
         "hours": [], "flags": _flags(wind, alert),
         "alerts": [{"event": "Wind Advisory"}] if alert else [],
         "credit": {"text": "Conditions by GoCheckMyWeather, NWS, 9:00 AM ET", "url": "https://gocheckmyweather.com/stadiums/x.html"},
         "window": {"from": "2026-10-18T16:00:00Z"}, "nws": {"generated_at": "2026-10-15T12:00:00+00:00"}}
    e.update(extra)
    return e


def _game(gid="1", venue="Mercedes-Benz Stadium"):
    return {"id": gid, "league": "NFL", "state": "pre", "start_utc": "2026-10-18T17:00Z", "network": "FOX", "venue": venue,
            "away": {"abbr": "CHI", "id": "3", "name": "Bears", "full": "Chicago Bears", "record": "3-2"},
            "home": {"abbr": "ATL", "id": "1", "name": "Falcons", "full": "Atlanta Falcons", "record": "2-3"}}


def check():
    fails = []
    import conditions as cx
    import site_build as sb
    import teams
    import conditions_report as cr

    # data layer: the roof field decides, whatever the stadium is called
    for roof, name, want in (("retractable", "Anywhere Dome Field", "roofed"), ("fixed", "Open Air Park", "roofed"),
                             ("open", "Mercedes-Benz Stadium", "forecast")):
        e = cx.roofed_entry(_forecast(roof, name))
        if e.get("status") != want:
            fails.append(f"roof: roof {roof!r} at {name!r} reads status {e.get('status')!r}, expected {want!r}")
    e = cx.roofed_entry(_forecast("retractable", wind=True, alert=True))
    if (e.get("flags") or {}).get("any") or any((e.get("flags") or {}).get(k, {}).get("on") for k in ("wind", "alert")) or e.get("alerts"):
        fails.append("roof: a roofed game still carries a lit flag or an alert")
    if (e.get("words") or {}).get("line") != USUALLY:
        fails.append(f"roof: the roofed words are {(e.get('words') or {}).get('line')!r}, expected {USUALLY!r}")
    for state, want in (("open", "Roof · open"), ("closed", "Roof · closed")):
        e2 = cx.roofed_entry(_forecast("retractable", roof_state=state))
        if (e2.get("words") or {}).get("line") != want:
            fails.append(f"roof: a published roof state {state!r} reads {(e2.get('words') or {}).get('line')!r}, expected {want!r}")
    if (cx.roofed_entry(_forecast("open", wind=True)).get("flags") or {}).get("any") is not True:
        fails.append("roof: an open-air game lost its flags")

    was = (sb.CX_DATA, sb._NOW_CACHE, sb.W2W_DATA, sb.BOARD_IDS)
    try:
        sb._NOW_CACHE = datetime.datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
        sb.W2W_DATA = None
        sb.BOARD_IDS = {"1", "2"}
        # the same game, once with a roof and once open: the card must differ only by the roof field
        sb.CX_DATA = {"games": {"1": _forecast("retractable", wind=True, alert=True),
                                "2": _forecast("open", "Mercedes-Benz Stadium", wind=True, alert=True)}}
        roofed, openair = sb.sbc_card(_game("1"), {}, ticket=True), sb.sbc_card(_game("2"), {}, ticket=True)
        if "sbc-lit" in roofed or re.search(r'sbc-bulb on', roofed) or "sbc-w on" in roofed or "on\">22" in roofed:
            fails.append("roof: the card of a roofed game lights a bulb or a plate")
        if USUALLY.lower() not in roofed.lower():
            fails.append("roof: the card of a roofed game does not read like a dome row")
        if "sbc-lit" not in openair:
            fails.append("roof: the open-air twin at the same stadium name is not lit, so a name list is in the way")
        # the wall
        row1 = sb.wall_row(_game("1"))
        row2 = sb.wall_row(_game("2"))
        if "wl-lit" in row1 or "wl-bulb on" in row1 or "wl-w on" in row1 or "wl-alert" in row1:
            fails.append("roof: the wall row of a roofed game is lit, yellow or carries an alert note")
        if f'<span class="wl-pl wl-one">{USUALLY}</span>' not in row1:
            fails.append("roof: the wall row of a roofed game is not one plate like a dome")
        if "wl-lit" not in row2:
            fails.append("roof: the open-air wall row at the same stadium name is not lit")
        # the schedule row
        wx1, lit1 = sb._tms_wx("1")
        wx2, lit2 = sb._tms_wx("2")
        if lit1 or "on" in re.findall(r'class="tms-pl([^"]*)"', wx1) or USUALLY not in wx1:
            fails.append("roof: the schedule row of a roofed game is lit or does not read like a dome")
        if not lit2:
            fails.append("roof: the open-air schedule row at the same stadium name is not lit")
    finally:
        sb.CX_DATA, sb._NOW_CACHE, sb.W2W_DATA, sb.BOARD_IDS = was

    # the log
    if teams.log_entry(_game("1"), _forecast("retractable", wind=True, alert=True)):
        fails.append("roof: a roofed game is in the conditions log")
    if not teams.log_entry(_game("2"), _forecast("open", wind=True)):
        fails.append("roof: an open-air game at the same stadium name is not in the conditions log")

    # the share card and the report
    g1, g2 = _game("1"), _game("2")
    row = cr.card_row(g1, cx.roofed_entry(_forecast("retractable", wind=True, alert=True)))
    if row.get("any") or row.get("alert") or row.get("wind_on") or row.get("status") != "roofed":
        fails.append(f"roof: the share card's row for a roofed game is lit or still a forecast ({row.get('status')!r})")
    games = [g1, g2]
    data = {"games": {"1": cx.roofed_entry(_forecast("retractable", wind=True)), "2": cx.roofed_entry(_forecast("open", wind=True))}}
    rep = cr.write(games, data, datetime.datetime(2026, 10, 15, 15, 0, tzinfo=UTC))
    if [f["id"] for f in rep["flagged"]] != ["2"]:
        fails.append(f"roof: the report writes up {[f['id'] for f in rep['flagged']]}, expected only the open-air game")
    if not any("Chicago Bears at Atlanta Falcons" in x or "Bears at Falcons" in x or "Chi at Atl" in x or "at Atlanta" in x for x in rep["indoor"]):
        fails.append("roof: the report does not list the roofed game with the indoor ones")
    if cr.gate(rep):
        fails.append(f"roof: the report's gate fails on a roofed game: {cr.gate(rep)[:2]}")
    return fails


def roof_canary():
    return check()


if __name__ == "__main__":
    f = roof_canary()
    for x in f:
        print("FAIL", x)
    print("roof canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
