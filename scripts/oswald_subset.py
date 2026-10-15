#!/usr/bin/env python3
"""scripts/oswald_subset.py: make the site's Oswald (S-2d, Jack's scoreboard look of 14 October 2026).

  python3 scripts/oswald_subset.py SOURCE.woff2

SOURCE is Google Fonts' latin Oswald variable woff2 (v57, wght 200 to 700, SIL Open Font
License). The script limits the weight axis to 500..700 (the look uses 500, 600 and 700 only)
and keeps only OSWALD_TEXT: every Oswald surface on the site is set in capitals by CSS
(text-transform:uppercase, which the browser applies before it picks a glyph), so the subset
carries capitals, figures and the punctuation those surfaces print. It writes:

  site/assets/fonts/oswald.woff2   the face the pages load (500..700, variable)
  site/assets/fonts/Oswald-600.ttf a static 600 for Pillow (the share card); never shipped,
                                   the build deletes every .ttf from the publish tree

strip_canary checks every Oswald text on the built home and game pages against the woff2's own
character map, so a name the subset cannot draw fails the gate rather than falling back unseen.
Needs fonttools and brotli (pip install fonttools brotli); the build itself does not.
"""
import os
import sys

OSWALD_TEXT = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝ"
               "0123456789"
               " .,:;!?&'’()-–/+#%°·")

# the sha256 of the oswald.woff2 this script writes from Google's v57 latin file (sha256
# 571f3457dab507b6f2ce5394d593ca015251b69fea81ab7a546bd2368e9fc3ed); strip_canary fails when the
# shipped file is not this one
OSWALD_SHA256 = "f5e100d6df7fdaebd596fb802210e1c7b053d2b0ebf63e0d5050db7e6badc207"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "site", "assets", "fonts")


def main(src):
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    from fontTools import subset
    f = TTFont(src)
    f = instancer.instantiateVariableFont(f, {"wght": (500, 700)})
    opts = subset.Options()
    opts.layout_features = ["kern", "liga", "tnum", "lnum"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    s = subset.Subsetter(opts)
    s.populate(text=OSWALD_TEXT)
    s.subset(f)
    f.flavor = "woff2"
    f.recalcTimestamp = False      # keep the source's head.modified, so the bytes are reproducible
    w = os.path.join(OUT, "oswald.woff2")
    f.save(w)
    st = instancer.instantiateVariableFont(TTFont(w), {"wght": 600})
    st.flavor = None
    st.recalcTimestamp = False
    t = os.path.join(OUT, "Oswald-600.ttf")
    st.save(t)
    print(f"oswald: {os.path.getsize(w)} bytes woff2 (500..700, {len(set(OSWALD_TEXT))} characters), "
          f"{os.path.getsize(t)} bytes static 600 for Pillow")


if __name__ == "__main__":
    main(sys.argv[1])
