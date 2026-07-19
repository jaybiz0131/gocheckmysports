# GoCheckMyCrypto (Crypto Cronkite): DEVIATIONS.md

Places where the build diverged from, or must flag a tension in, its instructions.
House rule (inherited from the GoCheckMy family): surface tensions, do not resolve them silently.

---

## D1 - Migrated out of the GoCheckMyPet repo (2026-07-10; resolves the original D-CRYPTO-1 tension 1)

Crypto Cronkite was originally built inside the GoCheckMyPet repo under `crypto_pipeline/`
(branch `claude/crypto-cronkite-pipeline-i9zgjh`, PR #1, never merged into that repo's main),
because it reused that repo's proven pattern: scheduled ingest, AI processing, verified and
human-gated output, and the two-layer self-verification discipline. The "different product,
same repo" tension was recorded from day one with the note "if it graduates to its own home,
the directory lifts out whole."

It graduated: this repo was created via `git subtree split --prefix=crypto_pipeline`, so the
full crypto commit history is preserved with the pipeline at the repo root. Only the CI
workflows, the Netlify config (now a zero-setting root `netlify.toml`), and doc paths were
adapted; no Python changed (every script resolves paths from its own location by design).
GoCheckMyPet's main was never touched by any of this work.

## D2 - Raw HTTP, not the Anthropic SDK

The Claude API guidance prefers the official SDK. This project is deliberately dependency-free
and offline-reproducible (standard library only, like its GoCheckMy siblings), so the LLM
client calls `https://api.anthropic.com/v1/messages` directly with `urllib` and the documented
headers. The request shape follows the current model family: no `temperature`/`top_p`/`top_k`
(those return HTTP 400 on `claude-opus-4-8` / `claude-sonnet-5`); register and determinism are
steered by the prompts.

## D3 - Quality-first models over the blueprint's cost emphasis (updated 2026-07-10)

The blueprint stresses cheap-per-run calls and a spend cap. Per the owner's explicit call
("the right man for the job; I will pay more for better quality"), the two JUDGMENT stages
run `claude-fable-5` (Anthropic's most capable model, $10/$50 per MTok): the editor, whose
job is filtering shill, and the verifier, whose job is accuracy against live sources. The
writer stays on `claude-opus-4-8` (strong news prose, human-reviewed anyway, and a second
model family after two Fable stages). Two Fable-specific accommodations in `llm.py`: a
600s HTTP timeout (its always-on thinking can run minutes) and a server-side refusal
fallback to `claude-opus-4-8` (hack/exploit coverage, core content for a crypto desk, can
trip Fable's cybersecurity safety classifiers; the fallback re-serves declined calls in the
same request, and a full-chain refusal still fails the stage closed). The cost discipline is
met by the hard cap (raised to $5/run for thinking-token headroom; typical runs land well
under $1.50), not by silently downgrading the model. Note: `claude-fable-5` requires 30-day
data retention on the Anthropic org; a zero-data-retention org would 400 on every call.

## D4 - Standalone brand; name-only GoCheckMy family tie

Two deliberate divergences from the GoCheckMy family conventions, decided with the owner:

1. **No family visual reskin.** GoCheckMy siblings share a teal/gold palette, Fraunces
   wordmark, and a shared disclosure-bar header. This site keeps its own trusted-newsroom
   identity (Newsreader serif, red masthead rule) because the owner has an existing Crypto
   Cronkite channel, logo, and audience; continuity there outweighs family visual consistency.
   The family tie is the NAME only: the domain `gocheckmycrypto.com`, a small
   "GoCheckMyCrypto.com" marker in the masthead top row, and the canonical
   `<a href="https://gocheckmy.com/">A GoCheckMy site</a>` hub link in the footer. Crypto
   Cronkite is the focal brand (masthead + tagline "And that's the way it is."); the Cronkite
   name is used as a brand/homage, never as the domain or company (the riskier play).

2. **Email newsletter kept, diverging from the family "no email capture" rule.** The crypto
   blueprint explicitly makes the newsletter the highest-value channel ("the owned audience,
   build this first"), and the owner confirmed this site stands on its own apart from the
   family. The signup stays (Netlify Forms; no selling of emails; unsubscribe-anytime copy
   baked in).

## D6 - The Netlify build fetches Whale Alert data (build is no longer purely deterministic)

The repo's stated posture is a deterministic site build from committed content. The Whale
Watch board needs fresh data without a human committing JSON every day, so the Netlify build
command runs `whale_flows.py` (network call to Whale Alert, keyed by a Netlify env var)
before `site_build.py`, and the daily-brief workflow pings a Netlify build hook so the board
refreshes every morning. The tension is contained: the fetch is fail-open (`|| true`; a
missing key or API error falls back to the committed `site/data/flows.json` snapshot, never
fails a deploy), everything else in the build stays deterministic from the commit, and a
local `python3 site_build.py` still reproduces the site from committed content exactly.

## D7 - Whale Alert: free public archive instead of the retired keyed API (2026-07-10)

Whale Alert retired the keyed v1 REST API this pipeline was built against. The replacements
(a $29.95/mo personal-use-only WebSocket needing a 24/7 listener, and a $699/mo Enterprise
REST API) fit neither the budget nor the static/serverless posture. Instead, both consumers
(the Whale Watch board and the brief's on-chain items) now read Whale Alert's FREE public
archive of every alert they post (`https://whale-alert.io/whale-alerts-archive.json.gzip`),
which Whale Alert explicitly offers for models/algorithms/research and which refreshes
continuously. Trade-offs, stated honestly on the site: (1) the archive names owners but has
no owner_type, so exchanges are identified by a curated name list in common.py (a heuristic);
(2) only transfers large enough for Whale Alert to post publicly (roughly $50M+) appear, so
the board reflects the very largest moves, not all whale activity. The loader streams the
newest-first gzip and stops at the window boundary, reading tens of KB, not the ~600MB file.
The board is fail-open (fetch failure keeps the previous snapshot); the news pipeline treats
a fetch failure as a documented skip. Attribution and links to Whale Alert are on the board.
Live-tested 2026-07-10: 21 archive alerts in 24h -> 11 exchange-relevant transfers, real
board committed. This resolves and replaces the old D5 concern for Whale Alert.

Addendum 2026-07-12: because only ~$50M+ moves appear, a quiet day can leave the configured
24h window with zero exchange-relevant transfers, and the build was overwriting a good board
with an empty one ("no board yet" in production). `whale_flows.py` now widens the lookback
(48h -> 72h -> 7d) until something exchange-relevant appears and labels the board with the
window it actually shows (the page explains the widening to the reader). If even a week is
empty it keeps the previous snapshot, the same fail-open as a fetch error.

## D8 - Market Pulse: third-party market data fetched at build time (2026-07-10)

The Market Pulse page (sentiment gauge, RSI/MACD/moving-average posture, stablecoin float,
Bitcoin network vitals) extends the D6 posture: `market_pulse.py` fetches four keyless
public sources at Netlify build time (alternative.me, CoinGecko, DefiLlama, mempool.space)
and computes the indicators with standard formulas in the standard library. Each section is
independently fail-open: a failed source is warned and omitted, a fully failed run keeps the
committed snapshot, and a deploy never fails on market data. The same honesty rules as Whale
Watch apply: sources are named on the page, every indicator gets a plain-language education
card, and none of it ever becomes a buy or sell call. The Whale Watch board also gained a
13-week net-flow history computed from the same public archive read (D7). Market data never
touches the editorial pipeline or the human gate.

## D9 - Leverage desk: OKX public API, because Binance/Bybit geo-block US builds (2026-07-12)

The Leverage dashboard (perp funding rates + open interest for the majors) wants
market-wide derivatives data, but the aggregators (Coinglass etc.) are keyed/paid and the
deepest venue, Binance, geo-blocks its futures API from US infrastructure (HTTP 451), as
does Bybit (403), which is what Netlify builds run on. So `market_pulse.py` reads OKX's
free public endpoints (funding-rate + open-interest, keyless, reachable from US builds),
with Deribit's public ticker as a BTC/ETH fallback, and the page says plainly that these
are single-venue snapshots, not market-wide totals. No BNB perp on OKX, so the leverage
board covers BTC/ETH/SOL/XRP/DOGE. Same fail-open posture as every Market Pulse section.

## D10 - Intake widened: macro/official feeds + the narratives watchlist (2026-07-12)

The original 11-feed intake was crypto-press only, so macro events that move crypto (Fed
decisions, legislation, DOJ enforcement) arrived secondhand and only if a crypto outlet
wrote the angle. Added five keyless feeds, all live-tested: Federal Reserve monetary-policy
releases, Senate Banking Committee press (where market-structure bills surface), Ethereum
Foundation blog, DOJ press releases, and MarketWatch top stories. The two broad feeds (DOJ
is all-of-DOJ, MarketWatch is all-of-markets) get a per-feed `keywords` relevance gate in
aggregate.py so they cannot flood the editor. Dead ends tried and rejected, so nobody
retries them: Treasury press RSS (404), CNBC (1-item stub), House Financial Services RSS
(404), govtrack (403), congress.gov most-viewed (stub).

Same change adds the `narratives` watchlist (config.json): the desk's ongoing storylines
(CLARITY Act, CBDC ban, BIP 110, ...), maintained by the editor-in-chief like
shill_rules.json. Matching clusters are tagged in items.json, the editor treats a genuine
development in a tagged narrative as presumptively rank-worthy, and a watchlist match
always passes a feed's keyword gate. Honest limit: a static list catches follow-ups to
NAMED narratives; a brand-new narrative is caught the normal way (multi-outlet clustering)
and should then be added to the list.

## D11 - The Chart Master's read is auto-generated from the boards (2026-07-13)

The wizard's read was a hand-written one-off (2026-07-10) with no generator, so it aged
into quoting stale numbers under a "reads the day's boards" promise. Owner's call: the
read must refresh like the news and execute like a professional. `chartmaster.py` now
digests the complete published tape (pulse.json + flows.json: sentiment, per-asset
posture, funding/OI, stablecoin float, whale flows and their weekly trend, movers,
network) and asks `claude-fable-5` (the judgment model, one call per brief, cents/day)
for a technician's read in a fixed professional order: regime, momentum-vs-trend,
positioning, flows, sentiment-as-foil, and a what-to-watch close. Two belts hold the
house line: the prompt forbids prediction/advice, and a deterministic banned-language
check refuses any read containing it (fail-open: the previous read stands). Market
commentary, not news: no editorial gate, fail-open everywhere, replay mode writes only
the out/ test artifact and can never touch site data. Runs in crypto-news-brief.yml
after a data-desk refresh so the read matches the boards the deploy publishes;
site/data/chartmaster.json is committed because Netlify builds do not regenerate it.

## D12 - Derivatives depth + ETF flows, all keyless; CryptoPanic de-recommended (2026-07-13)

The paid aggregators (Coinglass etc.) were assumed necessary for liquidations and ETF
flows; live testing found free paths for all of it. OKX's public API adds funding history,
30-day open-interest trend, the long/short account ratio, and recent liquidation orders
(sz is in CONTRACTS: notionals use ctVal from the instruments endpoint). CoinGecko /global
adds total cap + BTC dominance. Daily US spot BTC/ETH ETF net flows come from Farside
Investors' public tables - an HTML SCRAPE, the repo's only one, and brittle by nature: the
parser accepts only rows shaped exactly like the flow table (date cell + numeric total,
parens as negatives) and the section drops out fail-open on any doubt, so a Farside
redesign degrades to a missing board, never a wrong number. All of it is labeled
single-venue/lagging where true, feeds the Chart Master's digest, and refreshes each build.
Separately: CryptoPanic is no longer recommended (now ~$199/mo, previously suggested as a
free intake widener); the keyed adapter stays wired but dormant.

## D13 - Farside pre-publishes zero rows; flow charts become ledger rows (2026-07-13)

Two findings from the owner's phone. (1) Farside adds the NEXT trading day to its flow
table as a row of zeros before flows settle, so "latest day" read $0 on the live site;
_parse_farside now drops trailing rows whose per-fund cells are all zero/blank (interior
zero days stay). (2) SVG bar charts draw on a ~660-point canvas, so a 390px phone renders
their labels at ~6px; the ETF daily and whale 13-week bar charts are replaced by an HTML
"flow ledger" (date, diverging horizontal bar, full-size signed value per row) whose text
never scales down, and the remaining SVG charts got a ~35% in-chart font bump. Same change
turns the Market Pulse hub into The Board: one master dashboard of number-first widgets
for every desk including Whale Watch and the Chart Master's dated headline, two columns on
phones, each widget a tap into the deep board where the 101 teaching lives. Follow-up,
same day: the Board is ORDERED by the house reading doctrine (the Chart Master's method) -
the read as a full-width strip, then Price, Flows, Positioning, The day (sentiment last,
as the foil), Chain, with group kickers; and Whale Watch gained the expert layer: gross
on/off split behind the net, a pace chip vs the median week from the 13-week history,
per-move age plus a receipt link to the transfer on Whale Alert, and a by-exchange
concentration table.

## D5 - X source adapter is wired but not live-tested

X/Twitter remains a keyless-skip source (absence is a documented skip, never a failure) and
could not be exercised without a paid API key (~$100/mo). Treat the first keyed run as a
smoke test and check the intake log. (Whale Alert, formerly also in this entry, is now
live-tested via the public archive -- see D7.)
