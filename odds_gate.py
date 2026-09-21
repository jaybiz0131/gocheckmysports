#!/usr/bin/env python3
"""odds_gate.py: picks and sportsbooks reach no file and no page. HARD GATE.

THE LAW CHANGED ON 20 SEPTEMBER 2026 and this gate changed with it. Lines now come onto
the site as FACTS: the spread, the total and the moneyline from the feed's odds object,
with the provider named on the card, the line at open beside the line now, and on finals
whether the favourite covered and whether the total went over. So `odds` is no longer
contraband, and a gate that still blocked it would have blocked the thing the desk now
publishes.

WHAT IS STILL ABSOLUTE, and what this gate is now for:

  pickcenter          somebody else's pick
  againstTheSpread    a record presented as a betting guide
  predictor           a forecast

Those three are predictions and opinions, not readings, and the desk publishes neither.
A sportsbook LINK is also still banned: showing a line is reporting, sending a reader to
a book is a different business and a state-law question Jack decides separately.

AND A LINE WITHOUT ITS PROVIDER IS NOT A FACT. A spread is a number one company is
offering at one moment. Printing it unattributed makes it look like the desk's own
estimate, which is exactly the thing the desk does not do. So a page carrying a line
must name who set it.

The vocabulary scan stays advisory on the desk's own chrome and never fails the build:
the first cut of this file failed on eight legitimate pages, including a Lions story
naming the player Juice Scruggs and coverage of an Arizona gaming investigation.
Reporting a betting scandal is journalism.

USAGE  python3 odds_gate.py            # check site/data and site/publish
       python3 odds_gate.py --quiet    # summary line only
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "site", "data")
PUBLISH = os.path.join(HERE, "site", "publish")

# The three that are still contraband. "odds" came off the list on 20 Sep: the desk
# publishes the line now, attributed.
FIELDS = ("pickcenter", "againstTheSpread", "predictor")

# A sportsbook a reader could be sent to. Naming a provider is required; linking to one
# is not allowed, so this looks for the link and not for the name.
# A line on the page, and the attribution that has to sit with it.
# THE CONTAINER, not its children. "class=\"...tk-line\b" also matched tk-line-v and
# tk-line-ml, so one line counted three times and the check failed on a correct page.
LINE_SHOWN = re.compile(r'data-line-spread="')
PROVIDER_SHOWN = re.compile(r'data-line-provider="[^"]+"')
# The law's last clause has the same requirement as its first: a cover is a
# statement about one company's number, so a ruling with no name on it is the
# desk asserting a spread of its own.
RULING_SHOWN = re.compile(r'class="tk-ruling"')
RULING_PROVIDER = re.compile(r'data-ruling-provider="[^"]+"')

BOOKS = ("draftkings.com", "fanduel.com", "caesars.com", "betmgm.com", "pointsbet",
         "bet365", "barstoolsportsbook", "espnbet.com", "sportsbook.")

# SCOPE IS THE FOUR FIELD NAMES, and the first cut of this file proved why it has to
# be. A broader scan for sportsbook vocabulary failed the build on eight pages, and
# every one was legitimate: a Lions story naming the player Juice Scruggs, coverage of
# an Arizona gaming investigation, a horse-racing integrity probe. The desk reports on
# gambling as news; what it must never do is carry the feed's betting FIELDS. Reporting
# a betting scandal is journalism. Shipping `pickcenter` is the violation.
#
# The vocabulary scan is kept as advisory output on the desk's OWN surfaces only (never
# articles or editions), because a sportsbook word in the chrome would be worth seeing.
# It never fails the build.
CHROME = ("index.html", "fantasy/inactives.html", "where-to-watch.html", "keepers.html",
          "news.html", "about.html", "method.html", "standards.html")
VOCAB = re.compile(r"\b(moneyline|money line|point spread|against the spread|"
                   r"over/under|sportsbook|parlay|prop bet|puck line|run line|"
                   r"handicapper|betting odds|odds to win)\b", re.I)

# "odds" is an ordinary English word, so in HTML it is matched only where it can be a
# field: a data- attribute, a JSON key, or an assignment. Never as prose.
HTML_FIELD = re.compile(r'(?:data-(?:' + "|".join(F.lower() for F in FIELDS) + r')\b'
                        r'|"(?:' + "|".join(FIELDS) + r')"\s*:)')


def _keys(obj, path=""):
    """Every key path in a JSON document."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k
            yield from _keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            yield from _keys(v, f"{path}[{i}]")


def check_data():
    hits = []
    if not os.path.isdir(DATA):
        return hits
    for root, _d, files in os.walk(DATA):
        for f in files:
            if not f.endswith(".json"):
                continue
            p = os.path.join(root, f)
            try:
                doc = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            for path, k in _keys(doc):
                if k in FIELDS:
                    hits.append((os.path.relpath(p, HERE), path))
    return hits


def check_pages():
    hits = []
    if not os.path.isdir(PUBLISH):
        return hits
    for root, _d, files in os.walk(PUBLISH):
        for f in files:
            if not f.endswith(".html"):
                continue
            p = os.path.join(root, f)
            try:
                h = open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            rel = os.path.relpath(p, PUBLISH)
            for m in HTML_FIELD.findall(h):
                hits.append((rel, f"betting field {m!r}"))
            # A sportsbook a reader could be sent to.
            low = h.lower()
            for b in BOOKS:
                if f'href="http' in low and b in low:
                    for href in re.findall(r'href="(https?://[^"]+)"', low):
                        if b in href:
                            hits.append((rel, f"sportsbook link {href[:52]!r}"))
                            break
            # A LINE WITHOUT ITS PROVIDER. A page that prints a spread must say who set
            # it, or the number reads as the desk's own estimate.
            # PER LINE, NOT PER PAGE. Asking whether the page names a provider
            # anywhere lets one unattributed line hide among attributed ones, which is
            # exactly the line that would mislead. Every line gets its own.
            n_lines = len(LINE_SHOWN.findall(h))
            n_prov = len(PROVIDER_SHOWN.findall(h))
            if n_lines > n_prov:
                hits.append((rel, f"{n_lines - n_prov} line(s) with no provider named"))
            # A RULING WITHOUT ITS PROVIDER, counted the same way and for the same
            # reason. "KC covered" is arithmetic on somebody's spread; unattributed it
            # is the desk saying what the spread was.
            n_rule = len(RULING_SHOWN.findall(h))
            n_rprov = len(RULING_PROVIDER.findall(h))
            if n_rule > n_rprov:
                hits.append((rel, f"{n_rule - n_rprov} cover ruling(s) with no "
                                  f"provider named"))
    return hits


def check_vocab():
    """Advisory only, and only on the desk's own chrome. Never fails the build."""
    out = []
    for rel in CHROME:
        p = os.path.join(PUBLISH, rel)
        if not os.path.exists(p):
            continue
        h = open(p, encoding="utf-8", errors="ignore").read()
        for m in set(VOCAB.findall(h)):
            out.append((rel, m))
    return out


def main():
    quiet = "--quiet" in sys.argv
    d, pg, v = check_data(), check_pages(), check_vocab()
    if not quiet:
        for src, what in (d + pg)[:40]:
            print(f"  HIT {src}: {what}")
        for src, w in v[:10]:
            print(f"  advisory: {src} contains {w!r}")
    total = len(d) + len(pg)
    print(f"odds_gate: {len(d)} data hit(s), {len(pg)} page hit(s), {total} total"
          f"; {len(v)} advisory vocabulary note(s) on chrome")
    if total:
        print("odds_gate: FAIL. Betting data must reach no written file and no page.")
        return 1
    print("odds_gate: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
