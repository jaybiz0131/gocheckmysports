#!/usr/bin/env python3
"""odds_gate.py: no betting data reaches disk or a page. HARD GATE (ruling 6).

WHY A GATE AND NOT A HABIT. The game-summary endpoint returns `odds`, `pickcenter`,
`againstTheSpread` and `predictor` in the SAME payload as the box score, so every
fantasy surface this program builds holds betting data in memory while it works. The
doctrine is absolute (standing rule 3: no odds, no props, no sportsbook language
anywhere), and the distance between "we do not read that key" and "somebody wrote
json.dump(payload)" is one careless line.

So this checks the OUTPUT rather than trusting the code: every written data file and
every rendered page, for the four field names and for sportsbook vocabulary.

Exit 1 on any hit. The count is reported on every ship whether it is zero or not.

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

# The four field names named in the ruling.
FIELDS = ("odds", "pickcenter", "againstTheSpread", "predictor")

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
