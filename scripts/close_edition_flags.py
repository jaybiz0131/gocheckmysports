#!/usr/bin/env python3
"""
close_edition_flags.py: close the edition flag issues once an edition has been served.

THE CHASSIS COPY. Identical in gocheckmycrypto, gocheckmynews and gocheckmysports.

WHY THIS EXISTS (family audit 2026-09-02). The brief workflow opens one "Edition stage
failed: <slot> <date>" issue per failed slot, the watcher opens "Missed edition" and
edition_check opens "Edition gap", and nothing ever closed any of them: the crypto desk
had 25 open issues, one per slot, and the sports and news desks a dozen each. A tracker
where every entry is stale is a tracker nobody reads, and the next real failure arrived
as issue #74 with the same title shape as the 24 before it. The failure-flag step already
has its other half ("Clear the failure flag on a green run"); this is the edition's.

Runs after the wrap step, reads out/wrap-status.json, and when the slot was served
(mode synthesis or digest) closes every open issue whose title starts with one of the
edition flag prefixes, with a comment naming the run and the mode. Observability only:
it never fails the run, and it stays quiet when there is nothing to close.
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIXES = ("Edition stage failed:", "Edition gap:", "Missed edition:")


def _api(url, token, data=None, method=None):
    req = urllib.request.Request(
        url, data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("REPO")
    run_url = os.environ.get("RUN_URL", "")
    try:
        status = json.load(open(os.path.join(HERE, "out", "wrap-status.json"),
                                encoding="utf-8"))
    except Exception as e:
        print(f"close_edition_flags: no wrap status to act on ({e})")
        return 0
    mode = status.get("mode", "")
    if mode not in ("synthesis", "digest"):
        print(f"close_edition_flags: edition mode is {mode!r}; nothing to close")
        return 0
    if not token or not repo:
        print("close_edition_flags: no GitHub token or repo; skipping")
        return 0
    slot = f"{status.get('edition', '?')} {status.get('date', '?')}"
    note = (f"An edition was served for the {slot} slot ({mode}"
            + (f", {len(status.get('repairs') or [])} deterministic repair(s)"
               if status.get("repairs") else "")
            + f"): {run_url}\n\nClosing; a new flag opens if a later slot fails.")
    try:
        closed = 0
        for page in (1, 2, 3):
            issues = _api(f"https://api.github.com/repos/{repo}/issues?state=open"
                          f"&per_page=100&page={page}", token)
            if not issues:
                break
            for i in issues:
                if "pull_request" in i or not any(
                        str(i.get("title", "")).startswith(p) for p in PREFIXES):
                    continue
                _api(i["comments_url"], token, {"body": note})
                _api(f"https://api.github.com/repos/{repo}/issues/{i['number']}", token,
                     {"state": "closed", "state_reason": "completed"}, method="PATCH")
                closed += 1
            if len(issues) < 100:
                break
        print(f"close_edition_flags: closed {closed} edition flag issue(s) after the "
              f"{slot} edition published ({mode})")
    except Exception as e:
        print(f"::warning::close_edition_flags: could not update the tracker ({e}); "
              f"the flags stay open until the next served slot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
