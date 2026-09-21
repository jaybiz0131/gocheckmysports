# Sunday 20 September, the four checkpoints

Evidence, not build tasks. A defect found at a checkpoint was recorded and not fixed
until the freeze lifted at 8:30 PM ET. Screenshots are under
`shots/checkpoints/2026-09-20/`.

No tokens, no keys, no hook URLs in this file. The repos are public.

## U-5: the four checkpoints

| # | Due | Ran | What was read | Result |
|---|---|---|---|---|
| 1 | 11:45 AM | **missed** | the lists | Not run. The session was building A-3 and A-5 and did not stop for it. The 1 PM lists were read at checkpoint 2 instead, one hour and forty-five minutes late, so the "posted 11:3x" window itself was never observed. |
| 2 | 1:30 PM | **2:23 PM** | the slate live | Recovered, 53 minutes late. Marquee, order, counts, chips, the mini-scoreboard's six and five scoreboard requests in five minutes all as specified. |
| 3 | 4:45 PM | 4:48 PM | the turn | On time. Finals' delineation, late inactives at 2:35 and 2:55, and the "Next" line reading IND at KC 8:20 PM ET, all correct. |
| 4 | 8:35 PM | **9:16 PM** | the day | 41 minutes late, for the same reason as 1: mid-build on C-1 and did not stop. Everything below was read live at 9:16 to 9:25 PM. |

Two of four were late and one was missed outright. The cause is the same each time: a
checkpoint is an interruption of building, and nothing interrupted the building. The
instrument for the next programme is a clock that fires, not an intention.

## Checkpoint 4, in full

Read from the live site with a cache-busting query at 9:16 PM ET.

| Expected | Read | |
|---|---|---|
| Marquee: IND at KC live | IND at KC, `data-state=in`, **10-10**, "Live &middot; NFL &middot; 10:26 - 2nd" | met |
| The Edition: one paid run at 7:38 PM | one paid run, cron `38 23 * * *` (7:38 PM ET), ledger row written 7:52 PM, **$0.3786**, 237,771 tokens, `pushed=true`, against a $1.50 cap | met |
| The lead story under the day rule | "Dak Prescott breaks Cowboys passing touchdown record, September 20" leads, a story from today | met |
| The Edition card's date line | "The Evening Edition / Read tonight's Edition / September 20, 2026 &middot; 7:48 PM ET" | met, and "tonight's" is earned: tonight's edition had published |
| The week page | "Week 2 inactives", **29 lists posted, 177 players**, updated Sep 20 7:01 PM ET, per-list stamps at 7:01 PM and 3:06 PM | met |
| The health lines | 39 sources, **36 OK, 3 CHALLENGED** (ESPN's college football, NFL and tennis RSS, HTTP 202 bot challenge, a known and separately documented condition), all 39 lanes OK, no feed whose newest item is over 12 hours old | met |
| Block A ready to push at 6 AM | nine commits held, canary green, odds gate PASS | met |

Two further readings, both from the ledger: the 8:11 PM and 9:11 PM runs are the caged
watcher, `outcome=no report`, $0.00 and no push. The cage is holding.

Screenshots: `cp4-1440-2125.png` and `cp4-390-2125.png`. The phone capture is 390 wide,
not the 375 the programme asked for, because that is the width the shot tool's phone mode
uses; the file is named for the width actually captured. Neither width scrolls sideways.

## Differences, with the Programme 5 item that covers each

| # | What | Covered by |
|---|---|---|
| D-1 | **The band's stamp said "Updated 8:00 PM ET" at 9:16 PM** while the scores under it were seconds old, because the live poll rewrites the numbers and nothing rewrites the stamp. One page, two bases: the reader is told the board is 76 minutes old while looking at a current score. This is the Crypto desk's C-5 exactly, on Sports. | **new**. Sports twin of C-5. The stamp has to say which of the two it is stamping: the poll's last success while the poll is running, the build otherwise. |
| D-2 | **The week page still said "Sunday's lists post about 6:50 PM ET" at 9:20 PM**, beside its own line saying 29 lists were posted. The forward-looking sentence does not retire when the thing it forecasts has happened. Checkpoint 3 recorded the same shape at 4:05 and 4:25. | **A-5** (`_dg_list_state`), which rules on a list's state but is not reaching this sentence. Extend it, do not write a second rule. |
| D-3 | A-1's build hooks fired the 6 AM and noon builds and the marquee builds, and the last build before this read was 7:48 PM. That is correct by the current rule and is also why D-1 is visible: with no build for 76 minutes, the stamp and the poll drift as far apart as the gap. | **A-1**, working as specified. D-1 is the fix, not more builds. |

## Three instrument corrections from today

Recorded because each one nearly became a finding.

1. **ESPN blocks headless Chrome by user agent.** Two readings of the live poll as broken
   were the harness being refused, not the poll. The poll was working the whole time. A
   commit that said "ESPN sends no CORS header for localhost" was amended with the
   correction.
2. **A `file://` read of the built site has no stylesheet.** The pages link
   `/assets/site.css` root-absolute, which under `file://` resolves to the filesystem root
   and 404s, so every measurement came back with the unstyled defaults: padding 0, one
   font size everywhere. Measure over HTTP. A count of "green fills on the card" taken
   this way could only ever have seen inline styles, and the stylesheet's own fill is
   exactly what it was meant to prove gone.
3. **`textContent` joins block children with no separator.** A headline read back as
   "...on September 18, 20267:41 PM ET" and looked like a missing space. It is two block
   spans, 65px tall, on two lines, and renders correctly. Checked before recording, which
   is the only reason it is not a fourth false finding in this file.
