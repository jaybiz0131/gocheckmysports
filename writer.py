#!/usr/bin/env python3
"""
writer.py: Stage 4, the writer AI (drafts).

Drafts the stories that SURVIVED verification (VERIFIED, plus NEEDS-HUMAN-REVIEW which the
human may promote) into a script skeleton and an article draft, in the GoCheckMySports voice:
factual, sourced, neutral on betting, with a not-betting-advice disclaimer and an explicit,
empty human-take slot. REJECT stories are never drafted. Everything is tagged DRAFT. Fail-closed.

USAGE
  python3 writer.py
  DESK_LLM_MODE=replay python3 writer.py
"""

import json
import sys

import common
import llm as llmlib

DRAFTABLE = {"VERIFIED", "NEEDS-HUMAN-REVIEW"}
NFA = "GoCheckMySports reports events. It never advises bets. Nothing here is betting or gambling advice."


def select(editor, verifier):
    by_verdict = {v["id"]: v for v in verifier["verdicts"]}
    # The researcher's brief is the writer's entire universe of facts (three-role pipeline,
    # 2026-07-14): built from the full source-page texts, with per-claim confidence labels
    # and the bear case pulled deliberately. The old snippet-only source_material was why
    # early articles ran 30-80 words: the writer was honest but starving.
    briefs = {}
    try:
        for b in common.read_out("briefs.json").get("briefs", []):
            briefs[b.get("id")] = b
    except Exception:
        pass
    clusters = {}
    try:
        for c in common.read_out("items.json").get("clusters", []):
            clusters[c.get("id")] = c
    except Exception:
        pass
    out = []
    for s in editor["ranked"]:
        v = by_verdict.get(s["id"])
        if not v or v["verdict"] not in DRAFTABLE:
            continue
        story = {**s, "verdict": v["verdict"]}
        b = briefs.get(s["id"])
        if b:
            story["brief"] = b
        else:
            # No brief (researcher stage skipped/failed for this story): fall back to the
            # snippet so the writer still writes an honest short story, never nothing.
            c = clusters.get(s["id"]) or {}
            story["source_material"] = {
                "summary": (c.get("snippet") or "")[:600],
                "first_seen": c.get("timestamp", ""),
                "reported_by": [c.get("source", "")] + [
                    x.get("name", "") for x in (c.get("corroboration") or [])[:6]],
            }
        out.append(story)
    return out


def validate(obj, stories):
    if not isinstance(obj, dict) or not isinstance(obj.get("drafts"), list):
        raise llmlib.LLMError("writer output missing 'drafts' list")
    ids = {s["id"] for s in stories}
    by_id = {s["id"]: s for s in stories}
    # Per-item tolerance (2026-07-15): small models occasionally invent an id ("c016-alt").
    # An alien id alongside valid drafts is dropped, never published, never fatal; the whole
    # run only fails (climbing the contract ladder) when NOTHING valid came back.
    alien = [d.get("id") for d in obj["drafts"] if d.get("id") not in ids]
    if alien:
        print(f"::warning::writer: dropped draft(s) with invented id(s): {alien} "
              f"(ids come only from the input)")
        obj["drafts"] = [d for d in obj["drafts"] if d.get("id") in ids]
    if stories and not obj["drafts"]:
        raise llmlib.LLMError(f"writer returned no drafts with valid ids "
                              f"(invented: {alien})" if alien else
                              "writer returned an empty drafts list for non-empty input")
    for d in obj["drafts"]:
        art = d.get("article_draft") or {}
        skel = d.get("script_skeleton") or {}
        if not art or not skel:
            raise llmlib.LLMError(f"writer draft {d.get('id')} missing article_draft or script_skeleton")
        # Enforce the guardrails regardless of what the model returned.
        # If the model skipped The Bottom Line closer, fall back to the editor's
        # why_it_matters line rather than publishing without one.
        if not (art.get("bottom_line") or "").strip():
            art["bottom_line"] = by_id[d["id"]].get("why_it_matters", "")
        art["status"] = "DRAFT"
        art["not_financial_advice"] = NFA
        art.setdefault("human_take", "")
        art["human_take"] = ""  # never let the model fabricate the take
        skel.setdefault("human_take", "")
        skel["human_take"] = ""
        d["article_draft"], d["script_skeleton"] = art, skel
    return obj


def run(client=None):
    cfg = common.load_config()
    editor = common.read_out("editor.json")
    verifier = common.read_out("verifier.json")
    stories = select(editor, verifier)
    client = client or llmlib.Client(cfg)

    if not stories:
        # Nothing survived verification. That is a valid, fail-closed outcome: write an empty
        # draft set (the digest will show an empty queue) without spending an API call.
        obj = {"drafts": [], "_meta": {"stage": "4-writer", "mode": client.mode,
               "draftable": 0, "note": "no VERIFIED or REVIEW stories to draft",
               "budget": client.budget.summary()}}
        common.write_out("drafts.json", obj)
        print("writer: 0 draftable stories (nothing survived verification) -> out/drafts.json")
        return obj

    system = common.load_prompt("writer.md")
    # Full-length stories run 350-650 words each: batching 3 stories per call keeps every
    # response comfortably inside max_tokens (a single 8-story call would truncate mid-JSON
    # and fail the stage). Replay mode stays a single call (one fixture response).
    chunk_size = len(stories) if client.mode == "replay" else 3
    drafts = []
    for i in range(0, len(stories), chunk_size):
        chunk = stories[i:i + chunk_size]
        user = ("Draft these verified stories. Two formats each, DRAFT-tagged, human_take "
                "left empty.\n\n"
                + "Stories:\n" + json.dumps(chunk, indent=2))
        part = client.call_json("writer", system, user,
                                validate=lambda o: validate(o, chunk))
        drafts.extend(part["drafts"])
    obj = {"drafts": drafts}

    obj["_meta"] = {"stage": "4-writer", "mode": client.mode,
                    "draftable": len(stories), "drafted": len(obj["drafts"]),
                    "budget": client.budget.summary()}
    path = common.write_out("drafts.json", obj)
    print(f"writer: drafted {len(obj['drafts'])}/{len(stories)} -> {path} [mode={client.mode}]")
    return obj


def main():
    try:
        run()
    except llmlib.LLMError as e:
        common.gh("error", f"writer: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
