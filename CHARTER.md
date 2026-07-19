# Crypto Cronkite: the News Desk charter

This desk is Desk 1 of the GoCheckMy two-desk charter (2026-07-15). The family master
charter, including the reference desk and the six per-site mission briefs, lives in the
gcm-newsroom repo's CHARTER.md; this file is this desk's operating half.

Mission: report what actually happened in crypto, stripped of shill, for a reader who is
lied to all day. Speed matters; accuracy outranks it. A held story costs a slot, a wrong
one costs the brand. Fail-closed everywhere: nothing wrong ships to make a deadline.

THE FOUR STAGES
1. RESEARCHER: feed aggregation (16 tiered RSS sources, deduplicated into clusters) plus
   the breaking-news watcher (deterministic thresholds, no model). Draftable stories get
   a structured research brief built from the FULL fetched source pages: data points
   with per-claim confidence labels (verified-on-chain / reported / announced-not-
   verified / unconfirmed), a deliberately-pulled bear case, open questions.
2. VERIFIER-EDITOR: the editor ranks and de-shills over the deterministic shill belt,
   with the desk's last-48h published titles in view (the librarian's shelf: repeats
   rank only as genuine updates). An independent adversarial verifier live-fetches
   every cited source and issues VERIFIED / NEEDS-HUMAN-REVIEW / REJECT. BREAKING-AS-
   FACT needs two INDEPENDENT sources; wire rewrites are not independence;
   single-source breaking publishes only labeled unconfirmed, or holds a slot.
3. WRITER: the Cronkite voice: straight, sourced, no hype, no advice, epistemics in the
   prose, the take slot always empty for a human. Brief-bound: no fact outside the
   brief. Across the day's three slots, update and extend, never repeat.
4. GATE: ten deterministic classes (source liveness, dedup/rerun, compliance lint,
   persona/credential, em-dash, depth, template completeness, NFA, approver sign-off,
   breaking two-source), the post-draft approver tracing every fact to its brief, and
   the categorized editorial log.

CADENCE: The Morning Brief 10:40 UTC, The Afternoon Brief 17:08, The Evening Brief 23:08 (Eastern
audience clock); watcher-triggered breaking runs; slot recovery on cron drift; contract
ladder on small-model output; monthly aging review WITH the correction loop
(corrections.py: premise-flagged stories re-run through research -> write -> approve and
update in place only with the approver's signature, stamped with a correction note).

THE BOTTOM LINE (2026-07-15): each edition closes with the desk's signature 3-5
sentence read: synthesis of what happened and why it mattered, never price
direction, never setup language, never advice, never causation beyond sources.
It renders in its own band at the top of the homepage and the news desk, refreshed
every slot (breaking runs regenerate the current slot's edition), archived forever
at /bottom-line.html, and guarded by its own deterministic directional-language
gate on top of the prompt lane.

The reader-facing version of this charter is the site's method page.
