# GoCheckMySports: SPORTS_VERIFY.md

Verifiable claims for the GoCheckMySports pipeline. Human gate: the editor-in-chief
confirms each item before relying on it in production. Nothing here is deployed by the
build; publishing is the human's separate approved step.

Provenance: this desk was cloned from the family's crypto news desk chassis on 2026-07-19. The CV1-CV9
mechanics below were proven live on that chassis (session 2026-07-10); each check keeps its
ID and must be RE-VERIFIED against the sports sources and prompts before this desk's first
live publish. Status lines say which is which.

---

## Architecture (mirrors the GoCheckMyPet recall pipeline and the Storm pattern)

Scheduled ingest -> AI processing -> verified, human-gated output. Standard library only
(no third-party dependency), fail-closed everywhere, self-verifying. Six stages, one
orchestrator that runs Stages 1-5 and never publishes; Stage 6 is a separate human step.

---

## The checklist

**CV1 - Stage 1 aggregation runs against real feeds.** All configured sports feeds resolve
and parse: the ESPN league feeds, BBC Sport, CBS Sports, Guardian Sport, Yahoo Sports, plus
the official league data endpoints (MLB StatsAPI, NHL API, ESPN scoreboards). Raw items
window down and cluster as designed; a missing optional source is a documented skip, not a
failure. Status: mechanics proven on the chassis; re-verify live on the sports feeds.

**CV2 - Dedupe collapses cross-outlet duplicates.** Two near-identical headlines with
different URLs merge via headline-token Jaccard, and identical-URL copies merge by URL.
Canary asserts exactly 2 clusters from a 3-item set with one near-duplicate pair. Status:
verified on the chassis; canary must stay green on the sports fixture.

**CV3 - The deterministic hype belt works.** Obvious promotion and betting-pick content is
scored and rejected; borderline listicle content is flagged, not rejected; real
primary-source news scores 0, and a primary-tier item that merely uses a superlative is NOT
penalized (reputation dampening). Status: re-verify with the sports `shill_rules.json`
tells; the canary asserts the reject/clean pair.

**CV4 - Editor / verifier / writer wire end-to-end (offline replay).** aggregate -> editor
-> verifier -> writer -> digest runs over the fixture with NO API key and NO spend: the
editor splits ranked vs rejected; the verifier returns all three verdicts (VERIFIED /
NEEDS-HUMAN-REVIEW / REJECT); the writer drafts the draftable and drops the REJECT; every
draft is DRAFT-tagged with an empty `human_take` and the no-betting-advice disclaimer.
Status: re-verify on the sports fixture.

**CV5 - The verifier is independent and adversarial.** A separate API call with a distinct
prompt that live-fetches each cited source and confirms the claim's tokens are actually on
the page. Coverage is fail-closed: any story the verifier does not judge is forced to
NEEDS-HUMAN-REVIEW, never promoted. Editor confidence vs verifier verdict divergence is
surfaced in the digest for human eyes. Status: verified on the chassis (wiring + coverage
gate); exercise the adversarial fetch against live sports URLs before first publish.

**CV6 - The human gate is load-bearing and the publish path is fail-closed.** Must hold:
- No approval file -> publish does nothing.
- A replay-mode (test) approval -> publish refuses (`::error::`), publishes nothing.
- A `hold` story, or a story approved but not verified (REJECT) -> skipped.
- A NEEDS-HUMAN-REVIEW story approved WITHOUT a human take -> skipped (override needs the take).
- A live approval with `approve` + take + VERIFIED/REVIEW -> publishes (dry-run adapters;
  no real endpoint ships wired in v1).
Status: verified on the chassis (all gates exercised); unchanged code path.

**CV7 - No-key and budget fail-closed.** A live LLM call with `ANTHROPIC_API_KEY` unset
raises `LLMError` (the run fails, publishes nothing). The per-run token/USD budget raises
`BudgetError` before an over-cap call. Both are asserted by the canary. Status: verified on
the chassis; unchanged code path.

**CV8 - The canary is a real hard gate (fail-closed proven by tampering).** Adding
`temperature` to a model in config -> exit 1 (blocked). Weakening the hype belt so the
obvious promotion is not rejected -> exit 1 with a named `::error::`. Controls -> exit 0.
`verify_pipeline.py canary` blocks (exit 1) on any wiring/belt/gate drift; `sources`
(Layer 2) checks the configured feeds live and is notify-only (exit 3), never blocking.
Status: verified on the chassis; re-run both layers over the sports config.

**CV9 - Model/API correctness.** Calls `https://api.anthropic.com/v1/messages` with
`x-api-key` + `anthropic-version: 2023-06-01`. No `temperature`/`top_p`/`top_k` is sent
(those return HTTP 400 on the current model family); register and determinism are steered
by the prompt. Output is instructed-JSON, parsed defensively (first well-formed object
recovered even if the model wraps it); an unparseable response fails the stage closed.
Status: verified in code; a live key exercises the network path.

---

**CV10 - RETIRED with the crypto boards.** On the chassis this check covered the Whale
Watch flow-analysis board. The sports desk ships no market boards; the flow/pulse/chart
generator modules are removed along with their pages, nav links, and assets. The ID is
kept so the numbering stays comparable across the family's desks.

## Standing-rules compliance
- No em dashes in the copy or code (house style). Verify by scan.
- No-betting-advice discipline: report events, never advise bets, picks, or wagers;
  disclaimer on every draft and every published payload. Injuries only from official
  reports or on-record statements.
- Fail-closed everywhere; the human gate cannot be removed. No deploy performed by builds.
- Zero third-party dependencies (standard library only), matching the repo's offline,
  drag-and-drop, reproducible posture.
