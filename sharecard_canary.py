#!/usr/bin/env python3
"""sharecard_canary.py: S-3b item 1, the 1080 square share card on every game page.

Fixtures only: no Worker, no feed, no model. Each check names the break it exists for and was
seen red first (U-9).

  card      a card drawn from a fixture game exists, is 1080 by 1080, and draws both sites' names
            in plain text (GoCheckMySports and GoCheckMyWeather) with no logo
  pre       an unplayed game draws no score and never the word FINAL, even when the feed carries
            a 0 for each side; its kickoff is drawn in ET with the zone and its network is drawn
  post      a final draws its two scores from the feed and the word FINAL; a game in progress draws
            the page's own words and its running score, never FINAL, and the word live is on no card
  outside   a game outside NWS coverage draws the page's one line ("London · Outside NWS coverage")
            and no NWS credit; a card with a reading carries exactly one credit line, the stamp, with
            its day when the reading is not from the build's day
  plates    the conditions plates are the page's own numbers; a dome, an unreadable forecast and a
            game with no entry each draw a plate that says why, never a number
  palette   every color a card paints in bulk is one of the nine pinned here as literals, and WALL_PALETTE is them
  tags      a game page's og:image names /share/games/<id>-square.png with width and height 1080,
            twitter:image names the same file and twitter:card is "summary" (a square image under
            summary_large_image is cropped); the 1200x630 default is unchanged on a page with no
            card of its own
  tree      on the gate's own build: every game page's og:image file is in the tree, is 1080 by
            1080 (the dimensions in the tags are the file's own), and the page's tags agree

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import datetime
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ORIGIN = "https://gocheckmysports.com"


def _drawn(fn, *a):
    """Run a card draw and return (result, every string it drew, in order)."""
    from PIL import ImageDraw
    seen = []
    orig = ImageDraw.ImageDraw.text

    def spy(self, xy, text, *args, **kw):
        seen.append(str(text))
        return orig(self, xy, text, *args, **kw)
    ImageDraw.ImageDraw.text = spy
    try:
        return fn(*a), seen
    finally:
        ImageDraw.ImageDraw.text = orig


def check_cards():
    fails = []
    try:
        from PIL import Image
    except ImportError:
        return ["share card: Pillow is not installed, so no card was drawn"]
    import conditions_report as cr
    import site_build as sb
    import strip_canary as st
    was = (sb.CX_DATA, sb._NOW_CACHE)
    tmp = tempfile.mkdtemp()
    try:
        sb._NOW_CACHE = datetime.datetime(2026, 10, 15, 13, 0, tzinfo=datetime.timezone.utc)
        dome = {"status": "indoor", "venue": "Allegiant Stadium", "words": {"line": "Indoor", "roof": "Indoor"},
                "credit": {"text": "Conditions by GoCheckMyWeather, NWS, 8:34 PM ET"}}
        sb.CX_DATA = {"games": {"den": st._entry(), "dome": dome,
                                "gap": st._entry(kickoff_hour={"temp_f": None, "sky": "Sunny", "pop_pct": None,
                                                               "wind_mph": None, "wind": {}}, flags=st._QUIET)}}

        def draw(g, name):
            row = sb.game_share_row(g)
            p, texts = _drawn(cr.game_share_card, row, os.path.join(tmp, name))
            return row, Image.open(p).convert("RGB"), texts

        # the card from a fixture; the feed carries a 0 for each side of a game not yet played
        pre = st._game("den")
        pre["away"]["score"], pre["home"]["score"] = "0", "0"
        row, im, texts = draw(pre, "den.png")
        if im.size != (1080, 1080):
            fails.append(f"share card: {im.size} is not 1080 by 1080")
        for mark in ("GoCheckMySports", "GoCheckMyWeather"):
            if mark not in texts:
                fails.append(f"share card: the mark {mark} is not drawn in plain text")
        if im.getpixel((540, 540)) == im.getpixel((5, 5)):
            fails.append("share card: the card is not a panel inside a frame")
        # unplayed: no score, never Final
        if row["score_away"] is not None or row["score_home"] is not None or "0" in texts:
            fails.append(f"share card: an unplayed game draws a score ({row['score_away']}, {row['score_home']})")
        if any("FINAL" in t.upper() or "LIVE" in t.upper() for t in texts):
            fails.append("share card: a scheduled game says Final or Live")
        if "THU, OCT 15, 8:15 PM ET" not in [t.upper() for t in texts]:
            fails.append(f"share card: the kickoff is not drawn in ET with the zone: {texts}")
        if "ON PRIME VIDEO" not in [t.upper() for t in texts]:
            fails.append("share card: the network is not drawn")
        if not {"47", "18", "33"} <= set(texts):
            fails.append(f"share card: the conditions plates are not the page's own numbers: {texts}")
        # a final: both scores from the feed and the word FINAL
        fin = st._game("den", state="post")
        fin["away"]["score"], fin["home"]["score"] = "24", "17"
        _r, _i, t2 = draw(fin, "fin.png")
        if not {"24", "17", "FINAL"} <= set(t2):
            fails.append(f"share card: a final does not draw its scores and FINAL: {t2}")
        # a game in progress uses the page's own words and its running score, never Final, and the
        # word "live" is on no card at all until S-4 (ruling of 12 October, scorecard line 6)
        liv = st._game("den", state="in", status_short="3rd Quarter", detail="5:21")
        liv["away"]["score"], liv["home"]["score"] = "10", "7"
        _r, _i, tl = draw(liv, "live.png")
        if "3rd Quarter \u00b7 5:21" not in tl or "FINAL" in tl or not {"10", "7"} <= set(tl):
            fails.append(f"share card: a game in progress does not draw the page's words and its running score, or says Final: {tl}")
        liv2 = st._game("den", state="in")
        liv2["away"]["score"], liv2["home"]["score"] = "3", "0"
        _r, _i, tl2 = draw(liv2, "live2.png")
        if "In progress" not in tl2:
            fails.append(f"share card: a game in progress with no period words does not say In progress: {tl2}")
        liv3 = st._game("den", state="in", status_short="Live")
        liv3["away"]["score"], liv3["home"]["score"] = "3", "0"
        _r, _i, tl3 = draw(liv3, "live3.png")
        _everything = texts + t2 + tl + tl2 + tl3
        # a postponed game has no score even when the feed sends zeros
        pp = st._game("den", state="post", status_short="Postponed")
        pp["away"]["score"], pp["home"]["score"] = "0", "0"
        if sb.game_share_row(pp)["score_away"] is not None:
            fails.append("share card: a postponed game draws a score")
        # plates that say why
        _r, _i, t3 = draw(st._game("dome"), "dome.png")
        if "DOME" not in t3 or any(re.fullmatch(r"\d+", t) for t in t3):
            fails.append(f"share card: a dome does not draw one plate saying Dome, no number: {t3}")
        _r, _i, t4 = draw(st._game("none"), "none.png")
        if "NO FORECAST" not in t4:
            fails.append(f"share card: a game with no conditions entry does not say No forecast: {t4}")
        _r, _i, t5 = draw(st._game("gap"), "gap.png")
        if t5.count("missing") != 3:
            fails.append(f"share card: a forecast with no numbers does not print missing: {t5}")
        # palette: every color painted in bulk is a token
        # pinned here as literals: importing the tuple would let a changed palette pass its own test
        tok = {(7, 17, 12), (7, 38, 25), (14, 59, 42), (20, 26, 23), (244, 241, 230),
               (255, 210, 63), (217, 211, 180), (184, 178, 147), (59, 58, 34)}
        if set(cr.WALL_PALETTE) != tok:
            fails.append(f"share card: WALL_PALETTE is not the nine ruled colors: {sorted(set(cr.WALL_PALETTE) ^ tok)}")
        cols = im.getcolors(maxcolors=1 << 22) or []
        off = [c for n, c in cols if n >= 400 and c not in tok]
        if off:
            fails.append(f"share card: colors outside the wall's token set paint 400 or more pixels: {off[:3]}")
        # outside NWS coverage: the page's one line, and no NWS credit with no NWS reading
        sb.CX_DATA["games"]["wem"] = {"status": "outside_nws", "venue": "Wembley Stadium",
                                      "words": {"line": "Outside NWS coverage"},
                                      "credit": {"text": "Conditions by GoCheckMyWeather, NWS, 8:34 PM ET"}}
        wem = st._game("wem", venue_city="London")
        _r, _i, tw = draw(wem, "wem.png")
        if "LONDON \u00b7 OUTSIDE NWS COVERAGE" not in tw:
            fails.append(f"share card: Wembley does not draw the page's one line, London and Outside NWS coverage: {tw}")
        if any(t.lower().startswith("conditions by") for t in tw):
            fails.append(f"share card: a game outside NWS coverage carries an NWS credit: {tw}")
        # one credit line on a forecast card, never the caps line and the stamp both
        cred = [t for t in texts if "conditions by" in t.lower()]
        if cred != ["Conditions by GoCheckMyWeather, NWS, 8:34 PM ET"]:
            fails.append(f"share card: the credit is not exactly one stamp line: {cred}")
        # a stamp from another day than the build's carries its day; the build's own day does not
        sb.CX_DATA["games"]["old"] = dict(st._entry(), nws={"generated_at": "2026-10-14T00:34:00Z"})
        sb.CX_DATA["games"]["new"] = dict(st._entry(), nws={"generated_at": "2026-10-15T12:34:00Z"})
        _r, _i, to = draw(st._game("old"), "old.png")
        _r, _i, tn = draw(st._game("new"), "new.png")
        if "Conditions by GoCheckMyWeather, NWS, Tue, Oct 13, 8:34 PM ET" not in to:
            fails.append(f"share card: an older reading does not carry its day: {[t for t in to if 'onditions' in t]}")
        if "Conditions by GoCheckMyWeather, NWS, 8:34 PM ET" not in tn:
            fails.append(f"share card: today's reading carries a day it does not need: {[t for t in tn if 'onditions' in t]}")
        _everything += t3 + t4 + tw + to + tn
        if any(re.search(r"\blive\b", t, re.I) for t in _everything):
            fails.append(f"share card: the word live is on a card: {[t for t in _everything if re.search(r'live', t, re.I)]}")
        # no em dash in anything the card draws
        if any("\u2014" in t for t in _everything):
            fails.append("share card: an em dash is drawn")
    finally:
        sb.CX_DATA, sb._NOW_CACHE = was
    return fails


def _og(html):
    g = lambda rx: (re.search(rx, html) or [None, None])[1]
    return {"image": g(r'<meta property="og:image" content="([^"]*)"'),
            "w": g(r'<meta property="og:image:width" content="([^"]*)"'),
            "h": g(r'<meta property="og:image:height" content="([^"]*)"'),
            "tw_image": g(r'<meta name="twitter:image" content="([^"]*)"'),
            "tw_card": g(r'<meta name="twitter:card" content="([^"]*)"')}


def check_tags():
    fails = []
    import site_build as sb
    import strip_canary as st
    was = (sb.CX_DATA, sb._NOW_CACHE)
    try:
        sb._NOW_CACHE = datetime.datetime(2026, 10, 15, 13, 0, tzinfo=datetime.timezone.utc)
        sb.CX_DATA = {"games": {"den": st._entry()}}
        o = _og(sb.render_game_page(st._game("den"), None, {}, {}, [], "Thursday"))
        want = f"{ORIGIN}/share/games/den-square.png"
        if o["image"] != want:
            fails.append(f"share tags: a game page's og:image is {o['image']!r}, not {want}")
        if (o["w"], o["h"]) != ("1080", "1080"):
            fails.append(f"share tags: a game page's og:image size is {o['w']}x{o['h']}, not 1080x1080")
        if o["tw_image"] != want:
            fails.append(f"share tags: twitter:image is {o['tw_image']!r}, not the same file")
        if o["tw_card"] != "summary":
            fails.append(f"share tags: twitter:card is {o['tw_card']!r} over a square image")
        d = _og(sb.shell("T", "d", "Home", "<main></main>", "Thursday", path="/x.html"))
        if (d["w"], d["h"], d["tw_card"]) != ("1200", "630", "summary_large_image"):
            fails.append(f"share tags: a page with no card of its own changed its default: {d}")
    finally:
        sb.CX_DATA, sb._NOW_CACHE = was
    return fails


def check_tree(out):
    fails = []
    gdir = os.path.join(out, "games")
    pages = sorted(f for f in os.listdir(gdir) if f.endswith(".html")) if os.path.isdir(gdir) else []
    if not pages:
        print("::warning::share tree: the build holds no game pages; tree checks not run")
        return fails
    try:
        from PIL import Image
    except ImportError:
        return ["share tree: Pillow is not installed, so the card files were not read"]
    for f in pages:
        gid = f[:-5]
        o = _og(open(os.path.join(gdir, f), encoding="utf-8").read())
        want = f"{ORIGIN}/share/games/{gid}-square.png"
        if o["image"] != want or o["tw_image"] != want:
            fails.append(f"share tree: {gid} names {o['image']!r} / {o['tw_image']!r}, not {want}")
            continue
        fp = os.path.join(out, "share", "games", f"{gid}-square.png")
        if not os.path.exists(fp):
            fails.append(f"share tree: {gid}'s og:image file is not in the tree")
            continue
        size = Image.open(fp).size
        if size != (1080, 1080) or (o["w"], o["h"]) != ("1080", "1080"):
            fails.append(f"share tree: {gid} tags say {o['w']}x{o['h']} and the file is {size[0]}x{size[1]}")
    return fails


def sharecard_canary(out=None):
    f = check_cards() + check_tags()
    if out:
        f += check_tree(out)
    return f


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else None
    f = sharecard_canary(root)
    for x in f:
        print("FAIL", x)
    print("share card canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
