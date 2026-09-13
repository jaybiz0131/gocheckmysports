# gocheckmysports

Source for the daily sports news desk at
[gocheckmysports.com](https://gocheckmysports.com). Python 3, standard library only, no
third-party runtime dependencies.

How the desk works editorially is documented on the site itself, at
`/method.html` and `/standards.html`. This file is setup and operation.

Contact: desk@gocheckmysports.com

## Requirements

- Python 3.11 or newer. No packages to install.
- `ANTHROPIC_API_KEY` in the environment for a live run. Not needed for a replay run.
- Node and Google Chrome only if you want screenshots (`gcm-tools/fullpage-shot.mjs`).

## Running it

```sh
# Offline wiring test. No API key, no network, no spend.
python3 run.py --mode replay --fixture fixtures/sample_feed.xml

# Live run.
export ANTHROPIC_API_KEY=sk-ant-...
python3 run.py --mode live

# Build the static site into site/publish/
python3 site_build.py

# Ingest finished output into site/content/ and rebuild
python3 site_build.py --ingest
```

`run.py --mode live` writes its output under `out/`, including a queue file at
`out/review_queue/<date>.md`. `publish.py` promotes approved output; it reads
`approval.json`, which you create by copying `approval_template.json` and marking
entries.

## Stages

`run.py` drives these in order. Each writes a JSON artifact under `out/` and the next
stage reads it, so any stage can be inspected or re-run on its own.

| # | Stage | File | Output |
|---|---|---|---|
| 1 | Aggregate | `aggregate.py` | `items.json` |
| 2 | Editor | `editor.py` | `editor.json` |
| 3 | Verifier | `verifier.py` | `verifier.json` |
| 4 | Researcher | `researcher.py` | `research.json` |
| 5 | Writer | `writer.py` | `drafts.json` |
| 6 | Approver | `approver.py` | `approved.json` |
| 7 | Digest | `digest.py` | the queue file |
| 8 | Autopilot | `autopilot.py` | `approval.json` |
| 9 | Publish | `publish.py` | `site/content/*.json` |
| 10 | Wrap | `wrap.py` | the day's edition |

Data collectors run alongside the stages and write into `site/data/`:

| Script | Writes | Notes |
|---|---|---|
| `scores_pulse.py` | `scores.json` | league scoreboards |
| `where_to_watch.py` | `where-to-watch.json` | NFL windows and carriers; also called by `site_build.py` |
| `source_health.py` | `source_health.json` | advisory, always exits 0 |

## Configuration

Everything tunable is in `config.json`: `sources`, `budget`, `cadence`, `publish`,
`dedupe`, `edition`, `narratives`, `event_calendar`, `top_n`, `lookback_hours`.

A per-run budget cap lives under `budget`. A call that would exceed it raises before
it is made rather than after.

## Verifying a change

```sh
# Hard gate. Must print PASS before anything is pushed.
python3 verify_pipeline.py canary

# The site must build clean, exit 0, no traceback.
python3 site_build.py

# Advisory checks. These warn; they never fail a run.
python3 source_health.py --check
python3 twin_audit.py --quiet
```

`verify_pipeline.py canary` runs an offline replay end to end and asserts that every
fail-closed gate holds. It is fast and it is the gate: never push on a red canary.

Its deliberate negative tests print inside `::stop-commands::` so they do not post as
annotations on a green run.

## Fail-closed posture

- A stage that cannot complete stops the run rather than passing partial output on.
- A source that cannot be fetched is dropped, not guessed at.
- A gate that fires withholds the affected item, not the whole run.
- A data surface with no reading renders nothing rather than a zero.

## Scheduled workflows

| Workflow | What it runs |
|---|---|
| `sports-news-brief.yml` | the daily run and the edition slots |
| `watcher.yml` | breaking-news threshold checks |
| `sports-aging.yml` | archive and aging passes |
| `verify-sports-pipeline.yml` | the canary on a schedule |
| `janitor.yml` | housekeeping |
| `publicist.yml` | disabled; schedule removed, code kept |

## The site

`site_build.py` renders `site/publish/` from `site/content/` plus `site/data/`.
`site/publish/` is generated and is not committed. Netlify builds from `main`.

House rules the build enforces: no em dashes in desk copy, and a source's own words
inside a quotation are never repunctuated.
