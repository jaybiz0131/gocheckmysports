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
    sig |= _magnitudes(blob)
    return {t for t in sig if t and t not in _UBIQUITOUS and len(t) >= 2}


def _magnitudes(blob):
    """The SAME figure written two ways must fingerprint the same (2026-08-13 audit).
    The desk published one $200K bridge exploit twice: one headline said '$200K', the
    other '$200,000', and the key facts carried '199,916'. Literal tokens made those
    three different fingerprints, the pair scored one shared token against a threshold
    of two, and the guard let a duplicate through. Money and large counts are bucketed
    to a rounded magnitude so the writing style stops deciding whether two stories are
    the same event."""
    out = set()
    for num, suffix in re.findall(r"\$?\b(\d[\d,]*(?:\.\d+)?)\s*(k|m|b|bn|million|billion|thousand)?\b",
                                  blob, re.I):
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        mult = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6,
                "b": 1e9, "bn": 1e9, "billion": 1e9}.get((suffix or "").lower(), 1)
        v *= mult
        if v >= 1000:
            # two significant figures: 199,916 and 200,000 both land on mag:2.0e5
            import math
            exp = int(math.floor(math.log10(v)))
            out.add(f"mag:{round(v / 10 ** exp, 1)}e{exp}")
    return out


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
    # GENERAL-NEWS OUTLETS (2026-08-30). This list shipped to the news and sports desks
    # as the crypto chassis copy, so on those desks "CBS", "Guardian" and "NBC" counted
    # as NOVEL CLAIM TOKENS: attributing a story to a different outlet made it read as
    # new reporting, and that is one of the token classes that republished the same
    # event under a second URL. Attribution is not news on any desk.
    "cbs", "cbsnews", "guardian", "theguardian", "nbc", "nbcnews", "abc", "abcnews",
    "npr", "bbc", "fox", "foxnews", "cnn", "ap", "associated", "politico", "hill",
    "thehill", "nytimes", "nyt", "washingtonpost", "wapo", "espn", "athletic",
    "yahoo", "sportico", "sportsnet", "tsn", "skysports",
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


def classify_published(headline, key_fact="", within_days=21, body=None, corpus=None,
                       now=None):
    """Relate a candidate to the recently published corpus (widened from 5 to 21 days so
    multi-week running stories stay linked):
      ('rehash', title, slug)  near-duplicate to HOLD: same event, near-identical framing.
      ('update', title, slug)  a genuine development to publish AS AN UPDATE of the original.
      ('new', None, None)      unseen.
    Split rule: same event is matched as before; a near-identical HEADLINE (>=50% word
    overlap) is a rehash (the 5x-Kalshi case); the same event with a different angle plus
    >=2 new distinctive, non-outlet specifics (new actor/mechanism/number, e.g. the Ostium
    'Tornado Cash / 10,540 ETH' follow-up) is a development. The update links the EARLIEST
    matched story (the origin), so 'develops our earlier reporting' points at the first take.

    `now` is injectable, and that is not a convenience. This function reads the wall clock to
    build its window, so any test that pins its fixtures to absolute dates is a time bomb: it
    passes on the day it is written and fails silently when the calendar walks past the
    window. That is not hypothetical. The canary's Ostium follow-up fixture was dated
    2026-07-16, the window is 21 days, and on 2026-08-06 it aged out. The origin stopped
    matching, the follow-up classified 'new' instead of 'update', the assertion fired, and
    because the canary is a HARD GATE all three desks stopped publishing for two days over a
    date. hackwatch and fedreg already take an explicit `today=` for exactly this reason;
    this closes the last clock-reading gap in the pipeline."""
    # Z-suffixed, because stored published_utc values are and this is a raw string compare.
    # isoformat() emits +00:00, which sorts against "Z" wrongly at the window edge.
    _now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = ((_now - datetime.timedelta(days=within_days))
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


def adds_nothing_new(title, key_fact, body=None, corpus=None, within_days=21):
    """The certain half of dupe_audit's measure, promoted to a live gate.

    dupe_audit has always been able to name the stories that said the same thing twice
    ("10 added NOTHING new"), but it is advisory, so nothing stopped them: one Indonesia
    earthquake shipped as six separate URLs, one court ruling as three. classify_published
    cannot catch these on its own because its tri-state deliberately leans toward "update"
    (calling a real follow-up a duplicate silently loses reporting).

    So this asks dupe_audit's question, not the guard's: how many distinctive claim tokens
    does this story add that an already-published story on the same event did not carry?
    ZERO means the desk is about to say the same thing twice, and that is the only case
    this reports. One-fact-of-novelty stays where it is today, advisory, because that is
    the genuinely ambiguous zone where an editor should decide.

    Returns (title, slug) of the story it repeats, or (None, None).
    """
    cand = {"title": title or "", "key_fact": key_fact or "", "body": body or ""}
    # NO SIGNATURE, NO VERDICT (2026-08-21). See _unjudgeable below: an empty claim
    # signature made every loosely-matched story look like a retelling, and held real
    # follow-ups on the desk's own threads.
    if not _claim_signature(cand):
        return None, None
    for origin in (corpus if corpus is not None else _corpus_on_disk()):
        if origin.get("example") or str(origin.get("id") or "").startswith("wrap-"):
            continue
        if not is_coverage(origin):
            continue
        if not same_event(origin.get("title", ""), origin.get("key_fact", ""),
                          cand["title"], cand["key_fact"]):
            continue
        novel = _claim_signature(cand) - _covered_signature(origin) - _OUTLETS
        if not novel:
            return origin.get("title"), origin.get("slug")
    return None, None


def _unjudgeable(title, key_fact, body=None):
    """True when there is nothing here to measure novelty WITH.

    An empty claim signature makes `novel` trivially empty, which this function would
    otherwise report as "says nothing new" -- the strongest possible verdict drawn from
    the weakest possible evidence. It is not hypothetical: with an empty key_fact, the
    Buccaneers-Vea extension was held against the trade-request story it resolves, which
    is precisely the follow-up the desk was criticised for missing. dupe_audit's own notes
    warned about this ("a thin blurb yields a claim signature too small to match
    anything"). No signature means no verdict, and no verdict means publish.
    """
    return not _claim_signature({"title": title or "", "key_fact": key_fact or "",
                                 "body": body or ""})
