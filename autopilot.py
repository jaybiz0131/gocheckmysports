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

import dedupe

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


def discovery_only_holds(cluster):
    """AGGREGATOR-DISCOVERY GATE (2026-07-30). Discovery feeds (Google News and friends)
    ride the 'mixed'/'aggregator' tiers so the desk SEES stories its own feeds missed, but
    their links are redirects rather than article URLs and they are not themselves
    reporting. A story whose only sourcing is discovery-tier can never auto-publish: a
    directly-citable tier (primary, major, breaking) must carry it too. Deterministic,
    fail-closed, and independent of the BREAKING path (which only runs on breaking runs)."""
    DISCOVERY = {"mixed", "aggregator", "unknown"}
    tiers = {(cluster.get("source_tier") or "").strip().lower()}
    for x in (cluster.get("corroboration") or []):
        tiers.add((x.get("tier") or "").strip().lower())
    tiers.discard("")
    if not tiers:
        return True   # no tier information at all -> fail closed
    return tiers.issubset(DISCOVERY)


def breaking_two_source_holds(headline, source_names):
    """The BREAKING-path gate (additive, 2026-07-14 directive): a breaking piece publishes
    as fact only with >=2 independent sources; single-source may publish only when the
    headline itself carries the unconfirmed label; otherwise it HOLDS for the next
    scheduled slot. Deterministic, fail-closed."""
    import common as _c
    if _c.distinct_publishers(source_names) >= 2:
        return False
    return "unconfirmed" not in (headline or "").lower()


# already_published() was a 70% title-word test. It could not see a reworded headline,
# which is exactly how the crypto desk published one event three times. Replaced by the
# chassis guard in dedupe.py, called through _rehash_of below.


def _shipped_title(drafts, cid, story):
    """The title the READER will see, not the editor's ranked headline.

    The gate has to judge the string that ships. The crypto desk's three-in-one-day failure
    turned partly on this: one duplicate scored 0.444 as the editor had headlined it and
    0.750 as the writer rewrote it, and only the second number was ever on the page."""
    draft = (drafts.get(cid, {}) or {}).get("article_draft", {}) or {}
    return draft.get("title") or story.get("headline", "") or ""


def _rehash_of(drafts, cid, story):
    """True when this draft retells a story the desk has already published.

    The key fact comes from script_skeleton. article_draft has NO key_fact field (see the
    schema in prompts/writer.md: title/body/bottom_line/human_take/sources/status/
    not_financial_advice), and dedupe._claim_signature() reads key_fact exclusively, so
    reading it off the wrong object hands the guard an empty claim and everything looks new.
    That exact mistake shipped on the crypto desk and published a fourth copy of one
    sanctions story. The fallbacks are ordered so the richest available claim wins."""
    d = drafts.get(cid, {}) or {}
    skel = d.get("script_skeleton") or {}
    art = d.get("article_draft") or {}
    kf = skel.get("key_fact") or art.get("key_fact") or (story.get("snippet") or "")
    verdict, _title, _slug = dedupe.classify_published(
        _shipped_title(drafts, cid, story), kf)
    return verdict == "rehash"


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
    approved_this_run = []  # same-run dedup ledger (fix 3)

    for cid, story in approval.get("stories", {}).items():
        appr = approver.get(cid)
        words = body_word_count((drafts.get(cid, {}) or {}).get("article_draft", {}) or {})
        source_chars = (briefs.get(cid) or {}).get("source_chars", 0)
        c = clusters.get(cid) or {}
        src_names = [c.get("source", "")] + [x.get("name", "")
                                             for x in (c.get("corroboration") or [])]
        # INDEPENDENCE IS BY PUBLISHER, NOT FEED NAME (2026-07-31): ESPN NFL and ESPN Top
        # Lines are one publisher; counting them as two sources would pass the two-source
        # gate on a single-publisher story.
        src_urls = [c.get("url", "")] + [x.get("url", "")
                                         for x in (c.get("corroboration") or [])]
        if story.get("verifier_verdict") != "VERIFIED":
            story["decision"] = "hold"
            held += 1
        elif discovery_only_holds(c):
            story["decision"] = "hold"
            held += 1
            print(f"autopilot: discovery-only sourcing held "
                  f"'{story.get('headline','')[:60]}' (aggregator tier alone is never "
                  f"publishable; a citable outlet must carry it too)")
        elif breaking and breaking_two_source_holds(story.get("headline", ""), src_urls):
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
        elif _rehash_of(drafts, cid, story) and cid not in editor_updates:
            story["decision"] = "hold"
            reruns += 1
            print(f"autopilot: skipping rerun of already-published story: "
                  f"{_shipped_title(drafts, cid, story)[:70]}")
        elif any(dedupe.same_event(str(story.get("headline") or ""),
                                   str(story.get("key_fact") or ""), t, k)
                 for t, k in approved_this_run):
            # SAME-RUN DUPLICATE HOLD (ported from the crypto chassis, fix 3 2026-08-03).
            # The rehash guard above compares against the COMMITTED corpus, so two drafts
            # of one development approved in the same batch never met any guard: that is
            # how the Ceuta pair published 23 minutes apart on this chassis' sibling.
            story["decision"] = "hold"
            reruns += 1
            print(f"autopilot: HELD same-run duplicate of an event already approved this "
                  f"run ('{str(story.get('headline') or '')[:60]}')")
        else:
            story["decision"] = "approve"
            approved += 1
            approved_this_run.append((str(story.get("headline") or ""),
                                      str(story.get("key_fact") or "")))
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
