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
