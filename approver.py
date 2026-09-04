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

import datetime
import json
import os
import re
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


_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"))}
for _full, _n in list(_MONTHS.items()):
    _MONTHS[_full[:3]] = _n
_MONTHS["Sept"] = 9
_DATE_RE = re.compile(
    r"\b(" + "|".join(_WEEKDAYS) + r"),?\s+"
    r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+"
    r"(\d{1,2})(?:,?\s+(\d{4}))?\b")


def _weekday_date_conflicts(draft, default_year):
    """DETERMINISTIC weekday-vs-date lint. The 2026-08-31 queue approved a draft dating a
    flood 'Saturday, August 31, 2026'; August 31 was a Monday, and no model gate noticed
    because both halves read as fluent English. A named weekday beside a calendar date is
    checkable arithmetic, so it is checked here, not judged."""
    text = " ".join(str(draft.get(f) or "") for f in ("title", "body", "bottom_line"))
    out = []
    for m in _DATE_RE.finditer(text):
        wd, mon, day, year = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        try:
            d = datetime.date(int(year) if year else default_year,
                              _MONTHS[mon.rstrip(".")], day)
        except (ValueError, KeyError):
            continue
        actual = d.strftime("%A")
        if actual != wd:
            out.append(f"the draft dates {mon} {day}, {d.year} as a {wd}; "
                       f"{mon} {day}, {d.year} is a {actual}")
    return out


def _lint_weekday_dates(obj, pairs):
    """Flip any draft carrying an impossible weekday+date combination to REJECT (accuracy)
    with the precise finding, BEFORE the repair/rescue passes run, so the existing
    machinery gets its one shot at cutting or correcting the sentence."""
    default_year = datetime.date.today().year
    drafts_by_id = {p["id"]: p["draft"] for p in pairs}
    flipped = 0
    for a in obj["approvals"]:
        conflicts = _weekday_date_conflicts(drafts_by_id.get(a["id"]) or {}, default_year)
        if not conflicts:
            continue
        a.setdefault("reasons", []).extend(conflicts)
        if a["decision"] == "APPROVE":
            a["decision"] = "REJECT"
            a["category"] = "accuracy"
            flipped += 1
    return flipped


# P6, LINT 1: A NUMBER THE BRIEF DOES NOT CARRY IS SMUGGLED. The 2026-09-02 audit found a
# story about SEC press release 2026-81 that cited 2026-83 throughout. Both read as fluent
# English and both are plausible identifiers, so no model gate can catch it by reading; the
# only thing that can is asking whether the identifier appears in the sourced material at
# all. This is the cheapest possible accuracy check and it is exact, not statistical.
#
# Deliberately narrow. It matches SHAPED identifiers only, the kind that name a specific
# document, and never bare numbers: a draft is full of legitimate arithmetic (scores, dollar
# amounts, ages, yardage) that the brief has no reason to restate.
_IDENT_RES = [
    re.compile(r"\b(20\d\d-\d{1,4})\b"),                     # SEC/agency release: 2026-81
    re.compile(r"\b([Nn]o\.\s?\d{1,2}-\d{2,5})\b"),           # docket: No. 23-1234
    re.compile(r"\b(\d{1,2}:\d{2}-[a-z]{2}-\d{3,6})\b"),       # case: 1:24-cv-01234
    re.compile(r"\b([A-Z]{2,4}-\d{2,6})\b"),                   # agency file: HHS-1234
]


def _brief_haystack(brief):
    """Everything the brief actually carries, flattened. An identifier is 'in the brief' if
    it appears anywhere the desk sourced, including quoted source text."""
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(brief)
    return " ".join(out)


def _smuggled_identifiers(draft, brief):
    """Identifiers asserted by the draft that appear nowhere in its brief."""
    text = " ".join(str(draft.get(f) or "") for f in ("title", "body", "bottom_line"))
    if isinstance(draft.get("body"), list):
        text = " ".join([str(draft.get("title") or "")]
                        + [str(x) for x in draft["body"]]
                        + [str(draft.get("bottom_line") or "")])
    hay = _brief_haystack(brief)
    if not hay.strip():
        return []          # no brief to check against; the existing no-brief rule owns that
    seen, out = set(), []
    for rx in _IDENT_RES:
        for m in rx.finditer(text):
            ident = m.group(1)
            key = ident.lower().replace(" ", "")
            if key in seen:
                continue
            seen.add(key)
            if key not in hay.lower().replace(" ", ""):
                out.append(f"the draft cites identifier {ident!r}, which appears nowhere in "
                           f"the brief or its sourced text")
    return out


# P6, LINT 2: A DRAFT THAT CONTRADICTS ITSELF. The same audit found an article stating one
# quantity two different ways in consecutive sentences. Across stories the desk already has
# this machinery; pointed at a single draft it is the same arithmetic.
# THE SUFFIX TABLE MUST BE COMPLETE OR THE LINT INVENTS CONTRADICTIONS. The first cut
# omitted a bare "B" and "T", so "$2.3B" parsed as two dollars and change, landed in the
# same magnitude band as a "$0.41" elsewhere in the story, and reported a contradiction
# between two figures that were three orders of magnitude apart. Measured on the live
# crypto corpus: 3 false rejects out of 361, all of them this. Trillion is here for the
# same reason, before a market-cap story finds it.
_MONEY_RE = re.compile(
    r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand|bn|tn|[bmkt])?\b",
    re.I)
_SCALE = {"trillion": 1e12, "tn": 1e12, "t": 1e12,
          "billion": 1e9, "bn": 1e9, "b": 1e9,
          "million": 1e6, "m": 1e6,
          "thousand": 1e3, "k": 1e3}


def _money_values(text):
    """Normalized USD magnitudes with the surface form that produced each."""
    out = []
    for m in _MONEY_RE.finditer(text or ""):
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append((n * _SCALE.get((m.group(2) or "").lower(), 1.0), m.group(0).strip()))
    return out


def _intra_draft_contradictions(draft):
    """The same subject quantity given two different values inside one draft.

    ONLY THE HEADLINE FIGURE. Comparing every pair of numbers in a story reports a
    contradiction every time a piece legitimately carries a $30M fine and a $57M contract,
    which is most stories. The checkable claim is narrower: a figure asserted in the TITLE
    is the story's headline quantity, and the body restating it as a different number is a
    self-contradiction the reader sees without leaving the page."""
    title_vals = _money_values(str(draft.get("title") or ""))
    if not title_vals:
        return []
    body = draft.get("body")
    body_text = " ".join(str(x) for x in body) if isinstance(body, list) else str(body or "")
    body_text += " " + str(draft.get("bottom_line") or "")
    body_vals = _money_values(body_text)
    if not body_vals:
        return []
    out = []
    for tval, tsurf in title_vals:
        # Same order of magnitude means the body is talking about the same quantity rather
        # than a different figure that happens to be in the story.
        near = [(v, s) for v, s in body_vals if v and 0.2 <= v / tval <= 5.0]
        if not near:
            continue
        if any(abs(v - tval) / tval <= 0.02 for v, _s in near):
            continue                      # the body does restate the headline figure
        # EXACTLY ONE COMPETING VALUE, OR IT IS NOT A CONTRADICTION. A self-contradiction
        # is "the headline says X and the body says Y". A story carrying three different
        # figures in the same magnitude band is a story about three quantities, which is
        # ordinary reporting: "Stellar RWA quadruples to nearly $4B" legitimately discusses
        # $3 billion and $6.36 billion alongside it. Measured on the live crypto corpus,
        # this condition is the whole difference between 2 false rejects and 0.
        distinct = sorted({round(v, 2) for v, _s in near})
        if len(distinct) != 1:
            continue
        other = ", ".join(sorted({s for _v, s in near})[:3])
        out.append(f"the headline says {tsurf} but the body states {other} for what "
                   f"reads as the same figure, and never restates {tsurf}")
    return out


def _lint_accuracy(obj, pairs):
    """Flip drafts failing a deterministic accuracy lint to REJECT, with the precise
    finding, BEFORE repair/rescue, exactly as the weekday-date lint does."""
    by_id = {p["id"]: p for p in pairs}
    flipped = 0
    for a in obj["approvals"]:
        pair = by_id.get(a["id"]) or {}
        draft, brief = pair.get("draft") or {}, pair.get("brief") or {}
        findings = _smuggled_identifiers(draft, brief) + _intra_draft_contradictions(draft)
        if not findings:
            continue
        a.setdefault("reasons", []).extend(findings)
        if a["decision"] == "APPROVE":
            a["decision"] = "REJECT"
            a["category"] = "accuracy"
            flipped += 1
    return flipped


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
        _now = datetime.datetime.now(datetime.timezone.utc)
        user = ("Judge each draft against its research brief. Decision + categorized "
                "reason each.\n"
                f"Today is {_now.strftime('%A')}, {_now.date().isoformat()}. A draft that "
                "reports an event dated after today as having already happened is an "
                "accuracy REJECT; scheduled events are written as upcoming."
                "\n\nDrafts with briefs:\n" + json.dumps(chunk, indent=1))
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
    linted = _lint_weekday_dates(obj, pairs)
    if linted:
        print(f"approver: {linted} approval(s) flipped to REJECT by the weekday-date lint")
    acc = _lint_accuracy(obj, pairs)
    if acc:
        print(f"approver: {acc} approval(s) flipped to REJECT by the accuracy lints "
              f"(smuggled identifier / self-contradicting figure)")
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
