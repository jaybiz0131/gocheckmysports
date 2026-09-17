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
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# THE LEDGER STARTED HERE. Runs before this moment were never recorded and their
# containers are gone, so their tokens cannot be recovered. Every tally prints this
# date, so a tally can never silently claim a day it does not hold. Run counts for
# earlier days come from the Actions log; spend comparisons start the day after.
LEDGER_SINCE = "2026-09-16T16:27Z"


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
    # PROGRAM 4, T-4 (2026-09-16): THE SPEND. The Budget object already computes tokens
    # and dollars for every call in the run and run.py already writes them to
    # out/run_report.json; the number was computed on every run and thrown away when
    # the container died. Keeping it is the whole change.
    try:
        _rr = json.load(open(os.path.join(REPO, "out", "run_report.json"),
                             encoding="utf-8"))
        _b = _rr.get("budget") or {}
        row["tokens"] = _b.get("tokens", 0)
        row["usd"] = round(float(_b.get("usd") or 0.0), 4)
        row["cap_usd"] = _b.get("max_usd")
    except Exception:
        # A run that stood down at the guard never built a Budget. That is a real and
        # useful row: a run that cost nothing. It is recorded as zero, not omitted,
        # because "how many runs spent nothing" is half the question T-4 asks.
        row["tokens"] = 0
        row["usd"] = 0.0
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
    write_file_ledger(row)
    number = month_issue_number(repo, token, now.strftime("%Y-%m"))
    call(f"{API}/repos/{repo}/issues/{number}/comments", token, {"body": json.dumps(row)})
    print(f"ops ledger: appended to issue #{number}: {json.dumps(row)}")


def write_file_ledger(row):
    """T-4: the committed ledger.json. The issue comments are a remote view and need a
    token and a network call to read; the file is in the repo, so a week's spend is a
    grep. Appends, never rewrites history, and is idempotent on the Actions run id so a
    re-run of the same job does not double-count.

    Committed with [skip netlify] and covered by the ignore rule (T-3): a ledger row is
    not a site change and must not buy a build."""
    path = os.path.join(REPO, "ledger.json")
    try:
        doc = json.load(open(path, encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
            raise ValueError("ledger.json is not the expected shape")
    except FileNotFoundError:
        doc = {"desk": os.environ.get("GITHUB_REPOSITORY", ""),
               "since": LEDGER_SINCE, "runs": []}
    except Exception as exc:
        print(f"::warning::ledger.json unreadable ({exc}); starting a new one is NOT "
              f"done here, the row goes to the issue only")
        return
    rid = row.get("run")
    if rid and any(r.get("run") == rid for r in doc["runs"]):
        print(f"ops ledger: run {rid} already in ledger.json; not double-counting")
        return
    doc["runs"].append(row)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    _commit_ledger(path, row)


def _commit_ledger(path, row):
    def git(*a):
        return subprocess.run(["git"] + list(a), cwd=REPO, capture_output=True,
                              text=True)
    git("config", "user.name", "Jack Berno")
    git("config", "user.email",
        "297991518+jaybiz0131@users.noreply.github.com")
    git("add", path)
    if not git("diff", "--cached", "--quiet").returncode:
        return                      # nothing staged: identical row
    msg = (f"ledger: {row.get('t','')} {row.get('tokens',0)} tokens "
           f"${row.get('usd',0):.4f} [skip netlify]")
    git("commit", "-m", msg)
    for _ in range(4):
        if git("push").returncode == 0:
            print(f"ops ledger: {os.path.basename(path)} pushed")
            return
        # another job pushed first; take their history and replay this one row
        if git("pull", "--rebase").returncode != 0:
            git("rebase", "--abort")
            break
    print("::warning::ledger.json committed but not pushed; the next run carries it")


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
    _spend_lines(rows)
    return 0


def _spend_lines(rows):
    """T-4's weekly line: runs, tokens and computed spend per ISO week.

    Rows written before T-4 carry no tokens key. They are counted as runs but their
    spend is unknown, and the line says so rather than printing a zero that would read
    as a free run."""
    import collections
    weeks = collections.defaultdict(lambda: {"runs": 0, "tok": 0, "usd": 0.0, "old": 0})
    for r in rows:
        try:
            d = datetime.datetime.strptime(r.get("t", "")[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        y, w, _ = d.isocalendar()
        b = weeks[f"{y}-W{w:02d}"]
        b["runs"] += 1
        if "tokens" in r:
            b["tok"] += r.get("tokens") or 0
            b["usd"] += float(r.get("usd") or 0.0)
        else:
            b["old"] += 1
    if not weeks:
        return
    print("  week        runs    tokens      spend")
    for k in sorted(weeks):
        b = weeks[k]
        note = f"   ({b['old']} row(s) pre-ledger, spend unknown)" if b["old"] else ""
        print(f"  {k}  {b['runs']:5d}  {b['tok']:9,d}  ${b['usd']:8.2f}{note}")


def tally_file(path=None):
    """Read the committed ledger.json instead of the issue. No token, no network."""
    path = path or os.path.join(REPO, "ledger.json")
    try:
        rows = json.load(open(path, encoding="utf-8")).get("runs", [])
    except Exception as exc:
        print(f"no readable ledger at {path} ({exc})")
        return 1
    try:
        since = json.load(open(path, encoding="utf-8")).get("since") or LEDGER_SINCE
    except Exception:
        since = LEDGER_SINCE
    spent = [r for r in rows if r.get("usd")]
    print(f"ledger since {since} (runs before it are not recorded; "
          f"use the Actions log for those days)")
    print(f"{path}: {len(rows)} run(s), "
          f"{sum(r.get('tokens') or 0 for r in rows):,} tokens, "
          f"${sum(float(r.get('usd') or 0) for r in rows):.2f} total, "
          f"{len(rows) - len(spent)} that spent nothing")
    _spend_lines(rows)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--file":
        sys.exit(tally_file(sys.argv[2] if len(sys.argv) > 2 else None))
    if len(sys.argv) > 2 and sys.argv[1] == "--tally":
        sys.exit(tally(sys.argv[2]))
    try:
        append()
    except Exception as exc:  # observability must never fail the run
        print(f"::warning::ops ledger append failed ({exc}); run unaffected")
        sys.exit(0)
