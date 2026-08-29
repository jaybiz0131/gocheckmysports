"""Last-line duplicate sweep, run in the publish step AFTER the pre-push rebase.

WHY THIS EXISTS (2026-08-25): every autopilot guard judges against the corpus in the
run's checkout. The checkout is now the branch tip (ref: main), which with the shared
concurrency group closes the known race: a queued run judging an hour-stale corpus is
how one CIA-Moscow story published twice 83 minutes apart. This sweep is the layer that
does not care WHY a twin got this far. After the rebase merges whatever siblings landed
mid-run, it asks one question of every story this run is about to publish: does the
refreshed corpus already carry a story on this event that this one adds nothing to?
If so, the file is dropped before the commit, loudly.

The test is deliberately the narrow, measured one (the family duplicate audit,
2026-08-25, 121 confirmed URLs): same event AND zero novel claim tokens against the
published story's full covered signature. A follow-up carrying ANY new fact publishes
untouched; the owner's rule stands (adds anything = news; adds nothing = rehash).

Exit is always 0: hygiene must never kill a publish. A sweep crash publishes unswept
with a warning, which is exactly what yesterday's pipeline did every day.
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "site", "content")


def _new_content_files():
    """Story files this run adds relative to origin/main (post-rebase = our commits)."""
    try:
        # two-dot on purpose: a tree diff needs no merge-base, and the shallow
        # checkout (fetch-depth 1) often cannot produce one after origin advances
        out = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=A", "origin/main", "HEAD"],
            cwd=HERE, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return []
    return [os.path.join(HERE, p) for p in out.splitlines()
            if p.startswith("site/content/") and p.endswith(".json")]


def main():
    sys.path.insert(0, HERE)
    import dedupe

    new_files = _new_content_files()
    if not new_files:
        print("publish_sweep: no new stories in this run; nothing to sweep")
        return 0
    batch = {}
    for f in new_files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if d.get("example") or str(d.get("id") or "").startswith("wrap-"):
            continue
        if d.get("category") == "daily edition":
            continue
        batch[f] = d
    older = []
    batch_paths = {os.path.abspath(f) for f in batch}
    for f in glob.glob(os.path.join(CONTENT, "*.json")):
        if os.path.abspath(f) in batch_paths:
            continue
        try:
            older.append(json.load(open(f, encoding="utf-8")))
        except Exception:
            continue

    def _daygap(a, b):
        try:
            import datetime
            return abs((datetime.date.fromisoformat(str(a)[:10])
                        - datetime.date.fromisoformat(str(b)[:10])).days)
        except Exception:
            return 99

    dropped = []
    kept = []   # this batch's survivors, richest-first so the fuller twin wins
    by_slug = {o.get("slug"): o for o in older}
    for f, d in sorted(batch.items(),
                       key=lambda kv: -len(json.dumps(kv[1].get("body") or ""))):
        title = str(d.get("title") or "")
        kf = str(d.get("key_fact") or "")
        # TWO SIGNALS THAT NEED NO NOVELTY TEST AT ALL (owner report 2026-08-28). The
        # novelty bar below is zero-new-facts, and a twin that differs by ONE throwaway
        # token walks straight through it: the Seahawks sale published three times, and
        # the third copy's only novel claim token was "29". Raising the bar to one token
        # was measured against the live corpus and rejected, because it would also drop an
        # Infantino-erosion story against a private-equity retreat and a Kanter ejection
        # against his subsequent ban, which are different developments. These two are
        # exact instead of statistical, so they cost nothing in false drops:
        #
        # 1. A SLUG THAT ALREADY EXISTS. Two content files with one slug render to one
        #    URL, so the later silently overwrites the earlier at build and the feed emits
        #    the same GUID twice, which is a real syndication fault in RSS readers. This
        #    can never be legitimate, whatever the story says.
        # 2. A HEADLINE THAT IS WORD-FOR-WORD THE ONE ALREADY PUBLISHED. Every such pair
        #    in the live corpus is a true duplicate; a genuine follow-up writes a new
        #    headline, because it has something new to say in it.
        prior_slugs = {o.get("slug") for o in older if o.get("slug")} | \
                      {k.get("slug") for k in kept if k.get("slug")}
        if d.get("slug") in prior_slugs:
            dropped.append((f, d.get("slug"), "SLUG"))
            continue
        twin = next((o for o in older + kept
                     if dedupe._headline_overlap(title, str(o.get("title") or "")) >= 0.98
                     and _daygap(d.get("date"), o.get("date")) <= 1), None)
        if twin is not None:
            dropped.append((f, d.get("slug"), twin.get("slug")))
            continue
        rep_t, rep_s = dedupe.adds_nothing_new(title, kf, corpus=older + kept)
        if rep_t:
            # A DROP DELETES A VERIFIED STORY, so the bar is higher than the autopilot
            # hold (which only queues for review). adds_nothing_new's claim signature is
            # deliberately sparse - distinctive tokens only - so a genuine follow-up
            # whose news is in common nouns ("confirms prisoner-exchange agenda") can
            # look token-empty against a story whose body brushed the same words.
            # Measured on the 121-URL family audit: every confirmed twin ALSO shares
            # >=0.45 of its headline with its original and publishes within a day of
            # it, while the follow-up class sits far below (the Ratcliffe follow-up
            # probe scores 0.29). All three conditions or the story publishes.
            orig = by_slug.get(rep_s) or next(
                (k for k in kept if k.get("slug") == rep_s), {})
            close = _daygap(d.get("date"), orig.get("date")) <= 1
            overlap = dedupe._headline_overlap(title, str(orig.get("title") or rep_t))
            if close and overlap >= 0.45:
                dropped.append((f, d.get("slug"), rep_s))
                continue
        kept.append(d)

    for f, slug, rep in dropped:
        os.remove(f)
        if rep == "SLUG":
            # naming the same slug on both sides read as "retells itself" in the log
            print(f"::warning::publish_sweep dropped '{slug}': that URL is already "
                  f"published, and two files on one slug collide into a single page")
        else:
            print(f"::warning::publish_sweep dropped zero-novelty twin '{slug}' "
                  f"(retells published '{rep}'); the survivor already carries this event")
    if dropped:
        print(f"publish_sweep: dropped {len(dropped)} of {len(batch)} new stories as "
              f"exact retellings; re-run site_build before committing")
        # the caller rebuilds; signal via a marker file rather than exit code
        open(os.path.join(HERE, "out", "sweep_dropped"), "w").write(str(len(dropped)))
    else:
        print(f"publish_sweep: {len(batch)} new stories, no retellings")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:   # noqa: BLE001 - hygiene must never kill a publish
        print(f"::warning::publish_sweep crashed ({e}); publishing unswept")
        raise SystemExit(0)
