# Handoff, GoCheckMySports

One session per sprint (U-1). Start by reading this file and this sprint's section
of `PROGRAM-4-2026-09-16.md`. Do not re-read the boards or repos to reconstruct
state this file carries (U-6); open the file named for the item and the board named
for the item. Where a board and a rule disagree, ask in one line before inventing
(V-15).

Public repo. No tokens, keys or secret values in this file, ever.

Last updated: 1 October 2026, end of the merge-and-Cause-B session.
`main` ended at 0d02aa2. `build-stamp` and `cause-b-stamp-proof` are MERGED and
DELETED. `search-s1-canonical-urls` stays open at 64fe43f with S-2's work in `stash@{0}`.
The shared laws U-1 to U-13 are in `../HANDOFF.md`, not this file, by Jack's
option-two ruling of 1 October, along with the three rules added that day: a
plant's restore comes from a saved copy and never from `git checkout` on the file
under test; nothing is staged with `git add -A` and a documents-only message is
checked against `git diff --cached --stat`; a push's exit status is read from the
push and never from a pipe. The day
history is in `HANDOFF-2026-09-17-to-22.md` and `HANDOFF-2026-09-23-to-10-01.md`.

## 1. Where things live

| What | Where |
|---|---|
| Boards, packages, programs | `../gcm-tools/` |
| Program 4 + ScoreboardC/GameCardConcepts | `../gcm-tools/program-4-2026-09-16/` |
| Program 3 + StyleTile | `../gcm-tools/program-3-2026-09-15/` |
| Copy pass | `../gcm-tools/copy-pass-2026-09-16/COPY-PASS-SPORTS-2026-09-16.md` |
| Site audit + hero addendum | `../gcm-tools/site-audit-2026-09-14/` |
| Worker (slot-trigger) | `../gcm-newsroom/slot-trigger/` |
| Crypto desk | `../gocheckmycrypto/` |

Canonical checkout is `~/Desktop/Berno Projects/`. Deploy from there and report the
version ID. Jack handles every secret value.

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
- `site/data/venue_corrections.json`: a correction only where the feed is wrong, keyed
  `LEAGUE:TEAM`. The canary fails the day the feed changes its record; the monthly
  aging job lists every entry with its owner and date.

**Open:** Jack deploys the Worker (`cd ../gcm-newsroom/slot-trigger && npx wrangler
deploy`). Until then the evening slot has no automatic backstop; if it has not
published by 8:05 PM ET, dispatch `sports-news-brief.yml` with `slot=evening-brief`
and note it in the report.

## Where this session ended (1 October 2026, evening)

- `main` is **`0d02aa2`**, pushed and verified by hash, and live: the page's own `/stamp.txt`
  read `0d02aa29d579` at 22:57:27Z.
- **Cause B is fixed here** at `0d02aa2`. Eight checks that read the real publish tree could
  not fail in a job that builds nothing: three skipped behind an existence check, a glob and a
  walk that visited nothing and passed, and the rest. The gate builds its own tree now and all
  eight reads are unconditional. Reads of the real publish tree left in the gate: **zero**.
- The gate takes about **262 seconds**, up from about 90, because it builds the site once per
  run. Say that before someone reads it as a fault.
- Deploys today, from `/counts/today`, the count of record: **3 production builds** against an
  allowance of 12 (16 on Sundays). It is Thursday, so the Sunday game-window freeze, 12:30 to
  8:30 PM ET, did not apply to any of them.
- Branches: `search-s1-canonical-urls` at `64fe43f`, open, with S-2's work in `stash@{0}`
  (`fcacd1c`). `build-stamp` and `cause-b-stamp-proof` were merged and deleted after proving 0
  commits outstanding. Stashes: **one**, the S-2 work.
- **Next session's order, as Jack set it:** the twins branch on Crypto FIRST, link or retire;
  then **S-2 here**, as its own branch off `main` and not by applying the stash; then the
  deep-URL register; then Cause C, the H-6 scoreboard canary line, which healed on its own and
  is latent.
- Also open, with the last commit of each: A-17's font and poster work, shared with Crypto,
  nothing yet; H-5b, the byline carrying the date when it differs, nothing yet; H-12's Sunday
  grouping, still to be checked on a Sunday at 1:30 PM ET; the S-D day-14 report, owed since
  28 September and still owed.

## 4. Open items

| Item | Status | Last commit |
|---|---|---|
| V-1 Ticket scoreboard SC-1..SC-9 | done | `cdf4c41`, `fb6a16e` |
| V-2 copy pass, 51 lines + law | done, 0 banned words in chrome | `9197599` |
| V-3 lead row N-4 + D-13 | done, verified not assumed | earlier |
| V-4 fantasy surfaces | done | `ffd8983`, `7464d98` |
| V-5 punch 12 and 7 | done | `133fa98` |
| H-1, H-2, H-4, H-5, H-9, H-10, H-11 | done | `0f62903`, `157af75`, `9ed93e7` |
| L-2, L-3, L-4 live poll | done | `a3fd5bd` |
| X-1, X-2, X-2b, ledger `since` | done | `09ee73c`, `9ed93e7` |
| H-7, H-3, H-6, H-8 | done | `69878d9` |
| **H-5b byline carries the date when it differs** | **open** | |
| H-12 Sunday grouping | check Sun 1:30 PM ET | |
| V-6 inner pages and phone | done | `89dd26a` |
| V-7 fonts, poster, dead CSS | done | `0d1037e`, `00c618a` |
| V-8..V-12 Crypto visual | open, Sprint I | see the Crypto handoff |
| V-13 Crypto copy | **hold**, do not touch | Jack has not reviewed |
| V-14 Wire + reader panel W-4/W-7 | open, Sprint I | |
| L-1..L-6 live engine | open, Sprint H | Program 4 part 4 |
| Punch 5, 6, 8 (Crypto) | open | close Thu 6 PM ET |
| S-D day-14 report | **owed since Sep 28, still owed** | |
| U-13 preflight, both canaries, six plants red | done | `d9a093c` |
| Cause A, the workflow that loads with no jobs | fixed on Crypto `build-stamp` | `e2b77ec` |
| Cause B, the stamp and ignore proof | open, next session's first item | |
| Cause C, the H-6 scoreboard canary line | latent, healed on its own | |
| S-2, canonical URLs | open, its own branch after `build-stamp` | `64fe43f` + `stash@{0}` |

Sprint H closes Saturday noon ET, Sprint I Wednesday, Sprint J Friday. No deploys
Sunday 12:30 to 8:30 PM ET.

## 5. A-17 budgets, as measured

Measured 2026-09-17, local build, canonical harness at 390, median of three:
**Sports LCP 1,956 ms, Crypto 1,676 ms, CLS 0.0000 on both** (was 5,076 and 4,540
live on 09-16). Budget is under 3,000 ms; re-measure against the live pages after
the next deploy. Fonts: five files, 59.9 KB, same origin. Poster: phone variant at
10.2 KB (Sports) and 9.2 KB (Crypto).

- CSS 25.6 KB gz (Sports) / 23.8 (Crypto), JS 3.0 / 4.1. Budget 60 and 40. Pass.
- Fonts: 6 files, 4 families. Target is **five files, under 60 KB, same origin**:
  Plex Mono 400 and 700 only (600 goes), Newsreader roman and italic, Inter variable.
  Self-host as woff2 with `font-display: swap`, preload Newsreader 600 and Inter 400,
  and give the wordmark fallback a `size-adjust`. That closes the latent masthead
  shift (local CLS 0.1118 against live 0.0006) and takes Google off the LCP path.
- Poster: add a 390-wide variant, about 10 KB, chosen with `<picture>` or
  `imagesrcset` on the preload so the phone never fetches the 1600.
- Dead CSS to delete in Sprint I: the retired `.hero-*`, `.desk-coin` and pause
  blocks, about 25 per desk. Report CSS size before and after. The Edition's
  `.stamp{filter:saturate(.92)}` stays under S-22.
- Definition of done addition: **on phone, no request for an image that is not
  displayed**, checked from the network log.

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
