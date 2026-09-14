#!/usr/bin/env python3
"""scoreboard.py: the Scoreboard band's data (S-A). A site-lane fetcher.

WHY A NEW FETCHER RATHER THAN scores.json. scores_pulse.py runs inside the brief
workflow and is frozen by standing rule 1. What it writes is a ticker's worth of each
game: teams, scores, state, a detail string. The Scoreboard band needs the network, the
records, the period and clock, and the situation line, and none of those are in that
file. So this reads the same public scoreboards directly and writes its own file, and
scores_pulse.py is not touched.

WHAT IT DOES NOT CARRY, deliberately. The summary endpoint returns odds, pickcenter,
againstTheSpread and predictor beside the data we want. None of it is read here, and
odds_gate.py checks the written file rather than trusting that sentence.

Fail-safe, as elsewhere in the site lane: a league that fails is skipped and the others
still write; a total failure leaves the committed file alone; a file older than
STALE_HOURS is not served as current.

USAGE  python3 scoreboard.py            refresh
       python3 scoreboard.py --report   read the committed file
"""

import datetime
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

OUT = os.path.join(HERE, "site", "data", "scoreboard.json")
COLORS = os.path.join(HERE, "site", "data", "team-colors.json")
TIMEOUT = 15
STALE_HOURS = 6

# Tab order is audience order, which is what the marquee rule leans on.
LEAGUES = [
    ("NFL", "football/nfl", "nfl"),
    ("MLB", "baseball/mlb", "mlb"),
    ("CFB", "football/college-football", "college-football"),
    ("Soccer", "soccer/eng.1", None),
    ("NBA", "basketball/nba", "nba"),
    ("NHL", "hockey/nhl", "nhl"),
    ("WNBA", "basketball/wnba", "wnba"),
]
BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"


def _get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": common.ua_for(url), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _colors():
    try:
        return json.load(open(COLORS, encoding="utf-8"))
    except Exception:
        return {}


def _net(comp):
    """The carrier, from whichever field the league populates."""
    for g in comp.get("geoBroadcasts") or []:
        n = ((g.get("media") or {}).get("shortName") or "").strip()
        if n:
            return n
    for b in comp.get("broadcasts") or []:
        for n in b.get("names") or []:
            if n:
                return n
    return ""


def _progress(ev, comp, league):
    """How far through the game we are, 0 to 1, or None when it cannot be known.
    Never guessed: a sport whose length is not fixed returns None and the card draws
    no bar."""
    st = (ev.get("status") or {})
    t = st.get("type") or {}
    if t.get("state") != "in":
        return None
    per = st.get("period")
    if not isinstance(per, (int, float)) or per <= 0:
        return None
    regulation = {"NFL": 4, "CFB": 4, "NBA": 4, "WNBA": 4, "NHL": 3}.get(league)
    if not regulation:
        return None
    clock = st.get("displayClock") or ""
    frac = 0.0
    try:
        mm, ss = clock.split(":")
        length = 15 if regulation == 4 else 20
        frac = 1.0 - ((int(mm) * 60 + int(ss)) / (length * 60))
    except Exception:
        frac = 0.5
    done = (per - 1) + max(0.0, min(1.0, frac))
    return max(0.02, min(1.0, done / regulation))


def _league(name, path, colorkey, cmap):
    d = _get(BASE.format(path=path))
    games = []
    for ev in d.get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        st = (ev.get("status") or {})
        t = st.get("type") or {}
        sides = {}
        for c in comp.get("competitors") or []:
            team = c.get("team") or {}
            ab = team.get("abbreviation") or team.get("shortDisplayName") or ""
            rec = ""
            for r in c.get("records") or []:
                if r.get("type") == "total":
                    rec = r.get("summary") or ""
                    break
            sides[c.get("homeAway")] = {
                "abbr": ab,
                "name": team.get("shortDisplayName") or team.get("name") or ab,
                "score": c.get("score"),
                "record": rec,
                "id": str(team.get("id") or ""),
                "color": ((cmap.get(colorkey) or {}).get(ab) or {}).get("color", ""),
            }
        sit = comp.get("situation") or {}
        games.append({
            "id": str(ev.get("id") or ""),
            "league": name,
            "state": t.get("state") or "",
            "completed": bool(t.get("completed")),
            "status_short": t.get("shortDetail") or "",
            "detail": st.get("displayClock") or "",
            "period": st.get("period"),
            "start_utc": ev.get("date") or "",
            "network": _net(comp),
            "home": sides.get("home") or {}, "away": sides.get("away") or {},
            "situation": (sit.get("downDistanceText") or "") if sit else "",
            "possession": (sit.get("possession") or "") if sit else "",
            "progress": _progress(ev, comp, name),
            "venue_indoor": (comp.get("venue") or {}).get("indoor"),
        })
    return games


def refresh():
    cmap = _colors()
    out, failed = [], []
    for name, path, ck in LEAGUES:
        try:
            g = _league(name, path, ck, cmap)
            if g:
                out.append({"league": name, "games": g})
        except Exception as e:
            failed.append(f"{name} ({type(e).__name__})")
    if not out:
        print("scoreboard: every league failed; committed file left alone")
        return None
    payload = {"fetched_at": datetime.datetime.now(datetime.timezone.utc)
                                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
               "leagues": out, "failed": failed}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    n = sum(len(x["games"]) for x in out)
    print(f"scoreboard: {len(out)} league(s), {n} game(s)"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    return payload


def load():
    try:
        d = json.load(open(OUT, encoding="utf-8"))
        t = datetime.datetime.strptime(d["fetched_at"], "%Y-%m-%dT%H:%M:%SZ") \
            .replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None
    age = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 3600
    if age > STALE_HOURS:
        print(f"scoreboard: file is {age:.0f}h old, past {STALE_HOURS}h; band withheld")
        return None
    d["age_hours"] = round(age, 1)
    return d


def main():
    d = load() if "--report" in sys.argv else refresh()
    if not d:
        return 0
    for L in d["leagues"]:
        states = {}
        for g in L["games"]:
            states[g["state"]] = states.get(g["state"], 0) + 1
        print(f"  {L['league']:8} {len(L['games']):3} games {states}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
