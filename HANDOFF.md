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
