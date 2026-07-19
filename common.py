#!/usr/bin/env python3
"""common.py: shared helpers for the Crypto Cronkite pipeline stages."""

import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
PROMPTS = os.path.join(HERE, "prompts")
CONFIG = os.path.join(HERE, "config.json")
UA = "CryptoCronkite/1.0 (+news pipeline)"


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


# ---- Whale Alert public archive ------------------------------------------------
# Whale Alert's old keyed v1 REST API was retired (replacements are a $29.95/mo WebSocket
# and a $699/mo Enterprise API). Instead we use their FREE public archive of every alert
# they post to social media: a gzipped, NEWEST-FIRST JSON array refreshed continuously,
# which Whale Alert explicitly offers for models/algorithms/research. No key. Because it
# is newest-first, the loader streams the gzip and stops at the first alert older than
# the window, so only the first few tens of KB of a ~600MB (decompressed) file are read.
# See DEVIATIONS D7.

WHALE_ARCHIVE_URL = "https://whale-alert.io/whale-alerts-archive.json.gzip"

# The archive attributes owners by NAME only (no owner_type field), so exchange
# classification is a curated name list (normalized substring match). Deliberately not
# listed: DeFi protocols (aave...), custodians (ceffu), issuer treasuries. This is a
# heuristic and the site says so.
KNOWN_EXCHANGES = (
    "binance", "coinbase", "okex", "okx", "kraken", "bitfinex", "huobi", "htx",
    "kucoin", "gate.io", "bybit", "bitget", "gemini", "bitstamp", "poloniex",
    "crypto.com", "cryptocom", "upbit", "bithumb", "mexc", "deribit", "bitmex",
    "korbit", "coincheck", "bitflyer", "coinone", "bittrex", "bitso", "luno",
)


def _whale_owner(name):
    n = (name or "").strip().lower()
    is_exchange = any(x in n for x in KNOWN_EXCHANGES)
    return {"owner": name or "unknown wallet",
            "owner_type": "exchange" if is_exchange else "unknown"}


def _whale_alert_to_txns(alert):
    """Map one archive alert to the pipeline's canonical transaction dicts (one per amount)."""
    tx_hash = ""
    for u in alert.get("urls", []) or []:
        m = re.search(r"/transaction/[^/]+/([0-9a-zA-Z]+)", u)
        if m:
            tx_hash = m.group(1)
            break
    frm = _whale_owner(alert.get("from"))
    to = _whale_owner(alert.get("to"))
    txns = []
    for amt in alert.get("amounts", []) or []:
        txns.append({
            "timestamp": alert.get("timestamp", 0),
            "blockchain": alert.get("blockchain", ""),
            "transaction_type": alert.get("transaction_type", "transfer"),
            "hash": tx_hash,
            "symbol": amt.get("symbol") or "?",
            "amount": amt.get("amount", 0),
            "amount_usd": amt.get("value_usd", 0),
            "from": frm,
            "to": to,
            "text": alert.get("text", ""),
        })
    return txns


def _next_json_object(buf, start=0):
    """Return (parsed_object, end_index) for the first complete top-level {...} in buf,
    or (None, start_of_incomplete_object) if the buffer ends mid-object."""
    begin = buf.find("{", start)
    if begin == -1:
        return None, len(buf)
    depth = 0
    in_str = False
    esc = False
    for i in range(begin, len(buf)):
        c = buf[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(buf[begin:i + 1]), i + 1
                    except Exception:
                        return None, i + 1  # malformed object: skip past it
    return None, begin  # incomplete: caller should read more and retry from `begin`


def whale_archive_transactions(window_hours, archive_url=WHALE_ARCHIVE_URL,
                               max_decompressed_bytes=8_000_000, timeout=60):
    """Stream the newest slice of the Whale Alert public archive and return canonical
    transaction dicts for the last `window_hours`. Raises on network failure (callers
    decide whether that is fail-open or fail-closed for their stage)."""
    import gzip
    import time
    cutoff = time.time() - window_hours * 3600
    req = urllib.request.Request(archive_url, headers={"User-Agent": UA})
    txns = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        gz = gzip.GzipFile(fileobj=resp)
        buf = ""
        total = 0
        pos = 0
        while True:
            chunk = gz.read(65536)
            if not chunk:
                break
            total += len(chunk)
            buf = buf[pos:] + chunk.decode("utf-8", "replace")
            pos = 0
            done = False
            while True:
                obj, end = _next_json_object(buf, pos)
                if obj is None and end >= len(buf):
                    pos = len(buf)
                    break
                if obj is None:  # incomplete object at `end`; keep tail, read more
                    pos = end
                    break
                pos = end
                if (obj.get("timestamp") or 0) < cutoff:
                    done = True  # newest-first: everything after this is older
                    break
                txns.extend(_whale_alert_to_txns(obj))
            if done or total > max_decompressed_bytes:
                break
    return txns
