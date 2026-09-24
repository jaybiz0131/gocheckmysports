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

# U-11 (24 September 2026). A COMMIT THAT CHANGES NOTHING IN THE PUBLISHED TREE DOES NOT
# BUILD THE SITE. The Pet and Parents desks each found handoff commits in their production
# deploy lists, three builds apiece in one week with no site change behind them, and this
# desk spent two on 22 September writing standing rules into HANDOFF.md.
#
# The list is a WHITELIST OF THINGS THAT CANNOT REACH THE SITE, not a guess. Every entry
# was checked against the build: `command` in netlify.toml runs scores_pulse.py then
# site_build.py, and neither reads a markdown file or anything under docs/. A path is added
# here only after that check, because the cost of a wrong entry is a missed build, which is
# the failure this file must not cause.
DOC_PREFIXES = ("docs/", "shots/", "claims-reports/", "audit-report/")
DOC_SUFFIXES = (".md",)
# NOT the .md files: DOC_SUFFIXES already covers every one of them, and naming HANDOFF.md
# here too was config that could not fail. The first U-9 break on this file removed it from
# this tuple and the gate stayed green, which is how it was found.
DOC_FILES = ("netlify_ignore.py", ".gitignore")


def is_doc(p):
    """True when a path cannot change a single pixel of the published site.

    site_build.py is deliberately NOT here: it is the generator, and a change to it is the
    most site-changing commit there is.
    """
    if p in DOC_FILES or p.startswith(DOC_PREFIXES):
        return True
    # A markdown file anywhere, EXCEPT under the published tree, where one could be served.
    return p.endswith(DOC_SUFFIXES) and not p.startswith("site/")


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
                   if not (p.startswith(SKIPPABLE_PREFIXES) or p in SKIPPABLE_FILES
                           or is_doc(p))]
    if unskippable:
        return False, f"{len(unskippable)} file(s) that change the site, e.g. {unskippable[0]}"
    if all(is_doc(p) for p in paths):
        return True, (f"{len(paths)} file(s), all outside the published tree "
                      f"(U-11), e.g. {paths[0]}")
    # AN INACTIVES SNAPSHOT NEVER BUILDS THE SITE, in a window or out of one.
    #
    # This used to build inside a posting window on the grounds that the board IS the
    # product there, and it is, but the cost was not visible from this file: the poller
    # runs every 15 minutes across nine hours on a Sunday and every 20 minutes on four
    # other nights, and every one of those pushes was a production deploy. 1,188 deploys
    # in the 23 Aug to 22 Sep period at 15 credits each is 17,820 of the team's 15,000,
    # and at about 2 PM on 21 September Netlify paused every site on the team.
    #
    # The rule that replaces it: a deploy changes what the site SAYS; a number changing
    # is not a deploy. The snapshot still lands every 15 minutes, and the board still
    # shows it within one poll, because the page fetches the committed JSON itself.
    # Freshness is unchanged and the builds behind it are gone.
    return True, f"{len(paths)} file(s), none of which change the site"


if __name__ == "__main__":
    try:
        skip, why = decide(changed_files())
    except Exception as exc:          # never skip because this file broke
        print(f"netlify ignore: erred ({exc}); building")
        sys.exit(1)
    print(f"netlify ignore: {'SKIP' if skip else 'BUILD'} - {why}")
    sys.exit(0 if skip else 1)
