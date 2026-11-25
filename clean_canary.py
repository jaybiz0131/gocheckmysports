#!/usr/bin/env python3
"""clean_canary.py: S-DONE point 4, nothing unfinished in the words a page prints. A fixture test.

Every page of a built tree is read as a reader reads it (scripts, styles and comments out, tags
out, entities resolved) and each of these is counted. The count of record for each is zero:

  missing, undefined, NaN, null, None    a value the code did not have, printed as its own name
  $0, 0 pieces, 1 pieces                 a number that was never read, or a plural nobody checked
  a raw entity                           "&middot;" or "&amp;" printed as its letters (the separator
                                         itself, the middle dot the datelines use, is not a fault)
  a UTC stamp                            "UTC", "20:43Z", an ISO timestamp: every time is ET
  an em dash                             the house rule
  an internal note                       "read at build", TODO, FIXME, placeholder, a board item id

WHAT IS READ. The desk's own words on every page: the chrome, the cards, the stamps, the lists.
Authored story text is not the desk's chrome and is never edited by a scan: "after missing 14.5
months" is a sentence in a story. So on a story page (articles, Editions, the archive, storylines,
sections, hubs, the Record, the Wire) the story's own block is left out, and everywhere a
headline that links to a story is left out. The em dash and the UTC stamp are read in ALL text,
story text included: neither belongs anywhere on the site.

USAGE  python3 clean_canary.py TREE           counts, and exit 1 when any is not zero
       python3 clean_canary.py --url URL...   the same read on fetched pages (production)
"""

import html as _html
import os
import re
import sys

STORY = ("articles/", "edition/", "archive", "news", "bottom-line", "sections/", "coverage/", "keepers", "wire")
CHROME = {
    "missing": r"\bmissing\b",
    "undefined": r"\bundefined\b",
    "NaN": r"\bNaN\b",
    "null": r"\bnull\b",
    "None": r"\bNone\b",
    "$0": r"\$0(?![\d.,])",
    "0 pieces": r"\b0 pieces\b",
    "1 pieces": r"\b1 pieces\b",
    "a raw entity": r"&(?:middot|amp|nbsp|mdash|ndash|rsquo|lsquo|rdquo|ldquo|quot|#\d+|#x[0-9a-fA-F]+);",
    "an internal note": r"read at build|\bTODO\b|\bFIXME\b|\bplaceholder\b|\blorem ipsum\b|\b[SNJ]-\d+(?:\.\d+)?[a-z]?\b",
}
ANYWHERE = {
    # a time in UTC, not the letters: UTC is Chattanooga's abbreviation and prints on its cards
    "a UTC stamp": r"\b\d{1,2}:\d\d(?::\d\d)?\s?(?:[AP]M\s?)?(?:UTC|GMT)\b|\b(?:UTC|GMT)\s?[+-]\s?\d|\b\d{1,2}:\d\dZ\b"
                   r"|\b20\d\d-\d\d-\d\dT\d\d:\d\d",
    "an em dash": "\u2014",
}


def _strip(h):
    h = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", h)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    return re.sub(r"(?is)^.*?<body", "<body", h)


def _text(h):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h)))


def read(rel, page):
    """(chrome text, all text) for one page."""
    body = _strip(page)
    everything = _text(body)
    if rel.startswith(STORY):
        body = re.sub(r"(?is)<main\b.*?</main>", " ", body)
    body = re.sub(r"""(?is)<a\b[^>]*href=["']?(?:https://gocheckmysports\.com)?/(?:articles|edition|news|coverage)/[^>]*>.*?</a>""", " ", body)
    return _text(body), everything


def scan(pages):
    """`pages`: iterable of (rel, html). Returns ({name: count}, {name: [(rel, context)]}, pages read)."""
    counts = {k: 0 for k in list(CHROME) + list(ANYWHERE)}
    where = {k: [] for k in counts}
    n = 0
    for rel, page in pages:
        n += 1
        chrome, everything = read(rel, page)
        for group, text in ((CHROME, chrome), (ANYWHERE, everything)):
            for name, pat in group.items():
                for m in re.finditer(pat, text):
                    counts[name] += 1
                    if len(where[name]) < 5:
                        where[name].append((rel, text[max(0, m.start() - 50):m.end() + 40].strip()))
    return counts, where, n


def tree_pages(tree):
    for root, _d, fs in os.walk(tree):
        for f in sorted(fs):
            if f.endswith(".html"):
                p = os.path.join(root, f)
                yield os.path.relpath(p, tree).replace(os.sep, "/"), open(p, encoding="utf-8").read()


def unit():
    """The read itself, on three pages written here: the host re-quotes attributes (production
    serves href=/articles/x and href='/articles/x' where the build wrote href="/articles/x"), and
    a headline is a story's words under any of them."""
    f = []
    for q in ('"', "'", ""):
        page = f"<body><p>Roster</p><a class=hl href={q}/articles/2026-11-24-x{q}>Texans rule out a starter after missing practice</a></body>"
        c, _w, _n = scan([("teams/hou.html", page)])
        if c["missing"]:
            f.append(f"clean: a headline linked with href={q or 'unquoted'} is counted as the desk's own word")
    c, _w, _n = scan([("teams/hou.html", "<body><p>Record missing</p><a href=/teams/dal>Cowboys</a></body>")])
    if c["missing"] != 1:
        f.append(f"clean: the desk's own 'missing' on a team page is counted {c['missing']} time(s), not once")
    return f


def clean_canary(tree, label="the tree"):
    if not tree or not os.path.isdir(tree):
        return ["clean: no built tree to read"]
    counts, where, n = scan(tree_pages(tree))
    print(f"clean: {n} pages of {label} read; " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    f = []
    if n < 100:
        f.append(f"clean: only {n} pages were read")
    for k, v in counts.items():
        if v:
            rel, ctx = where[k][0]
            f.append(f"clean: {k} is printed {v} time(s) on {label}, first on /{rel}: ...{ctx}...")
    return f


if __name__ == "__main__":
    if "--url" in sys.argv:
        import urllib.request
        pages = []
        for u in sys.argv[sys.argv.index("--url") + 1:]:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "site-read"}), timeout=30) as r:
                rel = re.sub(r"^https?://[^/]+/", "", u) or "index.html"
                pages.append((rel, r.read().decode("utf-8", "replace")))
        counts, where, n = scan(pages)
        print(f"clean: {n} fetched page(s); " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        for k, v in where.items():
            for rel, ctx in v:
                print(f"  {k}: /{rel}: ...{ctx}...")
        sys.exit(1 if any(counts.values()) else 0)
    fs = clean_canary(sys.argv[1] if len(sys.argv) > 1 else "")
    for x in fs:
        print("::error::" + x)
    print("CLEAN CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
