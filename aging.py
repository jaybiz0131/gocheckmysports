#!/usr/bin/env python3
"""
aging.py: the SLOW feedback loop (monthly, REPORT-ONLY). Sports content rots fast; a
correction policy protects credibility more than perfection does.

For every published story in site/content/ it (1) re-fetches the story's recorded source
URLs and flags dead links, then (2) asks the model whether any story's premise has been
invalidated by what those pages say NOW. The output is an artifact-only report (out/
aging_report.json + .md); this script NEVER edits the site. A human reads the report and
decides on corrections.

Fail-open per story (a fetch failure is a flagged line, not a crash); fail-closed at the
stage level for the model call. PAUSE file at repo root skips the whole pass.

USAGE  python3 aging.py
"""

import glob
import json
import os
import sys

import common
import llm as llmlib

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "site", "content")


def load_published():
    stories = []
    for p in sorted(glob.glob(os.path.join(CONTENT, "*.json"))):
        if os.path.basename(p).startswith("example"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        body = d.get("body", "")
        if isinstance(body, list):
            body = "\n".join(str(x) for x in body)
        srcs = [s.get("url") if isinstance(s, dict) else s for s in d.get("sources", [])]
        stories.append({"file": os.path.basename(p), "title": d.get("title", ""),
                        "body": str(body)[:1200], "sources": [s for s in srcs if s]})
    return stories


def recheck_sources(stories):
    for s in stories:
        checks = []
        for url in s["sources"][:3]:
            code, page = common.fetch_page(url)
            checks.append({"url": url, "http_status": code,
                           "current_text": common.extract_article_text(page, cap=2500)
                           if code == 200 else ""})
        s["source_checks"] = checks
        s["dead_links"] = [c["url"] for c in checks if c["http_status"] != 200]
    return stories


PROMPT = """You are the AGING REVIEWER for GoCheckMySports, running the desk's monthly
post-publication review. For each published story you get its title, an excerpt of its
body, and the CURRENT text fetched from its original sources. Judge only one thing per
story: has the story's premise been invalidated or materially superseded by what the
sources say now (a suspension was overturned, a trade fell through, a figure was
corrected, an "expected" event did not happen)? Unreachable sources are already flagged
separately; do not treat
a fetch failure as invalidation. Be conservative: flag only clear cases, with the
specific reason. Respond with ONLY JSON:
{"flags": [{"file": "<file>", "reason": "<what changed and why it invalidates the story>"}]}
An empty flags list is a fine answer. Output valid JSON and nothing else."""


def main():
    if os.path.exists(os.path.join(HERE, "PAUSE")):
        print("aging: PAUSE file present -> skipping")
        return 0
    stories = load_published()
    if not stories:
        print("aging: no published stories -> nothing to review")
        return 0
    stories = recheck_sources(stories)
    dead = {s["file"]: s["dead_links"] for s in stories if s["dead_links"]}

    cfg = common.load_config()
    client = llmlib.Client(cfg)
    payload = [{k: s[k] for k in ("file", "title", "body")}
               | {"current_sources": s["source_checks"]} for s in stories]
    try:
        obj = client.call_json("aging", PROMPT,
                               "Published stories with re-fetched sources:\n"
                               + json.dumps(payload, indent=1))
        flags = obj.get("flags", []) if isinstance(obj, dict) else []
    except llmlib.LLMError as e:
        common.gh("error", f"aging: model review failed ({e}); reporting link rot only")
        flags = [{"file": "(model review failed)", "reason": str(e)}]

    report = {"stories_reviewed": len(stories), "dead_links": dead, "flags": flags}
    common.write_out("aging_report.json", report)
    lines = [f"# Aging review: {len(stories)} published stories\n"]
    lines += [f"- DEAD LINKS in {f}: {', '.join(u)}" for f, u in dead.items()]
    lines += [f"- FLAGGED {x.get('file','?')}: {x.get('reason','')}" for x in flags]
    if not dead and not flags:
        lines.append("Nothing flagged. All sources resolve and no premise looks invalidated.")
    os.makedirs(common.OUT_DIR, exist_ok=True)
    open(os.path.join(common.OUT_DIR, "aging_report.md"), "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))
    if dead or flags:
        common.gh("warning", f"aging: {len(dead)} stories with dead links, "
                  f"{len(flags)} premise flags -> human review (report-only, site untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
