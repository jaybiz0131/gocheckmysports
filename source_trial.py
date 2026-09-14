#!/usr/bin/env python3
"""source_trial.py: the daily record the S-D day-14 report will be built from.

WHY THIS HAD TO EXIST BEFORE THE 28th. S-D asks for three numbers at day 14: items
ingested per feed, verifier reject rate per feed, and stories published per lane. None
of the three was recoverable from what the desk keeps:

  - source_health.json holds per-feed item counts but is a SNAPSHOT, overwritten on
    every run. There is no series, so "items over fourteen days" did not exist.
  - A published story's provenance is the OUTLET IT CITES, not the feed it arrived
    through, so nothing could attribute a story or a rejection to a trial feed.
  - The aggregator's own per-feed output lives in out/, which is gitignored and
    replaced each run.

Waiting until the 28th to discover that would have meant a report with no data behind
it. This writes a dated file a day: per feed, its state, its item count, and the
headlines it carried. Headlines are what make the other two numbers possible, because a
rejected or published headline can be matched back to the feeds that carried it.

Exit is always 0. This is instrumentation and must never fail a run.

USAGE  python3 source_trial.py            record today
       python3 source_trial.py --report   summarise what has accumulated
"""

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SNAP_DIR = os.path.join(HERE, "site", "data", "source-trial")
CONFIG = os.path.join(HERE, "config.json")
HEADLINE_CAP = 40      # enough to attribute, small enough to keep fourteen days of


def _today():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def record(once_a_day=True):
    # ONE FETCH A DAY, NOT ONE PER BUILD. This re-reads every feed to capture
    # headlines, and the site builds many times a day. A day already recorded is left
    # alone unless a caller asks for a rewrite.
    if once_a_day and os.path.exists(os.path.join(SNAP_DIR, f"{_today()}.json")):
        print(f"source_trial: {_today()} already recorded")
        return None
    try:
        import source_health
        rows = source_health.gather()
    except Exception as e:
        print(f"source_trial: could not gather ({type(e).__name__}); nothing recorded")
        return None
    try:
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        trial = set((cfg.get("sources") or {}).get("sd_trial", {}).get("feeds") or [])
    except Exception:
        trial = set()

    # source_health reports counts; the headlines come from re-reading what it read, so
    # this asks the aggregator for them rather than inventing a second fetch path.
    heads = {}
    try:
        import aggregate, common, urllib.request
        for entry in (cfg.get("sources") or {}).get("rss") or []:
            url = entry.get("url") or ""
            if not url:
                continue
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": common.ua_for(url),
                    "Accept": "application/rss+xml, application/xml, text/xml, */*"})
                body = urllib.request.urlopen(req, timeout=20).read()
                items = aggregate.parse_feed(body, entry.get("name") or url,
                                             entry.get("tier") or "major")
                heads[entry.get("name")] = [
                    (i.get("headline") or "")[:140] for i in items[:HEADLINE_CAP]]
            except Exception:
                heads[entry.get("name")] = []
    except Exception:
        pass

    day = _today()
    payload = {
        "day": day,
        "recorded_utc": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feeds": [{
            "name": r.get("name"), "tier": r.get("tier"),
            "state": r.get("lane_state") or r.get("state"),
            "items": r.get("items"), "newest_age_h": r.get("newest_age_h"),
            "in_trial": r.get("name") in trial,
            "headlines": heads.get(r.get("name")) or [],
        } for r in rows if r.get("kind") == "rss"],
    }
    os.makedirs(SNAP_DIR, exist_ok=True)
    with open(os.path.join(SNAP_DIR, f"{day}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"), sort_keys=True)
    n_trial = sum(1 for x in payload["feeds"] if x["in_trial"])
    print(f"source_trial: recorded {len(payload['feeds'])} feed(s) for {day}, "
          f"{n_trial} in the S-D trial")
    return payload


def load_all():
    out = []
    if not os.path.isdir(SNAP_DIR):
        return out
    for f in sorted(os.listdir(SNAP_DIR)):
        if f.endswith(".json"):
            try:
                out.append(json.load(open(os.path.join(SNAP_DIR, f), encoding="utf-8")))
            except Exception:
                continue
    return out


def report():
    """What the day-14 write-up reads. Says plainly how many days it has."""
    days = load_all()
    if not days:
        print("source_trial: no days recorded yet")
        return 0
    try:
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        t = (cfg.get("sources") or {}).get("sd_trial") or {}
    except Exception:
        t = {}
    print(f"S-D trial: opened {t.get('opened','?')}, review {t.get('review_on','?')}, "
          f"{len(days)} day(s) recorded")
    agg = {}
    for d in days:
        for f in d.get("feeds") or []:
            a = agg.setdefault(f["name"], {"days": 0, "items": 0, "trial": f.get("in_trial"),
                                           "tier": f.get("tier"), "bad": 0})
            a["days"] += 1
            a["items"] += f.get("items") or 0
            if f.get("state") not in ("OK",):
                a["bad"] += 1
    print(f"  {'feed':38} {'tier':8} {'days':>5} {'items':>7} {'avg/day':>8}  state")
    for name, a in sorted(agg.items(), key=lambda kv: -kv[1]["items"]):
        mark = "TRIAL " if a["trial"] else "      "
        avg = a["items"] / a["days"] if a["days"] else 0
        st = "ok" if not a["bad"] else f"{a['bad']} bad day(s)"
        print(f"  {mark}{name[:32]:32} {str(a['tier'])[:8]:8} {a['days']:5} "
              f"{a['items']:7} {avg:8.1f}  {st}")
    return 0


def main():
    if "--report" in sys.argv:
        return report()
    record()
    return 0


if __name__ == "__main__":
    sys.exit(main())
