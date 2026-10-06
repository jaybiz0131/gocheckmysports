#!/usr/bin/env python3
"""scripts/indexnow.py: tell the search engines which URLs changed (IndexNow).

IndexNow is the protocol Bing, Yandex, Seznam and Naver read; Bing feeds DuckDuckGo and the
others. The site hosts a key file at /<key>.txt as proof of ownership and POSTs a list of URLs
to api.indexnow.org. No account, no secret: the key is public by design, the same on every
site in the family.

    python3 scripts/indexnow.py                      the whole site: every sitemap, in full
    python3 scripts/indexnow.py URL [URL ...]        a targeted send of exactly these URLs
    python3 scripts/indexnow.py --content FILE ...   the article URLs of these content files

Prints the count sent and the HTTP status of each batch. 200 and 202 are success. Any other
status prints the response body and the run exits non-zero. Standard library only.
"""
import json
import re
import sys
import urllib.error
import urllib.request

HOST = "gocheckmysports.com"
KEY = "75487c1df3b38a38ef2793600c7e7bf7"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10000
OK = (200, 202)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gocheckmysports-indexnow"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def sitemap_urls(get=fetch, root=f"https://{HOST}/sitemap.xml"):
    """Every URL in the sitemap index and every sitemap it lists (or the one sitemap)."""
    top = get(root)
    if "<sitemapindex" in top:
        bodies = [get(loc) for loc in re.findall(r"<sitemap>\s*<loc>([^<]*)</loc>", top)]
    else:
        bodies = [top]
    urls = []
    for b in bodies:
        urls += re.findall(r"<url>.*?<loc>([^<]*)</loc>", b, flags=re.S)
    return urls


def content_urls(paths):
    """The article URLs for site/content files, so a run can submit only what it published."""
    out = []
    for p in paths:
        try:
            slug = json.load(open(p, encoding="utf-8")).get("slug")
        except (OSError, ValueError):
            continue
        if slug:
            out.append(f"https://{HOST}/articles/{slug}")
    return out


def clean(urls):
    """Own-host http(s) URLs only, in order, once each. IndexNow rejects a foreign host."""
    seen, keep = set(), []
    for u in urls:
        u = u.strip()
        if u in seen or not re.match(rf"https?://{re.escape(HOST)}(/|$)", u):
            continue
        seen.add(u)
        keep.append(u)
    return keep


def body(urls):
    return {"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": list(urls)}


def post(payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=data, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "gocheckmysports-indexnow"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main(argv, get=fetch, send=post):
    args = list(argv)
    if args[:1] == ["--content"]:
        urls = content_urls(args[1:])
        what = f"{len(urls)} article URL(s) from {len(args) - 1} content file(s)"
    elif args:
        urls = args
        what = f"{len(args)} URL(s) from the command line"
    else:
        urls = sitemap_urls(get)
        what = "every URL in the sitemaps"
    kept = clean(urls)
    print(f"indexnow: {what}; {len(kept)} sent after keeping own-host URLs once each")
    if not kept:
        print("indexnow: nothing to send")
        return 0
    bad = 0
    for i in range(0, len(kept), BATCH):
        chunk = kept[i:i + BATCH]
        status, text = send(body(chunk))
        n = i // BATCH + 1
        print(f"indexnow: batch {n}: {len(chunk)} URL(s), HTTP {status}")
        if status not in OK:
            bad += 1
            print(f"indexnow: batch {n} refused with {status}: {text[:500]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
