# S-3a report: the team pages, the structured data, the wall's alert note

Thursday 15 October 2026. Base: origin/main at `86bfcb9` (the merge of `34f4a13`). Stack head: `65acd34` on `s3a-wall`.
Merged October 15, 2026: b6002f0 (s3a-wall, carrying s3a-teams and s3a-structured); closed 7313a9d.

## 0. The catch-up merge, as asked first

- `34f4a13` merged to main as a real merge commit, `86bfcb9`, at 6:17 PM ET. The branch tip was already on origin; main was pushed after it.
- `git branch -r --contains 34f4a13`: `origin/main` and `origin/claude/cool-goodall-o96ke8`.
- Count of record at 6:25 PM ET (`/counts/today`): gocheckmysports production ready **3** of 12. Production serves `86bfcb9` (`/stamp.txt`).
- No hand dispatch. Today's report landed on its own (`3b4e04b`), so the catch-up crons are a no-op today.

## 1. The stack

Three item branches, each gated green on its own tree with `python3 verify_pipeline.py canary` (`LAYER 1 CANARY: PASS`), a draft PR as the preview ([#107](https://github.com/jaybiz0131/gocheckmysports/pull/107), to be closed unmerged after the real merge).

| Branch | Tip | What |
|---|---|---|
| `s3a-teams` | `8e29cd2` | Item a: team pages |
| `s3a-structured` | `d3eed15` | Item b: SportsEvent and BroadcastEvent, IndexNow by prefix |
| `s3a-wall` | `b554995`, then `e0bf9de` (CI fix), `65acd34` (CSS polish) | Item c: the alert note |

### a. Team pages
- NFL: `/teams/<abbr>.html`, all 32. College: `/teams/cfb/<school>.html`. The paths are apart because an abbreviation is not an identity across leagues (MIA is the Dolphins and the Hurricanes).
- Each page, in the S-2d scoreboard look (the same green panel, plates and bulbs as the wall): the record and standing, the next game's full card (the week board's own card, with its weather) when the scoreboard holds the game, the last result, the schedule as a scoreboard (week, opponent plate, date, kickoff or result, network, and the TEMP, WIND and RAIN plates once a game is in the Worker's range, or one plate saying why not), and the conditions log. NFL pages keep the injury report and the desk's stories.
- **The top forty** is the AP Top 25 in rank order, then the week board's other programs by record, one page per school (`teams.top_programs`).
- **The conditions log** lists a team's games the Worker flagged (wind 15 mph and over, a 40 percent chance of precipitation and over, a feel below 32 or above 90, an NWS alert), with the Worker's own numbers. Past games leave `conditions.json` when the week rolls, so `conditions_report.py` now carries each run's flagged games in a `log` field and the build merges every report's log with the live file (latest reading of a game wins). **The log starts on 15 October**, and each page says so.
- The old schedule's links to `/games/<id>` for every fixture are gone: a row links a game page only when the build wrote it (the game link canary caught 258 dead links in the first cut).
- Sitemap: all team pages are in the priority sitemap (NFL 32, college 35 in the preview).

### b. Structured data and discovery
- `structured.py` builds the markup from the game record the page already renders. Every game page carries a SportsEvent (name, start with its Eastern offset, venue, both teams, the league) and one BroadcastEvent per carrier the where-to-watch block names, none when it names none. Team pages carry a SportsTeam and the next game as a SportsEvent with its BroadcastEvent. No dash characters in any string.
- `scripts/indexnow.py --prefix /teams/` sends only the sitemap's URLs under a prefix. **Nothing has been sent.** IndexNow posts to an outside service, so it runs after the merge and the production read, with Jack's word: `python3 scripts/indexnow.py --prefix /teams/ /games/`.

### c. The wall's alert note
A row lit only by an alert shows the alert's own name in a plate under it (ALERT when the name is over 20 characters). A row lit by a number, or with no flag, shows none. On the preview: Seahawks at Broncos, "Freeze Warning". I read "in its plates" as one plate under the row, so the three weather plates keep their numbers.

## 2. Tests, red then green

| Check | Red first | Green |
|---|---|---|
| `teams_canary.py` unit (top forty, log entry, merge, team match, event shape, IndexNow prefix) | cannot import `teams`, `structured`; no `with_prefix` | PASS |
| `teams_canary.py` tree (32 and the college pages, scoreboard schedule, record line, log, no score on an unplayed game, sitemap, SportsEvent names on the page, BroadcastEvent carriers on the page) | the first gate run: 37 failures (35 college pages "nobody decided to leave it out of the sitemaps", 258 dead game links, N-8) | PASS on all three branches |
| `strip_canary.check_wall` alert note | "a row lit only by an alert does not say why in its plates" | `[]` |
| N-8 (TV cell on every unplayed row, full name and abbreviation) | red on the new markup | rewritten for the scoreboard schedule, PASS |

Local gate runs: `s3a-teams` PASS (second run), `s3a-structured` PASS, `s3a-wall` PASS.

## 3. A finding outside the sprint: CI has been red since 14 October
`Verify sports pipeline` failed on every run from 319 to 323, main pushes included, for two missing inputs and nothing else: "report card: Pillow is not installed" and "records: no browser: playwright not found". The workflow installed neither. `e0bf9de` installs Pillow and Playwright 1.56.1 with Chromium, and sets `PLAYWRIGHT_NODE_MODULES`. Confirmed: the Layer 1 canary is green in CI on `e0bf9de` ([run 38821001520](https://github.com/jaybiz0131/gocheckmysports/actions/runs/38821001520)), the first green since 14 October. It rides the stack, so main stays red until the merge.

## 4. Weights
- `site.css`: 185,289 to 191,280 bytes raw (+5,991); gzip 47,077 to 48,175 (+1,098).
- Preview HTML, raw over the wire / decoded: `/teams/chi.html` 10.7 KB / 38.3 KB; `/teams/cfb/ohio-state.html` 5.8 KB / 17.2 KB; a game page 6.5 KB / 21.9 KB (about 1.6 KB of it the structured data); the home 20.2 KB / 133 KB (unchanged by this stack beyond the alert plate).

## 5. The sheet
`docs/s3a-proof/sheet.html`: an NFL team page (Bears), a college team page (Ohio State), a game page (Bears at Falcons) and the home's wall, each at 390 and 1440, light and dark, from the deploy preview of `65acd34` on live data, and the game page's JSON-LD parsed into a table (`game-401872999-jsonld.json` beside it).

## 6. Not done, and why
- **Forty programs became 35.** The AP Top 25 plus the week board's programs is 35 teams on the live data, because the scoreboard holds ESPN's default college group (16 games), not every FBS game. Forty needs the wider feed (the scoreboard's group for all of FBS). The page set and the sitemap take whatever count `top_programs` returns, so it fills to forty when the feed does.
- **No college season schedule.** The desk holds none for college (`schedules.py` is NFL only). A college page shows this week's games. A season schedule needs a college team-schedule fetch, which I could not test from this sandbox.
- **The next-game card** appears when the scoreboard holds the game (this week); a game further out is a row. The NFL team page falls back to a one-line "Next".
- **Search Console** was not read in this session.
- **Preview and the log:** the log shows one game per team at most today; it fills as reports publish.

## 7. The open list
S-3b: market pages ("NFL on TV in <market> this Sunday", the regional map linked, never copied); share cards for game pages (1080 square, the S-2d card's look); affiliate links from `data/affiliates.json` (Fubo through Impact, Sling, Philo), plain links until Jack supplies them, and the footer's "how we make money" line.
Held: web push with the team pick, until the relay is decided (does it need a server beyond the conditions Worker; stop for Jack before deploying anything).
Also open: the wider college feed and a college schedule fetch (above); IndexNow for the new pages after the merge.

## 8. Jack's yes, merge, production read
Not yet. Merge order when Jack says yes: `s3a-teams`, `s3a-structured`, `s3a-wall` as real merge commits (or `s3a-wall` alone, which contains the other two), tip first, `git branch --contains`, then production by stamp, the weights, and the count five minutes after the push.
