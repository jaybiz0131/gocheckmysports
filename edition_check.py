#!/usr/bin/env python3
"""
edition_check.py: the daily edition is supposed to be guaranteed. Prove it, or say so.

WHY THIS EXISTS
  The workflow runs the edition as `python3 wrap.py || echo "::warning::daily edition failed
  its gates; stories unaffected"`. Fail-open is the right call: an edition failure must never
  block story publishing, and it does not. But `|| echo` also means the job stays green, the
  warning scrolls past in a 700-line log, and nothing anywhere counts how long it has been.

  It went unnoticed for three days. On 2026-07-31 the newest edition on the site was the
  July 28 Evening Brief, still holding the homepage hero and still telling readers to watch
  an FOMC decision that had happened two days earlier. The desk published 13 stories in that
  window. Nobody knew the edition had stopped, because nothing was watching the one thing
  that would have said so: the gap.

  The root cause that day was real and fixable (an unstated sign convention on the whale
  board, see chartmaster._net_plain). The reason it lasted three days was not. A fail-open
  step with no gap check is indistinguishable from a step that works.

WHAT IT DOES
  Reads the committed editions and reports the age of the newest one. Over the threshold it
  emits a ::error:: annotation the workflow raises a flag from, exactly like the calendar and
  hacks-ledger checks. It never fails the run: whether a missing edition is worth acting on
  is an editorial judgment, and a check that could block publishing over one would be worse
  than the problem it reports.

THE THRESHOLD is 26 hours, not 24. Three slots a day means a healthy desk is never more than
about 8 hours from an edition, so 26 is generous by design: it clears a slot that legitimately
failed plus the next one, and only fires once a gap is no longer explainable as a bad run.

USAGE  python3 edition_check.py [--max-age-hours N]
"""

import datetime
import glob
import json
import os
import sys

import common

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "site", "content")

MAX_AGE_HOURS = 26


def _when(item):
    raw = item.get("published_utc") or ((item.get("date") or "") + "T00:00:00Z")
    try:
        return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def newest(kind, content=None):
    """The newest committed item, either 'edition' (a wrap) or 'story' (anything else)."""
    best = None
    for p in glob.glob(os.path.join(content or CONTENT, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("example"):
            continue
        is_wrap = str(d.get("id") or "").startswith("wrap-")
        if (kind == "edition") != is_wrap:
            continue
        when = _when(d)
        if when and (best is None or when > best[0]):
            best = (when, d)
    return best


def gap_hours(now=None, content=None):
    """(hours since the newest edition, the edition) or (None, None) if there are none."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    best = newest("edition", content)
    if not best:
        return None, None
    return (now - best[0]).total_seconds() / 3600, best[1]


def main():
    argv = sys.argv[1:]
    limit = (int(argv[argv.index("--max-age-hours") + 1])
             if "--max-age-hours" in argv else MAX_AGE_HOURS)
    hours, ed = gap_hours()
    if hours is None:
        common.gh("error", "edition_check: the desk has published NO daily edition at all.")
        return 0

    # Stories since the edition are what make a gap visible to a reader: the front page
    # carries newer reporting than the read that is supposed to summarise the day.
    since = 0
    latest = newest("story")
    if latest:
        ed_when = _when(ed)
        since = sum(1 for p in glob.glob(os.path.join(CONTENT, "*.json"))
                    if _newer_story(p, ed_when))

    msg = (f"newest edition is {hours:.0f}h old ({ed.get('date')}, "
           f"{(ed.get('title') or '')[:60]}), {since} story/stories published since")
    if hours > limit:
        common.gh("error",
                  f"edition_check: {msg}. The edition is supposed to run three times a day "
                  f"and the workflow step is fail-open, so a broken edition is silent unless "
                  f"something counts the gap. Read the wrap step's log for the gate it failed.")
        _flag_issue(msg)
    else:
        print(f"edition_check: OK, {msg}.")
    return 0


def _flag_issue(msg):
    """A warning inside a green run is a named anti-pattern (owner ruling 2026-08-03):
    every fail-open either fails closed or escalates to a flag issue. The edition step
    stays fail-open, so breach of the gap threshold files ONE deduplicated issue. Three
    sports editions died in a row on 2026-08-02..03 with only ::warning:: lines to show
    for it; this is the bell that was missing. No token -> the annotation above is the
    whole alarm, stated here so the gap in coverage is visible in the log."""
    import urllib.request
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        print("edition_check: no GH token in env; gap reported in annotations only")
        return
    title = "Edition gap: the guaranteed daily edition has stopped"
    hdrs = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues?state=open&labels=pipeline",
            headers=hdrs)
        if any(i["title"] == title for i in json.load(urllib.request.urlopen(req))):
            print("edition-gap issue already open; not duplicating")
            return
        body = (f"{msg}.\n\nThe edition step is fail-open by design (stories must never "
                "be blocked by a dead edition), so this issue is the loud part. Read the "
                "wrap step's log in the most recent brief runs for the belt or gate the "
                "edition died on. Close after the next published edition.")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues",
            data=json.dumps({"title": title, "body": body,
                             "labels": ["pipeline"]}).encode(),
            headers=hdrs, method="POST")
        urllib.request.urlopen(req)
        print("edition-gap issue opened")
    except Exception as e:
        print(f"edition_check: could not file the gap issue ({e.__class__.__name__})")


def _newer_story(path, cutoff):
    if not cutoff:
        return False
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return False
    if d.get("example") or str(d.get("id") or "").startswith("wrap-"):
        return False
    when = _when(d)
    return bool(when and when > cutoff)


if __name__ == "__main__":
    sys.exit(main())
