#!/usr/bin/env python3
"""
kill_streak.py: the kill ledger and its alarm (owner ruling 2026-08-03, N=3).

THE CHASSIS COPY. Identical in gocheckmycrypto, gocheckmynews and gocheckmysports.

WHY THIS EXISTS
  The Coldcard case: the desk broke the story on July 31, and over the next three days
  intake kept carrying the escalation, the editor kept ranking it, the writer kept
  drafting it, and the approver killed THIRTEEN consecutive drafts on accuracy while the
  story grew from $38M to nearly $89M and led every competitor. Each kill was logged
  individually and correctly; nothing counted them. FOMC died the same way, three kills
  in two days, promised to readers in the Week Ahead. The gate ran and caught; the
  pattern went unwatched.

WHAT IT DOES
  Reads editorial-log.json, groups rejected drafts into DEVELOPMENTS using the dedup
  guard's own matcher (dedupe.same_event, the same grain the publish guard uses), and
  treats a development's streak as broken only when a published story matches it after
  the last kill. Two consumers:

    kill_history(title)  -> the prior kills for a matching unbroken development, reasons
                            VERBATIM. The writer prepends these to the next draft's
                            prompt, so attempt N+1 knows exactly why attempts 1..N died
                            (the wraprescue pattern, applied at story level).
    main()               -> reports streaks; at N >= 3 files ONE deduplicated DIGEST
                            issue covering every live streak, each kill quoted verbatim
                            so a human can judge legitimate-versus-theater. '7.3K vs
                            7,300' is the calibration case study, in the template.

  Advisory for the run, loud for a human: never blocks anything.
"""
import glob
import json
import os
import sys

import common
import dedupe

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "editorial-log.json")
CONTENT = os.path.join(HERE, "site", "content")
STREAK_N = 3          # owner ruling 2026-08-03: three consecutive kills open the flag
RECENT_DAYS = 10      # a kill older than this is history, not a live streak


def _entries():
    try:
        return json.load(open(LOG, encoding="utf-8"))
    except Exception:
        return []


def _published(since_date=""):
    out = []
    for p in glob.glob(os.path.join(CONTENT, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("example") or str(d.get("id") or "").startswith("wrap-"):
            continue
        if str(d.get("date") or "") >= since_date:
            out.append((str(d.get("date") or ""), str(d.get("title") or "")))
    return out


def _recent_kills():
    import datetime
    cutoff = (datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)).isoformat()
    kills = []
    for e in _entries():
        d = str(e.get("date") or "")
        if d < cutoff:
            continue
        for r in e.get("rejected") or []:
            if r.get("headline"):
                kills.append({"date": d, "headline": r["headline"],
                              "category": r.get("category", "?"),
                              "reasons": [str(x) for x in (r.get("reasons") or [])]})
    return kills


def _group(kills):
    """Kills bucketed into developments by the publish guard's own matcher."""
    groups = []
    for k in kills:
        for g in groups:
            if dedupe.same_event(g[0]["headline"], "", k["headline"], ""):
                g.append(k)
                break
        else:
            groups.append([k])
    return groups


def _unbroken(group, published):
    """A publish matching the development after the last kill breaks the streak."""
    last = max(k["date"] for k in group)
    for date, title in published:
        if date >= min(k["date"] for k in group) and \
                dedupe.same_event(group[0]["headline"], "", title, ""):
            if date >= last:
                return False
    return True


def streaks(n=STREAK_N):
    kills = _recent_kills()
    if not kills:
        return []
    pub = _published(since_date=min(k["date"] for k in kills))
    return [sorted(g, key=lambda k: k["date"]) for g in _group(kills)
            if len(g) >= n and _unbroken(g, pub)]


def kill_history(title):
    """Prior unbroken kills matching this title's development, oldest first."""
    kills = _recent_kills()
    if not kills:
        return []
    pub = _published(since_date=min(k["date"] for k in kills))
    for g in _group(kills):
        if dedupe.same_event(g[0]["headline"], "", title, "") and _unbroken(g, pub):
            return sorted(g, key=lambda k: k["date"])
    return []


def _flag_digest(groups):
    """ONE digest issue for all live streaks (25 on first run; one issue per
    development would flood the tracker and bury the signal). Deduplicated by title;
    close it after triage and the next breach refiles with current state."""
    import urllib.request
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    title = f"Kill streaks: {len(groups)} developments the desk is abandoning"
    if not tok or not repo:
        print(f"kill_streak: no GH token; digest reported in log only")
        return
    hdrs = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues?state=open&labels=pipeline",
            headers=hdrs)
        if any(i["title"].startswith("Kill streaks:")
               for i in json.load(urllib.request.urlopen(req))):
            print("kill-streak digest already open; not duplicating")
            return
        sections = []
        for g in sorted(groups, key=lambda g: -len(g)):
            sections.append(f"\n### {len(g)}x: {g[-1]['headline'][:90]} "
                            f"({g[0]['date']}..{g[-1]['date']})")
            for k in g:
                sections.append(f"- **{k['date']}** [{k['category']}] {k['headline'][:90]}")
                for r in k["reasons"][:2]:
                    sections.append(f"  - {r[:300]}")
        body = (
            "Developments with three or more consecutive approver kills and no publish "
            "breaking the streak (the Coldcard pattern: 13 kills over three days while "
            "the story tripled and led every competitor).\n\nEach kill is quoted so a "
            "human can judge legitimate-versus-theater. The calibration case study is "
            "'7.3K BTC vs 7,300 BTC': a kill over notation identity is theater; a kill "
            "over a smuggled or contradicted fact is the gate working.\n"
            + "\n".join(sections) +
            "\n\nThe next draft of each development automatically carries its prior "
            "objections verbatim in the writer prompt. Close after triage; the next "
            "breach refiles with current state.")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues",
            data=json.dumps({"title": title, "body": body,
                             "labels": ["pipeline"]}).encode(),
            headers=hdrs, method="POST")
        urllib.request.urlopen(req)
        print(f"kill-streak digest opened: {title}")
    except Exception as e:
        print(f"kill_streak: could not file digest ({e.__class__.__name__})")


def main():
    hits = streaks()
    if not hits:
        print("kill_streak: no unbroken kill streaks at threshold "
              f"{STREAK_N} in the last {RECENT_DAYS} days.")
        return 0
    for g in hits:
        common.gh("error",
                  f"kill_streak: '{g[-1]['headline'][:70]}' killed {len(g)}x "
                  f"consecutively ({g[0]['date']}..{g[-1]['date']}) with no publish; "
                  f"the desk is abandoning a development it owns.")
    _flag_digest(hits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
