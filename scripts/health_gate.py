#!/usr/bin/env python3
"""health_gate.py: the one mail a desk sends Jack (N-1, November 22, 2026).

Once a day at 7 AM Eastern this reads the last 24 hours of the desk's run conclusions and the
public site's own freshness stamps, and FAILS (one "Run failed" mail) only when:

  1. the desk has not published for a full day:
       Sports  the site's /stamp.txt says it has not built for more than 24 hours
       Crypto  the same, or the newest Brief or morning read (/api/v1/brief/latest.json) is
               more than 24 hours old
  2. Sports: the scores went more than two hours without a new reading while a game was on
     (read from every scores snapshot committed in the last 24 hours, each by its own
     fetched_at, which is the time the "Scores as of" stamp prints)
  3. Crypto: the Board's prices were more than six hours old when the site last built
     (/api/v1/markets.json: built_utc minus as_of_utc). The Board builds twice a day by
     Jack's deploy budget, so its wall-clock age passes six hours every day by design; the
     reading that says CoinGecko failed a build is its age at that build.

Every other workflow is built so it reaches "failure" only when the desk did not do its job,
and this gate is the mail that says a desk has been down long enough to need Jack. What each
mail means and what to do: docs/HEALTH.md in gcm-newsroom.

A site that does not answer after three tries is itself a finding. The run conclusions are
printed as evidence beside the findings; they never fail the gate on their own.

USAGE
  python3 scripts/health_gate.py                 # in Actions: reads the site, the runs, git
  python3 scripts/health_gate.py --desk sports   # outside Actions (no token: runs not read)
Stdlib only. No model call.
"""

import datetime
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
SITES = {"sports": "https://gocheckmysports.com", "crypto": "https://gocheckmycrypto.com"}
PUBLISH_WORKFLOWS = {"sports": ("scores-cadence.yml", "inactives.yml", "conditions-report.yml"),
                     "crypto": ("crypto-news-brief.yml", "morning-read.yml", "watcher.yml")}
GATE_HOUR_ET = 7
PUBLISH_HOURS = 24
SCORES_GAP_HOURS = 2
BOARD_HOURS = 6
GAME_HOURS = 4.5          # a game this long after kickoff with no final is no longer counted as on
SCORES_PATH = "site/data/scoreboard.json"
# S-DONE: a reading is a build's snapshot or a re-read (live_board.py's copy, the board the pages
# replace theirs with between builds). Both carry fetched_at, the time the stamp prints.
SCORES_PATHS = (SCORES_PATH, "site/data/live/scoreboard.json")
SCORES_LEAGUES = ("NFL", "CFB")


def utc(iso):
    if not iso:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)


def et(d):
    """'Nov 21, 3:43 PM ET'. Reader-facing times are Eastern, with the zone."""
    return d.astimezone(ET).strftime("%b %-d, %-I:%M %p ET") if d else "never"


def hours(td):
    h = td.total_seconds() / 3600
    return f"{h:.1f} hours"


# ---- when the gate runs ---------------------------------------------------------------------

def should_run(now, event, earlier_today, by=""):
    """(run?, why). One gate a day: the first tick at or after 7 AM ET that finds no earlier gate
    run today. Two crons cover the two offsets (11:03 and 12:03 UTC); a dispatch by hand always
    runs. A dispatch the desk's own runs made (by == "start", S-DONE) keeps the day's rule."""
    if event == "workflow_dispatch" and by != "start":
        return True, "dispatched by hand"
    if now.astimezone(ET).hour < GATE_HOUR_ET:
        return False, f"before {GATE_HOUR_ET} AM ET ({et(now)}); the other cron line is today's gate"
    if earlier_today:
        return False, f"today's gate already ran ({earlier_today} earlier run(s) today, ET)"
    return True, ""


def _is_gate(r, now, any_status=False):
    """A run that is, or stood for, the gate of `now`'s ET day: created at or after 7 AM ET that day
    (a cron delivered before 7 stands down and is nobody's gate), by GitHub's cron or by the desk's
    own start; a dispatch by hand is neither."""
    made = utc(r.get("created_at"))
    if not made:
        return False
    day = now.astimezone(ET).replace(hour=GATE_HOUR_ET, minute=0, second=0, microsecond=0)
    if not (day <= made.astimezone(ET) and made.astimezone(ET).date() == day.date()):
        return False
    if r.get("event") == "workflow_dispatch" and "(start)" not in (r.get("display_title") or ""):
        return False
    return any_status or r.get("status") == "completed"


def gates_today(now, runs, this_run=None):
    """How many gates have already run today (ET), this run aside."""
    return sum(1 for r in runs or [] if str(r.get("id")) != str(this_run) and _is_gate(r, now))


def start_due(now, runs):
    """(bool, why): whether one of the desk's Worker-dispatched runs should start today's gate.
    GitHub delivered the 7:03 AM cron at 4:05 PM ET on November 24 and not at all by 2:30 PM on the
    25th. From 7 AM ET, when no gate of today's is queued, running or done, one is started. Runs
    that could not be read start nothing: this run can end in a mail."""
    if runs is None:
        return False, "the gate's runs could not be read"
    if now.astimezone(ET).hour < GATE_HOUR_ET:
        return False, f"before {GATE_HOUR_ET} AM ET"
    for r in runs:
        if _is_gate(r, now, any_status=True):
            return False, f"today's gate is run {r.get('id')} ({r.get('status')})"
    return True, "no gate has run since 7 AM ET"


# ---- the checks, pure -------------------------------------------------------------------------

def site_finding(now, built):
    if built is None:
        return "The site's build stamp (/stamp.txt) could not be read."
    if now - built > datetime.timedelta(hours=PUBLISH_HOURS):
        return (f"The site has not built for a full day: last build {et(built)}, "
                f"{hours(now - built)} ago.")
    return None


def crypto_findings(now, built, brief_asof, board_asof, board_built):
    out = []
    f = site_finding(now, built)
    if f:
        out.append(f)
    if brief_asof is None:
        out.append("No Brief or morning read could be read from /api/v1/brief/latest.json.")
    elif now - brief_asof > datetime.timedelta(hours=PUBLISH_HOURS):
        out.append(f"No Brief or morning read for a full day: the newest is from {et(brief_asof)}, "
                   f"{hours(now - brief_asof)} ago.")
    if board_asof is None or board_built is None:
        out.append("The Board's stamp could not be read from /api/v1/markets.json.")
    elif board_built - board_asof > datetime.timedelta(hours=BOARD_HOURS):
        out.append(f"The Board's prices were {hours(board_built - board_asof)} old when the site built "
                   f"at {et(board_built)} (prices from {et(board_asof)}).")
    return out


def _games(sb):
    for L in (sb or {}).get("leagues") or []:
        if L.get("league") not in SCORES_LEAGUES:
            continue
        for g in L.get("games") or []:
            yield g


def on_at(g, x):
    """True when game `g`, as one snapshot read it, was on at moment `x`: kicked off by then, not
    final in that snapshot, and inside GAME_HOURS of its kickoff."""
    k = utc(g.get("start_utc"))
    if not k or g.get("state") == "post" or g.get("completed"):
        return False
    if "postpon" in str(g.get("status_short") or "").lower():
        return False
    return k <= x <= k + datetime.timedelta(hours=GAME_HOURS)


def scores_findings(now, snaps):
    """`snaps`: [(fetched_at, scoreboard dict)], any order. Each gap between two readings (and
    from the newest reading to `now`) longer than SCORES_GAP_HOURS is a finding when a game, as
    the earlier reading had it, was on at the moment the stamp passed SCORES_GAP_HOURS."""
    out = []
    snaps = sorted((t, sb) for t, sb in snaps if t)
    for i, (t, sb) in enumerate(snaps):
        nxt = snaps[i + 1][0] if i + 1 < len(snaps) else now
        if nxt - t <= datetime.timedelta(hours=SCORES_GAP_HOURS):
            continue
        late = t + datetime.timedelta(hours=SCORES_GAP_HOURS)
        on = [g for g in _games(sb) if on_at(g, late)]
        if on:
            names = ", ".join(f"{(g.get('away') or {}).get('abbr')} at {(g.get('home') or {}).get('abbr')}"
                              for g in on[:3])
            more = f" and {len(on) - 3} more" if len(on) > 3 else ""
            out.append(f"Scores went {hours(nxt - t)} without a new reading while games were on: "
                       f"'Scores as of' read {et(t)} until {et(nxt) if i + 1 < len(snaps) else 'this check'} "
                       f"({names}{more}).")
    return out


# ---- reading the world ------------------------------------------------------------------------

def fetch(url, tries=3, timeout=20):
    """GET with three tries, jittered backoff, a total under a minute. Returns text or None."""
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gcm-health-gate"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError, ValueError):
            if n + 1 < tries:
                time.sleep(2 ** n * 3 + random.uniform(0, 2))
    return None


def stamp_built(text):
    for line in (text or "").splitlines():
        if line.startswith("built "):
            return utc(line[6:])
    return None


def feed(base, name):
    t = fetch(f"{base}/api/v1/{name}.json")
    try:
        return json.loads(t) if t else None
    except ValueError:
        return None


def git_snapshots(since, paths=SCORES_PATHS):
    """Every committed scores reading since `since`, as (fetched_at, dict), from this checkout: the
    build snapshots and the re-reads."""
    out = []
    ran = False
    for path in paths:
        try:
            shas = subprocess.run(["git", "log", f"--since={since.isoformat()}", "--format=%H", "HEAD", "--",
                                   path], capture_output=True, text=True, timeout=60).stdout.split()
            ran = True
        except (OSError, subprocess.SubprocessError):
            continue
        for h in shas:
            try:
                sb = json.loads(subprocess.run(["git", "show", f"{h}:{path}"], capture_output=True,
                                               text=True, timeout=60).stdout)
            except (ValueError, OSError, subprocess.SubprocessError):
                continue
            out.append((utc(sb.get("fetched_at")), sb))
        # the reading in force when the window opened, so a gap that began before it is measured
        try:
            h = subprocess.run(["git", "log", "-1", f"--before={since.isoformat()}", "--format=%H", "HEAD", "--",
                                path], capture_output=True, text=True, timeout=60).stdout.strip()
            if h:
                sb = json.loads(subprocess.run(["git", "show", f"{h}:{path}"], capture_output=True,
                                               text=True, timeout=60).stdout)
                out.append((utc(sb.get("fetched_at")), sb))
        except (ValueError, OSError, subprocess.SubprocessError):
            pass
    return out if ran else None


def gh_api(path):
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}", headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
        "User-Agent": "gcm-health-gate", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def runs_since(since):
    d = gh_api(f"actions/runs?created=>={since.strftime('%Y-%m-%dT%H:%M:%SZ')}&per_page=100")
    return None if d is None else d.get("workflow_runs") or []


def gate_runs():
    d = gh_api("actions/workflows/health.yml/runs?per_page=20")
    return None if d is None else d.get("workflow_runs") or []


def earlier_gates_today(now, this_run):
    return gates_today(now, gate_runs(), this_run)


def start(argv=()):
    """--start: run by the scores-start job of the poller and the brief. Never fails that job."""
    now = datetime.datetime.now(UTC)
    due, why = start_due(now, gate_runs())
    if not due:
        print(f"health_gate: not started, {why}")
        return 0
    r = subprocess.run(["gh", "workflow", "run", "health.yml", "--ref", "main", "-f", "by=start"],
                       capture_output=True, text=True, timeout=45)
    if r.returncode != 0:
        print(f"::warning::health: the start dispatch failed ({r.stderr.strip()[:160]}); the next run asks again")
    else:
        print(f"health_gate: today's gate is started ({why})")
    return 0


def summary(lines):
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    text = "\n".join(lines) + "\n"
    print(text)
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(text)


def main(argv):
    desk = None
    if "--desk" in argv:
        desk = argv[argv.index("--desk") + 1]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    desk = desk or ("sports" if repo.endswith("gocheckmysports") else "crypto" if repo.endswith("gocheckmycrypto") else None)
    if desk not in SITES:
        print("health_gate: name the desk (--desk sports|crypto)")
        return 2
    now = datetime.datetime.now(UTC)
    run, why = should_run(now, os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch"),
                          earlier_gates_today(now, os.environ.get("GITHUB_RUN_ID")), (os.environ.get("BY") or "").strip())
    if not run:
        print(f"health_gate: standing down, {why}")
        return 0
    base = SITES[desk]
    since = now - datetime.timedelta(hours=PUBLISH_HOURS)
    built = stamp_built(fetch(f"{base}/stamp.txt"))
    if desk == "crypto":
        br, mk = feed(base, "brief/latest"), feed(base, "markets")
        findings = crypto_findings(now, built, utc((br or {}).get("as_of_utc")),
                                   utc((mk or {}).get("as_of_utc")), utc((mk or {}).get("built_utc")))
        stamps = [f"| Site build | {et(built)} |",
                  f"| Newest Brief or morning read | {et(utc((br or {}).get('as_of_utc')))} |",
                  f"| Board prices / built | {et(utc((mk or {}).get('as_of_utc')))} / {et(utc((mk or {}).get('built_utc')))} |"]
    else:
        snaps = git_snapshots(since)
        findings = [f for f in [site_finding(now, built)] if f]
        if snaps is None:
            findings.append("The scores history could not be read from git.")
        else:
            findings += scores_findings(now, snaps)
        newest = max((t for t, _ in snaps or [] if t), default=None)
        stamps = [f"| Site build | {et(built)} |",
                  f"| Newest 'Scores as of' | {et(newest)} |",
                  f"| Score readings in 24 hours | {sum(1 for t, _ in snaps or [] if t and t >= since)} |"]
    runs = runs_since(since)
    lines = [f"## {desk.title()} health, {et(now)}", "", "| Stamp | Reads |", "|---|---|", *stamps, ""]
    if runs is None:
        lines.append("Run conclusions: not readable here (no token).")
    else:
        tally = {}
        for r in runs:
            k = r.get("path", "").split("/")[-1]
            tally.setdefault(k, {}).setdefault(r.get("conclusion") or r.get("status"), 0)
            tally[k][r.get("conclusion") or r.get("status")] += 1
        lines += ["| Workflow, last 24 hours | Conclusions |", "|---|---|"]
        lines += [f"| {k}{' (publishes)' if k in PUBLISH_WORKFLOWS[desk] else ''} | "
                  f"{', '.join(f'{c} {n}' for c, n in sorted(v.items()))} |" for k, v in sorted(tally.items())]
    lines.append("")
    if findings:
        lines.append("**Down long enough to need Jack.** What each line means and what to do: "
                     "docs/HEALTH.md in gcm-newsroom.")
        lines += [f"- {f}" for f in findings]
    else:
        lines.append("Healthy: published inside a day" + (", scores current through every game" if desk == "sports"
                     else ", the Board fresh at its last build") + ".")
    summary(lines)
    for f in findings:
        print(f"::error::{f}")
    return 1 if findings else 0


if __name__ == "__main__":
    if "--start" in sys.argv:
        sys.exit(start(sys.argv[1:]))
    sys.exit(main(sys.argv[1:]))
