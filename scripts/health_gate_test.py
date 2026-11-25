#!/usr/bin/env python3
"""N-1: the health gate's rules on fixed inputs (no network, no token, no model call).

The Sports case is Saturday November 21, 2026: fixtures/n1/scores-2026-11-21.json holds the four scores snapshots committed
that day (924922b 05:48Z, d88cc93 17:23Z, d852ed8 20:43Z, ee7cf59 00:42Z Nov 22), trimmed to the fields the gate reads,
every value the commit's own. College games ran from 17:00Z. The gate at 7 AM ET on November 22 would have sent one mail
naming three gaps: 17:23 to 20:43, 20:43 to 00:42, and 00:42 to the check, since no reading followed 00:42 while
the late college games were on (as read at 01:25 UTC November 22, when this fixture was made).

  python3 scripts/health_gate_test.py      # exit 1 on any failure
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "scripts"))
UTC = dt.timezone.utc


def guarded(fails, msg, fn):
    try:
        ok = bool(fn())
    except Exception as e:                                   # noqa: BLE001
        ok, msg = False, f"{msg} [{type(e).__name__}: {str(e)[:120]}]"
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


def unit():
    fails = []
    print("N-1 health gate (Sports)")
    import health_gate as hg
    u = hg.utc
    fx = json.load(open(os.path.join(HERE, "fixtures", "n1", "scores-2026-11-21.json"), encoding="utf-8"))
    snaps = [(u(s["fetched_at"]), s) for s in fx["snapshots"]]
    now = u("2026-11-22T12:03:00Z")
    got = hg.scores_findings(now, snaps)
    guarded(fails, "Nov 21: three findings, 12:23 PM to 3:43 PM ET, 3:43 PM to 7:42 PM ET, and 7:42 PM ET to the check",
            lambda: len(got) == 3 and "Nov 21, 12:23 PM ET until Nov 21, 3:43 PM ET" in got[0]
            and "Nov 21, 3:43 PM ET until Nov 21, 7:42 PM ET" in got[1] and "Nov 21, 7:42 PM ET until this check" in got[2])
    guarded(fails, "the overnight gap from 05:48 to 17:23 is no finding: no game had kicked off by 07:48",
            lambda: not any("12:48 AM ET" in f for f in got))
    grid = [u("2026-11-21T17:00:00Z") + dt.timedelta(minutes=30 * i) for i in range(39)]
    filled = [(t, max((x for x in snaps if x[0] <= t), key=lambda x: x[0])[1]) for t in grid] + snaps
    guarded(fails, "the same day read every 30 minutes through 12:00 UTC is no finding", lambda: not hg.scores_findings(now, filled))
    # S-DONE: a re-read (site/data/live/scoreboard.json) is a reading. The build snapshots of Nov 21 alone are
    # three findings; with a re-read every five minutes from the first kickoff they are none.
    guarded(fails, "the gate reads the build snapshots and the re-reads",
            lambda: hg.SCORES_PATHS == ("site/data/scoreboard.json", "site/data/live/scoreboard.json"))
    fives = [u("2026-11-21T17:00:00Z") + dt.timedelta(minutes=5 * i) for i in range(229)]
    reread = [(t, max((x for x in snaps if x[0] <= t), key=lambda x: x[0])[1]) for t in fives] + snaps
    guarded(fails, "the same day with a re-read every five minutes through 12:00 UTC is no finding",
            lambda: not hg.scores_findings(now, reread))
    built = u("2026-11-22T11:01:00Z")
    guarded(fails, "a site built at 6:01 AM ET is no finding; one not built for 25 hours is",
            lambda: not hg.site_finding(now, built) and hg.site_finding(now, now - dt.timedelta(hours=25)))
    guarded(fails, "a final is never 'on'; a game 5 hours past kickoff with no final is no longer 'on'",
            lambda: not hg.on_at({"start_utc": "2026-11-21T17:00Z", "state": "post"}, u("2026-11-21T18:00:00Z"))
            and hg.on_at({"start_utc": "2026-11-21T17:00Z", "state": "in"}, u("2026-11-21T18:00:00Z"))
            and not hg.on_at({"start_utc": "2026-11-21T17:00Z", "state": "in"}, u("2026-11-21T22:00:00Z")))
    guarded(fails, "one gate a day: 6:03 AM ET stands down, 7:03 runs, a second 7 AM run stands down, a dispatch runs",
            lambda: not hg.should_run(u("2026-11-22T11:03:00Z"), "schedule", 0)[0]
            and hg.should_run(u("2026-11-22T12:03:00Z"), "schedule", 0)[0]
            and not hg.should_run(u("2026-11-22T13:20:00Z"), "schedule", 1)[0]
            and hg.should_run(u("2026-11-22T03:00:00Z"), "workflow_dispatch", 3)[0])
    # S-DONE, a fault found while reading the rule: in Eastern STANDARD time the 11:03 UTC cron is 6:03 AM ET. It
    # stands down as too early, and was then counted as "today's gate" by the 12:03 one, which stood down as
    # well: on a day GitHub delivered both on time there was no gate at all. Only a run created at or after
    # 7 AM ET is the day's gate.
    guarded(fails, "the 6:03 AM ET run that stood down is not today's gate: the 7:03 one still runs",
            lambda: hg.gates_today(u("2026-11-26T12:03:20Z"), [
                {"id": 1, "event": "schedule", "status": "completed", "display_title": "Health gate (7 AM Eastern)", "created_at": "2026-11-26T11:03:10Z"},
                {"id": 2, "event": "schedule", "status": "in_progress", "display_title": "Health gate (7 AM Eastern)", "created_at": "2026-11-26T12:03:05Z"}], 2) == 0)
    # S-DONE: GitHub delivered neither health cron on November 25 by 2:30 PM ET, and the 24th's ran at 4:05 PM.
    # The desk's Worker-dispatched runs start the day's gate when no gate has run since 7 AM ET.
    R = lambda created, event="schedule", status="completed", title="Health gate (7 AM Eastern)", i=1: {
        "id": i, "event": event, "status": status, "display_title": title, "created_at": created}
    eve = u("2026-11-25T23:40:00Z")                      # 6:40 PM ET, the evening brief's fire
    scases = [
        ("6:40 PM ET and no gate today", eve, [R("2026-11-24T21:05:48Z"), R("2026-11-24T22:07:04Z")], True),
        ("before 7 AM ET", u("2026-11-25T11:50:00Z"), [], False),
        ("GitHub's cron ran today", eve, [R("2026-11-25T12:03:10Z")], False),
        ("a gate the desk started is still running", eve,
         [R("2026-11-25T23:10:00Z", "workflow_dispatch", "in_progress", "Health gate (7 AM Eastern) (start)")], False),
        ("only a hand dispatch today", eve, [R("2026-11-25T15:00:00Z", "workflow_dispatch")], True),
        ("the runs could not be read", eve, None, False),
    ]
    for name, now2, runs, want in scases:
        guarded(fails, f"start: {name}: {'starts' if want else 'does not start'} the gate",
                lambda now2=now2, runs=runs, want=want: hg.start_due(now2, runs)[0] is want)
    guarded(fails, "a gate the desk started keeps the day's rule: it runs when none ran, stands down when one did; a hand dispatch always runs",
            lambda: hg.should_run(eve, "workflow_dispatch", 0, "start")[0]
            and not hg.should_run(eve, "workflow_dispatch", 1, "start")[0]
            and not hg.should_run(u("2026-11-25T11:50:00Z"), "workflow_dispatch", 0, "start")[0]
            and hg.should_run(eve, "workflow_dispatch", 1, "")[0])
    guarded(fails, "today's gates: the cron's and the desk's own count, a hand dispatch and this run do not",
            lambda: hg.gates_today(eve, [R("2026-11-25T12:03:10Z", i=1),
                                         R("2026-11-25T23:10:00Z", "workflow_dispatch", "completed", "Health gate (7 AM Eastern) (start)", 2),
                                         R("2026-11-25T15:00:00Z", "workflow_dispatch", i=3),
                                         R("2026-11-25T23:39:00Z", i=4), R("2026-11-24T22:07:04Z", i=5)], 4) == 2)
    return fails


def main():
    fails = unit()
    print(f"\nN-1 health gate: {'PASS' if not fails else 'FAIL'} ({len(fails)} failure(s))")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
