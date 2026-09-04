#!/usr/bin/env python3
"""
source_health.py: is every source this desk relies on actually serving? ADVISORY.

WHY THIS EXISTS (2026-09-04). Every source failure this family shipped in the last two
weeks was SILENT, and each one was visible in a log line nobody reads:

  - The scoreboard ran baseball-only through NFL season because ESPN answered 403 to the
    desk's branded User-Agent. Each league printed "WARN ... skipped, not fatal" and the
    snapshot wrote anyway. Nobody knew for days.
  - Three working ESPN intake lanes were RETIRED as dead on the strength of the same 403,
    which was a User-Agent problem and not a dead feed at all.
  - market_pulse carries a failed section forward and says so only in a warning.

The common shape is not "a source broke". Sources break constantly and fail-open is the
right doctrine for a newsroom: a dead feed must never take the desk down. The shape is
that a PERMANENT failure and a QUIET NIGHT produce identical output, so nothing ever
escalates. This file exists to tell those two apart and to make the difference legible
without reading a workflow log.

WHAT IT IS NOT. Not a gate. Never fails a run, never blocks a publish, always exits 0.
A source list is an editorial asset and only the owner retires an entry. This reports.

HOW IT DECIDES. Every source gets fetched with exactly the agent the pipeline would use
(common.ua_for, so an exception host is tested the way it is really called) and lands in
one of five states:

  OK          served, and the desk would ingest at least one item
  EMPTY       served 200, but zero usable items: real for a quiet league feed, and a
              standing EMPTY on a news feed is a dead feed wearing a 200
  CHALLENGED  202 or 403: the bot-challenge and blocked-agent class. THE ONE THAT COST
              THE MOST, because it looks like a hard failure and is usually a header or
              an egress IP, not a dead endpoint
  DEAD        4xx/5xx/timeout/unparseable
  SKIPPED     needs a key this environment does not have

THE BASELINE IS THE POINT. A single run tells you today's state; the committed
site/data/source_health.json tells you what CHANGED. A feed that went OK -> CHALLENGED
overnight is the signal, and it is the one that would have caught every failure above on
the first run instead of the fourth day.

USAGE
  python3 source_health.py            # report, compare to baseline, rewrite baseline
  python3 source_health.py --check    # report and compare, write nothing (CI/pre-push)
  python3 source_health.py --quiet    # only regressions and the summary line
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

CONFIG = os.path.join(HERE, "config.json")
BASELINE = os.path.join(HERE, "site", "data", "source_health.json")
TIMEOUT = 25

OK, EMPTY, CHALLENGED, DEAD, SKIPPED = "OK", "EMPTY", "CHALLENGED", "DEAD", "SKIPPED"
# Ordered worst-first so a regression is any move toward the front of this list.
SEVERITY = [DEAD, CHALLENGED, EMPTY, OK, SKIPPED]


def _sev(state):
    try:
        return SEVERITY.index(state)
    except ValueError:
        return len(SEVERITY)


def _probe(url, is_json=False):
    """One fetch, no retries: this is a health check, and a retry ladder would mask
    exactly the flakiness worth reporting. Returns (state, detail, payload)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": common.ua_for(url),
        "Accept": "application/json" if is_json else
                  "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            code = getattr(r, "status", 200)
            # A 202 IS a challenge, not a success. ESPN's RSS hosts answer datacenter IPs
            # with one and it reads as 2xx to anything that only checks for < 400.
            if code == 202:
                return CHALLENGED, "HTTP 202 bot challenge", None
            return OK, f"HTTP {code}", body
    except urllib.error.HTTPError as e:
        if e.code in (202, 403, 401, 429):
            return CHALLENGED, f"HTTP {e.code}", None
        return DEAD, f"HTTP {e.code}", None
    except Exception as e:
        return DEAD, f"{type(e).__name__}", None


def _newest_age_hours(items):
    newest = None
    for it in items:
        ts = it.get("_ts") or it.get("timestamp")
        if isinstance(ts, (int, float)):
            newest = max(newest or 0, ts)
    if not newest:
        return None
    age = (datetime.datetime.now(datetime.timezone.utc).timestamp() - newest) / 3600.0
    return round(age, 1)


def check_rss(entry):
    """A feed the aggregator reads. Tests the primary, and its fallback_api when the
    primary is challenged, which is the real serving path on a GitHub runner."""
    import aggregate
    name = entry.get("name") or entry.get("url", "")[:40]
    url = entry.get("url") or ""
    row = {"name": name, "kind": "rss", "url": url, "tier": entry.get("tier") or ""}

    # NOT EVERY ENTRY IN sources.rss IS RSS. The desk routes some lanes through a JSON
    # API and marks them with "format" (the Federal Register's own API is one). The first
    # cut of this file parsed those as XML, called the ParseError a DEAD source, and would
    # have reported a perfectly healthy official-record feed as broken on its first run.
    # A monitor that cries wolf is worse than no monitor: same reason the canary lives
    # inside ::stop-commands::.
    fmt = entry.get("format")
    state, detail, body = _probe(url, is_json=bool(fmt))
    items = []
    if state == OK and body:
        try:
            if fmt:
                handler = getattr(aggregate, f"{fmt}_api", None)
                items = handler(entry) if handler else json.loads(body).get("results") or []
            else:
                items = aggregate.parse_feed(body, name, entry.get("tier") or "major")
        except Exception as e:
            state, detail = DEAD, f"unparseable ({type(e).__name__})"
    if state == OK and not items:
        state, detail = EMPTY, detail + ", 0 items"

    row.update({"state": state, "detail": detail, "items": len(items),
                "newest_age_h": _newest_age_hours(items)})

    fb = entry.get("fallback_api")
    if fb:
        # Only meaningful when the primary is not serving, which on this chassis is the
        # normal case for ESPN: RSS challenged from CI, JSON tier carrying the lane.
        fstate, fdetail, fbody = _probe(fb, is_json=True)
        fitems = []
        if fstate == OK and fbody:
            try:
                fitems = aggregate.espn_api_fallback(entry)
            except Exception as e:
                fstate, fdetail = DEAD, f"unparseable ({type(e).__name__})"
            if fstate == OK and not fitems:
                fstate, fdetail = EMPTY, fdetail + ", 0 items"
        row["fallback"] = {"url": fb, "state": fstate, "detail": fdetail,
                           "items": len(fitems), "newest_age_h": _newest_age_hours(fitems)}
        # THE LANE IS ALIVE IF EITHER TIER SERVES. Reporting the primary alone is how
        # three working lanes got retired: the RSS host was challenged, which was true,
        # and the fallback was assumed dead without being tested separately.
        row["lane_state"] = OK if (state == OK or fstate == OK) else \
            min([state, fstate], key=_sev)
    else:
        row["lane_state"] = state
    return row


def check_league_api(name, url):
    row = {"name": name, "kind": "league_api", "url": url, "tier": "primary"}
    state, detail, body = _probe(url, is_json=True)
    n = 0
    if state == OK and body:
        try:
            data = json.loads(body)
            n = len(data.get("events") or data.get("dates") or data.get("articles") or [])
        except Exception as e:
            state, detail = DEAD, f"unparseable ({type(e).__name__})"
    row.update({"state": state, "detail": detail, "items": n,
                "lane_state": state, "newest_age_h": None})
    return row


def gather():
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    src = cfg.get("sources") or {}
    rows = []
    for entry in src.get("rss") or []:
        if not entry.get("url"):
            continue
        rows.append(check_rss(entry))
    # league_apis is {note, endpoints:[{name,tier,url,note}]} on the sports desk and
    # absent on the other two. Walk it defensively rather than assuming either.
    la = src.get("league_apis")
    endpoints = []
    if isinstance(la, dict):
        endpoints = la.get("endpoints") or []
    elif isinstance(la, list):
        endpoints = la
    for ep in endpoints:
        if isinstance(ep, dict) and str(ep.get("url", "")).startswith("http"):
            rows.append(check_league_api(ep.get("name") or ep["url"][:40], ep["url"]))
    return rows


def compare(rows, prev_rows):
    """Regressions only. A source that was already broken yesterday is not news today;
    a source that changed state is the whole reason this file exists."""
    prev = {r.get("name"): r for r in prev_rows}
    regressed, recovered = [], []
    for r in rows:
        was = prev.get(r["name"])
        if not was:
            continue
        a, b = was.get("lane_state"), r.get("lane_state")
        if a == b:
            continue
        if _sev(b) < _sev(a):
            regressed.append((r["name"], a, b, r.get("detail", "")))
        else:
            recovered.append((r["name"], a, b))
    return regressed, recovered


def main():
    args = set(sys.argv[1:])
    quiet, check_only = "--quiet" in args, "--check" in args

    rows = gather()
    try:
        prev = json.load(open(BASELINE, encoding="utf-8")).get("sources") or []
    except Exception:
        prev = []
    regressed, recovered = compare(rows, prev)

    by_state = {}
    for r in rows:
        by_state.setdefault(r["lane_state"], []).append(r)

    if not quiet:
        for state in SEVERITY:
            group = by_state.get(state) or []
            if not group:
                continue
            print(f"\n{state} ({len(group)}):")
            for r in sorted(group, key=lambda x: x["name"]):
                age = f", newest {r['newest_age_h']}h old" if r.get("newest_age_h") is not None else ""
                line = f"  {r['name'][:42]:42} {r.get('detail','')}, {r.get('items',0)} items{age}"
                fb = r.get("fallback")
                if fb:
                    line += f"\n  {'':42} fallback: {fb['state']} ({fb['detail']}, {fb['items']} items)"
                print(line)

    for name, a, b, detail in regressed:
        common.gh("warning", f"source_health: {name} regressed {a} -> {b} ({detail})")
    for name, a, b in recovered:
        print(f"source_health: {name} recovered {a} -> {b}")

    counts = ", ".join(f"{s} {len(by_state.get(s) or [])}" for s in SEVERITY
                       if by_state.get(s))
    print(f"\nsource_health: {len(rows)} sources -> {counts}"
          f"; {len(regressed)} regressed, {len(recovered)} recovered")

    if not check_only:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        payload = {"checked_utc": datetime.datetime.now(datetime.timezone.utc)
                   .strftime("%Y-%m-%dT%H:%M:%SZ"), "sources": rows}
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
        print(f"source_health: baseline written to {BASELINE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
