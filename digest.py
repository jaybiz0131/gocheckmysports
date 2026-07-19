#!/usr/bin/env python3
"""
digest.py: Stage 5, the HUMAN REVIEW QUEUE (the non-negotiable gate).

Assembles everything the AIs produced into one review document the human editor-in-chief
approves from. This is where the 20 minutes of judgment + voice happen: the AI did the
reading, triage, fact-check, and drafting; the human overrides, adds the take, and approves.

Writes:
  out/review_queue/<date>.md    human-readable digest (ranked, verified, drafted, plus the
                                shill that was cut, and any editor/verifier divergence)
  out/review_queue/<date>.html  same, styled, for a browser
  out/approval_template.json    the file the human edits to approve stories (Stage 6 reads it)

Nothing here publishes. Approval is a separate, deliberate human step.

USAGE  python3 digest.py [--date YYYY-MM-DD]
"""

import html
import json
import os
import sys

import common

BADGE = {"VERIFIED": "VERIFIED", "NEEDS-HUMAN-REVIEW": "REVIEW", "REJECT": "REJECT"}


def _date(argv):
    if "--date" in argv:
        return argv[argv.index("--date") + 1]
    # No wall clock is read here so the digest is reproducible in tests; fall back to the
    # aggregation timestamp, which the pipeline already stamped.
    try:
        return common.read_out("items.json")["_meta"]["generated"][:10]
    except Exception:
        return "undated"


def assemble(date):
    items = common.read_out("items.json")
    editor = common.read_out("editor.json")
    verifier = common.read_out("verifier.json")
    drafts = common.read_out("drafts.json")
    v_by_id = {v["id"]: v for v in verifier["verdicts"]}
    d_by_id = {d["id"]: d for d in drafts["drafts"]}
    try:
        a_by_id = {a["id"]: a for a in common.read_out("approver.json").get("approvals", [])}
    except Exception:
        a_by_id = {}
    mode = editor.get("_meta", {}).get("mode", "live")

    rows = []
    for s in editor["ranked"]:
        v = v_by_id.get(s["id"], {})
        rows.append({
            "story": s,
            "verdict": v.get("verdict", "NEEDS-HUMAN-REVIEW"),
            "verdict_reasons": v.get("reasons", []),
            "diverged": (s.get("confidence") == "high" and v.get("verdict") != "VERIFIED"),
            "draft": d_by_id.get(s["id"]),
            "approval": a_by_id.get(s["id"]),
        })
    return {
        "date": date, "mode": mode, "items": items, "editor": editor,
        "verifier": verifier, "drafts": drafts, "rows": rows,
        "rejected": editor.get("rejected", []),
        "nfa": common.load_config()["publish"]["not_financial_advice"],
    }


def render_md(a):
    L = []
    banner = "" if a["mode"] == "live" else f"\n> WARNING: mode={a['mode']} (NON-PRODUCTION test run; do not approve or publish this).\n"
    L.append(f"# GoCheckMySports - review queue - {a['date']}\n{banner}")
    L.append(f"_The AI did the reading, triage, fact-check, and drafting. You do the judgment "
             f"and the voice. Nothing publishes without your sign-off._\n")
    m = a["items"]["_meta"]
    L.append(f"Intake: {m['clusters']} clusters from {m['fresh_items']} items across "
             f"{m['sources_ok']}/{m['sources_total']} sources. "
             f"Editor ranked {len(a['editor']['ranked'])}, cut {len(a['rejected'])} as shill/noise.\n")
    L.append("---\n")
    for i, r in enumerate(a["rows"], 1):
        s = r["story"]
        L.append(f"## {i}. {s['headline']}")
        L.append(f"**Verdict: {BADGE.get(r['verdict'], r['verdict'])}**"
                 + ("  |  EDITOR/VERIFIER DIVERGENCE - needs your eyes" if r["diverged"] else ""))
        L.append(f"- Category: {s.get('category','other')}  |  Editor confidence: {s.get('confidence','?')}")
        L.append(f"- Why it matters: {s['why_it_matters']}")
        if r["verdict_reasons"]:
            L.append(f"- Verifier: {'; '.join(r['verdict_reasons'])}")
        apr = r.get("approval")
        if apr:
            if apr["decision"] == "APPROVE":
                L.append("- Approver: APPROVED")
            else:
                L.append(f"- Approver: REJECTED ({apr.get('category','')}) - "
                         f"{'; '.join(apr.get('reasons', []))}")
        for u in s.get("source_urls", []):
            L.append(f"- Source: {u}")
        d = r["draft"]
        if d:
            art = d["article_draft"]
            L.append(f"\n**DRAFT article ({art['status']}):** {art['title']}\n")
            L.append(f"> {art['body']}\n")
            L.append(f"**Script angle:** {d['script_skeleton'].get('angle_prompt','')}")
            L.append(f"**YOUR TAKE (add on camera / in edit):** ______________________________")
            L.append(f"\n_{art['not_financial_advice']}_")
        else:
            L.append("\n_No draft (verdict was REJECT, or routed away from drafting)._")
        L.append(f"\nTo approve: set `\"{s['id']}\"` to `\"approve\"` in out/approval_template.json.\n")
        L.append("---\n")
    if a["rejected"]:
        L.append("## Cut as shill / low significance (the editor showed its work)\n")
        for rj in a["rejected"]:
            L.append(f"- **{rj.get('headline','?')}** - {', '.join(rj.get('shill_flag_reasons', []))}")
        L.append("")
    L.append(f"\n_{a['nfa']}_")
    return "\n".join(L)


def render_html(a):
    e = html.escape
    css = ("body{font:16px/1.5 system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}"
           "h1{margin-bottom:.2rem}.badge{display:inline-block;padding:.1rem .5rem;border-radius:4px;font-size:.8rem;font-weight:600}"
           ".VERIFIED{background:#d8f3dc;color:#1b4332}.REVIEW{background:#fff3bf;color:#664d03}.REJECT{background:#ffd6d6;color:#7d1a1a}"
           ".diverge{color:#7d1a1a;font-weight:600}.warn{background:#ffe8e8;border:1px solid #d33;padding:.6rem;border-radius:6px}"
           "blockquote{border-left:3px solid #ccc;margin:.5rem 0;padding:.2rem .8rem;color:#333}"
           ".take{background:#f3f0ff;border:1px dashed #8a7fd6;padding:.5rem;border-radius:6px}"
           ".src{font-size:.85rem;color:#555}hr{border:none;border-top:1px solid #eee;margin:1.5rem 0}.nfa{color:#666;font-size:.85rem}")
    P = [f"<style>{css}</style>", f"<h1>GoCheckMySports - review queue</h1><p class=src>{e(a['date'])}</p>"]
    if a["mode"] != "live":
        P.append(f"<p class=warn>WARNING: mode={e(a['mode'])} - NON-PRODUCTION test run. Do not approve or publish.</p>")
    P.append("<p><em>The AI did the reading, triage, fact-check, and drafting. You do the judgment and the voice. Nothing publishes without your sign-off.</em></p>")
    m = a["items"]["_meta"]
    P.append(f"<p class=src>Intake: {m['clusters']} clusters from {m['fresh_items']} items across "
             f"{m['sources_ok']}/{m['sources_total']} sources. Editor ranked {len(a['editor']['ranked'])}, "
             f"cut {len(a['rejected'])} as shill/noise.</p><hr>")
    for i, r in enumerate(a["rows"], 1):
        s = r["story"]
        cls = BADGE.get(r["verdict"], "REVIEW")
        P.append(f"<h2>{i}. {e(s['headline'])}</h2>")
        P.append(f"<p><span class='badge {cls}'>{cls}</span>"
                 + (" <span class=diverge>EDITOR/VERIFIER DIVERGENCE - needs your eyes</span>" if r["diverged"] else "") + "</p>")
        P.append(f"<p><b>Why it matters:</b> {e(s['why_it_matters'])}</p>")
        if r["verdict_reasons"]:
            P.append(f"<p class=src><b>Verifier:</b> {e('; '.join(r['verdict_reasons']))}</p>")
        for u in s.get("source_urls", []):
            P.append(f"<p class=src>Source: <a href='{e(u)}'>{e(u)}</a></p>")
        d = r["draft"]
        if d:
            art = d["article_draft"]
            P.append(f"<p><b>DRAFT article ({e(art['status'])}):</b> {e(art['title'])}</p>")
            P.append(f"<blockquote>{e(art['body'])}</blockquote>")
            P.append(f"<p><b>Script angle:</b> {e(d['script_skeleton'].get('angle_prompt',''))}</p>")
            P.append("<p class=take><b>YOUR TAKE</b> (add on camera / in edit): __________</p>")
            P.append(f"<p class=nfa>{e(art['not_financial_advice'])}</p>")
        else:
            P.append("<p class=src><em>No draft (REJECT or routed away from drafting).</em></p>")
        P.append(f"<p class=src>To approve: set \"{e(s['id'])}\" to \"approve\" in approval_template.json.</p><hr>")
    if a["rejected"]:
        P.append("<h2>Cut as shill / low significance</h2><ul>")
        for rj in a["rejected"]:
            P.append(f"<li><b>{e(rj.get('headline','?'))}</b> - {e(', '.join(rj.get('shill_flag_reasons', [])))}</li>")
        P.append("</ul>")
    P.append(f"<p class=nfa>{e(a['nfa'])}</p>")
    return "\n".join(P)


def build_approval_template(a):
    """The file the human edits to approve. Default every story to 'hold' - approval is an
    explicit opt-in, never a default. REJECT stories are not even listed."""
    stories = {}
    for r in a["rows"]:
        if r["verdict"] == "REJECT":
            continue
        stories[r["story"]["id"]] = {
            "headline": r["story"]["headline"],
            "verifier_verdict": r["verdict"],
            "decision": "hold",
            "_options": "approve | hold | kill",
            "human_take": ""
        }
    return {
        "_instructions": ("Set decision to 'approve' for each story you sign off on, add your "
                          "take in human_take, then run publish.py. Only stories you explicitly "
                          "approve are published. This file defaults everything to 'hold'."),
        "date": a["date"], "mode": a["mode"], "stories": stories
    }


def run(date=None):
    a = assemble(date or "undated")
    qdir = os.path.join(common.OUT_DIR, "review_queue")
    os.makedirs(qdir, exist_ok=True)
    md_path = os.path.join(qdir, f"{a['date']}.md")
    html_path = os.path.join(qdir, f"{a['date']}.html")
    open(md_path, "w", encoding="utf-8").write(render_md(a))
    open(html_path, "w", encoding="utf-8").write(render_html(a))
    common.write_out("approval_template.json", build_approval_template(a))
    print(f"digest: review queue for {a['date']} [mode={a['mode']}] -> {os.path.relpath(md_path)} "
          f"(+ .html, + approval_template.json)")
    return a


def main():
    date = None
    argv = sys.argv[1:]
    if "--date" in argv:
        date = argv[argv.index("--date") + 1]
    else:
        date = _date(argv)
    run(date)


if __name__ == "__main__":
    main()
