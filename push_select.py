#!/usr/bin/env python3
"""push_select.py: the one-push rule of S-3b.4 in Python.

The relay is JavaScript (netlify/lib/select.mjs, tick.mjs). This is its twin for the offline
canary: the same rule over the same fixture (fixtures/push_fixture.json), so a machine without
Node still proves the rule, and a machine with Node proves the two agree. If this and the
JavaScript ever disagree on the fixture, push_canary goes red.

THE RULE. A device that follows a team is sent one push for each of that team's games, on the
evening before the game by the Eastern calendar (7:00 PM ET to the end of that day), and never a
second for the same game: the device's record of what it was sent is checked first and written
before the send.
"""

import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SEND_FROM_HOUR_ET = 19
COND_MAX_AGE = datetime.timedelta(hours=36)


def _utc(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    except (ValueError, AttributeError):
        return None


def in_window(game, now):
    kick = _utc(game.get("kick"))
    if kick is None or kick <= now:
        return False
    n, k = now.astimezone(ET), kick.astimezone(ET)
    return n.date() == k.date() - datetime.timedelta(days=1) and n.hour >= SEND_FROM_HOUR_ET


def select_sends(subs, games, now):
    out, seen = [], set()
    for g in games:
        if not g.get("id") or g["id"] in seen:
            continue
        seen.add(g["id"])
        if not in_window(g, now):
            continue
        for s in subs:
            if (s.get("sent") or {}).get(g["id"]):
                continue
            if set(s.get("teams") or []) & set(g.get("teams") or []):
                out.append((s["id"], g["id"]))
    return out


def simulate(fixture):
    """Hourly ticks over the fixture's range with an always-accepting sender. Returns the list of
    (sub, game, tick) pushes, the way tick.mjs would send them."""
    subs = [dict(s, sent=dict(s.get("sent") or {})) for s in fixture["subs"]]
    by = {s["id"]: s for s in subs}
    sent = []
    t, end = _utc(fixture["ticks_from"]), _utc(fixture["ticks_to"])
    while t < end:
        for sid, gid in select_sends(subs, fixture["games"], t):
            by[sid]["sent"][gid] = t.isoformat()      # the mark is written before the send
            sent.append([sid, gid, t.strftime("%Y-%m-%dT%H:%M:%SZ")])
        t += datetime.timedelta(hours=1)
    return sorted(sent)


def message_for(game, now):
    at = _utc(game.get("cond_at") or "")
    fresh = bool(game.get("cond")) and at is not None and now - at <= COND_MAX_AGE
    return {"title": f"Tomorrow: {game['title']}",
            "body": f"{game['lead']} {game['cond']}." if fresh else game["lead"],
            "url": game["path"], "tag": f"game-{game['id']}"}
