#!/usr/bin/env python3
"""
dedupe.py: does the desk already have this story?

THE CHASSIS COPY. This file is identical in gocheckmycrypto, gocheckmynews and
gocheckmysports. The three desks are separate repositories with no shared package, so the
mechanism for shared logic is a synchronised module plus a canary in each repo running the
same behavioural fixtures. If the three ever disagree, those fixtures fail.

WHY IT WAS EXTRACTED (2026-07-31). The crypto desk published one Treasury designation THREE
times in a single day. The diagnosis found four defects, none in the event matcher itself:

  1. The rehash gate used raw headline word overlap (>=0.5) rather than the event matcher it
     sat behind. The third telling scored 0.44 and 0.38 and sailed through.
  2. Novelty was measured against min(matches), the OLDEST match, which was an unrelated
     18-day-old market story sharing only {hormuz, strait} and carrying no published_utc, so
     it always sorted first. Every duplicate looked novel beside it.
  3. The gate judged the EDITOR's ranked headline while the reader gets the WRITER's rewrite.
     The 18:40 duplicate scored 0.44 as judged and 0.75 as shipped.
  4. _signature() harvests capitalised tokens as proper nouns, and headlines are Title Case,
     so "US Sanctions Iranian Marine Insurers Accepting Bitcoin for Strait of Hormuz Passage"
     yields accepting, insurers, marine, passage, sanctions. Rewording looked like reporting.

Meanwhile the news desks had no event matcher at all, only a 70% title-word test, which that
same third telling also cleared. Hence one module for all three.

THE RULE. A candidate is a REHASH unless it asserts at least NOVELTY_MIN distinctive facts
appearing nowhere in the desk's existing coverage of the same event. Novelty is read from the
candidate's sentence-cased prose (never its headline) against everything the published
stories said (headline, key fact and body). An update anchors to the EARLIEST match so
"develops our earlier reporting" points at the first take; a rehash names the NEAREST.
"""

import datetime
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def is_coverage(d):
    """False for anything that is not coverage of an event happening.

    Two kinds get excluded, for the same reason: neither reports an event, so neither can
    be the thing a later story is duplicating.

    EDITIONS (wrap-) synthesise the day's own published stories.

    PREVIEWS (the Week Ahead) announce that something WILL happen. This one was not
    theoretical. The Week Ahead published 2026-07-27 listed "Wednesday, July 29: FOMC rate
    decision", and same_event() correctly matched that against the real story when the Fed
    actually decided. The FOMC story was ranked #1, VERIFIED against federalreserve.gov,
    and APPROVED, then held as already-published, so the desk missed the week's biggest
    event because it had told readers to expect it. Every event the Week Ahead flags was
    pre-suppressed for the following five days: the better the preview, the worse the
    blackout."""
    if str(d.get("id", "")).startswith("wrap-"):
        return False
    if (str(d.get("id", "")).startswith("week-ahead-")
            or (d.get("category") or "").strip().lower() == "week ahead"):
        return False
    return True


def _words(s):
    return set(re.findall(r"[a-z]{4,}", (s or "").lower()))


# Ubiquitous crypto vocabulary: shared between UNRELATED stories, so it is not an event
# fingerprint. Two stories both saying "Bitcoin"/"SEC"/"ETF" are not the same story.
_UBIQUITOUS = {
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency", "sec", "cftc", "etf",
    "token", "tokens", "blockchain", "defi", "stablecoin", "stablecoins", "market",
    "markets", "price", "prices", "exchange", "exchanges", "million", "billion", "billions",
    "trillion", "the", "and", "for", "with", "over", "into", "from", "u.s", "us", "new",
    "law", "bill", "act", "vote", "firm", "firms", "coin", "network", "protocol",
}


def _signature(*texts):
    """Event fingerprint: the DISTINCTIVE tokens that name a specific event. Proper nouns
    (Hut, IREN, Maruwa, Worldcoin, Grayscale, Parliament) and numbers/amounts (2,300,
    3,800, 1.65, 110), minus the ubiquitous crypto vocabulary two unrelated stories share.
    Two stories about the SAME event share these even when the headline words differ:
    'Amazon Japan supplier to pay 2,300 contractors' and 'AZ-COM Maruwa to pay 2,300
    partners' share {amazon, japan, 2300} though word-overlap is only 0.43."""
    blob = " ".join(t or "" for t in texts)
    proper = re.findall(r"\b([A-Z][A-Za-z0-9.\-]{2,}|[A-Z]{2,})\b", blob)
    nums = re.findall(r"\b\d[\d,\.]*\b", blob)
    sig = {p.lower().rstrip(".").replace(",", "") for p in proper}
    sig |= {n.replace(",", "").rstrip(".") for n in nums}
    return {t for t in sig if t and t not in _UBIQUITOUS and len(t) >= 2}


def same_event(a_title, a_kf, b_title, b_kf, word_thr=0.7, sig_thr=2):
    """True if two stories cover the same event: high headline-word overlap OR >= sig_thr
    shared distinctive fingerprint tokens (the news-dedup signal word overlap misses)."""
    wa, wb = _words(a_title), _words(b_title)
    if wa and wb and len(wa & wb) / min(len(wa), len(wb)) >= word_thr:
        return True
    return len(_signature(a_title, a_kf) & _signature(b_title, b_kf)) >= sig_thr


# Outlet / wire names: they appear as proper nouns in the signature but are not part of the
# EVENT, so a new outlet on the same story is not a new development.
_OUTLETS = {
    "coindesk", "cointelegraph", "decrypt", "theblock", "block", "defiant", "thedefiant",
    "blockworks", "blockonomi", "beacon", "reuters", "bloomberg", "forbes", "fortune",
    "cnbc", "messari", "nansen", "arkham", "lookonchain", "protos", "beincrypto",
    "cryptoslate", "dlnews", "axios", "wsj", "techcrunch", "coinshares",
}


def _headline_overlap(a_title, b_title):
    wa, wb = _words(a_title), _words(b_title)
    return len(wa & wb) / min(len(wa), len(wb)) if wa and wb else 0.0


# How many distinctive facts a candidate must add before it counts as a development rather
# than another telling of the same story. Two, so a single reworded number cannot promote a
# rehash, and a real follow-up (a new actor, a new amount, a new mechanism) clears it easily.
NOVELTY_MIN = 2


def _claim_signature(d):
    """What a candidate ASSERTS, read from sentence-cased prose only.

    Never the headline. _signature() harvests capitalised tokens as proper nouns, and
    headlines are Title Case, so every word in one looks distinctive: "US Sanctions Iranian
    Marine Insurers Accepting Bitcoin for Strait of Hormuz Passage" yields accepting,
    insurers, marine, passage, sanctions. Rewording a headline then looks like new
    reporting, which is exactly how the same Treasury designation published three times on
    2026-07-30."""
    return _signature(d.get("key_fact", ""))


def _covered_signature(d):
    """Everything a published story already told the reader: headline, key fact and body.

    Deliberately wider than _claim_signature. The question a rehash check asks is "does this
    candidate say anything the reader has not already been told", so the reference side
    should be generous and the candidate side strict."""
    body = d.get("body") or []
    return _signature(d.get("title", ""), d.get("key_fact", ""),
                      *[str(b) for b in body])


def _corpus_on_disk():
    """Every published story the desk has on disk."""
    out = []
    for p in glob.glob(os.path.join(HERE, "site", "content", "*.json")):
        try:
            out.append(json.load(open(p, encoding="utf-8")))
        except Exception:
            continue
    return out


def classify_published(headline, key_fact="", within_days=21, body=None, corpus=None):
    """Relate a candidate to the recently published corpus (widened from 5 to 21 days so
    multi-week running stories stay linked):
      ('rehash', title, slug)  near-duplicate to HOLD: same event, near-identical framing.
      ('update', title, slug)  a genuine development to publish AS AN UPDATE of the original.
      ('new', None, None)      unseen.
    Split rule: same event is matched as before; a near-identical HEADLINE (>=50% word
    overlap) is a rehash (the 5x-Kalshi case); the same event with a different angle plus
    >=2 new distinctive, non-outlet specifics (new actor/mechanism/number, e.g. the Ostium
    'Tornado Cash / 10,540 ETH' follow-up) is a development. The update links the EARLIEST
    matched story (the origin), so 'develops our earlier reporting' points at the first take."""
    # Z-suffixed, because stored published_utc values are and this is a raw string compare.
    # isoformat() emits +00:00, which sorts against "Z" wrongly at the window edge.
    cutoff = ((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=within_days))
              .strftime("%Y-%m-%dT%H:%M:%SZ")) if within_days else ""
    matches = []
    # corpus is injectable so the guard can be exercised against a controlled set of
    # stories. The version of this canary that only inspected source text let a revert to
    # the oldest-match novelty rule pass clean.
    for d in (_corpus_on_disk() if corpus is None else corpus):
        # Previews and editions can neither suppress a story nor anchor one. Neither reports
        # an event happening, so neither is prior coverage of it. See is_coverage: this is
        # the FOMC fix, applied to the gate that actually runs.
        if not is_coverage(d) or d.get("example"):
            continue
        when = d.get("published_utc") or (d.get("date", "") + "T00:00:00Z")
        if cutoff and when < cutoff:
            continue
        if same_event(headline, key_fact, d.get("title", ""), d.get("key_fact", "")):
            matches.append((when, d))
    if not matches:
        return ("new", None, None)

    # NOVELTY AGAINST EVERYTHING ALREADY PUBLISHED ON THIS EVENT, not against one pick.
    # The old rule measured against min(matches), the OLDEST match, which on 2026-07-30 was
    # an 18-day-old unrelated market story that shared only {hormuz, strait} and had no
    # published_utc, so it always sorted earliest. Every duplicate looked novel beside it.
    covered = set()
    for _, d in matches:
        covered |= _covered_signature(d)
    claim = _claim_signature({"key_fact": key_fact}) if body is None else \
        _signature(key_fact, *[str(b) for b in (body or [])])
    new = claim - covered - _OUTLETS

    earliest = min(matches, key=lambda m: m[0])[1]   # what the update links, for continuity
    nearest = max(matches, key=lambda m: m[0])[1]    # what a rehash is a rehash OF
    if len(new) >= NOVELTY_MIN:
        return ("update", earliest.get("title", ""), earliest.get("slug", ""))
    return ("rehash", nearest.get("title", ""), nearest.get("slug", ""))
