#!/usr/bin/env python3
"""
publish.py: Stage 6, the FAIL-CLOSED, approval-gated auto-push.

Auto-push handles the MECHANICAL distribution only, never the editorial decision. It publishes
a story ONLY when every gate passes:
  1. A human wrote an approval file (out/approval.json) with decision == "approve" for it.
  2. The verifier verdict was VERIFIED, or NEEDS-HUMAN-REVIEW WITH an explicit human approval
     (human override). REJECT is never publishable.
  3. The run is a live run (mode == "live"). A replay/test run can never publish.
Any gate that fails means that story is skipped and logged; a story is never published by default.

The push targets (newsletter/site/social/video) are adapters. Until a target is enabled and
given real credentials in config.json, each adapter is a DRY-RUN that logs the exact payload it
WOULD send and writes it to out/published/. This is the same fail-closed posture as the Storm
validation gate: nothing leaves the building unless it is approved, verified, and configured.

USAGE
  python3 publish.py                       # read out/approval.json, publish approved+verified
  python3 publish.py --approval PATH        # use a different approval file
  python3 publish.py --dry-run              # force dry-run even if a target is enabled
"""

import json
import os
import sys

import common

PUBLISHED_DIR = os.path.join(common.OUT_DIR, "published")


def load_approval(path):
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding="utf-8"))


def adapter_send(target, cfg_target, payload, force_dry):
    """A push adapter. Returns (sent_for_real: bool, note). Real sends require the target to be
    enabled AND to carry an endpoint/key; otherwise it is a logged dry-run. No real integration
    ships wired to a live endpoint by default - that is deliberate (fail-closed)."""
    enabled = cfg_target.get("enabled", False) and not force_dry
    endpoint = cfg_target.get("endpoint")
    if not enabled or not endpoint:
        return False, f"dry-run ({'disabled' if not cfg_target.get('enabled') else 'no endpoint'})"
    # A real integration would POST here. Intentionally not implemented against a live endpoint
    # in v1: wiring a real push requires the operator to add the endpoint + credential and a
    # send implementation, so the pipeline cannot accidentally broadcast.
    return False, "dry-run (no live send implementation shipped in v1; add one deliberately)"


def run(approval_path=None, force_dry=False):
    cfg = common.load_config()
    pub = cfg["publish"]
    approval_path = approval_path or os.path.join(common.OUT_DIR, "approval.json")
    approval = load_approval(approval_path)

    if approval is None:
        print(f"publish: no approval file at {os.path.relpath(approval_path)} -> nothing "
              f"approved, publishing NOTHING (fail-closed). Edit approval_template.json, save "
              f"it as approval.json, and re-run.")
        return {"published": [], "skipped": [], "reason": "no approval file"}

    mode = approval.get("mode", "live")
    if mode != "live":
        common.gh("error", f"publish: approval file is mode={mode} (a non-production run). "
                           f"Refusing to publish a test run. Publishing NOTHING.")
        return {"published": [], "skipped": [], "reason": f"mode={mode} not publishable"}

    drafts = {d["id"]: d for d in common.read_out("drafts.json")["drafts"]}
    verdicts = {v["id"]: v["verdict"] for v in common.read_out("verifier.json")["verdicts"]}
    allow_review = set(pub.get("allow_with_human_override", []))
    require = set(pub.get("require_verifier_verdict", []))

    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    published, skipped = [], []
    for sid, entry in (approval.get("stories") or {}).items():
        decision = entry.get("decision", "hold")
        verdict = verdicts.get(sid)
        if decision != "approve":
            skipped.append({"id": sid, "why": f"not approved (decision={decision})"})
            continue
        if verdict == "REJECT" or verdict is None:
            skipped.append({"id": sid, "why": f"verifier verdict {verdict} is never publishable"})
            continue
        if verdict not in require and verdict not in allow_review:
            skipped.append({"id": sid, "why": f"verdict {verdict} not in publishable set"})
            continue
        draft = drafts.get(sid)
        if not draft:
            skipped.append({"id": sid, "why": "no draft for approved story"})
            continue
        take = (entry.get("human_take") or "").strip()
        # A REVIEW story published on human override must carry the human's take (that is the
        # override); a VERIFIED story may publish with or without one.
        if verdict in allow_review and verdict not in require and not take:
            skipped.append({"id": sid, "why": "REVIEW story approved without a human take (override needs the take)"})
            continue

        payload = build_payload(draft, take, pub["not_financial_advice"])
        targets_log = {}
        for tname, tcfg in pub.get("targets", {}).items():
            sent, note = adapter_send(tname, tcfg, payload, force_dry)
            targets_log[tname] = {"sent": sent, "note": note}
        rec = {"id": sid, "verdict": verdict, "targets": targets_log, "payload": payload}
        json.dump(rec, open(os.path.join(PUBLISHED_DIR, f"{sid}.json"), "w", encoding="utf-8"), indent=2)
        published.append({"id": sid, "verdict": verdict, "targets": targets_log})

    print(f"publish: approved+publishable {len(published)}, skipped {len(skipped)} "
          f"(all target sends are dry-run in v1 until an operator wires a real endpoint).")
    for s in skipped:
        print(f"  skip {s['id']}: {s['why']}")
    if published:
        print("publish: to put these approved stories on the site, run:  "
              "python3 site_build.py --ingest")
    result = {"published": published, "skipped": skipped}
    common.write_out("publish_report.json", result)
    return result


def build_payload(draft, human_take, nfa):
    art = dict(draft["article_draft"])
    art["human_take"] = human_take
    art["status"] = "APPROVED" if human_take is not None else art.get("status")
    skel = dict(draft["script_skeleton"])
    skel["human_take"] = human_take
    return {"article": art, "script": skel, "not_financial_advice": nfa}


def main():
    argv = sys.argv[1:]
    approval_path = argv[argv.index("--approval") + 1] if "--approval" in argv else None
    run(approval_path=approval_path, force_dry="--dry-run" in argv)


if __name__ == "__main__":
    main()
