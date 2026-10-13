#!/usr/bin/env python3
"""carriage.py: which service carries which game, from the hand-kept data/carriage.json.

Sprint S-1 item 1 (12 October 2026). The feed names the network of each game; it does not
name the streams. The streams come from rows a person kept, each with the service's own page
as its source and the date it was read. Nothing here is guessed:

  * a row prints its service only while its status is "ok" AND its verified date is within
    `stale_days` of the build date (30); otherwise it prints "verify", and a game that
    matches a verify row shows one "verify" chip;
  * a game that matches no row shows no stream at all.

The window of a game (early, 1:00, 4:05 and 4:25, night; afternoon for a Saturday) is a
function of its kickoff in Eastern, computed here from the zone and never from a fixed
offset. Pure functions, standard library only.
"""

import datetime
import json
import os
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "data", "carriage.json")

WINDOW_LABEL = {"early": "Early", "1:00": "1:00", "4:05-4:25": "4:05 and 4:25",
                "afternoon": "Afternoon", "night": "Night"}
WINDOW_ORDER = ["early", "1:00", "afternoon", "4:05-4:25", "night"]
DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_ALIAS = {"fox": "fox", "nfl net": "nfl network", "nfl network": "nfl network",
          "amazon prime video": "prime video", "prime video": "prime video",
          "sec network": "sec network", "secn": "sec network",
          "acc network": "acc network", "accn": "acc network"}


def norm(name):
    n = (name or "").strip().lower()
    return _ALIAS.get(n, n)


def load(path=None):
    try:
        with open(path or PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def window_key(kick_utc, league):
    """The window a kickoff sits in, from its Eastern time."""
    et = kick_utc.astimezone(ET)
    m = et.hour * 60 + et.minute
    if league == "NFL":
        if et.weekday() == 6:
            if m < 12 * 60 + 30:
                return "early"
            if m < 15 * 60:
                return "1:00"
            if m < 19 * 60:
                return "4:05-4:25"
            return "night"
        return "night" if m >= 18 * 60 else "afternoon"
    if m < 14 * 60:
        return "early"
    if m < 18 * 60:
        return "afternoon"
    return "night"


def _fresh(row, today, stale_days):
    if row.get("status") != "ok":
        return False
    try:
        v = datetime.date.fromisoformat(row.get("verified") or "")
    except ValueError:
        return False
    age = (today - v).days
    return 0 <= age <= stale_days


def streams_for(game, kick_utc, doc, today):
    """The stream chips for one game: [{"label", "state"}], state "ok" or "verify".

    `game` carries league, carriers (the feed's networks); `kick_utc` is an aware datetime;
    `today` is the manifest's date. The verify chip is last and appears once."""
    if not doc:
        return []
    league = game.get("league") or "NFL"
    nets = {norm(c.get("name")) for c in (game.get("carriers") or [])}
    day = DAY[kick_utc.astimezone(ET).weekday()]
    win = window_key(kick_utc, league)
    stale = int(doc.get("stale_days") or 30)
    ok, verify, seen = [], [], set()
    for r in doc.get("rows") or []:
        if league not in (r.get("leagues") or []):
            continue
        m = r.get("match") or {}
        rn = [norm(x) for x in (m.get("networks") or [])]
        if "*" not in rn and not (nets & set(rn)):
            continue
        if "*" not in (m.get("days") or ["*"]) and day not in m["days"]:
            continue
        if "*" not in (m.get("windows") or ["*"]) and win not in m["windows"]:
            continue
        label = r.get("label") or r.get("service") or ""
        if label in seen:
            continue
        seen.add(label)
        (ok if _fresh(r, today, stale) else verify).append(
            {"label": label, "state": "ok" if _fresh(r, today, stale) else "verify",
             "id": r.get("id")})
    out = ok[:]
    if verify:
        out.append({"label": "verify", "state": "verify",
                    "services": [v["label"] for v in verify],
                    "id": ",".join(v["id"] for v in verify)})
    return out


def verify_rows(doc, today):
    """Rows that print verify at `today`: not ok, or older than stale_days. For the report."""
    stale = int((doc or {}).get("stale_days") or 30)
    return [r for r in (doc or {}).get("rows") or [] if not _fresh(r, today, stale)]
