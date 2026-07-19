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
UA = "GoCheckMySports/1.0 (+news pipeline)"


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


def fetch_page(url, timeout=25):
    """Fetch a URL and return (http_status, raw_html). Never raises; on failure returns
    (None, error string)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.getcode()
            body = r.read(200000).decode("utf-8", "replace")
        return code, body
    except Exception as e:
        return None, f"fetch failed: {e}"


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
        return text[:cap]
    out = []
    for p in paras:
        t = html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p)).strip())
        if len(t) >= 40:  # boilerplate lines (menus, "Share this", bylines) run shorter
            out.append(t)
    return "\n".join(out)[:cap]
