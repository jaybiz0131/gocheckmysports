#!/usr/bin/env python3
"""poller_alarm.py: a failing Inactives poller fails ONCE and says why.

WHY THIS EXISTS. The poller is dispatched every five minutes through a slate. From
2026-10-09, when the pipeline canary it ran a copy of went red, every tick that saw a new
inactive failed, nothing was pushed, so the next tick saw the same inactives as new and
failed again: 12 failed runs an hour, one failure email each, all for one cause. A failure
repeated every five minutes is read as noise, which is how a real one gets missed.

THE RULE. The first red tick of an episode fails the run and opens one issue that carries
the reason. Every later red tick in the same episode stays green and points at that issue.
The first green tick closes it. One cause, one failed run, one issue, however many ticks
it spans.

  python3 poller_alarm.py --outcome failure --log gate.log   (uses `gh`, needs GH_TOKEN)
  python3 poller_alarm.py --outcome success

Exit status: 1 only for the first failure of an episode, else 0.
"""
import argparse
import json
import os
import subprocess
import sys

TITLE = "Inactives poller: push gate red"


def decide(outcome, open_issue):
    """(action, fail_job). Pure, so the canary can prove every row of it.

    action: "open" (first failure), "note" (repeat failure, already said), "close"
    (recovered), "none" (green and nothing open)."""
    if outcome == "success":
        return ("close" if open_issue else "none"), False
    if open_issue:
        return "note", False
    return "open", True


def _gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _open_issue():
    rc, out = _gh("issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title',
                  "--json", "number,title")
    if rc != 0:
        return None
    for i in json.loads(out or "[]"):
        if i.get("title") == TITLE:
            return i["number"]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome", required=True, choices=("success", "failure"))
    ap.add_argument("--log")
    a = ap.parse_args(argv)
    num = _open_issue()
    action, fail = decide(a.outcome, num is not None)
    run = "{}/{}/actions/runs/{}".format(os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
                                         os.environ.get("GITHUB_REPOSITORY", ""),
                                         os.environ.get("GITHUB_RUN_ID", ""))
    if action == "open":
        tail = ""
        if a.log and os.path.exists(a.log):
            tail = "\n".join(open(a.log, encoding="utf-8", errors="replace").read()
                             .splitlines()[-40:])
        body = ("The Inactives poller's rebuild-and-push step failed, so no snapshot is "
                "being pushed.\n\nThis run failed once to say so. Later ticks stay green and "
                "do not email while this issue is open; the first green tick closes it.\n\n"
                f"First red run: {run}\n\nLast lines of the step:\n\n```\n{tail}\n```\n")
        _gh("issue", "create", "--title", TITLE, "--body", body)
        print(f"::error::{TITLE}: opened an issue with the reason; later ticks will not repeat this")
    elif action == "note":
        print(f"::notice::{TITLE}: still red, issue #{num} already says why; this tick is not "
              f"a new failure")
    elif action == "close":
        _gh("issue", "close", str(num), "--comment", f"The push gate is green again ({run}).")
        print(f"poller_alarm: closed issue #{num}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
