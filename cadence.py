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

THE RE-READ (S-DONE, November 25 2026). A build is a deploy and a deploy costs credits, so the
builds above stay as they are. Between them, while a game window is on, every tick re-reads the
feed, renders the board with the site's own renderer and commits it under site/data/live/ (a
push netlify_ignore.py never builds); the home and the Scores page read that file themselves and
replace their board and stamp in place, as the inactives board has since September 21. A run
that finds a window on, or a kickoff inside HOLD_AHEAD_HOURS, holds it: it ticks every
LIVE_EVERY_MIN minutes itself rather than wait for a scheduler, and hands over to a new run
before GitHub's six-hour limit.

Every tick reads the feed. Until S-DONE a tick fetched only when the COMMITTED snapshot showed a
game near kickoff, and that file is rewritten only when a build is due: on Tuesday November 24
it was Monday night's, held no Tuesday game, and both college games were played with every tick
answering "no game near kickoff in the committed snapshot". Production read them as upcoming at
4:00 AM Wednesday.

Pure apart from tick(), so the canary feeds it fixtures and a fixture clock.

USAGE  python3 cadence.py --tick [--last-build ISO] [--started ISO]
           decide; writes due=, live=, sleep= and handover= for the workflow's loop
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
LIVE_EVERY_MIN = 5            # while a window is on the board is re-read this often (no deploy)
HOLD_AHEAD_HOURS = 6          # a run that finds a kickoff this near waits for it
HOLD_WAKE_MIN = 30            # and re-reads the slate at least this often while it waits
HOLD_MAX_MIN = 320            # a run hands over to the next before GitHub's six-hour limit


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


def _postponed(g):
    return "postpon" in str(g.get("status_short") or "").lower() or "cancel" in str(g.get("status_short") or "").lower()


def window(now, sb):
    """(state, kickoff). 'on' while a board game is in play, is past its kickoff and not read as
    started or final, or is inside NEAR_BEFORE_MIN of its kickoff (each for NEAR_AFTER_HOURS at
    most: a card the feed never closed does not hold a run for ever); 'soon' with the next
    kickoff when it is inside HOLD_AHEAD_HOURS; else 'off' with the next kickoff, or None."""
    now = now.astimezone(UTC)
    nxt = None
    on = False
    for g in games(sb).values():
        k = _utc(g.get("start_utc"))
        if not k or g.get("state") == "post" or g.get("completed") or _postponed(g):
            continue
        if k - datetime.timedelta(minutes=NEAR_BEFORE_MIN) <= now <= k + datetime.timedelta(hours=NEAR_AFTER_HOURS):
            on = True
        elif k > now and (nxt is None or k < nxt):
            nxt = k
    if on:
        return "on", None
    if nxt is not None and nxt - now <= datetime.timedelta(hours=HOLD_AHEAD_HOURS):
        return "soon", nxt
    return "off", nxt


def hold(now, sb, started=None):
    """What the workflow's loop does after this tick: {'live', 'sleep', 'handover'}. live: re-read
    the board now. sleep: seconds until the next tick, 0 to end the run. handover: the run has
    reached HOLD_MAX_MIN with the window still on or near, so it dispatches the next run."""
    now = now.astimezone(UTC)
    state, nxt = window(now, sb)
    if state == "on":
        nap = LIVE_EVERY_MIN * 60
    elif state == "soon":
        until = (nxt - datetime.timedelta(minutes=NEAR_BEFORE_MIN) - now).total_seconds()
        nap = int(max(60, min(until, HOLD_WAKE_MIN * 60)))
    else:
        return {"live": False, "sleep": 0, "handover": False}
    spent = (now - started.astimezone(UTC)).total_seconds() if started else 0
    if spent + nap > HOLD_MAX_MIN * 60:
        return {"live": state == "on", "sleep": 0, "handover": True}
    return {"live": state == "on", "sleep": nap, "handover": False}


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
    arg = lambda k: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else ""
    known = [t for t in (_utc(arg("--last-build")), _last_snapshot_commit()) if t]
    last = max(known) if known else None
    started = _utc(arg("--started"))
    now = datetime.datetime.now(UTC)
    try:
        prev = json.load(open(scoreboard.OUT, encoding="utf-8"))
    except Exception:
        prev = {}
    # S-DONE: every tick reads the feed. The committed snapshot is the last BUILD's, and a slate
    # it never held (a Tuesday's college games under Monday night's file) was never fetched.
    cur = scoreboard.refresh()
    if cur is None:
        due, why = False, "every league failed to read; nothing to build from"
        plan = hold(now, prev, started)
        plan["live"] = False
    else:
        due, why = decide(now, cur, prev, last)
        plan = hold(now, cur, started)
    if plan["live"]:
        # the re-read: the board as the site's own renderer draws it, committed under
        # site/data/live/ for the pages to read. A render that fails costs this tick's re-read
        # and nothing else; the built page stands and its stamp says how old it is.
        try:
            import live_board
            print("cadence: " + live_board.write())
        except Exception as e:                               # noqa: BLE001
            plan["live"] = False
            print(f"::warning::scores: the board was not re-read ({type(e).__name__}: {str(e)[:160]})")
    print(f"cadence: {'DUE' if due else 'not due'}, {why} "
          f"(last build {last.strftime('%Y-%m-%dT%H:%MZ') if last else 'unknown'}); "
          f"window {window(now, cur or prev)[0]}, next tick in {plan['sleep']} s"
          + (", handing over" if plan["handover"] else ""))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"due={'true' if due else 'false'}\n")
            f.write(f"live={'true' if plan['live'] else 'false'}\n")
            f.write(f"sleep={plan['sleep']}\n")
            f.write(f"handover={'true' if plan['handover'] else 'false'}\n")
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
    # S-DONE: the window and the hold. Tuesday November 24, 2026: two college games at 7:00 PM ET.
    tue = _sb(_g(7, "pre", "2026-11-25T00:00Z"), _g(8, "pre", "2026-11-25T00:00Z"), _g(9, "pre", "2026-11-27T01:00Z"))
    wcases = [
        ("a game in play", t("2026-11-25T01:30Z"), _sb(_g(7, "in", "2026-11-25T00:00Z")), "on"),
        ("ten minutes before kickoff", t("2026-11-24T23:50Z"), tue, "on"),
        ("past kickoff, the feed still says scheduled", t("2026-11-25T00:20Z"), tue, "on"),
        ("three hours before kickoff", t("2026-11-24T21:00Z"), tue, "soon"),
        ("seven hours before kickoff", t("2026-11-24T16:59Z"), tue, "off"),
        ("every game final", t("2026-11-25T04:00Z"), _sb(_g(7, "post", "2026-11-25T00:00Z")), "off"),
        ("a card the feed never closed, seven hours on", t("2026-11-25T07:01Z"),
         _sb(_g(7, "in", "2026-11-25T00:00Z")), "off"),
        ("a postponed game past its kickoff", t("2026-11-25T00:20Z"),
         _sb(_g(7, "pre", "2026-11-25T00:00Z", "Postponed")), "off"),
    ]
    for name, now, sb, want in wcases:
        got = window(now, sb)[0]
        if got != want:
            fails.append(f"cadence window: {name}: {got}, expected {want}")
    h = hold(t("2026-11-25T01:30Z"), _sb(_g(7, "in", "2026-11-25T00:00Z")), t("2026-11-25T00:00Z"))
    if h != {"live": True, "sleep": LIVE_EVERY_MIN * 60, "handover": False}:
        fails.append(f"cadence hold: a game in play re-reads the board and ticks again in {LIVE_EVERY_MIN} minutes, got {h}")
    h = hold(t("2026-11-24T21:00Z"), tue, t("2026-11-24T21:00Z"))
    if h != {"live": False, "sleep": HOLD_WAKE_MIN * 60, "handover": False}:
        fails.append(f"cadence hold: three hours before kickoff waits {HOLD_WAKE_MIN} minutes without a re-read, got {h}")
    h = hold(t("2026-11-24T23:40Z"), tue, t("2026-11-24T21:00Z"))
    if h != {"live": False, "sleep": 300, "handover": False}:
        fails.append(f"cadence hold: 20 minutes before kickoff sleeps to the window's opening (300 s), got {h}")
    h = hold(t("2026-11-24T16:59Z"), tue, t("2026-11-24T16:59Z"))
    if h != {"live": False, "sleep": 0, "handover": False}:
        fails.append(f"cadence hold: no kickoff inside {HOLD_AHEAD_HOURS} hours ends the run, got {h}")
    h = hold(t("2026-11-25T01:30Z"), _sb(_g(7, "in", "2026-11-25T00:00Z")), t("2026-11-24T20:11Z"))
    if h != {"live": True, "sleep": 0, "handover": True}:
        fails.append(f"cadence hold: at the run's limit with a game on it re-reads once more and hands over, got {h}")
    if LIVE_EVERY_MIN > 10:
        fails.append(f"cadence: the re-read is every {LIVE_EVERY_MIN} minutes; the stamp must stay inside 15")
    # the Tuesday defect itself: the committed snapshot is Monday night's and holds no Tuesday game
    mon = _sb(_g(6, "in", "2026-11-24T01:15Z"))
    if window(t("2026-11-25T01:30Z"), mon)[0] != "off" or window(t("2026-11-25T01:30Z"), tue)[0] != "on":
        fails.append("cadence window: the Tuesday games are read from the feed's slate, not the committed one")
    import inspect
    src = inspect.getsource(tick)
    if "worth_fetching(" in src or "scoreboard.refresh()" not in src:
        fails.append("cadence tick: a tick must read the feed every time; the committed snapshot is the last build's "
                     "and held no Tuesday game on November 24")
    return fails


if __name__ == "__main__":
    if "--tick" in sys.argv:
        sys.exit(tick(sys.argv[1:]))
    fs = canary()
    for f in fs:
        print("::error::" + f)
    print("CADENCE CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
