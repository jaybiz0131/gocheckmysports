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

import os

from PIL import Image, ImageDraw, ImageFont

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


def _base(dark=False):
    im = Image.new("RGB", (W, H), BAND if dark else PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=GREEN)
    d.text((60, 44), "GoCheckMySports", font=_serif(38),
           fill=LIGHT if dark else INK)
    d.text((60, H - 74), "Every score. No odds. No noise.", font=_mono(22),
           fill=MUTED if not dark else (134, 139, 149))
    return im, d


def game_card(g, out_path):
    """Score, status and network. Nothing for a game with no score yet: the kickoff
    time is what an upcoming game has, and that is what it shows."""
    away, home = g.get("away") or {}, g.get("home") or {}
    started = g.get("state") in ("in", "post")
    im, d = _base(dark=True)
    d.text((60, 140), (g.get("status_short") or "").upper()[:34], font=_mono(26, True),
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
            d.text((W - 90 - d.textlength(s, font=_serif(96)), y - 10), s,
                   font=_serif(96), fill=LIGHT)
        y += 130
    net = g.get("network") or ""
    if net:
        tw = d.textlength(net, font=_mono(24, True))
        d.rectangle([60, H - 150, 60 + tw + 34, H - 150 + 46], fill=(42, 45, 53))
        d.text((77, H - 139), net, font=_mono(24, True), fill=LIGHT)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "PNG", optimize=True)
    return out_path


def inactives_card(board, out_path):
    """The count and the time. Both come straight off the board."""
    if not board or not board.get("teams"):
        return None
    im, d = _base()
    d.text((60, 150), "Today's inactives", font=_serif(72), fill=INK)
    big = str(board.get("total") or 0)
    d.text((60, 250), big, font=_serif(150), fill=GREEN)
    off = d.textlength(big, font=_serif(150))
    d.text((70 + off, 330), f"players listed across {len(board['teams'])} teams",
           font=_mono(28), fill=MUTED)
    stamp = board.get("last_change") or board.get("last_poll") or ""
    if stamp:
        d.text((60, 460), f"Updated {stamp[11:16]} UTC", font=_mono(24), fill=MUTED)
    d.text((60, 500), "Facts, not advice. Official reports only.",
           font=_mono(24), fill=MUTED)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "PNG", optimize=True)
    return out_path
