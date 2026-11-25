# S-DONE report: the whole site to 8 of 10 and self-running

Session opened Tuesday, November 24, 2026, 12:10 PM ET (17:10 UTC) on gocheckmysports, with gcm-newsroom cloned read-only; stopped at 12:40 PM ET by the owner and resumed Wednesday, November 25, 4:05 AM ET (09:05 UTC) in a fresh container (the first was reclaimed; nothing was lost, nothing had been committed). `docs/RULES.md` body hash at the opener (everything below the header's rule): `2b3ddc0f60f3f5433f9ef67409833dcc53186b1e486d4d4c6942eb0b9d365211`, equal to the header's. No trailer in any commit message (`commit_trailers.py`: 0 hits). This file is the running scorecard: it is updated after every merge.

## Scorecard (updated after every merge)

A report cannot carry its own merge hash, so each merge's copy of this file names the merges before it; the last section of the final copy names them all.

| # | Point | State | Evidence or reason |
|---|---|---|---|
| 1 | Fresh | merged as item 1 (`69aeaf1`); **red until a game window is read on production** and, for the Worker's half, until Jack's deploy | the re-read (below); the first run of the new job on GitHub (45597456275, 10:41 UTC) |
| 2 | Honest | built (`sdone-3-honest`), at its gate | `S-DONE-logs/plants-2-honest.log` |
| 3 | Readable | built (`sdone-4-readable`), at its gate | `plants-3-readable.log` |
| 4 | Clean | built (`sdone-6-clean`), behind 3 and 5 | `plants-4-clean.log` |
| 5 | Whole | built (`sdone-5-whole`), behind 3 | `plants-5-whole.log` |
| 6 | Fast | built (`sdone-9-fast`), behind 9 | Lighthouse 12.8.2 mobile on production (stamp `5b9e395`), November 25: home 95 and 96, Scores 96 and 100, a game page 100 and 100 |
| 7 | Current | built (`sdone-7-current`), behind 4 | `plants-7-current.log` |
| 8 | Quiet | merged as item 2 (`47207e2`) | the seven-day run tally (below); the health gate's next run is the read |
| 9 | Found | built (`sdone-8-found`), behind 7 | `plants-9-found.log` |
| 10 | Beautiful enough | built (`sdone-10-beauty`), last | `plants-10-beauty.log`; before screenshots in `S-DONE-shots/` |

## Merges, in order

| # | Item | Merge | Parents | Pushed (UTC, Nov 25) | U-8 | Production read by stamp |
|---|---|---|---|---|---|---|
| 1 | Fresh: the re-read (`sdone-1-fresh`) | `69aeaf1` | `5b9e395`, `b0e7d8b` | 10:33:31 | HEAD `69aeaf1` = origin/main `69aeaf1`, 0 ahead | `69aeaf1`, built 10:33:49; home and Scores at 375 and 1440: "1 game today", "Scores as of 5:33 AM ET, refreshed every 5 minutes from 8:00 PM ET", 32 games on the home each once, no sideways scroll (`S-DONE-logs/prod-read-69aeaf1.log`) |
| 2 | Quiet (`sdone-2-quiet`) | `47207e2` | `69aeaf1`, `0c02372` | 10:40:52 | HEAD `47207e2` = origin/main `47207e2`, 0 ahead | read as `12c3053` (the snapshot commit on top of it), built 11:00:43: the same four reads, "Scores as of 6:00 AM ET, refreshed every 5 minutes from 8:00 PM ET" (`prod-read-12c3053.log`) |

Each merge commit's tree is the gated commit's tree, hash for hash (`697a5029` and `97829f26`). IndexNow by hand after each: `/` and `/scores`, HTTP 200 both times. Count of record (the Worker's `/counts/today`, 11:55 UTC): gocheckmysports production ready 4 on 2026-11-25 (`69aeaf1` 10:37:15, `47207e2`, `12c3053` 11:03:34, and the 6:00 AM hook build).

The first run of the new scores job: 45597456275, `workflow_dispatch` by this desk at 10:41:54 UTC (not the Worker: it is the only dispatch on record for this workflow), success in 16 seconds. It read the feed, found Tuesday's two finals against Monday's committed snapshot, and pushed `12c3053` "scores: snapshot 10:42Z" (one file), which built. It spends no model key (U-4).

## The gate (U-12, U-15, U-16)

The harness that runs this session ends a foreground command at 10 minutes and the gate takes 19 to 21, so every `preflight && push` ran as one tracked command, its output to a file, its chain status written by the command itself and read after it exited. Each ran in its own git worktree of the commit under test, so the next item was built while a gate ran. Items are stacked (each branch on the one before), and an item's gate runs on its branch tip; when main has not moved, that tree is the merge commit's tree, hash for hash, and the merge is pushed on that gate.

| Tree | Started (UTC) | Load at start | Exit | Reds | Warnings | Log |
|---|---|---|---|---|---|---|
| main `5b9e395`, the baseline | Nov 25, 09:19:01 | 0.75 | 0 | 0 | 5 | `S-DONE-logs/gate-main-5b9e395.log` |
| item 1 `99ee766`, `preflight && push` | 09:37:04 | 1.68 | 1 | 3, none on the site: `truth` twice (its matcher and its own plant read the stamp tag as `data-mf="stamp">`, which now carries `data-asof`) and `home` (its matcher read the lead slot's tag without `data-live`); nothing was pushed | 5 | `S-DONE-logs/gate-1-99ee766-red.log` |
| item 1 `b0e7d8b`, `preflight && push` | 10:00:28 | 0.77 | 0 | 0 (59 fixture tests) | 5 | `S-DONE-logs/gate-1-b0e7d8b.log` |
| item 2 `0c02372`, `preflight && push`, beside item 1's | 10:00:28 | 0.77 | 0 | 0 (59 fixture tests) | 5 | `S-DONE-logs/gate-2-0c02372.log` |
| the whole stack `8e05c8a`, a shake-out before the per-item gates, no push | 10:41 | not read | 1 | 4 of 69, all older checks holding the behavior item 7 changes: `small` (it handed the fantasy hub a box score for a game the reading does not hold) and `home` three times (it wanted the footer to link Storylines, The Record and The Edition); both moved to the new truth in item 7's commit | 5 | `S-DONE-logs/gate-stack-8e05c8a-red.log` |

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
- Not proved until a game window passes on production: that a held run ticks through it, and the three reads of the public stamp. The next windows are Wednesday November 25 from 8:00 PM ET (Green Bay at the Rams) and Thursday November 26 from 1:00 PM ET (three NFL games and Texas Tech's).

## Jack's

1. **Deploy the Worker from current main.** On the Mac:

       cd ~/Desktop/"Berno Projects"/gcm-newsroom
       git pull origin main
       git log -1 --format=%h -- slot-trigger/src/worker.js     # must print 86a6329, or later
       grep -c scoresDue slot-trigger/src/worker.js             # must print 4
       cd slot-trigger && npx wrangler deploy

   Then, at a minute ending in 5 between 10 AM and 2:59 AM ET: `curl -s https://gcm-slot-trigger.gocheckmybrands.workers.dev/` lists `gocheckmysports/scores-cadence` in `due_this_tick`. No secret changes. Optional, in the same deploy: `docs/REPORTS/S-DONE-worker.patch` (6 lines, `git apply` from gcm-newsroom's root) adds `build` and `scores` to that page, so a deploy can be checked at any minute; the Worker's three test files pass with it (18, 31 and 95 cases).
