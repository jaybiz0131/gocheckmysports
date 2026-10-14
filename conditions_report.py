#!/usr/bin/env python3
"""conditions_report.py: the desk's one piece a day, the conditions report (S-2b item 3).

Program 7 (12 October 2026): the report names the games the weather will touch, says what the
numbers are and what they usually mean, carries the NWS stamp, and is a fact page: no picks and
no betting advice. It runs Thursday morning, then Saturday evening and Sunday morning to refresh
(.github/workflows/conditions-report.yml).

WRITTEN FROM THE NUMBERS, NOT BY A MODEL. Every sentence is a template filled from the
conditions Worker's answer for one game (conditions.py) and the schedule. Nothing here calls a
model (U-4), so a dry run costs nothing and the words cannot say a number the Worker did not
give. The gate below holds that: every number in a game's paragraph must be one of that game's
own numbers.

A GAME WITH NO FLAGS IS ONE LINE. A flagged game (the Worker's flags: wind 15 mph and over, a
40 percent chance of precipitation and over, a feel below 32 or above 90, an alert) gets a
paragraph. Indoor games, games outside NWS coverage and games not yet in range are listed by
name. A game whose stadium the table cannot place prints nothing, as on the cards.

OUTPUT. One file per run, site/reports/conditions/<date>-<slot>.json. The build renders the
newest into the home's report slot and every one at /conditions/<id>.html, with its share card.

USAGE
  python3 conditions_report.py --dry-run [--out DIR]   write the report and its card to DIR
                                                        (default: a temp dir), print the text;
                                                        publishes nothing
  python3 conditions_report.py --publish               write site/reports/conditions/<id>.json
                                                        (the workflow commits and pushes it)
"""

import argparse
import datetime
import json
import os
import re
import sys
import tempfile
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ET = ZoneInfo("America/New_York")
REPORTS = os.path.join(HERE, "site", "reports", "conditions")
SLOTS = {3: "thu", 5: "sat", 6: "sun"}          # weekday -> slot; any other day is "extra"
SLOT_NAME = {"thu": "Thursday", "sat": "Saturday", "sun": "Sunday", "extra": ""}

# What the numbers usually mean, in the desk's plain words. One sentence each, never a pick.
MEANS = {
    "wind": "Sustained wind of 15 mph or more usually shortens the deep passing game and long "
            "field goals and punts, and makes kicks drift.",
    "wind_along": "Wind down the field helps the team going with it and costs the team going "
                  "into it, and the teams swap ends each quarter.",
    "precip": "Rain makes the ball slick: snaps, handoffs and catches get harder, footing goes, "
              "and kickers lose distance.",
    "cold": "Cold air makes the ball harder and kicks shorter, and hands go numb on catches.",
    "heat": "Heat wears players down over four quarters, which shows late in the game.",
}

BETTING = re.compile(r"\b(bet|bets|betting|wager\w*|picks?|lock|fade|parlay|take the (?:over|under)|"
                     r"hammer|sharps?|cover(?:s|ed)? the|odds|spread|moneyline|underdog|favorite)\b", re.I)
NOT_AI = re.compile(r"\b(AI|artificial intelligence|model|language model|GPT|Claude)\b")


# ---- the schedule and the numbers -----------------------------------------------------------

def _dt(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None


def _clock(d):
    t = d.astimezone(ET)
    return f'{t.strftime("%I").lstrip("0")}:{t.strftime("%M %p")}'


def when_et(g):
    d = _dt(g.get("start_utc") or "")
    return f'{d.astimezone(ET).strftime("%a")} {_clock(d)} ET' if d else ""


def matchup(g):
    a, h = g.get("away") or {}, g.get("home") or {}
    return f'{a.get("name") or a.get("abbr")} at {h.get("name") or h.get("abbr")}'


def board(now):
    """The week board's games and their conditions, as the build sees them."""
    import scoreboard
    import site_build as sb
    import conditions as cx
    sb._NOW_CACHE = now
    try:
        scoreboard.refresh()
    except Exception as e:
        print(f"conditions report: scoreboard refresh failed ({type(e).__name__}); using the file")
    sbd = scoreboard.load()
    games = [g for _k, g in sb.board_games(sbd)]
    data = cx.refresh(games, now=now)
    return games, data


# ---- the words ------------------------------------------------------------------------------

def _n(v):
    return None if v is None else round(v)


def paragraph(g, e):
    """The write-up for one flagged game: what the numbers are, then what they usually mean."""
    k = e.get("kickoff_hour") or {}
    f = e.get("flags") or {}
    st = e.get("stadium") or {}
    s = []
    head = f'{matchup(g)}, {when_et(g)}, {st.get("name") or g.get("venue") or ""}.'
    t = _n(k.get("temp_f"))
    if t is not None:
        line = f"At kickoff it is forecast {t} degrees"
        fl = _n(k.get("feels_like_f"))
        if fl is not None and fl != t:
            line += f", feeling like {fl}"
        sky = (k.get("sky") or "").lower()
        s.append(line + (f", {sky}." if sky else "."))
    if e.get("roof") == "retractable":
        s.append("The stadium has a retractable roof, and whether it is open is the team's call.")
    w = (f.get("wind") or {})
    if w.get("on"):
        txt = (k.get("wind") or {}).get("text") or ""
        mx = _n(w.get("max_mph"))
        bit = f"The wind at kickoff is {txt}" if txt and txt != "Calm" else "The wind is calm at kickoff"
        if mx is not None and mx > (_n(k.get("wind_mph")) or 0):
            bit += f", and the forecast reaches {mx} mph during the game"
        s.append(bit + ".")
        s.append(MEANS["wind"])
        if "down the field" in txt:
            s.append(MEANS["wind_along"])
    p = f.get("precip") or {}
    if p.get("on"):
        typ = " and ".join((k.get("precip_type") or "precipitation").split(", "))
        at, mx = _n(k.get("pop_pct")), _n(p.get("max_pct"))
        bit = f"The chance of {typ} is {at} percent at kickoff" if at is not None else f"There is a chance of {typ}"
        if mx is not None and mx != at:
            bit += f" and {mx} percent at its highest during the game"
        s.append(bit + ".")
        s.append(MEANS["precip"])
    fe = f.get("feels") or {}
    if fe.get("on"):
        lo, hi = _n(fe.get("min_f")), _n(fe.get("max_f"))
        if lo is not None and lo < (fe.get("below_f") or 32):
            s.append(f"It feels as cold as {lo} degrees during the game.")
            s.append(MEANS["cold"])
        elif hi is not None and hi > (fe.get("above_f") or 90):
            s.append(f"It feels as hot as {hi} degrees during the game.")
            s.append(MEANS["heat"])
    for a in (e.get("alerts") or [])[:2]:
        until = _dt(a.get("ends") or a.get("expires") or "")
        u = f', until {until.astimezone(ET).strftime("%a")} {_clock(until)} ET' if until else ""
        s.append(f'The National Weather Service has a {a.get("event")} in force over the stadium{u}.')
    if e.get("alerts") is None:
        s.append("Alerts for the stadium could not be checked at this reading.")
    return head, " ".join(s)


def quiet_line(g, e):
    w = e.get("words") or {}
    wind = w.get("wind")
    bits = [w.get("temp"), "calm" if wind == "Calm" else wind, w.get("precip")]
    if e.get("roof") == "retractable":
        bits.append("retractable roof")
    return f'{matchup(g)}, {when_et(g)}: {", ".join(b for b in bits if b)}.'


def _stamp(data, games):
    """The NWS stamp: the range of the forecasts' own generated times, in ET."""
    ts = sorted(d for d in (_dt(((data["games"].get(str(g.get("id"))) or {}).get("nws") or {}).get("generated_at"))
                            for g in games) if d)
    if not ts:
        return "Conditions by GoCheckMyWeather, from the National Weather Service."
    a, b = ts[0].astimezone(ET), ts[-1].astimezone(ET)
    day = a.strftime("%A, %b ") + str(a.day)
    span = _clock(a) + " ET" if _clock(a) == _clock(b) else f"{_clock(a)} to {_clock(b)} ET"
    return (f"Conditions by GoCheckMyWeather, from the National Weather Service. Forecasts issued "
            f"{span} {day}.")


def write(games, data, now):
    """The report as a dict: title, lead, the write-ups, the one-liners, the stamp."""
    et = now.astimezone(ET)
    slot = SLOTS.get(et.weekday(), "extra")
    rid = f"{et.date().isoformat()}-{slot}"
    G = data.get("games") or {}
    flagged, quiet, indoor, outside, later = [], [], [], [], []
    leagues = {}
    for g in games:
        e = G.get(str(g.get("id")))
        if not e:
            continue
        st = e.get("status")
        if st == "forecast" and (e.get("flags") or {}).get("any"):
            head, body = paragraph(g, e)
            flagged.append({"id": str(g["id"]), "league": g.get("league"), "head": head, "body": body,
                            "href": f'/games/{g["id"]}.html'})
        elif st == "forecast":
            quiet.append({"id": str(g["id"]), "league": g.get("league"), "line": quiet_line(g, e),
                          "href": f'/games/{g["id"]}.html'})
        elif st == "indoor":
            indoor.append(f'{matchup(g)}, {when_et(g)}, {(e.get("stadium") or {}).get("name") or g.get("venue")}')
        elif st == "outside_nws":
            outside.append(f'{matchup(g)}, {when_et(g)}, {g.get("venue")}')
        elif st == "out_of_range":
            later.append(f'{matchup(g)}, {when_et(g)}: {(e.get("words") or {}).get("line")}')
        if st in ("forecast", "indoor"):
            leagues[g.get("league")] = leagues.get(g.get("league"), 0) + 1
    n_fc = sum(1 for g in games if (G.get(str(g.get("id"))) or {}).get("status") == "forecast")
    title = f"Conditions report, {et.strftime('%A')} {et.strftime('%b')} {et.day}"
    if flagged:
        names = [f["head"].split(",")[0] for f in flagged]
        lead = (f"The weather touches {len(flagged)} of the {n_fc} games with a forecast on this week's board: "
                + ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1] + ".")
    else:
        lead = f"No number that matters in any of the {n_fc} games with a forecast on this week's board."
    return {
        "id": rid, "slot": slot, "date": et.date().isoformat(),
        "written_at": now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "written_et": f'{et.strftime("%a, %b")} {et.day}, {_clock(et)} ET',
        "title": title, "lead": lead,
        "flagged": flagged, "quiet": quiet, "indoor": indoor, "outside": outside, "later": later,
        "stamp": _stamp(data, games),
        "card": f"/share/conditions/{rid}.png",
        "board": [card_row(g, G[str(g["id"])]) for g in games
                  if g.get("league") == "NFL" and G.get(str(g.get("id")))][:14],
        "numbers": {str(g["id"]): sorted(game_numbers(g, G.get(str(g["id"])) or {}))
                    for g in games if G.get(str(g.get("id")))},
    }


# ---- the gate -------------------------------------------------------------------------------

def game_numbers(g, e):
    """Every number a game's write-up may say: the Worker's numbers for it, its kickoff time,
    and the numbers in its teams' and stadium's names."""
    out = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            out.add(str(round(v)))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            out.update(re.findall(r"\d+", v))
    walk({k: v for k, v in e.items() if k not in ("hours",)})
    walk(e.get("hours"))
    walk([when_et(g), matchup(g), g.get("venue") or ""])
    for a in e.get("alerts") or []:
        until = _dt(a.get("ends") or a.get("expires") or "")
        if until:
            out.update(re.findall(r"\d+", _clock(until)))
    out.update({"15", "40", "32", "90", "4"})     # the thresholds and "four quarters", in MEANS
    return out


def banned():
    """publicist.BANNED, read from its source: importing publicist imports the model client,
    and this job imports none."""
    import ast
    tree = ast.parse(open(os.path.join(HERE, "publicist.py"), encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "BANNED" for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("publicist.BANNED not found")


def gate(rep):
    """The copy law and the facts. Returns failure strings; empty means it may publish."""
    fails = []
    texts = [rep["title"], rep["lead"], rep["stamp"]] + [f["head"] + " " + f["body"] for f in rep["flagged"]] \
        + [q["line"] for q in rep["quiet"]] + rep["indoor"] + rep["outside"] + rep["later"]
    whole = "\n".join(texts)
    for pat in banned():
        if re.search(pat, whole, re.I):
            fails.append(f"copy law: banned pattern [{pat}]")
    m = BETTING.search(whole)
    if m:
        fails.append(f"no picks: the report says {m.group(0)!r}")
    m = NOT_AI.search(whole)
    if m:
        fails.append(f"no mention of AI: the report says {m.group(0)!r}")
    if "National Weather Service" not in rep["stamp"]:
        fails.append("the NWS stamp is missing")
    for f in rep["flagged"]:
        allowed = set(rep["numbers"].get(f["id"]) or [])
        for n in re.findall(r"\d+", f["head"] + " " + f["body"]):
            if n not in allowed:
                fails.append(f"facts: {f['head'].split(',')[0]} says {n}, which is not one of its numbers")
    for q in rep["quiet"]:
        if q["line"].count(".") > 1 or len(q["line"]) > 160:
            fails.append(f"a game with no flags is written up, not one line: {q['line'][:60]}")
    flagged_ids = {f["id"] for f in rep["flagged"]}
    if flagged_ids & {q["id"] for q in rep["quiet"]}:
        fails.append("a game is both written up and listed")
    return fails


# ---- the share card -------------------------------------------------------------------------

def card_row(g, e):
    """What the share card draws for one NFL game, kept in the report so the build can draw it."""
    dd = _dt(g.get("start_utc") or "")
    k, f = e.get("kickoff_hour") or {}, e.get("flags") or {}
    return {"id": str(g.get("id")), "away": (g.get("away") or {}).get("abbr"),
            "home": (g.get("home") or {}).get("abbr"),
            "when": f'{dd.astimezone(ET).strftime("%a")} {_clock(dd)}' if dd else "",
            "status": e.get("status"), "words": e.get("words") or {}, "roof": e.get("roof"),
            "arrow_true_deg": (k.get("wind") or {}).get("arrow_true_deg"),
            "any": bool(f.get("any")), "alert": bool(e.get("alerts")),
            "wind_on": bool((f.get("wind") or {}).get("on")),
            "precip_on": bool((f.get("precip") or {}).get("on"))}


def share_card(rep, out_path):
    """A square image of the week's weather board: the NFL games in kickoff order, each with the
    temperature, the wind arrow and speed, the chance of precipitation, the venue flag; flagged
    numbers lit. Both marks. Drawn with the site's own fonts."""
    from PIL import Image, ImageDraw
    import math
    import share_cards as sc
    S = 1080
    BG, CARD, LIGHT, MUTE, SUN, RED = (19, 20, 25), (26, 28, 34), (235, 233, 227), (195, 199, 206), (255, 213, 105), (240, 135, 127)
    im = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, S, 10], fill=(31, 94, 63))
    d.text((56, 40), "GoCheckMySports", font=sc._serif(40), fill=LIGHT)
    mk = "GoCheckMyWeather"
    d.text((S - 56 - d.textlength(mk, font=sc._serif(40)), 40), mk, font=sc._serif(40), fill=(121, 184, 190))
    d.text((56, 104), "The weather at kickoff", font=sc._mono(30, True), fill=LIGHT)
    d.text((56, 146), rep["title"].replace("Conditions report, ", "NFL, ").upper(), font=sc._mono(22), fill=MUTE)
    leg = "Arrows point the way the wind blows, north up"
    d.text((S - 56 - d.textlength(leg, font=sc._mono(19)), 150), leg, font=sc._mono(19), fill=MUTE)
    y, rh = 196, 56
    for r in rep.get("board") or []:
        st, w = r.get("status"), r.get("words") or {}
        d.rounded_rectangle([40, y, S - 40, y + rh - 8], radius=8, fill=CARD)
        if r.get("any") or r.get("alert"):
            d.rectangle([40, y, 46, y + rh - 8], fill=RED if r.get("alert") else SUN)
        d.text((62, y + 12), f'{r.get("away")} at {r.get("home")}', font=sc._mono(24, True), fill=LIGHT)
        d.text((250, y + 14), r.get("when") or "", font=sc._mono(20), fill=MUTE)
        x = 470
        if st == "forecast":
            d.text((x, y + 10), w.get("temp", ""), font=sc._mono(28, True), fill=LIGHT)
            x += 90
            # north up on every row: the card draws no field, so a field-relative angle would
            # be read in the wrong frame
            deg = r.get("arrow_true_deg")
            if deg is not None and w.get("wind") != "Calm":
                cx_, cy_, rad = x + 18, y + 24, 16
                ang = math.radians(deg)
                dx, dy = math.sin(ang), -math.cos(ang)
                tip = (cx_ + dx * rad, cy_ + dy * rad)
                tail = (cx_ - dx * rad, cy_ - dy * rad)
                col = SUN if r.get("wind_on") else LIGHT
                d.line([tail, tip], fill=col, width=4)
                px, py = -dy, dx
                d.polygon([tip, (tip[0] - dx * 11 + px * 7, tip[1] - dy * 11 + py * 7),
                           (tip[0] - dx * 11 - px * 7, tip[1] - dy * 11 - py * 7)], fill=col)
            sp = (w.get("wind") or "").split(" mph")[0]
            d.text((x + 46, y + 12), (sp + " mph") if sp.isdigit() else "calm", font=sc._mono(24, True),
                   fill=SUN if r.get("wind_on") else LIGHT)
            pct = (w.get("precip") or "").split("%")[0]
            d.text((x + 200, y + 12), f"{pct}%" if pct.isdigit() else "", font=sc._mono(24, True),
                   fill=SUN if r.get("precip_on") else LIGHT)
            tag = (w.get("alert") if r.get("alert") else ("Retractable" if r.get("roof") == "retractable" else ""))
            d.text((x + 300, y + 14), sc._fit(d, tag or "", sc._mono(19), S - 60 - (x + 300)), font=sc._mono(19),
                   fill=RED if r.get("alert") else MUTE)
        else:
            d.text((x, y + 14), (w.get("line") or "").replace("Forecast from", "From"), font=sc._mono(22), fill=MUTE)
        y += rh
    d.text((56, S - 92), sc._fit(d, rep["stamp"].replace("Conditions by GoCheckMyWeather, from the ", "From the "),
                                 sc._mono(17), S - 112), font=sc._mono(17), fill=MUTE)
    d.text((56, S - 58), "gocheckmysports.com  ·  gocheckmyweather.com", font=sc._mono(20, True), fill=LIGHT)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "PNG", optimize=True)
    return out_path


# ---- the text, for a dry run ----------------------------------------------------------------

def as_text(rep):
    out = [rep["title"], f'Written {rep["written_et"]}', "", rep["lead"], ""]
    for f in rep["flagged"]:
        out += [f["head"], f["body"], ""]
    if rep["quiet"]:
        out.append("The rest, with no number that matters:")
        out += [f"  {q['line']}" for q in rep["quiet"]] + [""]
    if rep["indoor"]:
        out.append("Indoors: " + "; ".join(rep["indoor"]) + ".")
    if rep["outside"]:
        out.append("Outside NWS coverage: " + "; ".join(rep["outside"]) + ".")
    if rep["later"]:
        out.append("Not yet in range: " + "; ".join(rep["later"]) + ".")
    out += ["", rep["stamp"]]
    return "\n".join(out)


def in_freeze(now):
    """The Sunday freeze, 12:30 to 8:30 PM ET: a late scheduled run publishes nothing."""
    et = now.astimezone(ET)
    return et.weekday() == 6 and (12, 30) <= (et.hour, et.minute) < (20, 30)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if not (a.dry_run or a.publish):
        ap.print_help()
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    if a.publish and in_freeze(now):
        print("conditions report: inside the Sunday freeze (12:30 to 8:30 PM ET); nothing published")
        return 0
    games, data = board(now)
    rep = write(games, data, now)
    fails = gate(rep)
    for f in fails:
        print(f"::error::conditions report gate: {f}")
    if fails:
        return 1
    out = a.out or (tempfile.mkdtemp() if a.dry_run else REPORTS)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f'{rep["id"]}.json')
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, sort_keys=True)
    if a.dry_run:
        card = share_card(rep, os.path.join(out, f'{rep["id"]}.png'))
        print(as_text(rep))
        print(f"\n[dry run: nothing published; report {path}, card {card}]")
    else:
        print(f"conditions report: wrote {os.path.relpath(path, HERE)}, {len(rep['flagged'])} written up, "
              f"{len(rep['quiet'])} in one line")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
