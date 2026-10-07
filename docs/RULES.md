# Standing rules, all desks, U-1 to U-16: the verified copy for cloud sessions

Placed October 7, 2026, 9:17 AM EDT by the strategy desk under Jack's ruling of October 7, 2026. The one text of U-1 to U-13 and the three October 1 rules stays where Jack's option-two ruling of October 1, 2026 put it, the Sports root handoff (gocheckmysports/HANDOFF.md, its Standing rules section); U-14 to U-16 were issued in the Weather handoff (gocheckmyweather/docs/HANDOFF.md). A Claude Code cloud session clones one repository and cannot read either file, so every repository that runs in the cloud carries this file, the same text copied byte for byte, kept honest by its hash rather than by trust: the sha256 of everything below this header is

    4179b2ac06d0dc7fb9de9987dc077884df6f4e1b5ebabe1b6ff1bb2de8b3568d

Every cloud opener prints that hash; a desk whose copy hashes differently says so in its report and does not build until the copy is restored from the one text. When Jack issues a new rule, the one text changes first and this file is re-copied into every repository the same day, with the new hash in the next opener. Nothing below this line is edited here, ever.

---

# Standing rules, all desks

**U-1 to U-11, issued 24 September 2026, 12:50 PM ET. This is the one text.** Every desk
(Pet, Parents, Weather, Sports and Crypto) writes it into its HANDOFF.md as the
standing-rules section, replacing whatever set it holds, in one commit, and says so with
the hash in its next report. **Superseded in part on 1 October 2026 by Jack's option-two
ruling above: the laws now live in THIS file only, and a desk handoff points at it by
path instead of holding a copy. The rest of this paragraph stands, including that a desk
which cannot see a rule says so rather than cross-referencing it.** A rule is issued once by Jack, numbered next in the sequence,
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

**Addition, 24 September 2026, 6:10 PM ET.** Found on the Sports and Crypto desk while breaking
a test under U-9: on this machine Python's bytecode cache lives outside the project
(`sys.pycache_prefix` under `~/Library/Caches`), so deleting `__pycache__` clears nothing and
`python3 -B` only stops writing, not reading; a source file restored within the same second at
the same length leaves a stale `.pyc` that Python runs in place of the tree. Every Python test
run on every desk therefore sets a fresh `PYTHONPYCACHEPREFIX` for the run, or clears the prefix
it uses, so the bytecode under test is the tree under test. **A suite that goes red after a
restore is read as this before it is read as the code.**

## U-11. A commit that changes nothing in the published tree does not build the site.

Issued September 24, 2026, after the Pet and Parents desks each found handoff and script
commits in their production deploy lists: three builds on Pet and three on Parents this week
with no site change behind them. A deploy changes what the site says; a number changing is
never a deploy. netlify.toml carries an ignore rule so a commit touching only HANDOFF.md,
docs/ or scripts outside the published tree does not build, proven once by pushing a handoff
update after a merge and showing no build followed. Every page carries the build's stamp, the
merge commit written by the build into one meta tag and /stamp.txt, and every live read
asserts it before measuring. 

**The count clause, replaced 24 September 2026, 6:10 PM ET.** The count of record is the
Worker's deploy counter, fed by the Netlify deploy notifications Jack set on all five sites and
read at `/counts/today` on `gcm-slot-trigger.gocheckmybrands.workers.dev`. Until it answers for a
site, a desk prints the count it can read and names its source, and a desk that can read none
says it cannot read one rather than estimating. The clause naming Netlify commit statuses on
GitHub is withdrawn: Netlify posts no status, check or deployment to the Sports and Crypto
repositories, so that method reads nothing there. The rest of U-11 stands unchanged: the ignore
rule, its one-time proof, and the build stamp in one meta tag and `/stamp.txt` asserted by every
live read, which every desk that has not built it builds on its next branch.
## U-12. An exit status is captured from the command itself, never read through a pipe or inside a string.

Issued after the same trap bit the Weather desk three times in one day and the Sports and
Crypto desk once: "$?" inside an echo string reported the command substitution's status and
not the script's; "preflight.py | tail -1" discarded the script's status and a red preflight
read as clean, and a push went out on it. The form is: run the command to a file, capture its
status on the next line before anything else runs, and judge the output only after the status
is known. A harness prints the status it captured beside the output it judged, and a report
that says a suite was green names the status it read, not the last line it saw.

### Three rules from the 1 October session (one line each, Jack, 1 October 2026)

- **A restore in a plant comes from a saved copy, never from `git checkout` on the file under
  test**, which reverts the implementation along with the plant.
- **Nothing is staged with `git add -A`.** Files are staged by name, and a message that says
  documents only is checked against `git diff --cached --stat` before the commit.
- **A push's exit status is read from the push, never from a pipe.** This is U-12's third form
  and it sits here beside U-12 by Jack's word.

## U-13. A commit never carries a conflict marker, and preflight proves it.

Issued after the Weather site served its service worker with git conflict markers in it for
six days, from a stash applied on September 23: the file did not parse, so the offline shell
and web push were dead the whole time, a published page carried an empty conflict where a
reader could see it, and nothing looked broken because the site loads from the network
anyway; preflight read the version with a pattern that found the first of two values and
passed. Every desk's preflight therefore fails on <<<<<<<, ======= or >>>>>>> anywhere in the
tree it publishes or runs; parses every script the site serves, with node --check or the
language's own check, and fails on a file that does not parse; and asserts exactly one value
wherever a conflict leaves two. A stash is applied on a clean tree and its result is read
before anything is committed.
---

## U-14 to U-16, copied verbatim from the Weather handoff (`../gocheckmyweather/docs/HANDOFF.md`)

U-14, U-15 of 2026-10-05, 12:03 PM ET; U-16 of 2026-10-05, 9:28 PM ET.

**U-14. A push is gated on the preflight's exit status.** `preflight && push`, never chained with a semicolon or a newline; a red preflight means no push, under load or not, and a green rerun is a reason to push then, not a reason the first push was fine (the process error of 2026-10-05).

**U-15. The preflight runner prints the name of every failing case, never a count alone.** A red that cannot be named cannot be fixed. The load average is printed at each preflight (`scripts/preflight.py`, start and end) and reported: 48 to 88 is one desk, 300 to 970 is two desks at once, and Jack keeps that rule, not the desk.

**U-16. A suite's output goes to a file and is read after the suite exits.** It is never piped into head, tail, a pager or anything that can close the pipe early: a closed pipe kills the suite before its finally runs, and its server stays up as an orphan on its port (the two orphaned servers of 2026-10-05, both the desk's own). The preflight's red on an orphaned port is the rule working, not noise. (2026-10-05, 9:28 PM ET.)
