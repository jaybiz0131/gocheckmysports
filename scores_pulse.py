#!/usr/bin/env python3
"""
scores_pulse.py: the live-scores desk. Standard library only. FAIL-OPEN.

Fetches today's slate from league data sources and writes site/data/scores.json, the
render-ready snapshot the scores strip bakes from at build time. Modeled on the family's
market_pulse.py contract:

  - Each league fetches independently; a failed league is a warned skip, never a failure.
  - If EVERY league fails, nothing is written and the committed snapshot stands.
  - Netlify runs this before site_build.py ("python3 scores_pulse.py || true"), so a
    network-dead build still ships the last committed scores.

The 30-hour date window is load-bearing: out of season, ESPN scoreboards return future
or stale placeholder events (September NFL openers in July, June Finals in winter), so
only events starting within [now-30h, now+30h] survive. That is also what makes the
strip disappear on genuinely empty days instead of showing dead chrome.

THE USER-AGENT IS LOAD-BEARING (2026-09-04). This file previously sent
"GoCheckMySports-scores/1.0" and every ESPN league had been returning 403 for an unknown
length of time. MLB survived only because it comes from MLB's own StatsAPI, so the strip
degraded to a baseball-only bar during NFL season and said nothing: the per-league
handler warns to stdout and writes the snapshot anyway. ESPN's edge allows generic HTTP
client agents (curl, python-requests, Python-urllib, okhttp, Go-http-client) and rejects
both browser-impersonating strings and custom branded ones. Identifying the desk politely
and by name is exactly what got it blocked. Do not "fix" this back to a branded UA, and
if ESPN 403s again, test the agent FIRST: it is one request and it was the whole cause.

Sources and trust: MLB comes from MLB's own StatsAPI (tier primary) with ESPN as a
fallback; everything else comes from ESPN's scoreboard JSON (tier major, no SLA). League
data is market data, not news: nothing here passes the editorial pipeline and the strip
labels itself as league data. Client-side refresh (site_build.py inline script) only ever
updates games already present in this snapshot.

WHAT COUNTS AS A HEALTHY RUN. A league with no games is not a failure, it is September
for the NBA. A league whose fetch failed IS a failure and is recorded per league in the
snapshot's "sources" block, so "the NFL is quiet tonight" and "the NFL feed is down" stop
looking identical from the outside. Nothing here gates a publish.

USAGE  python3 scores_pulse.py          # writes site/data/scores.json (or leaves it)
"""

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "site", "data", "scores.json")

# See the module docstring. A generic client agent is what ESPN's edge accepts; this one
# is also true, since this is a Python urllib client.
UA = {"User-Agent": "Python-urllib/3"}

WINDOW_HOURS = 30
# Per league, so one busy Saturday of college football cannot crowd every other sport off
# the rail, and overall, so the strip stays a strip.
PER_LEAGUE = 6
MAX_GAMES = 48
RETRIES = 3
BACKOFF = 1.6

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/"
MLB_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=team,linescore"

# Regular season, wild card, division, league championship, world series. Filters out
# exhibitions and All-Star adjacent games.
MLB_GAME_TYPES = {"R", "F", "D", "L", "W"}

# THE DESK'S BEAT, NOT ESPN'S CATALOGUE. Each entry is (label, [(kind, url), ...]) and the
# sources are tried in order, so a league with a fallback survives one provider failing.
# Order here is the editorial order on the rail before live games are promoted.
LEAGUES = [
    ("MLB", [("mlb", MLB_URL), ("espn_team", ESPN_BASE + "baseball/mlb/scoreboard")]),
    ("NFL", [("espn_team", ESPN_BASE + "football/nfl/scoreboard")]),
    ("CFB", [("espn_team", ESPN_BASE + "football/college-football/scoreboard")]),
    ("NBA", [("espn_team", ESPN_BASE + "basketball/nba/scoreboard")]),
    ("WNBA", [("espn_team", ESPN_BASE + "basketball/wnba/scoreboard")]),
    ("NHL", [("espn_team", ESPN_BASE + "hockey/nhl/scoreboard")]),
    ("EPL", [("espn_team", ESPN_BASE + "soccer/eng.1/scoreboard")]),
    ("La Liga", [("espn_team", ESPN_BASE + "soccer/esp.1/scoreboard")]),
    ("Serie A", [("espn_team", ESPN_BASE + "soccer/ita.1/scoreboard")]),
    ("Bundesliga", [("espn_team", ESPN_BASE + "soccer/ger.1/scoreboard")]),
    ("UCL", [("espn_team", ESPN_BASE + "soccer/uefa.champions/scoreboard")]),
    ("MLS", [("espn_team", ESPN_BASE + "soccer/usa.1/scoreboard")]),
    # Tennis is a tournament, not a fixture list: the scoreboard payload carries the event
    # and hangs the matches off groupings. Singles only, because ESPN sends doubles pairs
    # with no athlete names and two blank rows is not a score.
    ("ATP", [("espn_tennis_men", ESPN_BASE + "tennis/atp/scoreboard")]),
    ("WTA", [("espn_tennis_women", ESPN_BASE + "tennis/wta/scoreboard")]),
]


def fetch_json(url, timeout=20):
    """GET with retries. Transient upstream trouble is the normal case for free feeds;
    one 503 should not cost the reader a whole league for the next three hours."""
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            # 4xx that is not rate limiting will not fix itself on a retry.
            if e.code not in (429, 500, 502, 503, 504):
                raise
            wait = BACKOFF ** attempt
            retry_after = e.headers.get("Retry-After") if e.headers else None
            if retry_after and str(retry_after).isdigit():
                wait = min(float(retry_after), 10.0)
            if attempt < RETRIES - 1:
                time.sleep(wait)
        except Exception as e:  # timeouts, DNS, malformed JSON
            last = e
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF ** attempt)
    raise last


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


def gather_mlb(now, url):
    games = []
    sched = fetch_json(url)
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
    return games, "statsapi.mlb.com"


def _espn_status(comp_or_event, start):
    st = ((comp_or_event.get("status") or {}).get("type") or {})
    state = st.get("state", "pre")
    if state == "pre":
        return state, et_clock(start)
    if state == "post":
        return state, "Final"
    return state, st.get("shortDetail") or "Live"


def gather_espn_team(now, url):
    """Team-vs-team scoreboards: NFL, college football, NBA, WNBA, NHL, MLB and every
    soccer league share this exact shape."""
    games = []
    board = fetch_json(url)
    for ev in board.get("events", []):
        start = ev.get("date", "")
        if not in_window(start, now):
            continue
        comp = (ev.get("competitions") or [{}])[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        home, away = sides.get("home", {}), sides.get("away", {})
        if not home and not away:
            continue
        state, detail = _espn_status(ev, start)
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
    return games, "site.api.espn.com"


def _sets_won(me, opp):
    """Sets on the board for one player. ESPN leaves competitor.score null on tennis and
    carries the real result in per-set linescores, so a match with no sets counted would
    render two blank rows."""
    a = [l.get("value") for l in (me.get("linescores") or [])]
    b = [l.get("value") for l in (opp.get("linescores") or [])]
    won = 0
    for x, y in zip(a, b):
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x > y:
            won += 1
    return won


def _player_label(competitor):
    ath = competitor.get("athlete") or {}
    return (ath.get("shortName") or ath.get("displayName") or "").strip()


def gather_espn_tennis(now, url, draw):
    """A slam is one event with the matches hung off groupings, one grouping per draw.

    THE DRAW FILTER IS NOT COSMETIC. During a slam BOTH the atp and wta endpoints return
    the same tournament with every draw attached, so taking any grouping named "Singles"
    pulled the identical 64 matches twice and filed women's matches under ATP: the rail
    showed "ATP: K. Rakhimova - A. Sabalenka". The duplicate eids would also have broken
    the client refresh, which looks a card up by data-eid and takes the first hit.""" 
    games = []
    board = fetch_json(url)
    for ev in board.get("events", []):
        for grouping in ev.get("groupings") or []:
            name = ((grouping.get("grouping") or {}).get("displayName") or "")
            if draw not in name:
                continue          # doubles arrive with no athlete names
            for comp in grouping.get("competitions") or []:
                start = comp.get("date", "")
                if not in_window(start, now):
                    continue
                sides = comp.get("competitors") or []
                if len(sides) != 2:
                    continue
                a, b = sides[0], sides[1]
                a_name, b_name = _player_label(a), _player_label(b)
                if not a_name or not b_name:
                    continue
                state, detail = _espn_status(comp, start)
                a_sets, b_sets = _sets_won(a, b), _sets_won(b, a)
                if state == "pre":
                    a_sets = b_sets = None
                games.append({
                    "away": a_name,
                    "home": b_name,
                    "away_score": a_sets,
                    "home_score": b_sets,
                    "state": state,
                    "detail": detail,
                    "start_utc": start,
                    "eid": str(comp.get("id", "")),
                })
    return games, "site.api.espn.com"


def gather_tennis_men(now, url):
    return gather_espn_tennis(now, url, "Men's Singles")


def gather_tennis_women(now, url):
    return gather_espn_tennis(now, url, "Women's Singles")


ADAPTERS = {
    "mlb": gather_mlb,
    "espn_team": gather_espn_team,
    "espn_tennis_men": gather_tennis_men,
    "espn_tennis_women": gather_tennis_women,
}

_STATE_RANK = {"in": 0, "pre": 1, "post": 2}


def _select(games):
    """Live first, then what is about to start, then what just finished. A rail the reader
    scrolls should open on the game that is happening now."""
    def key(g):
        state = g.get("state", "pre")
        start = g.get("start_utc") or ""
        # finals newest-first; everything else soonest-first
        return (_STATE_RANK.get(state, 3), start if state != "post" else _invert(start))
    return sorted(games, key=key)[:PER_LEAGUE]


def _invert(s):
    """Sort key that reverses a lexicographic ISO timestamp without reversing the tuple."""
    return "".join(chr(255 - ord(c)) if ord(c) < 255 else c for c in s)


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    leagues, sources = [], []
    seen_eids = set()
    attempted = 0
    failed = 0

    for label, chain in LEAGUES:
        attempted += 1
        games, source, error = [], "", None
        for kind, url in chain:
            adapter = ADAPTERS.get(kind)
            if not adapter:
                continue
            try:
                games, source = adapter(now, url)
                error = None
                break
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                continue
        if error is not None:
            failed += 1
            # ADVISORY, NEVER AN ERROR (house rule): an ::error:: on a green run trains
            # everyone to ignore annotations, and a league feed is not a publish gate.
            print(f"::warning::scores: {label} unavailable from every source ({error})")
            sources.append({"league": label, "status": "failed", "error": error})
            continue
        picked = _select(games)
        sources.append({
            "league": label,
            "status": "ok" if picked else "empty",
            "source": source,
            "games_seen": len(games),
            "games_kept": len(picked),
        })
        # The strip keys every card on data-eid and the client refresh takes the first
        # match, so one id may appear once on the whole rail.
        picked = [g for g in picked if not (g["eid"] in seen_eids or seen_eids.add(g["eid"]))]
        print(f"scores: {label} -> {len(games)} in-window games, kept {len(picked)}")
        if picked:
            leagues.append({"league": label, "source": source, "games": picked})

    if failed == attempted:
        print("scores: every league failed; leaving the committed snapshot in place")
        return 0

    # A league with a game in progress goes to the front of the rail; the rest keep the
    # editorial order declared in LEAGUES.
    order = {label: i for i, (label, _c) in enumerate(LEAGUES)}
    leagues.sort(key=lambda l: (0 if any(g.get("state") == "in" for g in l["games"]) else 1,
                                order.get(l["league"], 99)))

    total = sum(len(l["games"]) for l in leagues)
    if total > MAX_GAMES:
        budget = MAX_GAMES
        trimmed = []
        for l in leagues:
            if budget <= 0:
                break
            keep = min(len(l["games"]), max(2, budget))
            l["games"] = l["games"][:keep]
            budget -= keep
            trimmed.append(l)
        leagues = trimmed

    # stale_after_utc: the snapshot's own freshness policy, read by the build-time
    # guard in site_build.scores_strip() so the demote threshold lives in data, not
    # in a second hardcoded constant (2026-08-31: a bake older than this must not
    # render 'in' games as live).
    out = {"generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "stale_after_utc": (now + datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "leagues": leagues,
           # Every league's outcome, including the ones with nothing to show. This is what
           # makes a dead feed distinguishable from an off-season night without reading
           # workflow logs.
           "sources": sources}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    ok = sum(1 for s in sources if s["status"] == "ok")
    empty = sum(1 for s in sources if s["status"] == "empty")
    print(f"scores: wrote {OUT_PATH} ({sum(len(l['games']) for l in leagues)} games, "
          f"{len(leagues)} leagues on the rail; {ok} live-ish, {empty} idle, {failed} failed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
