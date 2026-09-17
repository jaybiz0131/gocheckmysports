#!/usr/bin/env python3
"""standings.py: the standings and the college football rankings (S-L1).

WHY A SEPARATE FETCHER. The band's file (scoreboard.json) is a day's games. Standings
are a season's shape, they change at a different rate, and they are read on pages the
band never touches. Same lane, same manners, its own file.

THE RULE THAT SHAPES THIS FILE. The upstream standings endpoint answers for the season
it considers current, and in September that is the 2026-27 season for basketball and
hockey: thirty teams at 0-0, a full table of numbers that are not readings. A table of
zeros is worse than no table, because it looks like a result. So a group is written
only when its teams have played, and a league with no played games is omitted entirely.
On 17 Sep 2026 that means NFL and MLB write and NBA and NHL do not, which is also what
a reader would expect of a sports desk in September.

The college football rankings are a different shape and are kept as one: the AP Top 25
with each team's record, the poll's week, and the movement since the last poll.

THE SEASON YEAR IS NOT RENDERED. The endpoint returned "2027" for MLB on 17 Sep 2026
while handing back the 2026 pennant race (Tampa Bay 92-59), because the upstream season
object rolls forward before the games do. It is kept in this file as provenance and the
pages do not print it: a table headed with the wrong year is a false statement, and the
desk cannot tell from the response which year the rows belong to. What the page carries
instead is the stamp, which is what the copy law asks of every section anyway.

Fail-safe, as elsewhere in the site lane: a league that fails is skipped and the others
still write; a total failure leaves the committed file alone; a file older than
STALE_HOURS renders marked rather than being withdrawn (L-4).

USAGE  python3 standings.py            refresh
       python3 standings.py --report   read the committed file
"""

import datetime
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

OUT = os.path.join(HERE, "site", "data", "standings.json")
TIMEOUT = 20
STALE_HOURS = 30          # a standings table is a day's fact, not an hour's

# (key, label, path, the word this league calls a division)
LEAGUES = [
    ("nfl", "NFL", "football/nfl", "division"),
    ("mlb", "MLB", "baseball/mlb", "division"),
    ("nba", "NBA", "basketball/nba", "division"),
    ("nhl", "NHL", "hockey/nhl", "division"),
]

STANDINGS = "https://site.api.espn.com/apis/v2/sports/{path}/standings?level=3"
RANKINGS = ("https://site.api.espn.com/apis/site/v2/sports/football/"
            "college-football/rankings")

# What a standings row carries. Everything here is a figure the source sends; nothing
# is computed, because a computed standing is an opinion about a tiebreak.
WANT = ["wins", "losses", "ties", "winPercent", "gamesBehind", "streak",
        "pointsFor", "pointsAgainst", "differential", "playoffSeed", "divisionRecord"]


def _get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": common.ua_for(url), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _stat(entry, name):
    for s in (entry.get("stats") or []):
        if s.get("name") == name:
            v = s.get("displayValue")
            return v if v not in (None, "") else None
    return None


def _played(entry):
    """Has this team played? A 0-0 row in a season that has not started is not a
    standing, and a group of them is not a table."""
    try:
        return int(_stat(entry, "wins") or 0) + int(_stat(entry, "losses") or 0) \
            + int(_stat(entry, "ties") or 0) > 0
    except ValueError:
        return False


def _row(entry):
    t = entry.get("team") or {}
    row = {"team": t.get("displayName") or t.get("name") or "",
           "abbr": t.get("abbreviation") or "",
           "short": t.get("shortDisplayName") or t.get("name") or ""}
    for k in WANT:
        v = _stat(entry, k)
        if v is not None:
            row[k] = v
    return row


def _groups(node, out=None, trail=()):
    """Every node that carries a table, with the conference it sits under."""
    out = [] if out is None else out
    entries = (node.get("standings") or {}).get("entries") or []
    name = node.get("name") or node.get("shortName") or ""
    if entries:
        # The nearest enclosing group, not the outermost: the trail for "AFC East" is
        # (National Football League, American Football Conference), and the league's
        # own name above a division table says nothing a reader needs.
        out.append({"name": name, "conference": trail[-1] if trail else "",
                    "entries": entries})
    for c in (node.get("children") or []):
        _groups(c, out, trail + ((name,) if name else ()))
    return out


def fetch_league(key, label, path):
    d = _get(STANDINGS.format(path=path))
    season = d.get("season")
    year = season.get("year") if isinstance(season, dict) else season
    groups = []
    for g in _groups(d):
        rows = [_row(e) for e in g["entries"] if _played(e)]
        # Part of a group having played is normal mid-week; none of it having played
        # means the season has not started, and the group is not written.
        if not rows:
            continue
        groups.append({"name": g["name"], "conference": g["conference"], "rows": rows})
    if not groups:
        return None
    return {"key": key, "league": label, "season": year, "groups": groups}


def fetch_rankings():
    d = _get(RANKINGS)
    poll = next((p for p in (d.get("rankings") or [])
                 if (p.get("shortName") or "").startswith("AP")), None)
    if not poll:
        return None
    rows = []
    for r in (poll.get("ranks") or []):
        t = r.get("team") or {}
        # In this feed `location` and `nickname` are both the school (Texas, Notre
        # Dame) and `name` is the mascot (Longhorns, Fighting Irish). Pairing location
        # with nickname printed "Texas Texas" down the whole poll.
        rows.append({"rank": r.get("current"), "previous": r.get("previous"),
                     "school": t.get("location") or t.get("nickname") or "",
                     "mascot": t.get("name") or "",
                     "abbr": t.get("abbreviation") or "",
                     "record": r.get("recordSummary") or "",
                     "trend": r.get("trend") or "",
                     "first_place": r.get("firstPlaceVotes")})
    if not rows:
        return None
    return {"poll": poll.get("name") or "AP Top 25",
            "week": (poll.get("occurrence") or {}).get("displayValue") or "",
            "rows": rows}


def refresh():
    out, failed, skipped = [], [], []
    for key, label, path, _word in LEAGUES:
        try:
            lg = fetch_league(key, label, path)
            if lg:
                out.append(lg)
            else:
                skipped.append(label)
        except Exception as e:
            failed.append(f"{label} ({type(e).__name__})")
    ranks = None
    try:
        ranks = fetch_rankings()
    except Exception as e:
        failed.append(f"CFB rankings ({type(e).__name__})")
    if not out and not ranks:
        print("standings: nothing resolved; committed file left alone")
        return None
    payload = {"fetched_at": datetime.datetime.now(datetime.timezone.utc)
                                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
               "leagues": out, "rankings": ranks,
               "failed": failed, "not_started": skipped}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    n = sum(len(g["rows"]) for lg in out for g in lg["groups"])
    print(f"standings: {len(out)} league(s), {n} team(s)"
          + (f", {len(ranks['rows'])} ranked" if ranks else "")
          + (f"; not started: {', '.join(skipped)}" if skipped else "")
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
    d["stale"] = age > STALE_HOURS
    if d["stale"]:
        print(f"standings: file is {age:.0f}h old, past {STALE_HOURS}h; "
              f"tables render marked stale")
    return d


def report():
    d = load()
    if not d:
        print("standings: no committed file")
        return
    print(f"standings: fetched {d['fetched_at']} ({d['age_hours']}h ago)"
          + (" STALE" if d.get("stale") else ""))
    for lg in d.get("leagues") or []:
        print(f"  {lg['league']} {lg.get('season') or ''}: "
              f"{len(lg['groups'])} group(s), "
              f"{sum(len(g['rows']) for g in lg['groups'])} team(s)")
    r = d.get("rankings")
    if r:
        print(f"  {r['poll']} {r['week']}: {len(r['rows'])} team(s)")
    if d.get("not_started"):
        print(f"  not started, omitted: {', '.join(d['not_started'])}")
    if d.get("failed"):
        print(f"  failed: {', '.join(d['failed'])}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        refresh()
