#!/usr/bin/env python3
"""canonical_urls.py: S-1. One URL for every page, enforced at the edge.

THE FAULT. Netlify serves both /page and /page.html with a 200, and /index.html beside
/. Google indexes both forms and splits the impressions between them: on the Parents
desk the facility checker's 312 and 191 are the same page counted twice.

THE RULE. Every page 301s to the form THIS SITE already treats as canonical, which is
the form its sitemap and its <link rel="canonical"> use. That form is not the same
across the family and must not be assumed: measured on 21 September 2026, Parents, Pet,
Weather and Estate are .html, while Sports, Crypto and News are extensionless, and on
those three Google has already chosen the extensionless form for the pages it ranks.
Pointing a 301 away from the URL Google chose spends the signal that URL has earned.

WHY THE RULES ARE ENUMERATED AND NOT A SPLAT. The obvious rule is one line,
"/articles/*.html /articles/:splat 301!", and it was shipped on 12 September and has
never once fired: Netlify's _redirects does not honour a splat with a suffix after it.
Both forms answered 200 for nine days while the file said otherwise. So the rules are
written out, one per URL, from the sitemap at build, which also means a new page gets
its rule the day it exists.

Standard library only: this runs inside the build and inside the offline canary.
"""

import os
import re

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def sitemap_urls(publish_dir):
    """Every URL named by this site's sitemaps, following a sitemapindex."""
    seen, out = set(), []
    names = [n for n in sorted(os.listdir(publish_dir))
             if n.startswith("sitemap") and n.endswith(".xml")]
    for n in names:
        try:
            s = open(os.path.join(publish_dir, n), encoding="utf-8").read()
        except Exception:
            continue
        for u in _LOC.findall(s):
            if u.endswith(".xml"):
                continue
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def canonical_form(urls):
    """'html' or 'bare', decided by this site's own sitemap and nothing else.

    A site is not asked which it prefers; it is measured. The majority wins because a
    handful of odd entries (a feed, a hub that predates the convention) should not flip
    the whole site's direction.
    """
    pages = [u for u in urls if not u.rstrip("/").endswith(("/sitemap", ".xml"))]
    if not pages:
        return None
    html = sum(1 for u in pages if u.endswith(".html"))
    return "html" if html * 2 > len(pages) else "bare"


def _path(url, origin):
    p = url[len(origin):] if url.startswith(origin) else url
    if not p.startswith("/"):
        p = "/" + p
    return p


def rules(publish_dir, origin):
    """The 301 lines for this site, as text, plus the report numbers.

    Returns (text, stats). Every line sends the NON-canonical twin to the canonical
    form. A URL with no twin to redirect (a directory path, the home page) produces no
    rule rather than a rule that could loop.
    """
    urls = sitemap_urls(publish_dir)
    form = canonical_form(urls)
    lines, pairs = [], 0
    if form is None:
        return ("", {"form": None, "urls": 0, "rules": 0})

    for u in urls:
        p = _path(u, origin)
        if p in ("/", ""):
            continue
        if form == "html":
            if p.endswith(".html"):
                twin = p[:-5]
                if twin and twin != "/":
                    lines.append(f"{twin}  {p}  301!")
                    pairs += 1
        else:
            if not p.endswith(".html") and not p.endswith("/"):
                lines.append(f"{p}.html  {p}  301!")
                pairs += 1

    # /index.html is the home page's twin on every site, whichever form it uses.
    lines.append("/index.html  /  301!")
    return ("\n".join(lines) + "\n", {"form": form, "urls": len(urls), "rules": pairs + 1})


_HREF = re.compile(r'href="(/[^"#?]*)"')


def internal_link_offenders(publish_dir, origin, limit=40):
    """S-1's second half: nothing on the site should link through a redirect.

    Returns [(page, href)] for internal links pointing at the non-canonical twin of a
    page the sitemap names. Links to pages the sitemap does not carry are left alone:
    those are not redirected by the rules above and so are not links through a redirect.
    """
    urls = sitemap_urls(publish_dir)
    form = canonical_form(urls)
    if form is None:
        return []
    canon = {_path(u, origin) for u in urls}
    bad_targets = set()
    for p in canon:
        if form == "html" and p.endswith(".html"):
            bad_targets.add(p[:-5])
        elif form == "bare" and not p.endswith(".html"):
            bad_targets.add(p + ".html")
    bad_targets.discard("")
    bad_targets.discard("/")

    out = []
    for root, _dirs, files in os.walk(publish_dir):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            fp = os.path.join(root, fn)
            rel = "/" + os.path.relpath(fp, publish_dir)
            try:
                s = open(fp, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            for href in set(_HREF.findall(s)):
                if href in bad_targets:
                    out.append((rel, href))
                    if len(out) >= limit:
                        return out
    return out
