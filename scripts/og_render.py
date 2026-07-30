#!/usr/bin/env python3
"""
og_render.py: render the share surfaces (Open Graph cards, home-screen icon) in PURE Python
(Pillow). No Chromium, no LLM, no image model, and nothing per-article committed to the
repo: site_build.py calls these at BUILD time (which runs on Netlify), writing straight into
the publish output. The brand fonts under site/assets/fonts/ are the only committed asset (a
one-time static dependency, not per-article growth).

DESIGN, approved by the owner 2026-07-30 ("design D", then the background mark):
  Ink ground, not newsprint. A share card competes in a feed, and cream-on-white lost.
  The GoCheckMy___ wordmark is the hero, the site half in the accent and italic, matching
  the masthead lockup.
  Behind it, a low-contrast mark drawn from the desk's OWN SUBJECT: candlesticks for crypto,
  a broadsheet column grid for news, a tournament bracket for sports. This replaced an
  oversized family seal, which duplicated the small check beside the domain and said the
  same thing twice at two sizes. The mark is what makes the three cards tellable apart in a
  feed while the wordmark, rule, and layout stay identical across the family.
  A halftone dot screen over everything, for printed depth without an image asset.

The byline persona (Crypto Cronkite, Charles Independence, Chuck Wando) is the writer, not
the brand, and never appears on a share card. Nothing here may describe how the desk works:
a share card is the one surface strangers see, and the process is not published.
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "site", "assets", "fonts")

# ---- BRAND: the only per-desk block. Porting this file to another desk means editing
# these ten lines and nothing else.
BRAND_BASE = "GoCheckMy"       # constant across the family
BRAND_SITE = "Sports"          # the half that carries the accent
DOMAIN = "gocheckmysports.com"
PROMISE = "Sports news, checked against the record before it runs."
STRAP = "INDEPENDENT  ·  NO HOT TAKES"
FOOT_NOTE = "Never betting advice"
MARK = "bracket"               # candles | columns | bracket

PAPER = (251, 250, 246)   # #FBFAF6
INK = (23, 24, 28)        # #17181C
MUTED = (92, 97, 107)     # #5C616B
LINE = (230, 226, 216)    # #E6E2D8
RULE = (31, 94, 63)       # #1F5E3F, the accent on paper
# The card ground is ink, so the card uses the accent this desk already owns for its own
# dark theme (--rule under prefers-color-scheme: dark). The paper accent is a deep tone
# picked to sit on cream; on near-black it goes muddy. This is not a new brand colour.
RULE_DARK = (87, 192, 138)# #57C08A
GROUND = (16, 17, 20)      # the card ground, a touch deeper than INK

# The watermark palette: three steps just off the ground. Depth, not decoration. If any of
# these reads as a figure rather than a texture, it is too bright.
WM_LINE = (44, 46, 52)
WM_FILL = (30, 32, 37)
WM_LIFT = (58, 60, 68)

W, H = 1200, 630
PAD_X, PAD_TOP = 72, 64

_MONO_SB = os.path.join(FONTS, "IBMPlexMono-SemiBold.ttf")
_MONO_MD = os.path.join(FONTS, "IBMPlexMono-Medium.ttf")
_SERIF = os.path.join(FONTS, "Newsreader.ttf")


def _serif(size, weight=600):
    f = ImageFont.truetype(_SERIF, size)
    try:
        f.set_variation_by_axes([weight])  # Newsreader is a variable font
    except Exception:
        pass
    return f


def _tracked(draw, xy, text, font, fill, tracking):
    """Draw text with letter-spacing (Pillow has none natively). Returns the end x."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x - tracking


def _tracked_width(draw, text, font, tracking):
    return sum(draw.textlength(ch, font=font) + tracking for ch in text) - tracking


def _wrap(draw, text, font, max_w, max_lines):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = wd
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and (len(" ".join(lines)) < len(text)):
        while lines and draw.textlength(lines[-1] + "...", font=font) > max_w:
            lines[-1] = lines[-1].rsplit(" ", 1)[0] if " " in lines[-1] else lines[-1][:-1]
        lines[-1] = lines[-1].rstrip(",. ") + "..."
    return lines


def _headline_size(n):
    return 74 if n <= 42 else 62 if n <= 72 else 52 if n <= 104 else 44


def _check(d, cx, cy, r, color, bg=None, weight=None):
    """The GoCheckMy check, drawn on a disc. Pillow has no SVG, and rasterising one would
    add a dependency for three strokes, so this is the mark in primitives. Coordinates are
    proportional to r so the same call works at icon size and at card size."""
    if bg is not None:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        stroke = bg
    else:
        stroke = color
    w = weight or max(3, int(r * 0.26))
    pts = [(cx - r * 0.46, cy + r * 0.02),
           (cx - r * 0.12, cy + r * 0.40),
           (cx + r * 0.50, cy - r * 0.42)]
    d.line(pts, fill=stroke, width=w, joint="curve")
    # round the ends: Pillow's line has no linecap
    for px, py in (pts[0], pts[-1]):
        d.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill=stroke)


def _italic(img, text, xy, font, fill, slant=0.21):
    """Newsreader ships no italic face, and the masthead lockup sets the site half in
    italic by owner directive. Shear a transparent layer of the real letterforms rather
    than substitute a different family, which would break the lockup."""
    x, y = xy
    pad = int(font.size * 1.2)
    lay = Image.new("RGBA", (int(font.size * max(1, len(text)) * 1.1) + pad * 2,
                             int(font.size * 2.0) + pad), (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((pad, pad // 2), text, font=font, fill=fill)
    dx = int(lay.height * slant)
    lay = lay.transform((lay.width + dx, lay.height), Image.AFFINE,
                        (1, slant, -slant * lay.height, 0, 1, 0), resample=Image.BICUBIC)
    img.alpha_composite(lay, (int(x) - pad, int(y) - pad // 2))


def _wordmark_dark(img, x, y, size, accent):
    """GoCheckMy in paper + the site word in accent italic, on the ink ground. The hero of
    every share surface. Returns the end x."""
    d = ImageDraw.Draw(img)
    f = _serif(size, 700)
    d.text((x, y), BRAND_BASE, font=f, fill=PAPER)
    x2 = x + d.textlength(BRAND_BASE, font=f)
    _italic(img, BRAND_SITE, (x2, y), f, accent)
    return x2 + d.textlength(BRAND_SITE, font=f) * 1.04


def _mix(c, t):
    """Fade a watermark colour toward the ground. t=1 is full strength."""
    return tuple(int(GROUND[i] + (c[i] - GROUND[i]) * t) for i in range(3))


def _data_mark(img, strength=1.0):
    """The desk's own subject, drawn as its data shape, bleeding off the right edge.

    Per-desk by design: this is the one element that differs between the three cards, and
    the reason a reader can tell them apart at feed size. Everything is geometric and
    proportional, so it never needs updating when content does.

    strength fades it toward the ground. Article cards pass a lower value, because there a
    four-line headline is the subject and the mark is only texture behind it.
    """
    d = ImageDraw.Draw(img)
    ln, fl, lf = _mix(WM_LINE, strength), _mix(WM_FILL, strength), _mix(WM_LIFT, strength)

    if MARK == "candles":
        # A candle series: a run up, a sharp drawdown, and off the edge mid-move.
        xs = list(range(660, W + 90, 46))
        highs = [420, 380, 396, 330, 348, 282, 300, 236, 268, 322, 384, 356, 300]
        lows = [520, 486, 500, 452, 466, 400, 424, 356, 396, 452, 500, 470, 420]
        for i, x in enumerate(xs):
            hi, lo = highs[i % len(highs)], lows[i % len(lows)]
            d.line([(x, hi - 34), (x, lo + 34)], fill=ln, width=3)
            up = i % 3 != 2
            d.rectangle([x - 15, min(hi, lo), x + 15, max(hi, lo)],
                        fill=fl if up else None, outline=lf if up else ln, width=3)

    elif MARK == "bracket":
        # Four into two into one, the final opening off the right edge. Positioned clear of
        # where the site word ends, so the wordmark never sits on a bracket rule.
        def rung(x, y, span, arm, w):
            d.line([(x, y - span), (x + arm, y - span)], fill=ln, width=w)
            d.line([(x, y + span), (x + arm, y + span)], fill=ln, width=w)
            d.line([(x + arm, y - span), (x + arm, y + span)], fill=ln, width=w)
            d.line([(x + arm, y), (x + arm + 62, y)], fill=lf, width=w)
        for y in (108, 300, 492):
            rung(810, y, 76, 60, 5)
        rung(932, 300, 192, 66, 6)
        d.line([(1190, 300), (W + 20, 300)], fill=lf, width=7)

    else:  # columns
        # A broadsheet column grid, cropped off the top and right so it reads as a page
        # continuing past the frame rather than an icon floating in space. Text is set as
        # rule-lines with ragged right edges; nothing is legible, and nothing should be.
        for col in range(4):
            cx = 700 + col * 152
            d.line([(cx - 20, -20), (cx - 20, H - 40)], fill=fl, width=2)
            y, n = -26, 0
            while y < H - 52:
                if n % 12 in (0, 9):
                    d.rectangle([cx, y, cx + 114, y + 17], fill=ln)   # a headline
                    y += 36
                else:
                    ragged = 114 - (28 if n % 7 == 6 else 0) - (46 if n % 11 == 10 else 0)
                    d.rectangle([cx, y, cx + ragged, y + 5], fill=fl)
                    y += 15
                n += 1


def _halftone(img, alpha=8, spacing=8, radius=1.1):
    """A printed dot screen over the whole card. This is what stops a flat dark rectangle
    from looking like a flat dark rectangle, and it costs one composite."""
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for y in range(0, img.size[1], spacing):
        for x in range(0, img.size[0], spacing):
            d.ellipse([x - radius, y - radius, x + radius, y + radius],
                      fill=(255, 255, 255, alpha))
    return Image.alpha_composite(img, lay)


def _ground(mark_strength=1.0):
    """Every share card starts the same way: ink, the desk's mark, the dot screen, the
    accent rule across the top. Shared so the site card and the article cards cannot drift
    apart, which is exactly what happened to the last generation of these."""
    img = Image.new("RGBA", (W, H), GROUND + (255,))
    _data_mark(img, mark_strength)
    img = _halftone(img)
    ImageDraw.Draw(img).rectangle([0, 0, W, 9], fill=RULE_DARK)
    return img


def render_site_card(out_path):
    """The card for the homepage and anything without its own. Strap, wordmark, the promise,
    and the domain lockup. No byline, no process, no claim we cannot stand behind."""
    img = _ground()
    d = ImageDraw.Draw(img)

    _tracked(d, (PAD_X, 128), STRAP, ImageFont.truetype(_MONO_SB, 17), RULE_DARK, 3.4)
    _wordmark_dark(img, PAD_X, 186, 116, RULE_DARK)
    d = ImageDraw.Draw(img)
    d.text((PAD_X, 352), PROMISE, font=_serif(34, 400), fill=(178, 183, 192))

    # the family mark, once, beside the domain. It is small here because the background is
    # no longer a second copy of it.
    _check(d, PAD_X + 24, H - 116, 30, RULE_DARK, bg=PAPER, weight=10)
    _tracked(d, (PAD_X + 74, H - 128), DOMAIN.upper(),
             ImageFont.truetype(_MONO_MD, 17), (132, 137, 147), 2.2)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


def render_icon(out_path, size=180):
    """Home-screen icon: the full family mark, drawn at whatever size is asked for.

    This is the committed logo rebuilt in primitives, not a simplification of it: ink
    ground, the accent ring, a cream disc, the two broadcast arcs, and the check. The ONE
    change from what shipped is that the ring takes the desk's own accent, because all three
    desks previously shipped a byte-identical icon and three saved icons were
    indistinguishable on a home screen.

    Drawn rather than committed so the three stay in sync: an icon that is generated from
    the same constants as the cards cannot drift away from them.
    """
    s = size / 540.0            # proportions measured off the committed 180px original
    img = Image.new("RGB", (size, size), INK)
    d = ImageDraw.Draw(img)
    c = size / 2

    def circle(r, **kw):
        d.ellipse([c - r, c - r, c + r, c + r], **kw)

    circle(201 * s, fill=RULE)                        # the accent ring
    circle(170 * s, fill=PAPER)                       # the cream disc
    circle(152 * s, outline=RULE, width=max(1, int(4 * s)))   # the thin inner ring

    # the two broadcast arcs, struck above the centre
    ac = (c, c - 8 * s)
    aw = max(2, int(15 * s))
    for r in (92 * s, 56 * s):
        d.arc([ac[0] - r, ac[1] - r, ac[0] + r, ac[1] + r], 202, 338, fill=INK, width=aw)
        # round the arc ends, which Pillow's arc does not do
        for ang in (202, 338):
            px = ac[0] + r * math.cos(math.radians(ang))
            py = ac[1] + r * math.sin(math.radians(ang))
            d.ellipse([px - aw / 2, py - aw / 2, px + aw / 2, py + aw / 2], fill=INK)

    _check(d, c, c + 22 * s, 88 * s, INK, weight=max(4, int(34 * s)))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def render_card(headline, kicker, out_path):
    """A story's own card. Same ground and mark as the site card, so a shared story and a
    shared homepage look like the same publication. The mark is faded here: the headline is
    the subject and the mark is texture behind it, which also keeps the headline full width
    instead of squeezed into a column beside a figure."""
    img = _ground(mark_strength=0.62)
    d = ImageDraw.Draw(img)
    content_w = W - 2 * PAD_X

    # ---- masthead: the wordmark, then the rule ----
    _wordmark_dark(img, PAD_X, PAD_TOP - 8, 40, RULE_DARK)
    d = ImageDraw.Draw(img)
    rule_y = PAD_TOP + 52
    d.rectangle([PAD_X, rule_y, W - PAD_X, rule_y + 3], fill=RULE_DARK)

    kick_f = ImageFont.truetype(_MONO_SB, 19)
    size = _headline_size(len(headline))
    hf = _serif(size, 600)
    lines = _wrap(d, headline, hf, content_w, 4)
    lh = int(size * 1.08)

    # vertical centring: kicker + headline as one block in the space between the rule and
    # the foot rule. A two-line headline used to sit high and leave a visible hole.
    foot_rule_y = H - PAD_TOP - 34
    block_h = 40 + lh * len(lines)
    ky = rule_y + max(26, int((foot_rule_y - rule_y - block_h) / 2))
    _tracked(d, (PAD_X, ky), (kicker or BRAND_SITE + " news").upper(), kick_f, RULE_DARK, 3.0)
    hy = ky + 40
    for ln in lines:
        d.text((PAD_X, hy), ln, font=hf, fill=PAPER)
        hy += lh

    # ---- foot: line, domain left, disclaimer right ----
    foot_f = ImageFont.truetype(_MONO_MD, 16)
    fy = H - PAD_TOP - 34
    d.rectangle([PAD_X, fy, W - PAD_X, fy + 1], fill=(52, 55, 62))
    _tracked(d, (PAD_X, fy + 20), DOMAIN, foot_f, (132, 137, 147), 0.8)
    nfa_sb = ImageFont.truetype(_MONO_SB, 16)
    nfa_w = _tracked_width(d, FOOT_NOTE, nfa_sb, 0.8)
    _tracked(d, (W - PAD_X - nfa_w, fy + 20), FOOT_NOTE, nfa_sb, RULE_DARK, 0.8)
    # the family mark, once, left of the disclaimer
    _check(d, W - PAD_X - nfa_w - 34, fy + 28, 15, RULE_DARK, bg=PAPER)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--headline")
    ap.add_argument("--kicker", default=BRAND_SITE + " News")
    ap.add_argument("--site-card", action="store_true")
    ap.add_argument("--icon", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.site_card:
        print("wrote", render_site_card(a.out))
    elif a.icon:
        print("wrote", render_icon(a.out))
    else:
        print("wrote", render_card(a.headline, a.kicker, a.out))
