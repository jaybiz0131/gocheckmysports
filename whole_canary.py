#!/usr/bin/env python3
"""whole_canary.py: S-DONE point 5, the built site holds together. A fixture test on a built tree.

  links      every internal href and src on every page resolves to a file the build wrote, by the
             rules the host serves by (the file, the file with .html, a directory's index.html, a
             line of _redirects). The count is printed, never only a pass.
  heads      every page has one <title> and one description, both with text, and one canonical
             link in its head; the 404 page alone has no canonical (any missing URL answers with
             it, so it has no address of its own).
  sitemaps   every <loc> in the three sitemaps is a page the build wrote, once, and none of them
             is noindexed; the index names exactly the sitemaps that exist.

USAGE  python3 whole_canary.py TREE
"""

import html as _html
import os
import re
import sys
from urllib.parse import urlsplit, unquote

ORIGIN = "https://gocheckmysports.com"
NO_CANONICAL = ("/404.html",)
SITEMAPS = ("sitemap-priority.xml", "sitemap-archive.xml", "news-sitemap.xml")


def _files(tree):
    out = set()
    for root, _d, fs in os.walk(tree):
        for f in fs:
            out.add("/" + os.path.relpath(os.path.join(root, f), tree).replace(os.sep, "/"))
    return out


def _redirects(tree):
    """[(from, to, status)] from _redirects. The catch-all that answers a missing URL with the 404
    page is not a rule a link may lean on, so a 404 line is left out."""
    out = []
    try:
        for ln in open(os.path.join(tree, "_redirects"), encoding="utf-8"):
            p = ln.split()
            if len(p) < 2 or ln.lstrip().startswith("#"):
                continue
            status = (p[2] if len(p) > 2 else "301").rstrip("!")
            if status == "404":
                continue
            out.append((p[0], p[1], status))
    except OSError:
        pass
    return out


def resolver(tree):
    files, red = _files(tree), _redirects(tree)
    exact = {a: b for a, b, _s in red if "*" not in a}
    stars = [(re.compile("^" + re.escape(a).replace(r"\*", "(.*)") + "$"), b) for a, b, _s in red if "*" in a]

    def served(path):
        if path in files:
            return True
        if path.endswith("/"):
            return (path + "index.html") in files
        return (path + ".html") in files or (path + "/index.html") in files

    def resolves(path):
        """True when the host answers `path` with a page: a file, or a redirect that lands on one."""
        path = unquote(path)
        if served(path):
            return True
        if path in exact:
            return served(exact[path])
        for rx, to in stars:
            m = rx.match(path)
            if m and served(to.replace(":splat", m.group(1))):
                return True
        return False

    def target(path):
        """The file a path serves, or None."""
        path = unquote(path)
        for c in (path, path + ".html", path.rstrip("/") + "/index.html"):
            if c in files and not c.endswith("/"):
                return c
        return None
    return files, resolves, target


def _head(page):
    m = re.search(r"(?is)<head\b.*?</head>", page)
    return m.group(0) if m else ""


def whole_canary(tree):
    if not tree or not os.path.isdir(tree):
        return ["whole: no built tree to read"]
    files, resolves, target = resolver(tree)
    pages = sorted(f for f in files if f.endswith(".html"))
    f, links, bad, noindex = [], 0, {}, set()
    for rel in pages:
        page = open(os.path.join(tree, rel.lstrip("/")), encoding="utf-8").read()
        body = re.sub(r"(?is)<script\b.*?</script>", "", page)
        # an attribute named href or src, not one that ends in it (data-src is a script's own business)
        for m in re.finditer(r'(?<![\w-])(?:href|src)="([^"]+)"', body):
            u = _html.unescape(m.group(1))
            if u.startswith(ORIGIN):
                u = urlsplit(u).path or "/"
            elif re.match(r"^(?:[a-z][a-z0-9+.\-]*:|//|#)", u):
                continue
            p = urlsplit(u).path
            if not p:
                continue
            if not p.startswith("/"):
                p = os.path.normpath(os.path.join(os.path.dirname(rel), p))
            links += 1
            if not resolves(p):
                bad.setdefault(p, []).append(rel)
        head = _head(page)
        if re.search(r'<meta name="robots" content="[^"]*noindex', head):
            noindex.add(rel)
        can = re.findall(r'<link rel="canonical" href="([^"]*)"', head)
        ttl = re.findall(r"(?is)<title>(.*?)</title>", head)
        dsc = re.findall(r'<meta name="description" content="([^"]*)"', head)
        if rel in NO_CANONICAL:
            if can:
                f.append(f"whole: {rel} carries a canonical; the 404 page has no address of its own")
        elif len(can) != 1 or not can[0].startswith(ORIGIN + "/"):
            f.append(f"whole: {rel} carries {len(can)} canonical link(s)" + (f" ({can[0]!r})" if len(can) == 1 else ""))
        elif not resolves(urlsplit(can[0]).path):
            f.append(f"whole: {rel} names a canonical that is not a page ({can[0]})")
        if len(ttl) != 1 or not ttl[0].strip():
            f.append(f"whole: {rel} carries {len(ttl)} title(s) with text")
        if len(dsc) != 1 or not dsc[0].strip():
            f.append(f"whole: {rel} carries {len(dsc)} description(s) with text")
    for p, froms in sorted(bad.items())[:10]:
        f.append(f"whole: {p} does not resolve; linked from {froms[0]}" + (f" and {len(froms) - 1} more" if len(froms) > 1 else ""))
    if len(bad) > 10:
        f.append(f"whole: and {len(bad) - 10} more paths that do not resolve")
    # sitemaps
    locs = []
    for sm in SITEMAPS:
        try:
            got = re.findall(r"<loc>([^<]+)</loc>", open(os.path.join(tree, sm), encoding="utf-8").read())
        except OSError:
            f.append(f"whole: {sm} is not in the tree")
            continue
        locs += [(sm, l) for l in got]
    try:
        idx = re.findall(r"<loc>([^<]+)</loc>", open(os.path.join(tree, "sitemap.xml"), encoding="utf-8").read())
    except OSError:
        idx = []
        f.append("whole: sitemap.xml is not in the tree")
    if sorted(urlsplit(u).path.lstrip("/") for u in idx) != sorted(SITEMAPS):
        f.append(f"whole: sitemap.xml names {sorted(urlsplit(u).path.lstrip('/') for u in idx)}, not the three sitemaps")
    seen = set()
    for sm, l in locs:
        if not l.startswith(ORIGIN + "/") and l != ORIGIN + "/":
            f.append(f"whole: {sm} lists {l}, not an address on this site")
            continue
        t = target(urlsplit(l).path or "/")
        if t is None:
            f.append(f"whole: {sm} lists {l}, which the build did not write")
        elif t in noindex:
            f.append(f"whole: {sm} lists {l}, which is noindexed")
        if l in seen:
            f.append(f"whole: {l} is listed twice in the sitemaps")
        seen.add(l)
    print(f"whole: {len(pages)} pages, {links} internal links, {len(bad)} that do not resolve; "
          f"{len(locs)} sitemap entries, {len(noindex)} noindexed page(s) outside them")
    if len(pages) < 100 or links < 1000:
        f.append(f"whole: only {len(pages)} pages and {links} links were read")
    return f[:25] + ([f"whole: and {len(f) - 25} more"] if len(f) > 25 else [])


if __name__ == "__main__":
    fs = whole_canary(sys.argv[1] if len(sys.argv) > 1 else "")
    for x in fs:
        print("::error::" + x)
    print("WHOLE CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
