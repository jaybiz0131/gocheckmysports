# Handoff, GoCheckMySports and GoCheckMyCrypto

Read this file first, then the current program section. Under 300 lines by U-1; the day
history for 17 to 22 September is in `docs/HANDOFF-2026-09-17-to-22.md` and nothing in it
is live.

No tokens, no keys, no hook URLs in this file or any other. The repos are public.

## Live as of 24 September 2026

- **Jack's outstanding action.** Deploy the Worker. The COUNTS KV namespace was created and
  bound on 24 September (`gcm-newsroom`, `slot-trigger/wrangler.toml`). The webhook secret is
  set with `npx wrangler secret put NETLIFY_WEBHOOK_SECRET`, never in a file, and the Netlify
  outgoing webhook points at `/hooks/netlify-deploy` for Deploy succeeded and Deploy failed.
- **The Worker serves four routes**: the deploy counter, `/go`, `/counts` and `/hit`. None of
  them touches the five-minute schedule trigger, which runs in `scheduled` while the routes
  are branches in `fetch`.
- **Sports push window.** Nothing between 12:30 and 8:30 PM ET **on Sundays**, which is the
  game window. That is the rule as issued and it applies to no other day. This file said
  "nothing 12:30 to 8:30 PM ET" flat, with no day named, which was a widening nobody issued
  and cost a held push on Thursday 24 September before Jack corrected it.
- **Crypto** is not under the freeze and may push outside the Edition quiet hour, 6:30 to
  8:15 PM ET.
- **The deploy allowance**, per day: Sports 12 production deploys (Sundays 16), Crypto 5, the
  newsroom's six sites one each, and Weather, Parents and Pet six between them.
- **The day's deploy count** is read from the Netlify commit statuses on GitHub through `gh`,
  never from a Netlify token, until the Worker's deploy counter is live, when that becomes the
  count of record (U-11). The command:

      gh api repos/jaybiz0131/gocheckmysports/commits/<sha>/statuses --jq '.[].context'

- **Where the inactives lists live**: published from the repo at
  `raw.githubusercontent.com/.../site/data/inactives/inactives-<day>.json`, fetched by the
  page itself. The poller commits them every 15 minutes and those commits do not build the
  site. This is working as designed; do not "fix" it.
- **Networks the feed abbreviates.** `network_name()` maps only what the desk has seen:
  `ESPN Unlmtd` to ESPN Unlimited, `USA Net` to USA Network, `NBC Sports BO` to NBC Sports
  Boston. Anything unmapped prints exactly as the feed gives it, which is the safe default.
  Add to the map when a new shorthand appears on a card, not before.

# Standing rules, all desks

**U-1 to U-11, issued 24 September 2026, 12:50 PM ET. This is the one text.** Every desk
(Pet, Parents, Weather, Sports and Crypto) writes it into its HANDOFF.md as the
standing-rules section, replacing whatever set it holds, in one commit, and says so with
the hash in its next report. A rule is issued once by Jack, numbered next in the sequence,
and every desk records it the same day, unchanged. A desk that finds a rule missing from
its file says so in its report rather than cross-referencing a rule it cannot see. Three
entries name things that are not on every desk; keep the rule, substitute the particular.

## U-1. One session per sprint, one handoff file.

The desk's HANDOFF.md, outside the published tree, is the only handoff: a session begins by
reading it and the current program section, and everything the next session needs goes back
into it at the end of every sprint and after every report. Under 300 lines, no tokens or
keys of any kind, no second file, no parallel notes.

## U-2. Model by kind of work.

Sonnet subagents for the mechanical items: greps and replacements, deletions, screenshots,
harness runs, tallies and report assembly. Opus for design and engine work and for anything
read and matched by eye.

## U-3. Batch, never poll.

One harness run per sprint plus one re-measure when a change lands; screenshots once per
page per sprint; log and workflow checks once per report. Never wait on a Netlify build or a
workflow run inside the session: note the commit, move to the next item, read the result at
the next check.

## U-4. The key is for scheduled runs only.

A desk's model key is spent only by its scheduled runs: no local pipeline runs that call the
model, no test briefs, no dry runs that reach the API, and no manual dispatch of a workflow
that spends, other than the one agreed backstop where a desk has one. Every stage is tested
on fixtures on its no-model path; a stage without one gets one before it is tested. Every
model call appears in the desk's ledger; a spend that is not in the ledger is a leak and
goes in the next report with its cause.

## U-5. Report form.

One line per item, no narrative, no adjectives: what merged, with both hashes; what was read
live and the stamp it was read at; what the tests say, with each new test's break named; what
is open; what is Jack's. Counts are printed as recorded, nothing rounded, nothing estimated,
and a number that does not exist is said not to exist. When a decision is needed, one
paragraph with the two options and the desk's recommendation.

## U-6. No re-derivation.

Do not re-read boards, packages or repositories to reconstruct state the handoff carries;
open the file named for the item and the board named for it. Where a board and a rule
disagree, ask in one line before inventing.

## U-7. A headless browser is closed in a finally block and launched with a timeout.

Issued to the Pet desk, September 22, 2026, after fourteen headless Chromes from other
sessions were found alive on the machine. A harness that throws between spawn and kill
leaves the process alive, and a session that measures forty times leaves forty of them. The
kill goes in a finally, not on the happy path, and the launch carries a timeout, so nothing
outlives the read that started it. The shared harness is gcm-tools/harness/measure.mjs, in
the repository rather than in /tmp, because /tmp is cleared between sessions and the harness
was rewritten from memory three times before that file existed.

## U-8. A push is verified by hash, not by exit code.

September 22, 2026: a git push returned exit 0 while a rebase was still in progress; the
local branch sat on origin's own tip, so the push was a no-op and nothing of the desk's work
landed, and the exit code said it had. After every push, fetch and compare: git push origin
main; git fetch -q origin; git rev-parse --short HEAD; git rev-parse --short origin/main; git
rev-list --count origin/main..HEAD, which must be 0. A push is done when the two hashes match
and the count is zero, and both hashes go in the handoff and the report for every push of the
day, preview and merge.

## U-9. A new test is not trusted until it has been seen to fail.

September 22, 2026: the recurring failure of that session was checks that passed by not
running: a canary guarded on data it never loads, so its whole block was skipped in silence;
an assertion matching a string the script contains as well as the markup, so deleting the
markup left it green; a comparison that cannot be true because its own input is on both
sides; a fixture whose parts summed to exactly the total, so a test written to catch a summed
total passed; an assertion on a message's wording that failed when the message improved. Each
looked green and tested nothing. Before a test is committed: break the thing it guards on
purpose, watch the test go red, restore it, watch it go green, and name the break in the
report. A test that cannot be made to fail is deleted, not kept.

## U-10. A measurement counts only when the thing measured is the thing shipped.

Issued on the Weather desk, September 23, 2026, after its fit tests were found measuring the
system font instead of the shipped face: every number they produced was real and about the
wrong thing. A test that measures a font, a build or a file first proves it has the real one
and fails loudly on a stand-in rather than quietly measuring the substitute. For every desk:
a read of production names the stamp it read and fails if that is not the deploy it meant; a
screenshot comes from the preview or production URL named in the report, never from a local
build; a harness number is taken on the deployed page with its own fonts loaded; a suite run
after a new file is added regenerates the project first, so the binary under test is the tree
under test; a fixture run against a stubbed model says so beside its result and never stands
in for the live run the report asks for. This is U-9's other half: U-9 asks whether a test can
fail, U-10 asks whether it is looking at the shipped thing.

## U-11. A commit that changes nothing in the published tree does not build the site.

Issued September 24, 2026, after the Pet and Parents desks each found handoff and script
commits in their production deploy lists: three builds on Pet and three on Parents this week
with no site change behind them. A deploy changes what the site says; a number changing is
never a deploy. netlify.toml carries an ignore rule so a commit touching only HANDOFF.md,
docs/ or scripts outside the published tree does not build, proven once by pushing a handoff
update after a merge and showing no build followed. Every page carries the build's stamp, the
merge commit written by the build into one meta tag and /stamp.txt, and every live read
asserts it before measuring. The day's deploy count is read from the Netlify commit statuses
on GitHub through gh, never from a Netlify token, until the Worker's deploy counter is live,
when that becomes the count of record; the method is printed once in the handoff and the
count in every report.

---

# For tomorrow's handoff

**The board's stamp between slates.** At 6:02 PM on 22 September the home scoreboard read
"Updated 3:28 PM ET" with no game live and the next first pitch at 6:40. That is the
build's stamp doing what D-1 asks of it, and it is not a finding. Confirm two things once
games are live: that the stamp moves with the Worker's refresh, and that between slates
the board still tells the reader when the next game starts, as it does now.
