#!/usr/bin/env python3
"""
scores_pulse.py: the live-scores desk. Standard library only. FAIL-OPEN.

Fetches today's slate from the league data sources already registered in config.json
(sources.league_apis) and writes site/data/scores.json, the render-ready snapshot the
scores strip bakes from at build time. Modeled on the family's market_pulse.py contract:

  - Each league fetches independently; a failed league is a warned skip, never a failure.
  - If EVERY league fails, nothing is written and the committed snapshot stands.
  - Netlify runs this before site_build.py ("python3 scores_pulse.py || true"), so a
    network-dead build still ships the last committed scores.

The 30-hour date window is load-bearing: out of season, ESPN scoreboards return future
or stale placeholder events (September NFL openers in July, June Finals in winter), so
only events starting within [now-30h, now+30h] survive. That is also what makes the
strip disappear on genuinely empty days instead of showing dead chrome.

Sources and trust: MLB comes from MLB's own StatsAPI (tier primary); NFL/NBA/NHL come
from ESPN's scoreboard JSON (tier major, no SLA). League data is market data, not news:
nothing here passes through the editorial pipeline and the strip labels itself as league
data. Client-side refresh (site_build.py inline script) only ever updates games already
present in this snapshot.

USAGE  python3 scores_pulse.py          # writes site/data/scores.json (or leaves it)
"""

import datetime
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "site", "data", "scores.json")
UA = {"User-Agent": "GoCheckMySports-scores/1.0"}
WINDOW_HOURS = 30
MAX_GAMES = 20

MLB_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=team,linescore"
ESPN = {
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
}
# Regular season, wild card, division, league championship, world series. Filters out
# exhibitions and All-Star adjacent games.
MLB_GAME_TYPES = {"R", "F", "D", "L", "W"}


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def in_window(start_utc, now):
    try:
        when = datetime.datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    return abs((when - now).total_seconds()) <= WINDOW_HOURS * 3600


def et_clock(start_utc):
    """'6:40 PM ET' from an ISO UTC stamp; the desk's stated audience clock."""
    try:
        from zoneinfo import ZoneInfo
        when = datetime.datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
        local = when.astimezone(ZoneInfo("America/New_York"))
        return local.strftime("%-I:%M %p ET")
    except Exception:
        return start_utc[11:16] + " UTC"


def gather_mlb(now):
    games = []
    sched = fetch_json(MLB_URL)
    for day in sched.get("dates", []):
        for g in day.get("games", []):
            if g.get("gameType") not in MLB_GAME_TYPES:
                continue
            start = g.get("gameDate", "")
            if not in_window(start, now):
                continue
            status = g.get("status", {})
            abstract = status.get("abstractGameState", "")
            detailed = status.get("detailedState", "")
            teams = g.get("teams", {})
            away = teams.get("away", {})
            home = teams.get("home", {})
            state = {"Preview": "pre", "Live": "in", "Final": "post"}.get(abstract, "pre")
            if detailed in ("Postponed", "Suspended", "Cancelled"):
                detail = {"Postponed": "PPD", "Suspended": "SUSP", "Cancelled": "CNCL"}[detailed]
            elif state == "pre":
                detail = et_clock(start)
            elif state == "post":
                detail = "Final"
            else:
                line = g.get("linescore", {})
                half = "Top" if line.get("isTopInning") else "Bot"
                inning = line.get("currentInning", "")
                detail = f"{half} {inning}" if inning else "Live"
            games.append({
                "away": (away.get("team") or {}).get("abbreviation") or "",
                "home": (home.get("team") or {}).get("abbreviation") or "",
                "away_score": away.get("score"),
                "home_score": home.get("score"),
                "state": state,
                "detail": detail,
                "start_utc": start,
                "eid": str(g.get("gamePk", "")),
            })
    return {"league": "MLB", "source": "statsapi.mlb.com", "games": games}


def gather_espn(league, url, now):
    games = []
    board = fetch_json(url)
    for ev in board.get("events", []):
        start = ev.get("date", "")
        if not in_window(start, now):
            continue
        comp = (ev.get("competitions") or [{}])[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        home, away = sides.get("home", {}), sides.get("away", {})
        st = (ev.get("status") or {}).get("type", {})
        state = st.get("state", "pre")
        if state == "pre":
            detail = et_clock(start)
        elif state == "post":
            detail = "Final"
        else:
            detail = st.get("shortDetail", "Live")
        games.append({
            "away": (away.get("team") or {}).get("abbreviation") or "",
            "home": (home.get("team") or {}).get("abbreviation") or "",
            "away_score": int(away["score"]) if str(away.get("score", "")).isdigit() else None,
            "home_score": int(home["score"]) if str(home.get("score", "")).isdigit() else None,
            "state": state,
            "detail": detail,
            "start_utc": start,
            "eid": str(ev.get("id", "")),
        })
    return {"league": league, "source": "site.api.espn.com", "games": games}


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    leagues, failures = [], 0
    jobs = [("MLB", lambda: gather_mlb(now))]
    jobs += [(name, (lambda u=url, n=name: gather_espn(n, u, now))) for name, url in ESPN.items()]
    for name, job in jobs:
        try:
            block = job()
            if block["games"]:
                leagues.append(block)
            print(f"scores: {name} -> {len(block['games'])} in-window games")
        except Exception as e:
            failures += 1
            print(f"scores: WARN {name} fetch failed ({e}); skipped, not fatal")
    if not leagues and failures == len(jobs):
        print("scores: every league failed; leaving the committed snapshot in place")
        return 0
    total = sum(len(l["games"]) for l in leagues)
    if total > MAX_GAMES:
        # Trim evenly from the end of each league list; MLB (primary source) keeps most.
        for l in leagues:
            keep = max(2, int(MAX_GAMES * len(l["games"]) / total))
            l["games"] = l["games"][:keep]
    out = {"generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "leagues": leagues}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"scores: wrote {OUT_PATH} ({sum(len(l['games']) for l in leagues)} games, "
          f"{len(leagues)} leagues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
