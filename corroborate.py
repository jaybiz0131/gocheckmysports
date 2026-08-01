#!/usr/bin/env python3
"""
corroborate.py: which OTHER outlets independently reported this same development?

THE CHASSIS COPY (identical in gocheckmynews and gocheckmysports).

WHY THIS EXISTS. The desk sells verification "against outlets deliberately spread across
the political spectrum", and most stories published citing one source. A 20-of-20 hand
sample on 2026-08-01 showed every single-source story DID have other outlets on the same
development, so the shortfall was never a sourcing reality, it was a matching failure.
Two attempts to close it inside the intake failed and were measured, not assumed:
headline entities reached 6% and a targeted post-ranking scan of the whole intake added
exactly zero, because the shared specifics are not reliably inside a 400-character RSS
summary. Fetching article text was rejected too: the outlets most worth corroborating
against (NYT, WSJ, Guardian) answer runner IPs with 403, which is why this codebase
already carries a JSON-LD fallback and a Guardian key.

What works is the method that PROVED the gap: query Google News for the story's own
distinctive terms and read which outlets came back. Keyless, one query per ranked story.

THE HONESTY RULE. Google News item links are google.com redirects, not article URLs, so
these are NEVER presented as the story's sources and never enter source_urls. They are
recorded as "also reported by", which is a claim about coverage existing, not a citation.

A TOPIC MATCH IS NOT AN EVENT MATCH. "FIFA World Cup" returns 37 outlets covering
anything FIFA. Every returned headline is therefore checked against ours for shared
distinctive entities, and only outlets whose own headline names the same development
are kept. That check is the difference between an honest signal and a fabricated one.
"""

import re
import urllib.parse
import urllib.request

UA = "GoCheckMyNews-corroboration/1.0"
GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

_GENERIC = {
    "the", "and", "for", "with", "from", "new", "news", "says", "said", "after", "over",
    "into", "amid", "his", "her", "its", "why", "how", "what", "when", "who", "will",
    "this", "that",
}

# Entities so common across UNRELATED stories that sharing them proves nothing. Measured
# 2026-08-01: without this, "Ninth Circuit Blocks Trump Mandatory Detention Rule" matched
# four different cases (a climate lawsuit, a college-funding block, and a FOURTH Circuit
# ruling) purely on {ninth, circuit, trump}. An institution is a venue, not an event.
_INSTITUTIONAL = {
    "trump", "biden", "circuit", "court", "supreme", "appeals", "federal", "district",
    "justice", "department", "senate", "house", "congress", "administration", "white",
    "state", "states", "united", "washington", "president", "government", "national",
    "committee", "commission", "agency", "office", "secretary", "judge", "attorney",
    "america", "american", "republican", "democrat", "democrats", "republicans",
    "ninth", "fifth", "fourth", "second", "third", "eleventh", "county", "city",
}


def _entities(text):
    """Distinctive tokens: capitalised words (skipping the sentence-initial one) and
    numbers. Same shape as the intake matcher so the two agree on what an entity is."""
    ents = set()
    for m in re.findall(r"\b\d[\d,.]*\b", text or ""):
        n = m.rstrip(".,").replace(",", "")
        if len(n) >= 2:
            ents.add(n)
    # NOTE: position 0 is NOT skipped here. The intake matcher skips it because it reads
    # sentence-cased prose, where the first word is capitalised by grammar. This reads
    # HEADLINES, where the first word is usually the story's main actor: skipping it
    # dropped "FIFA" from "FIFA cancels plan..." and "Anthropic" from "Anthropic's Claude
    # AI...", losing each story its single most distinctive entity.
    words = re.findall(r"[A-Za-z][A-Za-z'\-]+", text or "")
    for w in words:
        if len(w) < 3:
            continue
        if w[0].isupper() and w.lower() not in _GENERIC and w.lower() not in _INSTITUTIONAL:
            ents.add(w.lower())
    return ents


def _query_for(title):
    """The story's most distinctive proper nouns, which is what a person would search."""
    caps = [w for w in re.findall(r"[A-Z][a-zA-Z'\-]{2,}", title or "")
            if w.lower() not in _GENERIC]
    return " ".join(caps[:4]) if len(caps) >= 2 else " ".join((title or "").split()[:6])


def also_reported_by(title, our_source="", min_shared=3, max_outlets=6, timeout=20,
                     fetch=None):
    """[(outlet, their_headline), ...] for outlets that reported the SAME development.

    min_shared is the event-match bar: the outlet's own headline must share at least this
    many distinctive entities with ours, so a topic-level hit cannot be counted as
    corroboration. `fetch` is injectable so the canary can exercise this offline."""
    q = _query_for(title)
    if not q.strip():
        return []
    url = GNEWS.format(q=urllib.parse.quote(q))
    try:
        if fetch is not None:
            raw = fetch(url)
        else:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "ignore")
    except Exception:
        return []          # fail soft: corroboration is additive, never load-bearing
    mine = _entities(title)
    ours = (our_source or "").lower()
    out, seen = [], set()
    for block in re.findall(r"<item>(.*?)</item>", raw, re.S):
        t = re.search(r"<title>(?:<!\[CDATA\[)?([^<\]]+)", block)
        s = re.search(r"<source[^>]*>([^<]+)</source>", block)
        if not (t and s):
            continue
        headline, outlet = t.group(1).strip(), s.group(1).strip()
        # feeds publish their full masthead ("ABC News - Breaking News, Latest News and
        # Videos"); readers want the outlet, not the tagline
        outlet = re.split(r"\s+[-|\u2013]\s+", outlet)[0].strip().rstrip(",")
        key = outlet.lower()
        if key in seen or not outlet:
            continue
        if ours and (key in ours or ours in key):
            continue          # our own outlet is not corroboration of itself
        if len(mine & _entities(headline)) < min_shared:
            continue          # topic match, not event match
        # Google News carries scrapers and aggregators alongside real outlets, and a desk
        # that sells credibility should not answer "who else reported this" with
        # "en.bloomingbit.io". Outlet names that are bare domains are dropped, EXCEPT .gov
        # and .mil: an official release (centcom.mil on the Iran strikes) is the strongest
        # corroboration available, not the weakest.
        if "." in outlet and " " not in outlet and not outlet.lower().endswith((".gov", ".mil")):
            continue
        seen.add(key)
        out.append((outlet, headline))
        if len(out) >= max_outlets:
            break
    return out
