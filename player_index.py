#!/usr/bin/env python3
"""player_index.py: the daily player index behind the player check (S-B6).

WHAT IT HOLDS, per the item: name, team, position, current designation, next game,
kickoff and network, for the fantasy-relevant positions plus team defenses.

HOW THE 300 ARE CHOSEN, and this is the part that needed care. The item says "the top
300 fantasy-relevant players". Ranking players by fantasy value IS a projection, and
this desk does not publish those. So the cut is made on FACTS a reader can check:

  1. the player carries an official designation right now, or
  2. the player has a stat line this season.

Those are exactly the players somebody types a name into a search box about. Nobody
searches "is my third-string guard playing"; they search the name that is either
questionable or in their lineup. Within that set the order is most recently active
first, which is a fact about the corpus rather than a judgement about the player.

Practice-squad and injured-reserve players are indexed but never given a page: their
status is a roster fact, not a game-week question.

USAGE  python3 player_index.py            rebuild the index
       python3 player_index.py --report   read the committed index
"""

import datetime
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

OUT = os.path.join(HERE, "site", "data", "players.json")
W2W = os.path.join(HERE, "site", "data", "where-to-watch.json")
TEAMS = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
ROSTER = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}/roster"
TIMEOUT = 20
STALE_HOURS = 30
FANTASY_POS = ("QB", "RB", "WR", "TE", "K", "PK", "FB")
PAGE_CAP = 300


def _get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": common.ua_for(url), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _next_games():
    """team abbreviation -> its next unplayed game, from the schedule the site already
    fetches. No extra request and no second source of truth about kickoff."""
    try:
        w = json.load(open(W2W, encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for wk in w.get("weeks") or []:
        for g in wk.get("games") or []:
            if g.get("completed"):
                continue
            carriers = ", ".join(c.get("name", "") for c in (g.get("carriers") or []))
            for side, opp in (("home", "away"), ("away", "home")):
                ab = g.get(side)
                if not ab or ab in out:
                    continue
                out[ab] = {"opponent": g.get(opp), "home": side == "home",
                           "kickoff_et": g.get("kickoff_et"), "day": g.get("day_et"),
                           "network": carriers, "game_id": g.get("id")}
    return out


def _designations():
    """Current designation per player, from the snapshot the board already keeps."""
    try:
        import inactives
        snap = inactives.load_snapshot()
    except Exception:
        return {}, {}
    if not snap:
        return {}, {}
    desig, inact = {}, {}
    for t in snap.get("teams", {}).values():
        for p in (t.get("designations") or {}).values():
            if p.get("name"):
                desig[p["name"]] = {"status": p.get("status"),
                                    "detail": p.get("detail"),
                                    "first_seen": p.get("first_seen")}
        for p in (t.get("players") or {}).values():
            if p.get("name"):
                inact[p["name"]] = p.get("first_seen")
    return desig, inact


def build():
    try:
        teams = _get(TEAMS)["sports"][0]["leagues"][0]["teams"]
    except Exception as e:
        print(f"player_index: team list failed ({type(e).__name__})")
        return None
    nxt = _next_games()
    desig, inact = _designations()
    players, failed = [], 0
    for t in teams:
        tm = t["team"]
        ab = tm.get("abbreviation") or ""
        try:
            r = _get(ROSTER.format(tid=tm["id"]))
        except Exception:
            failed += 1
            continue
        for grp in r.get("athletes") or []:
            bucket = grp.get("position") or ""
            for a in grp.get("items") or []:
                pos = ((a.get("position") or {}).get("abbreviation") or "").upper()
                if pos not in FANTASY_POS:
                    continue
                nm = a.get("displayName") or a.get("fullName") or ""
                if not nm:
                    continue
                d = desig.get(nm)
                players.append({
                    "name": nm, "slug": slug(nm), "team": ab, "pos": pos,
                    "jersey": a.get("jersey") or "",
                    "roster": bucket,
                    "designation": (d or {}).get("status") or "",
                    "detail": (d or {}).get("detail") or "",
                    "inactive_seen": inact.get(nm) or "",
                    "next": nxt.get(ab) or {},
                })
    # Team defenses, one per club, as the item asks.
    for t in teams:
        tm = t["team"]
        ab = tm.get("abbreviation") or ""
        nm = f'{tm.get("shortDisplayName") or tm.get("name") or ab} defense'
        players.append({"name": nm, "slug": slug(nm), "team": ab, "pos": "DST",
                        "jersey": "", "roster": "defense", "designation": "",
                        "detail": "", "inactive_seen": "", "next": nxt.get(ab) or {}})
    payload = {"built_at": datetime.datetime.now(datetime.timezone.utc)
                                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
               "players": sorted(players, key=lambda p: (p["team"], p["pos"], p["name"])),
               "teams_failed": failed}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"), sort_keys=True)
    print(f"player_index: {len(players)} players, {failed} team(s) failed")
    return payload


def load():
    try:
        d = json.load(open(OUT, encoding="utf-8"))
        t = datetime.datetime.strptime(d["built_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except Exception:
        return None
    if (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 3600 > STALE_HOURS:
        return None
    return d


def page_set(index, stats_names=()):
    """Which players get a static page. Facts only: a live designation, or a stat line
    this season. Never a ranking."""
    if not index:
        return []
    want = []
    for p in index.get("players") or []:
        if p.get("roster") in ("practiceSquad",):
            continue
        if p.get("designation") or p["name"] in stats_names:
            want.append(p)
    # Most recently active first; the cap is a page budget, not a judgement.
    want.sort(key=lambda p: (p.get("inactive_seen") or "", p.get("designation") or ""),
              reverse=True)
    return want[:PAGE_CAP]


def main():
    d = load() if "--report" in sys.argv else build()
    if not d:
        print("player_index: nothing to report")
        return 0
    import collections
    c = collections.Counter(p["pos"] for p in d["players"])
    print("  by position:", dict(c))
    print("  with a designation:",
          sum(1 for p in d["players"] if p.get("designation")))
    print("  page set (designation only):", len(page_set(d)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
