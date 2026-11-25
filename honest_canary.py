#!/usr/bin/env python3
"""honest_canary.py: S-DONE point 2, the counts a reader can add up. A fixture test on a built tree.

Every count on the board is checked against the cards under it, on the pages as built:

  Scores (every day page and /scores.html)
      All = the sum of the league tabs = the cards on the page
      Live + Upcoming + Final = All, and each state tab = the cards in its panel
      no game is drawn twice
  the home
      each day tab = the cards drawn under that day + the "N more college games" line there

S-60 found All printing 85 over 58 cards (the count came from every league in the feed, the page
drew two). Its fixture covers one Saturday; this reads every board page of whatever tree it is
given, so the rule holds on the day's build and on the gate's slate alike.

USAGE  python3 honest_canary.py TREE
"""

import glob
import os
import re
import sys


def _small(html, attr, value):
    m = re.search(r'<a [^>]*%s="%s"[^>]*>[^<]*<small>(\d+)</small>' % (attr, re.escape(value)), html)
    return int(m.group(1)) if m else None


def scores_page(rel, html):
    f = []
    lg = re.search(r'<div class="tk-tabs sc-leagues">(.*?)</div>', html, re.S)
    if not lg:
        return [f"honest counts: {rel} carries no league tabs"]
    tabs = dict(re.findall(r'data-league="([^"]+)"[^>]*>[^<]*<small>(\d+)</small>', lg.group(1)))
    if "All" not in tabs:
        return [f"honest counts: {rel} carries no All tab"]
    allc = int(tabs.pop("All"))
    parts = re.split(r'<div class="sc-panel" data-panel="', html)[1:]
    by_panel, gids = {}, []
    for p in parts:
        name = p.split('"', 1)[0]
        ids = re.findall(r'<article class="tk-c[^"]*" data-gid="([^"]+)"', p)
        by_panel[name] = len(ids)
        gids += ids
    if sum(int(v) for v in tabs.values()) != allc:
        f.append(f"honest counts: {rel}: All says {allc}, the league tabs add to {sum(int(v) for v in tabs.values())} ({tabs})")
    if len(gids) != allc:
        f.append(f"honest counts: {rel}: All says {allc} over {len(gids)} card(s)")
    if len(set(gids)) != len(gids):
        f.append(f"honest counts: {rel}: a game is drawn twice")
    states = {t: _small(html, "data-tab", t) for t in ("live", "upcoming", "final")}
    if None in states.values():
        f.append(f"honest counts: {rel} is missing a state tab")
    else:
        if sum(states.values()) != allc:
            f.append(f"honest counts: {rel}: Live, Upcoming and Final add to {sum(states.values())}, All says {allc}")
        for t, n in states.items():
            if by_panel.get(t) != n:
                f.append(f"honest counts: {rel}: the {t.title()} tab says {n} over {by_panel.get(t)} card(s)")
    for lgname, n in tabs.items():
        got = len(re.findall(r'<article class="tk-c[^"]*" data-gid="[^"]+"(?: data-sbc="[^"]*")? data-league="%s"' % re.escape(lgname), html))
        if got != int(n):
            f.append(f"honest counts: {rel}: the {lgname} tab says {n} over {got} card(s)")
    return f


def home_page(html):
    """The day tabs against the day sections, paired in page order (the gate's slate can hold two
    days of one name, a Tuesday at each end of its week, so a name is not a key)."""
    f = []
    tabs = re.findall(r'<a class="tk-tab wb-t" data-day="([a-z]{3})"[^>]*>[^<]*<small>(\d+)</small>', html)
    secs = re.split(r'<section class="bd-mod wb-day" id="day-', html)[1:]
    if not tabs or not secs:
        return ["honest counts: the home carries no day tabs or no day sections"]
    seen = []
    for s in secs:
        day = s.split('"', 1)[0]
        body = s.split("</section>", 1)[0]
        cards = len(re.findall(r'<article class="tk-c[^"]*" data-gid="', body))
        more = sum(int(x) for x in re.findall(r"(\d+) more college games?\.", body))
        seen.append((day, cards, more))
    if [d for d, _n in tabs] != [d for d, _c, _m in seen]:
        return [f"honest counts: the home's day tabs ({' '.join(d for d, _n in tabs)}) are not its day sections "
                f"({' '.join(d for d, _c, _m in seen)})"]
    for (day, n), (_d, cards, more) in zip(tabs, seen):
        if cards + more != int(n):
            f.append(f"honest counts: the home's {day.title()} tab says {n}; {cards} card(s) are drawn and the line "
                     f"under them counts {more} more")
    return f


def readable(tree, slate=False):
    """S-DONE point 3, on the board's cards as built (the home and every Scores page):
      a game to come or in play names its carrier, and by the name networks.py gives it: a chip
        that prints a code the table spells out ("CBSSN" for CBS Sports Network) fails
      on the gate's slate, where every game has them: a game to come carries its line and its
        kickoff conditions or the one line that says why not; a game in play or final draws no
        "Conditions unavailable"."""
    import networks
    f, n = [], 0
    pages = [os.path.join(tree, "index.html"), os.path.join(tree, "scores.html")] \
        + sorted(glob.glob(os.path.join(tree, "scores", "*.html")))
    for p in pages:
        if not os.path.exists(p):
            continue
        rel = os.path.relpath(p, tree)
        html = open(p, encoding="utf-8").read()
        for a in re.split(r'(?=<article class="tk-c)', html)[1:]:
            a = a.split("</article>")[0]
            st = re.search(r'data-state="(\w+)"', a)
            gid = re.search(r'data-gid="([^"]+)"', a)
            if not st or not gid:
                continue
            st, gid = st.group(1), gid.group(1)
            n += 1
            chips = [c.strip() for c in re.findall(r'class="(?:tk-chip|sbc-chip)"[^>]*>([^<]*)<', a)]
            if st in ("pre", "in") and not any(chips):
                f.append(f"readable: {rel}: game {gid} ({st}) names no carrier")
            for c in chips:
                if c and (networks.label(c)[0] != c):
                    f.append(f"readable: {rel}: game {gid} prints the carrier as {c!r}; its name is {networks.label(c)[0]!r}")
            wx = 'class="sbc-wx"' in a or 'class="sbc-wp' in a
            if st in ("in", "post") and "Conditions unavailable" in a:
                f.append(f"readable: {rel}: game {gid} ({st}) draws 'Conditions unavailable'; kickoff conditions are for a game to come")
            if slate and st == "pre":
                if 'class="tk-line"' not in a:
                    f.append(f"readable: {rel}: game {gid} is to come and prints no line")
                if not wx:
                    f.append(f"readable: {rel}: game {gid} is to come and prints neither its kickoff conditions nor why not")
    if not n:
        f.append("readable: no game card was read")
    return f[:12] + ([f"readable: and {len(f) - 12} more"] if len(f) > 12 else [])


def honest_canary(tree):
    if not tree or not os.path.isdir(tree):
        return ["honest counts: no built tree to read"]
    f, n = [], 0
    pages = [os.path.join(tree, "scores.html")] + sorted(glob.glob(os.path.join(tree, "scores", "*.html")))
    for p in pages:
        if not os.path.exists(p):
            continue
        html = open(p, encoding="utf-8").read()
        if 'class="tk-tabs sc-leagues"' not in html:
            continue        # a placeholder for a day the feed no longer holds draws no board
        n += 1
        f += scores_page(os.path.relpath(p, tree), html)
    if not n:
        f.append("honest counts: no Scores page with a board was read")
    hp = os.path.join(tree, "index.html")
    if os.path.exists(hp):
        f += home_page(open(hp, encoding="utf-8").read())
    else:
        f.append("honest counts: the home is not in the tree")
    return f


if __name__ == "__main__":
    fs = honest_canary(sys.argv[1] if len(sys.argv) > 1 else "")
    for x in fs:
        print("::error::" + x)
    print("HONEST CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
