#!/usr/bin/env python3
"""
twin_audit.py: near-identical headlines that are NOT linked as an update. ADVISORY.

P2. The desk publishes the same event twice and the existing guards do not stop it. This
file is the measurement, deliberately not the gate, and the reason is in the record.

WHAT WAS ALREADY KNOWN. publish_sweep drops a story when THREE conditions hold together:
adds_nothing_new says it carries no new claim token, it published within a day of its
twin, and it shares at least 45% of the twin's headline. Replaying those against every
real twin on this family's corpora, the binding constraint is the FIRST one, on 9 of 9:
every twin added at least one novel token, so none of them was ever dropped. The day
window fails on 7 of 9 but is not the cause; widening it fixes nothing, which is worth
knowing because it is the obvious first thing to reach for.

publish_sweep's own comment predicted this: "a twin that differs by ONE throwaway token
walks straight through it", and raising the bar to one token was already measured and
rejected for false drops.

WHAT TWO CANDIDATE RULES GOT WRONG, both rejected on live data:

  1. Headline overlap >= 0.70 alone catches every real twin, and also 21 of 95 DECLARED
     follow-ups on the news desk. Exempting update_of handles those.
  2. Overlap plus a shared subject word still drops this pair:

         Japan earthquake kills at least 18; rescue operations under way
         Indonesia earthquake kills at least 47, rescue operations continue

     Two different earthquakes, seventeen days apart, 0.75 headline overlap. They share
     "earthquake", "kills", "rescue" and "operations" because they share a SENTENCE
     TEMPLATE, not a subject. Dropping the second loses a real story about a real
     disaster, which is the worst outcome available to this check.

WHAT ACTUALLY SEPARATES THEM. The distinctive-token signature, which dedupe already
computes. A genuine retelling shares fingerprint tokens with its twin; two different
events that happen to be written the same way share NONE:

    Japan / Indonesia   shared 0     <- different events
    BlackRock funds     shared 1
    Billings shooting   shared 2
    USPS whistleblower  shared 3
    Supreme Court       shared 7

WHY THIS IS STILL NOT A GATE. A publish_sweep drop DELETES A VERIFIED STORY, and the bar
for that is higher than for a hold. One shared token is a thin floor, and "a matcher
satisfied by a single shared token needs a floor measured from the corpus" is the rule
this chassis has now relearned four times: consistency.RECURRING_ACTORS, the month names,
supersede_ok's dedupe branch, and a WNBA rule that read Sky Sports as a basketball team.
Shipping a deletion rule on a separator with one clean day of evidence would be the fifth.

So this reports, with the evidence attached, and the numbers accumulate. When the record
is clean across several days the threshold can move into publish_sweep with something
behind it. Same order source_health went in: instrument first, teeth later.

Exit is always 0.

USAGE  python3 twin_audit.py            # report
       python3 twin_audit.py --quiet    # the summary line only
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402
import dedupe  # noqa: E402
import site_build as sb  # noqa: E402

# Headline overlap at or above this makes a pair worth looking at. Every confirmed twin on
# both corpora sits at 0.75 or higher; the follow-up class sits far below.
OVERLAP_MIN = 0.70
# Shared distinctive tokens at or below this reads as two different events wearing one
# sentence template, rather than one event told twice.
DIFFERENT_EVENT_MAX_SHARED = 0


def _live():
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, "site", "content", "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if sb._is_wrap(d) or d.get("example") or d.get("superseded_by"):
            continue
        out.append(d)
    return out


def _linked(a, b):
    """The editor already said these two are one lineage; that is not a duplicate."""
    sa, sbg = a.get("slug"), b.get("slug")
    return (a.get("superseded_by") == sbg or b.get("superseded_by") == sa
            or a.get("continued_by") == sbg or b.get("continued_by") == sa
            or a.get("update_of") == sbg or b.get("update_of") == sa)


def candidates(items=None):
    """Unlinked pairs whose headlines are near-identical, with the evidence to judge them."""
    items = items if items is not None else _live()
    out = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            ov = dedupe._headline_overlap(a.get("title", ""), b.get("title", ""))
            if ov < OVERLAP_MIN or _linked(a, b):
                continue
            sig_a = dedupe._signature(a.get("title", ""), a.get("key_fact", ""))
            sig_b = dedupe._signature(b.get("title", ""), b.get("key_fact", ""))
            shared = sig_a & sig_b
            verdict = ("DIFFERENT EVENTS" if len(shared) <= DIFFERENT_EVENT_MAX_SHARED
                       else "LIKELY TWIN")
            out.append({
                "verdict": verdict, "overlap": round(ov, 2),
                "shared": sorted(shared),
                "a_only": sorted(sig_a - sig_b), "b_only": sorted(sig_b - sig_a),
                "a": a, "b": b,
            })
    out.sort(key=lambda r: (r["verdict"] != "LIKELY TWIN", -r["overlap"]))
    return out


def main():
    quiet = "--quiet" in sys.argv
    rows = candidates()
    twins = [r for r in rows if r["verdict"] == "LIKELY TWIN"]
    diff = [r for r in rows if r["verdict"] != "LIKELY TWIN"]

    if not quiet:
        for r in rows:
            print(f"\n  {r['verdict']}  headline overlap {r['overlap']}, "
                  f"{len(r['shared'])} shared distinctive token(s)")
            print(f"    A  {(r['a'].get('title') or '')[:74]}")
            print(f"       {r['a'].get('published_utc', '')}  /{r['a'].get('slug', '')[:52]}")
            print(f"    B  {(r['b'].get('title') or '')[:74]}")
            print(f"       {r['b'].get('published_utc', '')}  /{r['b'].get('slug', '')[:52]}")
            print(f"    shared : {r['shared'] or '(none: two different events, most likely)'}")
            print(f"    A only : {r['a_only'][:8]}")
            print(f"    B only : {r['b_only'][:8]}")

    if twins:
        common.gh("warning",
                  f"twin_audit: {len(twins)} near-identical unlinked pair(s) look like the "
                  f"same event published twice; {len(diff)} more share a headline template "
                  f"but no distinctive token and are probably different events. Advisory: "
                  f"nothing was changed.")
    print(f"\ntwin_audit: {len(rows)} candidate pair(s) -> {len(twins)} likely twin, "
          f"{len(diff)} likely different events (advisory; nothing changed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
