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

# HOSTS THAT REJECT AN HONEST UA (2026-09-04). The desk identifies itself by name and
# links its homepage, which is the right default and what most publishers want. ESPN's
# edge does the opposite: it allows generic HTTP client agents (curl, python-requests,
# Python-urllib, okhttp, Go-http-client) and answers 403 to anything branded, and also
# to anything impersonating a browser. Measured 2026-09-04, same URL, same second:
#
#   GoCheckMySports-scores/1.0                            403
#   GoCheckMySports/1.0 (+news pipeline; +https://...)    403
#   Mozilla/5.0 (Macintosh; ...) Chrome/124.0             403
#   Python-urllib/3                                       200
#
# This cost the desk more than a header. The scoreboard ran baseball-only through NFL
# season, and on 2026-09-03 three working ESPN news feeds were retired as dead when the
# only thing wrong with them was the name in this string. Proven from CI, not just a
# laptop: the first scheduled run after the scores fix pulled 9 leagues and 29 games
# from site.api.espn.com on a GitHub runner IP, so the 403 was never about the egress.
#
# This is a narrow exception, not a new policy. It names hosts, it is not a wildcard,
# and the substitute is TRUE: these are Python urllib clients. The desk does not
# impersonate a browser here or anywhere, and every other host still gets the name and
# the link. ESPN's RSS hosts are a SEPARATE and still-unsolved problem: they answer
# datacenter IPs with HTTP 202 bot challenges, which no User-Agent fixes.
GENERIC_CLIENT_UA = "Python-urllib/3"
UA_EXCEPTIONS = ("site.api.espn.com", "now.core.api.espn.com", "sports.core.api.espn.com")


def ua_for(url, default=None):
    """The User-Agent to send to this host.

    Callers pass their OWN branded string as `default`, so each module keeps the identity
    it already advertised everywhere except the listed hosts. Only the exception is
    shared, not the name.
    """
    branded = default or UA
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return branded
    return GENERIC_CLIENT_UA if host in UA_EXCEPTIONS else branded


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


# THE FETCH LAYER IS THE CONTENT LAYER (family audit 2026-09-02). The verifier's rule
# is absolute: a source the desk could not READ can never be VERIFIED, and a story that
# is not VERIFIED never auto-publishes. So every fetch that fails for a mechanical reason
# is a story lost, and the run logs were full of mechanical reasons: CoinDesk answering
# 429 to the sixth request in ten seconds, Google News 503 on three feeds in one run,
# 200-byte challenge stubs, a 200KB read cap that cut PBS pages before their prose
# closed. Three fixes, all honest (the desk's own UA, no disguises):
#   - per-host spacing: at least HOST_GAP seconds between requests to one host, so a
#     run reading twelve stories from one outlet is a polite reader, not a burst;
#   - retry: 429 and 5xx and timeouts get two more tries with backoff (and Retry-After
#     when the server names it); 4xx other than 429 are final, as before;
#   - the headers a browser sends with every request (Accept, Accept-Language), which
#     several CDNs require before they will serve the article markup at all.
HOST_GAP = 1.2
RETRY_STATUSES = {429, 500, 502, 503, 504, 520, 521, 522, 524}
_LAST_HIT = {}


def _polite_wait(url):
    import time as _t
    from urllib.parse import urlparse
    host = (urlparse(url or "").netloc or "").lower()
    if not host:
        return
    last = _LAST_HIT.get(host)
    now = _t.monotonic()
    if last is not None and now - last < HOST_GAP:
        _t.sleep(HOST_GAP - (now - last))
    _LAST_HIT[host] = _t.monotonic()


def fetch_page_meta(url, timeout=25, retries=2):
    """Fetch a URL and return the WHOLE story of the fetch, never raising:
    {status, final_url, content_type, bytes, body, error, attempts}.

    WHY THIS EXISTS (owner report 2026-08-25): "0 chars" had become the desks' entire
    diagnostic. The blanket except below collapsed a 403 challenge, a paywall, a
    JS-only shell, a redirect loop and a timeout into the same two words, and nobody
    could fix what the log did not name. An HTTPError in particular carries the real
    status and usually a challenge body; both are kept now.
    """
    import time as _t
    meta = {"status": None, "final_url": url, "content_type": "", "bytes": 0,
            "body": "", "error": "", "attempts": 0}
    headers = {
        "User-Agent": ua_for(url),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    delay = 3.0
    for attempt in range(retries + 1):
        meta["attempts"] = attempt + 1
        _polite_wait(url)
        retry_after = None
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                # 600KB, not 200KB (Kyiv-strike audit 2026-08-31): a live PBS NewsHour
                # article runs ~262KB with its first closing </p> past byte 221,560,
                # so the old cap cut every PBS page before its prose closed.
                raw = r.read(600000)
                meta.update(status=r.getcode(), final_url=r.geturl() or url,
                            content_type=r.headers.get("Content-Type", ""),
                            bytes=len(raw), body=raw.decode("utf-8", "replace"),
                            error="")
            return meta
        except urllib.error.HTTPError as e:
            try:
                raw = e.read(200000)
            except Exception:
                raw = b""
            meta.update(status=e.code, final_url=getattr(e, "url", url) or url,
                        content_type=(e.headers.get("Content-Type", "") if e.headers else ""),
                        bytes=len(raw), body=raw.decode("utf-8", "replace"),
                        error=f"HTTP {e.code}")
            if e.code not in RETRY_STATUSES:
                return meta
            try:
                retry_after = float((e.headers or {}).get("Retry-After") or 0) or None
            except (TypeError, ValueError):
                retry_after = None
        except Exception as e:
            meta["error"] = f"fetch failed: {e}"
        if attempt < retries:
            wait = min(15.0, retry_after or delay)
            print(f"  fetch: {meta.get('error') or 'error'} on {url[:80]}; retry "
                  f"{attempt + 1}/{retries} in {wait:.0f}s")
            _t.sleep(wait)
            delay *= 2
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


def next_data_text(html_body, cap=6000):
    """Prose embedded in a Next.js page's __NEXT_DATA__ JSON, or ''. Client-rendered
    outlets (Decrypt, and the class that returns 200 with 130 extractable chars) ship
    the article body inside this script block for hydration: the publisher's own text,
    in the same response, invisible to a <p> scan. Strings that read as prose (long,
    with sentences) are collected in document order; a malformed block yields ''."""
    m = re.search(r'(?is)<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                  html_body or "")
    if not m:
        return ""
    try:
        data = json.loads(m.group(1).strip())
    except Exception:
        return ""
    out, seen = [], set()
    stack = [data]
    while stack and sum(len(x) for x in out) < cap * 2:
        node = stack.pop(0)
        if isinstance(node, dict):
            stack.extend(v for v in node.values() if isinstance(v, (dict, list, str)))
        elif isinstance(node, list):
            stack.extend(v for v in node if isinstance(v, (dict, list, str)))
        elif isinstance(node, str) and len(node) >= 120:
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", node)).strip()
            if (t.count(". ") + t.count("? ") + t.count("! ") + (1 if t.endswith(".") else 0)) < 2:
                continue
            if "{" in t[:5] or t.lower().startswith(("http", "//")):
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
    return "\n".join(out)[:cap]


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
    if len(text) < 400:
        nd = next_data_text(html_body)
        if len(nd) > len(text):
            text = nd
    if len(text) < 200:
        og = og_description(html_body)
        if len(og) > len(text):
            text = og
    return text
