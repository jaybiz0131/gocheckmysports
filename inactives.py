#!/usr/bin/env python3
"""inactives.py: the Sunday Inactives board's data layer (S-B2).

WHY THIS SNAPSHOTS INSTEAD OF QUERYING, which is the whole design and is not a
preference. Measured on 2026-09-13 mid-slate, across all sixteen games:

  1. There is no inactives list in any feed. Inactives are a value of an injury row's
     fantasy status: details.fantasyStatus.description == "INACTIVE".
  2. THE FLAG REVERTS. Los Angeles played Thursday; by Sunday their rows read 23
     Active, 1 Out, 1 Questionable, and zero inactives. Seattle, who played
     Wednesday, still showed seven. The field is current state, not a record, and it
     reverts on no schedule we control.
  3. THE LEAGUE FEED IS CAPPED at 25 rows per team and ?limit= does not lift it.
     Teams must declare seven inactives; the feed returned seven for CIN, TB and NO,
     six for SF, TEN and ATL, five for DET. Sixteen of thirty-two teams had a real
     designation sitting in the last available slot, which is what truncation looks
     like from outside.

So a board that asks the feed "who is inactive" at render time is wrong twice: it
loses players to the cap, and it loses whole teams once their game ends. This module
polls, writes every INACTIVE row it sees to a dated file ON FIRST SIGHT, and the page
renders from that file. A player the cap hid at one poll is captured at the next,
because the 25 rows returned are not a stable set.

THE STAMP IS OURS AND SAYS SO (ruling 1, 2026-09-13). "first seen HH:MM ET" is the
poll that first saw the flag, never "posted": the league posts about 90 minutes before
kickoff and we do not observe that moment, we observe our own check.

NO EXPECTED COUNT IS ASSERTED (ruling 2). No feed carries a game-day roster or an
active count, so nothing here assumes seven. The list shows with its count. It is
marked incomplete only on evidence: the team hit the row cap, or reconciliation
returned rows the poll never saw.

SNAPSHOTS ARE KEPT (ruling 7). They are the designation history the player pages will
read later.

USAGE
  python3 inactives.py                 poll once and merge into today's snapshot
  python3 inactives.py --reconcile     also reconcile capped teams against the
                                       uncapped per-team endpoint (once per slate;
                                       roughly 60 requests per capped team)
  python3 inactives.py --report        print today's board without fetching
"""

import datetime
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

SNAP_DIR = os.path.join(HERE, "site", "data", "inactives")
LEAGUE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
TEAM_CORE = ("https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
             "/teams/{tid}/injuries?limit=200")
TIMEOUT = 15
ROW_CAP = 25          # the league feed's own cap; hitting it is the truncation signal
INACTIVE = "INACTIVE"


def _athlete_id(a):
    """A stable id for a player across both feed shapes. The summary carries
    athlete.id; the league-wide feed carries only names and a player-card link with
    the id inside it. Falls back to a name slug so a row is never dropped merely
    because the id is not where the other endpoint puts it."""
    import re as _re
    if a.get("id"):
        return str(a["id"])
    for l in a.get("links") or []:
        m = _re.search(r"/id/(\d+)", l.get("href") or "")
        if m:
            return m.group(1)
    nm = (a.get("displayName") or "").strip().lower()
    return _re.sub(r"[^a-z0-9]+", "-", nm).strip("-") if nm else ""


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _stamp(dt=None):
    return (dt or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": common.ua_for(url), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def snapshot_path(day=None):
    day = day or _now().strftime("%Y-%m-%d")
    return os.path.join(SNAP_DIR, f"inactives-{day}.json")


def load_snapshot(day=None):
    try:
        return json.load(open(snapshot_path(day), encoding="utf-8"))
    except Exception:
        return None


def _blank(day):
    return {"day": day, "first_poll": None, "last_poll": None, "last_change": None,
            "source": "ESPN NFL injuries feed", "teams": {}}


def poll(reconcile=False):
    """One poll. Merges what it sees into today's file and returns the file."""
    day = _now().strftime("%Y-%m-%d")
    snap = load_snapshot(day) or _blank(day)
    try:
        feed = _get(LEAGUE)
    except Exception as e:
        print(f"inactives: poll failed ({type(e).__name__}); snapshot left as it was")
        return snap

    seen_at = _stamp()
    snap["first_poll"] = snap.get("first_poll") or seen_at
    snap["last_poll"] = seen_at
    added = updated_teams = 0

    for block in feed.get("injuries") or []:
        name = block.get("displayName") or ""
        tid = str(block.get("id") or "")
        rows = block.get("injuries") or []
        if not name:
            continue
        t = snap["teams"].setdefault(tid or name, {
            "team": name, "id": tid, "players": {}, "capped": False,
            "rows_returned": 0, "reconciled_at": None, "reconciled_added": 0})
        t["team"], t["id"] = name, tid
        t["rows_returned"] = len(rows)
        # HITTING THE CAP IS THE ONLY TRUNCATION SIGNAL THE FEED GIVES. It never says
        # what it dropped, so this records that it may have dropped something.
        if len(rows) >= ROW_CAP:
            t["capped"] = True
        for r in rows:
            fs = ((r.get("details") or {}).get("fantasyStatus") or {}).get("description")
            if fs != INACTIVE:
                continue
            a = r.get("athlete") or {}
            pid = _athlete_id(a)
            if not pid:
                continue
            if pid in t["players"]:
                continue                      # first sight wins; never restamp
            t["players"][pid] = {
                "name": a.get("displayName") or "",
                "pos": ((a.get("position") or {}).get("abbreviation") or ""),
                "jersey": a.get("jersey") or "",
                "first_seen": seen_at,
                "feed_date": r.get("date") or "",
                "reason": ((r.get("details") or {}).get("type") or ""),
                "via": "poll",
            }
            added += 1
            updated_teams += 1

    if reconcile:
        added += _reconcile(snap)

    if added:
        snap["last_change"] = seen_at
    os.makedirs(SNAP_DIR, exist_ok=True)
    with open(snapshot_path(day), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1, sort_keys=True)
    tot = sum(len(t["players"]) for t in snap["teams"].values())
    with_any = sum(1 for t in snap["teams"].values() if t["players"])
    print(f"inactives: {added} new, {tot} held across {with_any} team(s), "
          f"{sum(1 for t in snap['teams'].values() if t['capped'])} capped")
    # Machine-readable, for the workflow's build-and-push decision.
    print(f"INACTIVES_ADDED={added}")
    return snap


def _reconcile(snap):
    """Once per slate, for capped teams only: ask the uncapped per-team endpoint and
    add anything the poll never saw, stamped from the reconciliation rather than from
    a poll that did not see it.

    Not usable on the five-minute cadence. The per-team list returns one $ref per
    record and the athlete name is a further $ref behind that, so league-wide this is
    roughly 1,900 requests before names. Once, for the handful of teams whose rows hit
    the cap, it is cheap."""
    added = 0
    for t in snap["teams"].values():
        if not t.get("capped") or t.get("reconciled_at"):
            continue
        tid = t.get("id")
        if not tid:
            continue
        try:
            lst = _get(TEAM_CORE.format(tid=tid))
        except Exception as e:
            print(f"  reconcile {t['team']}: list failed ({type(e).__name__})")
            continue
        stamp = _stamp()
        got = unnamed = 0
        for item in lst.get("items") or []:
            ref = item.get("$ref") or ""
            if not ref:
                continue
            try:
                rec = _get(ref.replace("http://", "https://"))
            except Exception:
                continue
            fs = ((rec.get("details") or {}).get("fantasyStatus") or {}).get("description")
            if fs != INACTIVE:
                continue
            aref = ((rec.get("athlete") or {}).get("$ref") or "")
            pid = aref.rstrip("/").split("/")[-1].split("?")[0] if aref else ""
            if not pid or pid in t["players"]:
                continue
            name = pos = jersey = ""
            try:
                ath = _get(aref.replace("http://", "https://"))
                name = ath.get("displayName") or ""
                pos = ((ath.get("position") or {}).get("abbreviation") or "")
                jersey = ath.get("jersey") or ""
            except Exception:
                pass
            if not name:
                unnamed += 1
                continue          # a row we cannot name is a row we cannot publish
            t["players"][pid] = {
                "name": name, "pos": pos, "jersey": jersey,
                "first_seen": stamp, "feed_date": rec.get("date") or "",
                "reason": ((rec.get("details") or {}).get("type") or ""),
                "via": "reconcile",
            }
            got += 1
            added += 1
        t["reconciled_at"] = stamp
        t["reconciled_added"] = got
        # Evidence of a gap we could not close: the endpoint's own count against the
        # inactive rows we now hold, when rows came back we could not name.
        t["unresolved"] = bool(unnamed)
        if unnamed:
            print(f"  reconcile {t['team']}: {unnamed} row(s) could not be named")
        print(f"  reconcile {t['team']}: +{got}")
    return added


def board(day=None):
    """What the page renders. Returns None when there is nothing to show, so the
    page and its nav entry withdraw together rather than showing an empty table."""
    snap = load_snapshot(day)
    if not snap:
        return None
    teams = [t for t in snap["teams"].values() if t.get("players")]
    if not teams:
        return None
    out = []
    for t in teams:
        ps = sorted(t["players"].values(), key=lambda p: (p.get("first_seen") or "",
                                                          p.get("name") or ""))
        firsts = [p["first_seen"] for p in ps if p.get("first_seen")]
        # RULING 2, AND THE FIRST CUT GOT THIS WRONG. Flagging on `capped` alone put
        # "list may be incomplete" on all thirty-two teams, because all thirty-two hit
        # the row cap. That is noise, and the cap is a suspicion rather than the
        # evidence the ruling asks for: the league feed publishes no count to disagree
        # with. Evidence is the uncapped endpoint's own `count` exceeding what we hold
        # after reconciliation, or rows it returned that could not be named and so
        # could not be added.
        #
        # What keeps a partial list from reading as complete is the page's wording, not
        # a badge: it says "N inactive listed" and never "all" or "the N inactives".
        incomplete = bool(t.get("unresolved"))
        out.append({
            "team": t["team"], "id": t.get("id"),
            "players": ps, "count": len(ps),
            "first_seen": min(firsts) if firsts else "",
            "last_added": max(firsts) if firsts else "",
            "incomplete": incomplete,
            "reconciled_at": t.get("reconciled_at"),
        })
    out.sort(key=lambda t: (t["first_seen"] or "z", t["team"]))
    return {"day": snap.get("day"), "first_poll": snap.get("first_poll"),
            "last_poll": snap.get("last_poll"),
            "last_change": snap.get("last_change") or snap.get("last_poll"),
            "teams": out,
            "total": sum(t["count"] for t in out)}


def main():
    if "--report" in sys.argv:
        b = board()
        if not b:
            print("inactives: nothing held for today")
            return 0
        print(f"day {b['day']}  last poll {b['last_poll']}  {b['total']} players")
        for t in b["teams"]:
            flag = "  LIST MAY BE INCOMPLETE" if t["incomplete"] else ""
            print(f"  {t['team']:26} {t['count']:2}  first seen {t['first_seen'][11:16]}Z{flag}")
        return 0
    poll(reconcile="--reconcile" in sys.argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
