#!/usr/bin/env python3
"""
merge_state.py: resolve the rebase conflicts a concurrent publish creates.

PORTED FROM THE CRYPTO DESK, which learned this the expensive way. The brief's push is
race-safe by design: main can move while a run is working, so a rejected push rebases and
retries. The workflow comment here claimed rebases are clean "because story files are
per-slug". Half true. site/content/ IS per-slug and never conflicts. editorial-log.json is
appended by EVERY run, so the moment two runs overlap (and the watcher's drifted retries
land in pairs, by its own comment) the rebase stops, the step exits non-zero under bash -e,
and the run's verified stories are lost.

That is not hypothetical: it is what killed crypto's 2026-07-28 23:20Z run, and this desk
has the same publish step with none of the fixes.

HOW IT MERGES, and why
  editorial-log.json   A record of what each run approved and rejected. Two runs each wrote
                       a real entry, so the union is the answer. Taking either side would
                       silently delete the other run's editorial record, which is the one
                       file where that matters most. Deduped on exact content, by date.
  site/data/scores.json
                       One generated snapshot of the live-scores fallback, not a record.
                       There is nothing to merge, so the newer generated_utc wins and on a
                       tie UPSTREAM wins. That direction is deliberate: upstream landed
                       while this run was still working, so its snapshot is the later one,
                       and letting our older one overwrite it would walk the board
                       backwards. Losing this run's costs nothing; the next run refetches.

SAFETY
  Only these paths are ever resolved. A conflict anywhere else is a real conflict that a
  human should see, and this script refuses to touch it and exits non-zero so the rebase
  stays stopped and the workflow fails loudly.

USAGE, from inside a stopped rebase
  python3 merge_state.py && git add <paths> && git rebase --continue
"""

import json
import subprocess
import sys

# The only paths this script will resolve. Anything else conflicting is a real conflict.
KNOWN = ("editorial-log.json", "site/data/scores.json")

def _stage(path, n):
    """One side of the conflict straight from the index, so conflict markers in the
    working file never have to be parsed."""
    r = subprocess.run(["git", "show", f":{n}:{path}"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def conflicted():
    r = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"],
                       capture_output=True, text=True, check=True)
    return [p for p in r.stdout.split("\n") if p.strip()]


def merge_editorial_log(upstream, replayed):
    """Union of run records, deduped on exact content, ordered by date.

    Dates repeat by design (one entry per slot per day), so dedup is on the whole record
    rather than on the date, and a genuinely identical record from both sides collapses
    to one."""
    seen, out = set(), []
    for entry in (upstream or []) + (replayed or []):
        key = json.dumps(entry, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(entry)
    return sorted(out, key=lambda e: str(e.get("date", "")))


def merge_scores(upstream, replayed):
    """Not a merge: a snapshot. Newer generated_utc wins, and on a tie UPSTREAM wins.

    Note the direction, and note it is the opposite of what "prefer our own work" would
    suggest. Upstream pushed while this run was still working, so upstream's snapshot is
    the later one; preferring our older one would walk the board backwards. Nothing is
    lost either way, because the next run refetches from the league APIs."""
    if not replayed:
        return upstream
    if not upstream:
        return replayed
    return (replayed if str(replayed.get("generated_utc", "")) >
            str(upstream.get("generated_utc", "")) else upstream)


MERGERS = {"editorial-log.json": merge_editorial_log,
           "site/data/scores.json": merge_scores}


def main():
    paths = conflicted()
    if not paths:
        print("merge_state: nothing conflicted")
        return 0

    unknown = [p for p in paths if p not in KNOWN]
    if unknown:
        print(f"::error::merge_state: refusing to auto-resolve a real conflict in "
              f"{', '.join(unknown)}. Only {', '.join(KNOWN)} have a deterministic "
              f"resolution; this one needs a human.")
        return 1

    for p in paths:
        # During a rebase, stage 2 is the upstream side and stage 3 is the commit being
        # replayed, which is this run's work. Named for what they mean here.
        upstream, mine = _stage(p, 2), _stage(p, 3)
        if upstream is None and mine is None:
            print(f"::error::merge_state: neither side of {p} parsed as JSON")
            return 1
        merged = MERGERS[p](upstream, mine)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=1, ensure_ascii=False,
                      sort_keys=(p != "editorial-log.json"))
            f.write("\n")
        size = len(merged) if isinstance(merged, (list, dict)) else 1
        print(f"merge_state: resolved {p} ({size} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
