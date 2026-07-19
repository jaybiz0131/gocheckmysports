# GoCheckMyCrypto: the Crypto Cronkite news desk

This is the source of an automated crypto news desk, live at
[gocheckmycrypto.com](https://gocheckmycrypto.com). Many sources are aggregated and
deduplicated; an editor model ranks and strips shill; an independent verifier fetches every
cited source page and audits the claim; a researcher builds a structured fact brief; a
writer drafts only from that brief; a post-draft approver traces every fact back to it, and
a battery of deterministic fail-closed gates (source liveness, dedup, compliance lint,
depth, a two-source rule on breaking news) decides what publishes. If any stage fails, the
desk publishes nothing. Opinion never ships in a human voice unless a human wrote it, and
nothing here is financial advice. The full editorial mechanics are described publicly at
[gocheckmycrypto.com/method.html](https://gocheckmycrypto.com/method.html). Contact:
desk@gocheckmycrypto.com. Plus
Whale Watch, the follow-the-money on-chain board.

Built on the same architecture as its GoCheckMy sibling's recall pipeline (GoCheckMyPet) and
the Storm NFIP pattern: scheduled ingest, AI processing, verified and gated output. Standard
library only, fail-closed everywhere, self-verifying. Migrated to its own repo with history
preserved (see DEVIATIONS.md D1).

## The one non-negotiable rule

**The AI is the newsroom staff. The human is the editor-in-chief and the on-air voice.**
Publication is gated by the independent adversarial verifier: VERIFIED stories auto-publish
(the owner's standing full-auto instruction, 2026-07-11, implemented in `autopilot.py`),
NEEDS-HUMAN-REVIEW waits in the queue for the human, REJECT never ships. The human
editor-in-chief oversees the desk, can overrule any call in either direction, and owns
everything in a human voice: no "take" is ever machine-written. The automation removes the
grunt work (reading, triage, fact-check, drafting), never the judgment or the voice, and the
public method/standards pages describe this gate exactly as it runs.

## The stages

| Stage | Script | What it does | Output (in `out/`) |
|-------|--------|--------------|--------------------|
| 1 Aggregate | `aggregate.py` | Pull RSS (official/primary + macro + major outlets; CryptoPanic if `CRYPTOPANIC_TOKEN` set), normalize, keyword-gate the broad official feeds, tag clusters that match the ongoing-narratives watchlist (`config.json -> narratives`), dedupe near-identical stories into clusters, run the deterministic shill pre-pass | `items.json` |
| 2 Editor | `editor.py` | Managing-editor AI ranks the top stories by genuine significance and strips shill, showing its work | `editor.json` |
| 3 Verifier | `verifier.py` | A SEPARATE, adversarial AI live-fetches each cited source and audits the editor: VERIFIED / NEEDS-HUMAN-REVIEW / REJECT, with reasons and editor-divergence | `verifier.json` |
| 4 Writer | `writer.py` | Drafts the surviving stories into a script skeleton + article draft, DRAFT-tagged, neutral on price, not-financial-advice, with an empty human-take slot | `drafts.json` |
| 5 Digest | `digest.py` | Builds the human review queue (Markdown + HTML) and an approval template | `review_queue/<date>.md`, `.html`, `approval_template.json` |
| 6 Publish | `publish.py` | Fail-closed, approval-gated auto-push. Publishes ONLY stories a human approved AND the verifier cleared. Push targets are dry-run adapters until an operator wires a real endpoint | `published/`, `publish_report.json` |

`run.py` orchestrates Stages 1-5 (fail-closed) and **never** publishes. Stage 6 is a separate,
deliberate, human step.

## Running it

```sh
# Full offline wiring test - no API key, no network for the AI stages, no spend:
python3 run.py --mode replay --fixture fixtures/sample_feed.xml

# Live daily brief (needs ANTHROPIC_API_KEY; optional CRYPTOPANIC_TOKEN):
export ANTHROPIC_API_KEY=sk-ant-...
python3 run.py --mode live
#  -> read out/review_queue/<date>.md
#  -> copy approval_template.json to approval.json, set stories you sign off to "approve",
#     add your take, then:
python3 publish.py
```

## Fail-closed posture (STAGE 0 of the blueprint)

- No `ANTHROPIC_API_KEY` -> the LLM call raises, the run reports failed, nothing publishes.
- Per-run token/USD budget cap (`config.json`) -> a call that would exceed it raises first.
- Any stage error -> `run.py` writes `status: failed` and exits non-zero (CI flags a human).
- A story publishes only if: a human set it to `approve`, the verifier said VERIFIED (or
  NEEDS-HUMAN-REVIEW **with** a human take as an override), and the run is `live` (a replay
  test run can never publish). REJECT is never publishable.
- Push targets ship as dry-run adapters; a real send requires an operator to add the endpoint,
  credential, and send implementation deliberately.

## Verify

`verify_pipeline.py` mirrors the GoCheckMyPet recall verifier's two layers:

```sh
python3 verify_pipeline.py canary    # Layer 1: offline HARD GATE (blocks)
python3 verify_pipeline.py sources   # Layer 2: live feed check (notify-only)
```

Layer 1 proves the pipeline is wired, the shill/dedupe belts work, the offline replay runs
end-to-end to a DRAFT-tagged review queue, and every fail-closed gate holds. Layer 2 checks
the configured RSS feeds still resolve. Wired to `.github/workflows/verify-crypto-pipeline.yml`.

## Configuration

- `config.json` - sources and tiers, cadence, top-N, budget cap, per-stage model, publish gates.
- `shill_rules.json` - deterministic shill tells and source reputation (the living tune-list).
- `prompts/` - the editor / verifier / writer system prompts (your editorial judgment, once).

## Cost control

The editor/verifier/writer calls are capped by `config.json -> budget` (tokens and USD;
hard fail-closed ceilings). No `temperature`/`top_p`/`top_k` is sent (rejected by the
current model family); register and determinism are steered by the prompts. The lineup is
quality-first (see DEVIATIONS D3): `claude-fable-5` on the editor and verifier (the
judgment stages), `claude-opus-4-8` on the writer, with a server-side refusal fallback to
Opus on the Fable calls. A typical run lands well under $1.50; `claude-opus-4-8` or
`claude-sonnet-5` across all stages are the cheaper swaps.

## The website

The public reader-facing site lives in `site/` and is generated by `site_build.py` into
`site/publish/` (a build artifact, gitignored, reproducible). It has its own editorial
"trusted newsroom" identity: masthead, serif headlines, verdict badges that reuse the
pipeline's vocabulary, a "how we work" trust strip, a Netlify-Forms newsletter signup, and
baked-in not-financial-advice. Pages: home, archive, how-we-work (`method.html`), about,
standards/corrections, per-story article pages, plus 404 and a subscribe thank-you.

```sh
python3 site_build.py            # build site/publish/ from committed content
python3 site_build.py --ingest   # promote approved payloads, then build
```

**Whale Watch (follow the money).** `whale_flows.py` turns Whale Alert's public alert data
into a higher-perspective signal instead of a scrolling list: it classifies each transfer as
moving onto an exchange (potential sell pressure) or off an exchange (accumulation), scores
stablecoins separately as incoming buying power, and aggregates net flow per asset. It writes
`site/data/flows.json`, which the site renders as the "Whale Watch" page (a diverging bar chart
by asset + the biggest onto-exchange moves). Market data, not news, so it does not go through the
human gate, but it is clearly labelled as such. Data comes KEYLESS from Whale Alert's free
public alert archive (see DEVIATIONS D7) and refreshes at every Netlify build. Refresh locally:
`python3 whale_flows.py` (or `--fixture fixtures/whale_sample.json` to preview).

**Market Pulse (the data desk).** `market_pulse.py` fetches seven keyless public sources at
build time (Fear & Greed from alternative.me, daily closes from CoinGecko, stablecoin float
from DefiLlama, the full derivatives tape from OKX - funding current + history, open
interest + 30d trend, long/short ratio, recent liquidations - total cap + BTC dominance
from CoinGecko global, daily US spot ETF net flows from Farside Investors, network vitals
from mempool.space) and computes RSI-14, MACD, 50/200-day averages, 12-month-high distance,
and 30-day realized volatility with standard formulas in the standard library. The site
renders it as the "Market Pulse" page: a sentiment gauge, per-asset posture cards, the
stablecoin dry-powder trend, leverage and ETF-flow dashboards, and "101" sections that
teach every indicator in plain language. The site also emits an RSS feed of the published
stories at `/feed.xml`. Each source is independently fail-open and, like
Whale Watch, it refreshes at every Netlify build (see DEVIATIONS D8). Market data, not news:
it never touches the human gate and the page says so.

Content flow: a story is published only after human approval (`publish.py`). `--ingest`
promotes those approved payloads (`out/published/*.json`) into committed content
(`site/content/*.json`), which the build renders. Committed seed content is an honest launch
editorial plus one clearly-labeled example story that shows the format. Deploy and cadence
steps are in `LAUNCH_CHECKLIST.md`.

## Not financial advice

Crypto Cronkite reports events. It never advises trades. Nothing it produces is financial
advice, and that disclaimer is baked into every draft and every published payload.
