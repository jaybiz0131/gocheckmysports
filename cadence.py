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

WHO STARTS A RUN (S-DONE). GitHub delivers 4 to 6 of the 100 cron ticks a day this workflow asks
for, hours late, and the Worker's tick was not deployed on November 25. So: (1) the runs the
Worker does dispatch on this desk (the inactives poller through its windows, the evening brief's
three fires from 6:40 PM ET) each start the scores run when none is queued or running (--start);
(2) a run started while an older one holds the window ends in its first step (--aside), so the
Worker's ten-minute tick costs seconds and queues nothing; (3) with no Worker tick on record in
WORKER_SEEN_HOURS, a run waits for a kickoff up to BRIDGE_AHEAD_HOURS off, which carries a night
game's run to the next day's first kickoff. The Worker's first tick retires (3).

USAGE  python3 cadence.py --tick [--last-build ISO] [--started ISO]
           decide; writes due=, live=, sleep= and handover= for the workflow's loop
       python3 cadence.py --aside     the scores run's first step: aside=true when an older run holds
       python3 cadence.py --start     another workflow's job: start the scores run when none is running
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
BRIDGE_AHEAD_HOURS = 16       # with no Worker tick on record a run waits this far ahead: a night game to the next day's first kickoff
WORKER_SEEN_HOURS = 4         # the Worker ticks every 10 minutes with gaps of 3 hours at most; older than this, it is not ticking
START_QUIET_MIN = 20          # a run that ended clean this recently found no window; nobody starts another
WORKFLOW = "scores-cadence.yml"


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


def window(now, sb, ahead=HOLD_AHEAD_HOURS):
    """(state, kickoff). 'on' while a board game is in play, is past its kickoff and not read as
    started or final, or is inside NEAR_BEFORE_MIN of its kickoff (each for NEAR_AFTER_HOURS at
    most: a card the feed never closed does not hold a run for ever); 'soon' with the next
    kickoff when it is inside `ahead` hours; else 'off' with the next kickoff, or None."""
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
    if nxt is not None and nxt - now <= datetime.timedelta(hours=ahead):
        return "soon", nxt
    return "off", nxt


def hold(now, sb, started=None, ahead=HOLD_AHEAD_HOURS):
    """What the workflow's loop does after this tick: {'live', 'sleep', 'handover'}. live: re-read
    the board now. sleep: seconds until the next tick, 0 to end the run. handover: the run has
    reached HOLD_MAX_MIN with the window still on or near, so it dispatches the next run.
    `ahead`: how many hours off a kickoff may be and still be waited for (ahead_hours)."""
    now = now.astimezone(UTC)
    state, nxt = window(now, sb, ahead)
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


# ---- who starts a run, and who steps aside (S-DONE) ----------------------------------------
# A run is {"id", "status", "conclusion", "event", "title", "created", "updated"}: one row of
# `gh run list` for this workflow. A run the desk's own jobs dispatch names itself in its title
# ("Game-day scores (start)", "(handover)"); the Worker's tick, like a person's, carries no name.

def steps_aside(me, runs, by=""):
    """True when this run (id `me`) ends at once: an OLDER run of the workflow is queued or in
    progress, so the window is held. The younger of two always yields, so two ticks in one second
    leave one holder. The run a holder dispatched at its limit (by == 'handover') never yields: the
    holder is still closing when it starts. A list that could not be read (None) yields nothing."""
    if by == "handover" or not runs:
        return False
    return any(r.get("status") != "completed" and int(r.get("id") or 0) < int(me) for r in runs)


def start_due(now, runs):
    """(bool, why): whether another workflow's run should start the scores run now. Not while one
    is queued or in progress, and not within START_QUIET_MIN of one that ended clean (it read the
    feed and found no window on or near). The scores run decides for itself what the slate holds;
    this only makes sure one is asked. A list that could not be read starts one: a run too many
    ends in seconds, a window with no run goes stale."""
    if runs is None:
        return True, "the runs could not be listed"
    now = now.astimezone(UTC)
    for r in runs:
        if r.get("status") != "completed":
            return False, f"run {r.get('id')} is {r.get('status')}"
    for r in runs:
        ended = _utc(r.get("updated") or r.get("created"))
        if r.get("conclusion") == "success" and ended and now - ended < datetime.timedelta(minutes=START_QUIET_MIN):
            return False, f"run {r.get('id')} ended {int((now - ended).total_seconds() // 60)} minutes ago and found no window"
    return True, "no run is queued or in progress, and none ended clean in the last %d minutes" % START_QUIET_MIN


def worker_live(now, runs):
    """True when the Worker's own tick is on record inside WORKER_SEEN_HOURS: a workflow_dispatch
    run whose title carries no name of the desk's own (a hand dispatch reads the same, and for
    those hours it is treated the same)."""
    now = now.astimezone(UTC)
    for r in runs or []:
        made = _utc(r.get("created"))
        if (r.get("event") == "workflow_dispatch" and "(" not in (r.get("title") or "") and made
                and now - made <= datetime.timedelta(hours=WORKER_SEEN_HOURS)):
            return True
    return False


def ahead_hours(now, runs):
    """How far ahead a kickoff may be and still hold a run. With the Worker ticking every ten
    minutes a run only has to be there shortly before the kickoff: HOLD_AHEAD_HOURS. Without it
    nothing reliable starts a run before a weekday afternoon game, so the night's run waits for
    the next day's first kickoff: BRIDGE_AHEAD_HOURS. Retires itself on the Worker's first tick."""
    return HOLD_AHEAD_HOURS if worker_live(now, runs) else BRIDGE_AHEAD_HOURS


def _runs():
    """This workflow's latest runs from the GitHub CLI, or None when they cannot be read."""
    try:
        r = subprocess.run(["gh", "run", "list", "--workflow", WORKFLOW, "--limit", "40", "--json",
                            "databaseId,status,conclusion,event,displayTitle,createdAt,updatedAt"],
                           cwd=HERE, capture_output=True, text=True, timeout=45)
        if r.returncode != 0:
            print(f"::warning::scores: the runs could not be listed ({r.stderr.strip()[:160]})")
            return None
        return [{"id": x.get("databaseId"), "status": x.get("status"), "conclusion": x.get("conclusion") or "",
                 "event": x.get("event"), "title": x.get("displayTitle") or "", "created": x.get("createdAt"),
                 "updated": x.get("updatedAt")} for x in json.loads(r.stdout or "[]")]
    except Exception as e:                                    # noqa: BLE001
        print(f"::warning::scores: the runs could not be listed ({type(e).__name__}: {str(e)[:120]})")
        return None


def aside(argv=()):
    """--aside: the scores run's first step. Writes aside=true when an older run holds the window."""
    me = os.environ.get("GITHUB_RUN_ID") or "0"
    by = (os.environ.get("BY") or "").strip()
    yes = steps_aside(me, _runs(), by)
    print("cadence: " + ("an older run holds the window; this one ends here" if yes
                         else "no older run holds the window" + (f" (started by: {by})" if by else "")))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"aside={'true' if yes else 'false'}\n")
    return 0


def start(argv=()):
    """--start: run by the desk's Worker-dispatched jobs (the inactives poller, the evening brief).
    Starts the scores run when start_due says so. Never fails the job it runs in."""
    due, why = start_due(datetime.datetime.now(UTC), _runs())
    if not due:
        print(f"cadence: the scores run is not started: {why}")
        return 0
    r = subprocess.run(["gh", "workflow", "run", WORKFLOW, "--ref", "main", "-f", "by=start"],
                       cwd=HERE, capture_output=True, text=True, timeout=45)
    if r.returncode != 0:
        print(f"::warning::scores: the start dispatch failed ({r.stderr.strip()[:160]}); the next tick asks again")
    else:
        print(f"cadence: the scores run is started ({why})")
    return 0


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
    ahead = ahead_hours(now, _runs())
    if cur is None:
        due, why = False, "every league failed to read; nothing to build from"
        plan = hold(now, prev, started, ahead)
        plan["live"] = False
    else:
        due, why = decide(now, cur, prev, last)
        plan = hold(now, cur, started, ahead)
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
          f"window {window(now, cur or prev, ahead)[0]} looking {ahead} hours ahead, next tick in {plan['sleep']} s"
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
    # S-DONE: who starts the run, and who steps aside. GitHub delivers 4 to 6 of this workflow's 100
    # cron ticks a day, so the desk's own Worker-dispatched runs start it, a run started while another
    # holds the window ends at once, and with no Worker tick on record a run bridges the night to the
    # next day's first kickoff.
    R = lambda i, status="completed", concl="success", event="schedule", title="Game-day scores", created="2026-11-25T23:00Z", updated=None: {
        "id": i, "status": status, "conclusion": concl if status == "completed" else "", "event": event, "title": title,
        "created": created, "updated": updated or created}
    acases = [
        ("an older run in progress holds the window", 101, [R(100, "in_progress")], "", True),
        ("an older run still queued will hold it", 101, [R(100, "queued")], "", True),
        ("a younger run is the one that steps aside", 101, [R(102, "in_progress")], "", False),
        ("every other run is finished", 101, [R(100), R(99, concl="failure")], "", False),
        ("the run a holder handed over to never steps aside", 101, [R(100, "in_progress")], "handover", False),
        ("the list of runs could not be read", 101, None, "", False),
        ("the run itself in the list", 101, [R(101, "in_progress")], "", False),
    ]
    for name, me, runs, by, want in acases:
        try:
            got = steps_aside(me, runs, by)
        except Exception as e:                                # noqa: BLE001
            got = f"{type(e).__name__}: {e}"
        if got != want:
            fails.append(f"cadence aside: {name}: {got}, expected {want}")
    n = t("2026-11-25T23:40Z")
    scases = [
        ("no run on record", [], True),
        ("a run holds the window", [R(100, "in_progress", created="2026-11-25T20:00Z")], False),
        ("a run is queued", [R(100, "queued")], False),
        ("a run ended ten minutes ago and found no window", [R(100, created="2026-11-25T23:30Z")], False),
        ("the last run ended fifty minutes ago", [R(100, created="2026-11-25T22:50Z")], True),
        ("the last run failed ten minutes ago", [R(100, concl="failure", created="2026-11-25T23:30Z")], True),
        ("the last run was cancelled five minutes ago", [R(100, concl="cancelled", created="2026-11-25T23:35Z")], True),
        ("the list of runs could not be read", None, True),
    ]
    for name, runs, want in scases:
        try:
            got = start_due(n, runs)[0]
        except Exception as e:                                # noqa: BLE001
            got = f"{type(e).__name__}: {e}"
        if got != want:
            fails.append(f"cadence start: {name}: {got}, expected {want}")
    lcases = [
        ("a Worker tick an hour ago", [R(100, event="workflow_dispatch", created="2026-11-25T22:35Z")], HOLD_AHEAD_HOURS),
        ("only GitHub's own cron on record", [R(100, created="2026-11-25T22:35Z")], BRIDGE_AHEAD_HOURS),
        ("only the desk's own start and hand-over on record",
         [R(100, event="workflow_dispatch", title="Game-day scores (start)", created="2026-11-25T22:35Z"),
          R(99, event="workflow_dispatch", title="Game-day scores (handover)", created="2026-11-25T21:35Z")], BRIDGE_AHEAD_HOURS),
        ("the last Worker tick was five hours ago", [R(100, event="workflow_dispatch", created="2026-11-25T18:35Z")], BRIDGE_AHEAD_HOURS),
        ("the list of runs could not be read", None, BRIDGE_AHEAD_HOURS),
    ]
    for name, runs, want in lcases:
        try:
            got = ahead_hours(n, runs)
        except Exception as e:                                # noqa: BLE001
            got = f"{type(e).__name__}: {e}"
        if got != want:
            fails.append(f"cadence ahead: {name}: {got}, expected {want}")
    # Thanksgiving 2026: the Wednesday night game is final at 04:20Z, the first Thursday kickoff is 17:30Z
    thu = _sb(_g(7, "post", "2026-11-26T01:00Z"), _g(8, "pre", "2026-11-26T17:30Z"))
    try:
        h6 = hold(t("2026-11-26T04:20Z"), thu, t("2026-11-25T23:40Z"))
        h16 = hold(t("2026-11-26T04:20Z"), thu, t("2026-11-25T23:40Z"), BRIDGE_AHEAD_HOURS)
        hov = hold(t("2026-11-26T04:50Z"), thu, t("2026-11-25T23:40Z"), BRIDGE_AHEAD_HOURS)
        far = hold(t("2026-11-26T04:20Z"), _sb(_g(8, "pre", "2026-11-26T21:30Z")), t("2026-11-25T23:40Z"), BRIDGE_AHEAD_HOURS)
    except Exception as e:                                    # noqa: BLE001
        h6 = h16 = hov = far = f"{type(e).__name__}: {e}"
    if h6 != {"live": False, "sleep": 0, "handover": False}:
        fails.append(f"cadence bridge: with the Worker's tick on record the night's run ends at the last final, got {h6}")
    if h16 != {"live": False, "sleep": HOLD_WAKE_MIN * 60, "handover": False}:
        fails.append(f"cadence bridge: with no Worker tick the night's run waits for a kickoff 13 hours off, got {h16}")
    if hov != {"live": False, "sleep": 0, "handover": True}:
        fails.append(f"cadence bridge: a waiting run at its limit hands over, got {hov}")
    if far != {"live": False, "sleep": 0, "handover": False}:
        fails.append(f"cadence bridge: a kickoff more than {BRIDGE_AHEAD_HOURS} hours off ends the run, got {far}")
    import inspect
    src = inspect.getsource(tick)
    if "worth_fetching(" in src or "scoreboard.refresh()" not in src:
        fails.append("cadence tick: a tick must read the feed every time; the committed snapshot is the last build's "
                     "and held no Tuesday game on November 24")
    return fails


if __name__ == "__main__":
    if "--tick" in sys.argv:
        sys.exit(tick(sys.argv[1:]))
    if "--aside" in sys.argv:
        sys.exit(aside(sys.argv[1:]))
    if "--start" in sys.argv:
        sys.exit(start(sys.argv[1:]))
    fs = canary()
    for f in fs:
        print("::error::" + f)
    print("CADENCE CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
