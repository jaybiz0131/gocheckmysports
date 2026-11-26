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


def hero_word(rel, html):
    """The copy law's one fixed word: the Scores hero says "Scoreboard", and nothing else to the eye
    (a day's page adds its day for a screen reader; the lit day tab under the word shows it)."""
    m = re.search(r'<h1 class="sb-claim">(.*?)</h1>', html, re.S)
    if not m:
        return [f"copy: {rel} draws no hero heading"]
    seen = re.sub(r'<span class="sr-only">.*?</span>', "", m.group(1), flags=re.S)
    if seen != "Scoreboard":
        return [f"copy: the Scores hero on {rel} says {re.sub('<[^>]+>', '', seen)!r}; the copy law's word is 'Scoreboard'"]
    whole = re.sub(r"<[^>]+>", "", m.group(1))
    if rel != "scores.html" and not re.fullmatch(r"Scoreboard, [A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2}", whole):
        return [f"copy: the Scores hero on {rel} does not name its day to a screen reader ({whole!r})"]
    return []


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


def late_night():
    """S-DONE point 3, after midnight: /scores.html answers "what is on right now". Saturday's late
    game kicks off at 10:30 PM ET and is in play at 12:30 AM Sunday. The landing page opened on the
    new calendar day, read "Live 0" over Sunday's slate, and the game in play was a day tab away.
    Until 4 AM ET (cadence.DAY_CUT_HOURS, the cut the build cadence has always used) the landing
    page is the day before while one of its games is still on; after its last final, or after the
    cut, it is today's. Rendered here from a fixture on three clocks; no network."""
    import datetime
    import build_manifest as bm
    import site_build as sb
    UTC = datetime.timezone.utc
    u = lambda t: datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(UTC)

    def g(i, lg, a, h, kick, state="pre", status=""):
        return {"league": lg, "id": i, "state": state, "completed": state == "post", "status_short": status,
                "detail": status, "period": 4 if state == "in" else 0, "start_utc": kick, "network": "ESPN",
                "venue": "Stadium", "venue_city": "Town", "venue_state": "CA",
                "away": {"abbr": a, "full": a + " Team", "name": a, "school": a, "score": "21", "id": "a" + i, "rank": None},
                "home": {"abbr": h, "full": h + " Team", "name": h, "school": h, "score": "17", "id": "h" + i, "rank": None}}

    def landing(now_iso, late_state):
        late = g("late1", "CFB", "ARIZ", "UCLA", "2026-11-29T03:30Z", late_state, "8:12 - 4th" if late_state == "in" else "Final")
        early = g("early1", "CFB", "OSU", "MICH", "2026-11-28T17:00Z", "post", "Final")
        sun = [g("nfl1", "NFL", "NO", "CIN", "2026-11-29T18:00Z"), g("nfl2", "NFL", "SEA", "SF", "2026-11-29T21:25Z")]
        sbd = {"fetched_at": now_iso, "leagues": [{"league": "NFL", "games": sun}, {"league": "CFB", "games": [early, late]}]}
        keep = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.CX_DATA, sb.GAME_PAGE_IDS)
        try:
            sb._NOW_CACHE = u(now_iso)
            sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.CX_DATA, sb.GAME_PAGE_IDS = sbd, None, False, None, set()
            sb.MANIFEST = bm.build(sb._build_now(), sbd, None)
            return sb.render_scores_pages(sbd, {}, "")
        finally:
            (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST, sb.CX_DATA, sb.GAME_PAGE_IDS) = keep

    f = []
    cases = [
        ("12:30 AM ET Sunday, Saturday's late game in play", "2026-11-29T05:30:00Z", "in", True),
        ("12:30 AM ET Sunday, Saturday's games all final", "2026-11-29T05:30:00Z", "post", False),
        ("4:30 AM ET Sunday, a card the feed never closed", "2026-11-29T09:30:00Z", "in", False),
        ("11:50 PM ET Saturday, the late game in play", "2026-11-29T04:50:00Z", "in", True),
    ]
    for name, now_iso, state, on_landing in cases:
        try:
            pages = landing(now_iso, state)
        except Exception as e:                                # noqa: BLE001
            f.append(f"readable: late night: {name}: the pages did not render ({type(e).__name__}: {str(e)[:120]})")
            continue
        home = pages.get("/scores.html") or ""
        has = 'data-gid="late1"' in home
        live = _small(home, "data-tab", "live")
        if has != on_landing:
            f.append(f"readable: late night: {name}: /scores.html {'draws' if has else 'does not draw'} the late game "
                     f"(Live says {live})")
        elif on_landing and live != 1:
            f.append(f"readable: late night: {name}: the late game is on /scores.html and Live says {live}")
        f += [x.replace("honest counts:", "readable: late night: " + name + ":") for x in scores_page("scores.html", home)] if home else []
        if 'data-gid="late1"' not in (pages.get("/scores/2026-11-28.html") or ""):
            f.append(f"readable: late night: {name}: Saturday's own page lost the late game")
        if 'data-gid="nfl1"' not in (pages.get("/scores/2026-11-29.html") or ""):
            f.append(f"readable: late night: {name}: Sunday's own page lost its games")
    return f


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
        f += hero_word(os.path.relpath(p, tree), html)
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
