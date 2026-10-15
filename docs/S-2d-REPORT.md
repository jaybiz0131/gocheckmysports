# S-2d report: the scoreboard look

Program 7, Sports. Cloud session on jaybiz0131/gocheckmysports, opened Wed Oct 14 7:29 PM ET (the shell's date). Every time is ET from the shell.

**Status: merged and live on production `374e5dd`, Wednesday October 14, 10:08 PM ET.**

## The start

- RULES.md body hash (`tail -n +11 docs/RULES.md | sha256sum`): `4179b2ac06d0dc7fb9de9987dc077884df6f4e1b5ebabe1b6ff1bb2de8b3568d`. Equals the opener.
- origin/main at the start: `74b60d2`. It carries S-2c's three merges (`d937a96` s2c-hud, `5af9907` s2c-game-hero, `917ed23` s2c-fixes) and its close (`7d87e71`).
- Count of record at the start (`/counts/today`, 7:29 PM): 5 built (production 3 ready, previews 2 ready), 3 canceled. **7 of 12 remained.**
- The three artboards were written verbatim to `/tmp/s2d-designs/` and shot at their own sizes (390x1180, 390x1180, 1440x900). The wall's rows were expanded from its own list.

## Before S-2d: W-45, the stale schedule and scoreboard (Jack's interjection)

- **Cause, one line:** the site never published `where-to-watch.json` or `scoreboard.json`. The only copies outside a build were the repository's. Those refresh only when the inactives poller commits `site/data`, and it last did on Sunday at 8:06 PM ET.
- **The live pages were current throughout:** Where to Watch and Scores on production `917ed23` read Week 6, "Updated Oct 14, 3:39 PM ET".
- **Fix:**
  - The build publishes both files at `/data/` beside `conditions.json`.
  - The manifest carries `started_utc`.
  - `gamepage_canary.check_data_fresh` fails when either file is missing or was fetched before the build began.
- **Red first:** the check failed on the origin/main build (no `started_utc`), and on three plants: the Sunday scoreboard, the Sunday schedule, and the schedule unpublished.
- **Merged:**
  - Branch `w45-data-fresh` `eb3e72b`, merge `aa62909`.
  - Pushed 8:03:49 PM: `74b60d2..aa62909`, chain status 0, gate PASS, 0 trailers.
  - HEAD and origin/main both `aa62909`; rev-list count 0.
- **Production read by stamp `aa62909` (built 00:04:12Z), 8:07 PM:**
  - manifest `started_utc` 00:04:08Z.
  - `/data/where-to-watch.json` fetched 00:04:11Z; `/data/scoreboard.json` fetched 00:04:12Z. Both are after `started_utc`.
  - Where to Watch and Scores carry `aa62909` and "Updated Oct 14, 8:04 PM ET".
- **Count, 8:08:52 PM:** production 4 ready and 3 canceled, previews 2 ready. `aa62909` counted ready at 00:07:07Z. **6 of 12 remained.**
- **Weather's side:** read `gocheckmysports.com/data/where-to-watch.json` and `/data/scoreboard.json`. The repository's copies still refresh only with the poller.

## The branches (stacked, as S-2c's were: all three change `strip_canary.py` and `site_build.py`)

| Item | Branch | Tip | Gate |
|---|---|---|---|
| 0, the board cards as scoreboards | s2d-board | `976ca24` | PASS, status 0 |
| 1, the game page board | s2d-game | `cdd7bf0` | PASS, status 0 |
| 2, the wall and the share card, with Jack's W-45 retry | s2d-wall | `6a7dbce` | PASS, status 0 |

- Every push was gated on its own tree's gate status, with 0 trailers.
- Load average: 0.39 to 1.65 across all gate runs.
- Preview: [PR 106](https://github.com/jaybiz0131/gocheckmysports/pull/106), a draft from `s2d-wall`. It was closed unmerged with a comment at 10:02 PM, before the tip push, so the push spent no preview build.

## W-45, the gate's retry (Jack, 9:50 PM)

- **The rule:** a published schedule or scoreboard older than the build is first read as the feed failing during the gate's own build, so the gate fetches that feed once more, without writing the committed file.
  - A retry that gets it passes, with a warning naming the first failure.
  - A retry that fails, or comes back stale, is red.
  - A file the build did not publish, or a manifest with no `started_utc`, is red at once.
- **Code:** `scoreboard.refresh` takes `check=True`, as `where_to_watch.refresh` already did.
- **Live:** run live at 9:54 PM, the retry fetched both feeds without touching the repository.
- **Commits:** `73cafc7` (the retry) and `6a7dbce` (the self-test's own warning captured; it was printing a `::warning::` on every gate run).
- **`check_data_fresh_retry`, 4 breaks, each red (`plants-w45-retry.txt`):**
  - the retry's answer ignored
  - no retry at all
  - a missing file excused
  - a stale retry accepted
- **Gate on `6a7dbce`:** PASS, status 0, load 0.63 to 1.23.

## Item 0, the board cards (ScoreboardBoard)

- **The panel.** Each card is a green panel (`#0E3B2A`) in a `#072619` frame, with `#141A17` plates (inset shadow), cream `#F4F1E6` Oswald names and numerals, and yellow `#FFD23F` labels, kickoff line and lit bulbs.
- **The line score.**
  - The day's first card (the Ticket) has quarters 1 to 4 and a yellow T; OT only when the feed's status says overtime.
  - The rest have the total only.
  - Plates are empty until the feed has the number.
  - A final's loser total dims to `#8E8A6E` (5.05:1 on the plate).
- **The weather.**
  - TEMP, WIND (with the arrow) and RAIN plates, labelled, with the feel, the gust and the window's peak under each.
  - Four bulbs: WIND, RAIN, COLD (feel under 60°F) or HEAT, and ALERT. Each is lit by its own flag only.
  - A lit bulb lights the plate that matters and the board's yellow edge.
  - The words line is yellow only with the wind flag, and carries the linked credit.
- **One plate.** A dome reads "Dome · No weather". Outside coverage names the city from the feed ("London · Outside NWS coverage"). A retractable roof keeps the plates and adds a ROOF plate.
- **The day tabs** are plates in a green panel; the active day is yellow with a soft glow.
- **S-1's laws kept on the new card:**
  - Every card dates itself ("Thu Oct 15 · 8:15 PM ET · Empower Field").
  - The network plate is followed by the first stream chip or the verify chip.
  - The line keeps its provider ("DraftKings via ESPN").
- **Amber retires**, on the Scores page cards too: they carry the same weather panel.
- **Off-bulb labels:** the artboard's `#8E8A6E` is 3.58:1 on the panel. The labels take `#A7A285`, 4.86:1.

## Item 1, the game page (ScoreboardGame)

- **Top:** the yellow mono kicker (dark gold `#8A6A00` on the light paper) and the title in Oswald capitals.
- **One board:**
  - The line score with an OT column, the abbreviations and the records.
  - The line (with its provider) and the network.
  - A rule.
  - Conditions at kickoff: the field in the board's frame, with team-colour end zones and three glowing yellow arrows; TEMP, WIND, GUST and RAIN plates; the words line.
  - By the hour: °F, MPH and RAIN plate rows, with the game's hours framed in yellow and the wind yellow at or over the Worker's threshold.
- **Under the board:**
  - The yellow "Watch on <service>" button and the outlined second stream. Both come from in-date carriage rows; a verify row is never a button.
  - The Weather stadium link with the credit and stamp.
  - Then where to watch, the venue, designations and inactives.
- **Desktop:** at 900px and up the board fills the left column.
- **Removed:** the Ticket, S-2c's hero, its chart and the HUD retire from the game page, with their CSS.

## Item 2, the wall and the share card (ScoreboardWall)

- **The wall.**
  - At 1100px and up the home opens on the NFL week in two columns.
  - Each row has a bulb lit when any flag is on (alert included), the team plates, the kickoff, and TEMP, WIND and RAIN plates (the wind yellow when flagged), or one plate.
  - Each day's college games follow in a wall titled by the day.
  - Every row links its game page. Under 1100px the wall is not shown.
- **The share card.**
  - The conditions report's card renders in the wall's look at 1080x1080 from the report's own rows.
  - Both sites' names are in plain text.
  - Oswald comes from a static 600 TTF, which the build deletes from the publish tree.
  - The report carries its NFL week.

## The font

- **Oswald:** `site/assets/fonts/oswald.woff2`, **7,588 bytes**.
- **Source:** Google's v57 latin variable file, limited to weights 500 to 700, and subset to capitals, figures and the plates' punctuation (84 characters).
- **Reproducible:** `scripts/oswald_subset.py` makes it byte for byte; `head.modified` is kept so the sha is stable.
- **Loading:** self-hosted woff2 with `font-display:swap`, like the site's other faces.
- **Tests:**
  - `strip_canary` checks the sha and the 500 to 700 declaration.
  - It also checks that every character the home sets in Oswald is in the subset.

## The weights, the home

| | Width | Bytes on the site's own host | Home document (encoded) | Requests |
|---|---|---|---|---|
| Before: production `aa62909` | 390 | 139,694 | 17,383 | 11 |
| Before: production `aa62909` | 1440 | 896,730 | 17,377 | 12 |
| Preview `dde2ed2` | 390 | 151,395 | 17,645 | 38 (the Netlify drawer's) |
| Preview `dde2ed2` | 1440 | 908,752 | 17,586 | 39 (the Netlify drawer's) |
| After: production `374e5dd` | 390 | 148,378 | 17,426 | 12 |
| After: production `374e5dd` | 1440 | 905,719 | 17,436 | 13 |

- On production the site's own bytes went up by 8,684 at 390 and 8,989 at 1440.
- One request more at each width: the Oswald file, 7,588 bytes. `weights-before.txt`, `weights-after.txt`.

## The tests, red then green

Every break was planted, seen red, restored from a saved copy (checked by sha) and seen green. The logs are in `docs/s2d-proof/plants-*.txt`.

**`strip_canary`, item 0, 28 fixture breaks (`plants-item0.txt`):**
- contrast: off-bulb label at `#8E8A6E`; the plate's sub line at `#8E8A6E`
- yellow on numbers with no flag; amber on a lit bulb
- the font: declared 400 to 700; a different woff2
- the line score: no quarter 4; compact cards with quarters; an empty total as 0; quarters from a half-filled feed; the winner dimmed; OT always (weak at first, see below)
- the weather plates: a final losing its weather; a peak not higher
- the bulbs: RAIN lit by wind; COLD at a 60 feel; ALERT lit by any flag
- yellow with no flag: the edge; the words line
- the credit unlinked
- the arrow: at the field angle; Calm drawing one (weak at first, see below); drawn inline
- a missing temperature as 0
- alerts null silent
- one plate: a dome as Indoor; outside coverage without its city; ROOF dropped
- the kicker with the full stadium name

**Two weak tests found by their own plants and fixed before commit (`plants-item0-weak.txt`):**
- OT: no fixture had a fifth period without OT in its status.
- Calm: the test found "Calm" in the words line, not on the plate.

**`strip_canary` tree, 6 breaks (`plants-item0-tree.txt`):**
- a card not a scoreboard
- a day opening compact
- a second Ticket
- amber left on the home
- a name the subset cannot draw
- no Oswald text found

**`home_canary` and `truth_canary` on the new card (`plants-item0-home.txt`):**
- the record out of its name plate
- the stream chip dropped
- the card's date dropped: red in `strip_canary`; the truth canary's fixture date is a final's

**`gamepage_canary`, item 1, 20 breaks (`plants-item1.txt`, `plants-item1-weak.txt`):**
- the line score: no OT column; nicknames for abbreviations; network dropped
- the field: white arrows; not rotated
- the plates: GUST dropped; GUST unlit under the wind flag; a missing temperature as 0
- yellow with no flag: the words line; the edge
- by the hour: game hours unframed; wind yellow only over the threshold; the label without the wind
- a dome drawing hours
- a verify row as the second button. Weak at first: verify rows sort last, so a fixture with one in-date row was added.
- the Weather link without its stamp
- the board in the right column at 900px
- contrast: the kicker in yellow on the light paper; an hour label at `#8E8A6E`; cream on the yellow button

**Item 2, 11 breaks (`plants-item2.txt`):**
- the wall: shown under 1100px; a label at `#8E8A6E`; every wind yellow; the alert not lighting the bulb; the wind yellow with no flag; a dome as Indoor; college rows in the NFL wall; a row with no link
- the card: every bulb lit; wind yellow with no flag; S-2c's dark ground

**Wall tree, 4 breaks (`plants-item2-tree.txt`):**
- the band ahead of the wall
- an NFL row missing
- a dead row link
- the first slicing plant, which went red for the wrong reason and was re-planted

**The gate:** `python3 verify_pipeline.py canary` exited 0 on every branch tree before every push.

**A preview-only report was not pushed.** A dry-run conditions report committed to the preview would have let the preview draw the share card. Its real game links failed the gate's fixture game-link canary, and a red gate means no push (U-14). The share card is therefore drawn by `conditions_report.share_card` at `dde2ed2` from the 8:47 PM dry run (no model call).

## The comparison sheet

Every built shot is from deploy preview 106 at stamp `dde2ed2`, read at 9:17 PM. All 8 reads carry meta `dde2ed2`, none scrolls sideways, and Oswald loaded on each (`preview-reads.txt`).

| Sheet | Shows |
|---|---|
| `compare-1-home-390.jpg` | the artboard; the built tabs, Seahawks at Broncos (the Ticket), Steelers at Buccaneers and Bills at Raiders at 390, light and dark. The cards are element shots stacked in the artboard's order, with the fixed tab bar hidden for those shots. |
| `compare-2-final.jpg` | Bills at Rams, Week 5 final, 37 to 34 in OT, from this season's feed through the card code at `dde2ed2`, in a preview page. No weather plates: the Worker holds no conditions for last week's games. |
| `compare-3-game-390.jpg` | the artboard; Seahawks at Broncos at 390, light and dark |
| `compare-4-game-1440.jpg` | Seahawks at Broncos at 1440, light and dark |
| `compare-5-wall-1440.jpg` | the artboard; the wall at 1440, light and dark |
| `compare-6-share-card.jpg` | the new share card, 1080x1080 |

**Readings of the design, for Jack:**
1. **Labels and subs on every card.** The Steelers artboard shows its weather plates without labels or the subs. The brief's text gives every card labelled plates with the feel, gust and peak, so every card has them.
2. **The line stays on the cards** (the 20 September ruling), under the line score with its provider. The artboards do not show it.
3. **Names.** The plates print the nickname in the NFL ("Seahawks") and the school in college; the game page's line score prints abbreviations, as the artboards do. The full name stays in each plate's label and the page title. N-1 asks for one full name everywhere; the artboards are newer and are followed here.
4. **Arrows.** The game page's arrows are always glowing yellow, as the artboard draws them for an unflagged game. S-2c's white arrows retire. The wind flag lights the WIND and GUST plates and the board's edge.
5. **Temperatures** are cream, as the artboards set them. S-2c's Weather-ramp ink on the temperature retires with the HUD.
6. **The day tabs** keep "All" and the manifest's day counts (S-1), as plates.
7. **The kicker carries the date** ("Thu Oct 15 · 8:15 PM ET"), because every card dates itself (S-1). The artboard shows "THU 8:15 PM ET".

## Jack's yes

- **Wed Oct 14, 3:11 PM:** the scoreboard look (the canvas).
- **9:50 PM:** yes on the comparison sheet, all seven calls as built.
- **One change first:** the W-45 check retries the fetch once inside the gate and stays a hard check.
- **Then:** merge tonight, well before Thursday 6:00 AM ET; push the tip first and confirm with `git branch --contains`; one production build; read production; read the count; close PR 106 unmerged; close with documents only.

## Merged

**The tip first.** `s2d-wall` `6a7dbce` was pushed gated at 10:04 PM (0 trailers).
- `git branch -a --contains 6a7dbce`: `s2d-wall`, `remotes/origin/s2d-wall`.
- `cdd7bf0` is in origin/s2d-game and origin/s2d-wall.
- `976ca24` is in origin/s2d-board, s2d-game and s2d-wall.

**One push**, `aa62909..374e5dd`, at 10:08 PM ET. Real merge commits, in item order:

| Item | Branch tip | Merge on main |
|---|---|---|
| 0, the board cards | s2d-board `976ca24` | `bb85c54` |
| 1, the game page | s2d-game `cdd7bf0` | `e4e4d6f` |
| 2, the wall, the share card, the W-45 retry | s2d-wall `6a7dbce` | `374e5dd` |

- The merged tree is byte-identical to `6a7dbce` (`git diff` empty).
- Pushed as `verify_pipeline.py canary && commit_trailers.py && git push origin main`: chain status 0, `LAYER 1 CANARY: PASS`, 0 trailers, load 0.81 at the start and 0.81 at the end.
- After the push: HEAD and origin/main both `374e5dd`; `git rev-list --count origin/main..HEAD` is 0.

## Production read

- **`/stamp.txt`** read `374e5dd`, built 02:08:18Z, at 10:11:37 PM.
- **`scripts/prod-read.mjs --commit 374e5dd`** (`prod-read.txt`):
  - It read the home, Seahawks at Broncos and Bills at Raiders at 390 and 1440, light and dark.
  - All 12 reads carry build `374e5dd`; none scrolls sideways, and none says "live".
  - The home carries 30 games, 30 unique.
- **Structure read** (`prod-structure.txt`), 8 reads at 390 and 1440, light and dark. Every page carries `374e5dd`, Oswald loaded, and no S-2c amber is on any page.

| Page | Read at 390 and 1440 |
|---|---|
| Home board | 30 scoreboard cards, 4 Tickets (Thu, Sat, Sun, Mon), 8 lit, 9 lit bulbs, "London · Outside NWS coverage" and "Dome · No weather" plates |
| The wall | 30 rows, 8 lit; hidden at 390, shown at 1440 |
| Seahawks at Broncos | one board with its forecast block |

- **Shots:** `production-*.jpg`.

## Count of record (`/counts/today`)

Read at 10:13:15 PM, five minutes after the push:
- Sports production 5 ready and 3 canceled; deploy previews 4 ready.
- `374e5dd` counted ready at 02:11:31Z.
- **9 built, 3 of 12 remain.**

This close is documents only and does not build (U-11).

## Open, for S-3

- On the wall, a row lit only by an alert shows why: ALERT, or the alert's short name, in its plates. Seahawks at Broncos is lit by a Freeze Watch alone tonight, and its row shows no reason.

## Open, Jack's

1. Delete the merged branches (the proxy refuses branch deletes): `w45-data-fresh`, `s2d-board`, `s2d-game`, `s2d-wall`, `s2d-close`, and the session branch `claude/happy-hawking-ex9z34`.
2. Weather reads `/data/where-to-watch.json` and `/data/scoreboard.json` from gocheckmysports.com.
3. Unchanged: DKR-Texas Memorial and TDECU have no coordinates in the Weather table; their wall plates read "No forecast".

## Thursday

- The first live conditions report runs at 7:17 AM EDT, with the first live card in the wall's look.
- Nothing is pushed to main between 6:00 and 9:30 AM.
- The next session reads `/conditions/2026-10-15-thu.html`, its card and the home's slot on production by stamp.
