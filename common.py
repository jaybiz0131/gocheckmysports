#!/usr/bin/env python3
"""common.py: shared helpers for the GoCheckMySports pipeline stages."""

import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
PROMPTS = os.path.join(HERE, "prompts")
CONFIG = os.path.join(HERE, "config.json")
UA = "GoCheckMySports/1.0 (+news pipeline; +https://gocheckmysports.com)"


def gh(level, msg):
    """GitHub Actions annotation, also readable in a plain terminal."""
    print(f"::{level}::{msg}")


def load_config():
    return json.load(open(CONFIG, encoding="utf-8"))


def load_prompt(name, **subs):
    text = open(os.path.join(PROMPTS, name), encoding="utf-8").read()
    for k, v in subs.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def read_out(name):
    return json.load(open(os.path.join(OUT_DIR, name), encoding="utf-8"))


def write_out(name, obj):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    json.dump(obj, open(path, "w", encoding="utf-8"), indent=2)
    return path


def fetch_text(url, timeout=25):
    """Fetch a URL and return (http_status, plain_text_excerpt). Never raises; on failure
    returns (None, error string) so the verifier can treat unreachable as unconfirmed."""
    code, body = fetch_page(url, timeout=timeout)
    if code is None:
        return code, body
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
    return code, text


def fetch_page_meta(url, timeout=25):
    """Fetch a URL and return the WHOLE story of the fetch, never raising:
    {status, final_url, content_type, bytes, body, error}.

    WHY THIS EXISTS (owner report 2026-08-25): "0 chars" had become the desks' entire
    diagnostic. The blanket except below collapsed a 403 challenge, a paywall, a
    JS-only shell, a redirect loop and a timeout into the same two words, and nobody
    could fix what the log did not name. An HTTPError in particular carries the real
    status and usually a challenge body; both are kept now.
    """
    meta = {"status": None, "final_url": url, "content_type": "", "bytes": 0,
            "body": "", "error": ""}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(200000)
            meta.update(status=r.getcode(), final_url=r.geturl() or url,
                        content_type=r.headers.get("Content-Type", ""),
                        bytes=len(raw), body=raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            raw = e.read(200000)
        except Exception:
            raw = b""
        meta.update(status=e.code, final_url=getattr(e, "url", url) or url,
                    content_type=(e.headers.get("Content-Type", "") if e.headers else ""),
                    bytes=len(raw), body=raw.decode("utf-8", "replace"),
                    error=f"HTTP {e.code}")
    except Exception as e:
        meta["error"] = f"fetch failed: {e}"
    return meta


def fetch_page(url, timeout=25):
    """Fetch a URL and return (http_status, raw_html). Never raises; on failure returns
    (None, error string). Thin wrapper over fetch_page_meta, kept for every caller."""
    m = fetch_page_meta(url, timeout=timeout)
    if m["status"] is not None:
        return m["status"], m["body"] or m["error"]
    return None, m["error"]


def fetch_article_text(url, timeout=25):
    """fetch_page + extract_article_text with a publisher-API fallback. ESPN article
    pages are client-rendered shells (the HTML carries ~0 extractable prose), but the
    body is served by ESPN's own public content API, the same call their page makes
    in the browser. Honest fetch: their published endpoint, our UA, no disguises.
    Returns (http_status, text); on total failure (None, error string)."""
    code, page = fetch_page(url, timeout=timeout)
    text = extract_article_text(page) if code == 200 else ""
    if len(text) < 400:
        m = re.search(r"espn\.com/.*?/id/(\d+)", url or "")
        if m:
            acode, abody = fetch_page(
                "https://now.core.api.espn.com/v1/sports/news/" + m.group(1),
                timeout=timeout)
            if acode == 200:
                try:
                    arts = json.loads(abody).get("headlines") or []
                    story = (arts[0].get("story") or "") if arts else ""
                except Exception:
                    story = ""
                api_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", story)).strip()
                if len(api_text) > len(text):
                    return 200, api_text
    if code != 200:
        return code, page if isinstance(page, str) else ""
    return code, text


def publisher_of(url):
    """The registrable domain behind a URL, used as PUBLISHER IDENTITY. A desk can carry
    several feeds from one publisher (ESPN NFL, ESPN MLB, ESPN Top Lines; BBC News and BBC
    World), and counting those as separate sources would claim corroboration the desk does
    not have. Measured 2026-07-31: 64% of apparently corroborated clusters were one
    publisher wearing two feed names. Independence is judged by this, never by feed name."""
    from urllib.parse import urlparse
    host = (urlparse(url or "").netloc or "").lower()
    host = host[4:] if host.startswith("www.") else host
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) > 2 and parts[-2] in ("co", "com", "org", "net", "gov", "ac"):
        return ".".join(parts[-3:])   # bbc.co.uk
    return ".".join(parts[-2:])


def distinct_publishers(refs):
    """How many INDEPENDENT publishers back a set of source references. Accepts URLs
    (preferred: the domain is the publisher) and bare feed/outlet names (falls back to the
    normalized name), so callers holding either shape get the same independence semantics.
    Empty entries are ignored."""
    out = set()
    for r in refs or []:
        r = (r or "").strip()
        if not r:
            continue
        dom = publisher_of(r) if "//" in r or r.startswith("www.") else ""
        out.add(dom or r.lower())
    return len(out)



def ldjson_article_body(html_body):
    """The longest articleBody in any <script type="application/ld+json"> block, or ''.
    Most news CMSes embed it server-side even when the visible HTML is a client-rendered
    shell (ported from the news desk 2026-08-25). A malformed block is skipped."""
    best = ""
    for m in re.finditer(r"(?is)<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
                         html_body or ""):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                b = node.get("articleBody")
                if isinstance(b, str) and len(b) > len(best):
                    best = b
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)
    return re.sub(r"\s+", " ", best).strip()


def og_description(html_body):
    """The page's own og:description / twitter:description, or ''. The publisher's own
    one-line summary of their own story, served in the same response (owner audit
    2026-08-25)."""
    import html as _h
    for pat in (r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{40,})',
                r'<meta[^>]+content=["\']([^"\']{40,})["\'][^>]+property=["\']og:description["\']',
                r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\']([^"\']{40,})'):
        m = re.search(pat, html_body or "", re.I)
        if m:
            return _h.unescape(m.group(1)).strip()
    return ""


def extract_article_text(html_body, cap=6000):
    """Readability-lite article extraction, stdlib only. Prefers the <article> block if the
    page has one, else collects <p> contents; strips tags/scripts, unescapes entities, and
    drops short boilerplate lines (nav crumbs, cookie banners) so the researcher gets prose,
    not nav-soup. Returns up to `cap` chars."""
    import html as html_mod
    if not html_body:
        return ""
    body = re.sub(r"(?is)<(script|style|noscript|nav|header|footer|aside)[^>]*>.*?</\1>",
                  " ", html_body)
    m = re.search(r"(?is)<article[^>]*>(.*?)</article>", body)
    scope = m.group(1) if m else body
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", scope)
    if not paras and m is None:
        # No <p> tags at all (some CMSes): fall back to the naive strip of the whole page.
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        # PROSE HAS SENTENCES (owner report 2026-08-25): a JS/CSS shell stripped of tags
        # can yield thousands of chars of selector soup, which then defeats every
        # downstream length gate as if it were source text. Junk in means invented
        # stories out, so a long no-<p> extraction must show minimal sentence density
        # or it is not prose and returns empty (which the desk handles honestly).
        if len(text) > 400 and (text.count(". ") + text.count("! ") + text.count("? ")
                                ) < max(3, len(text) // 400):
            text = ""
        return _thin_fallbacks(text, html_body)[:cap]
    out = []
    for p in paras:
        t = html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p)).strip())
        if len(t) >= 40:  # boilerplate lines (menus, "Share this", bylines) run shorter
            out.append(t)
    return _thin_fallbacks("\n".join(out), html_body)[:cap]


def _thin_fallbacks(text, html_body):
    """Server-side text the markup pass missed: the page's own JSON-LD articleBody, then
    its og:description. Both are the publisher's own words in the same response we already
    fetched (owner audit 2026-08-25: MLB.com and CBSSports.com returned 200 with the full
    story present and this extractor read ZERO chars, so the desk asserted what a readable
    source 'did not contain'). A short honest fragment beats a confident false negative."""
    if len(text) < 400:
        ld = ldjson_article_body(html_body)
        if len(ld) > len(text):
            text = ld
    if len(text) < 200:
        og = og_description(html_body)
        if len(og) > len(text):
            text = og
    return text
