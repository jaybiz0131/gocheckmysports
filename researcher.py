#!/usr/bin/env python3
"""
researcher.py: Stage 3.5, the RESEARCHER AI (builds the brief the writer writes from).

Role 1 of the three-role editorial pipeline (owner's framework, 2026-07-14): research fails
on accuracy, writing fails on clarity, approval fails on liability - so each gets a dedicated
stage with a handoff standard. The researcher's deliverable is a structured BRIEF, not prose:
every data point with its source, a confidence label per claim, the bear case pulled
deliberately, and the open questions flagged. The handoff standard: the writer must be able
to produce the article without doing any new research - if a number is not in the brief, it
does not exist.

Input: the stories that survived verification (VERIFIED + NEEDS-HUMAN-REVIEW, the same set
the writer drafts) + the full source-page extractions the verifier already fetched
(out/source_texts.json - one HTTP pass serves both stages) + the aggregate cluster
(snippet, corroboration, timestamps).

Fail-open per story: if the model returns no brief for a story (or its sources were
paywalled/unreachable), a deterministic thin brief is built from the cluster snippet and
flagged thin=true, so a fetch failure can never kill the pipeline - it just yields an
honest, shorter story downstream. Fail-closed at the stage level: model/parse errors raise.

USAGE
  python3 researcher.py
  DESK_LLM_MODE=replay python3 researcher.py
"""

import json
import sys

import boundary
import common
import llm as llmlib

BRIEFABLE = {"VERIFIED", "NEEDS-HUMAN-REVIEW"}


def select(editor, verifier):
    by_verdict = {v["id"]: v for v in verifier["verdicts"]}
    clusters = {}
    try:
        for c in common.read_out("items.json").get("clusters", []):
            clusters[c.get("id")] = c
    except Exception:
        pass
    try:
        source_texts = common.read_out("source_texts.json")
    except Exception:
        source_texts = {}
    out = []
    for s in editor["ranked"]:
        v = by_verdict.get(s["id"])
        if not v or v["verdict"] not in BRIEFABLE:
            continue
        c = clusters.get(s["id"]) or {}
        texts = source_texts.get(s["id"], [])
        out.append({
            "id": s["id"], "headline": s["headline"],
            "why_it_matters": s["why_it_matters"],
            "category": s.get("category", "other"),
            "verdict": v["verdict"],
            "source_urls": s.get("source_urls", []),
            "first_seen": c.get("timestamp", ""),
            "snippet": (c.get("snippet") or "")[:600],
            "reported_by": [c.get("source", "")] + [
                x.get("name", "") for x in (c.get("corroboration") or [])[:6]],
            "source_texts": [t for t in texts if t.get("source_text")],
        })
    return out


def thin_brief(story):
    """Deterministic fallback when the model skipped a story or nothing fetched: the brief
    is the snippet, honestly labeled, so the writer writes short rather than inventing."""
    return {
        "id": story["id"],
        "core_claim": story["headline"],
        "angle": story["why_it_matters"],
        "data_points": [{
            "claim": story["snippet"] or story["headline"],
            "source_url": (story["source_urls"] or [""])[0],
            "source_name": (story["reported_by"] or [""])[0],
            "timestamp": story["first_seen"],
            "confidence": "reported",
        }],
        "bear_case": [],
        "open_questions": ["source pages could not be fetched; only the feed summary is available"],
        "thin": True,
    }


def validate(obj, stories):
    if not isinstance(obj, dict) or not isinstance(obj.get("briefs"), list):
        raise llmlib.LLMError("researcher output missing 'briefs' list")
    ids = {s["id"] for s in stories}
    by_id = {}
    for b in obj["briefs"]:
        if b.get("id") not in ids:
            raise llmlib.LLMError(f"researcher briefed an unexpected id: {b.get('id')}")
        b.setdefault("data_points", [])
        b.setdefault("bear_case", [])
        b.setdefault("open_questions", [])
        b.setdefault("thin", False)
        by_id[b["id"]] = b
    # Fail-open per story: an unbriefed story gets the deterministic thin brief, never dropped.
    for s in stories:
        if s["id"] not in by_id:
            by_id[s["id"]] = thin_brief(s)
        # source_chars is DETERMINISTIC (measured, not model-claimed): the depth gate keys
        # off how much source material actually existed for this story.
        by_id[s["id"]]["source_chars"] = sum(
            len(t.get("source_text", "")) for t in s["source_texts"])
        _stamp_boundary(by_id[s["id"]], s)
    obj["briefs"] = [by_id[s["id"]] for s in stories]
    return obj


def _stamp_boundary(brief, story):
    """Classify boundary-class stories and check the block against the fetched advisory.

    DETERMINISTIC, and deliberately not a raise. The researcher's discipline is fail-open per
    story: a brief that cannot carry a confirmed boundary is still a brief, and the desk still
    has a story it may run without the who-is-affected claim, or hold. What must never happen
    is the boundary reaching a reader unchecked, so the finding is recorded on the brief and
    the fail-closed decision is taken later, by the stage that can see the finished draft.

    Both directions are stamped. A story that is NOT boundary-class carries the flag as False
    rather than as an absent key, because downstream a missing key and a negative answer look
    identical and only one of them means the check ran."""
    brief["boundary_required"] = boundary.story_is_boundary_class(story, brief)
    b = brief.get("boundary")
    if not brief["boundary_required"]:
        # A boundary block on a story that is not boundary-class is not an error; the
        # classifier is deliberately narrow and the researcher may see something it does not.
        # Confirm it anyway if it is there, and let it stand unconfirmed if not.
        if not b:
            brief.pop("boundary", None)
            brief["boundary_ok"] = None
            return
    if not b:
        brief["boundary_ok"] = False
        brief["boundary_reasons"] = ["this story turns on a version, date range or threshold "
                                     "but the brief carries no boundary block"]
        common.gh("warning", f"researcher: {brief['id']} is boundary-class with no boundary "
                             f"block; the who-is-affected claim cannot be published")
        return
    ok, reasons = boundary.check_against_sources(b, story.get("source_texts") or [])
    brief["boundary_ok"] = ok
    brief["boundary_reasons"] = reasons
    if not ok:
        common.gh("warning", f"researcher: {brief['id']} boundary unconfirmed: "
                             f"{'; '.join(reasons)}")


def run(client=None):
    cfg = common.load_config()
    editor = common.read_out("editor.json")
    verifier = common.read_out("verifier.json")
    stories = select(editor, verifier)
    client = client or llmlib.Client(cfg)

    if not stories:
        obj = {"briefs": [], "_meta": {"stage": "3.5-researcher", "mode": client.mode,
               "briefed": 0, "note": "no VERIFIED or REVIEW stories to brief",
               "budget": client.budget.summary()}}
        common.write_out("briefs.json", obj)
        print("researcher: 0 briefable stories -> out/briefs.json")
        return obj

    # WIDEN THE BRIEF ON A KILL STREAK (owner fix list 2026-08-18, item 2): the
    # dominant kill reason across all three desks is a draft carrying facts the brief
    # does not, and it repeats because attempt N+1 gets the same thin brief attempt N
    # died with. A development killed 3+ times gets a WIDE brief: every extractable
    # data point from the same sources, so the writer has no gap to fill from memory.
    # Fail-soft: no history available means no change.
    try:
        import kill_streak as _ks
        for s in stories:
            hist = _ks.kill_history(str(s.get("headline") or ""))
            if len(hist) >= 3:
                s["_widen_brief"] = len(hist)
                common.gh("notice", f"researcher: widening the brief for "
                          f"{str(s.get('headline'))[:70]!r} (killed {len(hist)}x; "
                          f"a thin brief invites the writer to fill gaps from memory)")
    except Exception as e:
        common.gh("warning", f"researcher: kill-history widening unavailable ({e})")

    system = common.load_prompt("researcher.md")
    # Exhaustive briefs are LONG, and the judgment model's thinking bills against the same
    # output ceiling: an all-stories single call truncates mid-JSON at 6+ stories (it did,
    # in CI, 2026-07-14). Batch 2 stories per call; replay stays a single call (one fixture).
    chunk_size = len(stories) if client.mode == "replay" else 2
    briefs = []
    for i in range(0, len(stories), chunk_size):
        chunk = stories[i:i + chunk_size]
        widen = [s for s in chunk if s.get("_widen_brief")]
        user = ("Build a research brief for each story from its fetched source texts.\n\n"
                + "".join(
                    f"WIDE BRIEF REQUIRED for story id {s.get('id')}: earlier drafts of "
                    f"this development were rejected {s['_widen_brief']} times for "
                    f"carrying facts the brief did not. Extract EVERY concrete data "
                    f"point the source texts support (numbers, names, dates, titles, "
                    f"direct quotes), not just the leading ones; a wide brief leaves "
                    f"the writer nothing to fill in from memory.\n\n"
                    for s in widen)
                + "Stories:\n" + json.dumps(chunk, indent=1))
        part = client.call_json("researcher", system, user,
                                validate=lambda o: validate(o, chunk))
        briefs.extend(part["briefs"])
    obj = {"briefs": briefs}

    thin = sum(1 for b in obj["briefs"] if b.get("thin"))
    obj["_meta"] = {"stage": "3.5-researcher", "mode": client.mode,
                    "briefed": len(obj["briefs"]), "thin": thin,
                    "budget": client.budget.summary()}
    path = common.write_out("briefs.json", obj)
    print(f"researcher: briefed {len(obj['briefs'])} stories ({thin} thin) -> {path} "
          f"[mode={client.mode}]")
    return obj


def main():
    try:
        run()
    except llmlib.LLMError as e:
        common.gh("error", f"researcher: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
