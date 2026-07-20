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
