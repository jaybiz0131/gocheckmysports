#!/usr/bin/env python3
"""fast_canary.py: S-DONE point 6, the two faults a Lighthouse read of production named. A fixture test.

Lighthouse itself is a report and never a gate (Jack's ruling of November 22); what it found on
November 25 on production is a rule of the code and is held here:

  aria-label   no div or span carries an aria-label without a role. The home's empty report slot
               did, and that one element was the whole of the home's accessibility score short of
               100 (96: "Elements use prohibited ARIA attributes").
  the scripts  the two scripts S-DONE adds to every board page (the re-read and the aged-page
               guard) ship without their indentation and together stay under SCRIPT_PIN bytes: the
               home is measured against HOME_BUDGET with them, and every byte they take is a
               college card the home does not draw.

USAGE  python3 fast_canary.py [TREE]
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCRIPT_PIN = 3600        # LIVE_JS + HONEST_JS, bytes as shipped


def aria(name, html):
    f = []
    body = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    for m in re.finditer(r"<(div|span)\b([^>]*\baria-label=[^>]*)>", body):
        if not re.search(r"\brole=", m.group(2)):
            f.append(f"fast: {name}: <{m.group(1)}{m.group(2)[:90]}> carries an aria-label with no role")
            break
    return f


def scripts():
    import site_build as sb
    f = []
    n = len(sb.LIVE_JS.encode("utf-8")) + len(sb.HONEST_JS.encode("utf-8"))
    if n > SCRIPT_PIN:
        f.append(f"fast: the re-read and the aged-page guard are {n} bytes on every board page, over the {SCRIPT_PIN} pin")
    for name, js in (("LIVE_JS", sb.LIVE_JS), ("HONEST_JS", sb.HONEST_JS)):
        if re.search(r"\n[ \t]+\S", js):
            f.append(f"fast: {name} ships its indentation")
        if "/*" in js or re.search(r"(?m)^\s*//", js):
            f.append(f"fast: {name} ships a comment")
    return f


def fast_canary(tree=None):
    import site_build as sb
    f = scripts()
    f += aria("the home (rendered)", sb.render_home([], ""))
    if tree and os.path.isdir(tree):
        games = sorted(os.listdir(os.path.join(tree, "games")))[:1] if os.path.isdir(os.path.join(tree, "games")) else []
        for rel in ["index.html", "scores.html", "about.html", "fantasy/index.html"] + ["games/" + g for g in games]:
            p = os.path.join(tree, rel)
            if os.path.exists(p):
                f += aria("/" + rel, open(p, encoding="utf-8").read())
    return f


if __name__ == "__main__":
    fs = fast_canary(sys.argv[1] if len(sys.argv) > 1 else None)
    for x in fs:
        print("::error::" + x)
    print("FAST CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
