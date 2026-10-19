#!/usr/bin/env python3
"""affiliates.py: the affiliate link for a streaming service, from data/affiliates.json (S-3b.2).

The file is the only place an affiliate URL lives. A slot with an empty url means no
affiliate link: the renderers print the service's plain link and the page carries no money
line. A filled slot prints its url with REL on the anchor, and the page's footer carries
MONEY_LINE. Standard library only. Nothing here invents a url."""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "data", "affiliates.json")

REL = "sponsored nofollow noopener"

# The footer sentence on any page that prints an affiliate link. No ruling in docs/RULINGS.md
# words it, so it is written to the September 16 copy law: plain, no hype, no pick.
MONEY_LINE = ("How we make money: some streaming links on this page are affiliate links, "
              "and we may earn a commission if you subscribe through one. It never changes "
              "which games or services are listed.")


def load(path=None):
    try:
        with open(path or PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _key(label):
    return re.sub(r"\s*\([^)]*\)\s*", " ", label or "").strip().lower()


def _slots(doc):
    return [s for s in (doc or {}).get("slots") or [] if isinstance(s, dict)]


def url_for(label, doc=None):
    """The affiliate url for a service label, or '' when no slot names it or the slot is empty.
    Only an https url counts."""
    doc = load() if doc is None else doc
    k = _key(label)
    if not k:
        return ""
    for s in _slots(doc):
        if k in {_key(n) for n in (s.get("names") or []) + [s.get("service") or ""]}:
            u = (s.get("url") or "").strip()
            return u if u.startswith("https://") else ""
    return ""


def is_affiliate(url, doc=None):
    doc = load() if doc is None else doc
    u = (url or "").strip()
    return bool(u) and any((s.get("url") or "").strip() == u for s in _slots(doc))
