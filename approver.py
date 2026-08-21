#!/usr/bin/env python3
"""
approver.py: Stage 4.5, the APPROVER AI (post-draft, the last line of editorial defense).

Role 3 of the three-role pipeline. Not a proofreader: it reads each finished draft AGAINST
its research brief and checks, in order, (1) accuracy & liability - every fact in the draft
must trace to the brief; smuggled facts are a REJECT back to research, the writer never
patches facts - (2) balance - did the brief's bear case survive drafting? - (3) quality.
Every REJECT carries a categorized reason (accuracy | balance | clarity | compliance) so
patterns surface over time in editorial-log.json: three straight accuracy bounces is a
research-process problem, not three individual mistakes.

Kill authority is structural: autopilot publishes only VERIFIED stories this stage
APPROVED. There is no override path in the automated flow (the human editor-in-chief's
manual publish.py path remains the one legitimate override, because that human IS the
desk). Fail-closed: a draft this stage did not judge is treated as REJECT, and a stage
error fails the run.

USAGE
  python3 approver.py
  DESK_LLM_MODE=replay python3 approver.py
"""

import json
import os
import sys

import common
import llm as llmlib

DECISIONS = {"APPROVE", "REJECT"}
CATEGORIES = {"accuracy", "balance", "clarity", "compliance"}
LOG_PATH = os.path.join(common.HERE, "editorial-log.json")


def pair_drafts_with_briefs(drafts, briefs):
    b_by_id = {b["id"]: b for b in briefs.get("briefs", [])}
    pairs = []
    for d in drafts.get("drafts", []):
        pairs.append({
            "id": d["id"],
            "draft": d.get("article_draft", {}),
            "brief": b_by_id.get(d["id"]) or {"note": "no brief exists for this story; "
                                              "every draft fact must then trace to the "
                                              "draft's own cited sources or be rejected"},
        })
    return pairs


def validate(obj, pairs):
    if not isinstance(obj, dict) or not isinstance(obj.get("approvals"), list):
        raise llmlib.LLMError("approver output missing 'approvals' list")
    ids = {p["id"] for p in pairs}
    by_id = {}
    for a in obj["approvals"]:
        if a.get("id") not in ids:
            # Per-item tolerance (2026-07-15): an invented id is ignored with a warning;
            # coverage below fail-closes any draft left unjudged (it becomes a REJECT).
            print(f"::warning::approver: ignored decision for invented id {a.get('id')!r}")
            continue
        if a.get("decision") not in DECISIONS:
            raise llmlib.LLMError(f"approver: invalid decision '{a.get('decision')}' "
                                  f"for id {a.get('id')}")
        if a["decision"] == "REJECT" and a.get("category") not in CATEGORIES:
            a["category"] = "accuracy"  # uncategorized rejection defaults to the strictest bin
        a.setdefault("reasons", [])
        by_id[a["id"]] = a
    # Fail-closed on coverage: an unjudged draft is REJECTED, never silently promoted.
    for pid in ids:
        if pid not in by_id:
            by_id[pid] = {"id": pid, "decision": "REJECT", "category": "accuracy",
                          "reasons": ["approver returned no decision for this draft"]}
    obj["approvals"] = [by_id[p["id"]] for p in pairs]
    return obj


def append_editorial_log(date, mode, approvals, drafts):
    """The fast feedback loop: categorized rejections accumulate in a committed rolling log
    so patterns surface. Live runs only; replay/canary runs never pollute the record."""
    if mode != "live":
        return
    d_by_id = {d["id"]: d for d in drafts.get("drafts", [])}
    entry = {
        "date": date,
        "approved": sum(1 for a in approvals if a["decision"] == "APPROVE"),
        "rejected": [
            {"id": a["id"],
             "headline": (d_by_id.get(a["id"], {}).get("article_draft", {}) or {}).get("title", ""),
             "category": a.get("category", ""),
             "reasons": a.get("reasons", [])}
            for a in approvals if a["decision"] == "REJECT"],
    }
    log = []
    if os.path.exists(LOG_PATH):
        try:
            log = json.load(open(LOG_PATH, encoding="utf-8"))
        except Exception:
            log = []
    log.append(entry)
    json.dump(log[-200:], open(LOG_PATH, "w", encoding="utf-8"), indent=1)


def _repair_rejects(obj, pairs, drafts):
    """Cut the sentences the approver named and publish the rest. No model call.

    THE STORY IS NOT THE SENTENCE (owner directive 2026-08-21). The desk was losing whole
    correct stories to one loose clause, over and over: a Verstappen contract extension
    killed 7 times over a phrasing inversion in a sentence about last season, a Yoshida IL
    placement killed 4 times over one ambiguous clause about what the club had not
    confirmed, a Rodri transfer killed over a currency conversion in a 2019 aside. The news
    in each was right and the desk published nothing, run after run, until the spend
    breaker parked the development for good.

    Asking a model to rewrite (the rescue path below) trades one error surface for another:
    a fresh draft can smuggle a fresh mistake, which is exactly what the kill streaks show.
    Deleting the named sentence cannot invent anything. So this runs FIRST and is purely
    mechanical: the offending text is matched verbatim in the body, cut, and what remains
    is published if it still stands as a story.

    Refuses to repair when the damage is structural rather than incidental: nothing matched
    verbatim, the lead paragraph is the problem (the story's own premise is wrong), or too
    little body survives. Those are the rejections that should stand.
    """
    MIN_WORDS_AFTER = 90
    by_id = {a["id"]: a for a in obj["approvals"]}
    pair_by_id = {p["id"]: p for p in pairs}
    draft_by_id = {d["id"]: d for d in drafts.get("drafts", [])}
    repaired = 0
    for a in [x for x in obj["approvals"] if x.get("decision") == "REJECT"]:
        bad = [str(t).strip() for t in (a.get("offending_text") or []) if str(t).strip()]
        pid = a["id"]
        draft = draft_by_id.get(pid)
        pair = pair_by_id.get(pid)
        if not bad or not draft or not pair:
            continue
        art = draft.get("article_draft") or {}
        body = str(art.get("body") or "")
        if not body:
            continue
        paras = [p for p in body.split("\n") if p.strip()]
        if not paras:
            continue
        lead = paras[0]
        if any(t in lead for t in bad):
            common.gh("notice", f"approver: NOT repairing {pid}; the objection is in the "
                                f"lead, so the story's own premise is what failed")
            continue
        new_body, cut = body, 0
        for t in bad:
            if t in new_body:
                new_body = new_body.replace(t, "")
                cut += 1
        if not cut:
            continue  # the quote was a paraphrase, not the draft's own words
        new_body = "\n".join(p.strip() for p in new_body.split("\n") if p.strip())
        if len(new_body.split()) < MIN_WORDS_AFTER:
            common.gh("notice", f"approver: NOT repairing {pid}; too little of the story "
                                f"survives the cut ({len(new_body.split())} words)")
            continue
        art["body"] = new_body
        draft["article_draft"] = art
        pair["draft"] = art
        by_id[pid].update({"decision": "APPROVE", "repaired": True,
                           "repair_note": f"cut {cut} sentence(s) the approver named"})
        by_id[pid].pop("category", None)
        repaired += 1
        common.gh("notice", f"approver: REPAIRED {pid} by cutting {cut} sentence(s) the "
                            f"approver objected to; the rest of the story publishes "
                            f"('{str(pair.get('draft', {}).get('title'))[:60]}')")
    if repaired:
        common.write_out("drafts.json", drafts)
    return repaired


def _rescue_rejects(client, obj, pairs, drafts):
    """Redraft each REJECTED story once against the approver's stated objection, then
    re-judge. Mutates obj["approvals"] in place. Returns the number of drafts that were
    corrected and subsequently approved."""
    if client.mode == "replay":
        return 0
    by_id = {a["id"]: a for a in obj["approvals"]}
    pair_by_id = {p["id"]: p for p in pairs}
    draft_by_id = {d["id"]: d for d in drafts.get("drafts", [])}
    rejects = [a for a in obj["approvals"] if a.get("decision") == "REJECT"]
    if not rejects:
        return 0
    writer_sys = common.load_prompt("writer.md")
    approver_sys = common.load_prompt("approver.md")
    fixed = 0
    for a in rejects:
        pid = a["id"]
        pair, draft = pair_by_id.get(pid), draft_by_id.get(pid)
        if not pair or not draft:
            continue
        if client.budget.would_starve_approver():
            common.gh("warning", "approver: stopping corrective redrafts to leave budget "
                                 "for judging; remaining rejects stand")
            break
        objection = "; ".join(str(r) for r in (a.get("reasons") or []))[:1200]
        try:
            user = ("Rewrite ONE story. The desk's approver rejected your previous draft "
                    "for a specific, categorized reason. Fix exactly that and change "
                    "nothing else. Every fact must still trace to the brief.\n\n"
                    f"REJECTION [{a.get('category')}]: {objection}\n\n"
                    "Previous draft:\n" + json.dumps(pair["draft"], indent=1) +
                    "\n\nBrief:\n" + json.dumps(pair["brief"], indent=1))
            new_draft = client.call_json("writer", writer_sys, user)
            art = new_draft.get("article_draft") or new_draft
            if not isinstance(art, dict) or not art.get("title"):
                continue
            judged = client.call_json(
                "approver", approver_sys,
                "Judge this corrected draft against its brief. Decision + categorized "
                "reason.\n\nDrafts with briefs:\n" +
                json.dumps([{"id": pid, "draft": art, "brief": pair["brief"]}], indent=1))
            verdict = next((x for x in (judged.get("approvals") or [])
                            if x.get("id") == pid), None)
        except Exception as e:
            common.gh("warning", f"approver: corrective redraft failed for {pid} ({e}); "
                                 f"the original rejection stands")
            continue
        if verdict and verdict.get("decision") == "APPROVE":
            draft["article_draft"] = art
            pair["draft"] = art
            by_id[pid].update(verdict)
            by_id[pid]["corrected"] = True
            fixed += 1
        # a redraft that still fails keeps its ORIGINAL rejection: the record should show
        # what the desk actually objected to, not the second version of the argument
    if fixed:
        common.write_out("drafts.json", drafts)
    return fixed


def run(client=None):
    cfg = common.load_config()
    drafts = common.read_out("drafts.json")
    try:
        briefs = common.read_out("briefs.json")
    except Exception:
        briefs = {"briefs": []}
    client = client or llmlib.Client(cfg)
    pairs = pair_drafts_with_briefs(drafts, briefs)

    if not pairs:
        obj = {"approvals": [], "_meta": {"stage": "4.5-approver", "mode": client.mode,
               "judged": 0, "note": "no drafts to judge",
               "budget": client.budget.summary()}}
        common.write_out("approver.json", obj)
        print("approver: 0 drafts to judge -> out/approver.json")
        return obj

    system = common.load_prompt("approver.md")
    # Same ceiling discipline as researcher/writer: the judgment model's thinking bills
    # against max_tokens, so judge 3 pairs per call; replay stays single (one fixture).
    chunk_size = len(pairs) if client.mode == "replay" else 3
    approvals = []
    for i in range(0, len(pairs), chunk_size):
        chunk = pairs[i:i + chunk_size]
        user = ("Judge each draft against its research brief. Decision + categorized "
                "reason each.\n\nDrafts with briefs:\n" + json.dumps(chunk, indent=1))
        part = client.call_json("approver", system, user,
                                validate=lambda o: validate(o, chunk))
        approvals.extend(part["approvals"])
    obj = {"approvals": approvals}

    # ONE CORRECTIVE REDRAFT, THEN THE KILL STANDS (owner directive 2026-08-18, quality
    # over quantity). A REJECT is not a verdict that the STORY is bad; it is a finding
    # that this DRAFT misstated something, and the finding is precise: "the draft says
    # mid-April, the brief says April". Today that finding is thrown away. The story dies
    # for the run and the next run drafts it from scratch, which is how one ETF story
    # died eleven times on eleven DIFFERENT objections, each draft fixing nothing because
    # each draft never saw the last one's fault.
    #
    # So the writer gets the objection and one attempt to fix it, and the approver judges
    # the result fresh. This raises quality rather than volume: what publishes is a draft
    # whose known defect was corrected, not a draft that skipped a gate. Exactly one
    # attempt, deliberately. A second would be grinding the gate rather than fixing the
    # copy, and the cross-run spend breaker already handles a development that cannot be
    # written correctly at all.
    # CUT THE BAD SENTENCE BEFORE PAYING TO REWRITE THE STORY (2026-08-21). Deterministic
    # repair runs first: it cannot invent anything, and it saves the common case where one
    # incidental clause failed an otherwise-correct story. Whatever it cannot repair still
    # gets the one corrective redraft below.
    repaired = _repair_rejects(obj, pairs, drafts)
    if repaired:
        print(f"approver: {repaired} draft(s) repaired by cutting the objected sentences")
    rescued = _rescue_rejects(client, obj, pairs, drafts)
    if rescued:
        print(f"approver: {rescued} draft(s) corrected on the approver's own objection "
              f"and re-judged")

    counts = {"APPROVE": 0, "REJECT": 0}
    for a in obj["approvals"]:
        counts[a["decision"]] += 1
    date = ""
    try:
        date = common.read_out("items.json")["_meta"]["generated"][:10]
    except Exception:
        pass
    append_editorial_log(date, client.mode, obj["approvals"], drafts)
    obj["_meta"] = {"stage": "4.5-approver", "mode": client.mode,
                    "judged": len(pairs), "counts": counts,
                    "budget": client.budget.summary()}
    path = common.write_out("approver.json", obj)
    print(f"approver: {counts} across {len(pairs)} drafts -> {path} [mode={client.mode}]")
    return obj


def main():
    try:
        run()
    except llmlib.LLMError as e:
        common.gh("error", f"approver: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
