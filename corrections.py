#!/usr/bin/env python3
"""
corrections.py: CLOSES THE AGING LOOP (charter, 2026-07-15). Stale or invalidated
articles do not just get flagged: they queue a correction run through the same pipeline.

Reads out/aging_report.json (written by aging.py) and, for every premise-flagged story,
re-runs the three-role chain via rewrite_thin.rewrite_one: re-fetch the story's sources
as they read NOW -> researcher brief -> brief-bound writer -> approver. Only APPROVED
rewrites apply; the update preserves slug/date/id (the URL never changes), appends a
visible correction note field, and the workflow commit deploys it. Dead-link-only flags
are left to the human report (a dead source is a citation problem, not a premise change).

Fail-closed per story: no approval, no change. Runs in crypto-aging.yml after aging.py.

USAGE  python3 corrections.py            (needs ANTHROPIC_API_KEY)
"""

import datetime
import json
import os
import sys

import common
import llm as llmlib
from rewrite_thin import fetch_sources, rewrite_one, body_words
from site_build import destyle

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "site", "content")


def main():
    if os.path.exists(os.path.join(HERE, "PAUSE")):
        print("corrections: PAUSE file present -> skipping")
        return 0
    try:
        report = common.read_out("aging_report.json")
    except Exception:
        print("corrections: no aging report this run; nothing to correct.")
        return 0
    flags = [f for f in report.get("flags", []) if f.get("file", "").endswith(".json")]
    if not flags:
        print("corrections: aging review flagged no premises; nothing to correct.")
        return 0

    cfg = common.load_config()
    client = llmlib.Client(cfg, budget=llmlib.Budget(max_tokens=400_000, max_usd=4.0))
    fixed = held = 0
    for f in flags:
        path = os.path.join(CONTENT, f["file"])
        if not os.path.exists(path):
            continue
        story = json.load(open(path, encoding="utf-8"))
        texts = fetch_sources(story)
        if not any(t["source_text"] for t in texts):
            print(f"HELD {f['file']}: sources no longer fetchable; flag stays human-only")
            held += 1
            continue
        try:
            art, brief, appr = rewrite_one(client, story, texts)
        except llmlib.BudgetError as e:
            print(f"STOP: {e}")
            break
        except llmlib.LLMError as e:
            print(f"HELD {f['file']}: correction run failed ({e})")
            held += 1
            continue
        if not art or not appr or appr.get("decision") != "APPROVE":
            why = (appr or {}).get("category", "no approval")
            print(f"HELD {f['file']}: approver did not sign the correction ({why})")
            held += 1
            continue
        paras = [destyle(p.strip()) for p in str(art.get("body", "")).split("\n") if p.strip()]
        story["body"] = paras
        story["bottom_line"] = destyle(art.get("bottom_line", story.get("bottom_line", "")))
        story["human_take"] = ""
        story["corrected"] = (f"{datetime.date.today().isoformat()}: updated after the "
                              f"desk's aging review ({destyle(f.get('reason', ''))[:160]})")
        json.dump(story, open(path, "w", encoding="utf-8"), indent=1)
        print(f"CORRECTED {f['file']}: {body_words(story['body'])} words "
              f"(reason: {f.get('reason','')[:80]})")
        fixed += 1
    print(f"corrections: {fixed} corrected, {held} held for human judgment "
          f"[budget {client.budget.summary()}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
