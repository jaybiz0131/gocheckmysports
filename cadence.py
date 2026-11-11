#!/usr/bin/env python3
"""cadence.py: when the site rebuilds for scores (Sprint A of the November 7 2026 audit, A2).

THE SITE HAS NO LIVE SCORE LAYER. The Worker's /live route (J-4) was never deployed and the
client poll left with the word "live" on 12 October, so every score a reader sees is the one
the last Netlify build fetched. Nothing rebuilt the site on a clock (the build hook secret is
empty), so on Saturday 7 November the whole site read "Updated Nov 7, 6:00 AM ET" at 5:25 PM
with 51 college games on the board and not one score on a Saturday card.

The cure is builds during games. This file decides, on each tick of scores-cadence.yml, whether
a build is due now. When it is, the workflow commits the refreshed site/data/scoreboard.json,
and that push builds the site (netlify_ignore.py builds any push that touches it).

THE CADENCE, by the ET day the slate belongs to (a game after midnight belongs to the day it
kicked off, so the cut is 4:00 AM ET):

  every day        the morning build, the first tick at or after 6:00 AM ET
  Sat and Sun      every 30 minutes from the first kickoff to the last final, then one at the final
  Mon and Thu      at each kickoff, at each halftime and at each final
  other days       one after the last game of the night

A tick that is not due fetches nothing when the committed snapshot shows no game near its
kickoff, so a quiet Tuesday costs a few seconds of runner and no request.

Pure apart from tick(), so the canary feeds it fixtures and a fixture clock.

USAGE  python3 cadence.py --tick [--last-build ISO]   decide, refresh when due, print due=...
"""

import datetime
import json
import os
import subprocess
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc

LEAGUES = ("NFL", "CFB")      # the board's leagues (Program 7)
WEEKEND = (5, 6)              # Saturday, Sunday
NIGHTS = (0, 3)               # Monday, Thursday
EVERY_MIN = 30
EARLY_MIN = 5                 # a 10-minute tick lands within 5 minutes of the half hour
MIN_GAP_MIN = 8               # never two builds closer than this
MORNING_HOUR = 6
DAY_CUT_HOURS = 4             # 1:30 AM Sunday is still Saturday's slate
NEAR_BEFORE_MIN = 15          # a game this close to kickoff makes a tick fetch
NEAR_AFTER_HOURS = 6          # a game this long after kickoff may still be on


def _utc(iso):
    if not iso:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)


def games(sb):
    """{id: game} for the board's leagues."""
    out = {}
    for L in (sb or {}).get("leagues") or []:
        if L.get("league") not in LEAGUES:
            continue
        for g in L.get("games") or []:
            if g.get("id") is not None:
                out[str(g["id"])] = g
    return out


def slate_day(now):
    return (now.astimezone(ET) - datetime.timedelta(hours=DAY_CUT_HOURS)).date()


def _half(g):
    return "half" in (g.get("status_short") or "").lower()


def decide(now, cur, prev, last_build):
    """(due, reason). `cur` is the snapshot just fetched, `prev` the committed one the last
    build was made from, `last_build` the newest build time known (aware datetime or None)."""
    now = now.astimezone(UTC)
    et = now.astimezone(ET)
    if last_build is None:
        return True, "no build on record"
    since = (now - last_build).total_seconds() / 60
    if since < MIN_GAP_MIN:
        return False, f"last build {since:.0f} min ago"
    morning = et.replace(hour=MORNING_HOUR, minute=0, second=0, microsecond=0)
    if et >= morning and last_build < morning:
        return True, "the morning build"

    gc, gp = games(cur), games(prev)
    live = [g for g in gc.values() if g.get("state") == "in"]
    unread = [g for g in gc.values() if g.get("state") == "pre"
              and (_utc(g.get("start_utc")) or now) <= now
              and now - (_utc(g.get("start_utc")) or now) < datetime.timedelta(hours=NEAR_AFTER_HOURS)]
    active = bool(live or unread)
    finals = [i for i, g in gc.items() if g.get("state") == "post"
              and (gp.get(i) or {}).get("state") != "post"]
    kicked = [i for i, g in gc.items() if g.get("state") == "in"
              and (gp.get(i) or {}).get("state") not in ("in", "post")]
    halves = [i for i, g in gc.items() if g.get("state") == "in" and _half(g)
              and not _half(gp.get(i) or {})]
    soon = [g for g in gc.values() if g.get("state") == "pre"
            and now < (_utc(g.get("start_utc")) or now) <= now + datetime.timedelta(hours=3)]

    wd = slate_day(now).weekday()
    if wd in WEEKEND:
        if active and since >= EVERY_MIN - EARLY_MIN:
            return True, f"every {EVERY_MIN} minutes while {len(live) + len(unread)} game(s) are on"
        if finals and not active:
            return True, f"the last final ({len(finals)} new)"
        return False, ("games on, last build " f"{since:.0f} min ago" if active else "no game on")
    if wd in NIGHTS:
        bits = [f"{len(kicked)} kickoff(s)" if kicked else "", f"{len(halves)} halftime(s)" if halves else "",
                f"{len(finals)} final(s)" if finals else ""]
        bits = [b for b in bits if b]
        if bits:
            return True, "game-night milestone: " + ", ".join(bits)
        return False, "no kickoff, halftime or final since the last build"
    if finals and not active and not soon:
        return True, f"after the last game ({len(finals)} final(s))"
    return False, "a weekday: the morning build and one after the last game"


def worth_fetching(now, prev, last_build):
    """True when a tick should fetch the feed before deciding: the morning build is due, or the
    committed snapshot has a game near or past its kickoff that it does not show final."""
    if last_build is None:
        return True
    et = now.astimezone(ET)
    morning = et.replace(hour=MORNING_HOUR, minute=0, second=0, microsecond=0)
    if et >= morning and last_build < morning:
        return True
    for g in games(prev).values():
        k = _utc(g.get("start_utc"))
        if not k or g.get("state") == "post":
            continue
        if now - datetime.timedelta(hours=NEAR_AFTER_HOURS) <= k <= now + datetime.timedelta(minutes=NEAR_BEFORE_MIN):
            return True
    return False


def _last_snapshot_commit():
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%cI", "--", "site/data/scoreboard.json"],
                           cwd=HERE, capture_output=True, text=True, timeout=15)
        return _utc(r.stdout.strip())
    except Exception:
        return None


def tick(argv):
    import scoreboard
    stamp = argv[argv.index("--last-build") + 1] if "--last-build" in argv else ""
    known = [t for t in (_utc(stamp), _last_snapshot_commit()) if t]
    last = max(known) if known else None
    now = datetime.datetime.now(UTC)
    try:
        prev = json.load(open(scoreboard.OUT, encoding="utf-8"))
    except Exception:
        prev = {}
    if not worth_fetching(now, prev, last):
        due, why = False, "no game near kickoff in the committed snapshot"
    else:
        cur = scoreboard.refresh()
        if cur is None:
            due, why = False, "every league failed to read; nothing to build from"
        else:
            due, why = decide(now, cur, prev, last)
    print(f"cadence: {'DUE' if due else 'not due'}, {why} "
          f"(last build {last.strftime('%Y-%m-%dT%H:%MZ') if last else 'unknown'})")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"due={'true' if due else 'false'}\n")
    return 0


# ---- the canary's cases ------------------------------------------------------------------

def _g(i, state, kick, status=""):
    return {"id": i, "state": state, "start_utc": kick, "status_short": status}


def _sb(*gs):
    return {"leagues": [{"league": "CFB", "games": list(gs)}]}


def canary():
    """Fixture cases for decide(); returns failure strings."""
    t = lambda s: _utc(s)
    fails = []
    sat = "2026-11-14T"      # Saturday, EST (UTC-5)
    on = _sb(_g(1, "in", sat + "17:00Z"))
    pre = _sb(_g(1, "pre", sat + "17:00Z"))
    cases = [
        ("Saturday, a game on, 31 min since the build", t(sat + "19:41Z"), on, on, t(sat + "19:10Z"), True),
        ("Saturday, a game on, 15 min since the build", t(sat + "19:25Z"), on, on, t(sat + "19:10Z"), False),
        ("Saturday, first kickoff after the morning build", t(sat + "17:05Z"), pre, pre, t(sat + "11:05Z"), True),
        ("Saturday, the last final", t(sat + "21:00Z"), _sb(_g(1, "post", sat + "17:00Z")), on,
         t(sat + "20:50Z"), True),
        ("Saturday, quiet, nothing on", t(sat + "16:00Z"), pre, pre, t(sat + "11:05Z"), False),
        ("Sunday 12:30 AM ET is Saturday's slate", t("2026-11-15T05:30Z"), on, on, t("2026-11-15T04:55Z"), True),
        ("the morning build", t(sat + "11:07Z"), pre, pre, t("2026-11-14T02:00Z"), True),
        ("Thursday kickoff", t("2026-11-13T01:20Z"), _sb(_g(2, "in", "2026-11-13T01:15Z")),
         _sb(_g(2, "pre", "2026-11-13T01:15Z")), t("2026-11-12T23:00Z"), True),
        ("Thursday halftime", t("2026-11-13T02:50Z"), _sb(_g(2, "in", "2026-11-13T01:15Z", "Halftime")),
         _sb(_g(2, "in", "2026-11-13T01:15Z", "Q2 3:10")), t("2026-11-13T01:20Z"), True),
        ("Thursday third quarter, no milestone", t("2026-11-13T03:20Z"),
         _sb(_g(2, "in", "2026-11-13T01:15Z", "Q3 9:10")), _sb(_g(2, "in", "2026-11-13T01:15Z", "Halftime")),
         t("2026-11-13T02:50Z"), False),
        ("Tuesday, a final with a game still on", t("2026-11-11T02:00Z"),
         _sb(_g(3, "post", "2026-11-10T23:00Z"), _g(4, "in", "2026-11-11T00:30Z")),
         _sb(_g(3, "in", "2026-11-10T23:00Z"), _g(4, "in", "2026-11-11T00:30Z")), t("2026-11-10T11:05Z"), False),
        ("Tuesday, after the last game", t("2026-11-11T03:30Z"),
         _sb(_g(3, "post", "2026-11-10T23:00Z"), _g(4, "post", "2026-11-11T00:30Z")),
         _sb(_g(3, "in", "2026-11-10T23:00Z"), _g(4, "in", "2026-11-11T00:30Z")), t("2026-11-10T11:05Z"), True),
        ("no two builds inside 8 minutes", t(sat + "19:45Z"), on, on, t(sat + "19:40Z"), False),
    ]
    for name, now, cur, prev, last, want in cases:
        got, why = decide(now, cur, prev, last)
        if got != want:
            fails.append(f"cadence: {name}: due={got} ({why}), expected due={want}")
    if worth_fetching(t("2026-11-11T16:00Z"), _sb(_g(5, "pre", "2026-11-14T17:00Z")), t("2026-11-11T11:05Z")):
        fails.append("cadence: a quiet Wednesday tick fetches the feed with no game near kickoff")
    return fails


if __name__ == "__main__":
    if "--tick" in sys.argv:
        sys.exit(tick(sys.argv[1:]))
    fs = canary()
    for f in fs:
        print("::error::" + f)
    print("CADENCE CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
