# Crypto Cronkite: CRYPTO_VERIFY.md

Verifiable claims for the Crypto Cronkite pipeline (session 2026-07-10). Human gate: the
editor-in-chief confirms each item before relying on it in production. Nothing here was
deployed; this is a build, and publishing is the human's separate approved step.

---

## Architecture (mirrors the GoCheckMyPet recall pipeline and the Storm pattern)

Scheduled ingest -> AI processing -> verified, human-gated output. Standard library only
(no third-party dependency), fail-closed everywhere, self-verifying. Six stages, one
orchestrator that runs Stages 1-5 and never publishes; Stage 6 is a separate human step.

---

## What was proven live (2026-07-10)

**CV1 - Stage 1 aggregation runs against real feeds.** All 8 configured RSS feeds resolved
HTTP 200 and parsed: SEC (25), CFTC (10), CoinDesk (25), The Block (19), Decrypt (37), DL
News (40), Bitcoin Magazine (10), Cointelegraph (30). 196 raw items -> 98 within the 30h
window -> 97 clusters. CryptoPanic correctly skipped (no token; documented, not a failure).
Status: verified live.

**CV2 - Dedupe collapses cross-outlet duplicates.** Over the fixture, two near-identical SEC
headlines with different URLs merged via headline-token Jaccard, and identical-URL copies
merged by URL, producing the expected 5 clusters from 6 distinct stories. Canary asserts
exactly 2 clusters from a 3-item set with one near-duplicate pair. Status: verified.

**CV3 - The deterministic shill belt works.** The moon post
("PEPECOIN to $10 imminent, get in early ... sponsored presale ... 100x moon") scores 9 and
is `shill_rejected`; the affiliate listicle scores 4 (flagged, not rejected); real
primary-source news scores 0. A primary-source item that merely uses a superlative is NOT
penalized (reputation dampening). Canary asserts moon=rejected, primary-source=clean.
Status: verified.

**CV4 - Editor / verifier / writer wire end-to-end (offline replay).** aggregate -> editor ->
verifier -> writer -> digest ran over the fixture with NO API key and NO spend: editor split
3 ranked / 2 shill-rejected; verifier returned all three verdicts (VERIFIED /
NEEDS-HUMAN-REVIEW / REJECT); writer drafted the 2 draftable (VERIFIED + REVIEW) and dropped
the REJECT; every draft is DRAFT-tagged with an empty `human_take` and the not-financial-advice
disclaimer. Status: verified.

**CV5 - The verifier is independent and adversarial.** A separate API call with a distinct
prompt that live-fetches each cited source and confirms the claim's tokens are actually on the
page (same live-source discipline as the Pet curated-recall verifier). Coverage is fail-closed:
any story the verifier does not judge is forced to NEEDS-HUMAN-REVIEW, never promoted. Editor
confidence vs verifier verdict divergence is surfaced in the digest for human eyes. Status:
verified (wiring + coverage gate); adversarial fetch exercised against live URLs in Stage 3.

**CV6 - The human gate is load-bearing and the publish path is fail-closed.** Proven:
- No approval file -> publish does nothing.
- A replay-mode (test) approval -> publish refuses (`::error::`), publishes nothing.
- A `hold` story, or a story approved but not verified (REJECT) -> skipped.
- A NEEDS-HUMAN-REVIEW story approved WITHOUT a human take -> skipped (override needs the take).
- A live approval with `approve` + take + VERIFIED/REVIEW -> 2 stories published (dry-run
  adapters; no real endpoint ships wired in v1).
Status: verified (all gates exercised).

**CV7 - No-key and budget fail-closed.** A live LLM call with `ANTHROPIC_API_KEY` unset raises
`LLMError` (the run fails, publishes nothing). The per-run token/USD budget raises `BudgetError`
before an over-cap call. Both are asserted by the canary. Status: verified.

**CV8 - The canary is a real hard gate (fail-closed proven by tampering).**
- Adding `temperature` to a model in config -> exit 1 (blocked). Control -> exit 0.
- Raising the shill reject threshold so the moon post is not rejected -> exit 1 with a named
  `::error::`. Control -> exit 0.
`verify_pipeline.py canary` blocks (exit 1) on any wiring/belt/gate drift; `sources` (Layer 2)
checked all 8 feeds live (HTTP 200 + feed-shaped) and is notify-only (exit 3), never blocking.
Status: verified live.

**CV9 - Model/API correctness.** Calls `https://api.anthropic.com/v1/messages` with
`x-api-key` + `anthropic-version: 2023-06-01`. Default model `claude-opus-4-8`. No
`temperature`/`top_p`/`top_k` is sent (those return HTTP 400 on the current model family);
register and determinism are steered by the prompt. Output is instructed-JSON, parsed
defensively (first well-formed object recovered even if the model wraps it); an unparseable
response fails the stage closed. Status: verified in code (offline); a live key exercises the
network path.

---

**CV10 - Whale Watch flow analysis is honest and locked.** `whale_flows.py` classifies large
transfers as exchange inflow (potential sell pressure) vs outflow (accumulation) and, crucially,
scores stablecoins SEPARATELY as incoming buying power (a stablecoin onto an exchange is the
opposite signal from BTC onto an exchange, so lumping them would mislead). Over the sample
transactions the canary asserts: 10 of 12 count (exchange-to-exchange and wallet-to-wallet
excluded), volatile net = +$35M off exchanges, stablecoin buying power = $200M, BTC net negative
(onto exchanges), and no stablecoin leaks into the volatile chart. The site renders it as a
diverging bar chart with triple polarity encoding (side of zero + sign in the label + color, not
color alone), labelled market-data-not-news, with the heuristic caveats shown. Ships an EXAMPLE
snapshot (clearly ribboned) until a Whale Alert key is connected. Status: verified (classification
canary + rendered board).

## Standing-rules compliance
- No em dashes in the new copy or code (house style). Verified by scan.
- Not-financial-advice discipline: report events, never advise trades; disclaimer on every
  draft and every published payload.
- Fail-closed everywhere; the human gate cannot be removed. No deploy performed.
- Zero third-party dependencies (standard library only), matching the repo's offline,
  drag-and-drop, reproducible posture.
