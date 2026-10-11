# Close, Sunday 11 October 2026: the red canary, the frozen desk, the email storm

Session start 10:06 AM EDT. Report written 10:59 AM EDT (shell clock, America/New_York). Nothing here is rounded or estimated unless it says "projection".

## Preflight

- RULES.md body hash by the repository's recipe (`tail -n +11 docs/RULES.md | sha256sum`, everything below the header rule): `4179b2ac06d0dc7fb9de9987dc077884df6f4e1b5ebabe1b6ff1bb2de8b3568d`. Equals the hash in the brief. Verified again on origin/main after both merges.
- origin/main at start: `8016e36` (ledger row, 2026-10-11T02:10:51Z). All branches were cut from origin/main, never from the generated `claude/...` branch.

## Item 0, the canary (branch s-canary-clock, merged)

The strategy desk reported five failures. The runner reports four. S-2 is real but only where ESPN cannot be reached; both are proven below.

| # | Failure | Cause | File and line (at 8016e36) |
|---|---|---|---|
| 1 | C-1 "the open line was overwritten by a later reading: None" | Fixture kickoff `2026-09-27T17:00:00Z`. `lines.log()` drops any game whose kickoff is more than `KEEP_DAYS` (12) old, so from 2026-10-09 17:00Z the logged game expired on the call that logged it and `for_game` returned None. | `verify_pipeline.py:2350` (fixture), `lines.py:38` (`KEEP_DAYS = 12`), `lines.py:107` (the cut) |
| 2 | C-1 "the latest reading was not kept" | Same cause, same read of an empty file. | `verify_pipeline.py:2359` |
| 3 | C-1 "the move was not counted: None" | Same cause. | `verify_pipeline.py:2361` |
| 4 | C-1 "the expiry sweep took a live game with it" | Same cause: the "live" game was the 2026-09-27 one. The other half of that case used a 2020 date and was correct. | `verify_pipeline.py:2366` to `2371` |
| 5 | S-2 "the build wrote no player pages" | The gate build calls `player_index.build()`, which fetches ESPN. When that fails, `load()` falls back to the committed `site/data/players.json` and refuses it once it is older than `STALE_HOURS` (30). That file was last committed 2026-10-09T00:04Z by the poller; only the poller and the brief refresh it, and both run this canary first. A gate whose input is refreshed only by what it gates. On the runner ESPN answers, so the build refetches and S-2 passes (the runner log of 02:55Z shows exactly four C-1 errors). In a clean clone with no ESPN it is red. | `verify_pipeline.py:671`, `site_build.py:11399` and `11400`, `player_index.py:43` and `193` to `203` |

Timeline check: the daily brief's last green run is #457 (started 2026-10-09T03:02Z); the first red is #458 (started 2026-10-09T23:40Z), after the 17:00Z expiry. The last edition on main is the 2026-10-08 Evening Brief.

Fix (`c6ad6a8`, in merge `2fd5ca2`): the C-1 kickoffs, the expired game and `log(..., now=)` all come from one clock, the run's own; the gate build gets a fixed, fresh, designated player index through `player_index.build/load` (restored in a `finally`), so it fetches nothing and writes nothing tracked.

### Red then green (each plant made in a separate copy of the tree; the real tree was never planted, so no restore was needed)

| Plant | Check that went red | Result |
|---|---|---|
| `lines.py`: `cur["open"] = r` on every reading | C-1 "open line was overwritten" | red (1 problem), message carries the overwritten reading |
| `lines.py`: no `moves` increment, no `now` update | C-1 "latest reading was not kept", "move was not counted: 0" | red (2 problems) |
| `lines.py`: cut moved to `now + 30 days` | C-1 all four (live game swept) | red (4 problems) |
| `lines.py`: cut moved to `now - 100000 days` | C-1 "a game months past its kickoff stayed in the file" | red (1 problem) |
| `site_build.py`: player page loop emptied (`for _p in []`) | S-2 "the build wrote no player pages" | red (1 problem) |
| unplanted fixed tree | none | `LAYER 1 CANARY: PASS`, exit 0, locally and on the PR runner (14:42Z) and in brief run 466 (14:47Z) |
| S-2 with `player_index._get` made to raise (ESPN unreachable), old tree | S-2 | red, reproduces the desk's failure |
| same, fixed tree | S-2 | `S2 FAILS: []` |

### Other fixed dates that would expire in 90 days

Method, not a hand read: the whole canary was run with the clock moved to 2027-01-14 (+95 days) using freezegun in a scratch directory (not in the repo). Result: `LAYER 1 CANARY: PASS`, exit 0. So no other fixture in the canary depends on today's calendar inside 95 days. Listed by kind:
- Expiring dates found: one, the C-1 kickoff above (fixed).
- Dates that look fixed but are inputs to functions given an explicit `now` (`byline_stamp`, `_sb._NOW_CACHE`, the `_gb`/`_g3` slate fixtures, `netlify_ignore` window fixtures, schedule fixtures dated 2026-09-17 to 2026-10-20): these carry their own clock and cannot expire.
- Not covered by this method: anything keyed on hour or weekday of the real clock rather than the date, and anything the live network changes (the canary build still reads ESPN for the scoreboard and boards; those degrade softly).

## Item 1, the Inactives poller (branch s-inactives-poller, merged)

Why it failed: not its own cause. Its "Rebuild and push" step ran `verify_pipeline.py canary` under `set -e` on every tick that saw a new inactive (`.github/workflows/inactives.yml:152` at 8016e36). The canary was red (item 0), so nothing was pushed, so the next tick saw the same inactives as new (log of run 1806: "14 new inactive(s) captured", because no snapshot had been committed since 2026-10-09) and failed again. The poller runs its own copy of the canary; that was the wrong design for a job whose product is a data snapshot, so it no longer does: the canary already gates every push to main (`verify-sports-pipeline.yml`) and every brief.

Fix (`8ebe198`, merged by `070045`; the branch also carries merge `6846dfd` of main): the step's gate is the build and the odds gate; `poller_alarm.py` makes a red gate fail the first tick of an episode, open one issue (title "Inactives poller: push gate red") carrying the last 40 lines, keep later red ticks green with a notice, and close the issue on the first green tick. Canary check `_poller_alarm_canary` pins the decision table and the workflow wiring.

Red then green: the new check run against the old workflow gave three problems (private canary copy, no alarm call, step not continue-on-error); with `decide` returning `("open", False)` it gave "first red tick must open an issue and fail the run"; with `decide("failure", True)` returning fail it gave "a repeat red tick must stay green"; restored from saved copies (`cmp` identical) it is green. A stub-`gh` simulation of 16 ticks (12 red, 1 green, 3 red): 2 failed runs, issue created, closed, created.

Failure emails, one per failed run:
- Before, measured: 138 failed runs on 2026-10-10 UTC (133 `workflow_dispatch`, 5 `schedule`), 38 failed on 2026-10-11 up to 02:55Z, 28 of them consecutive between 00:50Z and 02:55Z (runs 1779 to 1806). Run 1 of 2026-10-09 UTC at 00:05Z also failed, for a cause not examined.
- Projection for a Sunday window (15:00Z to 04:59Z, 14 hours, 12 ticks an hour): 168 failed runs.
- After: 1 failed run per cause (plus the one issue notification), however many ticks the cause spans.

Observed live: run 1807 (`workflow_dispatch`, 15:00:35Z, on `0700451`, the first tick on the new workflow) concluded success: "Rebuild and push" success, "Say why once" skipped, "Close the alarm" success (so `poller_alarm.py` ran under the job's `GITHUB_TOKEN`, listed issues, found none open and exited 0), and it pushed `af3e7d3 inactives: snapshot 15:02Z`, the first snapshot since 2026-10-09T00:05Z. The red path (issue creation, repeat notice, close) has run only against a stub `gh`; no issue titled "push gate red" exists.

## Item 2, standings

The standings file did not stop refreshing by its own job; there is none. `standings.refresh()` runs inside `site_build.py` at every build, and Netlify only builds on a commit that changes the site. Every commit after 2026-10-09T00:05Z was a ledger row marked `[skip netlify]`, because the canary blocked every real commit, so no build ran and the page aged to 62 hours (`standings: file is 62h old, past 30h`). The pipeline freeze and the standings freeze are one cause.

Read on production by stamp, after the merges:
- `/stamp.txt` at 10:52 AM EDT: `commit 070045164561b91c77ee6ede9780e8f8664ef78c`, built 2026-10-11T14:47:52+00:00 (merge of #101). The deploy before it was `2fd5ca2`, built 14:44:44Z.
- `/standings/nfl.html`: meta `build-commit` `070045164561b91c77ee6ede9780e8f8664ef78c`, "Updated 10:47 AM ET", no stale marker, AFC East BUF 3-1, NE 2-2, NYJ 1-3, MIA 0-4.

Open, structural: nothing in the repo rebuilds the site on a clock, so any stretch of 30 hours without a site-changing commit marks the tables stale again. A scheduled Netlify build hook (netlify_ignore.py already expects "a scheduled or hook build") would close it; not built, because it adds deploys against the 12 and 16 a day limits and that is Jack's number. The committed `site/data/standings.json` was `2026-10-09T00:03:59Z` until the poller's first successful push (`af3e7d3`, 15:02Z) rewrote it with the rest of `site/data`; builds alone do not commit it.

## Item 3, the hand-run brief

Run 466 (`workflow_dispatch`, main at `2fd5ca2`, started 14:44:25Z, 10:44 AM EDT, outside the quiet window): conclusion failure, and it published nothing.
- Canary: `LAYER 1 CANARY: PASS`, 14:47:55Z, in the run's own log.
- Gate reason, quoted from the log: "Slot guard: dispatched with no slot; standing down before any model call. Name a slot, or set breaking=true."
- Stories through the gates: none ran. Edition published: none. Cost: no model call, 0 tokens, $0. The run's red conclusion comes from its last step, "Edition gap over threshold; stories were unaffected" (`edition_check: newest edition is 63h old (2026-10-08, The Evening Brief ...), 0 stories published since`), which will stay red until an edition lands.
- Advisories in the same log, warnings only: kill_streak 1 development killed 8 times ('Joey Porter Jr. ruled out with illness'); dupe_audit 186 clusters of 653; twin_audit 2 pairs.

The dispatch was mine and named no slot. I stopped there as instructed ("quote the gate's reason and stop"). The decision, as one paragraph: the desk serves one slot now, `evening-brief` (`watcher.SLOT_DEADLINES`). Option A, dispatch again with slot `evening-brief` before 12:30 PM: an Evening Brief for 2026-10-11 would be written this morning, and because the slot guard checks origin/main for `2026-10-11-evening-brief`, the real 23:38Z cron (7:38 PM ET) would then stand down, so Sunday's afternoon games would never be in an edition; it also spends the model key by hand against U-4 (Jack's item 3 overrides that for one run). Option B, leave it to the 23:38Z cron: the canary is green on main, so tonight's run should publish normally with the day's results, but its push lands at about 7:42 PM ET, inside the 12:30 to 8:30 PM no-deploy window, so Jack either accepts that one build or holds the cron. Recommendation: B, and A only if Jack wants an edition visible before the quiet window starts.

## Merges and pushes (U-8: hashes, then count)

| Item | Branch tip | Merge into main | Parents | PR | Push check |
|---|---|---|---|---|---|
| 0 | `c6ad6a8` | `2fd5ca28d2b9fabd2f5d2dd34b826b3154813fe3` | `8016e36`, `c6ad6a8` | #100 | local HEAD and origin tip equal, ahead count 0 |
| 1 | `6846dfd` (merge of main into the branch over `8ebe198`) | `070045164561b91c77ee6ede9780e8f8664ef78c` | `2fd5ca2`, `6846dfd` | #101 | same |

Both merges were real merge commits made on GitHub (merge method "merge"); neither branch message, nor any commit in this session, carries an attribution trailer (grep of `origin/main..HEAD` messages for co-authored, session and generated lines: no match, run before each push).

## Counts

- Deploys today at 10:57 AM EDT, from the Worker's `/counts/today`: gocheckmysports production ready 4 (2 were already there at session start, 2 are the merges `2fd5ca2` and `070045`), deploy previews ready 2. Limit 16 on a Sunday; the poller's snapshot `af3e7d3` (15:02Z) changes files outside the skippable set, so it may add a build the counter had not shown at the time of this read; this close is docs-only and `docs/` is skipped by `netlify_ignore.py`, so it adds none.
- Canary runs this session: 1 on origin/main (red, 4 failures), 1 on the fix (green), 5 planted (all red as named), 1 at +95 days (green), 2 on PR runners (both green), 1 in brief run 466 (green). The runner canary took 1m44s and 1m34s; this sandbox takes about 4 minutes.
- Failing poller runs counted above; the brief runs 458 to 465 were all failures before this session.
- Model spend this session: none by me. Run 466 made no model call.

## Open

- The poller's red path in Actions (issue open, repeat notice, close) is unexercised; the green path has run once (run 1807).
- Edition gap: red until an edition is published (item 3 decision).
- The masthead date on production pages still reads "OCTOBER 8, 2026" (taken from the newest edition); seen on the standings page, not investigated.
- A scheduled rebuild for standings (item 2).
- Jack: option A or B above; whether a scheduled rebuild is worth deploys.

Ended: Sun Oct 11 11:02:46 EDT 2026 (shell date, ET).
