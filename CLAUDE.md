# GoCheckMy newsroom: operating brief

Claude Code reads this file at the start of every session in this repo. It exists so a
cold session does not re-diagnose a solved problem, and does not re-break a rule the desk
learned the hard way. Keep it current: when you fix something structural, add it here.

The three desks (gocheckmysports, gocheckmynews, gocheckmycrypto) share one chassis.
A fix to shared code belongs in all three unless the reason is desk-specific.

---

## 1. The loop

Diagnosis starts with the actual failing step, never the run summary. The summary shows
annotations, and the real cause is usually in a step log that produces no annotation at
all. Both times a human escalated this week, the cause was invisible from the summary.

```sh
gh run list --workflow=crypto-news-brief.yml --limit 10
gh run view <run-id> --log-failed        # the failing step's log, in full
gh run view <run-id> --json jobs --jq '.jobs[].steps[] | select(.conclusion=="failure")'
```

A run is healthy when: it is green, the summary carries no errors, an edition file exists
for the slot in `site/content/<date>-<slot>-brief.json`, and the stories that ran are on
`main`. Green alone is not enough. A run can be green and have published nothing.

Before pushing anything: `python3 verify_pipeline.py canary` must print
`LAYER 1 CANARY: PASS`. It is a hard gate and it is fast. Never push on a red canary.

---

## 2. Doctrine

These are not style preferences. Each one was written after a specific failure, and each
one has been violated at least once by a well-meaning fix.

**The part is not the whole.** A defect in one sentence costs that sentence, not the
story. A defect in one story costs that story, not the run. This was ruled three times:
the story is not the sentence (2026-08-21, `approver._repair_rejects`), the edition is
not the sentence (2026-09-02, `edition_repair.py`), the contradiction is not the whole run
(2026-09-03, `consistency_gate._quarantine`). If you are about to make a gate fail an
entire unit of work over a localized defect, cut the defect instead.

**Fail-closed means do not ship the wrong thing. It does not mean ship nothing.** Every
gate needs an answer to "what publishes when this fires?" A gate whose only answer is
"nothing" will eventually take the whole desk dark over a false positive, and every gate
on this chassis is grep-class heuristics that produce false positives.

**A shallow key is not an identity.** Two stories sharing one token are not the same
subject. "fbi" paired an agent's $1M theft with a $560K Hamas seizure and blocked a
publish (fixed: `consistency.RECURRING_ACTORS`). The same class caused the supersede bug
in section 5. Any matcher keyed on a single shared token needs a floor.

**A model declaration is not a fact.** When a model says "this story updates that one" or
"this claim is unsupported," that is a claim to be checked, not an instruction to obey.
The trace checker now states `stands` per item and withdrawn items are dropped
(`wrap.check`). The supersede path does not check anything yet, and it retired a correct
story. See section 5.

**Refusals are not editorial kills.** When the writer cannot draft (no brief, no source
text) that is a sourcing failure. It must not enter the kill ledger, must not deepen a
streak, and must not park a real development. `kill_streak.is_refusal_title` filters
these; extend it when a new refusal phrasing appears rather than letting it ledger.

**Advisory checks warn; they do not error.** An `::error::` annotation on a green run
trains everyone to ignore annotations. The offline canary runs inside `::stop-commands::`
because its deliberate negative tests were posting fake errors on every run. Keep it that
way, and keep advisory checks (kill streaks, dupe audit, coverage gaps) at warning level.

**No em dashes anywhere.** House rule, family-wide, enforced by belts and by `destyle`.

---

## 3. Fixed this week; do not re-diagnose

| Symptom | Cause | Fix |
|---|---|---|
| Editions failing nightly, 40+ "Edition stage failed" issues | Trace checker listed items its own reasoning withdrew; hand-kept phrase lists never covered the next wording | Checker states `stands` per item; withdrawn items dropped before any word list (`wrap.check`) |
| Whole slot lost to one bad sentence | Edition failed as a unit | `edition_repair.py`: cut the flagged sentences, then Sonnet rescue, then a digest built only from published stories |
| Every run showed errors | Canary's deliberate negative tests posted as annotations | Canary wrapped in `::stop-commands::`; real failure still exits non-zero |
| Stories lost to 429/403/202/timeouts | No retry, no per-host spacing, 200KB read cap, no JS-shell fallback | `common.fetch_page_meta`: polite spacing, retry with Retry-After, 600KB, `next_data_text` |
| Verified stories starved of text | Feed-text fallback only fired when every page failed | Fires whenever total readable text is under 1200 chars (`verifier.gather_sources`) |
| Publishable stories starved of budget | Drafting order was editor rank; REVIEW stories consumed budget VERIFIED ones needed | VERIFIED drafts first (`writer.select`) |
| Kill streaks on "STORY REJECTED: Research Brief Required" | Writer's refusal returned as the draft, then ledgered as a kill | `writer._is_refusal` drops them; `kill_streak.is_refusal_title` ignores any still in the log |
| Stage failures on transient API errors | 4 attempts over 14s | 5 attempts over ~45s with Retry-After (`llm._post_with_retry`) |
| Evening slot never self-healed on sports/news | Recovery window 23:48-24:00 contained no watcher tick | Window crosses midnight to 05:00; `missed_slot` checks the slot's own day |
| Whole run discarded over a false contradiction | Consistency gate was all-or-nothing, last step before push | `consistency_gate._quarantine`: withhold the colliding surface, publish the rest |
| Correct live stories missing from every listing page | An editor update declaration was obeyed with no check, and a chain retired its own first chapter | `site_build.supersede_ok` floor, `mark_continued` for lineages, dangling pointers fail open |

---

## 4. Open work, in priority order

Priority is by reader impact: a correct story nobody can reach is worse than a missing
one, and a wrong story is worse than both.

### P0. Push the pending gate fix (crypto)
`~/Downloads/newsroom-gate-fix-2026-09-03/gocheckmycrypto/0001-*.patch`. Until it lands,
any cross-surface collision still discards a whole crypto run.

### P1. DONE, pending push: false supersedes were hiding 22 correct stories
Patch: `~/Downloads/newsroom-supersede-fix/`. Sports and news only; crypto updates in
place and never writes `superseded_by`.

**What was happening.** `site_build.find_superseded` had a declared path that obeyed the
editor with no check of any kind:

```python
if declared_title and t.strip() == declared_title.strip():
    return d.get("slug")
```

One declaration retired a live, correct, VERIFIED story from the homepage, every listing
page and the archive, and rewrote its page to send readers to an unrelated story.
Permanently: nothing un-supersedes. Second defect: the ingest block that creates a CHAIN
(two genuine developments of one storyline) called `mark_superseded` too, deleting the
first chapter of a lineage its own comment asks to keep visible. Third: one pointer per
desk named a successor that was never published, so the story was hidden behind nothing.

Measured: 8 stories wrongly hidden on sports (including the audit's Clippers penalties
story, retired by an unrelated SEC/Daktronics item with **zero** shared title words), 14
on news (a Seattle shooting retired by a Georgia sentencing, a Grand Canyon flash flood
retired by a Nepal flood, a Midwest flood threat retired by Indiana storms).

**The fix.** `supersede_ok(old_title, new_title, old, new)` gates retirement: shared
subject words are mandatory, then either a third of them overlap or `dedupe.same_event`
agrees. A declaration that fails is DOWNGRADED, not discarded: the pair links as a
lineage (`continued_by` on the older story, `update_of` on the newer, a callout on both)
and both stay reachable. That failure mode is deliberate. Two live cross-linked pages is
a small cost; a correct story nobody can reach is the failure a reader notices.

**A date stamp is not a subject.** The first cut of this fix still cleared the Clippers
case, the very pair it was written to stop. Titles on these desks carry a "(September 2)"
suffix, so `september` was a shared "subject" word, and with `dedupe.same_event` agreeing,
that single token carried the whole floor. Month, weekday and slot names
(morning/afternoon/evening) are now in `GENERIC_TITLE_WORDS`. When you add anything to a
title template, ask what it does to every matcher keyed on title words: a token every
story carries is a token that matches everything.

Verified against both corpora: 47 of 55 sports chains and 65 of 79 news chains still
retire, exactly the wrong ones stop. Canary passes on both desks and both sites build
clean.

### P2. Duplicates reaching publish
Audit found USPS x3 in 76 minutes, Revolut x4, SEC x3. Guards exist and partially work
(run logs show `autopilot: VERIFIED and APPROVED, then held: near-duplicate`), so this is
a leak, not an absence. Investigate in this order:

1. **Are the duplicates from one run or consecutive runs?** Check `published_utc` spacing.
2. **If consecutive:** the corpus guard compares against the checkout, and the workflow
   checks out `main` at run start. A story published by run A after run B started is
   invisible to run B. `publish_sweep.py` exists to catch exactly this after fetching
   origin/main; confirm it actually runs and that its matcher is not narrower than
   `dedupe.same_event`.
3. **Suspect a feedback loop with blocked runs.** When the consistency gate blocked a
   push, the story never landed in the corpus, so the next run legitimately saw it as new
   and re-drafted it. The P0 fix reduces this, but check whether `out/published/` payloads
   are re-ingested on a later run and can produce a second file for one event.
4. Add a last-line check in `site_build.py --ingest`: refuse to write a new content file
   whose `dedupe.same_event` matches an existing live story unless the editor declared it
   an update. Deterministic, cheap, and it is the last place before the file exists.

### P3. Stale market data presented as current (crypto)
Audit: ticker reads +0.0%, frozen 11 hours. Run logs across three runs show the cause:

```
market_pulse: section 'assets' failed (HTTP Error 429: Too Many Requests)
  -> carrying the previous snapshot's assets forward (dated 2026-09-02T12:05:58Z)
```

Two separate defects:
- **The carry-forward is invisible to the reader.** The board is honestly stamped with its
  oldest data, but the ticker renders it as live. A carried-forward board must render its
  own timestamp and visibly degrade ("as of 12:05 UTC"), never present as current.
- **+0.0% is probably arithmetic on a duplicated snapshot.** If change is computed between
  the carried-forward snapshot and itself, it is exactly zero by construction. Check the
  change computation when a section is carried forward; suppress the number rather than
  print a fake zero.
- `market_pulse.py` has its own `urllib.request.urlopen` calls and did not get the retry
  and per-host spacing that `common.fetch_page_meta` now has. Route it through the same
  layer, or give it the same treatment.

### P4. The desk is blind to market moves as news (crypto)
Audit: missed BTC to ~$76,500 on the Iran/oil shock with Fed hike odds at 66%, while
CoinDesk, Cointelegraph and The Block all led with it. The watcher only fires on N
independent sources for a cluster, and a market-price trigger was deliberately removed
from the **sports** desk as editorially meaningless. On a crypto desk a large move **is**
the story. Add a market-move trigger to `watcher.py` on the crypto desk only: a BTC or
total-cap move beyond a threshold over 24h fires a breaking run. The desk already computes
these numbers every run in `market_pulse`; nothing new needs fetching.

### P5. Tennis is invisible (sports)
Audit: zero US Open coverage for two days, no Tennis section in nav, no tennis on the
scoreboard. The intake half is already fixed (ESPN feeds retired after their JSON
fallbacks 403'd from the runner; a Google News slam lane replaced them). Remaining:
- add a Tennis section to the site nav in `site_build.py`
- add tennis to `scores_pulse.py` so the scoreboard strip carries it during slams
- the event calendar already lists US Open Aug 30 to Sep 13; confirm `event_coverage.py`
  is flagging the gap and that the flag is being read

### P6. Accuracy lints the approver cannot do by reading
Audit found an article citing SEC press release 2026-83 when the story is about 2026-81,
and an article contradicting itself in consecutive sentences. Both are deterministic:
- **Identifier lint:** extract identifier patterns from the draft (`\b20\d\d-\d+\b`,
  docket and case numbers) and require each to appear in the brief. A number the brief does
  not carry is smuggled, and this is the cheapest possible check.
- **Intra-draft contradiction:** the same quantity stated twice with different values in
  one draft. The desk already has the machinery in `consistency.usd_figures`; point it at
  a single draft instead of across stories.

---

## 5. What an A looks like

Grade the desk against these, not against green runs:

1. **Nothing missed that competitors led with.** The event calendar and the watcher are
   the instruments. A marquee event with no story by end of slot is a failure even if
   every run was green.
2. **Nothing published twice.** One event, one URL, updated in place.
3. **Nothing unreachable.** Every live story is on a listing page. `superseded_by` is only
   ever set by a real update chain.
4. **Nothing self-contradictory**, within a story, across stories, or against the boards.
5. **Data surfaces are current or visibly stale.** Never a fake zero, never a stale number
   rendered as live.
6. **Every slot served.** Three editions a day, and the digest floor means silence is
   never the outcome.

When you finish a fix, verify against the next scheduled run, not against the canary
alone. The canary proves wiring; only a live run proves the desk.
