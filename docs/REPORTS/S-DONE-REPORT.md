# S-DONE report: the whole site to 8 of 10 and self-running

Session opened Tuesday, November 24, 2026, 12:10 PM ET (17:10 UTC) on gocheckmysports, with gcm-newsroom cloned read-only; stopped at 12:40 PM ET by the owner and resumed Wednesday, November 25, 4:05 AM ET (09:05 UTC) in a fresh container (the first was reclaimed; nothing was lost, nothing had been committed). `docs/RULES.md` body hash at the opener (everything below the header's rule): `2b3ddc0f60f3f5433f9ef67409833dcc53186b1e486d4d4c6942eb0b9d365211`, equal to the header's. No trailer in any commit message (`commit_trailers.py`: 0 hits). This file is the running scorecard: it is updated after every merge. The container was replaced twice more on November 25 (09:05 and 11:48 UTC); nothing committed was lost either time.

## Scorecard

**Nine of ten green on production at this writing (November 25, 16:00 UTC); point 1 is red.** Its first game window since the merges opens at 8:00 PM ET tonight and is read then; by the brief's own rule it stays red after that until Jack's Worker deploy is confirmed. <!-- window -->

| # | Point | State | Evidence, or the reason |
|---|---|---|---|
| 1 | Fresh | **red**: not yet read through a game window (tonight, 8:00 PM ET), and red by rule until Jack's deploy | Merged as items 1 and 11 (`69aeaf1`, `00a62d0`); what was found and built is under "Point 1" below. Proved on GitHub's runner so far: the new job's due path (run 45597456275, 10:41 UTC, which pushed `12c3053` "scores: snapshot 10:42Z") and its step-aside and look-ahead path (run 45619617831, 13:02 UTC, "window off looking 6 hours ahead"); both were dispatched by this desk, not by the Worker. Outside a window the stamp says so: "Scores as of 10:43 AM ET, refreshed every 5 minutes from 8:00 PM ET". <!-- window-1 --> |
| 2 | Honest | **green** | Checks `honest counts`, `live` (a browser on fixed clocks), `s60`, `n1`. On production (`a02c209`): the stamp is the reading's time in ET with its zone (`<meta name="scores-asof">` beside it), never the build's; All 1 = NFL 1 = Live 0 + Upcoming 1 + Final 0 = 1 card on `/scores`; the home's day tabs add to their cards and "N more college games" lines. A card past its kickoff with no state from the feed prints "No update since" with the reading's time and moves to Live (browser case, a day-old page). A final prints its time only when the desk read the final within 5.5 hours of kickoff; Tuesday's two finals, first read at 5:42 AM Wednesday, print "Final, Tue Nov 24" and no clock, because the desk did not see them end. |
| 3 | Readable | **green** | `/scores` at 375 by 812: the tabs Live 0, Upcoming 1, Final 0 and the first card with both teams and "Netflix" are in the first screen (`S-DONE-shots/after-scores-375-0.jpg`). Networks print by name (Fox, CBS, ESPN, ABC, NBC, SEC Network, Prime Video, Netflix, FS1 on the home; "CBS Sports Network", "Big Ten Network", never a code or a radio call sign). The line prints with its opener where the book moved it ("LAR -2.5 · O/U 44.5, Opened LAR -3.5"; 6 of Saturday's 53 cards carry an opener). Ranks print (Notre Dame 4, Miami 7; 15 of Saturday's 53). Kickoff conditions print, or the one reason ("Dome · No weather"). On the home at 375 the first card's own line (kickoff, venue, network) is in the first screen since merge 13; its team names are one flick down. Checks `readable`, `page width, every page type`. |
| 4 | Clean | **green** | The crawl below: 1,293 pages of production, every term zero. Checks `clean` (1,252 pages of the day's build and 1,250 of the slate) and `clean read, every page type` (61,221 text elements in a browser, none cut mid-word, no empty section or card). The literal "·" in the list was read as a raw entity printed as its letters (`&middot;`, `&amp;` and the like): the middle dot itself is the house separator, in about 19,000 places. |
| 5 | Whole | **green** | The crawl below: 52,821 internal links, zero that do not answer 200; one title, one description and one canonical on each of 1,293 pages (the 404 page has no canonical); 513 sitemap entries, every one a page that answers 200, none noindexed; the tab bar with its five links on 1,293 of 1,293. A missing URL answers 404. No page type is wider than the viewport at 375 or 1440 (72 pages of 25 kinds, 144 loads, 0 findings). Checks `whole`, `page width, every page type`. |
| 6 | Fast | **green** | Lighthouse 12.8.2, mobile, on production `a02c209`, November 25, 15:48 UTC: home 100 performance and 100 accessibility, Scores 100 and 100, a game page 99 and 100 (`S-DONE-logs/lighthouse-a02c209.json`). The baseline on `5b9e395` was 95 and 96, 96 and 100, 100 and 100. Check `fast`. |
| 7 | Current | **green** | `/fantasy/` prints Week 12, the week the calendar says on November 25: "Week 12 inactives, Wednesday's lists post about 6:30 PM ET", "Week 12: Out 11, Doubtful 6, Questionable 120, Updated Nov 25", byes for Week 13. Each fantasy surface prints its own data's stamp. The stale-lane rule is live: `/keepers` prints "Nothing new since October 8, 2026." and `/news` "Nothing new since October 12, 2026."; neither is in the navigation, the footer or on the home. The Edition stays off. Check `current`. |
| 8 | Quiet | **green**, with two reds named | The seven-day tally below: 3 failures in 557 runs, each a real outage or a class S-61 already closed. The health gate is live; its last three runs are red, red and green, and both reds are real score gaps (point 1's cause). Every run on a push to main in this session is green (13 of 13). `netlify_ignore.py` treats `docs/`, `review/` and reports as no build (check `inline layer 1`). |
| 9 | Found | **green** | Home title "College football and NFL scores, where to watch, spreads and kickoff weather - GoCheckMySports", the same phrase opening the description and under the masthead on every page. `SportsEvent` data on the home and `/scores` for the day's games; the block on `/scores` validates at validator.schema.org with 0 errors and 0 warnings, and the home's block is the same bytes (the validator turned the home's own request away three times). About: "GoCheckMySports is run by Go Check My Brands LLC, a South Carolina limited liability company", two contacts, nothing about how. Check `found`. |
| 10 | Beautiful enough | **green** | Six before and six after screenshots at 375 and 1440 in `S-DONE-shots/`. What changed, with existing tokens only: the band ends under its controls on a phone (150px of empty photo gone), the page no longer starts inside the band's dark foot, the count and stamp are legible on the photo, the Sunday windows row says "Sunday", today's college games are drawn first inside the byte budget, a game under way on the wall draws "Under way" in place of three "n/a" plates, and on a phone the first game follows the band. Check `beauty`. Left as it is and named: the pale strip behind the sticky day heading. |

## Merges, in order

Thirteen items, thirteen merge commits, each pushed by this desk and each read on production by its stamp before the next. The merge's tree is the gated commit's tree in every case; the only file that differs is `site/data/scoreboard.json`, which main's own scores job writes.

| # | Item (branch) | Gated | Merge | Parents | Pushed (UTC, Nov 25) | Production read by stamp |
|---|---|---|---|---|---|---|
| 1 | Fresh: the re-read (`sdone-1-fresh`) | `b0e7d8b` | `69aeaf1` | `5b9e395`, `b0e7d8b` | 10:33:31 | built 10:33:49 |
| 2 | Quiet (`sdone-2-quiet`) | `0c02372` | `47207e2` | `69aeaf1`, `0c02372` | 10:40:52 | read as `12c3053`, built 11:00:43 |
| 3 | Honest (`sdone-3-honest`) | `37c3b9a` | `8ebe34e` | `12c3053`, `37c3b9a` | 12:30:39 | built 12:31:01, read 12:34:09 |
| 4 | Readable (`sdone-4-readable`) | `860f95a` | `d0a589e` | `8ebe34e`, `860f95a` | 12:34:28 | built 12:34:45, read 12:37:57 |
| 5 | Fresh: who starts the run (`sdone-11-start`) | `6037f84` | `00a62d0` | `d0a589e`, `6037f84` | 13:02:31 | built 13:02:52, read 13:06:13 |
| 6 | Whole (`sdone-5-whole`) | `ef8ec71` | `ab8d129` | `00a62d0`, `ef8ec71` | 13:06:29 | built 13:06:51, read 13:09:38 |
| 7 | Clean (`sdone-6-clean`) | `1b9f255` | `1ec5e83` | `ab8d129`, `1b9f255` | 13:35:39 | built 13:36:00, read 13:39:22 |
| 8 | Current (`sdone-7-current`) | `5121aed` | `08cf916` | `1ec5e83`, `5121aed` | 13:39:42 | built 13:40:03, read 13:43:06 |
| 9 | Found (`sdone-8-found`) | `6713c89` | `7f2b896` | `08cf916`, `6713c89` | 14:08:20 | built 14:08:41, read 14:12:24 |
| 10 | Fast (`sdone-9-fast`) | `6a93ec1` | `a3801f7` | `7f2b896`, `6a93ec1` | 14:12:50 | built 14:13:15, read 14:16:13 |
| 11 | Beautiful enough (`sdone-10-beauty`) | `96c346d` | `d004423` | `a3801f7`, `96c346d` | 14:29:47 | built 14:30:08, read 14:33:11 |
| 12 | The copy law's word (`sdone-12-scoreboard`) | `c4553dc` | `17470c5` | `d004423`, `c4553dc` | 15:21:16 | built 15:21:38, read 15:25:20 |
| 13 | The home's first glance at 375 (`sdone-13-glance`) | `94b12c0` | `a02c209` | `17470c5`, `94b12c0` | 15:42:42 | built 15:43:09, read 15:46:47 |

U-8 on every push: HEAD equal to origin/main by hash, 0 ahead, printed by the merge command. Each production read is `scripts/prod-read.mjs --commit` at 375 and 1440 on the home, Scores, Where to Watch and Fantasy: the stamp is the merge, no page scrolls sideways (8 of 8 each time), and the logs are `S-DONE-logs/prod-read-<merge>.log`. IndexNow by hand after each merge: `/` and `/scores` (with `/fantasy/` after merge 8 and `/about` after merge 9), HTTP 200 thirteen times.

**The count of record** (the Worker's `/counts/today`, read after each merge): gocheckmysports production ready **15** on 2026-11-25 at 15:46 UTC: the 6:00 AM hook build, the morning scores snapshot, and thirteen merges. That is over the allowance of 12 a day (J-17). The brief asked for the merges one at a time, each read on production before the next, however many it took; each merge is one deploy and none was made for a number alone.

Items 12 and 13 were found after merge 11, by reading the after screenshots as a stranger would: the Scores hero printed "Scores" where the copy law's word is "Scoreboard", and on a phone the home drew a screen of the latest finals between its band and today's first game.

## The gate (U-12, U-15, U-16)

The harness that runs this session ends a foreground command at 10 minutes and the gate takes 20 to 33, so every `preflight && push` ran as one tracked command, its output to a file, its chain status written by the command itself and read after it exited (`scratchpad/gate.sh`: `python3 verify_pipeline.py canary >> log && git push origin sha:branch`). Each ran in its own git worktree of the commit under test with a fresh `PYTHONPYCACHEPREFIX`, two at a time. Items are stacked (each branch on the one before), and an item's gate runs on its branch tip; the merge command refuses a merge whose tree differs from the gated tree outside `site/data/` and `data/`.

| Tree | Started (UTC) | Load at start | Exit | Fixture tests | Reds | Log |
|---|---|---|---|---|---|---|
| main `5b9e395`, the baseline | 09:19:01 | 0.75 | 0 | 58 | 0 | `gate-main-5b9e395.log` |
| item 1 `99ee766` | 09:37:04 | 1.68 | 1 | 59 | 3, none on the site: `truth` twice and `home` once read the stamp's and the lead slot's tags by their exact old text; nothing was pushed | `gate-1-99ee766-red.log` |
| item 1 `b0e7d8b` | 10:00:28 | 0.77 | 0 | 59 | 0 | `gate-1-b0e7d8b.log` |
| item 2 `0c02372` | 10:00:28 | 0.77 | 0 | 59 | 0 | `gate-2-0c02372.log` |
| the whole stack `8e05c8a`, a shake-out, no push | 10:41 | not read | 1 | 69 | 4: `small` and `home` three times held the behavior item 7 changes; moved to the new truth in item 7's commit | `gate-stack-8e05c8a-red.log` |
| item 3 `37c3b9a` | 11:58:48 | 0.18 | 0 | 60 | 0 | `gate-3-37c3b9a.log` |
| item 4 `860f95a` | 11:58:56 | 0.32 | 0 | 61 | 0 | `gate-4-860f95a.log` |
| item 11 `6037f84` | 12:30:37 | 7.02 | 0 | 61 | 0 | `gate-11-6037f84.log` |
| item 5 `ef8ec71` | 12:30:37 | 7.02 | 0 | 63 | 0 | `gate-5-ef8ec71.log` |
| item 6 `1b9f255` | 13:02:28 | 8.62 | 0 | 65 | 0 | `gate-6-1b9f255.log` |
| item 7 `5121aed` | 13:02:47 | 6.23 | 0 | 66 | 0 | `gate-7-5121aed.log` |
| item 8 `6713c89` | 13:35:29 | 9.60 | 0 | 67 | 0 | `gate-8-6713c89.log` |
| item 9 `6a93ec1` | 13:35:29 | 9.60 | 0 | 68 | 0 | `gate-9-6a93ec1.log` |
| item 10 `96c346d` | 14:08:18 | 8.27 | 0 | 69 | 0 | `gate-10-96c346d.log` |
| item 12 `c4553dc` | 14:44:31 | 0.23 | 0 | 69 | 0 | `gate-12-c4553dc.log` |
| item 13 `0137a09`, the first cut | 14:45:54 | 1.10 | 1 | 69 | 1, and right: "shift: with #day-fri at 390 the page shifts 0.0568". The cut reordered the lead with CSS and trimmed the band through a `:has()` rule over a later sibling, so the band's title block moved 35px once `main` had been parsed. Nothing was pushed; the item was rebuilt with the order in the markup. | `gate-13-0137a09-red.log` |
| item 13 `94b12c0` | 15:21:12 | 0.43 | 0 | 69 | 0 | `gate-13-94b12c0.log` |

**The last gate's output: `docs/REPORTS/S-DONE-logs/gate-13-94b12c0.log`** (exit 0, 69 fixture tests, 15:21:12 to 15:42:32 UTC). Every gate carried the same 4 live-canary warnings, all on the day's data and all older than this session: five college team pages 8px wide of a 320 viewport, two of them at 340, and two `plate same` notes of a fraction of a pixel. 320 is a warning by ruling.

Eleven fixture tests are new (58 to 69): `live`, `honest counts`, `readable`, `whole`, `page width, every page type`, `clean`, `clean read, every page type`, `current`, `found`, `fast`, `beauty`. Every one was seen red before its code and again under planted faults (U-9): `S-DONE-logs/plants-*.log`, one file per item. No test was skipped, disabled or loosened to get a green; four older checks were moved to a new truth and each is named in the table above or in its item's commit.

## Production, read on the final stamp

`commit a02c2092dbecf9ffa64873d6426fc6f83e01ff9d`, built 2026-11-25T15:43:09+00:00.

**The crawl** (U-10, the deployed site and nothing else): every URL in the three sitemaps, then every internal link found on every page fetched, until none is new. `S-DONE-logs/prod-crawl-a02c209.json`.

| Read | Count |
|---|---|
| pages fetched | 1,293 (all HTML, all 200) |
| internal links followed | 52,821 |
| links or assets that did not answer 200 | **0** (28 assets checked by HEAD) |
| sitemap entries | 513, every one 200, none noindexed |
| pages without exactly one title, one description, one canonical | 0, 0, 0 |
| pages without the five-link tab bar | 0 |

**The grep.** Each page is read as a reader reads it (scripts, styles and comments out, tags out, entities resolved) by `clean_canary.scan`, the same code the gate runs; on a story page the story's own text is left out for the six words, and the em dash and the UTC stamp are read in all text, stories included. The patterns, as the file holds them:

    missing            \bmissing\b
    undefined          \bundefined\b
    NaN                \bNaN\b
    null               \bnull\b
    None               \bNone\b
    $0                 \$0(?![\d.,])
    0 pieces           \b0 pieces\b
    1 pieces           \b1 pieces\b
    a raw entity       &(?:middot|amp|nbsp|mdash|ndash|rsquo|lsquo|rdquo|ldquo|quot|#\d+|#x[0-9a-fA-F]+);
    an internal note   read at build|\bTODO\b|\bFIXME\b|\bplaceholder\b|\blorem ipsum\b|\b[SNJ]-\d+(?:\.\d+)?[a-z]?\b
    a UTC stamp        \b\d{1,2}:\d\d(?::\d\d)?\s?(?:[AP]M\s?)?(?:UTC|GMT)\b|\b(?:UTC|GMT)\s?[+-]\s?\d|\b\d{1,2}:\d\dZ\b|\b20\d\d-\d\d-\d\dT\d\d:\d\d
    an em dash         U+2014

Result on 1,293 pages: **missing 0, undefined 0, NaN 0, null 0, None 0, $0 0, 0 pieces 0, 1 pieces 0, a raw entity 0, an internal note 0, a UTC stamp 0, an em dash 0.** To run it again on any pages: `python3 clean_canary.py --url https://gocheckmysports.com/ https://gocheckmysports.com/scores`. The UTC pattern wants a time beside the letters because "UTC" alone is Chattanooga's abbreviation on its cards. Empty sections, empty cards and text cut mid-word need a browser; that read is the gate's (`clean read, every page type`: 72 pages of 25 kinds at 375 and 1440, 61,221 text elements, 0 findings).

**Lighthouse** 12.8.2, mobile, 15:48 UTC: `/` performance 100, accessibility 100 (LCP 1.7 s, TBT 20 ms, CLS 0.003); `/scores` 100 and 100 (1.6 s, 0 ms, 0); `/games/401873079` 99 and 100 (1.9 s, 0 ms, 0). A report, not a gate.

**At 375 by 812 on the home:** the band ends at 633px, the open day's first card begins at 719px (it began at 1,031px before merge 13), the tab bar begins at 759px.

## What each item built

1. **Fresh, the re-read** (`69aeaf1`). A deploy every ten minutes through a week's windows is more than the team's Netlify credits (about 1,080 deploys a month at 15 credits against 15,000), and the September 21 ruling says a number changing is not a deploy. So builds stay on the J-17 schedule, and between them, while a game window is on, the scores job reads the feed every five minutes, renders the home and Scores with the site's own builder (4 seconds against 190), and commits the board's parts under `site/data/live/`; the pages read that file from the repository and replace their board, counts and stamp in place, as the inactives board has since September 21. A run holds its window by ticking itself and hands over to a new run before GitHub's six-hour limit. Every tick reads the feed (until now a tick fetched only when the committed snapshot showed a game near kickoff, which is why Tuesday's two games were never read).
2. **Quiet** (`47207e2`). A dead source feed and an Edition gap warn and open their issue; they no longer fail a run. The push relay test's one-in-256 false red is closed. `review/` joins the no-build paths.
3. **Honest** (`8ebe34e`). A stamp from another ET day carries its date; a reading over 15 minutes old drops the "refreshed every 5 minutes" tail; a card past kickoff with no state says "No update since" with the reading's time; a final's clock is printed only when the desk saw it; no stamp falls back to the build's clock.
4. **Readable** (`d0a589e`). TV before streaming, never radio; networks by name; no "Conditions unavailable" on a game in play or final; the Scores hero's days are one scrolling row on a phone, which lifts the first card from 811px to 570px.
5. **Fresh, who starts the run** (`00a62d0`). Below, under point 1.
6. **Whole** (`ab8d129`). Two dead links retired, a self-canonical on noindexed pages, none on the 404 page, and the link, head, sitemap and width reads as gates.
7. **Clean** (`1ec5e83`). A long team name wraps where it was cut; a one-plate wall row wraps; an Edition with no rail draws no empty rail; the word scan and the browser's truncation and empty-box read as gates.
8. **Current** (`08cf916`). The fantasy week is the calendar's; the hub draws this week's lists only; each surface carries its data's stamp; a story lane with nothing new in 14 days comes off the navigation, the footer and the home and its hub prints one dated line.
9. **Found** (`7f2b896`). The phrase in the title, the description and under the masthead; About rewritten to who runs it; `SportsEvent` for the day's games on the home and Scores.
10. **Fast** (`a3801f7`). The one accessibility fault Lighthouse named (an `aria-label` on an element with no role) and two roles on the possession and timeout marks; the two new scripts ship tight (3,600 bytes pinned).
11. **Beautiful enough** (`d004423`). Listed in the scorecard's row 10.
12. **The copy law's word** (`17470c5`). The Scores hero reads "Scoreboard". A day's page keeps its day in the heading for a screen reader and a crawler; the eye has it on the lit day tab.
13. **The home's first glance at 375** (`a02c209`). The board comes before the lead in the markup (Sprint A's A6 drew the lead first), and under 720px the space over the first card comes in. At 1100px and up the wall is still the first view.

## Byte pins

- `HOME_BUDGET` 140,000: **held.** Production's home is 136,611 bytes. Inside it the home now draws today's college games first, so on this week's slate it draws 13 of 64 college games where main drew 16: the `SportsEvent` block and the live parts' attributes are inside the budget too.
- `PAGE_BUDGET` 150,000 and `SCORES_PIN` 240,000 (`build_cost_canary.py`): **held**, unchanged. Production's `/scores` is 37,420 bytes.
- `SCRIPT_PIN` 3,600 (`fast_canary.py`): **new**, the shipped bytes of the two scripts this session added (`LIVE_JS`, `HONEST_JS`). No old value.
- `NODE_MIN_CHECKS` (`push_canary.py`, a floor on the push relay's own checks): **re-pinned, 40 to 41**, for the one check item 2 added.
- `site/assets/site.css` carries no pin: 213,752 bytes on `5b9e395`, 219,317 on `a02c209`.
- No other pin was touched.

## Point 8, Quiet: the last seven days of runs (read November 25, 09:20 UTC)

557 runs created from November 18, 09:00 UTC: 533 success, 21 skipped (`sports-news-brief.yml`, off by ruling), 3 failure, 0 cancelled. By workflow: conditions-report 9 of 9 success; inactives 480 of 480 (470 by the Worker, 10 by cron before the cron was removed); janitor 7 of 7; scores-cadence 33 of 33, all `schedule`; health 1 success, 2 failure; verify 3 success, 1 failure.

- `health.yml` 45298417199 (Nov 24, 00:35 UTC) and 45487565359 (Nov 24, 21:05 UTC, the 7:03 AM cron delivered at 4:05 PM ET): both real. "Scores went 4.9 hours without a new reading while games were on" (Sunday night) and "19.1 hours" (Monday night through Tuesday). The cause is point 1's. 45497807049 (22:07 UTC) stood down as the day's second gate.
- `verify-sports-pipeline.yml` 45238565129 (Nov 23, 18:27 UTC, scheduled): class C2, three layout findings at 320 on the day's data. Since S-61 (`0aca29f`) those are warnings; the three runs after it are green.
- Classes A, B, D, E, F in the seven days: 0 runs.
- Two paths could still fail a run for less than an outage and are closed in item 2: a dead source feed in the weekly Layer 2 job (exit 3 failed the job; it now warns and opens its issue), and the brief's "Edition gap" step (`core.setFailed`; a warning now, as on Crypto since N-1; the job is off). A third was a false red: the push relay test's own key (about one run in 256, CI run 45298380007).
- Kept as real failures: the Layer 1 canary on a push to main, the brief's push after three attempts and its Edition stage (both off with the job), `odds_gate.py` in the scores job, the conditions report's build, the inactives poller's first red tick (`poller_alarm.py`), and the health gate itself.

## Point 1, Fresh: what was read

- `scores-cadence.yml` runs since November 23: 14 runs from November 22, 17:45 UTC to November 25, 07:11 UTC, every one `schedule`, none `workflow_dispatch`. The Worker is not dispatching it.
- The Worker's status page, read at a due minute (November 24, 17:25:03 UTC, 12:25 PM ET, an hour in `SCORES_ET_HOURS`): `due_this_tick` is `[]`, `token_ok` true. gcm-newsroom main (`2f1f538`) carries `scoresDue` since `86a6329`, so the source is right and the deployed Worker is not that source. The window logic, the workflow name (`scores-cadence.yml`, which takes `workflow_dispatch`) and the token (it dispatches `inactives.yml` in the same repository: 470 `workflow_dispatch` runs in seven days) are all correct. The one cause left is the deploy itself: made from a checkout that did not hold `86a6329` (N-1 merged on GitHub from a cloud session at 01:43 UTC November 22), or a deploy that did not complete. Jack's action is under "Jack's".
- A second cause, in this repository, found on the night of November 24: `cadence.py` fetched the feed only when the COMMITTED snapshot showed a game near kickoff, and that file is rewritten only when a build is due. Tuesday's was Monday night's (`5b9e395`, 01:57 UTC), which held no Tuesday game. Runs at 20:36, 23:42, 05:42 and 07:11 UTC each logged `cadence: not due, no game near kickoff in the committed snapshot` (run 45555393018). Both Tuesday college games were played and production read them "Upcoming, Tue 7:00 PM ET" under "Scores as of 6:00 AM ET" at 4:12 AM ET Wednesday (stamp `5b9e395`, built 2026-11-24T11:00:53Z).
- A third: the schedule itself. `cadence.py` builds every 30 minutes on Saturday and Sunday and at kickoff, halftime and final on Monday and Thursday, so with every tick delivered the stamp is 30 minutes old on a weekend and up to 90 on a Monday. Inside 15 minutes by building is a build every 10 minutes through about 42 window-hours a week: about 250 production deploys a week, 1,080 a month, at the 15 credits `netlify_ignore.py` records, 16,200 credits against the team's 15,000. The September 21 pause was this arithmetic.
- The cure is the September 21 ruling applied to scores ("a deploy changes what the site says; a number changing is not a deploy"): between builds, each tick commits the board as the site's own renderer draws it, and the page reads it from the repository, as the inactives board does. Builds stay on the J-17 schedule.
- Item 1 as built: every tick reads the feed; `cadence.window` and `cadence.hold` (a run that finds a game on, or a kickoff inside six hours, ticks every five minutes itself and hands over to a new run at 320 minutes, so one delivered cron tick carries a whole day); `live_board.py` renders the home and Scores with `site_build.build()` in LIVE_TICK mode (the same code path; 4.2 s against 191.7 s for the full build, and byte for byte the full build's parts on the fixture slate: 7 of 7) and commits `site/data/live/home.json`, `scores.json` and the reading; the pages take a file only for their own stylesheet hash and day and only when newer; `netlify_ignore.py` skips a push that touches only `site/data/live/`; the health gate counts a re-read as a reading. The stamp reads "Scores as of 3:43 PM ET, refreshed every 5 minutes" in a window and "..., refreshed every 5 minutes from Thu 1:00 PM ET" before one.
- What it adds: `raw.githubusercontent.com` as a host on the home and Scores (the inactives page has read it since September 21), and about 150 small commits to main on a full Saturday (the inactives poller already commits every five minutes in its windows).
- **Who starts the run (item 11, built after merge 2).** Read on November 25: GitHub delivered this workflow's cron at 20:36 and 23:42 UTC on the 24th and at 05:42 and 07:11 on the 25th, four of about 100, and the 7:03 AM health cron of the 24th ran at 21:05 UTC, ten hours late. One delivered tick carries a day only if it lands in the six hours before the first kickoff; a Thanksgiving 1:00 PM kickoff has no such promise. The Worker's tick is the cure and it is Jack's deploy. Until then, three things in this repository, none of them a new trigger on a clock: (1) the runs the Worker does dispatch here, on time (the inactives poller every five minutes in its windows; the evening brief's three fires at 6:40, 7:10 and 8:10 PM ET, whose own job is off), each gain a `scores-start` job that starts the scores run when none is queued or running and none ended clean in the last 20 minutes (`cadence.py --start`); (2) a scores run started while an older one holds the window ends in its first step (`cadence.py --aside`), and the workflow's concurrency group is gone, because a group left every extra tick pending for hours and each new one cancelled the one before it: after the Worker deploy that would have been five cancelled runs an hour through every window; (3) with no Worker tick on record in four hours, a run waits for a kickoff up to 16 hours off (six with the Worker), so a night game's run carries to the next day's first kickoff. That is a runner asleep, waking every 30 minutes, whenever a kickoff is inside 16 hours: most of the hours between Tuesday night and Sunday night in season, on a public repository's free minutes; the Worker's first tick retires it with no change here. What (1) to (3) do not cover: a weekday afternoon game on a day with no game the night before and no cron delivered.
- A fault this item's own first draft carried, caught before it was committed: a one-line `run:` holding `": "` does not parse as YAML, and GitHub fails such a run before it starts. `scripts/n1_workflows_test.py` now reads every workflow for that.
- Not proved until a game window passes on production: that a held run ticks through it, and the three reads of the public stamp. The next windows are Wednesday November 25 from 8:00 PM ET (Green Bay at the Rams) and Thursday November 26 from 1:00 PM ET (three NFL games and Texas Tech's).

## Named, so nobody finds it later

- **The pages now read one file from GitHub.** The home and Scores fetch `raw.githubusercontent.com/jaybiz0131/gocheckmysports/main/site/data/live/` (the inactives page has read that host since September 21). If it does not answer, the page stands as built and its stamp says how old it is.
- **Commits to main.** A held window commits a re-read every five minutes when the board changed: about 150 small commits on a full Saturday, none of which builds.
- **A runner asleep between game days**, until the Worker's deploy: with no Worker tick on record, a scores run that finds a kickoff inside 16 hours waits for it, waking every 30 minutes. In season that is most nights from Tuesday to Sunday, on a public repository's free minutes. The Worker's first tick brings the wait back to six hours with no change here.
- **Two day tabs of one name** can only happen for a kickoff between midnight and 6 AM ET on a Tuesday; the gate's slate has one and the home pairs tabs and sections by order, not by name.
- **A final's clock** is printed only when the desk read the final within 5.5 hours of kickoff. A final first read the next morning prints its day.
- **The home's lead** ("Latest finals") now follows the board at every width. One line in `site_build._render_home` puts it back.
- **The inactives page** asks for today's UTC file before the first list exists and the browser logs that 404; nothing is drawn wrong. Older than this session, left as it is.
- **Not done, and why.** No Netlify setting and no Worker code was changed (Jack's). No new test tool was built beyond the gate's checks; the production crawl and the screenshot scripts are scratch files of this session and are not in the repository.

## Jack's

1. **Deploy the Worker from current main.** On the Mac:

       cd ~/Desktop/"Berno Projects"/gcm-newsroom
       git pull origin main
       git log -1 --format=%h -- slot-trigger/src/worker.js     # must print 86a6329, or later
       grep -c scoresDue slot-trigger/src/worker.js             # must print 4
       cd slot-trigger && npx wrangler deploy

   Then, at a minute ending in 5 between 10 AM and 2:59 AM ET: `curl -s https://gcm-slot-trigger.gocheckmybrands.workers.dev/` lists `gocheckmysports/scores-cadence` in `due_this_tick`. No secret changes. Optional, in the same deploy: `docs/REPORTS/S-DONE-worker.patch` (6 lines, `git apply` from gcm-newsroom's root) adds `build` and `scores` to that page, so a deploy can be checked at any minute; the Worker's three test files pass with it (18, 31 and 95 cases).
