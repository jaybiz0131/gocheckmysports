# The checks, by kind (S-61, November 23, 2026)

The gate is `python3 verify_pipeline.py canary`, run by `verify-sports-pipeline.yml` on every push and
by every desk before a push (`preflight && push`, U-14). It runs two kinds of check, and the runner
(`verify_pipeline._run`) holds the difference, not the check:

- **Fixture test.** A fixed input (an inline case, a file under `fixtures/`, the repository's own code
  and workflows) or a code rule that holds for any data. Its findings fail the gate (exit 1).
- **Live canary.** Reads the day's data: the gate's own build of today's feed read in a browser, or a
  tool the machine may not have. Each finding prints one `::warning::live canary (NAME): FINDING`
  naming the page and the measurement, is listed again under `live canaries:` at the end of the run,
  and never touches the exit status. Whatever a canary returns or raises, `_run` hands the gate
  nothing (`_runner_canary` plants both on every run; `python3 verify_pipeline.py plant` shows it).

Jack's rulings of November 22, 2026 (U-14, second paragraph): the layout floor is 375, so a layout
check fails at 375 and 1440 on the fixture slate and only warns at 320; Lighthouse is a report, not a
gate; a desk may push its branch over reds that main already shows, and never merges over a red gate.

**The fixture slate.** `verify_pipeline._fixture_tree()` is a second `site_build.build()` with the
scoreboard fixed to `fixtures/n1/scoreboard-2026-11-21T2043Z.json` (the 3:43 PM ET reading of
Saturday, November 21, 2026: 70 college games, a kickoff the feed had not flipped, a 2OT card), moved
onto the run's clock by one whole-minute offset so its games are today's. Its other inputs are the
build's own. It runs last in the gate because its build resets `site_build`'s globals.

**"The day's build"** below is `_built_tree()`, the gate's build of today's feed. A fixture test that
reads it asserts a rule of the code that holds for any data (every link resolves, every page is in a
sitemap, one stylesheet, no off-token color in the CSS); none of these has been red on data in the 30
days N-1 read (its 13 C2 reds were all `plate` and `look rendered`, now canaries, and `performance`).

## Layer 1, `verify_pipeline.py canary`, in the order the gate runs them (the inline group is spread through it)

| # | Check (runner name) | Kind | Input | What fails it |
|---|---|---|---|---|
| 1 | conflict | fixture | the tree | a conflict marker, a script that does not parse (U-13) |
| 2 | trailer | fixture | git log | an attribution trailer in a commit message |
| 3 | workflow | fixture | `.github/workflows` | a workflow that does not parse or lost its guards |
| 4 | jobs | fixture | `desk.json`, workflows | a cron line gained or lost against the register (health.yml 2, inactives Worker-only) |
| 5 | cadence | fixture | inline clocks | the score cadence's ticks; S-DONE: the game window (on, soon, off), the hold and its hand-over, and a tick that does not read the feed every time |
| 6 | edition check | fixture | inline slots | one missed slot errors instead of warning |
| 7 | edition link | fixture | inline | the Edition link does not resolve |
| 8 | stale module | fixture | inline | the stale-module rule |
| 9 | home lead | fixture | inline | the home's lead |
| 10 | rain and windows | fixture | inline | a rain plate outside 0 to 100, a windows note not named by day |
| 11 | small | fixture | inline | the small truths (S-1 item 4) |
| 12 | poller alarm | fixture | inline | a red poller fails more than once |
| 13 | us date | fixture | the tree | a date not in US order |
| 14 | undefined name | fixture | the code | an undefined name |
| 15 | one definition | fixture | the code | a function defined twice |
| 16 | corpus integrity | fixture | `site/content` | a duplicate slug, a circular update |
| 17 | inline layer 1 | fixture | inline | config and models, prompt guardrails, shill and dedupe belts, standings zeros, the netlify ignore rule (S-DONE: a re-read under `site/data/live/` and a screenshot under `review/` do not build; a due snapshot and `site/reports/` do), H-12 and the other `_check` cases written in `layer1_canary` |
| 18 | stamp | fixture | the day's build | the build stamp in the meta tag and `/stamp.txt` |
| 19 | sitemap | fixture | the day's build | games out of the sitemaps, still built and linked |
| 20 | register | fixture | the day's build | a page in neither a sitemap nor the register |
| 21 | byline date | fixture | inline | H-5b |
| 22 | sunday slate | fixture | inline fixture | H-12 |
| 23 | truth | fixture | fixtures and the day's build | counts and stamps from one truth |
| 23a | s60 | fixture | `fixtures/s60-nov21-*.json` | the Live, Upcoming and Final tabs, card states, network names, one count, the cadence line |
| 24 | watch | fixture | fixtures and the day's build | Where to Watch by day and window |
| 25 | home | fixture | fixtures and the day's build | the home is the week board |
| 26 | conditions | fixture | fixtures | the conditions intake |
| 27 | strip | fixture | the day's build | the conditions on every card |
| 28 | gamepage | fixture | the day's build | the game pages |
| 29 | report | fixture | fixtures | the conditions report and its card |
| 30 | roof | fixture | fixtures | a roofed stadium reads like a dome |
| 31 | teams | fixture | the day's build | team pages, structured data, IndexNow |
| 32 | fbs | fixture | the day's build | the college slate is every FBS game of the week |
| 33 | look | fixture | the day's build | resolve, colors in the markup, one stylesheet, chrome, the S-2d look, CSS luminance and tokens, and a browser sweep that did not run or read too few pages |
| 34 | look rendered (the day's pages) | **canary** | the day's build in a browser | a color or an Oswald glyph the day's pages render outside the token set |
| 35 | plate | fixture | label fixtures | the blind fixture not reported clipped; the longest label clipped at 375 or wider; a sweep that did not run |
| 36 | plate fit and plate same (the day's pages) | **canary** | the day's build in a browser, 21 widths | a plate clipped or a page wider than the viewport on today's pages; a plate drawn unlike main; the longest label clipped under 375 |
| 37 | build cost | fixture | the day's build | page bytes over the pins, the heading clear |
| 38 | registry | fixture | the day's build | college team pages are permanent |
| 39 | sharecard | fixture | the day's build | the 1080 square card and its tags |
| 40 | affiliate | fixture | the day's build | affiliate links, the plain link, the money line |
| 41 | push | fixture | the day's build | web push, the absent key |
| 42 | measure | fixture | the day's build in a browser | invalid JSON-LD; a console error; the console and structured fixtures not red |
| 43 | performance (Lighthouse, a report) | **canary** | the day's build in Lighthouse | Lighthouse absent (one warning, the read skipped); a score under 90; the slow fixture not under 90 |
| 44 | register read | fixture | inline | the Search Console read |
| 45 | game link | fixture | the day's build | a `/games/` link with no built page |
| 46 | report link | fixture | the day's build | a report row linking a page the build does not write |
| 47 | h6 hour sweep | fixture | inline clocks | the H-6 line at every hour |
| 48 | indexnow | fixture | the day's build | the key file and the submitter |
| 49 | live word scan | fixture | the day's build | the word "live" where the page cannot back it |
| 49a | s60 tree scan | fixture | the day's build | "verify", a bare feed code or "missing" in reader text |
| 50 | nav consistency scan | fixture | the day's build | one header on every page |
| 51 | replay e2e | fixture | `fixtures/sample_feed.xml` | the offline replay end to end |
| 52 | dedupe guard | fixture | inline | the near-duplicate guard |
| 53 | boundary | fixture | inline | boundary-class claims |
| 54 | merge state | fixture | inline | merge state |
| 55 | edition repair | fixture | inline | the edition repair ladder |
| 56 | fail closed | fixture | inline | a missing key fails closed; REJECT never publishes |
| 57 | contract ladder | fixture | inline | the contract ladder and slot recovery |
| 58 | n1 | fixture | `fixtures/n1/` | `scripts/n1_scores_test.py` (the stale card and its chip row, 2OT, ERADM), `scripts/n1_workflows_test.py` (S-DONE: the scores job's loop, timeout and hand-over; a dead source feed and an Edition gap warn, never fail), `scripts/health_gate_test.py` (S-DONE: a re-read is a reading) |
| 59 | slate layout 375 and 1440 | fixture | the fixture slate in a browser | a plate clipped or a page wider than the viewport at 375 or 1440 on the home, every Scores page, every game page |
| 60 | slate layout 320 | **canary** | the fixture slate in a browser | the same at 320 |
| 60a | live | fixture | the fixture slate, and in a browser | S-DONE, `live_canary.py`: a live part cut other than byte for byte; the home or Scores without its live root, parts, reading time or script; the tick's render (`site_build.build()` in LIVE_TICK mode) differing from the full build of the same reading; a built page that does not take a newer board for its look and day, loses the reader's tab or day, or takes one from another look, another day or an older reading |
| 61 | runner | fixture | inline plants | a canary that hands the gate a finding; a fixture whose finding is lost; a check of no kind |

59 fixture tests run under the runner and gate the run (56 from S-61, 2 from S-60, `live` from S-DONE), with the inline group beside them; 4 live canaries warn. The gate prints the count it ran on its `checks:` line. Moved from
gate to canary by S-61: 4 (`look rendered`, `plate fit and plate same` on the day's pages, `performance`,
and the 320 widths of every layout check, now `slate layout 320` and the under-375 half of `plate`).

## Outside the gate

| Check | Kind | Where | Note |
|---|---|---|---|
| Layer 2 sources | live canary by design, a separate job | `verify_pipeline.py sources`, `verify-sports-pipeline.yml` job 2 | notify-only: never blocks a run; it exits 3 on a dead feed so its job opens one issue naming the feeds |
| the health gate | a monitor, not a test | `scripts/health_gate.py`, `health.yml` 7:03 AM ET | fails, one mail, only when the site has not built for a day or "Scores as of" stood still more than two hours during a game |
| `scripts/health_gate_test.py`, `n1_*_test.py` | fixture | run inside check 58 | also runnable alone |
