# GoCheckMySports: DEVIATIONS.md

Places where the build diverged from, or must flag a tension in, its instructions.
House rule (inherited from the GoCheckMy family): surface tensions, do not resolve them silently.

---

## Provenance

This repo was cloned from the family's crypto news desk chassis on 2026-07-19 and
adapted into the GoCheckMySports daily sports news desk. The crypto desk's own deviation
history stays with that repo; it documents that desk's decisions, not this one's. Chassis
facts that still matter here live in the adapted docs (README.md, CHARTER.md,
SPORTS_VERIFY.md, LAUNCH_CHECKLIST.md), not re-listed as deviations.

Removed at cloning: the crypto-only boards (Whale Watch, Market Pulse, The Chart Master),
their generator modules, pages, nav links, live-markets ticker, and assets. Kept: the full
fail-closed pipeline, the verdict-badge honesty UI, the trusted-newsroom design system
(masthead rule retinted to varsity field green), and the human gate.

## Deviations

### D1 (2026-07-20): the build clock, scoped

House rule: "dateline reflects the newest content, never a wall clock." The daypart
front (home_stack in site_build.py) reads the build-time UTC clock to pick the hero
lead, decay the Breaking badge (3 hours), and anchor The Bottom Line to the current
slot's edition. The clock decides STACKING ONLY; every rendered dateline stays
content-derived. SITE_BUILD_NOW pins the clock for deterministic replays. Tension
surfaced here rather than resolved silently: a static page can present a stale stack
between builds, and the accepted bound is the existing rebuild rhythm (slot publishes,
breaking runs, the 12:00 UTC refresh); no extra builds were added to tighten it.

Also 2026-07-20: the live-scores strip (scores_pulse.py -> site/data/scores.json)
reuses the chassis ticker CSS removed at cloning. League data, not news: it bypasses
the editorial pipeline by design and the strip labels it as such.


### D2 (2026-09-02): the edition floor

THE EDITION FLOOR (family audit 2026-09-02). House rule: fail-closed everywhere, and
the edition failed closed to SILENCE: when the synthesis could not clear its trace check
after a Haiku attempt and a Sonnet rescue, the slot published nothing, the run went red,
the watcher re-fired the whole story pipeline every 30 minutes until the window closed,
and the tracker filed one issue per failed slot (40+ across the three desks in the week of
Aug 25 to Sep 2). The run logs showed the checker withdrawing its own objections in its
reasoning ("this is supported paraphrase", "permitted under connecting and synthesizing")
while the slot died anyway.

The tension: the edition is the GUARANTEED product (never a zero-content slot) and it is
also gated fail-closed. Both cannot hold when the gate is wrong. Resolution, surfaced here
rather than silently: the gate keeps its teeth on the SYNTHESIS, and what publishes when
the synthesis fails is text that cannot invent anything. The order is now synthesis ->
deterministic sentence cuts of exactly what the checker flagged (the story-is-not-the-
sentence doctrine of 2026-08-21, applied to the edition) -> the Sonnet rescue -> cuts
again -> a plain DIGEST built only from the desk's own published, verified stories
(edition_repair.py; config edition.fallback_digest, default true). A digest slot is
labeled as a digest in its dek, logged as a ::warning::, recorded in out/wrap-status.json
and the ops ledger (wrap: digest), and the rejected synthesis is kept in
out/wrap-rejected.json on the run artifact. The checker also now states, per item and
after its reasoning, whether the item stands; a withdrawn item is dropped before any
word list. Set fallback_digest to false to restore fail-closed-to-silence.

Same audit, same family-wide changes: the offline canary's deliberate negative tests no
longer post ::error:: annotations on every run (stop-commands around the step); a writer
refusal returned as a draft is a sourcing failure, not a kill; VERIFIED stories draft
before NEEDS-HUMAN-REVIEW ones; article fetches are polite per host, retry on 429/5xx,
and read __NEXT_DATA__ prose; the feed text rides along whenever the pages read thin;
the API retry ladder waits 45 seconds instead of 14; and a served slot closes the
"Edition stage failed" / "Edition gap" / "Missed edition" flags.
