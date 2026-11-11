# Handoff, GoCheckMySports

One session per sprint (U-1). Start by reading this file and this sprint's section
of `PROGRAM-4-2026-09-16.md`. Do not re-read the boards or repos to reconstruct
state this file carries (U-6); open the file named for the item and the board named
for the item. Where a board and a rule disagree, ask in one line before inventing
(V-15).

Public repo. No tokens, keys or secret values in this file, ever.

Last updated: 11 November 2026, after Sprint B of the November 7 audit (first section below), and Sprint A
before it. Before that: 14 October 2026, 10:20 PM ET, after the S-2d merge (`374e5dd`, Program 7). The six 6
October branches (`docs-cloud-rules-u14-u16`, `search-s2-sitemap-no-games`, `deep-url-register`,
`cause-c-h6-hour-sweep`, `indexnow`, `ignore-claude-dir`) are merged; the proxy refuses branch
deletes, so Jack deletes them, and the S-1, S-2b, S-2c and S-2d item branches with them.
`search-s1-canonical-urls` stays open at `64fe43f`, untouched; its stash was a Mac artifact. The shared laws U-1 to U-16 are in `../HANDOFF.md`, not
this file. The day history is in `HANDOFF-2026-09-17-to-22.md`,
`HANDOFF-2026-09-23-to-10-01.md`, `HANDOFF-2026-10-06.md` and `HANDOFF-2026-10-12.md` (which also
holds, at its end, the S-2b to S-2d section and the A-17 budgets moved out on 11 November).

## Sprint B of the November 7 2026 audit (session of 11 November 2026)

Opener: `docs/RULES.md` body hash `4179b2ac...568d`, verified. No attribution trailer in any commit
(0 hits in `f6691f1..HEAD`), no em or en dash in any added line. Rulings applied: J-17, the scores
cadence runs as shipped for two weekends as a trial, and scoreboard data pushes are exempt from the
Sunday freeze; J-18, Jack turns NEWSROOM_JOBS back on himself, nothing here touches it. Not touched:
the fantasy hub modules, `/players`, Where to Watch, team pages, game page post-kickoff content, the
Wire's scope (Sprint C).

**Where it is.** Nine commits on `claude/great-heisenberg-gqoz7b`, pushed there and not to `main`
(the session's instruction names the branch). So "canary green on main" is not yet true: it is true
of this branch, `LAYER 1 CANARY: PASS`, exit 0, on `931359f`, the first full pass on a tree with the
plate fix. Merging the branch is the step that turns main green.

| Item | Commit | What shipped | Seen red by |
|---|---|---|---|
| B0a | `eef20f9` | `plate same` allows 0.25px of type size (was 0.01) | baseline gate on `f6691f1`: 47.7867px against 48px at 1100 |
| B0b | `bfe5935` | `scripts/cadence_report.py`: scores builds by day, Netlify build minutes, longest final-to-build gap | no weekend yet; ran on 8 Nov: 0 builds, "not read" lines |
| B0c | none (checked) | see below | fixture clock |
| B1 | none (checked) | see below | the gate's own 130, 101, -1 plates |
| B2 | `48ea4c6` | Scores All tab counts the board's leagues (NFL, CFB) like the home and the day tabs; `check_sprint_b` stops the build if home, Scores, All tab and today's day tab disagree | planted All tab +4 |
| B3 | `ce99953` | inactives header counts the posted cards drawn under it; "Lists we have not seen" removed; posted cards carry date and time; awaiting cards say Designations and drop out when the list posts; the build checks header against rows and that no team is in both states | planted header "2 lists, 10 players" over 1 list, 2 rows; planted posted and awaiting for one team id |
| B4 | `14ec83b` | game card link names ("Texas at Missouri, 12:00 PM ET, ESPN" before, "Texas 24, Missouri 17, Final" after); logo alt; lit bulbs are chips ("Wind 12 mph"), unlit ones leave the DOM text; spaces between plate spans and linescore cells; the build stops on a link with no name | not planted red; the check ran clean over all 1,288 built pages |
| B5 | `f98a7d8` | `data/team-abbr.json` (271 team codes, sportsbook spellings); the card disc no longer clips `TA&M` to `TA&`; Utah is `UTA` in the NHL and NBA; "Draft Kings" prints "DraftKings"; the build stops on a code not in the table | `ZZZ` code |
| B6 | `6921520` | one "No betting advice." per page, in the footer (1,288 of 1,288 pages, once each); "Facts, not advice" and the wind caption removed; per-card "Where to watch" control dropped where the card names a network; meta description "Scores, where to watch, fantasy facts and the lines, checked." | not planted red; the built tree grep reads 1,288 pages, one each |
| B7 | `df17d69` | /scores order: live by time left, then upcoming by kickoff, then finals newest first; the Standings door removed from /scores; a league with no game that day gets one line ("No NFL games today. Next: Thu Nov 12, 8:15 PM ET.") | sort fixture below |
| follow-through | `931359f` | canaries that encoded the old behavior, found by the first gate run, rewritten as ruled | gate run 1: 29 problems |

**B0a, and why 0.25 and not 0.1.** J-19 offered an integer type size or a 0.1px tolerance. Neither
works. The audit's 33.97 against 34 is the 34px (phone) plate; at 1100 the same plate is drawn
47.7867 against 48, a 0.21px gap, so 0.1 would have stayed red. Integer sizes would move the plate
by up to a pixel, which `plate same` exists to catch. The runner's hinting makes `100cqw / --w`
land a hair under the cap. A quarter pixel is half a percent of type.

**B0b, not readable yet.** The Nov 14 and 15 numbers do not exist at the time of writing, and there
is no Netlify token in the cloud session. Run from a full clone after Sunday night:
`git fetch --unshallow; NETLIFY_AUTH_TOKEN=... NETLIFY_SITE_ID=... python3 scripts/cadence_report.py 2026-11-14 2026-11-15`
and paste the output under the next heading. The gap is measured from the first snapshot that shows
a game final to the deploy that carried it; the end of the game itself is in no file, so the true
gap can exceed the figure by up to one tick (10 minutes). Weekend 1 (Nov 14 and 15): **to be filled.**
Weekend 2 (Nov 21 and 22): to be filled. J-17 stays a trial until both are in.

**B0c, confirmed on a fixture.** `home_lead` with the build clock pinned six hours after the newest
final in the feed: no Edition gives the Wire block ("Latest finals", three rows); an Edition 30
hours old gives the Wire block; an Edition published two hours earlier gives the Edition block
(headline, Bottom Line, links). The window is 26 hours from the Edition's `published_utc`, not the
calendar day, so an Edition at 7:48 PM still holds the block at 9 PM the next night and gives way
to the finals after.

**B1, partly verified, and what could not be.** The Nov 7 06:00 build's weather inputs are not in git
history: `site/data/conditions.json` is gitignored and rewritten by every build, and the 7 Nov
report in `site/reports/conditions/` keeps only the rendered words. Those words already read sane
(LAR at WSH "0% precip", DET at MIA "2% precip" at 7:33 PM) but are not the build's inputs, so the
130 and the DET at MIA mismatch were not reproduced from the day they happened. What was run
instead: the tile code (`sbg_conditions`) and the card code (`sbc_weather`) over every forecast
game in today's Worker data, both the published file (built 21:01Z) and the build's own: 73 games,
0 outside 0 to 100, 0 where tile differs from card, highest 93%. The gate's planted 130, 101 and -1
for DET at MIA print "missing" on every plate and name the game in the build log. Both surfaces read
`cx_parts()["pop"]`, so they agree by construction. To make the next audit checkable, nothing keeps
the day's raw inputs; if that matters, commit a dated copy of `conditions.json` into the report
JSON (a Sprint C question).

**B2.** The 4-game gap on Nov 7 (home 51, All tab 55) was the All tab reading the manifest's
all-league total (MLB, NBA, NHL, soccer, WNBA included) while the home and the day tabs read NFL and
CFB. All four now read `_mf_today_total(BOARD_LEAGUES)`.

**B3.** The old header was recounted by the page's own script from the whole day's snapshot (every
team the file held, including teams whose list belongs to another game), while the cards below were
placed by game window; and the "not seen" box was built from the board's teams without that window,
so it could name a team that also had a card. The script now counts the posted cards in the DOM, and
removes a team's awaiting card when its list lands. Not exercised against a live Sunday: the page
today has no posted lists. First look: Sunday 15 Nov, a fixture or two before 1:00 PM and after.

**B4 notes.** Bulb labels for unlit lamps are drawn by `.sbc-bulb:not(.on)::after{content:attr(data-l)}`
in `site.css`, so the look is unchanged and the text is not in the DOM. No 390 and 1440 screenshots
were taken (no designer in this session); the look sweep read 1,035 pages in both themes with 0
findings and the plate fit read 73,185 plates with 0 clipped. A text dump of a card now reads
"Temp 66° Wind 12 [Wind from the west] gust 23 mph Rain 41% rain showers".

**B5 risk to know about.** A team code the table does not hold stops the build. That is what was
asked, and it means a new ESPN code (an expansion team, a CFB program new to FBS) blocks the next
production build until one line is added to `data/team-abbr.json`. Netlify keeps serving the last
good deploy meanwhile. The log line is `::error::team codes not in data/team-abbr.json: CFB:XXX`.

**B6 left for Sprint C.** "Facts, not advice" is still in `/players` meta (66 pages,
`site_build.py` player page description) and in the image drawn by `share_cards.py`. Both are
outside this sprint's scope.

**B7.** Fixture: live Q4 2:10, live Q2, Saturday noon, Saturday 7:30, a final at 10 AM, Friday's
final, a postponed game sorts `live-q4, live-q2, sat-noon, sat-730, sat-early-final, fri-final,
postponed`. The H-12 canary expected the old closeness order (tie, one-score, 4-point game in the
second, blowout); under "by time remaining" the second-quarter game goes last, so its expectation
was changed in `verify_pipeline.py` and the closeness rule is the tie-break. Friday's finals live on
Friday's page, which is the day the games were on; the Saturday page lists noon above 7:30.

**Gate (U-12, U-15).** `LAYER 1 CANARY: PASS`, exit 0, on `931359f`. Two lessons for the next cloud
session. First: the gate restores every tracked file that changes while it runs and deletes files
it did not see at start, so an edit made during a run is silently wiped; commit first, then run, and
touch nothing for the roughly fifteen minutes. This session lost its uncommitted edits to it once.
Second: this sandbox has no Lighthouse, so the performance lines fail with "lighthouse not found".
`npm install --prefix <dir> playwright@1.56.1 lighthouse@12.8.2` into a scratch directory, symlink
`/opt/node-tools/node_modules/*` and `lighthouse` into `<tools>/node_modules`, and export
`PLAYWRIGHT_NODE_MODULES=<tools>/node_modules`; the gate then measures the home and a game page. The
pre-existing browser halves of the day-tab check still warn "playwright is not installed" here;
that is a warning, as on the baseline. A local `site/publish` also trips the US-date check on the
archive page ("page 1 of 5" followed by "October 12"); it is absent on CI and in the gate's own
tree, so delete a local `site/publish` before a gate run. That archive heading is a small pre-existing
defect for the board.

**Left for Jack.**
- Merge `claude/great-heisenberg-gqoz7b` to `main` (Netlify builds on the merge). Sunday 15 Nov: the
  scores builds are exempt from the freeze by J-17; this merge is not, so merge before 12:30 PM ET
  Sunday or after 8:30 PM.
- J-19 is answered by B0a (the tolerance, not a re-pin); J-17 and J-18 are your rulings of today.
  Moved under Answered in `docs/JACK.md`.
- Fill in the two weekends' numbers (B0b) and decide J-17 for good after the second.
- `NETLIFY_AUTH_TOKEN` and `NETLIFY_SITE_ID` in your shell for the cadence report, never in a file.

**Live URLs to check after the merge.** https://gocheckmysports.com/ (one count; the Edition or the
three finals under the band), https://gocheckmysports.com/scores.html (noon games above 7:30,
All tab equals the home), `/scores/2026-11-14.html` (a league with no game shows its next date),
`/fantasy/inactives.html` (header equals rows on Sunday; Designations until a list posts),
`/games/<any>.html` (card labels, hero tiles equal card plates), `/stamp.txt`; a text-only look:
`curl -s https://gocheckmysports.com/scores.html | sed 's/<[^>]*>/ /g' | tr -s ' ' | head -c 2000`.

## Sprint A of the November 7 2026 audit (session of 11 November 2026)

Opener: `docs/RULES.md` body hash `4179b2ac...568d`, verified. Pushed to `main` by the sprint's
instruction, one commit per item, no attribution trailer (`commit_trailers.py`: 0 hits). Jack's two
decisions are J-17, J-18 and J-19 in `docs/JACK.md`.

**The live layer (A1).** There is no live score layer, and nothing about the Worker or its token is
broken. No page ships a client-side score poll: S-1 removed it with the word "live" on 12 October.
The Worker's `/live` route (Program 4 L-1, board S-4.0, J-4) was never deployed, so between builds
nothing writes a score to the published site. The Scoreboard, the home and every `/scores` page
print what `scoreboard.py` fetched at the last Netlify build. Nothing rebuilt the site on a clock.
The `NETLIFY_BUILD_HOOK` secret is empty (the 12 Oct 23:40Z brief run logs `HOOK:` blank), so
builds came only from site-changing pushes: merges, conditions reports, and inactives ticks that
touch `site/data`. Saturday 7 November had none between 6:00 AM and the 7:37 PM ET conditions
push. Because the scores are static, the raw HTML is the score and there is nothing client-side to
back-fill. A1 adds the check that the raw HTML of `/scores` prints both scores, and Final, for
every started game. A2 makes the builds happen. Nothing for Jack's Mac.

**Why the Edition stopped on 12 October (A3).** Not a failed step, a slot guard, a lost trigger or
an expired token. Jack's ruling of 12 October (Program 7, S-1 item 3) retired the Edition as a news
digest. `sports-news-brief.yml` has no `schedule:` key and its job is gated on `NEWSROOM_JOBS`,
which is unset. The Worker's dispatch works: 23:40, 00:10 and 01:10 UTC every night. Every run
from 13 Oct 23:40Z (`38485643595`) to today concludes `skipped`. The last run that served was
12 Oct 23:40Z (`38323352077`, Evening Edition No. 77, $0.6381). Restarting it is J-18.

| Item | Commit | What shipped | Seen red by |
|---|---|---|---|
| A1 | `f35f45c` | truth canary `check_started_scored`: no-script `/scores` prints both scores, Final, the stamp; fails if it checked no card | `_tk_score` returning None (KCBUF 10 and 7) |
| A2 | `2c35679` | `scores-cadence.yml` + `cadence.py`; "Scores as of 4:52 PM ET" on the home and `/scores` (`build_manifest.asof`) | 60-min cadence, no halftime (3 cases); `git add -A site/data` |
| A3 | `7b2a8c5` | `edition_check.py` reads served slots from `watcher.SLOT_DEADLINES`: one missed slot warns (26h), three error (74h) | `OUTAGE_SLOTS = 1` (3 cases) |
| A4 | `d1e8cd9` | `edition_link()`: "The Edition" is the newest Edition inside 48h, else `/archive.html` | window widened to 30 days |
| A5 | `f349bb4` | report slot only same-day written from same-day forecasts, started games leave it; Record lanes "Nothing new since Oct 9"; Wire empty state | `cr_fresh` always true, started filter removed (4 lines) |
| A6 | `b09cc12` | home lead under the band: today's Edition (headline, Bottom Line, 3 links), else 3 newest finals with times, else "Back after tonight's games." | empty `home_lead` (6 lines) |
| extras | `3c7e4a2` | every rain plate reads `cx_parts()["pop"]`, `cx_pct()` fails the plate outside 0 to 100; windows note named by its day | range check removed, old note (7 lines) |

Gate (U-12, U-15): `verify_pipeline.py canary` on `3c7e4a2`, exit 1, load 11. Its reds: `plate same`
on three game-page hero plates (33.97px against 34), which origin/main fails identically here and in
its own CI run of 9 Nov (`42656647167`), and one look page timed out under load (`look_canary` alone
on the same tree: PASS, 1035 of 1035). Pushed on that red by the sprint owner's word, recorded as J-19.
Push: `48ba399..3c7e4a2`, HEAD `3c7e4a2` = origin/main `3c7e4a2`, 0 ahead, 21:01 UTC 11 Nov.

**How the cadence works:** rules in `cadence.py`'s docstring, ticks in the workflow header. A due tick commits only `site/data/scoreboard.json` ("scores: snapshot HH:MMZ") and that push
builds. Stop it by deleting `.github/workflows/scores-cadence.yml`.

**Acceptance, not yet readable (U-3: read at the next check, not waited on).**
- A2: Thursday 12 Nov TNF, a `scores:` commit at kickoff, at the half and at the final. Saturday 14
  Nov, one every 30 minutes from the first kickoff. Sunday 15 Nov, the stamp on `/` and
  `/scores.html` is inside 30 minutes at any check.
- A1: during that slate, `curl -s https://gocheckmysports.com/scores.html` shows a score or Final
  for every started game and "Scores as of".
- A4 to A6: on the first build after the push, no page links `/edition/2026-10-12.html` but the
  Edition pages, `/bottom-line.html` and the sitemaps (the archive of issues); the home carries
  `id="lead"` with a headline.

**Open, the desk's.** The audit's rain values (130, 101, 63 against 3) are not in today's Worker data,
so not reproduced; the guard holds and the build log names any game it fails.

**Live URLs.** https://gocheckmysports.com/ , `/scores.html`, `/scores/2026-11-14.html`, `/wire.html`,
`/keepers.html`, `/stamp.txt`; the count at gcm-slot-trigger.gocheckmybrands.workers.dev/counts/today; runs at https://github.com/jaybiz0131/gocheckmysports/actions/workflows/scores-cadence.yml

## 1. Where things live

| What | Where |
|---|---|
| Boards, packages, programs | `../gcm-tools/` |
| Program 7, Game Day (current; mockup `gameday-mockup.html` not yet committed) | `PROGRAM-7-GAME-DAY-2026-10-12.md` |
| Program 4 + ScoreboardC/GameCardConcepts | `../gcm-tools/program-4-2026-09-16/` |
| Program 3 + StyleTile | `../gcm-tools/program-3-2026-09-15/` |
| Copy pass | `../gcm-tools/copy-pass-2026-09-16/COPY-PASS-SPORTS-2026-09-16.md` |
| Site audit + hero addendum | `../gcm-tools/site-audit-2026-09-14/` |
| Worker (slot-trigger) | `../gcm-newsroom/slot-trigger/` |
| Crypto desk | `../gocheckmycrypto/` |

Canonical checkout is `~/Desktop/Berno Projects/`. Deploy from there and report the
version ID. Jack handles every secret value.

From 6 October 2026 this desk runs in Anthropic's cloud, working directory
`/home/user/gocheckmysports`, cloned from GitHub, pushing through the session's proxy.
The stash notes in the day histories describe the Mac; `stash@{0}` does not exist here.

## 2. Laws in force

**Standing, both desks.** No em dashes anywhere. No mention of AI. Times in ET with
one as-of line per surface. Never a fabricated number: a missing reading is omitted
or says the feed carried none, never "$0". Authored text is never truncated. URLs
never change. A module with no data is omitted. A shallow key is not an identity.

**A (Program 3, atmosphere).** A-1 ground on every page. A-2 poster 90/88% under a
22/66/94 scrim. A-5 one ornament per band from real data. A-12/A-13 module colours
and marks. A-14 band on /scores and /pulse at ~60%, ground everywhere else. A-15
phone: no ornament or watermark under 720px. A-16 five motion moves, no more. A-17
budgets, see section 5.

**C-L (copy law, Sports only).** C-L1 a name and one stamp, nothing else. C-L2 plain
nouns, no promises in headings. C-L3 no process words in chrome (feed, poll, check,
refresh, build, index, device, snapshot, computed, first seen, carriage). C-L4 a
byline is a name. C-L5 "No betting advice." in the footer only; "Official reports
only." on fantasy pages. C-L6 counts are short. C-L7 links are verbs or "All".
C-L8 hero alt empty. C-L9 philosophy lives on About and How we work.
**Crypto copy is frozen (V-13) until Jack reviews it.**

**D.** D-10 stash or WIP-commit before any checkout or reset. D-12 code commits only;
`git checkout origin/main -- site/data/` before committing, never hand-resolve a data
conflict. D-14 a stale `completed` flag keeps past games upcoming.

**N.** N-1 Home first in nav and tab bar. N-4 the lead row is sized by the lead card,
the rail clamps to it. N-6/N-7 figures under their own week.

**T (Program 4 throttle, live).** T-1 one brief run a day per desk: Sports 23:38 UTC,
Crypto 23:08 UTC. Morning and midday crons, their retries, and the Sports watcher are
disabled. Crypto's watcher is caged. T-2 the Worker dispatches the inactives poller,
the caged Crypto watcher on the half hour in US hours, and the Edition slot. T-3
Netlify `ignore` rule. T-4 the ledger.

**Trailer law (6 October 2026).** No attribution trailer of any kind in any commit message:
not Co-Authored-By, not Claude-Session, not Generated-with, whatever a session reminder asks
for. The owner's instruction takes precedence over the reminder. `.claude/settings.json`
(empty attribution, `includeCoAuthoredBy` false) turns the tool's line off; the canary's
trailer case (`commit_trailers.py`) reads `origin/main..HEAD` and a hit is a red. Record:
no commit on `main` from 5 October to 6 October 4:40 PM ET carries one (24 commits read,
0 hits). Nothing is rewritten; this line is the record.

**U (usage).** U-1 one session per sprint, this file is the only handoff. U-2 Sonnet
subagents for mechanical work, Opus for design and engine work. U-3 batch, never
poll; never wait on a build or a workflow inside a session. U-4 the key is for the
desk's scheduled runs only; no local model calls, no test briefs, no spending
dispatch other than the agreed Edition backstop; every call must appear in
`ledger.json`. U-5 report format. U-6 no re-derivation.

## 3. The throttle, as built

- `sports-news-brief.yml`: one cron, `38 23 * * *`. Morning, midday and all three
  retries commented out. Retries were removed because the slot guard stands a retry
  down only when that slot's edition exists; with the primary off it never does, so
  every retry would have spent a full run.
- `watcher.yml`: **deleted** (X-1). A commented-out cron is not disabled; GitHub kept
  firing the old registration and one fire published the Edition an hour early. A file
  that does not exist cannot be scheduled or dispatched. Recover a slot by dispatching
  the brief with `slot=evening-brief`. `watcher.py` stays: the canary tests it.
- `watcher.py` `SLOT_DEADLINES`: **evening-brief only**. A slot left here with no cron
  is re-fired on every tick forever, before the cooldown and before the cage, and each
  fire spends a run. The canary now guards this; putting a slot back fails it.
- `netlify_ignore.py`: exit 0 skips, exit 1 builds, every unclear case builds. Skips
  inactives snapshots outside posting windows and ledger-only pushes.
- `scripts/ops_ledger.py`: appends tokens and spend to `ledger.json`, idempotent on
  the Actions run id, commits with `[skip netlify]`. The file carries `since`
  (2026-09-16T16:27Z) and every tally prints it: a tally never claims a day it does
  not hold. Run counts for earlier days come from the Actions log.
- **The slot guard (X-2, X-2b)** applies to EVERY run, not only crons. A run for a
  slot whose Edition exists stands down at zero; a dispatch naming no slot stands
  down; a dispatch naming a slot the desk no longer serves stands down. `breaking=true`
  is the only bypass. The served list is read from `watcher.py`'s `SLOT_DEADLINES`.
  Ten cases per desk in the canary, run against the guard extracted from the YAML.
- **The live poll (L-2/L-3/L-4)** is in `SB_LIVE_JS`: 60s while a game on the page is
  live, 10 min otherwise, visible tabs only, updating in place. Source is the public
  scoreboard feed; L-1 swaps the URL for `/live/scores.json` and nothing else changes.
  Three misses mark the band stale and drop the live dot. The stamp is the source's
  own time or the build's, never the browser's.
- **The band never withdraws (H-7).** `scoreboard.load()` returns the snapshot with
  `stale: true` past `STALE_HOURS`; the band renders it and the stamp says
  "· stale". `scores_strip`, `SCORES_JS` and `SCORES_AGE_JS` are deleted.
- **Web push (S-3b.4, merged October 19).** Two Netlify functions deployed with the site: `netlify/functions/push.mjs` (POST /api/push, the subscribe route) and `netlify/functions/push-send.mjs` (scheduled `0 * * * *`, hourly). Both do nothing until `WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY` and `WEB_PUSH_SINCE` are set in the Netlify environment (J-5): the route answers 503 and the send reaches no network. Once set, the send pushes one notification per device per game between 7 PM and midnight ET the evening before kickoff. It publishes nothing to the site. Spend: one function run an hour, plus a subscribe call per reader action and Netlify Blobs storage (stores `push-subs` and `push-sent`), all within Netlify's plan, no model call. No npm install: the Blobs client is vendored at `netlify/vendor/netlify-blobs.mjs` with its rebuild line and licenses.
- `site/data/venue_corrections.json`: a correction only where the feed is wrong, keyed
  `LEAGUE:TEAM`. The canary fails the day the feed changes its record; the monthly
  aging job lists every entry with its owner and date.

**Open:** none here; the Worker dispatches on its tick (Sprint A read its runs, 11 November).

## Search

- **Sitemaps (S-2).** `sitemap.xml` is an index of `sitemap-priority.xml`,
  `sitemap-archive.xml` and `news-sitemap.xml`. Per-game pages are built and linked but are
  in no sitemap; players are in the archive.
- **The deep-URL register.** A page the build generates and leaves out of every sitemap is a
  choice on record, not an accident. `site_build.deep_url_register` runs last in `build()` and
  writes `/data/deep-urls.json`: the build's stamp at file level and one entry per generated
  page in no sitemap, with `url`, `kind` (game, superseded-article, aged-out-article,
  example-article, storyline-page, noindex), `linked_from` (the shallowest page that links it,
  or null) and `inbound`. It is computed from the pages on disk and the sitemap files
  written, never from the lists that made them. The build log prints `deep urls: N in no
  sitemap` with the kinds. `_register_canary` fails on a page in both places, in neither, a
  kind not in the list, a false `linked_from`, a stale stamp or a missing log line. Set a
  Search Console "Discovered, currently not indexed" row against it: in the register means
  deep by design, not in it means the sitemap asked for it. First build: 1,303 pages, 1,034
  listed, 269 deep.
- **The Search Console read (S-6), `scripts/register-read.mjs`.** Node, no packages. Reads the
  two exports against the register and the sitemaps (both default to the live files) and writes
  `docs/SEARCH-READ-<ET date>.md`: the unknowns first (URLs in an export that are in neither
  the register nor a sitemap), the deep pages indexed anyway, the linked pages missing from the
  index, then every page with its class. A page with no row is "absent" or "no row", never
  zero; a trailing slash, a query string, a fragment and a `.html` suffix match the page, and
  rows that match one page add. **Classes:** the register holds only the deep pages, so
  "linked" means a page the sitemaps list, which the register does not carry; `--help` prints
  the exports. Fixtures and the canary case: `fixtures/search-console/`. The report's shape was
  defined here, no earlier day-14 shape existed in the repo. **The two exports Jack makes on
  Monday 20 October 2026:** Performance, Pages (Performance > Search results > Pages tab >
  Export), and Indexing, Pages (Indexing > Pages: the indexed list, and one CSV per "why pages
  aren't indexed" reason). The read is his.
- **IndexNow.** Key file `/75487c1df3b38a38ef2793600c7e7bf7.txt` (content is the key, no
  newline, `text/plain`, written by the build). `scripts/indexnow.py` submits the sitemaps in
  full, URLs given on the command line, or `--content FILE...` for article URLs. First full
  send 6 October 2026, 10:03:19 AM ET: 1,034 URLs, one batch, HTTP 200 (10:02:08 AM got 403
  `SiteVerificationNotCompleted`, the engine had not fetched the key yet). The step in
  `sports-news-brief.yml` runs after the deploy check and sends the pages the brief commit
  changed, advisory, with its own `indexnow:` log lines. The inactives poller's commits do not
  build the site, so it has no step. Bing Webmaster Tools is Jack's.

## 4. Open items

| Item | Status | Last commit |
|---|---|---|
| H-12 Sunday grouping | grouping checked under fixture `sunday-130pm-early-live` (`_sunday_slate_canary`), green first, plants red; **live look Sunday 11 October 1:30 PM ET, one line:** the band's marquee and folds read live games first (tie, then one-score, then the rest), then the 4:05 and 4:25, then the night game, and the header, the NFL tab and the Next line (the 4:05) match | `55cf9e0`, merge `9bc6854` |
| V-8..V-12 Crypto visual | open, Sprint I | see the Crypto handoff |
| V-13 Crypto copy | **hold**, do not touch | Jack has not reviewed |
| V-14 Wire + reader panel W-4/W-7 | open, Sprint I | |
| L-1..L-6 live engine | open, Sprint H | Program 4 part 4 |
| Punch 5, 6, 8 (Crypto) | open | close Thu 6 PM ET |
| S-D day-14 report | **owed since Sep 28, still owed.** Not the Search read; this one is the source trial (`source_trial.py --report`) | |
| S-6 register reader, `scripts/register-read.mjs` | tool done; **the read is Jack's, Monday 20 October** | `e25f03e`, merge `4cd1b85` |

No deploys Sunday 12:30 to 8:30 PM ET, except the score builds of J-17.

## 6. Commands

```sh
# serve the built sites
cd site/publish && python3 -m http.server 8801      # crypto: 8802

# build
python3 site_build.py

# the gate. READ ITS EXIT CODE; do not pipe it into tail and trust the chain.
python3 verify_pipeline.py canary; echo "exit=$?"

# screenshots and page height (the canonical harness)
node ../gcm-tools/fullpage-shot.mjs <url> <out.png> --phone --perf

# ad hoc measuring, LCP and bytes
node /tmp/cdp.js <url> <width> <out.png> [mobile]
node /tmp/measure.js <url> <width> '<js expression>'

# the ledger
python3 scripts/ops_ledger.py --file            # committed file, no token, no network
python3 scripts/ops_ledger.py --tally 2026-09   # the month, via the issue

# workflow runs for a report
gh api "repos/jaybiz0131/gocheckmysports/actions/runs?created=>YYYY-MM-DDTHH:MM:SSZ" \
  --jq '.workflow_runs[]|"\(.created_at) \(.name) \(.event) \(.conclusion)"'
```

The copy grep must cover every chrome class the law names, not a subset. Grepping a
narrow set returned zero while 707 violations were shipping.

## 7. Traps this build has already paid for

- **"Absent from today's build" is not "dead".** Grepping built HTML misses markup
  behind a freshness gate (`.hero-bl` renders only when a Bottom Line edition is
  fresh; `.live-dot` only when an edition is under 24h) and classes added at runtime
  by JS (`.flash` / `.flash-dn` come from `pulse-live.js`). Before deleting CSS, check
  `site_build.py` and the JS for a producer, not only the current output. A subagent
  caught three of these after I had called them dead.
- **A preload must request the same URL the page will.** The asset versioner rewrites
  `/assets/...` in HTML but not inside `site.css`, so a preloaded font and the
  `@font-face` url() were two URLs for the same bytes: seven requests for five files.
  Fonts are exempt from versioning for that reason.

- A nickname is a shallow key. "Bills" matched a story about legislation. Match the
  full team name, or the nickname in the headline only, case-sensitive.
- Naming a team is not being about it. A headline opening with another team in the
  same league is that team's story.
- `display:grid` outranks `[hidden]`. Eight league panels rendered at once.
- `display:none` on an `<img>` still downloads it. Use a CSS background.
- `_utc_stamp` read the UTC hour and labelled it UTC, converting nothing.
- `git checkout <rev> -- <path>` **stages** what it restores. Re-check `git status`
  before committing, or data files ride along.
- An f-string expression cannot contain a backslash on this Python. Hoist separators
  into a constant.
- The build regenerates `site/data/*`; `git checkout -- site/data/` before committing.
