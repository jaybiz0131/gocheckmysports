#!/usr/bin/env python3
"""jobs_canary.py: Sprint S-1 item 3, the desk's jobs (12 October 2026).

The recap, storyline, lane and Edition job is off; the inactives poll, the designations, the
scores refresh and the counts stay; the conditions report job is a stub that prints nothing.

  brief-off     sports-news-brief.yml has no schedule: key and its job is gated on NEWSROOM_JOBS
  kept          the inactives poller still has its crons
  stub          the conditions report job exists, runs Thursday only, runs the stub, and the
                stub prints nothing, exits 0 and imports no model client and no network code
  set           the set of workflows with a schedule is exactly the expected five

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, ".github", "workflows")
# the live cron lines each workflow keeps, exactly: nothing gained, nothing lost
EXPECTED = {"conditions-report.yml": 1, "inactives.yml": 5, "janitor.yml": 1,
            "sports-aging.yml": 1, "verify-sports-pipeline.yml": 1}


def _crons(text):
    """The live cron lines of a workflow: under an uncommented schedule: key."""
    out, in_sched, indent = [], False, 0
    for l in text.split("\n"):
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        ind = len(l) - len(l.lstrip())
        if s == "schedule:":
            in_sched, indent = True, ind
            continue
        if in_sched:
            if ind <= indent:
                in_sched = False
            elif s.startswith("- cron:"):
                out.append(re.match(r'- cron:\s*"([^"]*)"', s).group(1))
    return out


def has_schedule_key(text):
    return any(l.strip() == "schedule:" and not l.lstrip().startswith("#")
               for l in text.split("\n"))


def jobs_canary():
    fails = []
    try:
        files = {f: open(os.path.join(WF, f), encoding="utf-8").read()
                 for f in os.listdir(WF) if f.endswith(".yml")}
    except OSError as e:
        return [f"jobs: cannot read the workflows ({e})"]

    brief = files.get("sports-news-brief.yml", "")
    if has_schedule_key(brief):
        fails.append("jobs: sports-news-brief.yml still has a schedule: key; the recap, storyline, "
                     "lane and Edition job must not be fired by the scheduler")
    if not re.search(r"^  brief:\n    if: \$\{\{ vars\.NEWSROOM_JOBS == 'on' \}\}", brief, re.M):
        fails.append("jobs: the brief job is not gated on NEWSROOM_JOBS, so the Worker's dispatch "
                     "would still run the newsroom")

    got = {f: len(_crons(t)) for f, t in files.items() if _crons(t)}
    if got != EXPECTED:
        fails.append(f"jobs: the cron lines per workflow are {dict(sorted(got.items()))}, "
                     f"expected {dict(sorted(EXPECTED.items()))}")

    cr = files.get("conditions-report.yml", "")
    cc = _crons(cr)
    if len(cc) != 1 or not re.fullmatch(r"\d+ \d+ \* \* 4", cc[0]):
        fails.append(f"jobs: the conditions report cron is {cc}, expected one Thursday-only line")
    if "python3 conditions_report.py" not in cr:
        fails.append("jobs: the conditions report workflow does not run conditions_report.py")
    if re.search(r"contents:\s*write|secrets\.", cr):
        fails.append("jobs: the conditions report stub can push or reads a secret")

    stub = os.path.join(HERE, "conditions_report.py")
    try:
        r = subprocess.run([sys.executable, stub], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            fails.append(f"jobs: the conditions report stub exited {r.returncode}")
        if r.stdout or r.stderr:
            fails.append(f"jobs: the conditions report stub printed {(r.stdout + r.stderr)[:80]!r}")
        src = open(stub, encoding="utf-8").read()
        for bad in ("import llm", "urllib", "requests", "anthropic", "open(", "subprocess"):
            if re.search(r"^\s*(import|from)\s+" + re.escape(bad.split()[-1]) + r"\b", src, re.M) \
                    or (bad in ("open(", "subprocess") and bad in src.split('"""')[2]):
                fails.append(f"jobs: the conditions report stub uses {bad}")
    except Exception as e:
        fails.append(f"jobs: the stub did not run: {type(e).__name__}: {e}")
    return fails


if __name__ == "__main__":
    fs = jobs_canary()
    for f in fs:
        print("::error::" + f)
    print("JOBS CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
