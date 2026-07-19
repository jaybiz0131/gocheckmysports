#!/usr/bin/env python3
"""
deploy_check.py: post-publish deploy verification (directive item 10, 2026-07-14).

A published commit that never deployed is a story nobody sees, and at 3+ deploys/day a
silent Netlify failure WILL eventually happen. After the workflow pushes, this probes the
LIVE domain for the just-published pages (stories + today's edition) until they serve or
the timeout passes. Outcome is recorded in the job log; on failure it opens a GitHub
Issue (the flag) and exits non-zero so the run goes red.

No Netlify API token exists in this repo, so verification is by direct HTTP probe of the
CDN, which is also the ground truth a reader experiences. (If NETLIFY_AUTH_TOKEN is ever
added, build-level status could be read instead.)

USAGE  python3 deploy_check.py   (env: GITHUB_TOKEN + GITHUB_REPOSITORY to open the flag)
"""

import datetime
import glob
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "https://gocheckmysports.com"
TIMEOUT_MIN = 8
POLL_SECONDS = 30


def just_published_urls():
    """Pages this run added: approved story slugs from out/published + today's edition."""
    urls = []
    for p in glob.glob(os.path.join(HERE, "out", "published", "*.json")):
        try:
            rec = json.load(open(p, encoding="utf-8"))
            art = (rec.get("payload", {}) or {}).get("article", {}) or {}
            title = art.get("title", "")
            if title:
                import site_build
                urls.append(f"{ORIGIN}/articles/{site_build.slugify(title)}.html")
        except Exception:
            continue
    today = datetime.date.today().isoformat()
    for slug in ("morning-brief", "afternoon-brief", "evening-brief"):
        if os.path.exists(os.path.join(HERE, "site", "content", f"{today}-{slug}.json")):
            urls.append(f"{ORIGIN}/articles/{slug}-{today}.html")
    return sorted(set(urls))


def probe(url):
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "GoCheckMySports-deploycheck/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.getcode() == 200
    except Exception:
        return False


def open_flag(missing):
    tok, repo = os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", "")
    if not (tok and repo):
        return
    body = ("A publish commit pushed but these pages never went live within "
            f"{TIMEOUT_MIN} minutes (probable Netlify deploy failure):\n\n"
            + "\n".join(f"- {u}" for u in missing)
            + "\n\nCheck the Netlify deploy log; a retry deploy usually resolves it.")
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues",
            data=json.dumps({"title": f"Deploy failure flag: {len(missing)} page(s) not live",
                             "body": body, "labels": ["deploy"]}).encode(),
            headers={"Authorization": f"Bearer {tok}",
                     "Accept": "application/vnd.github+json"}, method="POST")
        urllib.request.urlopen(req)
        print("deploy_check: flag issue opened")
    except Exception as e:
        print(f"::warning::deploy_check: could not open flag issue ({e})")


def main():
    urls = just_published_urls()
    if not urls:
        print("deploy_check: nothing was published this run; nothing to verify.")
        return 0
    deadline = time.time() + TIMEOUT_MIN * 60
    pending = set(urls)
    while pending and time.time() < deadline:
        for u in sorted(pending):
            if probe(u):
                print(f"deploy_check: LIVE {u}")
                pending.discard(u)
        if pending:
            time.sleep(POLL_SECONDS)
    if pending:
        for u in sorted(pending):
            print(f"::error::deploy_check: NOT LIVE after {TIMEOUT_MIN}m: {u}")
        open_flag(sorted(pending))
        return 1
    print(f"deploy_check: all {len(urls)} published page(s) verified live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
