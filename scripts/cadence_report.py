#!/usr/bin/env python3
"""cadence_report.py: the weekend's numbers for the J-17 trial (Sprint B, B0b). Prints a block to paste
under the Sprint B section of docs/HANDOFF.md. Run from a full clone (git fetch --unshallow first).

  python3 scripts/cadence_report.py 2026-11-14 2026-11-15

  builds    the "scores: snapshot" commits pushed on those ET dates (each push builds), by day
  minutes   Netlify build minutes for the deploys published on those dates, from the Netlify API when
            NETLIFY_AUTH_TOKEN and NETLIFY_SITE_ID are set (the token stays in the environment, never in a
            file); otherwise the line says it could not be read and gives no number
  gap       for every game that reached Final in the snapshots, the time from the first snapshot that shows
            it final to the deploy that carried that snapshot (the next deploy at or after the commit). The
            true end of a game is not in any file, so a game that ended before that snapshot is later than
            this number says by up to one tick; the longest gap is the worst case across the dates.
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout


def snapshots(days):
    out = []
    for ln in git("log", "--format=%H %cI", "--grep=^scores:", "--", "site/data/scoreboard.json").splitlines():
        h, t = ln.split()
        t = datetime.datetime.fromisoformat(t)
        if t.astimezone(ET).date().isoformat() in days:
            out.append((t, h))
    return sorted(out)


def finals_in(h):
    try:
        d = json.loads(git("show", f"{h}:site/data/scoreboard.json"))
    except Exception:
        return set()
    return {g["id"] for L in d.get("leagues", []) for g in L.get("games", []) if g.get("state") == "post"}


def deploys():
    tok, site = os.environ.get("NETLIFY_AUTH_TOKEN"), os.environ.get("NETLIFY_SITE_ID")
    if not (tok and site):
        return None
    rows, page = [], 1
    while page < 20:
        req = urllib.request.Request(f"https://api.netlify.com/api/v1/sites/{site}/deploys?per_page=100&page={page}",
                                     headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            chunk = json.loads(r.read())
        if not chunk:
            break
        rows += chunk
        page += 1
    return rows


def main(days):
    snaps = snapshots(days)
    print(f"Scores builds, {' and '.join(days)}: {len(snaps)}")
    for d in days:
        print(f"  {d}: {sum(1 for t, _ in snaps if t.astimezone(ET).date().isoformat() == d)}")
    dep = deploys()
    if dep is None:
        print("Netlify build minutes: not read (set NETLIFY_AUTH_TOKEN and NETLIFY_SITE_ID in the environment)")
        pub = []
    else:
        pub = sorted((datetime.datetime.fromisoformat(x["published_at"].replace("Z", "+00:00")), x)
                     for x in dep if x.get("published_at") and x.get("state") == "ready")
        mine = [x for t, x in pub if t.astimezone(ET).date().isoformat() in days]
        secs = sum(x.get("deploy_time") or 0 for x in mine)
        print(f"Netlify build minutes: {secs / 60:.1f} across {len(mine)} deploys")
    seen, worst = set(), (datetime.timedelta(0), "")
    for t, h in snaps:
        new = finals_in(h) - seen
        seen |= new
        if new and pub:
            carried = next((p for p, _x in pub if p >= t), None)
            if carried and carried - t > worst[0]:
                worst = (carried - t, f"{len(new)} final(s) first shown in {h[:7]}")
    if pub:
        print(f"Longest gap, first snapshot showing a final to the deploy that carried it: {worst[0]} ({worst[1]})")
    else:
        print("Longest gap: not read (needs the deploy list)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
