# S-2b report: the conditions strip, the game pages and the Thursday report

Program 7, the Sports half of S-2. Cloud session on jaybiz0131/gocheckmysports, opened Tue Oct 13 9:26 PM ET (the shell's date; the opener was written for Wednesday). Every time is ET from the shell.

**Status: merged and live on production `4f026ed`, Wednesday October 14, 7:43 AM ET.**

## The start

- RULES.md body hash (`tail -n +11 docs/RULES.md | sha256sum`): `4179b2ac06d0dc7fb9de9987dc077884df6f4e1b5ebabe1b6ff1bb2de8b3568d`. Equals the opener.
- origin/main at the start: `98ec496` (S-1 close), which is the required commit.
- Worker at the start: `GET https://conditions.gocheckmybrands.workers.dev/stadiums` answered 200, `built 2026-10-13T19:20:00Z`, 163 rows.
- Count of record, Tue Oct 13 (`/counts/today`), read 9:30 PM: Sports production 6 ready and 3 canceled, deploy previews 4 ready. That is 10 built, so **2 of the 12 remained**.

## Item 4.1: did S-1's handoff commit 98ec496 build?

- **No.** The Worker's `last:gocheckmysports:production` reads `98ec496`, state `error`, "Canceled build due to no content change", counted as canceled at 17:46:43Z.
- **Correction to the Oct 13 record:** the S-1 close read "10 built, 2 canceled" at 17:46:03Z. 98ec496 was canceled 40 seconds later, so the day's canceled count is 3, not 2. Built stays 10.
- Netlify's own deploy list was not read: there is no Netlify token in this session. The Worker's counter is the count of record (U-11).

## Item 4.2: the October 8 article's dateline

- Production `3b11d14`, read at 390 and 1440 on `/articles/brewers-defeat-padres-to-face-dodgers-in-third-straight-nlcs`:
  - the masthead reads "OCTOBER 13, 2026";
  - the article's own dateline reads "OCTOBER 8, 2026 · 7:43 PM ET", visible.
- **The date is right; nothing needed fixing.**
- **Position:** the dateline sits in the eyebrow just above the headline (top 241px; the headline starts at 277px at 390). Under the headline the byline reads only "By The GoCheckMySports Desk". That has always been the layout. It is not changed here; moving the date under the headline is Jack's call.

## The games covered

- Live intake, 10:44 PM build: **30 board games** (14 NFL, 16 FBS).
  - forecast: 26
  - indoor: 1 (Bills at Raiders, Allegiant)
  - outside NWS coverage: 1 (Texans at Jaguars, Wembley)
  - missing: 2 (below)
- **Missing venues** (the Worker answers 503 `no_coordinates`; the strip prints nothing and the build log lists them):
  - Florida at Texas, DKR-Texas Memorial Stadium
  - Oklahoma St at Houston, TDECU Stadium
- **Match:** all 52 FBS games on ESPN's Saturday group-80 feed match a table row by both venue id and exact name.
- **The board's college slate** is still the feed's default 16 games, not every FBS game. This is the S-1 open item, unchanged.

## Merged

Merged in one push, `98ec496..4f026ed`, at 7:43:27 AM ET on Wednesday Oct 14. Every merge is a real merge commit (`--no-ff`), in item order.

| Item | Branch tip | Merge on main |
|---|---|---|
| 0, the intake | `5232473` | `849649c` |
| 1, the strip | `7fac7a8` | `4b6c33f` |
| 2, the game pages | `57f7ebe` | `cc068fa` |
| 3, the report | `eb43403` | `4f026ed` |

- `5232473` is the one commit added after the yes: Jack's ruling 4, `site/data/conditions.json` in `.gitignore`. It was pushed before the merge, and the canary passed on its own tree first.
- **Before the push:** the canary exited 0 on the merged tree, load 1.04 to 1.05.
- **`git branch --contains`:** every item tip is on main.
- **After the push:** `HEAD` and `origin/main` are both `4f026ed`; `git rev-list --count origin/main..HEAD` is 0.
- `commit_trailers.py`: 0 hits.
- **The preview branch** `s2b-preview` (`432269b`, carrying the dry-run report) was never merged. PR #104 was closed unmerged with a comment.

## Deviations, said plainly

- **Alerts that end before the game are dropped.** An alert whose `ends` (or `expires`) falls before the game's window opens is dropped in the intake, and the alert flag is recomputed. The Worker sends whatever is in force at the time of the read. Without this, Tuesday night's Severe Thunderstorm Watch at Arrowhead would have turned Sunday's strip red. The Weather desk should know the strip differs from `flags.alert` on that point.
- **Game page addresses stay `/games/<id>.html`.** NFL pages already lived at that address, so FBS pages use the same scheme. The brief's `/games/<slug>` was not followed because URLs never change.
- **The old rulings are narrowed to the board, not removed:**
  - S-2 (games out of the sitemaps) and 6 October (game pages for the NFL only): the board's game pages are now in the priority sitemap, and every FBS board game has a page.
  - Every other game page stays deep, on the register.
  - Both old checks were planted red again.
- **The report has no model.** It is written by template from the Worker's numbers. Under U-4 a dry run then costs nothing, and the gate can check every number against the game's own data.
- **The share card's arrows are north up.** The card draws no field, so a field-relative angle would be read in the wrong frame. A legend line on the card says so.
- **`kickoff_weather.py` had no tests,** so no fixture was kept. The old weather helpers (`_wx_chip`, `_w2w_wx`, and the weather half of `_tk_venue`) are inert, because `WX_DATA` is always None now. They are left in place, to be deleted later.
- **No attribution trailer in any commit** (trailer law). `commit_trailers.py` read 0 hits before every push.

## The tests, red then green

Every break below was planted, seen red, restored from a saved copy and seen green again. The plant logs are `docs/s2b-proof/plants.txt`.

**`conditions_canary.py`, item 0. Ten breaks:**
- indoor read as a forecast
- the retractable word
- the out-of-range day computed in UTC
- Wembley asked of the Worker
- a missing venue not listed
- `alerts: null` printed as "No alerts"
- a near college name matched
- a final's strip dropped
- an alert ending before the window kept
- the alert flag not recomputed

**`strip_canary.py`, item 1. Sixteen breaks:**
- the precipitation cell dropped
- indoor not muted
- the flags not bright
- the alert word dropped
- the alert rule grey
- unchecked alerts silent
- the credit unlinked
- the arrow drawn true on the field
- no compass
- a final loses its strip
- the small text at #7A7F88
- the glyph sprite duplicated
- Calm drawing an arrow
- the peak dropped
- the peak on an unlit cell

Two weak tests were found by their own plants and fixed before commit:
- the Calm fixture had no degrees, so it could not draw an arrow;
- the code checked Calm twice, so removing either check alone changed nothing.

**Contrast.** Every strip text colour in the shipped `site.css`, and every temperature-ink stop, clears 4.5:1 on six grounds: light and dark paper, under the brightest team wash, and under a lit cell. The first run was red, 48 failures. The fix was a scrim under the strip, which the test reads from the CSS.

**`gamepage_canary.py`, item 2. Twelve breaks**, eleven on a copy of the built tree and one in code:
- an FBS page missing
- two conditions blocks
- no block
- a block on a missing venue's page
- a forecast on an indoor page
- a foreign runtime host
- the title
- the order above the fold
- the home's link
- the sitemap, dropped
- the sitemap, off the board
- verify printing the service (weak at first; tightened, then red)

Also: the old S-2 sitemap check and the register check were each planted red again after narrowing.

**`report_canary.py`, item 3. Sixteen breaks:**
- a quiet game written up (red only by crashing at first; now names the failure)
- the wind meaning dropped
- the cold meaning dropped
- the stamp not in ET (both conversions together, since either one alone covers for the other)
- each of the six gate rules turned off
- the Weather mark painted out
- the freeze on Saturday
- the slot showing last week's report

**`home_canary`, three more breaks:** the slot never filled, an extra block in it, and the fixture not isolated.
- **This one found a real bug.** The gate's build left this week's reports loaded, so after Thursday's first report every push on main would have gone red. It was fixed before any merge.

**`jobs_canary`** now holds:
- the three crons;
- the Sunday cron before 15:00 UTC;
- the build before the push;
- only `site/reports/conditions` staged;
- no secret and no model import.

**The gate:** `python3 verify_pipeline.py canary` exited 0 before every push. Load average was 0.13 to 1.25.

## The weights, the home at 390

| | Bytes on the site's own host | Home document (encoded) | Requests |
|---|---|---|---|
| Before: production `3b11d14` | 133,901 | 15,785 | 13 |
| After: preview `432269b` | 141,353 | 18,952 | 42 |

- The site's own bytes went up **by 7,452**.
- The preview's other bytes are Netlify's review drawer (`app.netlify.com`, Segment, Bugsnag, about 385 KB). Production does not serve them.
- The "after" includes the dry-run report in the home slot. Production carries none until Thursday's run.
- Each glyph is drawn once per page, as a sprite.

## The contact sheet

The sheets are `docs/s2b-proof/contact-sheet-1.jpg` to `-4.jpg`. They come from deploy preview 104, stamp `432269b`, built 11:08 PM ET. 28 shots: 390 and 1440, light and dark. None scrolls sideways.

- **Sheet 1:** the home board, with Thursday's game, Ohio State at Indiana (open), Bills at Raiders (dome) and the report slot.
- **Sheet 2:** Seahawks at Broncos.
- **Sheet 3:** Bills at Raiders.
- **Sheet 4:** the dry-run report page.
- **Plus:** the dry-run share card.

Three size defects were found on the first preview (`9944227`) and fixed before this one: the regional maps line, the report subhead, and the report's time, stamp and list lines. All had lost to `.lx p` and a page-wide `h2` rule.

## The dry-run report

Written by `python3 conditions_report.py --dry-run` against Week 6's live data at 10:29 PM ET Tuesday. Nothing was published. The text is `docs/s2b-proof/dry-run-report.txt`; the card is `share-card-dry-run.png` there.

- 6 games written up:
  - Seahawks at Broncos: wind and rain
  - Mississippi St at LSU: wind
  - Florida St at Miami: rain
  - Bears at Falcons: wind, retractable roof
  - Steelers at Buccaneers: wind
  - Commanders at 49ers: wind
- 20 games in one line each.
- 1 indoor, 1 outside NWS coverage.

## Jack's yes

**Given Wednesday Oct 14, 7:35 AM ET**, on the contact sheets and the dry-run report. Rulings that came with it:

1. Merge today, in as few pushes as the items allow, so that Thursday 7:17 AM is the first live report.
2. The Cloudflare Web Analytics beacon stays on game pages. It is the cookie-free beacon ruled on Crypto Oct 12, and it is the one named exception in the canary. Recorded in `HANDOFF.md`.
3. The dateline stays above the headline.
4. `site/data/conditions.json` goes into `.gitignore` on `s2b-intake`.
5. Close PR #104 unmerged; read production; read the count; send IndexNow; record the three rulings; close with documents only.
6. If the Thursday 7:17 AM cron slips, the report is late but correct. The trigger is not changed.

## Production read, the count, IndexNow

**Production read by stamp:** `/stamp.txt` read `4f026ed`, built 11:43:46Z, at 7:46:43 AM ET. At 390 and 1440, every page carries the meta `4f026ed`, and none scrolls sideways.

| Page | Read |
|---|---|
| Home | 28 strips: 26 forecast, 1 indoor, 1 outside |
| Seahawks at Broncos | title "Seahawks at Broncos: weather, where to watch, inactives. Thursday 8:15 PM ET."; one forecast block with the hourly line; credit "Conditions by GoCheckMyWeather, NWS, 6:49 AM ET", linked to `gocheckmyweather.com/stadiums/empower-field-at-mile-high.html` |
| Bills at Raiders | one "Indoor" block, no forecast |
| Texans at Jaguars | one "Outside NWS coverage" block |

Thursday's strip at that read: 50°, feels 47°, 8 mph down the field, gusting 18, 9% precip, open air.

**Count of record** (`/counts/today`), read 7:48:35 AM ET, five minutes after the push:
- Sports production: 2 ready today.
- The merge `4f026ed` counted ready at 11:46:32Z.
- **10 of the 12 remain.**

**IndexNow:** 32 URLs (the home, `/scores` and the 30 board game pages), one batch, HTTP 200, about 7:50 AM ET.

## The cron line (`.github/workflows/conditions-report.yml`)

```
17 11 * * 4   Thursday 11:17 UTC = 7:17 AM EDT (6:17 AM EST from Nov 1)
17 21 * * 6   Saturday 21:17 UTC = 5:17 PM EDT
17 10 * * 0   Sunday   10:17 UTC = 6:17 AM EDT
```

- **First live run:** Thursday October 15, 7:17 AM EDT. The report branch is merged.
- The scheduler has been measured 1.5 to 4 hours late, so the report may land as late as about 11:15 AM.
- Each run that writes a report is one build.

## Open, Jack's

1. Two FBS stadiums have no coordinates in the Weather table (DKR-Texas Memorial, TDECU), so those games print nothing. That fix belongs to the Weather desk.
2. Delete the merged item branches (`s2b-intake`, `s2b-strip`, `s2b-game-pages`, `s2b-report`) and `s2b-preview`. The proxy refuses branch deletes.
3. Unchanged from S-1: the six `verify` carriage rows and the regional maps link; the Worker line and `NEWSROOM_JOBS`; the affiliate links.

## Thursday

- The first live report runs at 7:17 AM EDT.
- **If this session is still open,** it reads `/conditions/2026-10-15-thu.html` and the home's slot on production, by stamp.
- **Otherwise the next session does.** The handoff says so.

## What S-3 must know

- **The Weather desk** can now link college games to `gocheckmysports.com/games/<id>.html`. Every FBS board game has a page.
- **Game pages have no `SportsEvent` or `BroadcastEvent` data yet.** That is S-3's.
- **Share cards for game pages are not drawn yet** for college games; NFL games keep theirs. Also S-3's.
- **The strip reads the build's numbers only.** Live reads wait for S-4. The credit names the NWS forecast's generated time.
- **Cascade trap, twice this session:** `.lx p` (17px) and the page's `h2` outrank any one-class rule. Give a new `<p>` or `<h2>` a selector with a parent class. A browser size check would catch the next one.

Shell date at the end: Wed Oct 14 07:49:53 EDT 2026
