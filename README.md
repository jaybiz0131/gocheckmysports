# GoCheckMySports: the daily sports news desk

This is the source of an automated sports news desk for
[gocheckmysports.com](https://gocheckmysports.com). The score is a fact; the story gets
checked. Many sources are aggregated and deduplicated; an editor model ranks and strips the
hype; an independent verifier fetches every cited source page and audits the claim; a
researcher builds a structured fact brief; a writer drafts only from that brief; a
post-draft approver traces every fact back to it, and a battery of deterministic
fail-closed gates (source liveness, dedup, compliance lint, depth, a two-source rule on
anything sourced below primary) decides what publishes. If any stage fails, the desk
publishes nothing. Opinion never ships in a human voice unless a human wrote it, and
nothing here is ever betting or gambling advice. The full editorial mechanics are described
publicly at gocheckmysports.com/method.html. Contact: desk@gocheckmysports.com.

Built on the same architecture as its GoCheckMy siblings (the Pet recall pipeline, the
Storm NFIP pattern, and the family's crypto news desk this repo was cloned from):
scheduled ingest, AI processing, verified and gated output. Standard library only,
fail-closed everywhere, self-verifying.

## The one non-negotiable rule

**The AI is the newsroom staff. The human is the editor-in-chief and the on-air voice.**
Publication is gated by the independent adversarial verifier: VERIFIED stories auto-publish
(the owner's standing full-auto instruction, implemented in `autopilot.py`),
NEEDS-HUMAN-REVIEW waits in the queue for the human, REJECT never ships. The human
editor-in-chief oversees the desk, can overrule any call in either direction, and owns
everything in a human voice: no "take" is ever machine-written. The automation removes the
grunt work (reading, triage, fact-check, drafting), never the judgment or the voice, and the
public method/standards pages describe this gate exactly as it runs.

## Sourcing doctrine

- **Primary tier: official league data.** MLB StatsAPI and the NHL API are the desk's
  ground truth for schedules, scores, and transactions; league-published data outranks any
  outlet's retelling. ESPN's scoreboard JSON rides along as stable-but-unofficial data.
- **Major tier:** established outlets with editorial standards (ESPN, BBC Sport, CBS
  Sports, The Guardian).
- **Mixed tier:** aggregated or rumor-adjacent feeds (Yahoo Sports). Never publishable
  alone; the two-source rule applies.
- **Injuries only from official reports or on-record statements.** Speculation about an
  athlete's body is not news and never runs.
- **Never betting advice.** The desk reports events; it never advises bets, picks, or
  wagers, and that discipline is enforced by a deterministic gate, not just a prompt.

## The stages

| Stage | Script | What it does | Output (in `out/`) |
|-------|--------|--------------|--------------------|
| 1 Aggregate | `aggregate.py` | Pull RSS (official league data + major outlets), normalize, keyword-gate the broad feeds, tag clusters that match the ongoing-narratives watchlist (`config.json -> narratives`), dedupe near-identical stories into clusters, run the deterministic hype pre-pass | `items.json` |
| 2 Editor | `editor.py` | Managing-editor AI ranks the top stories by genuine sporting significance and strips the hype, showing its work | `editor.json` |
| 3 Verifier | `verifier.py` | A SEPARATE, adversarial AI live-fetches each cited source and audits the editor: VERIFIED / NEEDS-HUMAN-REVIEW / REJECT, with reasons and editor-divergence | `verifier.json` |
| 4 Writer | `writer.py` | Drafts the surviving stories into a script skeleton + article draft, DRAFT-tagged, neutral on outcomes, no betting advice, with an empty human-take slot | `drafts.json` |
| 5 Digest | `digest.py` | Builds the human review queue (Markdown + HTML) and an approval template | `review_queue/<date>.md`, `.html`, `approval_template.json` |
| 6 Publish | `publish.py` | Fail-closed, approval-gated auto-push. Publishes ONLY stories a human approved AND the verifier cleared. Push targets are dry-run adapters until an operator wires a real endpoint | `published/`, `publish_report.json` |

`run.py` orchestrates Stages 1-5 (fail-closed) and **never** publishes. Stage 6 is a separate,
deliberate, human step.

## Running it

```sh
# Full offline wiring test - no API key, no network for the AI stages, no spend:
python3 run.py --mode replay --fixture fixtures/sample_feed.xml

# Live daily brief (needs ANTHROPIC_API_KEY):
export ANTHROPIC_API_KEY=sk-ant-...
python3 run.py --mode live
#  -> read out/review_queue/<date>.md
#  -> copy approval_template.json to approval.json, set stories you sign off to "approve",
#     add your take, then:
python3 publish.py
```

## Fail-closed posture (STAGE 0 of the blueprint)

- No `ANTHROPIC_API_KEY` -> the LLM call raises, the run reports failed, nothing publishes.
- Per-run token/USD budget cap (`config.json`) -> a call that would exceed it raises first.
- Any stage error -> `run.py` writes `status: failed` and exits non-zero (CI flags a human).
- A story publishes only if: a human set it to `approve`, the verifier said VERIFIED (or
  NEEDS-HUMAN-REVIEW **with** a human take as an override), and the run is `live` (a replay
  test run can never publish). REJECT is never publishable.
- Push targets ship as dry-run adapters; a real send requires an operator to add the endpoint,
  credential, and send implementation deliberately.

## Verify

`verify_pipeline.py` mirrors the GoCheckMyPet recall verifier's two layers:

```sh
python3 verify_pipeline.py canary    # Layer 1: offline HARD GATE (blocks)
python3 verify_pipeline.py sources   # Layer 2: live feed check (notify-only)
```

Layer 1 proves the pipeline is wired, the hype/dedupe belts work, the offline replay runs
end-to-end to a DRAFT-tagged review queue, and every fail-closed gate holds. Layer 2 checks
the configured RSS feeds still resolve. Wired to `.github/workflows/verify-sports-pipeline.yml`.

## Configuration

- `config.json` - sources and tiers (official league APIs + outlet RSS), cadence, top-N,
  budget cap, per-stage model, publish gates.
- `shill_rules.json` - deterministic hype/promotion tells and source reputation (the living
  tune-list).
- `prompts/` - the editor / verifier / writer system prompts (your editorial judgment, once).

## Cost control

The desk calls are capped by `config.json -> budget` (tokens and USD; hard fail-closed
ceilings). No `temperature`/`top_p`/`top_k` is sent (rejected by the current model family);
register and determinism are steered by the prompts. The lineup runs the pre-revenue agent
economy (family directive): `claude-haiku-4-5` on every desk stage, with the deterministic
gates as the quality floor and a `claude-sonnet-5` rescue lane for the Daily Edition. A
typical full run lands around $0.15-0.30, well under the $1.50 cap.

## The website

The public reader-facing site lives in `site/` and is generated by `site_build.py` into
`site/publish/` (a build artifact, gitignored, reproducible). It has its own editorial
"trusted newsroom" identity: masthead, serif headlines, verdict badges that reuse the
pipeline's vocabulary, a "how we work" trust strip, a Netlify-Forms newsletter signup, and
the no-betting-advice disclaimer baked into every page. Pages: home, latest, archive,
how-we-work (`method.html`), about, standards/corrections, The Bottom Line history,
per-story article pages, an RSS feed at `/feed.xml`, plus 404 and a subscribe thank-you.

```sh
python3 site_build.py            # build site/publish/ from committed content
python3 site_build.py --ingest   # promote approved payloads, then build
```

Content flow: a story is published only after human approval (`publish.py`). `--ingest`
promotes those approved payloads (`out/published/*.json`) into committed content
(`site/content/*.json`), which the build renders. Deploy and cadence steps are in
`LAUNCH_CHECKLIST.md`.

## Never betting advice

GoCheckMySports reports events. It never advises bets. Nothing here is betting or gambling
advice, and that disclaimer is baked into every draft and every published payload.
