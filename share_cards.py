#!/usr/bin/env python3
"""share_cards.py: 1200x630 share cards, drawn at build (S-F).

WHY THEY EXIST. A link pasted into a group chat currently unfurls to the desk's generic
image, which tells a reader nothing. The point of these is that the NUMBER travels with
the link: the score and the network on a game, the count and the time on the inactives
board.

EVERY FIGURE COMES FROM THE SAME DATA THE PAGE RENDERS. There is no separate path that
could disagree with what the page says, and a card is not drawn at all when the page
has no number to put on it. A card that says 0-0 for a game that has not kicked off is
the same fabricated number the band was fixed for.
"""

import datetime as _dt
import os
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

_ET = ZoneInfo("America/New_York")


def _zone(text):
    """G-7: the feed's status_short carries the offset name of the day ("9/18 - 7:30 PM
    EDT"). One label all year on the card as on the page."""
    import re as _re
    return _re.sub(r"\b(EDT|EST)\b", "ET", str(text or ""))


def _et_clock(iso):
    """G-7: a card is reader-facing, so its clock is Eastern. This drew a raw UTC slice
    ("Updated 00:00 UTC"), which is the same defect S-11 cleared off the pages - and a
    card is the part of the site that travels furthest from it."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ"):
        try:
            t = _dt.datetime.strptime(iso, fmt).replace(tzinfo=_dt.timezone.utc)
            return t.astimezone(_ET).strftime("%-I:%M %p ET")
        except Exception:
            continue
    return ""


def _board_heading(board):
    """S-19's rule, on the card: name the day the board is actually showing. "Today's
    inactives" on a Monday card for Sunday's lists is wrong in a chat window for as long
    as the link survives, which is longer than the page is wrong for."""
    day = str((board or {}).get("day") or "")[:10]
    try:
        d = _dt.datetime.strptime(day, "%Y-%m-%d").date()
    except Exception:
        return "Today's inactives"
    today = _dt.datetime.now(_dt.timezone.utc).astimezone(_ET).date()
    if d == today:
        return "Today's inactives"
    if d == today - _dt.timedelta(days=1):
        return f"{d.strftime('%A')}'s inactives, final"
    return f"{d.strftime('%A %-d %B')} inactives"

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "site", "assets", "fonts")
W, H = 1200, 630
PAPER = (251, 250, 246)
INK = (23, 24, 28)
MUTED = (92, 97, 107)
GREEN = (31, 94, 63)
BAND = (19, 20, 25)
LIGHT = (235, 233, 227)


def _font(name, size):
    p = os.path.join(FONTS, name)
    try:
        return ImageFont.truetype(p, size)
    except Exception:
        return ImageFont.load_default()


def _serif(size):
    return _font("Newsreader.ttf", size)


def _mono(size, bold=False):
    return _font("IBMPlexMono-SemiBold.ttf" if bold else "IBMPlexMono-Medium.ttf", size)


def _fit(draw, text, font, max_w):
    """Trim to width rather than let it run off the card."""
    t = str(text or "")
    while t and draw.textlength(t, font=font) > max_w:
        t = t[:-1]
    return t


def _base(dark=False, wordmark=True):
    im = Image.new("RGB", (W, H), BAND if dark else PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=GREEN)
    # The small wordmark identifies a card whose subject is a number. On the default
    # card the wordmark IS the subject, so it is drawn once, large, and not twice.
    if wordmark:
        d.text((60, 44), "GoCheckMySports", font=_serif(38),
               fill=LIGHT if dark else INK)
    # THE 20 SEPTEMBER LAW RETIRES "No odds". The desk reports the line now, attributed,
    # so a card promising the opposite would be the site contradicting itself on the
    # thing a reader shares. What has not changed is the rest of it: no picks, no
    # advice, no book. "Checked" is the promise that survives all of that.
    d.text((60, H - 74), "Every score, checked. No noise.", font=_mono(22),
           fill=MUTED if not dark else (134, 139, 149))
    return im, d


def _lost(g, side):
    """Which side to mute: only at final, and only when the scores differ - the same
    rule the band uses. Muting a leader mid-game would call a result."""
    if g.get("state") != "post":
        return False
    try:
        a = int((g.get("away") or {}).get("score"))
        h = int((g.get("home") or {}).get("score"))
    except Exception:
        return False
    return (a < h) if side == "away" else (h < a)


def line_text(g):
    """C-5: what the card says about the line, and who it says set it, decided together.

    Returns ("", "") whenever there is no provider, so there is no path that paints a
    spread with nobody's name under it. It is a function rather than a branch inside the
    drawing code so it can be tested: a card is a PNG, and a canary cannot read one.

    A card is the part of this site that travels furthest from it and the part a reader
    is least able to check, which is the argument for the rule rather than against it.
    """
    line = g.get("line") or {}
    prov = line.get("provider") or ""
    if not prov:
        return ("", "")
    ruling = (g.get("ruling") or "").strip()
    if ruling:
        return (ruling, f"{prov} via ESPN")
    bits = [str(line["detail"])] if line.get("detail") else []
    if line.get("total") is not None:
        bits.append(f"O/U {line['total']}")
    if not bits:
        return ("", "")
    return ("  \u00b7  ".join(bits), f"{prov} via ESPN")


def game_card(g, out_path):
    """Score, status and network. Nothing for a game with no score yet: the kickoff
    time is what an upcoming game has, and that is what it shows."""
    away, home = g.get("away") or {}, g.get("home") or {}
    started = g.get("state") in ("in", "post")
    im, d = _base(dark=True)
    d.text((60, 140), _zone(g.get("status_short")).upper()[:34], font=_mono(26, True),
           fill=(61, 220, 132) if g.get("state") == "in" else (166, 171, 180))
    y = 210
    for side, t in (("away", away), ("home", home)):
        col = t.get("color") or ""
        try:
            rgb = tuple(int((col.lstrip("#"))[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            rgb = (42, 45, 53)
        d.rectangle([60, y + 6, 76, y + 74], fill=rgb)
        d.text((100, y), _fit(d, t.get("abbr") or "", _mono(54, True), 260),
               font=_mono(54, True), fill=LIGHT)
        d.text((100, y + 66), _fit(d, t.get("name") or "", _mono(24), 420),
               font=_mono(24), fill=(166, 171, 180))
        if started and t.get("score") not in (None, ""):
            s = str(t["score"])
            # Art direction: a card is the page in miniature, so a final mutes the
            # losing score here exactly as the scoreboard does.
            d.text((W - 90 - d.textlength(s, font=_serif(96)), y - 10), s,
                   font=_serif(96), fill=(122, 126, 136) if _lost(g, side) else LIGHT)
        y += 130
    net = g.get("network") or ""
    if net:
        tw = d.textlength(net, font=_mono(24, True))
        d.rectangle([60, H - 150, 60 + tw + 34, H - 150 + 46], fill=(42, 45, 53))
        d.text((77, H - 139), net, font=_mono(24, True), fill=LIGHT)

    # C-5: THE LINE TRAVELS WITH THE LINK, under the same law as the card on the page.
    # The number and the name that set it are drawn together, in one call, so there is
    # no path through this function that paints a spread with nobody's name under it.
    # A card is the part of this site that travels furthest from it and the part a
    # reader is least able to check, which is the argument for the rule rather than
    # against applying it here.
    txt, src = line_text(g)
    if txt and src:
        f1, f2 = _mono(26, True), _mono(20)
        x = W - 60 - d.textlength(txt, font=f1)
        d.text((x, H - 152), txt, font=f1, fill=LIGHT)
        d.text((W - 60 - d.textlength(src, font=f2), H - 118), src,
               font=f2, fill=(166, 171, 180))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "PNG", optimize=True)
    return out_path


def inactives_card(board, out_path):
    """The count and the time. Both come straight off the board."""
    if not board or not board.get("teams"):
        return None
    im, d = _base()
    d.text((60, 150), _board_heading(board), font=_serif(72), fill=INK)
    big = str(board.get("total") or 0)
    d.text((60, 250), big, font=_serif(150), fill=GREEN)
    off = d.textlength(big, font=_serif(150))
    d.text((70 + off, 330), f"players listed across {len(board['teams'])} teams",
           font=_mono(28), fill=MUTED)
    stamp = _et_clock(board.get("last_change") or board.get("last_poll") or "")
    if stamp:
        d.text((60, 460), f"Updated {stamp}", font=_mono(24), fill=MUTED)
    d.text((60, 500), "Facts, not advice. Official reports only.",
           font=_mono(24), fill=MUTED)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "PNG", optimize=True)
    return out_path


def og_card(out_path):
    """The default share card, for a page with no number of its own.

    THE WORDMARK IS ONE WORD. The committed og-image.png set it as "GoCheckMy Sports",
    spaced, which is the same identity split S-22 found on the Edition: a link unfurls
    to a wordmark the site does not use. Drawing it here rather than shipping a static
    PNG also means the card cannot drift from the site again - it is the same fonts,
    the same palette and the same band as every other card in this file."""
    im, d = _base(dark=True, wordmark=False)
    base, site = "GoCheckMy", "Sports"
    f = _serif(88)
    d.text((60, 210), base, font=f, fill=LIGHT)
    d.text((60 + d.textlength(base, font=f), 210), site, font=f, fill=(61, 220, 132))
    d.text((60, 340), "Sports news, checked against the record before it runs.",
           font=_serif(32), fill=(198, 202, 210))
    d.text((60, 140), "INDEPENDENT  ·  NO HOT TAKES", font=_mono(22, True),
           fill=(61, 220, 132))
    d.text((60, H - 150), "GOCHECKMYSPORTS.COM", font=_mono(24, True),
           fill=(166, 171, 180))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "PNG", optimize=True)
    return out_path
