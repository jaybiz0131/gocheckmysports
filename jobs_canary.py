#!/usr/bin/env python3
"""jobs_canary.py: Sprint S-1 item 3, the desk's jobs (12 October 2026).

The recap, storyline, lane and Edition job is off; the inactives poll, the designations, the
scores refresh and the counts stay. The conditions report job (S-2b item 3) runs Thursday,
Saturday and Sunday, calls no model and publishes only through its gate.

  brief-off     sports-news-brief.yml has no schedule: key and its job is gated on NEWSROOM_JOBS
  kept          the inactives poller still has its crons
  report        the conditions report job runs Thursday morning, Saturday evening and Sunday
                morning before the freeze, runs conditions_report.py --publish and then the build,
                reads no secret, and the script imports no model client
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
EXPECTED = {"conditions-report.yml": 9, "inactives.yml": 5, "janitor.yml": 1,
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
    cc = sorted(_crons(cr))
    # each slot has the primary and two catch-ups: GitHub delivered no run at all for the 14 Oct
    # primary (15 Oct 7:17 AM EDT), and conditions_report.py publishes a slot once, so a repeat is free
    want = sorted(["17 11 * * 4", "47 12 * * 4", "17 14 * * 4",
                   "17 21 * * 6", "47 22 * * 6", "47 23 * * 6",
                   "17 10 * * 0", "17 11 * * 0", "17 12 * * 0"])
    if cc != want:
        fails.append(f"jobs: the conditions report crons are {cc}, expected {want} "
                     "(Thu 7:17 AM, Sat 5:17 PM, Sun 6:17 AM EDT, each with two catch-ups)")
    for c in cc:
        m = re.fullmatch(r"(\d+) (\d+) \* \* 0", c)
        if m and int(m.group(2)) >= 15:
            fails.append(f"jobs: the Sunday report cron {c} lands too close to the 12:30 PM ET freeze "
                         "for a scheduler that runs up to four hours late")
    if "python3 conditions_report.py --publish" not in cr:
        fails.append("jobs: the conditions report workflow does not run conditions_report.py --publish")
    if cr.find("python3 site_build.py") < cr.find("conditions_report.py --publish") or "git push" not in cr \
            or cr.find("git push") < cr.find("python3 site_build.py"):
        fails.append("jobs: the conditions report is pushed without the build as its gate")
    if re.search(r"secrets\.", cr):
        fails.append("jobs: the conditions report job reads a secret")
    if "git add site/reports/conditions" not in cr or "git add -A" in cr:
        fails.append("jobs: the conditions report job stages more than its report")
    src = open(os.path.join(HERE, "conditions_report.py"), encoding="utf-8").read()
    for bad in ("llm", "anthropic", "publicist", "openai"):
        if re.search(r"^\s*(import|from)\s+" + bad + r"\b", src, re.M):
            fails.append(f"jobs: conditions_report.py imports {bad}")
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "conditions_report.py")],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            fails.append(f"jobs: conditions_report.py with no arguments exited {r.returncode}")
    except Exception as e:
        fails.append(f"jobs: conditions_report.py did not run: {type(e).__name__}: {e}")
    return fails


if __name__ == "__main__":
    fs = jobs_canary()
    for f in fs:
        print("::error::" + f)
    print("JOBS CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
