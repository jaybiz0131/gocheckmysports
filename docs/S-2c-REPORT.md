# S-2c report: the game-day look

Program 7, Sports. Cloud session on jaybiz0131/gocheckmysports, opened Wed Oct 14 9:42 AM ET (the shell's date). Every time is ET from the shell.

**Status: merged and live on production `917ed23`, Wednesday October 14, 3:39 PM ET.**

## The start

- RULES.md body hash (`tail -n +11 docs/RULES.md | sha256sum`): `4179b2ac06d0dc7fb9de9987dc077884df6f4e1b5ebabe1b6ff1bb2de8b3568d`. Equals the opener.
- origin/main at the start: `427439e` (the S-2b close). It contains `4f026ed` (S-2b merge) and `427439e`.
- Count of record at the start (`/counts/today`, 9:42 AM): Sports production 2 ready, 1 canceled. 2 built, **10 of 12 remained**.
- The three artboards were written verbatim to `/tmp/s2c-designs/` and shot at their own sizes (390x1180, 390x1180, 1440x900).

## Merged

One push, `427439e..917ed23`, at 3:39:23 PM ET. Real merge commits, in item order.

| Item | Branch tip | Merge on main |
|---|---|---|
| 0, the card HUD | s2c-hud `7b8b7da` | `d937a96` |
| 1, the game-page hero, with Jack's 3:05 PM fixes | s2c-game-hero `39cce00` | `5af9907` |
| 2, the S-2b loose ends | s2c-fixes `cc84312` | `917ed23` |

- `s2c-fixes` was built on `s2c-game-hero` (both change `gamepage_canary.py`), and took Jack's fixes in by merge `cc84312`. The merged tree on main is byte-identical to `s2c-fixes`.
- Before the push: `python3 verify_pipeline.py canary && python3 commit_trailers.py && git push`, chain status 0. The gate printed `LAYER 1 CANARY: PASS`. Load 0.47 at the start, 0.96 at the end.
- After the push: `HEAD` and `origin/main` are both `917ed23`; `git rev-list --count origin/main..HEAD` is 0.
- `commit_trailers.py`: 0 hits. No commit carries a trailer.
- PR #105 (the preview) was closed unmerged with a comment.

## Item 0, the conditions HUD (Main.dc.html)

- Three tiles under each card's Ticket: kickoff temperature in the Weather ramp's ink, glowing; the wind as a compass arrow (true bearing, the way it blows) with speed and gust; the rain ring filled to the kickoff hour with "up to N%" when the window's peak is higher.
- Under the tiles: the words line, the roof and venue in mono, the credit link.
- A card with a number flag (wind, rain, feels) gets the amber border and glow. An alert alone gets the red rule, not amber.
- Indoor: one muted line with the roof icon, "Indoor · <stadium> · No weather". "Outside NWS coverage" keeps its own line.
- The active day tab is green: `#3DDC84` on solid `#193028`.
- The compass, arrow, ring and roof are one sprite per page, placed with `<use>`. The production home carries the compass once and 22 arrow references.

## Item 1, the game-page hero (SportsGamePhone, SportsGameDesktop)

- The field: north up with an N mark, rotated to the stadium's `orientation_deg`, yard lines, end zones in the teams' colours, three glowing arrows (amber with the wind flag, white without). The line under it: "Arrows point the way the wind blows".
- No orientation: a compass rose and one arrow. No field is drawn. Example: Florida St at Miami, Hard Rock Stadium.
- The panels: big temperature in its ramp ink, wind with its words, rain with its peak and the peak's hour.
- The chart: the line in each hour's ramp ink with a dot per hour, the game window as a green band, rain and wind rows with the wind amber at or over the Worker's threshold, and an accessible label carrying every hour's numbers.
- The link card goes to the Weather stadium page, with the credit and the NWS stamp.
- Desktop at 900px and up: two columns, the hero filling the right.
- Removed with their only caller: S-2b's hourly strip (`cx_hourly`) and small field graphic (`_cx_field`).

**Jack's fixes of 3:05 PM**
1. On every width the order is the Ticket, the hero, where to watch, then the venue, designations and inactives. The venue, designations and inactives rows left the Ticket for their own card under where to watch.
2. Desktop sizes, measured on preview `cc84312` at 1440: field column 300px, tiles 456px, hero 840px (the design's widths). Numerals are 60px, 113px wide inside 141px tiles. The wind tile carries the design's short line, "mph from the N, gusts 18".
3. `scoreboard.py` keeps the feed's `alternateColor`. When the two primaries are one family, the home end zone takes the home alternate. Seahawks at Broncos on production: `#002a5c` and `#fc4c02`.

## Item 2, the two S-2b loose ends

1. **The white bar of S-2b's contact sheets 1 and 2 is Netlify's deploy-preview drawer.**
   - It is a 780x48 fixed iframe at the viewport's bottom, painted white in a dark page. It shows only on previews, never on production.
   - Production `4f026ed` did carry a white bar at 1440 dark: the home band's fade (`.sb-fade`) ended on the light paper `#FBFAF6` in both themes. It now ends on `var(--paper)`.
   - The proof shots hide the drawer.
2. **"From the desk" carries stories from the last 7 days that name either team, and is absent with none.**
   - Before the fix the Seahawks at Broncos page carried the Sept 16 Darnold story.
   - On production `917ed23` none of the four game pages read carries the section.

## The tests, red then green

Every break was planted, seen red, restored from a saved copy, and seen green again. The logs are in `docs/s2c-proof/plants-*.txt`.

- **`strip_canary.py`, item 0, 23 breaks:**
  - contrast of the tile label
  - contrast of the green tab
  - the rain tile dropped
  - indoor without its roof
  - a flag not lighting its tile
  - the flagged card without its border
  - an alert alone turning the card amber
  - the words line amber with no flag
  - amber in CSS with no flag
  - glow in CSS on the words line
  - the temperature off the ramp
  - the ring filled to the remainder
  - the peak only on a flagged tile (the S-2b rule)
  - a peak printed when not higher
  - a missing temperature printed as 0
  - the alert word dropped
  - "Alerts not checked" silent
  - the credit unlinked
  - the arrow at the field angle
  - Calm drawing an arrow
  - the arrow drawn inline
  - the sprite not appended
  - a final losing its HUD
- **`gamepage_canary.py`, item 1, 23 fixture breaks:**
  - field not rotated
  - N mark dropped
  - end zones not in team colours
  - a field guessed with no orientation
  - arrows at the field angle
  - arrows amber with no flag
  - arrows white with the flag
  - Calm drawing arrows
  - caption dropped
  - temperature off the ramp
  - wind words dropped
  - rain peak dropped
  - missing printed as 0
  - chart line one colour
  - a dot dropped
  - game window dropped
  - wind amber only over the threshold (> not >=)
  - label without the wind
  - link card without the stamp
  - hero amber with no flag
  - desktop hero in the left column
  - caption contrast
  - chart hour-row contrast
- **`gamepage_canary.py`, item 1, 3 tree breaks:**
  - the hero above where to watch (the old order check)
  - an indoor page printing a chart
  - an indoor page with a temperature
- **Jack's fixes, 5 fixture breaks:**
  - field column back to a share
  - numerals back to 47px
  - one family kept as primaries
  - an alternate used for distinct primaries
  - the wrong team's alternate
- **Jack's fixes, 3 tree breaks:**
  - the hero back under where to watch
  - the facts above the hero
  - the venue back inside the Ticket
- **Two weak tests found by their own plants and fixed before commit:**
  - The distinct-primaries fixture carried no alternates, so it could not catch one being used; the plant stayed green until the fixture carried them.
  - The first contrast scan read shape fills (the turf, the rose) as text.
- **Item 2:**
  - `gamepage_canary` "From the desk", 3 fixture breaks: no date rule (the S-2b behaviour), 30 days, a story naming neither team.
  - The tree check was red on the pre-fix build: 18 stale rows (`desk-tree-red-before-fix.txt`). It is green on the gate's own build.
  - `home_canary`, 1 break: the fade back on `#FBFAF6`.
- **Contrast.** Every HUD and hero text colour clears 4.5:1, or 3:1 for the numerals at 24px and up, on every ground: the card over light and dark paper, under the brightest team wash, a tile, a flagged tile, the rain panel, the game window and the link card. The HUD and hero are solid dark in both themes. Glow is not counted.
- **The gate:** `python3 verify_pipeline.py canary` exited 0 on every branch tree before every push, and on the merged tree.

## The weights, the home at 390

| | Bytes on the site's own host | Home document (encoded) | Requests |
|---|---|---|---|
| Before: production `4f026ed` | 132,936 | 17,512 | 11 |
| Preview `2b49aac` | 136,705 | 17,606 | 37 (the Netlify drawer's) |
| After: production `917ed23` | 134,550 | 17,294 | 11 |

On production the site's own bytes went up by 1,614.

## The comparison sheet

Each artboard is shown beside the build from deploy preview 105, at the same size, light and dark.

| Sheet | Stamp | Shows |
|---|---|---|
| `docs/s2c-proof/compare-1-home.jpg` | `2b49aac` | Seahawks at Broncos, Steelers at Buccaneers, Bills at Raiders, Ohio State at Indiana |
| `compare-1b-home-top.jpg` | `2b49aac` | the green day tab, the fixed fade at 1440 dark |
| `compare-2-game-390.jpg` | `cc84312`, re-shot after the fixes | Seahawks at Broncos at 390 |
| `compare-3-game-1440.jpg` | `cc84312`, re-shot after the fixes | Seahawks at Broncos at 1440 |
| `compare-4-no-orientation.jpg` | `2b49aac` | Florida St at Miami, compass only |

- Reads: `preview-reads.txt` and `preview-reads-2.txt`. Every page carried the meta stamp and none scrolls sideways.
- Readings of the design, as stated with the first sheet:
  - Every card carries the full three-tile HUD.
  - The words line is amber only with the wind flag.

## Jack's yes

- **Wed Oct 14, 9:33 AM:** the design approved (the canvas).
- **3:05 PM:** approved with fixes 1 to 3 above. Re-shoot sheets 2 and 3; if they match, merge outside Thursday 6:00 to 9:30 AM and the Sunday freeze, read production, read the count, close PR 105 unmerged, record the rulings, close with documents only.
- Sheets 2 and 3 were re-shot from `cc84312`, matched, and were sent before the merge.

## Production read, the count

**Production read by stamp:**
- `/stamp.txt` read `917ed23`, built 19:39:46Z, at 3:42:46 PM.
- `scripts/prod-read.mjs --commit 917ed23` read the home and four game pages (Seahawks at Broncos, Florida St at Miami, Bills at Raiders, Texans at Jaguars) at 390 and 1440, light and dark. All 20 reads carry meta `917ed23`, none scrolls sideways, and none says "live".

| Page | Read |
|---|---|
| Home | 26 HUDs, 6 flagged cards, 1 indoor line, 1 outside line |
| Seahawks at Broncos | forecast hero, field, end zones `#002a5c` and `#fc4c02` |
| Florida St at Miami | forecast hero, compass |
| Bills at Raiders | indoor |
| Texans at Jaguars | outside NWS coverage |

All four game pages are in Jack's order.

**Count of record** (`/counts/today`), read 3:44:26 PM, five minutes after the push:
- Sports production 3 ready, 1 canceled; deploy previews 2 ready.
- `917ed23` counted ready at 19:42:31Z.
- 5 built, **7 of the 12 remain**.

## Deviations, said plainly

- **Branch stacking.** `s2c-fixes` sits on `s2c-game-hero`, so the three merges carry no conflict.
- **HANDOFF.md was at 295 lines.** The 22 September "For tomorrow's handoff" note moved verbatim to `docs/HANDOFF-2026-10-12.md` to keep it under 300 (U-1).
- **The proof sheets were also pushed early** to the session branch `claude/bold-tesla-6buikt`, which no PR or build watches.
- **A build-wrapper mistake, mine, cost one redo.** My local build wrapper restored files edited during its run. The item 0 edits were reapplied from saved copies; nothing reached a commit.

## Open, Jack's

1. Delete the merged branches `s2c-hud`, `s2c-game-hero`, `s2c-fixes` and `claude/bold-tesla-6buikt` (the proxy refuses branch deletes).
2. Unchanged from S-2b: DKR-Texas Memorial and TDECU have no coordinates in the Weather table.

## Thursday

- The first live conditions report runs at 7:17 AM EDT. Nothing is pushed to main between 6:00 and 9:30 AM.
- The next session reads `/conditions/2026-10-15-thu.html` and the home's slot on production by stamp.

Shell date at the end: Wed Oct 14 15:46:04 EDT 2026
