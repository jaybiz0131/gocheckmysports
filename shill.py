#!/usr/bin/env python3
"""
shill.py: deterministic shill-tell scoring (the fail-closed BELT for Stage 2a).

Sports "news" is full of tout bait, rumor churn, and paid promotion disguised as
reporting, and it has tells. This module
scores each aggregated item against rule-based tells (shill_rules.json) and its source
reputation, entirely OFFLINE and deterministically, so the canary can unit-test it. The
editor AI (Stage 2) is the suspenders and the verifier AI (Stage 3) is a second net; this
belt exists so a rule-obvious shill can be caught and shown to the editor even if a prompt
has a blind spot.

Contract per item (added in place):
  shill_score       int   sum of matched tell weights, adjusted by source reputation
  shill_flags       list  [{id, reason, weight}] for each matched tell
  shill_rejected    bool  score >= reject_score (editor still sees it, with the reason)
  reputation_weight float source-tier multiplier (and low-rep-domain penalty)
"""

import json
import os
import re
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "shill_rules.json")


def load_rules(path=RULES_PATH):
    return json.load(open(path, encoding="utf-8"))


def _compile(rules):
    out = []
    for t in rules.get("tells", []):
        out.append((t, re.compile(t["pattern"], re.I)))
    return out


def reputation_weight(item, rules):
    rep = rules.get("source_reputation", {})
    w = rep.get(item.get("source_tier", "unknown"), rep.get("unknown", 0.6))
    low = rep.get("known_low_rep_domains", {})
    domains = low.get("domains", [])
    if domains:
        host = (urlparse(item.get("url", "")).netloc or "").lower()
        if any(host == d or host.endswith("." + d) for d in domains):
            w = min(w, low.get("penalty", 0.4))
    return float(w)


def score_item(item, rules, compiled=None):
    """Annotate one normalized item in place with its shill assessment. Returns the item."""
    compiled = compiled or _compile(rules)
    text = " ".join(str(item.get(k, "")) for k in ("headline", "snippet", "source"))
    flags = []
    raw = 0
    for t, rx in compiled:
        if rx.search(text):
            flags.append({"id": t["id"], "reason": t["reason"], "weight": t["weight"]})
            raw += t["weight"]

    rep_w = reputation_weight(item, rules)
    # A low-reputation source amplifies the tells it carries; a primary/official source
    # dampens them (an SEC or CFTC release using the word "massive" is not shill).
    adjusted = int(round(raw * (2.0 - rep_w))) if raw else 0

    thresholds = rules.get("thresholds", {})
    reject_at = thresholds.get("reject_score", 5)

    item["reputation_weight"] = rep_w
    item["shill_flags"] = flags
    item["shill_score"] = adjusted
    item["shill_rejected"] = adjusted >= reject_at
    return item


def annotate(items, rules=None):
    rules = rules or load_rules()
    compiled = _compile(rules)
    for it in items:
        score_item(it, rules, compiled)
    return items
