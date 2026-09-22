# Handoff, Thursday 17 September 2026, evening

No tokens, no keys, no secrets in this file. The repos are public.

## Read this first on Friday

**N-7b is the first thing on Friday, before anything else on the list.** It is the
poller's data model, so it lands as one commit with its test, in the morning, not during
a game.

The defect. `inactives.load_week()` merges eight day files and keeps a player's FIRST
sighting, and `board()` sets a team's `first_seen` to the MINIMUM across the week. So a
player inactive on the 13th and again on the 17th carries only the 13th on the week page,
and a team that had a list in Week 1 is stamped Week 1 for the whole week.

What it should do:

- the merged board keeps EVERY sighting with its own date and the game it belongs to
- a team's `first_seen` is the LATEST list's, not the oldest
- the week page shows a repeat listing under each week it belongs to

The canary: a player inactive on the 13th and the 17th appears under both, each with its
own date. Prove it by breaking it, as with the others.

Note the game page no longer depends on this. `site_build._ia_for_game` reads the day
file for the game's own Eastern date (commit b17faa5), so tonight's lists are right on
the game page whatever the merge does. N-7b is about the WEEK page.

## Held commits, and when they go

Two Sports commits are committed locally and deliberately unpushed. The freeze protects
the first live test of the band, and the week's inactives page is live and correct, so no
reader is without the lists.

| commit | what |
|---|---|
| `797ec49` | H-6: the count line names what the tab holds, in the case that actually occurs |
| `b17faa5` | H-1: this game's inactive list comes from this game's day, not the week's merge |

Push both **at the final whistle tonight if the session is up, otherwise 6 AM Friday**,
and say which happened.

Crypto's queue went out at 8:15 PM; if it did not, it is six commits ahead of origin and
they rebase cleanly (no file overlap with the desk's own runs).

## What shipped today

UX-1 to UX-18, closing every item in `UI-UX-AUDIT-2026-09-17.md` (S-1..S-19, C-1..C-12),
then the lead items Jack authorised:

- **S-L1** standings and the AP Top 25, `6cebf70`
- **S-L2** team pages, `c4b71d0`
- **S-L4** sticky mini-scoreboard, `d00eeea`
- **S-L3** my teams (device-only pins), `5adf72e`
- **C-L1** coin pages, **C-L4** pinned-coin mini-board, **C-L5** provenance on tap

Not started, and scheduled elsewhere: **S-L5 and C-L2** (the Wire and the reader panel)
are Monday; **C-L3** (the Board live from the Worker) is Saturday.

## Rules learned today, worth not relearning

**A bare class selector is not a safe way to say anything about position or layout on
this chassis.** `body > :not(.ground){position:relative}` from the A-14 atmosphere is
(0,1,1) and beats any bare class at (0,1,0). It silently broke the phone tab bar, the
standings team column, the schedule table and the mini-scoreboard, in one day, twice
after I had written the warning down. Give the element, or give the table its class.

**A generic modifier class collides.** `.msb-s.lead` picked up the stylesheet's own
`.lead`, which carries 34px of padding, and a 33px strip rendered at 78px. Namespace
modifiers the way the Ticket card does.

**A fixture that goes through a build has to survive the build's own fetch.** Two attempts
to test the H-6 count line wrote into `site/data/scoreboard.json` and rebuilt; `build()`
calls `scoreboard.refresh()` first and overwrote both. The canary calls
`scoreboard_band()` directly for that reason.

**A name in a detail is not what a story is about.** The team pages matched a team's full
name anywhere in a story's summary fields and put a 49ers story on the Titans page,
because the key fact named the Titans as the opponent. Claims come from the headline or
the dek. Fourth member of the family after the nickname rule, the date-stamp trap and
`RECURRING_ACTORS`.

**Never a fabricated number, applied to standings.** The upstream endpoint answers for
the season it thinks is current: in September that is thirty NBA and NHL teams at 0-0. A
league writes only when its teams have played. It also returned "2027" for MLB while
handing back the 2026 pennant race, so the season year is not printed anywhere.

## Open

**M-9 to M-18 have never been defined.** PROGRAM-4 carries M-1 to M-4; M-19 was given
inline. Jack says the master list is in the close paste; as of 7:40 PM it had not arrived
in Downloads. Block 2 cannot start without it.

**The merge undercount above (N-7b)**, until Friday morning.

## Weekend additions (given 7:56 PM Thursday)

None of these is a new surface. They decide whether anyone finds the sites and whether
we know they are wrong before a reader does.

**P-2, Friday, one hour, after N-7b.** Reachability for search engines. Confirm both
sitemaps and the news sitemap are complete after today's additions (standings, 32 team
pages, 100 coin pages), that every page carries one canonical, that the 301s from old
URLs still resolve, that robots.txt allows everything meant to be crawled, and that the
structured data validates. The report gives Jack the exact sitemap URLs and the
verification method he needs for Google Search Console, Bing Webmaster Tools and the
Google Publisher Center application. He submits; we supply.

**P-1, Saturday, with R-5.** The live-page probe, in the Worker, which already wakes
every five minutes. On each wake it fetches both live homepages with a cache-busting
query, reads the stamps it finds there (the Sports band's "Updated", the Crypto Board's
"As of", the Edition card's date) and the response headers, and writes the reading to a
small KV record. When a stamp is older than the register's freshness for that surface, or
a page fails to load twice running, it opens ONE issue on that desk's repo and adds a
line to the morning health report. This is M-16's freshness column enforced against the
live pages rather than the repo, which is the only place staleness is real.
Test: set the Board's freshness to one minute, watch the probe flag it, set it back.

**P-3, in the Saturday close report.** An accessibility pass: contrast on the dark cards
and the chips at 4.5:1 or better, visible focus on every control including the folds and
the tabs, the tab switcher and the fold open usable by keyboard and announced by a screen
reader, and the reduced-motion path checked on both sites. Lighthouse accessibility
scores for the homepage, /scores or /pulse, and a game or coin page, at both widths.

### For the register, answered Thursday night

Cloudflare Web Analytics is on BOTH sites, and has been since before the audit:

| desk | since | commit |
|---|---|---|
| Crypto | 10 July 2026 | `99d0c4c`, "gated CF analytics" |
| Sports | 19 July 2026 | `f6fbb13`, inherited when the chassis was cloned from Crypto |

The beacon renders only when `CF_ANALYTICS_TOKEN` is set, so no key is in either repo;
the token is set in both Netlify environments, and both live homepages carry the beacon
tonight. Neither site loads Google Analytics. Jack can read traffic in Cloudflare now,
before Netlify Analytics is decided.

## Program 5 (Sunday 20 September), and Jack's decisions

**Backdrop: A, the velvet blend.** Jack chose it on the 20th over the analysis's
recommendation of B ("stadium lights"). B-2 builds the velvet: the two team colours
meeting in a soft blend, with grain and one skewed sash. The glow-and-field-lines option
is not the fallback, it is off. C, the crest, still belongs on the share card only.

Still Jack's to decide: the sportsbook links question (needs the state rules read first),
the default lens (recommended All), and whether the countdown shows on the band's rows or
only the marquee (recommended both).

**The law that changed on the 20th.** Lines come onto the site as facts: spread, total and
moneyline from the feed's odds object, the provider named on the card ("DraftKings via
ESPN"), the line at open beside the line now once the poller logs it, and on finals
whether the favourite covered and whether the total went over. No picks, no advice, no
sportsbook links. The share card's "No odds" line retires and the Standards page gains a
paragraph saying lines are shown as reported and attributed. Everything else stands.

**Blocks:** A Monday 6 AM (the morning after: build hooks, counts from the cards, the
mini-scoreboard, expiring live state, fantasy corrections). B Tuesday and Wednesday (the
Ticket second cut, the ordering law, the lenses, the week). C Thursday and Friday (lines,
leaders and linescores, win probability, pinned reordering, the share card). D on Crypto
Monday and Tuesday (L-1 live Board, C-13, CR-1 and CR-2, D-2, the phone, the watchlist).
E is the desk: the lead rule gains the day, and the Wire and reader panel land the week
after Block C.

**A-1 needs Jack**, and nothing else in Block A does: one Netlify build hook per site
(Site configuration, Build and deploy, Build hooks), the URLs into the Worker's secrets,
never logged.

## Sunday 20 September: the four checkpoints

Evidence, not build tasks. A defect found at a checkpoint is RECORDED, not fixed, until
the freeze lifts at 8:30 PM. Each one: clock time, the build stamp read back with a
cache-busting query, the DOM facts, and two screenshots (375px and 1440px) under
shots/checkpoints/2026-09-20/ with the checkpoint number in the filename.

| # | Time | What |
|---|---|---|
| 1 | 11:45 AM | The lists. 1 PM games read "posted 11:3x" with a count; 4:05 and 4:25 still "post about"; the inactive flag only where a list posted; the hub counts Week 2. Record the poller's snapshot times and whether the builds landed inside ten minutes. |
| 2 | 1:30 PM (H-12) | The slate live. Marquee and why under SC-3; the order of the eight; header and tab counts; the mini-scoreboard's six; situation, possession, clock; chips; five scoreboard requests in five minutes; the points page's top ten and stamp; one game page against its card. |
| 3 | 4:45 PM | The turn. Finals' delineation; how many finals still carry a situation line (expected non-zero until A-4); order across finals and live; the late inactives at about 2:35 and 2:55; points for finished games; counts; the "Next" line (expected IND at KC 8:20 PM ET). |
| 4 | 8:35 PM | The day. Marquee (expected IND at KC live); the Edition's run time, cost and push from the ledger (expected one paid run at 7:38 PM); the lead story under the day rule; the Edition card's date line; the week page; the health lines; and the first two Block A items ready to push at 6 AM with their tests named. |

All four go in one U-5 table in Monday's first report, with a line per difference naming
the Program 5 item that covers it, or "new".

Sports pushes: nothing 12:30 to 8:30 PM ET. Crypto is NOT under the freeze; D-1 to D-6
may push today outside the Edition quiet hour, 6:30 to 8:15 PM ET.

---

# Monday 21 September 2026, the deploy budget and what runs on its own

No tokens, no keys, no hook URLs in this file. The repos are public.

## Jack's action, and it is the only one outstanding: deploy the Worker

The window-open and window-close rule is on `main` in gcm-newsroom and **is not live**.
Until it is deployed the old 30-minute cadence still fires: about eight firings for a
single Monday night game, and 32 on an NFL Sunday.

| | |
|---|---|
| repo | `gcm-newsroom` |
| commit | `15e1188` on `main` |
| worker | `gcm-slot-trigger` |
| command | `cd slot-trigger && npx wrangler deploy` |

Run it from the Mac, from the repo root's `slot-trigger` directory. Wrangler uses the
login already on that machine; nothing here needs a token and none is printed. Before
Sunday is what matters, because Sunday is where the 32 firings are.

## Where the inactives lists are live now, so the next session does not "fix" it

**The inactives page is the live surface.** `/fantasy/inactives.html` fetches the day's
committed snapshot itself, every five minutes, and the file carries `max-age=300`, so
the board is inside ten minutes of a poller run with no deploy behind it.

**The game pages and the scoreboard cards are built content.** The lists on a game page
and the word "posted" on a card arrive with the window-open hook at kickoff and the
last-final hook, not with every poll. That is inside the budget and it is deliberate.

## The day's deploy count, in two halves

The desk cannot read the Netlify list and should not use Jack's login, so the number is
assembled from two places.

**What the desk counts itself**, printed in the handoff and the U-5 report with the
date: production pushes to `main` that the ignore script let through (merges, the 6 AM
batch, the Edition, story pushes), plus the hook firings the Worker logs.

**What only Netlify knows**, and Jack's setup: each project's Notifications gain an
outgoing webhook on "Deploy succeeded" posting to a Worker route; the Worker keeps a
per-site count per day in KV and answers `/deploys/today`; the desk reads that at
handoff time and prints it beside its own tally. Until that exists, Jack's weekly read
of the Netlify list is the reconciliation.

Netlify project names are the domains: gocheckmysports.com, gocheckmycrypto.com,
gocheckmyweather.com, gocheckmyparents.com, gocheckmypet.com, gocheckmynews.com,
gocheckmy.com, api.gocheckmy.com. The project IDs are on each project's configuration
page, which is Jack's read.

**21 September, what this desk can count:** 4 production pushes to main (the three at
4:23 PM plus the 11:39 AM gate fix), 1 branch deploy (`search-s1-canonical-urls`), and
the Netlify list itself was rate-limiting all afternoon and would not load. The two
4:2x pushes are confirmed built and spent from the publish times Jack read: sports at
4:25 PM, crypto at 4:26 PM.

## The allowance

Sports 12 a day, 16 on Sunday. Crypto 5. The newsroom's six sites one each. Weather,
Parents and Pet 6 a day between them for previews and merges.

## What is paused, and why

**S-1 and S-2** are paused until the period resets. The branch exists
(`search-s1-canonical-urls`, `64fe43f`), the generator is written and tested, and the
work is five sites: Weather, Estate, Sports, Crypto and News. Parents and Pet already
pass the whole test in production. One preview per branch from tomorrow.

---

# U-8: a push is verified by hash, not by exit code

**22 September 2026.** A `git push` returned exit 0 while a rebase was still in
progress. The local branch was sitting on origin's own tip, so the push was a no-op:
nothing of the desk's work landed, and the exit code said it had.

Nothing was damaged, and that is the point. The exit code was true and useless.

**After every push, fetch and compare the hashes.** Both go in the handoff, for every
push of the day:

```sh
git push origin main
git fetch -q origin
git rev-parse --short HEAD          # what the desk believes it pushed
git rev-parse --short origin/main   # what is actually there
git rev-list --count origin/main..HEAD   # must be 0
```

A push is done when those two hashes match and the count is zero. Not before.

## Pushes on 22 September

| repo | local HEAD | origin/main | ahead |
|---|---|---|---|
| gocheckmysports | `a6e24d9` | `a6e24d9` | 0 |
| gocheckmycrypto | `453427b` | `453427b` | 0 |
| gcm-newsroom | the `sp` commit, on main | matched | 0 |

## Networks the feed abbreviates

`network_name()` maps what the desk has seen. Anything without an entry prints exactly
as the feed gives it, which is the safe default and the reason this list exists rather
than a guess at the whole catalogue.

Mapped today: `ESPN Unlmtd` to ESPN Unlimited, `USA Net` to USA Network,
`NBC Sports BO` to NBC Sports Boston.

Seen and left alone, because they are the names themselves rather than shorthand:
`ESPN+`, `ESPNU`, `MLB.TV`, `CW26`, `Fox 12 Plus`, `SEC Network`, `ACC Network`,
`Scripps Sports`, `Peacock`, `Prime Video`, `TNT`, `ABC`, `CBS`, `FOX`, `NBC`, `CW`.

Add to the map when a new shorthand appears on a card, not before.

---

# Standing rules for this desk

Three rules, each written after a specific failure. U-8 has its own section above with
the commands; the other two are stated here in full.

## U-7: a headless browser is closed in a `finally` block

Every measurement harness spawns Chrome. A harness that throws between spawn and kill
leaves the process alive, and a session that measures forty times leaves forty of them.
The kill goes in a `finally`, not on the happy path.

`gcm-tools/harness/measure.mjs` is the desk's harness and lives in the repo rather than
in `/tmp`, because `/tmp` is cleared between sessions and the harnesses were rewritten
from memory three times before that file existed.

## U-8: a push is verified by hash, not by exit code

See the section above for the command sequence. A push returned exit 0 while a rebase
was in progress, against a branch sitting on origin's own tip: the push was a no-op and
the exit code said it had worked. Both hashes go in the handoff for every push.

## U-9: a new test is not trusted until it has been seen to fail

**22 September 2026.** The recurring failure of this session was not in the code. It was
checks that passed by not running:

- a canary guarded on `TEAM_DATA` being loaded, which the canary never loads, so the
  whole block was skipped in silence;
- an assertion matching `data-mine`, a string the script contains as well as the markup,
  so deleting the markup left it green;
- a comparison asking whether `max(spark + [price]) < price`, which cannot be true
  because the price is in its own input;
- a fixture whose periods summed to exactly the score, so a total computed by adding the
  cells passed a test written to stop exactly that;
- an assertion on a belt's WORDING that failed when the message improved, over a
  sentence the belt was catching correctly.

Each looked green. Each tested nothing.

**Before a test is committed:** break the thing it guards on purpose, watch the test go
red, restore it, watch it go green. **The report names the break used.** A test that
cannot be made to fail is deleted, not kept.

The newsroom's own tests get the same treatment the next time one is touched.

---

# For tomorrow's handoff

**The board's stamp between slates.** At 6:02 PM on 22 September the home scoreboard read
"Updated 3:28 PM ET" with no game live and the next first pitch at 6:40. That is the
build's stamp doing what D-1 asks of it, and it is not a finding. Confirm two things once
games are live: that the stamp moves with the Worker's refresh, and that between slates
the board still tells the reader when the next game starts, as it does now.
