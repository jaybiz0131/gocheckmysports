#!/usr/bin/env python3
"""netlify_ignore.py: PROGRAM 4, T-3. Decide whether a push deserves a build.

Netlify's contract: exit 0 = SKIP the build, exit 1 = BUILD. The default is to build,
and every unclear case here resolves to building. A missed build shows a reader stale
numbers; a skipped build that should have run is the failure this file must not cause,
so it errs toward spending.

What it skips: a push that touches nothing but inactives snapshots outside the posting
windows, and a push that touches nothing but the ops ledger. Those are the two kinds of
commit that change no pixel on the site.

Why the windows matter: inside a posting window an inactives snapshot IS the product
(M-3 wants a posted list on the page within a minute), so it always builds. Outside
them the poller is writing snapshots nobody is reading yet; the evening Edition's own
push will carry them.
"""
import datetime
import os
import subprocess
import sys

# The inactives poller's own windows, in UTC, from .github/workflows/inactives.yml.
# (weekday set, first hour, last hour) with Monday = 0.
WINDOWS = [
    ({6}, 15, 23),          # Sunday slate, through the night game
    ({0, 1, 4, 5}, 0, 4),   # night games after UTC midnight
    ({0, 3, 4}, 22, 23),    # Mon/Thu/Fri night lists
    ({5}, 16, 23),          # Saturday slate
]

SKIPPABLE_PREFIXES = ("site/data/inactives/",)
SKIPPABLE_FILES = ("ledger.json",)


def in_posting_window(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    for days, lo, hi in WINDOWS:
        if now.weekday() in days and lo <= now.hour <= hi:
            return True
    return False


def changed_files():
    """Paths changed since the last built commit, or None when that cannot be known."""
    base = os.environ.get("CACHED_COMMIT_REF")
    head = os.environ.get("COMMIT_REF") or "HEAD"
    if not base:
        return None
    r = subprocess.run(["git", "diff", "--name-only", base, head],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [p for p in r.stdout.splitlines() if p.strip()]


def decide(paths, now=None):
    """(skip, reason). Pure, so the test below is the whole proof."""
    if paths is None:
        return False, "cannot diff against the last built commit; building"
    if not paths:
        # THE ONE CASE THIS FILE GOT EXACTLY BACKWARDS, and it cost the board.
        #
        # A build with no changed files is not a pointless build: it is a SCHEDULED or
        # HOOK-TRIGGERED one, and those exist precisely to re-fetch. This desk's build
        # command runs scores_pulse.py before site_build.py, and site_build itself
        # refreshes the scoreboard, the standings, the schedules and the line log at
        # build time. Every number on the board comes from the BUILD, not the commit.
        #
        # So A-1 added build hooks to unfreeze the morning board, and every hook ping
        # that arrived with no new commit was declined right here. The hooks fired on
        # time and the board did not move: at checkpoint 4 on 20 September the masthead
        # read 7:48 PM at 9:16 PM while the live poll showed scores seconds old.
        #
        # This is what the docstring above already asks for: a skipped build that should
        # have run is the failure this file must not cause.
        return False, "no files changed, so this is a scheduled or hook build; the " \
                      "board refetches at build time and that is the point of it"
    unskippable = [p for p in paths
                   if not (p.startswith(SKIPPABLE_PREFIXES) or p in SKIPPABLE_FILES)]
    if unskippable:
        return False, f"{len(unskippable)} file(s) that change the site, e.g. {unskippable[0]}"
    if any(p.startswith(SKIPPABLE_PREFIXES) for p in paths) and in_posting_window(now):
        return False, "inactives changed inside a posting window; the board is the product"
    return True, f"{len(paths)} file(s), none of which change the site"


if __name__ == "__main__":
    try:
        skip, why = decide(changed_files())
    except Exception as exc:          # never skip because this file broke
        print(f"netlify ignore: erred ({exc}); building")
        sys.exit(1)
    print(f"netlify ignore: {'SKIP' if skip else 'BUILD'} - {why}")
    sys.exit(0 if skip else 1)
