#!/usr/bin/env python3
"""
rewrite_thin.py: ONE-SHOT backfill for the thin launch-era stories (2026-07-14).

The early pipeline handed the writer only an RSS snippet, so live stories ran 30-80 word
bodies. This script reruns each thin published story through the NEW three-role chain:
re-fetch its recorded sources -> researcher brief -> brief-bound writer -> approver. Only
APPROVED rewrites that are actually longer than the original are applied. Title, slug,
date, id, verdict, rank, sources, and the (empty) human_take are preserved: the URL and
the editorial record do not change, only the story's depth.

Report-only unless --apply is passed. Run locally, review, then rebuild + commit.

USAGE
  python3 rewrite_thin.py            # dry-run: show what would change
  python3 rewrite_thin.py --apply    # write the approved rewrites into site/content/
"""

import glob
import json
import os
import sys

import common
import llm as llmlib
from site_build import destyle

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "site", "content")
THIN_WORDS = 150


def body_words(body):
    if isinstance(body, list):
        body = " ".join(str(p) for p in body)
    return len(str(body).split())


def load_thin():
    out = []
    for p in sorted(glob.glob(os.path.join(CONTENT, "*.json"))):
        if os.path.basename(p).startswith("example"):
            continue
        d = json.load(open(p, encoding="utf-8"))
        if body_words(d.get("body", "")) < THIN_WORDS:
            out.append((p, d))
    return out


def fetch_sources(story):
    texts = []
    for s in story.get("sources", [])[:3]:
        url = s.get("url") if isinstance(s, dict) else s
        if not url:
            continue
        code, page = common.fetch_page(url)
        text = common.extract_article_text(page) if code == 200 else ""
        texts.append({"url": url, "http_status": code, "source_text": text})
    return texts


def rewrite_one(client, story, texts):
    """researcher -> writer -> approver for one story. Returns (article_draft, brief,
    approval)."""
    sid = story.get("id", "c000")
    research_input = [{
        "id": sid, "headline": story.get("title", ""),
        "why_it_matters": story.get("bottom_line", "") or story.get("dek", ""),
        "category": story.get("category", "news"), "verdict": story.get("verdict", ""),
        "source_urls": [t["url"] for t in texts],
        "first_seen": story.get("published_utc", ""),
        "snippet": story.get("dek", ""),
        "reported_by": [],
        "source_texts": [t for t in texts if t["source_text"]],
    }]
    briefs = client.call_json("researcher", common.load_prompt("researcher.md"),
                              "Build a research brief for each story from its fetched "
                              "source texts.\n\nStories:\n" + json.dumps(research_input, indent=1))
    brief = next((b for b in briefs.get("briefs", []) if b.get("id") == sid), None)
    if not brief:
        return None, None, None
    brief["source_chars"] = sum(len(t["source_text"]) for t in texts)

    wstories = [{"id": sid, "headline": story.get("title", ""),
                 "why_it_matters": story.get("dek", ""),
                 "category": story.get("category", "news"),
                 "verdict": story.get("verdict", ""),
                 "source_urls": [t["url"] for t in texts], "brief": brief}]
    drafts = client.call_json("writer", common.load_prompt("writer.md"),
                              "Draft these verified stories. Two formats each, DRAFT-tagged, "
                              "human_take left empty.\n\nStories:\n" + json.dumps(wstories, indent=2))
    draft = next((d for d in drafts.get("drafts", []) if d.get("id") == sid), None)
    if not draft:
        return None, brief, None
    art = draft.get("article_draft", {})

    pairs = [{"id": sid, "draft": art, "brief": brief}]
    approvals = client.call_json("approver", common.load_prompt("approver.md"),
                                 "Judge each draft against its research brief. Decision + "
                                 "categorized reason each.\n\nDrafts with briefs:\n"
                                 + json.dumps(pairs, indent=1))
    appr = next((a for a in approvals.get("approvals", []) if a.get("id") == sid), None)
    return art, brief, appr


def apply_rewrite(path, story, art):
    paras = [destyle(p.strip()) for p in str(art.get("body", "")).split("\n") if p.strip()]
    story["body"] = paras
    story["bottom_line"] = destyle(art.get("bottom_line", story.get("bottom_line", "")))
    if art.get("title"):
        # keep the ORIGINAL title (slug/URL stability); the rewrite only deepens the body
        pass
    story["human_take"] = ""
    story["rewritten"] = "2026-07-14 depth backfill (three-role pipeline)"
    json.dump(story, open(path, "w", encoding="utf-8"), indent=1)


def main():
    apply = "--apply" in sys.argv
    thin = load_thin()
    print(f"rewrite_thin: {len(thin)} published stories under {THIN_WORDS} words\n")
    cfg = common.load_config()
    # One-shot local backfill over ~20 stories x 3 model calls each: the daily run's
    # per-run cap is far too small for it (the first dry run hit 220K tokens at story 13).
    # Still hard-capped, just sized for the job.
    client = llmlib.Client(cfg, budget=llmlib.Budget(max_tokens=1_500_000, max_usd=20.0))
    changed = 0
    for path, story in thin:
        name = os.path.basename(path)
        old_words = body_words(story.get("body", ""))
        texts = fetch_sources(story)
        fetched = sum(1 for t in texts if t["source_text"])
        if not fetched:
            print(f"SKIP {name}: no source page fetchable anymore ({len(texts)} tried) "
                  f"-> keeping the current {old_words}-word body")
            continue
        try:
            art, brief, appr = rewrite_one(client, story, texts)
        except llmlib.BudgetError as e:
            print(f"STOP: {e}")
            break
        except llmlib.LLMError as e:
            print(f"SKIP {name}: model call failed ({e})")
            continue
        if not art or not appr:
            print(f"SKIP {name}: pipeline returned no draft/approval")
            continue
        new_words = body_words(art.get("body", ""))
        if appr.get("decision") != "APPROVE":
            print(f"HELD {name}: approver REJECTED ({appr.get('category')}) "
                  f"{'; '.join(appr.get('reasons', [])[:2])}")
            continue
        if new_words <= old_words:
            print(f"SKIP {name}: rewrite not longer ({new_words} vs {old_words} words)")
            continue
        print(f"{'APPLIED' if apply else 'WOULD APPLY'} {name}: {old_words} -> {new_words} "
              f"words (brief: {len(brief.get('data_points', []))} data points, "
              f"{len(brief.get('bear_case', []))} bear-case items; approver: APPROVE)")
        if apply:
            apply_rewrite(path, story, art)
            changed += 1
    print(f"\nbudget: {client.budget.summary()}")
    if apply and changed:
        print(f"rewrite_thin: {changed} stories rewritten; now run 'python3 site_build.py' "
              f"and commit site/ + site/content/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
