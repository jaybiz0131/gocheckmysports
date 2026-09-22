#!/usr/bin/env python3
"""schedules.py: a team's season, for the team pages (S-L2).

WHY A THIRD FILE IN THE LANE. scoreboard.json is today's games and standings.json is
the season's shape. Neither holds a team's own season: the fixtures it has played, what
happened, and what is next. That is the spine of a team page, and it is one request per
team, so it is fetched on its own schedule and cached rather than read on every build.

SCOPE. The NFL only, for now. A team page is worth building where the desk has the rest
of the furniture to put on it (the inactives board, the designations, the standings row
and the stories), and that is the NFL today. A seventeen-game season is also a schedule
a reader can hold in one view; a 162-game one is a different page and a different
decision.

CACHING. Thirty-two requests is not something to do on every build. The file carries
its own fetch time and refresh() is a no-op inside MAX_AGE_HOURS unless --force is
passed, so a build that runs four times an hour costs nothing after the first.

Fail-safe: a team that fails keeps whatever the committed file already had for it, so
one bad response costs one team's freshness and never the page.

USAGE  python3 schedules.py            refresh if the file is old enough
       python3 schedules.py --force    refresh regardless
       python3 schedules.py --report   read the committed file
"""

import datetime
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

OUT = os.path.join(HERE, "site", "data", "schedules.json")
STANDINGS = os.path.join(HERE, "site", "data", "standings.json")
TIMEOUT = 20
MAX_AGE_HOURS = 6         # fixtures move rarely; results settle within the hour
STALE_HOURS = 30
SPACING = 0.35            # polite, the same manners common.fetch_page_meta keeps
LEAGUE = "nfl"
PATH = "football/nfl"

URL = ("https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{abbr}/schedule")


def _get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": common.ua_for(url), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _teams():
    """The league's teams, from the standings file rather than a call of its own. If
    the standings have not been fetched there is nothing to build pages for anyway."""
    try:
        d = json.load(open(STANDINGS, encoding="utf-8"))
    except Exception:
        return []
    for lg in (d.get("leagues") or []):
        if lg.get("key") == LEAGUE:
            return sorted({r["abbr"] for g in lg["groups"] for r in g["rows"]
                           if r.get("abbr")})
    return []


def _event(ev, abbr):
    """One fixture, from this team's side. A score is carried only when the game is
    over: an in-progress or scheduled game has no result, and printing a 0 for one
    would be inventing a reading."""
    comp = (ev.get("competitions") or [{}])[0]
    status = ((comp.get("status") or {}).get("type") or {})
    state = status.get("state") or ""
    us = them = None
    for c in (comp.get("competitors") or []):
        (us, them) = ((c, them) if (c.get("team") or {}).get("abbreviation") == abbr
                      else (us, c))
    if not us or not them:
        return None

    def score(c):
        v = c.get("score")
        if isinstance(v, dict):
            v = v.get("displayValue")
        try:
            return int(str(v))
        except (TypeError, ValueError):
            return None

    # timeValid is the feed saying whether the kickoff time is set. Week 18 comes back
    # at 05:00Z with timeValid false, which renders as "12:00 AM ET" if it is believed:
    # a precise time the league has not announced. The date is real, the clock is not.
    out = {"id": ev.get("id"), "date": ev.get("date"), "state": state,
           "time_set": bool(ev.get("timeValid", True)),
           "week": (ev.get("week") or {}).get("number"),
           "home": (us.get("homeAway") == "home"),
           "opp": (them.get("team") or {}).get("abbreviation") or "",
           "opp_name": (them.get("team") or {}).get("shortDisplayName")
                       or (them.get("team") or {}).get("name") or "",
           # N-1: the opponent's full name, the same field the scoreboard takes.
           "opp_full": (them.get("team") or {}).get("displayName") or ""}
    net = ((comp.get("broadcasts") or [{}])[0].get("names") or [])
    if net:
        out["network"] = net[0]
    if state == "post":
        a, b = score(us), score(them)
        if a is not None and b is not None:
            out["score"], out["opp_score"] = a, b
            out["result"] = "W" if a > b else ("L" if a < b else "T")
    return out


def refresh(force=False):
    prev = {}
    try:
        old = json.load(open(OUT, encoding="utf-8"))
        prev = old.get("teams") or {}
        t = datetime.datetime.strptime(old["fetched_at"], "%Y-%m-%dT%H:%M:%SZ") \
            .replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 3600
        if not force and age < MAX_AGE_HOURS:
            print(f"schedules: file is {age:.1f}h old, inside {MAX_AGE_HOURS}h; kept")
            return old
    except Exception:
        pass

    abbrs = _teams()
    if not abbrs:
        print("schedules: no team list (standings not fetched); nothing written")
        return None
    teams, failed = dict(prev), []
    got = 0
    for n, abbr in enumerate(abbrs):
        if n:
            time.sleep(SPACING)
        try:
            d = _get(URL.format(path=PATH, abbr=abbr))
            evs = [x for x in (_event(e, abbr) for e in (d.get("events") or [])) if x]
            if not evs:
                failed.append(abbr)
                continue
            t = d.get("team") or {}
            teams[abbr] = {
                "abbr": abbr,
                "name": t.get("displayName") or t.get("name") or abbr,
                "short": t.get("shortDisplayName") or t.get("name") or abbr,
                "nickname": t.get("name") or "",
                "location": t.get("location") or "",
                "color": ("#" + t["color"]) if t.get("color") else "",
                "bye": (d.get("byeWeek") if isinstance(d.get("byeWeek"), int) else None),
                "events": evs,
            }
            got += 1
        except Exception as e:
            failed.append(f"{abbr} ({type(e).__name__})")
    if not teams:
        print("schedules: every team failed; committed file left alone")
        return None
    payload = {"fetched_at": datetime.datetime.now(datetime.timezone.utc)
                                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
               "league": LEAGUE.upper(), "teams": teams, "failed": failed}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print(f"schedules: {got}/{len(abbrs)} team(s) refreshed, {len(teams)} on file"
          + (f"; kept from before: {', '.join(failed)}" if failed else ""))
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
    return d


def report():
    d = load()
    if not d:
        print("schedules: no committed file")
        return
    print(f"schedules: fetched {d['fetched_at']} ({d['age_hours']}h ago)"
          + (" STALE" if d.get("stale") else ""))
    teams = d.get("teams") or {}
    played = sum(1 for t in teams.values() for e in t["events"] if e.get("result"))
    print(f"  {len(teams)} team(s), "
          f"{sum(len(t['events']) for t in teams.values())} fixture(s), "
          f"{played} with a result")
    if d.get("failed"):
        print(f"  kept from before: {', '.join(d['failed'])}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        refresh(force="--force" in sys.argv)
