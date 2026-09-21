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


def _leaders(comp, n=3):
    """C-2: the feed's own leaders, for the leagues where the desk computes none.

    The cards name three leaders on a live or final game from the desk's fantasy points,
    which exist for the NFL and nowhere else, so a live baseball, hockey or basketball
    card named nobody at all. The feed carries leaders for most of them.

    Carried as the feed states them: the category's short name, the athlete's short
    name, and the line the feed already wrote ("26/38, 327 YDS, 4 TD"). Nothing is
    computed here, because a number this desk derives from a box score is a number it
    then has to defend, and the feed's own line is attributable to the feed.
    """
    out = []
    for cat in (comp.get("leaders") or []):
        rows = cat.get("leaders") or []
        if not rows:
            continue
        top = rows[0]
        ath = top.get("athlete") or {}
        nm = (ath.get("shortName") or ath.get("displayName") or "").strip()
        val = str(top.get("displayValue") or "").strip()
        if not nm or not val:
            continue
        # A COMPOSITE RATING IS NOT A LABEL A READER CAN USE. Baseball's only category
        # is "MLBRating", whose short name is "RAT", so the card read "B. Bichette RAT"
        # over a line that already says everything: "1-4, HR, RBI, R, K". The category
        # is dropped where it is one of these and the line stands on its own. PASS,
        # RUSH and REC stay, because those do tell a reader what they are looking at.
        _key = str(cat.get("name") or "")
        _cat = "" if "rating" in _key.lower() else (
            cat.get("shortDisplayName") or cat.get("abbreviation") or "").strip()
        out.append({"cat": _cat,
                    "name": nm, "line": val,
                    "team": str((top.get("team") or {}).get("id") or "")})
        if len(out) >= n:
            break
    return out


def _line(comp):
    """The line as the feed reports it, with the provider that set it.

    Returns None unless BOTH a provider and at least one number are present: an
    unattributed spread would read as the desk's own estimate, which is the one thing
    the new law does not allow."""
    o = (comp.get("odds") or [None])[0]
    if not o:
        return None
    prov = ((o.get("provider") or {}).get("name") or "").strip()
    if not prov:
        return None
    out = {"provider": prov}
    if o.get("details"):
        out["detail"] = str(o["details"]).strip()
    if o.get("spread") is not None:
        out["spread"] = o["spread"]
    if o.get("overUnder") is not None:
        out["total"] = o["overUnder"]
    for side, key in (("awayTeamOdds", "ml_away"), ("homeTeamOdds", "ml_home")):
        t = o.get(side) or {}
        ml = t.get("moneyLine")
        if ml is None:
            ml = (t.get("current") or {}).get("moneyLine")
        if isinstance(ml, dict):
            ml = ml.get("american") or ml.get("value")
        if ml not in (None, ""):
            out[key] = ml
        if t.get("favorite"):
            out["favorite"] = "away" if side == "awayTeamOdds" else "home"
    return out if len(out) > 1 else None


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
            # CFB-1: THE POLL RANK RIDES WITH THE GAME. curatedRank is the rank the
            # feed had for this team at this kickoff, which is the one a card should
            # print: a game played in week 3 is not relabelled when the week 4 poll
            # lands. The feed says 99 for unranked, so anything outside the top 25 is
            # dropped here rather than being printed as a rank of 99.
            cr = (c.get("curatedRank") or {}).get("current")
            rank = cr if isinstance(cr, int) and 1 <= cr <= 25 else None
            sides[c.get("homeAway")] = {
                "abbr": ab,
                "name": team.get("shortDisplayName") or team.get("name") or ab,
                # CFB-1: the school in full, for the leagues whose cards print it.
                # `location` is the school ("Ohio State"), `name` is the mascot
                # ("Buckeyes"); the pair is what standings.py already learned not to
                # concatenate. No location in the feed, no school: the card falls back
                # to the short name rather than inventing one.
                "school": team.get("location") or "",
                # CFB-2: THE MASCOT, SEPARATELY. `name` is the mascot in every league
                # ("Hurricanes", "Dolphins", "Scarlet Knights"); `shortDisplayName`,
                # which the line above prefers, is the mascot in the pro leagues but
                # the school again in college ("Rutgers"). Kept as its own field so a
                # card can say which Miami it means without the pairs being concatenated
                # at the source, which is the mistake standings.py already learned.
                "mascot": team.get("name") or "",
                "rank": rank,
                "score": c.get("score"),
                "record": rec,
                # C-2: the periods, as the feed displays them. A quarter in football, an
                # inning in baseball, a period in hockey: the desk does not name them
                # here, it carries them in order and lets the league's own count say
                # what they are. displayValue and not value, because value is a float
                # and 0.0 is not how a scoreboard writes nothing.
                "periods": [str(x.get("displayValue") or "")
                            for x in (c.get("linescores") or [])],
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
            "leaders": _leaders(comp),
            "situation": (sit.get("downDistanceText") or "") if sit else "",
            "possession": (sit.get("possession") or "") if sit else "",
            # B-2: the three facts a live football card is missing, all of them already
            # in the situation object the down-and-distance line came from. Timeouts are
            # carried as they are given, INCLUDING zero, which is a fact a reader wants
            # ("no timeouts left") and not an absence; None means the feed said nothing.
            "red_zone": bool(sit.get("isRedZone")) if sit else False,
            "to_home": sit.get("homeTimeouts") if sit else None,
            "to_away": sit.get("awayTimeouts") if sit else None,
            "progress": _progress(ev, comp, name),
            "venue_indoor": (comp.get("venue") or {}).get("indoor"),
            # H-11: the venue's name comes from the FEED. It used to come from our own
            # venues.json, which still called Houston's stadium "Reliant" eleven years
            # after it was renamed NRG. A table of ours goes stale silently; the feed
            # does not. A game the feed does not name gets no venue line.
            "venue": (comp.get("venue") or {}).get("fullName") or "",
            "line": _line(comp),
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
    d["age_hours"] = round(age, 1)
    # H-7 / L-4: A STALE SNAPSHOT IS RENDERED, MARKED. This used to return None past
    # STALE_HOURS, which withdrew the whole band and dropped the homepage onto the old
    # scores strip. L-4 is the opposite rule: stale data renders with its own stamp and
    # a stale mark, and nothing on the page shows a number the source did not send. A
    # reader who arrives at 7:57 AM to a band that says "Updated 7:57 AM ET · stale"
    # knows exactly what they have; one who arrives to a different component does not.
    d["stale"] = age > STALE_HOURS
    if d["stale"]:
        print(f"scoreboard: file is {age:.0f}h old, past {STALE_HOURS}h; "
              f"band renders marked stale")
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
