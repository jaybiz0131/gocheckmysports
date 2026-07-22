#!/usr/bin/env python3
"""
Autopilot: full-auto release for the daily brief, on Jack's standing instruction (2026-07-11).

Policy (supersedes the launch-era always-human gate; recorded in DEVIATIONS):
  - VERIFIED stories publish automatically: the adversarial verifier IS the gate.
  - NEEDS-HUMAN-REVIEW stories are never auto-published; they stay in the review queue for a
    human take (publish.py still enforces that override rule independently).
  - REJECT never publishes. A failed run publishes nothing (fail-closed inheritance).

Three-role pipeline (2026-07-14): auto-publish now also requires the post-draft APPROVER's
sign-off (verdicts VERIFIED alone no longer suffice), and a DEPTH GATE holds any story whose
body ran under 120 words even though its research brief carried >=2000 chars of fetched
source text: the writer had material and did not use it, a quality failure. Thin-source
brevity stays legal (the honesty case): a short story from a thin brief publishes.

Runs after run.py in the daily workflow: writes an approval file that approves exactly the
VERIFIED+APPROVED set, runs Stage 6 (publish.py), then ingests approved payloads into site
content (site_build.py --ingest). The workflow then commits site/content and pushes, which
deploys.
"""

import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")


def _words(s):
    return set(re.findall(r"[a-z]{4,}", (s or "").lower()))


def body_word_count(article_draft):
    body = article_draft.get("body", "")
    if isinstance(body, list):
        body = " ".join(str(p) for p in body)
    return len(str(body).split())


def depth_gate_holds(body_words, source_chars, min_words=120, min_source_chars=2000):
    """True when the story must be HELD: a short body despite substantial source material.
    A short body from thin sources passes (honest brevity is legal; padding is not)."""
    return body_words < min_words and source_chars >= min_source_chars


def breaking_two_source_holds(headline, source_names):
    """The BREAKING-path gate (additive, 2026-07-14 directive): a breaking piece publishes
    as fact only with >=2 independent sources; single-source may publish only when the
    headline itself carries the unconfirmed label; otherwise it HOLDS for the next
    scheduled slot. Deterministic, fail-closed."""
    distinct = {n.strip().lower() for n in source_names if n and n.strip()}
    if len(distinct) >= 2:
        return False
    return "unconfirmed" not in (headline or "").lower()


def already_published(headline):
    """The daily lookback window overlaps day to day, so yesterday's big story can rank again
    under a slightly different headline. Anything sharing >=70% of its meaningful words with
    an existing published title is a rerun and never auto-publishes."""
    hw = _words(headline)
    if not hw:
        return False
    for p in glob.glob(os.path.join(HERE, "site", "content", "*.json")):
        try:
            t = json.load(open(p, encoding="utf-8")).get("title", "")
        except Exception:
            continue
        tw = _words(t)
        if tw and len(hw & tw) / min(len(hw), len(tw)) >= 0.7:
            return True
    return False


def main():
    tpl_path = os.path.join(OUT, "approval_template.json")
    report_path = os.path.join(OUT, "run_report.json")
    if not (os.path.exists(tpl_path) and os.path.exists(report_path)):
        print("autopilot: no run outputs found -> nothing to publish (fail-closed)")
        return 1
    report = json.load(open(report_path, encoding="utf-8"))
    if report.get("mode") != "live" or report.get("status") not in ("ok", "OK", None) and not report.get("review_queue"):
        print(f"autopilot: run not live/ok -> nothing to publish (mode={report.get('mode')})")
        return 1

    # The approver's post-draft verdicts and the researcher's measured source volume: both
    # feed the publish decision. Missing files fail closed (everything holds).
    def _load(name):
        try:
            return json.load(open(os.path.join(OUT, name), encoding="utf-8"))
        except Exception:
            return {}
    approver = {a.get("id"): a for a in _load("approver.json").get("approvals", [])}
    briefs = {b.get("id"): b for b in _load("briefs.json").get("briefs", [])}
    drafts = {d.get("id"): d for d in _load("drafts.json").get("drafts", [])}
    # stories the editor explicitly declared as updates of published work: the rerun
    # guard lets these through; ingest converts them into the update chain
    editor_updates = {r.get("id"): r.get("updates")
                      for r in _load("editor.json").get("ranked", []) if r.get("updates")}
    clusters = {c.get("id"): c for c in _load("items.json").get("clusters", [])}
    breaking = os.environ.get("BREAKING") == "1"

    approval = json.load(open(tpl_path, encoding="utf-8"))
    approved = held = reruns = 0
    for cid, story in approval.get("stories", {}).items():
        appr = approver.get(cid)
        words = body_word_count((drafts.get(cid, {}) or {}).get("article_draft", {}) or {})
        source_chars = (briefs.get(cid) or {}).get("source_chars", 0)
        c = clusters.get(cid) or {}
        src_names = [c.get("source", "")] + [x.get("name", "")
                                             for x in (c.get("corroboration") or [])]
        if story.get("verifier_verdict") != "VERIFIED":
            story["decision"] = "hold"
            held += 1
        elif breaking and breaking_two_source_holds(story.get("headline", ""), src_names):
            story["decision"] = "hold"
            held += 1
            print(f"autopilot: BREAKING two-source gate held "
                  f"'{story.get('headline','')[:60]}' (single-source, not labeled "
                  f"unconfirmed -> waits for the next scheduled slot)")
        elif not appr or appr.get("decision") != "APPROVE":
            story["decision"] = "hold"
            held += 1
            why = f"{appr.get('category')}: {'; '.join(appr.get('reasons', [])[:2])}" if appr else "no approver decision (fail-closed)"
            print(f"autopilot: approver held '{story.get('headline','')[:60]}' ({why})")
        elif depth_gate_holds(words, source_chars):
            story["decision"] = "hold"
            held += 1
            print(f"autopilot: depth gate held '{story.get('headline','')[:60]}' "
                  f"({words} words from {source_chars} chars of source material)")
        elif already_published(story.get("headline", "")) and cid not in editor_updates:
            story["decision"] = "hold"
            reruns += 1
            print(f"autopilot: skipping rerun of already-published story: "
                  f"{story.get('headline','')[:70]}")
        else:
            story["decision"] = "approve"
            approved += 1
    json.dump(approval, open(os.path.join(OUT, "approval.json"), "w", encoding="utf-8"), indent=1)
    print(f"autopilot: auto-approved {approved} VERIFIED, held {held} for human review")
    if approved == 0:
        print("autopilot: nothing VERIFIED today -> site publish skipped, queue kept for human")
        return 0

    r = subprocess.run([sys.executable, os.path.join(HERE, "publish.py")], cwd=HERE)
    if r.returncode != 0:
        print("autopilot: publish.py failed -> fail-closed")
        return 1
    r = subprocess.run([sys.executable, os.path.join(HERE, "site_build.py"), "--ingest"], cwd=HERE)
    if r.returncode != 0:
        print("autopilot: ingest/build failed -> fail-closed")
        return 1
    print("autopilot: published + ingested; workflow commit/push makes it live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
