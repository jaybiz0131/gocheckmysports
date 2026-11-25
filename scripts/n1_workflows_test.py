#!/usr/bin/env python3
"""N-1 (November 21, 2026): a Sports run reaches "failure" only when the desk did not do its job.

  1. One trigger (class D). The Worker dispatches inactives.yml every five minutes in its Eastern windows; its GitHub
     crons are removed (73 extra runs in 30 days, and their pending runs evicted the Worker's: 16 cancelled on Nov 1).
     scores-cadence.yml keeps its crons until the Worker deploy that dispatches it (Jack's) is live: a workflow the
     deployed Worker does not dispatch keeps its cron.
  2. One writer per file (class D). The Nov 15 inactives push conflicted on a rebase over a "scores:" commit: the poller
     committed site/data/scoreboard.json, which is the score cadence's file. It no longer does.
  3. A rejected push rebases and retries; when it still cannot land, the run warns and exits 0, and the next tick
     takes a fresh main. Inactives, scores and conditions alike.
  4. The health gate (Phase 3) exists, runs daily at 7 AM Eastern, reads the scores history, pushes nothing.

Stdlib only.   python3 scripts/n1_workflows_test.py      # exit 1 on any failure
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(HERE, ".github", "workflows")
sys.path.insert(0, HERE)
PUSHERS = ("inactives.yml", "scores-cadence.yml", "conditions-report.yml")


def read(name):
    p = os.path.join(WF, name)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def active_crons(txt):
    return re.findall(r'^\s*-\s*cron:\s*["\']([^"\']+)["\']', txt, re.M)


def guarded(fails, msg, fn):
    try:
        ok = bool(fn())
    except Exception as e:                                   # noqa: BLE001
        ok, msg = False, f"{msg} [{type(e).__name__}: {str(e)[:120]}]"
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


def push_block(txt):
    m = re.search(r"ok=false\n(.*?)\n\s*\[ \"\$ok\" = true \][^\n]*", txt, re.S)
    return m.group(0) if m else ""


def unit():
    fails = []
    print("N-1 workflows (Sports)")
    ina = read("inactives.yml")
    guarded(fails, "inactives.yml: the Worker dispatches it, so no GitHub cron", lambda: ina and not active_crons(ina))
    guarded(fails, "inactives.yml: still takes workflow_dispatch with its reconcile input",
            lambda: "workflow_dispatch:" in ina and "reconcile" in ina)
    guarded(fails, "inactives.yml: the poller never commits site/data/scoreboard.json (the score cadence's file)",
            lambda: re.search(r"git (?:reset -q|restore --staged)[^\n]*site/data/scoreboard\.json", ina))
    for name in PUSHERS:
        b = push_block(read(name))
        guarded(fails, f"{name}: a push that cannot land after its retries warns and exits 0, never 1",
                lambda b=b: b and "exit 1" not in b and "return 1" not in b and "::warning::" in b
                and ("exit 0" in b or "return 0" in b))
    sc = read("scores-cadence.yml")
    guarded(fails, "scores-cadence.yml: keeps its crons until the Worker deploy that dispatches it is live",
            lambda: active_crons(sc))
    # S-DONE: a run holds its window, so the cadence does not rest on a scheduler delivering every tick
    guarded(fails, "scores-cadence.yml: the tick loops on cadence.py's sleep and stages the snapshot and the re-read by name",
            lambda: "while :; do" in sc and "sed -n 's/^sleep=//p'" in sc and "git add site/data/live" in sc
            and "git add site/data/scoreboard.json" in sc and not re.search(r"git add (-A|\.)", sc))
    guarded(fails, "scores-cadence.yml: the job's timeout is past cadence.HOLD_MAX_MIN, so a holding run hands over before GitHub ends it",
            lambda: int(re.search(r"timeout-minutes:\s*(\d+)", sc).group(1)) >= __import__("cadence").HOLD_MAX_MIN + 20
            and int(re.search(r"timeout-minutes:\s*(\d+)", sc).group(1)) <= 360)
    guarded(fails, "scores-cadence.yml: the hand-over dispatches this workflow with the job's own token (actions: write, no secret)",
            lambda: "gh workflow run scores-cadence.yml" in sc and re.search(r"actions:\s*write", sc)
            and "GH_TOKEN: ${{ github.token }}" in sc and "secrets." not in sc)
    guarded(fails, "scores-cadence.yml: a tick that raises warns and commits nothing; it never fails the run",
            lambda: re.search(r"python3 cadence\.py --tick[^\n]*\\\n\s*\|\| echo \"::warning::", sc))
    h = read("health.yml")
    guarded(fails, "health.yml exists and runs scripts/health_gate.py at 7 AM Eastern (11:03 and 12:03 UTC)",
            lambda: h and "scripts/health_gate.py" in h and set(active_crons(h)) == {"3 11 * * *", "3 12 * * *"})
    guarded(fails, "health.yml reads 30 hours of history and pushes nothing",
            lambda: h and "--shallow-since" in h and "git push" not in h and "sports-publish" not in h)
    return fails


def main():
    fails = unit()
    print(f"\nN-1 workflows: {'PASS' if not fails else 'FAIL'} ({len(fails)} failure(s))")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
