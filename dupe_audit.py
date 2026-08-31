#!/usr/bin/env python3
"""
dupe_audit.py: has the desk told the same story twice? Ask the corpus, not the calendar.

WHY THIS EXISTS
  The dedupe guard in dedupe.py stops a duplicate at publish time. It says nothing about the
  ones already on the site, so the desk still needs a way to ask "what did we let through
  before the guard existed, or while it was misconfigured?".

  The throwaway scan that question was first answered with compared stories PUBLISHED ON THE
  SAME DAY. It reported the CFTC/Kalshi cluster as five articles. An outside audit reported
  six, and the audit was right: the sixth published the following day. One day of vision is
  not an approximation of the answer, it is a different question, and it happened to be the
  wrong one.

  So this uses the guard's own window, the guard's own matcher, and the guard's own novelty
  threshold, over the whole corpus rather than one day of it.

WHAT IT REPORTS, and why it is a COUNT and not a verdict
  Pairs where the matcher says "same event" AND the later story added fewer than
  dedupe.NOVELTY_MIN new facts, ranked by how little it added. Zero means the desk said the
  same thing twice.

  Filtering on the guard's own tri-state was tried and does not work here, in both
  directions. The tri-state is tuned for the PUBLISH decision, where calling a genuine
  follow-up a duplicate silently loses reporting, so it leans toward "update": filtering on
  "rehash" found 1 of the 6 CFTC copies. Accepting "update" as well reported 37 pairs,
  including a Kalshi lawsuit matched to an XRP phishing drain. The novelty count is the
  number underneath both verdicts, and it is the thing an editor can actually judge.

  Each pair carries a suggested canonical: the most complete and best-sourced copy, which is
  the owner's rule, never the timestamp. It suggests; it never edits. Merging is an editorial
  act, it loses a URL, and it needs a human to diff the copies first.

WHAT IT DELIBERATELY DOES NOT FLAG
  - Editions (wrap-*): a daily edition summarises the day's stories. That is its job.
  - A story already linked to another by update_of: a declared follow-up is not a duplicate.
    (But a declared follow-up whose headline nearly repeats its origin's is listed
    separately as a chained retelling, because that link is also where a retelling
    mis-filed as a development hides from this scan.)
  - Anything already retired into a canonical (site_build.RETIRED_ARTICLES), because a merged
    duplicate would otherwise be reported forever.

ADVISORY, NEVER A GATE. Exits 0 whatever it finds. Whether two stories about one event are
a duplicate or a legitimate development is a judgment, and a check that could block a
publish over it would cost more than it saves.

USAGE  python3 dupe_audit.py [--within-days N] [--quiet]
"""

import glob
import json
import os
import sys

import common
import dedupe

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "site", "content")

WITHIN_DAYS = 21  # the guard's own window; see dedupe.classify_published


def _load(content=None):
    out = []
    for p in sorted(glob.glob(os.path.join(content or CONTENT, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("example") or str(d.get("id") or "").startswith("wrap-"):
            continue
        out.append(d)
    out.sort(key=lambda d: (d.get("published_utc") or d.get("date") or ""))
    return out


def _retired():
    try:
        import site_build
        return set(site_build.RETIRED_ARTICLES)
    except Exception:
        return set()


def _completeness(d):
    """The owner's canonical rule, in the order it was stated: completeness and sourcing,
    never timestamp. Sources first because a two-outlet story outranks a longer single-source
    one, then body length as the tiebreak."""
    body = d.get("body") or []
    return (len(d.get("sources") or []),
            sum(len(str(b).split()) for b in body))


def clusters(items=None, within_days=WITHIN_DAYS):
    """Groups of published stories the guard's matcher considers one event."""
    items = items if items is not None else _load()
    retired = _retired()
    # is_coverage() is the guard's own preview filter and it is load-bearing here. Without
    # it the Week Ahead, which previews a dozen unrelated topics in one story, matches most
    # of the corpus and becomes a hub.
    items = [d for d in items
             if d.get("slug") not in retired and dedupe.is_coverage(d)]

    # ASK THE GUARD, DO NOT REIMPLEMENT IT. Two earlier versions of this function got the
    # same thing wrong in different ways, and both were wrong for one reason: they treated
    # dedupe.same_event() as a duplicate verdict. It is not. It is the guard's CANDIDATE
    # filter, deliberately loose, and classify_published() is what decides between rehash,
    # update and new by measuring novelty against everything already covered. Used alone it
    # paired "New York sues Kalshi" with a fake-staking XRP drain, because a loose matcher
    # asked a question nobody wanted the answer to.
    #
    # So this replays the guard: walk the corpus oldest-first and ask, for each story, what
    # classify_published() would have said against everything published before it. A story
    # that comes back "rehash" is one the desk told twice, by the desk's own definition, and
    # that definition is the one the publish gate enforces today. An audit that disagrees
    # with the live gate is just a second opinion nobody asked for.
    out = []
    for i, story in enumerate(items):
        best = None
        for origin in items[:i]:
            if origin.get("update_of") == story.get("slug") or \
                    story.get("update_of") == origin.get("slug"):
                continue
            da, db = (origin.get("date") or ""), (story.get("date") or "")
            if not (da and db) or abs(_days(da) - _days(db)) > within_days:
                continue
            if not dedupe.same_event(origin.get("title", ""), origin.get("key_fact", ""),
                                     story.get("title", ""), story.get("key_fact", "")):
                continue
            # MEASURE, DO NOT CLASSIFY. The guard's tri-state is tuned for the publish
            # decision, where calling a real follow-up a duplicate silently loses reporting,
            # so it leans toward "update". Filtering an audit on "rehash" found 1 of the 6
            # CFTC copies; accepting "update" too reported 37 pairs including a Kalshi
            # lawsuit matched to an XRP phishing drain. Neither is the question.
            #
            # The question is how much this story added, so that is what gets reported: the
            # count of claim tokens not already covered by the earlier story. Zero means the
            # desk said the same thing twice. The threshold is the guard's own NOVELTY_MIN,
            # which is the line the live gate already draws between a retelling and a
            # development, and the count is printed so the editor can see how close it sat.
            # BOTH DIRECTIONS, OR THE AUDIT IS BLIND TO HALF THE CLASS (family audit
            # 2026-08-31). Forward novelty alone misses the superset retelling: the
            # newcomer covers everything the origin said and pads a token or two, so fwd
            # clears NOVELTY_MIN while rev sits at zero. The live Deribit pair scored
            # fwd 2, rev 0 and never appeared in this report. So the measure is
            # min(fwd, rev), and a direction only speaks when its claim signature
            # actually exists (dedupe's own 2026-08-21 no-signature-no-verdict rule:
            # an empty signature makes its count zero vacuously).
            sig_story = dedupe._claim_signature(story) - dedupe._OUTLETS
            sig_origin = dedupe._claim_signature(origin) - dedupe._OUTLETS
            directions = []
            if sig_story:
                directions.append(
                    ("fwd", sorted(sig_story - dedupe._covered_signature(origin))))
            if sig_origin:
                directions.append(
                    ("rev", sorted(sig_origin - dedupe._covered_signature(story))))
            if not directions:
                continue
            direction, novel = min(directions, key=lambda d: len(d[1]))
            if best is None or len(novel) < best[0]:
                best = (len(novel), origin, novel, direction)
        if best is None or best[0] >= dedupe.NOVELTY_MIN:
            continue
        out.append({"novel": best[0], "novel_tokens": best[2], "direction": best[3],
                    "stories": sorted([best[1], story], key=_completeness, reverse=True)})
    out.sort(key=lambda g: (g["novel"], g["stories"][0].get("date") or ""))
    return out


def chained_retellings(items=None, overlap_min=0.7):
    """update_of-linked pairs whose headlines agree so strongly the declared follow-up
    reads as the same story told again.

    The duplicate scan above exempts a chained pair on purpose: a declared development is
    not a duplicate. That exemption is also where a retelling MIS-FILED as a development
    hides, and it hid three of them across the family desks (the news Ratcliffe same-day
    pair among them). A follow-up that keeps nearly the whole headline is asserting the
    same subject and the same event in the desk's own words, so it gets its own advisory
    list for the editor. Overlap 0.7, not the merge gate's 0.45: a chain was declared by
    someone, so only near-repetition earns a second look."""
    items = items if items is not None else _load()
    retired = _retired()
    items = [d for d in items
             if d.get("slug") not in retired and dedupe.is_coverage(d)]
    by_slug = {d.get("slug"): d for d in items}
    out = []
    for story in items:
        origin = by_slug.get(story.get("update_of") or "")
        if not origin:
            continue
        hov = dedupe._headline_overlap(origin.get("title") or "",
                                       story.get("title") or "")
        if hov >= overlap_min:
            out.append({"overlap": hov, "origin": origin, "story": story})
    out.sort(key=lambda g: -g["overlap"])
    return out


def _days(date_str):
    import datetime
    try:
        return datetime.date.fromisoformat(date_str[:10]).toordinal()
    except ValueError:
        return 0


def main():
    argv = sys.argv[1:]
    within = (int(argv[argv.index("--within-days") + 1])
              if "--within-days" in argv else WITHIN_DAYS)
    found = clusters(within_days=within)
    chained = chained_retellings()
    total = len(_load())
    if not found:
        print(f"dupe_audit: no duplicate clusters across {total} published stories "
              f"(window {within} days, cross-day).")
    else:
        extra = sum(len(g["stories"]) - 1 for g in found)
        exact = sum(1 for g in found if g["novel"] == 0)
        common.gh("warning",
                  f"dupe_audit: {len(found)} cluster(s) covering {extra} redundant "
                  f"stor{'y' if extra == 1 else 'ies'} of {total}. {exact} added NOTHING new; the "
                  f"rest added fewer than {dedupe.NOVELTY_MIN} new facts. Advisory: the "
                  f"editor decides whether each is a duplicate or a development.")
        for g in found:
            pairing = g["stories"]
            # fwd: the later story added this little; rev: the earlier story holds this
            # little the later one does not cover (a superset retelling)
            side = "later adds" if g["direction"] == "fwd" else "origin keeps only"
            print(f"\n  {pairing[0].get('date')}  [{side} {g['novel']} fact(s)"
                  f"{': ' + ', '.join(g['novel_tokens']) if g['novel_tokens'] else ''}]"
                  f"  suggested canonical first:")
            for i, d in enumerate(pairing):
                srcs, words = _completeness(d)
                print(f"    {'CANON' if i == 0 else '     '} {d.get('slug', '')[:70]}")
                print(f"          {words}w, {srcs} source(s), {d.get('published_utc') or d.get('date')}")
    if chained:
        print(f"\nCHAINED RETELLINGS (advisory): {len(chained)} update_of-linked pair(s) "
              f"with headline overlap >= 0.7; a declared follow-up this similar is "
              f"usually the same story told again:")
        for g in chained:
            print(f"    {g['overlap']:.2f}  {g['story'].get('slug', '')[:70]}")
            print(f"          retells {g['origin'].get('slug', '')[:70]}")
    if found:
        extra = sum(len(g["stories"]) - 1 for g in found)
        print(f"\ndupe_audit: {len(found)} cluster(s), {extra} redundant "
              f"(advisory; nothing changed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
