#!/usr/bin/env python3
"""ops_ledger.py: the desk's build ledger (owner ruling 2026-08-17, audit fixes 5b/5d).

Append mode (default, run from CI at the end of every brief execution): posts one
JSON-line comment on this month's "Ops ledger YYYY-MM (auto)" issue. Each row records
what triggered the execution and whether it ended in a content push, a build-hook ping,
or neither, so "how many paid builds, and why" is a lookup instead of a log dig. Rows
written from watcher-embedded executions carry the watcher's workflow name, which is
how those runs become countable at all. Fail-soft: any error prints and exits 0.

Tally mode (--tally YYYY-MM, run from anywhere): reads the month's ledger back through
the public API (no token needed) and prints the bucket counts.

Fields per row: t (UTC), wf (workflow name; the watcher's name marks an embedded run),
ev (trigger event), breaking, cron (which schedule fired, empty for embedded/manual),
guard (retry stood down before spending anything; sports/news only), pushed (content
build), pinged (hook build), run (Actions run id).
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.request

API = "https://api.github.com"


def call(url, token=None, data=None):
    hdrs = {"User-Agent": "ops-ledger", "Accept": "application/vnd.github+json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, headers=hdrs,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def month_issue_number(repo, token, month):
    title = f"Ops ledger {month} (auto)"
    for issue in call(f"{API}/repos/{repo}/issues?state=open&labels=ops-ledger&per_page=100", token):
        if issue["title"] == title:
            return issue["number"]
    body = (
        "Machine-written build ledger: one comment per brief execution.\n\n"
        "Fields: t (UTC), wf (workflow that ran it; the watcher's name marks an "
        "embedded breaking run), ev (trigger), breaking, cron, guard (retry stood "
        "down), pushed (content build), pinged (hook build), run (Actions run id).\n\n"
        f"Tally the month: `python3 scripts/ops_ledger.py --tally {month}`\n\n"
        "Mute this issue; it is a ledger, not a conversation.")
    made = call(f"{API}/repos/{repo}/issues", token,
                {"title": title, "body": body, "labels": ["ops-ledger"]})
    return made["number"]


def append():
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    now = datetime.datetime.now(datetime.timezone.utc)
    row = {
        "t": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wf": os.environ.get("WF", ""),
        "ev": os.environ.get("EV", ""),
        "breaking": os.environ.get("BREAKING") == "1",
        "cron": os.environ.get("CRON", ""),
        "guard": os.environ.get("SERVE", ""),
        "pushed": os.environ.get("PUSHED") == "true",
        "pinged": os.environ.get("PINGED") == "true",
        "run": os.environ.get("RUN_ID", ""),
    }
    # the edition's outcome for the slot (family audit 2026-09-02): synthesis, a
    # sentence-repaired synthesis, the digest floor, skip, abstain, or failed, so the
    # ledger answers "how often does the synthesis actually clear" as a lookup
    try:
        _ws = json.load(open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "out", "wrap-status.json"), encoding="utf-8"))
        row["wrap"] = _ws.get("mode", "")
        if _ws.get("repairs"):
            row["wrap_repairs"] = len(_ws["repairs"])
    except Exception:
        pass
    number = month_issue_number(repo, token, now.strftime("%Y-%m"))
    call(f"{API}/repos/{repo}/issues/{number}/comments", token, {"body": json.dumps(row)})
    print(f"ops ledger: appended to issue #{number}: {json.dumps(row)}")


def infer_repo():
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    url = subprocess.run(["git", "config", "--get", "remote.origin.url"],
                         capture_output=True, text=True).stdout.strip()
    tail = url.split("github.com")[-1].lstrip(":/")
    return tail.removesuffix(".git")


def tally(month):
    repo = infer_repo()
    title = f"Ops ledger {month} (auto)"
    issues = call(f"{API}/repos/{repo}/issues?state=all&labels=ops-ledger&per_page=100")
    match = next((i for i in issues if i["title"] == title), None)
    if not match:
        print(f"no ledger issue titled '{title}' in {repo}")
        return 1
    rows, page = [], 1
    while True:
        batch = call(f"{API}/repos/{repo}/issues/{match['number']}/comments"
                     f"?per_page=100&page={page}")
        if not batch:
            break
        for c in batch:
            try:
                rows.append(json.loads(c["body"]))
            except ValueError:
                pass
        page += 1
    pushed = sum(1 for r in rows if r.get("pushed"))
    pinged = sum(1 for r in rows if r.get("pinged"))
    stood_down = sum(1 for r in rows if r.get("guard") == "false")
    embedded = sum(1 for r in rows if r.get("ev") not in ("schedule", "workflow_dispatch"))
    breaking = sum(1 for r in rows if r.get("breaking"))
    print(f"{repo} ops ledger {month}: {len(rows)} brief executions")
    print(f"  builds from content pushes: {pushed}")
    print(f"  builds from hook pings:     {pinged}")
    print(f"  retry stand-downs (no build, no model spend): {stood_down}")
    print(f"  watcher-embedded executions: {embedded} (breaking flag on {breaking})")
    print(f"  executions with no build:   {len(rows) - pushed - pinged}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--tally":
        sys.exit(tally(sys.argv[2]))
    try:
        append()
    except Exception as exc:  # observability must never fail the run
        print(f"::warning::ops ledger append failed ({exc}); run unaffected")
        sys.exit(0)
