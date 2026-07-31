#!/usr/bin/env python3
"""event_coverage.py: post-run check that the day's known major events got covered.

Owner directive 2026-07-27 (audit: Spence-Tszyu covered, Joshua's KO the same night
missed): aggregation is reactive to feeds; this check makes the run AWARE of the
schedule. For every calendar event active today (config event_calendar plus the
weekly hand-updated event-week.json), it looks for a published story from the last
36 hours matching the event's keywords and emits a ::warning:: for any event with
none, so the editor-in-chief sees the gap the same day. Fail-open: flags only,
never blocks; NO MODEL CALLS.
"""

import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    from editor import active_events
    events = active_events()
    if not events:
        print("event coverage: no calendar events active today")
        return 0
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(hours=36)).isoformat()
    stories = []
    for p in glob.glob(os.path.join(HERE, "site", "content", "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("id", "").startswith("wrap-") or (d.get("published_utc") or "") < cutoff:
            continue
        stories.append(" ".join([d.get("title") or "", d.get("dek") or "",
                                 d.get("key_fact") or ""]))
    blob = " \n ".join(stories).lower()
    uncovered = []
    for e in events:
        kws = e.get("keywords") or []
        rx = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")\b", re.I) \
            if kws else None
        if rx is None or not rx.search(blob):
            uncovered.append(e["name"])
    # Write the gap report, not just warnings. A ::warning:: is invisible unless somebody
    # opens the run log, which is how the crypto desk missed the FOMC decision it had
    # itself flagged. The workflow reads this file and raises a flag a human will see.
    # Still fail-open, still never a gate: a coverage gap is a judgment call.
    today = datetime.datetime.now(datetime.timezone.utc)
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    json.dump({"checked_utc": today.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "uncovered": [{"date": today.strftime("%Y-%m-%d"), "kind": "event",
                              "title": e["name"],
                              "match": e.get("keywords") or [],
                              "source": e.get("source", "today's event calendar")}
                             for e in events if e["name"] in uncovered]},
              open(os.path.join(HERE, "out", "event_gaps.json"), "w", encoding="utf-8"),
              indent=1)
    for name in uncovered:
        print(f"::warning::event coverage: '{name}' is on today's calendar with NO "
              f"published story in 36h; the desk may be missing a marquee event")
    if not uncovered:
        print(f"event coverage: all {len(events)} active calendar events have coverage")
    return 0


if __name__ == "__main__":
    sys.exit(main())
