#!/usr/bin/env python3
"""
verifier.py: Stage 3, the INDEPENDENT verifier AI (audits the editor).

A separate call with an adversarial prompt (the builder never verifies their own work). For
each ranked story it live-fetches the cited source_urls and hands the model the actual page
text, so it can confirm the claim's facts are really present (the same live-source discipline
as the Pet curated-recall verifier). Emits a per-story verdict VERIFIED / NEEDS-HUMAN-REVIEW
/ REJECT and computes divergence from the editor. Fail-closed.

Note: in replay mode the live source fetch is skipped (offline), and every source_check is
recorded as skipped so the model routes unconfirmed items to NEEDS-HUMAN-REVIEW, which is the
correct fail-closed direction for a test run.

USAGE
  python3 verifier.py
  DESK_LLM_MODE=replay python3 verifier.py
"""

import json
import sys

import common
import llm as llmlib

VALID = {"VERIFIED", "NEEDS-HUMAN-REVIEW", "REJECT"}


def gather_sources(story, mode):
    """Fetch each cited source once. text_excerpt (article-extracted, 1500 chars) goes to the
    verifier model; source_text (the full extraction, ~6000 chars) is persisted downstream so
    the researcher can build its brief without a second HTTP pass."""
    checks = []
    if mode == "replay":
        for url in story.get("source_urls", []) or []:
            checks.append({"url": url, "http_status": None, "source_text": "",
                           "text_excerpt": "(skipped: replay mode is offline)"})
        return checks
    for url in (story.get("source_urls", []) or [])[:3]:
        code, text = common.fetch_article_text(url)
        if code == 200:
            checks.append({"url": url, "http_status": code, "source_text": text,
                           "text_excerpt": text[:1500]})
        else:
            checks.append({"url": url, "http_status": code, "source_text": "",
                           "text_excerpt": text})
    return checks


def build_user(enriched):
    # The model sees the 1500-char excerpts, not the full extractions (cost discipline);
    # the full source_text rides only in out/source_texts.json for the researcher.
    slim = [{**s, "source_checks": [{k: v for k, v in c.items() if k != "source_text"}
                                    for c in s["source_checks"]]} for s in enriched]
    return ("Audit these ranked stories. For each, use the fetched source_checks to confirm or "
            "refute the claim, then return a verdict.\n\n" + json.dumps(slim, indent=2))


def validate(obj, ranked):
    if not isinstance(obj, dict) or "verdicts" not in obj or not isinstance(obj["verdicts"], list):
        raise llmlib.LLMError("verifier output missing 'verdicts' list")
    ids = {s["id"] for s in ranked}
    by_id = {}
    for v in obj["verdicts"]:
        vid = v.get("id")
        verdict = v.get("verdict")
        if verdict not in VALID:
            raise llmlib.LLMError(f"verifier: invalid verdict '{verdict}' for id {vid}")
        v.setdefault("reasons", [])
        by_id[vid] = v
    # Fail-closed on coverage: any story the verifier did not judge is treated as REVIEW,
    # never silently promoted.
    for sid in ids:
        if sid not in by_id:
            by_id[sid] = {"id": sid, "verdict": "NEEDS-HUMAN-REVIEW",
                          "reasons": ["verifier returned no verdict for this story"],
                          "source_supported": False, "shill_missed_by_editor": False}
    obj["verdicts"] = [by_id[s["id"]] for s in ranked]
    return obj


def run(client=None):
    cfg = common.load_config()
    editor = common.read_out("editor.json")
    ranked = editor["ranked"]
    client = client or llmlib.Client(cfg)
    system = common.load_prompt("verifier.md")
    enriched = []
    for s in ranked:
        enriched.append({
            "id": s["id"], "headline": s["headline"], "why_it_matters": s["why_it_matters"],
            "category": s.get("category", "other"), "confidence": s.get("confidence", "medium"),
            "source_urls": s.get("source_urls", []),
            "source_checks": gather_sources(s, client.mode),
        })
    # Persist the full extractions for the researcher (one fetch serves both stages).
    common.write_out("source_texts.json", {
        s["id"]: [{"url": c["url"], "http_status": c["http_status"],
                   "source_text": c.get("source_text", "")} for c in s["source_checks"]]
        for s in enriched})
    user = build_user(enriched)

    obj = client.call_json("verifier", system, user,
                           validate=lambda o: validate(o, ranked))

    counts = {"VERIFIED": 0, "NEEDS-HUMAN-REVIEW": 0, "REJECT": 0}
    for v in obj["verdicts"]:
        counts[v["verdict"]] += 1
    obj["_meta"] = {"stage": "3-verifier", "mode": client.mode,
                    "audited": len(ranked), "counts": counts,
                    "budget": client.budget.summary()}
    path = common.write_out("verifier.json", obj)
    print(f"verifier: {counts} across {len(ranked)} stories -> {path} [mode={client.mode}]")
    return obj


def main():
    try:
        run()
    except llmlib.LLMError as e:
        common.gh("error", f"verifier: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
