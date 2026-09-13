#!/usr/bin/env python3
"""where_to_watch.py: the NFL week's windows and the carriers that show them.

WHY THIS FILE EXISTS AND WHY IT IS NOT IN THE PIPELINE (S2, 2026-09-13). The order
says to build Where to Watch from "the league schedule feed the scoreboard already
uses". site/data/scores.json cannot support it: it carries no broadcast field at all,
and it is a scoreboard strip capped at six games per league, so on a Sunday every one
of its NFL rows sits in the same window and there is no week to page through.

The feed itself is fine. The cap and the missing carriers are scores.json's shape, not
ESPN's. The same endpoint scores_pulse.py already calls returns all sixteen events with
`broadcasts` and `geoBroadcasts` on every one. So this module reads that endpoint
directly and writes its own file, and scores_pulse.py is left alone: it runs inside
sports-news-brief.yml and this run does not touch pipeline files.

FOR LATER: if scores_pulse.py ever captures broadcasts itself, this module can drop its
fetch and read scores.json instead. That is a one-field change there and a deletion
here.

NOTHING IS EVER TYPED IN. Carriers come only from what the feed returns. NFL broadcast
windows are well enough known that writing them from memory would be easy and would
also be a news desk asserting facts it has not sourced. A game the league has not
announced a carrier for renders as unannounced.

FAIL-SAFE, in order:
  1. The fetch fails and the committed file is under STALE_DAYS old: keep it and render
     it with its own real "as of" stamp.
  2. Older than that, or missing: the page, the homepage card and the nav entry all
     disappear together. Never an empty table, never a stale week shown as current.
  3. A failed fetch never fails the build and never changes any other page.

USAGE  python3 where_to_watch.py          # refresh the file and report
       python3 where_to_watch.py --check  # report only, write nothing
"""

import datetime
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

OUT = os.path.join(HERE, "site", "data", "where-to-watch.json")
BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
TIMEOUT = 10
STALE_DAYS = 6          # past this the page is withdrawn rather than shown stale
WEEKS_AHEAD = 1         # this week plus next

# Carriers that are streaming services rather than channels. The feed's own type field
# says "TV" for most of these, so the distinction has to be made here.
STREAMERS = {"netflix", "prime video", "amazon prime video", "peacock", "paramount+",
             "espn+", "nfl+", "youtube tv", "youtube", "tubi", "max", "hulu"}

# ET window names, keyed on the local kickoff. Anything that does not fall in one of
# these renders under its own day and time rather than being forced into a slot.
def window_name(dt_et):
    wd, hhmm = dt_et.weekday(), dt_et.hour * 60 + dt_et.minute
    if wd == 3:
        return "Thursday night"
    if wd == 5:
        return "Saturday"
    if wd == 0:
        return "Monday night"
    if wd == 6:
        if hhmm < 13 * 60:
            return "Sunday morning"          # the international window
        if hhmm < 16 * 60:
            return "Sunday afternoon, 1:00 ET"
        if hhmm < 19 * 60:
            return "Sunday afternoon, 4:05 and 4:25 ET"
        return "Sunday night"
    return dt_et.strftime("%A")


WINDOW_ORDER = ["Thursday night", "Friday", "Saturday", "Sunday morning",
                "Sunday afternoon, 1:00 ET", "Sunday afternoon, 4:05 and 4:25 ET",
                "Sunday night", "Monday night"]


def _et(iso):
    """ESPN stamps Zulu. Eastern is UTC-4 through the regular season; the feed also
    prints a local time string, and the two agree, so this is only used for grouping."""
    try:
        dt = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%MZ")
    except ValueError:
        try:
            dt = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    return dt.replace(tzinfo=datetime.timezone.utc) - datetime.timedelta(hours=4)


def _get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": common.ua_for(url),
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _carriers(comp):
    """Only what the feed returns. geoBroadcasts carries market and type; broadcasts is
    the fallback and is national by convention."""
    out, seen = [], set()
    for g in comp.get("geoBroadcasts") or []:
        name = ((g.get("media") or {}).get("shortName") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        market = ((g.get("market") or {}).get("type") or "National").strip().title()
        kind = "Streaming" if name.lower() in STREAMERS else \
            (((g.get("type") or {}).get("shortName") or "TV").strip() or "TV")
        out.append({"name": name, "market": market, "type": kind})
    if not out:
        for b in comp.get("broadcasts") or []:
            for name in b.get("names") or []:
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                out.append({"name": name,
                            "market": (b.get("market") or "national").title(),
                            "type": "Streaming" if name.lower() in STREAMERS else "TV"})
    return out


def _week(params=""):
    d = _get(BASE + (("?" + params) if params else ""))
    season = (d.get("season") or {})
    wk = (d.get("week") or {}).get("number")
    games = []
    for e in d.get("events") or []:
        comp = (e.get("competitions") or [{}])[0]
        teams, scores = {}, {}
        for c in comp.get("competitors") or []:
            ha = c.get("homeAway")
            teams[ha] = ((c.get("team") or {}).get("abbreviation")
                         or (c.get("team") or {}).get("shortDisplayName") or "")
            scores[ha] = c.get("score")
        et = _et(e.get("date") or "")
        # STATUS COMES FROM THE FEED, NEVER FROM THE CLOCK. A build running at 03:00
        # UTC on Saturday cannot tell from the time alone whether Thursday's game
        # finished, was postponed or is in a weather delay. The feed says.
        st = ((e.get("status") or {}).get("type") or {})
        games.append({
            "away": teams.get("away", ""), "home": teams.get("home", ""),
            "kickoff_utc": e.get("date") or "",
            "kickoff_et": et.strftime("%-I:%M %p ET") if et else "",
            "day_et": et.strftime("%a %-d %b") if et else "",
            "window": window_name(et) if et else "",
            "carriers": _carriers(comp),
            "state": st.get("state") or "",              # pre | in | post
            "completed": bool(st.get("completed")),
            "status": st.get("shortDetail") or st.get("description") or "",
            "away_score": scores.get("away"), "home_score": scores.get("home"),
        })
    games.sort(key=lambda g: g["kickoff_utc"])
    return {"season": season.get("year"), "season_type": season.get("type"),
            "week": wk, "games": games}


def refresh(check=False):
    """Fetch this week and the next. Returns the payload, or None on any failure."""
    try:
        cur = _week()
    except Exception as e:
        print(f"where_to_watch: fetch failed ({type(e).__name__}); leaving the "
              f"committed file alone")
        return None
    weeks = [cur]
    for n in range(1, WEEKS_AHEAD + 1):
        try:
            nxt = _week(f"seasontype={cur.get('season_type') or 2}&week={(cur['week'] or 0) + n}")
            if nxt.get("games"):
                weeks.append(nxt)
        except Exception:
            pass                       # one missing future week is not a failure
    payload = {
        "fetched_at": datetime.datetime.now(datetime.timezone.utc)
                              .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "ESPN NFL scoreboard",
        "weeks": weeks,
    }
    if not check:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
    return payload


def load(max_age_days=STALE_DAYS):
    """What site_build reads. None means render nothing anywhere."""
    try:
        d = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        return None
    try:
        got = datetime.datetime.strptime(d.get("fetched_at", ""), "%Y-%m-%dT%H:%M:%SZ") \
            .replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None
    age = (datetime.datetime.now(datetime.timezone.utc) - got).days
    if age > max_age_days:
        print(f"where_to_watch: file is {age} days old, past the {max_age_days}-day "
              f"limit; the page and its nav entry are withdrawn")
        return None
    d["age_days"] = age
    return d


def main():
    check = "--check" in sys.argv
    p = refresh(check=check) or load()
    if not p:
        print("where_to_watch: nothing to render")
        return 0
    for w in p.get("weeks") or []:
        wins = {}
        for g in w.get("games") or []:
            wins.setdefault(g["window"], []).append(g)
        nc = sum(1 for g in w.get("games") or [] if not g["carriers"])
        print(f"  week {w.get('week')}: {len(w.get('games') or [])} games, "
              f"{len(wins)} windows, {nc} without a carrier yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
