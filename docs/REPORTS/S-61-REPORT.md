# S-61 report: the gate judges the code, not the day's games

Session of Monday, November 23, 2026, from 5:28 PM ET (the container up at 22:28 UTC) into November 24, one Claude Code cloud session on gocheckmysports with gcm-newsroom attached read-only. `docs/RULES.md` body hash at the opener (`tail -n +11 docs/RULES.md | sha256sum`): `4179b2ac06d0dc7fb9de9987dc077884df6f4e1b5ebabe1b6ff1bb2de8b3568d`, equal to the header's. Re-pinned by this session to `2b3ddc0f60f3f5433f9ef67409833dcc53186b1e486d4d4c6942eb0b9d365211` (U-14's second paragraph, below). No trailer in any commit message (`commit_trailers.py`: 0 hits). Branch `s61-gate-split`. Logs: `docs/REPORTS/S-61-logs/`.

## Merged (U-8: local equals origin, 0 ahead, after every push)
- S-61: `0aca29f`, merge of `s61-gate-split` (`307d872`, `46f2d29`, `f61c063`, `c2ecb76` the N-1 patch by `git am`; `dfaa10d` part 4; `8e85aae` parts 1 to 3) onto `ed8282b`. Pushed 00:35 UTC November 24. HEAD `0aca29f` = origin/main `0aca29f`, 0 ahead.
- S-60: `61a8436`, merge of `claude/s60-scoreboard-state-tabs-96a7of` rebased onto `0aca29f` (`85607b9`, `100c940`, `7b1647b`, `d651cce`) onto `3df41c5`. Pushed 01:19 UTC. HEAD `61a8436` = origin/main `61a8436`, 0 ahead.
- Branch pushes: `s61-gate-split` at `8e85aae` (after the 23:44 UTC gate; local = origin, 0 ahead); `claude/s60-scoreboard-state-tabs-96a7of` from `1a846b6` to `d651cce` (a rebase, `--force-with-lease` against `1a846b6`).

## The gate, status read from the command (U-12, U-15)
| Tree | Started (UTC) | Load at start | Exit | Reds | Warnings | Log |
|---|---|---|---|---|---|---|
| main `93dc3c0` before S-61 | Nov 23, not stamped | not read | 1 | 7: plate fit `/games/401858528.html` at 320 (`sbc-tot` "18" and "16"), plate same `index.html` at 320 (`sbc-big`), measure (Lighthouse not found), performance `/index.html` and `/games/401873066.html` not measured, the slow fixture | 0 | `main-93dc3c0-canary.log` |
| branch, first run | Nov 23, 22:59:41 | 1.80 | 1 | 1: `replay e2e` FileNotFoundError, my kind constant `FIXTURE` shadowed the sample feed path; renamed `FIXTURE_TEST` | 6 | `gate1.log` |
| branch, the tree of `8e85aae` before its commit | 23:17:44 | 3.88 | 0 | 0 | 6 | `gate2.log` |
| `8e85aae`, `preflight && push` | 23:44:47 | 0.23 | 0 | 0 | 6 | `preflight-push2.log` |
| merge `e343030`, `preflight && push` | Nov 24, 00:01:28 | 4.03 | 0 | 0 (push rejected: main moved by `inactives: snapshot 00:01Z`; nothing landed) | 6 | `preflight-merge1.log` |
| merge `0aca29f`, `preflight && push` | 00:18:48 | 2.99 | 0 | 0 | 6 | `preflight-merge2.log` |
| S-60 rebased `d651cce`, `preflight && push` | 00:45:51 | 0.02 | 0 | 0 | 7 | `preflight-s60.log` |
| S-60 merge `ff44d48`, `preflight && push` | 01:02:51 | 3.80 | 0 | 0 (redone on `3df41c5`) | 7 | `preflight-merge-s60.log` |

The worker process restarted once during the first `preflight && push` of the branch (`preflight-push1.log`, started 23:34:34 UTC, cut off in the plate sweep); the run was killed before the push and nothing landed. Its throwaway build's 7 data rewrites were restored from the index, and the whole `preflight && push` was run again.

Main moves every five minutes while the inactives poller runs, and a gate takes 15 minutes, so each merge push ran through a guard (in the session's scratch directory, not committed): after a green gate, if main had moved only by commits touching `site/data/` or `data/`, the merge was redone on the new tip and pushed; anything else stopped the push. On S-61 the guard did not act (main was still `ed8282b`). On S-60 it acted once: `61a8436` differs from the gated `ff44d48` only by `3df41c5` (`inactives: snapshot 01:07Z`, 5 files in `site/data/`).

## The five parts
1. **Two kinds of check.** `verify_pipeline._run(kind, name, fn)`. A fixture test's findings fail the gate. A live canary's findings each print `::warning::live canary (NAME): FINDING`, are listed again at the end, and `_run` returns nothing to the gate, whatever the canary returns or raises. Every check in the gate runs through it; `docs/TESTS.md` is the table. `_runner_canary` (a fixture test) plants a canary returning two findings and one that raises, and requires an empty return and three recorded warnings. `python3 verify_pipeline.py plant` shows a planted canary failure as a warning with exit 0 (`S-61-logs/plant.log`).
2. **The floor is 375.** The fixture slate is a second `build()` with the scoreboard fixed to `fixtures/n1/scoreboard-2026-11-21T2043Z.json` (byte for byte the S-60 fixture), moved onto the run's clock. It runs last in the gate. `slate layout 375 and 1440` (fixture test): no plate clipped and no page wider than the viewport on the home, every Scores page and every game page (139 to 140 pages). `slate layout 320` is a canary. `scripts/plate-fit.mjs` now also reads the page's own width (`documentElement.scrollWidth`). Two parts moved to canaries: the day's build in the browser (`plate fit and plate same`, 21 widths) and `look rendered`. The plate label fixtures under 375 warn; at 375 and wider they fail. No fixture failed at 375 on main, so there was no bug to fix there.
3. **Lighthouse is optional.** `measure_canary.lighthouse_where()` resolves `lighthouse/package.json` beside Playwright. If it is absent, one warning names it and the read is skipped; if present, scores print and a score under 90 warns. Structured data and console errors stay fixture tests. The last Lighthouse scores read: CI run 45238565129 on `93dc3c0`, November 23, 18:42 UTC, Lighthouse 12.8.2 mobile: `/index.html` 99 (runs 99, 99, 98), `/games/401873066.html` 99 (99, 99, 99), slow fixture 61.
4. **N-1 landed, fixed.** `git am --3way` of `N-1-sports-n1-reliability.patch` applied clean onto `93dc3c0`. The defect: a `feed_lag` game (state rewritten to `in`) had its chip row drawn live. Now `_tk_matchup` draws the plain matchup with the reading's "No update since" time in `.tk-stale` (the review color). `_tk_marks` and `_tk_redzone` draw nothing for it, `_sb_status` prints the stale line with no live dot, and the kicker dates the card. `health.yml` is on main. The expected-cron register (`jobs_canary.EXPECTED`) has `health.yml: 2`, inactives Worker-only, and `desk.json` registers it; the `jobs` check is green.
5. **S-60 landed.** Rebased with two conflicts in `verify_pipeline.py` (S-60's `s60` and `s60 tree scan` calls, now fixture tests under the runner) and one in `site_build.network_name` (S-60's table taken, so ERADM prints "Check local listings"; N-1's ERADM test moved to that truth, and no card prints ERADM either way). One combined defect found and fixed: `s60.live_label` read N-1's "2OT as of 3:43 PM ET" as a clock and printed "2OT 3:43". Every S-60 fixture is green at 375 and 1440 on the slate: 8 "USA Network" chips drawn, 0 findings at 375 or 1440, 0 at 320. The cadence line now reads "Scores as of 3:43 PM ET, refreshed every 30 minutes when the run fires" (below). The S-60 report carries one added line with its merge hash.

## Tests, each seen red first (U-9), break named
| Test | Red | Plant (restored from a saved copy) |
|---|---|---|
| `n1_scores_test` chip row, 5 new cases | 4 named on the N-1 code: score chip, live dot, stale style and time, band status | `feed_lag` guard on `started` removed: 3 red |
| `_runner_canary` | n/a, new runner | canaries returning their findings: 2 named red, `plant` exit 1 |
| `slate layout 375 and 1440` | 0 findings on main's slate | `.tk-chip-score{min-width:400px}`: 9 fixture failures at 375, the page 458 wide in 375 |
| gate split (parts 2 and 3) | main `93dc3c0` exit 1 on 7 reds | the same 7 now warnings, exit 0 |
| `n1_scores_test` BYU 2OT after rebase | "the BYU card prints '2OT as of 3:43 PM ET'" | the `" as of "` guard in `live_label` removed: red |
| `s60_canary` cadence | "cadence on a Saturday: got ', refreshed every 30 minutes'" | n/a, the wording changed |

## The table of checks
`docs/TESTS.md`: 58 fixture tests under the runner plus the inline group, and 4 live canaries. **Moved from gate to canary: 3** (`look rendered` on the day's pages, `plate fit and plate same` on the day's pages, `performance`). One canary is new: `slate layout 320`, the 320 half of the new fixture slate check.

## Warnings the canaries printed on the day of the merge (S-60 merge gate, 01:02 UTC November 24)
1. plate fit: `/games/401858528.html`, `/teams/cfb/jacksonville-state.html`, `/teams/cfb/minnesota.html` and 3 more at 320: the page is 331 wide in 320
2. plate fit: `/teams/cfb/jacksonville-state.html`, `/teams/cfb/tennessee-tech.html` at 340: the page is 348 wide in 340
3. plate fit: `/games/401858528.html` at 320: `span.sbc-pl.sbc-tot` "18" off the viewport 291..331 of 320
4. plate fit: `/games/401858528.html` at 320: `span.sbc-pl.sbc-tot.sbc-lose` "16" off the viewport 291..331 of 320
5. plate same: `index.html` at 320: `span.sbc-big` 77.33x39.19 on main, drawn 82.7x39.19 (3 plates)
6. plate same: `games/401856746.html` and 35 more at 900: `span.sbg-big` 45x68.8 on main, drawn 45x64.72 (144 plates; S-60's game page change)
7. performance: Lighthouse is not installed beside Playwright on this machine, so the performance read was skipped

The S-61 merge gate (00:18 UTC) printed 1 to 5 and 7.

## Read live
- Production `/stamp.txt`, 01:22 UTC: `commit 61a843620f33df4e00102dfd0ba27648d1ba4d3e`, `built 2026-11-24T01:19:53+00:00`.
- `scripts/prod-read.mjs --commit 61a8436`, 375 and 1440, `/` and `/scores.html`: build-commit `61a8436` on all four reads, no sideways scroll, "1 game today", "Scores as of 8:19 PM ET"; the home 40 games, each once; `/scores.html` 1 game (CIN at WSH, Live 1, Upcoming 0, Final 0). The word "live" is on `/scores.html` as S-60's Live tab, which `truth_canary` allows on Scores pages. Four screenshots were taken (home and Scores at 375 and 1440, light) and are not committed: `netlify_ignore.decide` counts `review/` as a site change, so committing them would build production for a documents commit (U-11).
- IndexNow by hand, 01:22 UTC: `/` and `/scores.html`, HTTP 200.
- Count of record, the Worker's `/counts/today`, 01:22 UTC: gocheckmysports production ready 8 on 2026-11-23 (7 at 01:19 UTC, before the `61a8436` build).
- The Worker's `/`, 00:45:05 UTC (7:45 PM ET, a :x5 minute in the scores hours): `due_this_tick` is `["gocheckmysports/inactives"]` only. The N-1 Worker change that dispatches `scores-cadence.yml` is not deployed.
- **Sports health gate:** `health.yml` is on main. Its first run (workflow_dispatch 45298417199, 00:35 UTC, on `0aca29f`) concluded **failure**, and the cause is real: "Scores went 4.9 hours without a new reading while games were on: 'Scores as of' read Nov 22, 8:05 PM ET until Nov 23, 12:58 AM ET (MIN at SF)." GitHub's cron missed the Sunday-night ticks, which is the gap the Worker tick closes. Its first green run waits on that deploy.
- CI on push: `verify-sports-pipeline.yml` on `0aca29f` (run 45298380007) failed on `push relay (node)`: 4 checks with the keyed relay (`readVapid()` null), "only 36 check(s) ran". This is not S-61's code. `netlify/test/push.test.mjs` makes a fresh key with ECDH every run, and Node's `getPrivateKey()` drops a leading zero byte about one run in 256, so the private key is 31 bytes and `readVapid` refuses it. Locally the same code passed 40 of 40 in three gates. Failed jobs re-run (attempt 2); the run on `61a8436` (45304188107) was in progress at the report. U-3: read at the next check, not waited on.

## Open, and proposals
1. **Jack: deploy the Worker** (the diff is gcm-newsroom `86a6329`, `slot-trigger/src/worker.js`, already on gcm-newsroom main: `SCORES`, `SCORES_ET_HOURS`, `scoresDue(now)` dispatching `gocheckmysports/scores-cadence.yml` at :05, :15 ... :55 in the 6 AM ET hour and 10 AM to 2:59 AM ET, joined into `due` and `due_this_tick`). From gcm-newsroom: `cd slot-trigger`, then `npx wrangler deploy`. No secret changes. After it, the Worker's `/` lists `gocheckmysports/scores-cadence` at a :x5 minute in those hours. Then the desk's next session removes the three crons from `scores-cadence.yml` (and `jobs_canary.EXPECTED`, `desk.json`), and the cadence line returns to "refreshed every 30 minutes" read from the Worker's interval.
2. **The push relay test's flake:** generate the test VAPID key until `getPrivateKey()` is 32 bytes (or pad it), red first with a fixed short key.
3. **The 320 page width on game and team pages** (warnings 1 to 4): the line score's total column at 320 and two college team pages at 340; a Sports item if Jack wants 320 back above warnings.
4. **The hero number at 900 on game pages** (warning 6, S-60's change): re-pin `fixtures/plate-base` for `sbg-big` if 64.72 is the intended height.
5. **`s60_canary.py` run alone exits 0 on FAIL** (its `__main__`); inside the gate its list fails the run, so the gate is unaffected.
6. **Layer 2 sources** stays a separate notify-only job that exits 3 to open its issue (`docs/TESTS.md`, outside the gate).
7. `netlify_ignore` treats `review/` (screenshots, never published) as a site change; proposal: add it to the paths that do not build, red first with a screenshot-only commit.
8. `docs/VOCABULARY.md` exists in neither repository (gocheckmysports, gcm-newsroom); not read, said here.

## Byte pins
- `docs/RULES.md` body hash: `4179b2ac06d0dc7fb9de9987dc077884df6f4e1b5ebabe1b6ff1bb2de8b3568d` to `2b3ddc0f60f3f5433f9ef67409833dcc53186b1e486d4d4c6942eb0b9d365211`.
- S-60's own (its report): `SCORES_BUDGET` 150000 to 240000 and new `SCORES_PIN` 240000 for Scores pages only; `BUDGET`, `PAGE_BUDGET`, `HOME_BUDGET` held. S-61 moves no page-byte pin. `site.css` gains the `.tk-stale` rule (1 line plus its comment); no pin on it.

## Jack's
- The Worker deploy (open item 1). It also turns the health gate green, since it fails today on the Sunday-night gap.
