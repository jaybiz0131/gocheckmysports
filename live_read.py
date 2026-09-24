#!/usr/bin/env python3
"""live_read.py: read a deployed page and ASSERT WHICH DEPLOY IT IS before measuring.

U-10 and U-11, 24 September 2026. A measurement counts only when the thing measured is the
thing shipped, and on 24 September this desk could not prove a documents-only push had not
rebuilt the site, because Netlify posts no status to GitHub and a paused site and a skipped
build read identically. Every page now carries the commit that built it, and every live read
comes through here.

    python3 live_read.py https://gocheckmysports.com/ --expect 75ecb4e
    python3 live_read.py https://gocheckmysports.com/ --expect-head   # expect origin/main

Exit 0 only when the page's stamp matches. Exit 2 on a mismatch, which is the case that used
to pass silently: the number you then take is real and about the wrong deploy.
"""
import argparse
import re
import subprocess
import sys
import urllib.request

META = re.compile(r'<meta name="build-commit" content="([0-9a-fA-F]{7,40}|unknown)"')


def fetch(url, timeout=25):
    # Cache-busted, because a CDN copy of the previous deploy is exactly the stale read
    # this file exists to catch.
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(url + f"{sep}cb=live_read",
                                 headers={"User-Agent": "gcm-live-read",
                                          "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def stamp_of(url):
    """(commit, source). The page's meta tag, falling back to /stamp.txt."""
    status, body = fetch(url)
    m = META.search(body)
    if m:
        return m.group(1), f"meta tag on {url} (HTTP {status})"
    root = url.split("//", 1)[0] + "//" + url.split("//", 1)[1].split("/", 1)[0]
    try:
        st, txt = fetch(root + "/stamp.txt")
        m2 = re.search(r"commit ([0-9a-fA-F]{7,40}|unknown)", txt)
        if m2:
            return m2.group(1), f"/stamp.txt (HTTP {st}); the page carried no meta tag"
    except Exception as exc:
        return None, f"no meta tag on {url} and /stamp.txt unreadable ({exc})"
    return None, f"no meta tag on {url} and /stamp.txt carried no commit"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--expect", help="the commit the deploy should be")
    ap.add_argument("--expect-head", action="store_true",
                    help="expect origin/main, read with git")
    a = ap.parse_args()

    want = a.expect
    if a.expect_head:
        want = subprocess.run(["git", "rev-parse", "origin/main"],
                              capture_output=True, text=True).stdout.strip()
    got, src = stamp_of(a.url)
    print(f"live read: {a.url}")
    print(f"  stamp: {got}   ({src})")
    if got is None:
        print("  VERDICT: no stamp. Nothing may be measured against this read.")
        return 2
    if got == "unknown":
        print("  VERDICT: the build could not name its own commit. Not a deploy to measure.")
        return 2
    if not want:
        print("  VERDICT: stamp read, no --expect given, so nothing is asserted.")
        return 0
    n = min(len(want), len(got))
    if want[:n].lower() != got[:n].lower():
        print(f"  VERDICT: MISMATCH. Expected {want[:12]}, the page was built from "
              f"{got[:12]}. Measure nothing from this read.")
        return 2
    print(f"  VERDICT: match on {n} chars. This is the deploy meant; measuring is allowed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
