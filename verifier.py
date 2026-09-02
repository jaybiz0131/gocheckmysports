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
    feed_text = str(story.get("feed_text") or "")
    # UP TO 6 URLS FOR 3 READABLE PAGES (ported from the news desk's 2026-07-21 fix,
    # which this desk never received; owner directive 2026-08-25). A blocked URL no
    # longer consumes one of the three read slots while a fetchable corroborating
    # outlet sits further down the list.
    fetched_ok = 0
    for url in (story.get("source_urls", []) or [])[:6]:
        if fetched_ok >= 3:
            break
        code, text = common.fetch_article_text(url)
        if code != 200:
            text = ""
        if len(text) < 200:
            # THE LOG NAMES THE CAUSE (owner report 2026-08-25): one meta probe on the
            # thin minority so the log carries status/final URL/content-type/bytes
            # instead of the old two-word "0 chars" diagnostic.
            m = common.fetch_page_meta(url)
            diag = (f"status={m['status']} final={str(m['final_url'])[:120]} "
                    f"ctype={str(m['content_type'])[:40]} bytes={m['bytes']} "
                    f"extract={len(text)}")
            common.gh("warning", f"source fetch thin: {diag} :: {url}")
        else:
            diag = f"status={code} extract={len(text)}"
        if len(text) >= 200:
            fetched_ok += 1
        checks.append({"url": url, "http_status": code,
                       # KEEP WHAT THE PUBLISHER GAVE US (owner audit 2026-08-25). This
                       # discarded anything under 200 chars, which threw away the exact
                       # og:description and JSON-LD text the extractor had just recovered
                       # (97-147 chars of the publisher's own summary), so eight stories
                       # a run still reached the writer as "0 chars of source text". The
                       # writer's own floor decides what is too thin to write from; this
                       # stage's job is to carry whatever was actually read.
                       "source_text": text,
                       "text_origin": "page", "fetch_meta": diag,
                       "text_excerpt": (text[:1500] if text else f"(unreadable: {diag})")})
    # PUBLISHER'S OWN FEED TEXT, ONLY WHEN NO PAGE COULD BE READ (owner report
    # 2026-08-25): when every article page came back unreadable but the story's feed
    # entry carries the publisher's own words, the desk verifies and briefs from those,
    # labeled as exactly that. The page always wins when any page was readable, and the
    # fallback never stacks on top of real text, so source_chars stays honest.
    # THIN, NOT ONLY EMPTY (family audit 2026-09-02). The fallback fired only when
    # EVERY page was unreadable, so one 130-char og:description from a client-rendered
    # shell counted as "a page was read" and the publisher's 2,000-char feed text was
    # thrown away; the brief was built from 130 chars, the writer starved, the approver
    # killed. When what was read totals under READABLE_FLOOR, the feed text rides too,
    # labeled as exactly what it is, and source_chars counts it honestly.
    READABLE_FLOOR = 1200
    _read = sum(len(c.get("source_text") or "") for c in checks)
    if checks and _read < READABLE_FLOOR and len(feed_text) >= 150 \
            and not any(feed_text[:200] in (c.get("source_text") or "") for c in checks):
        checks.append({"url": (story.get("source_urls") or [""])[0], "http_status": None,
                       "source_text": feed_text[:6000], "text_origin": "feed",
                       "fetch_meta": "publisher feed text; the article pages read thin or unreadable",
                       "text_excerpt": ("(the article pages read thin or could not be read; "
                                        "what follows is the publisher's own feed text for "
                                        "this story) "
                                        + feed_text)[:1500]})
    return checks



def _with_siblings(story, clusters):
    """The story enriched with URLs (and the richest feed_text) from OTHER clusters
    covering the same event.

    THE 12:36 DISPATCH RUN'S LESSON (2026-08-25): the editor ranked the day's stories
    via their walled-outlet framing (CoinDesk 429, The Block 403, Cointelegraph
    client-shell), while READABLE coverage of the SAME events from other configured
    outlets sat in sibling clusters the verifier never tried, because cross-outlet
    versions do not always merge in dedupe (headline styles differ). Result: VERIFIED
    0 of 12 while verifiable text existed in intake. Same event, different outlet,
    real fetch: that is corroboration, not a shortcut, and the verifier still judges
    the claim against whatever text it actually reads.
    """
    # dedupe the story's OWN urls too: corroboration entries repeat the head url when
    # outlets share a canonical link, and each repeat was a wasted paid fetch of a page
    # already read (six identical fetches observed on one story).
    urls = []
    for u in (story.get("source_urls") or []):
        if u and u not in urls:
            urls.append(u)
    feed_text = ""
    head = str(story.get("headline") or "")
    try:
        import dedupe as _dd
        for c in clusters.values():
            ft = str(c.get("feed_text") or "")
            if c.get("id") == story.get("id"):
                if len(ft) > len(feed_text):
                    feed_text = ft
                continue
            if not _dd.same_event(head, "", str(c.get("headline") or ""), ""):
                continue
            for u in [c.get("url")] + [x.get("url") for x in (c.get("corroboration") or [])]:
                if u and u.startswith("http") and u not in urls:
                    urls.append(u)
            if len(ft) > len(feed_text):
                feed_text = ft
    except Exception:
        pass
    return {**story, "source_urls": urls[:6], "feed_text": feed_text}


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
    # the cluster carries the publisher's feed text for the fallback in gather_sources
    try:
        _clusters = {c.get("id"): c for c in common.read_out("items.json").get("clusters", [])}
    except Exception:
        _clusters = {}
    client = client or llmlib.Client(cfg)
    system = common.load_prompt("verifier.md")
    enriched = []
    for s in ranked:
        enriched.append({
            "id": s["id"], "headline": s["headline"], "why_it_matters": s["why_it_matters"],
            "category": s.get("category", "other"), "confidence": s.get("confidence", "medium"),
            # THE TIER RULE NEEDS THE TIER (owner directive 2026-08-25). The verifier is
            # now told that one PRIMARY source is the strongest sourcing there is and one
            # established outlet's own reporting is publishable with attribution, while a
            # low-tier single source is not. It could not apply any of that: the enriched
            # payload carried outlet NAMES but never the configured tier, so every source
            # looked alike and everything single-outlet was routed to the review queue.
            "source_tier": (_clusters.get(s["id"], {}) or {}).get("source_tier", "unknown"),
            "corroborating_outlets": [x.get("name") for x in
                                      ((_clusters.get(s["id"], {}) or {}).get("corroboration") or [])],
            "source_urls": s.get("source_urls", []),
            "source_checks": gather_sources(_with_siblings(s, _clusters), client.mode),
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
