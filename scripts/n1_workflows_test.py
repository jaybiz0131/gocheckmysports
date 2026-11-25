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
    guarded(fails, "scores-cadence.yml: the hand-over names itself (by=handover), so the run it starts does not step aside for the one ending",
            lambda: re.search(r"gh workflow run scores-cadence\.yml --ref main -f by=handover", sc))
    guarded(fails, "scores-cadence.yml: a run started while another holds the window steps aside in its first step; no concurrency group queues it",
            lambda: "python3 cadence.py --aside" in sc and sc.count("steps.aside.outputs.aside != 'true'") >= 2
            and not re.search(r"(?m)^concurrency:", sc) and re.search(r"(?m)^      by:\s*$", sc))
    for name in ("inactives.yml", "sports-news-brief.yml"):
        w = read(name)
        job = w.split("\n  scores-start:\n", 1)[1] if "\n  scores-start:\n" in w else ""
        guarded(fails, f"{name}: the Worker-dispatched run starts the scores run when none is running (its own job, actions: write, warns, never fails)",
                lambda job=job: job and re.search(r"actions:\s*write", job) and "GH_TOKEN: ${{ github.token }}" in job
                and re.search(r"python3 cadence\.py --start \|\| echo \"::warning::", job) and "NEWSROOM_JOBS" not in job
                and "secrets." not in job and "git push" not in job)
    guarded(fails, "scores-cadence.yml: a tick that raises warns and commits nothing; it never fails the run",
            lambda: re.search(r"python3 cadence\.py --tick[^\n]*\\\n\s*\|\| echo \"::warning::", sc))
    # S-DONE point 8: a run fails only when the desk did not do its job. Two paths failed it for less.
    vf = read("verify-sports-pipeline.yml")
    guarded(fails, "verify: a dead source feed (exit 3) opens its issue and warns; only another status fails the job",
            lambda: 'rc=$?' in vf and '[ "$rc" -eq 3 ]' in vf and "::warning::" in vf.split("Check RSS feeds resolve")[1]
            and "steps.feeds.outputs.broken == 'true'" in vf and "if: failure()" not in vf.split("Check RSS feeds resolve")[1]
            and 'exit "$rc"' in vf)
    br = read("sports-news-brief.yml")
    gap = br.split("Edition gap")[-2] + br.split("Edition gap")[-1] if "Edition gap" in br else ""
    guarded(fails, "the brief: an Edition gap is a warning beside its issue, never a failed run (N-1 class A, as on Crypto)",
            lambda: "core.warning(\"Edition gap over threshold" in br and "core.setFailed(\"Edition gap" not in br)
    # S-DONE: a one-line `run:` that holds ": " or " #" is not the command it looks like: YAML reads a
    # mapping or a comment, the file does not parse, and GitHub fails the run before it starts.
    import glob as _glob
    bad = []
    for path in sorted(_glob.glob(os.path.join(WF, "*.yml"))):
        for i, ln in enumerate(open(path, encoding="utf-8").read().split("\n"), 1):
            m = re.match(r"\s+(?:- )?run: (?![|>])(.*)$", ln)
            if m and not m.group(1).startswith(("'", '"')) and (": " in m.group(1) or " #" in m.group(1)):
                bad.append(f"{os.path.basename(path)}:{i}")
    guarded(fails, "every workflow: a one-line run: holds no ': ' or ' #' outside a block (YAML would not parse it)"
            + (f" [{', '.join(bad[:4])}]" if bad else ""), lambda: not bad)
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
