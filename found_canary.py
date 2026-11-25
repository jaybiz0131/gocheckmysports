#!/usr/bin/env python3
"""found_canary.py: S-DONE point 9, a searcher can tell what the site is and a crawler what is on.

  the words     the home's title, its description and the masthead line all carry the phrase a
                searcher would type: "college football and NFL scores, where to watch, spreads and
                kickoff weather"; the old "Sports, checked." is on none of them
  About         the About page names who runs the site (Go Check My Brands LLC) and how to reach
                them, and says nothing about how the desk works: no "verif", "editor", "published",
                "bias", "rumor", "sources" and no "How" heading
  the events    the home and /scores.html carry a schema.org SportsEvent for each of the day's
                games that has a game page: a name, a start time with its ET offset, a venue with
                its city, both teams and the game page's URL, sharing the @id the game page's own
                markup uses; the JSON parses; nothing the schema does not accept
                (teams_canary.type_errors) and nothing Google requires missing
                (measure_canary.SPORTS_EVENT_REQUIRED)

USAGE  python3 found_canary.py [TREE]     the words and About on fixtures; the events on a built tree
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PHRASE = "college football and NFL scores, where to watch, spreads and kickoff weather"
HOW_WORDS = ("verif", "editor", "published", "publish", "bias", "rumor", "sources", "checked against",
             "how a story", "how we", "standard")


def _text(html):
    import html as _h
    html = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html or "")
    m = re.search(r"(?is)<main\b.*?</main>", html)
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", m.group(0) if m else html)))


def words():
    import site_build as sb
    f = []
    home = sb.render_home([], "")
    title = (re.search(r"(?is)<title>(.*?)</title>", home) or [None, ""])[1]
    desc = (re.search(r'<meta name="description" content="([^"]*)"', home) or [None, ""])[1]
    mast = (re.search(r'<span class="mh-slogan">([^<]*)</span>', home) or [None, ""])[1]
    for name, got in (("title", title), ("description", desc), ("masthead line", mast)):
        if PHRASE.lower() not in got.lower().replace("&amp;", "&"):
            f.append(f"found: the home's {name} reads {got!r}; it does not say {PHRASE!r}")
        if "sports, checked" in got.lower() or "independent sports news" in got.lower():
            f.append(f"found: the home's {name} still reads {got!r}")
    if len(title) > 110:
        f.append(f"found: the home's title is {len(title)} characters")
    if '"description": "' + desc[:40] not in home.replace('"description":"', '"description": "'):
        f.append("found: the publisher's description in the home's markup is not the page's description")
    about = sb.render_about("")
    t = _text(about)
    if "Go Check My Brands LLC" not in t:
        f.append("found: the About page does not name Go Check My Brands LLC")
    if "hello@gocheckmysports.com" not in t:
        f.append("found: the About page gives no way to reach who runs the site")
    low = t.lower()
    for w in HOW_WORDS:
        if w in low:
            f.append(f"found: the About page says how the desk works ({w!r}); it says who runs the site and nothing else")
    if re.search(r"(?i)<h2[^>]*>\s*how\b", about):
        f.append("found: the About page carries a How heading")
    if len(t) > 900:
        f.append(f"found: the About page's body is {len(t)} characters; who runs it is a few lines")
    ad = (re.search(r'<meta name="description" content="([^"]*)"', about) or [None, ""])[1]
    if "Go Check My Brands LLC" not in ad:
        f.append(f"found: the About page's description reads {ad!r}")
    return f


def _ld(html):
    out = []
    for m in re.findall(r'(?s)<script type="application/ld\+json">(.*?)</script>', html):
        out.append(json.loads(m))
    return out


def events(tree):
    """The SportsEvent markup on the built home and Scores page, against the game pages in the tree."""
    import measure_canary as mc
    import teams_canary as tc
    f = []
    for page in ("index.html", "scores.html"):
        p = os.path.join(tree, page)
        if not os.path.exists(p):
            f.append(f"found: {page} is not in the tree")
            continue
        html = open(p, encoding="utf-8").read()
        try:
            graphs = _ld(html)
        except ValueError as e:
            f.append(f"found: {page} carries JSON-LD that does not parse ({e})")
            continue
        evs = [n for g in graphs for n in (g.get("@graph") or [g]) if isinstance(n, dict) and n.get("@type") == "SportsEvent"]
        # the day's games the page draws that have a game page
        day = (re.search(r'data-live-day="([^"]+)"', html) or [None, ""])[1]
        cards = {}
        for a in re.split(r'(?=<article class="tk-c)', html)[1:]:
            gid = re.search(r'data-gid="([^"]+)"', a)
            kick = re.search(r'data-kick="([^"]+)"', a)
            if gid and kick:
                cards[gid.group(1)] = kick.group(1)
        want = {g for g in cards if os.path.exists(os.path.join(tree, "games", g + ".html"))}
        if page == "index.html":
            # the home names the games of its day: the cards under the section dated data-live-day
            m = re.search(r'<section class="bd-mod wb-day"[^>]*data-date="%s".*?</section>' % re.escape(day), html, re.S)
            today = set(re.findall(r'data-gid="([^"]+)"', m.group(0))) if m else set()
            want &= today
        if not want:
            continue        # a day with no game drawn carries no event; nothing to hold it to
        got = {}
        for n in evs:
            m = re.search(r"/games/([^/.]+)\.html", n.get("url") or "")
            if m:
                got[m.group(1)] = n
        miss = sorted(want - set(got))
        if miss:
            f.append(f"found: {page} draws {len(want)} of its day's games with a game page and carries a SportsEvent "
                     f"for {len(want & set(got))}; none for game {miss[0]}" + (f" and {len(miss) - 1} more" if len(miss) > 1 else ""))
        extra = sorted(set(got) - set(cards))
        if extra:
            f.append(f"found: {page} carries a SportsEvent for game {extra[0]}, which it does not draw")
        for gid, n in sorted(got.items())[:80]:
            lost = mc._missing(n, mc.SPORTS_EVENT_REQUIRED + ["url", "homeTeam.name", "awayTeam.name", "eventStatus"])
            if lost:
                f.append(f"found: {page}: the SportsEvent for game {gid} is missing {', '.join(lost)}")
                break
            if not re.search(r"T\d\d:\d\d:\d\d-0[45]:00$", n.get("startDate") or ""):
                f.append(f"found: {page}: game {gid} starts at {n.get('startDate')!r}, not a time with its ET offset")
                break
            if n.get("@id") != f"https://gocheckmysports.com/games/{gid}.html#event":
                f.append(f"found: {page}: game {gid}'s event is {n.get('@id')!r}, not the game page's own")
                break
        for g in graphs:
            errs = tc.type_errors(g)
            if errs:
                f.append(f"found: {page}: {errs[0]}")
                break
        if not f:
            print(f"found: {page} carries {len(got)} SportsEvent(s) for the {len(want)} game(s) of {day} it draws with a game page")
    return f


def found_canary(tree=None):
    f = words()
    if tree:
        if not os.path.isdir(tree):
            f.append("found: no built tree to read the events from")
        else:
            f += events(tree)
    return f


if __name__ == "__main__":
    fs = found_canary(sys.argv[1] if len(sys.argv) > 1 else None)
    for x in fs:
        print("::error::" + x)
    print("FOUND CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
