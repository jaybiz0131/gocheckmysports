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
import teams  # noqa: E402  (the team pages' log reads this field; same flags, one definition)
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


def _nfl_week(now):
    """The NFL week this report falls in, from the schedule the build reads; None when unknown."""
    try:
        import build_manifest as bm
        import where_to_watch as w2w
        return bm.week_for(now, (w2w.load() or {}).get("weeks"))
    except Exception:
        return None


def write(games, data, now):
    """The report as a dict: title, lead, the write-ups, the one-liners, the stamp."""
    et = now.astimezone(ET)
    slot = SLOTS.get(et.weekday(), "extra")
    rid = f"{et.date().isoformat()}-{slot}"
    import conditions as _cx
    G = {k: _cx.roofed_entry(v) for k, v in (data.get("games") or {}).items()}   # a roofed stadium reads like a dome
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
        elif st in ("indoor", "roofed"):
            indoor.append(f'{matchup(g)}, {when_et(g)}, {(e.get("stadium") or {}).get("name") or g.get("venue")}'
                          + (f' ({(e.get("words") or {}).get("line", "").lower()})' if st == "roofed" else ""))
        elif st == "outside_nws":
            outside.append(f'{matchup(g)}, {when_et(g)}, {g.get("venue")}')
        elif st == "out_of_range":
            later.append(f'{matchup(g)}, {when_et(g)}: {(e.get("words") or {}).get("line")}')
        if st in ("forecast", "indoor", "roofed"):
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
        "title": title, "lead": lead, "week": _nfl_week(now),
        "flagged": flagged, "quiet": quiet, "indoor": indoor, "outside": outside, "later": later,
        "stamp": _stamp(data, games),
        "card": f"/share/conditions/{rid}.png",
        "log": [x for x in (teams.log_entry(g, G.get(str(g.get("id")))) for g in games) if x],
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
    import conditions as _cx
    e = _cx.roofed_entry(e)
    dd = _dt(g.get("start_utc") or "")
    k, f = e.get("kickoff_hour") or {}, e.get("flags") or {}
    return {"id": str(g.get("id")), "away": (g.get("away") or {}).get("abbr"),
            "home": (g.get("home") or {}).get("abbr"),
            "when": f'{dd.astimezone(ET).strftime("%a")} {_clock(dd)}' if dd else "",
            "status": e.get("status"), "words": e.get("words") or {}, "roof": e.get("roof"),
            "arrow_true_deg": (k.get("wind") or {}).get("arrow_true_deg"),
            "any": bool(f.get("any")), "alert": bool(e.get("alerts")),
            "wind_on": bool((f.get("wind") or {}).get("on")),
            "precip_on": bool((f.get("precip") or {}).get("on")),
            "city": g.get("venue_city") or ""}


# The wall's token set (S-2d item 2). Every square card on this site draws from these nine colors and
# no others: share_card (the week's board) and game_share_card (one game, S-3b.1) both unpack this
# one tuple, and the canary reads the pixels of a drawn card against it.
WALL_PALETTE = ((7, 17, 12), (7, 38, 25), (14, 59, 42), (20, 26, 23),
                (244, 241, 230), (255, 210, 63), (217, 211, 180), (184, 178, 147), (59, 58, 34))


def share_card(rep, out_path):
    """A square image of the week's weather board in the wall's look (S-2d item 2, Jack's ruling of
    14 October 2026, 3:11 PM ET, ScoreboardWall.dc.html): a green scoreboard in a darker frame, one
    row per NFL game in kickoff order, a bulb lit when any of its flags is on, the team plates, the
    kickoff in yellow, then the TEMP, WIND and RAIN plates with the wind yellow when flagged, or one
    plate for a dome or outside coverage. Both sites' names in plain text, no marks. Every number is
    the report's own, so the card cannot say what the page does not."""
    from PIL import Image, ImageDraw
    import re as _re
    import share_cards as sc
    S = 1080
    BG, FRAME, PANEL, PLATE, CREAM, YELLOW, SOFT, MUTE, OFF = WALL_PALETTE
    osw = lambda n: sc._font("Oswald-600.ttf", n)
    im = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([24, 24, S - 24, S - 24], radius=18, fill=FRAME)
    d.rounded_rectangle([34, 34, S - 34, S - 34], radius=12, fill=PANEL)
    d.text((64, 56), "GoCheckMySports", font=sc._mono(20, True), fill=SOFT)
    mk = "GoCheckMyWeather"
    d.text((S - 64 - d.textlength(mk, font=sc._mono(20, True)), 56), mk, font=sc._mono(20, True), fill=SOFT)
    wk = rep.get("week") or (_re.search(r"Week (\d+)", rep.get("title") or "") or [None, None])[1]
    t1 = f"NFL WEEK {wk}" if wk else "NFL"
    d.text((64, 92), t1, font=osw(58), fill=CREAM)
    d.text((64 + d.textlength(t1 + " ", font=osw(58)), 92), "· KICKOFF WEATHER", font=osw(58), fill=YELLOW)
    d.ellipse([64, 182, 80, 198], fill=YELLOW)
    d.text((90, 179), "WEATHER MATTERS", font=sc._mono(17, True), fill=SOFT)
    leg = "TEMP °F · WIND MPH · RAIN %"
    d.text((S - 64 - d.textlength(leg, font=sc._mono(17, True)), 179), leg, font=sc._mono(17, True), fill=SOFT)
    rows = rep.get("board") or []
    top, bottom = 220, S - 150
    rh = min(54, (bottom - top) // max(1, len(rows)))
    ph = rh - 8
    fs = max(20, min(32, ph - 12))

    def plate(x0, x1, y, text, col=CREAM, font=None):
        d.rounded_rectangle([x0, y, x1, y + ph], radius=4, fill=PLATE)
        f = font or osw(fs)
        tw = d.textlength(text, font=f)
        d.text(((x0 + x1 - tw) / 2, y + (ph - fs) / 2 - fs * .12), text, font=f, fill=col)
    y = top
    for r in rows:
        lit = bool(r.get("any") or r.get("alert"))
        cy = y + ph / 2
        d.ellipse([66, cy - 8, 82, cy + 8], fill=YELLOW if lit else OFF)
        plate(100, 210, y, (r.get("away") or "").upper())
        f_at = sc._mono(16, True)
        d.text((236 - d.textlength("AT", font=f_at) / 2, cy - 10), "AT", font=f_at, fill=SOFT)
        plate(262, 372, y, (r.get("home") or "").upper())
        when = _re.sub(r":(\d\d) ([AP])M( ET)?", r":\1\2", (r.get("when") or "")).upper()
        f_w = sc._mono(19, True)
        d.text((466 - d.textlength(when, font=f_w) / 2, cy - 12), when, font=f_w, fill=YELLOW)
        w = r.get("words") or {}
        if r.get("status") == "forecast":
            temp = w.get("temp") or ""
            sp = (w.get("wind") or "").split(" mph")[0]
            wind = sp if sp.isdigit() else ("CALM" if (w.get("wind") or "").startswith("Calm") else "")
            pct = (w.get("precip") or "").split("%")[0]
            rain = f"{pct}%" if pct.isdigit() else ""
            for x0, txt, col in ((572, temp, CREAM), (722, wind, YELLOW if r.get("wind_on") else CREAM),
                                 (872, rain, CREAM)):
                if txt:
                    plate(x0, x0 + 140, y, txt, col)
                else:
                    plate(x0, x0 + 140, y, "missing", SOFT, sc._mono(16))
        else:
            note = {"indoor": "DOME", "outside_nws": (r.get("city") or "OUTSIDE NWS").upper(),
                    "roofed": (w.get("line") or "ROOF").upper()}.get(
                r.get("status"), (w.get("line") or "").upper())
            plate(572, 1012, y, note, MUTE, osw(max(18, fs - 8)))
        y += rh
    d.text((64, S - 128), "CONDITIONS BY GOCHECKMYWEATHER · NATIONAL WEATHER SERVICE", font=sc._mono(17, True), fill=SOFT)
    d.text((64, S - 100), sc._fit(d, (rep.get("stamp") or "").replace("Conditions by GoCheckMyWeather, from the ", "From the "),
                                  sc._mono(16), S - 128), font=sc._mono(16), fill=SOFT)
    d.text((64, S - 72), "gocheckmysports.com  ·  gocheckmyweather.com", font=sc._mono(20, True), fill=CREAM)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "PNG", optimize=True)
    return out_path


def game_share_card(row, out_path):
    """The 1080 square card for one game page (S-3b.1), in the wall's look: the same green panel in a
    darker frame, Oswald plates, scoreboard yellow. `row` is site_build.game_share_row's dict, built
    from the same game record and conditions entry the page renders, so the card cannot say what the
    page does not. Both sites' names in plain text, no logos and no team mark (scorecard line 5).
    A score is drawn only when the row carries one, and the row carries one only for a game that has
    started; a scheduled game shows its kickoff and never the word Final."""
    from PIL import Image, ImageDraw
    import share_cards as sc
    S = 1080
    BG, FRAME, PANEL, PLATE, CREAM, YELLOW, SOFT, MUTE, OFF = WALL_PALETTE
    osw = lambda n: sc._font("Oswald-600.ttf", n)
    im = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([24, 24, S - 24, S - 24], radius=18, fill=FRAME)
    d.rounded_rectangle([34, 34, S - 34, S - 34], radius=12, fill=PANEL)
    d.text((64, 56), "GoCheckMySports", font=sc._mono(20, True), fill=SOFT)
    mk = "GoCheckMyWeather"
    d.text((S - 64 - d.textlength(mk, font=sc._mono(20, True)), 56), mk, font=sc._mono(20, True), fill=SOFT)

    def center(text, y, font, fill, x0=64, x1=S - 64):
        d.text(((x0 + x1 - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)

    def plate(x0, y0, x1, y1, text, font, fill=CREAM):
        d.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=PLATE)
        bx = d.textbbox((0, 0), text, font=font)
        d.text(((x0 + x1 - (bx[0] + bx[2])) / 2, (y0 + y1 - (bx[1] + bx[3])) / 2), text, font=font, fill=fill)

    # the matchup: two team plates and AT, abbreviations in Oswald, full names under in mono
    top = 130
    plate(64, top, 424, top + 150, row.get("away") or "", osw(96))
    plate(S - 64 - 360, top, S - 64, top + 150, row.get("home") or "", osw(96))
    f_at = sc._mono(26, True)
    d.text((S / 2 - d.textlength("AT", font=f_at) / 2, top + 58), "AT", font=f_at, fill=SOFT)
    for x0, x1, nm in ((64, 424, row.get("away_name")), (S - 64 - 360, S - 64, row.get("home_name"))):
        center(sc._fit(d, nm or "", sc._mono(22), 350), top + 162, sc._mono(22), SOFT, x0, x1)
    y = top + 226
    # the score, only when the row has one
    if row.get("score_away") is not None and row.get("score_home") is not None:
        plate(64, y, 424, y + 110, str(row["score_away"]), osw(84), CREAM)
        plate(S - 64 - 360, y, S - 64, y + 110, str(row["score_home"]), osw(84), CREAM)
        if row.get("state_word"):
            bx = d.textbbox((0, 0), row["state_word"], font=osw(40))
            d.text(((424 + S - 64 - 360 - bx[0] - bx[2]) / 2, y + 55 - (bx[1] + bx[3]) / 2),
                   row["state_word"], font=osw(40), fill=YELLOW)
        y += 134
    # the kickoff, in ET with the zone, and the network
    y += 22
    center((row.get("when") or "").upper(), y, osw(52), YELLOW)
    y += 76
    if row.get("network"):
        center(("ON " + row["network"]).upper(), y, sc._mono(26, True), SOFT)
    y += 66
    # the conditions plates, the page's own words
    d.ellipse([64, y + 4, 80, y + 20], fill=YELLOW if row.get("lit") else OFF)
    d.text((90, y), "WEATHER MATTERS" if row.get("lit") else "KICKOFF CONDITIONS", font=sc._mono(18, True), fill=SOFT)
    y += 44
    ph = 150 if row.get("score_away") is not None else 210   # a scored card gives the room to the score
    if row.get("status") == "forecast":
        gap, pw = 20, (S - 128 - 40) // 3
        for i, (lab, val, col) in enumerate((("TEMP °F", row.get("temp"), CREAM),
                                              ("WIND MPH", row.get("wind"), YELLOW if row.get("wind_on") else CREAM),
                                              ("RAIN %", row.get("rain"), CREAM))):
            x0 = 64 + i * (pw + gap)
            d.rounded_rectangle([x0, y, x0 + pw, y + ph], radius=6, fill=PLATE)
            d.text((x0 + pw / 2 - d.textlength(lab, font=sc._mono(17, True)) / 2, y + 12), lab, font=sc._mono(17, True), fill=SOFT)
            if val:
                f = osw(124 if ph == 210 else 84)
                bx = d.textbbox((0, 0), val, font=f)
                d.text((x0 + (pw - bx[0] - bx[2]) / 2, y + (ph + 30) / 2 - (bx[1] + bx[3]) / 2), val, font=f, fill=col)
            else:
                f = sc._mono(26)
                d.text((x0 + (pw - d.textlength("missing", font=f)) / 2, y + ph / 2 + 4), "missing", font=f, fill=SOFT)
    else:
        note = (row.get("note") or "No forecast").upper()
        nf = 64
        while nf > 30 and d.textlength(note, font=osw(nf)) > S - 160:
            nf -= 2   # one line at any length, never trimmed: the whole of what the page prints
        plate(64, y, S - 64, y + ph, note, osw(nf), MUTE)
    y += ph
    if row.get("venue"):
        center(sc._fit(d, row["venue"], sc._mono(22), S - 140), y + 28, sc._mono(22), SOFT)
    # one credit line, the stamp, and only when the page has an NWS reading to credit
    if row.get("stamp"):
        d.text((64, S - 108), sc._fit(d, row["stamp"], sc._mono(18, True), S - 128), font=sc._mono(18, True), fill=SOFT)
    d.text((64, S - 72), "gocheckmysports.com  ·  gocheckmyweather.com", font=sc._mono(20, True), fill=CREAM)
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


def already_published(rid, directory=REPORTS):
    """True when this slot's report is already on disk. The workflow carries catch-up crons because
    GitHub's scheduler delivered no run at all for the 15 Oct Thursday slot; a repeat for a slot
    that has its report publishes nothing and costs no build."""
    return os.path.exists(os.path.join(directory, f"{rid}.json"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true", help="rewrite a slot that already has its report")
    a = ap.parse_args(argv)
    if not (a.dry_run or a.publish):
        ap.print_help()
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    if a.publish and in_freeze(now):
        print("conditions report: inside the Sunday freeze (12:30 to 8:30 PM ET); nothing published")
        return 0
    et = now.astimezone(ET)
    rid = f"{et.date().isoformat()}-{SLOTS.get(et.weekday(), 'extra')}"
    if a.publish and not a.force and already_published(rid):
        print(f"conditions report: {rid} is already published; nothing to do")
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
