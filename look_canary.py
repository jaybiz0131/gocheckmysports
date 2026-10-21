#!/usr/bin/env python3
"""look_canary.py: S-5.5, one look on every page a reader can reach.

Scorecard line 5 (docs/BOARD.md) is scored on the site: the S-2d scoreboard look and nothing beside
it, on every page, not on the home, the game pages and the team pages alone. strip_canary holds the
look where it was built. This canary walks EVERY page the gate's build wrote (all of them are
reachable; the three sitemap files are a subset and are checked to resolve), and names each page
that fails, by URL, so a failure is never a count.

Each check names the break it exists for and was seen red first (U-9, U-15).

  resolve   every URL the three sitemap files list is a page the build wrote
  colors    a page's markup (style attributes, SVG paint attributes, inline <style>) carries only
            colors from the token set: the :root tokens of site.css in both themes, the S-2d palette,
            and a team's own colors (team-colors.json, the scoreboard feed, the CFB registry), which
            are colors and never logos. Scripts and URL fragments are not colors
  sheet     the only stylesheet is /assets/site.css, the only font preloads are self-hosted woff2,
            and the only script sources are the hosts the October 14 ruling names
  chrome    the masthead (brand, dateline, nav) is the home's, and the footer is the home's (the
            fantasy pages add their own note line and nothing else)
  wears     every page other than the home, a game page and a team page (which are built in the look)
            wears it: body.sbp, one main landmark, one h1; a bare page is wrapped by the shell
  oswald    every element a converted page RENDERS in Oswald, whichever rule put it there (the browser's
            computed font names it; no class list is kept by hand), is made only of characters the
            pinned subset carries, read after text-transform, so a rule that does not uppercase is
            read as the mixed case it prints. Round 2 of S-5.5: .tk-num set the matchup in Oswald
            with no uppercase and no lowercase in the subset
  rendered  the computed color, background and border colors of everything displayed inside main on
            a converted page are in the token set, the shipped S-2d bulb colors and a team's colors:
            a stylesheet color on a page is read where the markup check cannot see it (.fw-odd)
  css       site.css, read as text: every `color:` a body.sbp rule sets clears 4.5:1 on the frame, the
            panel and a plate, and every color value (hex, rgb, rgba, hsl, a named color) in ANY
            declaration of a rule that names body.sbp (backgrounds, borders, outlines, fills, strokes,
            shadows, gradients, custom properties) is a token, a S-2d bulb color or a team color, alpha
            ignored as the browser read ignores it. Black and white are allowed in a box-shadow or
            text-shadow only (a shade is not a color of the look). A rule without body.sbp in its
            selector is not judged here; the rendered sweep judges it where it lands
  sweep     round 3 of S-5.5: the rendered half reads EVERY converted page, not a sample (a sample let a
            color on /fantasy/injuries.html and /standings/mlb.html through). The pages read are
            counted in both themes and the canary fails when either count is under the converted set

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import html as _html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "https://gocheckmysports.com"
S2D = ("#0e3b2a", "#072619", "#141a17", "#f4f1e6", "#ffd23f", "#ffe680")
# the pages built in the look by S-2d and S-3a; they are checked for colors, sheet and chrome, and
# are not asked to carry the S-5.5 wrapper
BUILT_IN_LOOK = re.compile(r"^(index\.html|games/[^/]+\.html|teams/.+\.html)$")
# the two bulb colors main's shipped S-2d CSS (site.css, the .sbc lamp rules) prints on the board
BULBS = ("#a7a285", "#3b3a22")
SWEEP_TIMEOUT = 900
SCRIPT_HOSTS = ("static.cloudflareinsights.com",)
HEX = re.compile(r"#[0-9A-Fa-f]{8}\b|#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")


def _norm(c):
    c = c.lower().replace(" ", "")
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        c = "#" + "".join(ch * 2 for ch in c[1:])
    return c[:7] if re.fullmatch(r"#[0-9a-f]{8}", c) else c


def _css(root=None):
    return open(os.path.join(root or HERE, "site", "assets", "site.css"), encoding="utf-8").read()


def token_colors(css=None):
    """Every color the :root blocks of site.css name, in both themes, plus the S-2d palette."""
    css = css if css is not None else _css()
    out = set(S2D)
    for blk in re.findall(r":root[^{]*\{([^{}]*)\}", css):
        for c in HEX.findall(blk):
            out.add(_norm(c))
    return out


def team_colors(root=None):
    """The colors teams own, read from the data the pages are built from."""
    root = root or HERE
    out = set()

    def walk(x, key=""):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, str(k).lower())
        elif isinstance(x, list):
            for v in x:
                walk(v, key)
        elif isinstance(x, str) and "color" in key and re.fullmatch(r"#[0-9A-Fa-f]{3,8}", x.strip()):
            out.add(_norm(x.strip()))
    for rel in ("site/data/team-colors.json", "site/data/scoreboard.json", "data/cfb-teams-built.json",
                "site/data/standings.json", "site/data/scores.json"):
        fp = os.path.join(root, rel)
        if os.path.exists(fp):
            try:
                walk(json.load(open(fp, encoding="utf-8")))
            except Exception:
                pass
    return out


def pages(out):
    """Every .html the build wrote, as paths relative to the tree."""
    res = []
    for r, _, fs in os.walk(out):
        for f in fs:
            if f.endswith(".html"):
                res.append(os.path.relpath(os.path.join(r, f), out).replace(os.sep, "/"))
    return sorted(res)


def sitemap_files(out):
    """(unresolved URLs, resolved relative paths) from the three sitemap files."""
    bad, ok = [], []
    for n in ("sitemap-priority.xml", "sitemap-archive.xml", "news-sitemap.xml"):
        fp = os.path.join(out, n)
        if not os.path.exists(fp):
            bad.append(n)
            continue
        for u in re.findall(r"<loc>([^<]*)</loc>", open(fp, encoding="utf-8").read()):
            p = u.replace(ORIGIN, "").strip("/") or "index"
            for c in (p + ".html", p + "/index.html"):
                if os.path.exists(os.path.join(out, c)):
                    ok.append(c)
                    break
            else:
                bad.append(u)
    return bad, ok


def _strip_scripts(h):
    return re.sub(r"<script\b.*?</script>", "", h, flags=re.S | re.I)


def stray_colors(h, allowed):
    """Colors in a page's markup that are not in the allowed set."""
    h = _strip_scripts(h)
    # a URL fragment (href="/scores.html#cfb", url(#glow)) is not a color
    h = re.sub(r'\b(?:href|src|xlink:href|action|data-href|poster)="[^"]*"', "", h)
    h = re.sub(r"url\(\s*#[^)]*\)", "", h)
    h = re.sub(r"\bid=\"[^\"]*\"", "", h)
    bad = set()
    for c in HEX.findall(_html.unescape(h)):
        n = _norm(c)
        if n not in allowed:
            bad.add(n)
    return sorted(bad)


def _block(h, rx):
    m = re.search(rx, h, re.S)
    return m.group(0) if m else None


def _mast(h):
    m = _block(h, r'<header class="masthead">.*?</nav>')
    return re.sub(r" class=active", "", m) if m else None


def _foot(h):
    return _block(h, r'<footer class="site">.*?</footer>')


def _fantasy_note(f):
    return re.sub(r'<p class="fnote">.*?</p>', "", f or "", flags=re.S)


def _luminance_fail(css):
    sc = _strip()
    fails = []
    css = re.sub(r"@media print\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", css)   # print is ink on paper, not the board
    grounds = {"the frame": sc._rgb(sc.FRAME), "the panel": sc._rgb(sc.PANEL), "a plate": sc._rgb(sc.PLATE)}
    n = 0
    for sel, decl in sc._rules(css, rx=r"^body\.sbp\b"):
        for c in re.findall(r"(?:^|;)\s*color\s*:\s*(#[0-9A-Fa-f]{6})\b", decl):
            n += 1
            for gname, g in grounds.items():
                r = sc.contrast(sc._rgb(c), g)
                if r < 4.5:
                    fails.append(f"css: {sel[:60]} sets {c} at {r:.2f}:1 on {gname}, under 4.5:1")
    if n == 0:
        fails.append("css: site.css has no body.sbp color rule, so the look has no text colors to check")
    return fails

NAMED = set("""aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown
burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred
darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink
deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold
goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush
lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey
lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime
limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise
palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue
saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow
springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen""".split())
# properties whose value can name a color by word; a hex or rgb in ANY declaration is read
COLOR_PROPS = re.compile(r"^(?:--[\w-]+|color|background(?:-color|-image)?|border(?:-[a-z]+)*|outline(?:-color)?|"
                         r"fill|stroke|box-shadow|text-shadow|text-decoration(?:-color)?|caret-color|accent-color|"
                         r"column-rule(?:-color)?)$")


def _decl_colors(prop, val):
    """(color, kind) for every color a declaration names: hex, rgb(a), hsl(a), and named colors on a color property."""
    val = re.sub(r"url\([^)]*\)", "", val)
    val = re.sub(r"var\(--[\w-]+\)", "", val)
    out = [c for c in HEX.findall(val)]
    if COLOR_PROPS.match(prop.strip().lower()):
        out += [w for w in re.findall(r"(?<![\w#-])[a-z]+(?![\w(-])", val.lower()) if w in NAMED]
    return out


def _token_fail(css, allowed):
    """Static: every color a body.sbp rule names is in the allowed set (tokens, bulbs, teams)."""
    sc = _strip()
    fails, n = [], 0
    css = re.sub(r"@media print\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", css)
    ok = {h for h in (_hex_of(c) for c in allowed) if h}
    for sel, decl in sc._rules(css, rx=r"body\.sbp\b"):
        for prop, val in re.findall(r"(?:^|;)\s*([a-zA-Z-]+)\s*:\s*([^;]*)", decl):
            for c in _decl_colors(prop, val):
                n += 1
                if c.lower() in NAMED:
                    if c.lower() in ("black", "white") and prop.lower() in ("box-shadow", "text-shadow"):
                        continue
                    fails.append(f"css token: {sel[:70]} sets {prop} to the named color {c}, which is not a token")
                    continue
                h = _hex_of(c)
                if h in ("#000000", "#ffffff") and prop.lower() in ("box-shadow", "text-shadow"):
                    continue
                if h is None or h not in ok:
                    fails.append(f"css token: {sel[:70]} sets {prop} to {c.strip()}, which is not a token, a bulb or a team color")
    if n == 0:
        fails.append("css token: no color was read from any body.sbp rule, so the token check proves nothing")
    return fails


def _strip():
    import importlib
    import sys
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    return importlib.import_module("strip_canary")


def _oswald_chars():
    import importlib.util
    spec = importlib.util.spec_from_file_location("oswald_subset", os.path.join(HERE, "scripts", "oswald_subset.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return set(m.OSWALD_TEXT)


def oswald_selectors(css=None):
    """The body.sbp selectors site.css itself sets in the display face (Oswald), read from the sheet."""
    css = css if css is not None else _css()
    sc = _strip()
    out = []
    for sel, decl in sc._rules(css, rx=r"^body\.sbp\b"):
        if re.search(r"(?:^|;)\s*font(?:-family)?\s*:[^;]*oswald", decl, re.I):
            out.append(sel)
    return out


def _hex_of(c):
    """A token written as rgb(a) as #rrggbb, for the browser's computed colors."""
    c = _norm(c)
    if c.startswith("#"):
        return c
    m = re.fullmatch(r"rgba?\(([^)]*)\)", c)
    if m:
        p = re.split(r"[,/ ]+", m.group(1))
        try:
            return "#" + "".join("%02x" % round(float(x)) for x in p[:3])
        except ValueError:
            return None
    return None


def sweep_pages(pgs):
    """The converted pages the rendered sweep opens: ALL of them (round 3 of S-5.5; a sample of one
    page per directory let an off-token color on /fantasy/injuries.html and /standings/mlb.html
    through). The pages built in the look by S-2d and S-3a are the only ones left out."""
    return [p for p in pgs if not BUILT_IN_LOOK.match(p)]


def rendered_sweep(out, pgs, allowed, osw):
    """The browser half: scripts/look-sweep.mjs over the pages, its findings as failure strings."""
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if not node:
        return ["look rendered: node is not installed, so no page was read in a browser"]
    tmp = tempfile.mkdtemp(prefix="look-sweep-")
    try:
        cfgp = os.path.join(tmp, "config.json")
        with open(cfgp, "w", encoding="utf-8") as f:
            json.dump({"pages": pgs, "allowed": sorted(allowed), "oswald": "".join(sorted(osw))}, f)
        try:
            r = subprocess.run([node, os.path.join(HERE, "scripts", "look-sweep.mjs"), out, cfgp],
                               capture_output=True, text=True, timeout=SWEEP_TIMEOUT)
        except subprocess.TimeoutExpired:
            return ["look rendered: the browser sweep timed out"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    fails, group, summary = [], {}, None
    for line in r.stdout.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if "fail" in o:
            fails.append("look rendered: " + o["fail"])
        elif "summary" in o:
            summary = o["summary"]
        elif o.get("kind") == "oswald":
            group.setdefault(("oswald", o["el"]), []).append(o)
        elif o.get("kind") == "color":
            group.setdefault(("color", o["el"], o["prop"], o["color"]), []).append(o)
        else:
            fails.append("look rendered: " + json.dumps(o))
    for k, v in sorted(group.items()):
        pg = sorted({x["page"] for x in v})
        where = ", ".join(pg[:3]) + (f" and {len(pg) - 3} more" if len(pg) > 3 else "")
        if k[0] == "oswald":
            odd = sorted({c for x in v for c in x["odd"]})
            texts = sorted({x["text"] for x in v})
            fails.append(f"look oswald: {where}: {k[1]} renders in Oswald (text-transform {v[0]['transform']}) "
                         f"{len(texts)} text(s) the subset cannot draw, e.g. \"{texts[0]}\" ({''.join(odd[:8])})")
        else:
            fails.append(f"look rendered: {where}: {k[1]} renders {k[2]} {k[3]} (\"{v[0]['text']}\"), "
                         f"outside the token set")
    if summary is None and not fails:
        fails.append("look rendered: the browser sweep wrote no summary" + (": " + r.stderr[-200:] if r.stderr else ""))
    elif summary is not None and not summary.get("measured") and not fails:
        fails.append("look rendered: the browser sweep measured nothing")
    if summary is not None:
        for sch in ("light", "dark"):
            got = summary.get("read_" + sch, 0)
            if got != len(pgs):
                fails.append(f"look rendered: the {sch} sweep read {got} of the {len(pgs)} converted pages, "
                             f"so a page a reader can reach was not read")
        print(f"look sweep: {summary.get('read_light', 0)} of {len(pgs)} converted pages read in light and "
              f"{summary.get('read_dark', 0)} in dark at 390 wide, {summary.get('measured', 0)} elements, "
              f"{summary.get('signatures', 0)} tag+class signatures, {summary.get('findings', 0)} findings, "
              f"{summary.get('seconds', 0)} s in the browser")
    return fails


def look_canary(out, root=None):
    fails = []
    if not out or not os.path.isdir(out):
        return ["look: the gate's build wrote no tree, so no page was checked"]
    css = _css(root)
    allowed = token_colors(css) | team_colors(root)
    unresolved, listed = sitemap_files(out)
    for u in unresolved:
        fails.append(f"look resolve: the sitemaps list {u} and the build wrote no such page")
    allp = pages(out)
    missing = sorted(set(listed) - set(allp))
    for m in missing:
        fails.append(f"look resolve: {m} is listed and not built")
    if "index.html" not in allp:
        return fails + ["look: the build has no home page"]
    home = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    hm, hf = _mast(home), _foot(home)
    if not hm or not hf:
        fails.append("look chrome: the home has no masthead or footer to compare against")
    osw = _oswald_chars()
    n_wear = 0
    for p in allp:
        h = open(os.path.join(out, p), encoding="utf-8").read()
        name = "/" + p
        # colors
        bad = stray_colors(h, allowed)
        if bad:
            fails.append(f"look colors: {name} carries {len(bad)} color(s) outside the token set: {bad[:4]}")
        # sheet
        sheets = re.findall(r'<link[^>]+rel="stylesheet"[^>]*href="([^"]*)"', h)
        sheets += re.findall(r'<link[^>]+href="([^"]*)"[^>]*rel="stylesheet"', h)
        if any(not s.split("?")[0] == "/assets/site.css" for s in sheets):
            fails.append(f"look sheet: {name} loads a stylesheet besides /assets/site.css: {sheets[:3]}")
        for f in re.findall(r'<link[^>]+rel="preload"[^>]+as="font"[^>]*href="([^"]*)"', h):
            if not (f.startswith("/assets/fonts/") and f.endswith(".woff2")):
                fails.append(f"look sheet: {name} preloads a font that is not self-hosted woff2: {f}")
        for s in re.findall(r'<script[^>]+src="([^"]*)"', h):
            if s.startswith("http") and not any(x in s for x in SCRIPT_HOSTS):
                fails.append(f"look sheet: {name} loads a script from a host the rulings do not allow: {s[:60]}")
        # chrome
        if _mast(h) != hm:
            fails.append(f"look chrome: {name} does not carry the home's masthead, brand, dateline and nav")
        f = _foot(h)
        if f is None:
            fails.append(f"look chrome: {name} has no footer")
        elif f != hf and _fantasy_note(f) != _fantasy_note(hf):
            fails.append(f"look chrome: {name} does not carry the home's footer")
        if BUILT_IN_LOOK.match(p):
            continue
        # wears the look
        n_wear += 1
        body = re.search(r"<body class=\"([^\"]*)\"", h)
        if not body or "sbp" not in body.group(1).split():
            fails.append(f"look wears: {name} is not in the S-2d look (body is not .sbp)")
            continue
        if len(re.findall(r"<main\b", h)) != 1:
            fails.append(f"look wears: {name} has {len(re.findall(r'<main', h))} main landmarks, not one")
        if len(re.findall(r"<h1\b", h)) != 1:
            fails.append(f"look wears: {name} has {len(re.findall(r'<h1', h))} h1 elements, not one")
    if n_wear == 0:
        fails.append("look wears: no page was asked to wear the look, so the check proves nothing")
    fails += _luminance_fail(css)
    fails += _token_fail(css, allowed | set(BULBS))
    # the browser half: what the converted pages render, in Oswald and in color
    sw = sweep_pages(allp)
    if set(sw) != {p for p in allp if not BUILT_IN_LOOK.match(p)}:
        fails.append("look rendered: the sweep's page list is not every converted page")
    for must in ("scores.html", "fantasy/index.html"):
        if must not in sw:
            fails.append(f"look rendered: {must} is not among the pages the sweep reads")
    if not oswald_selectors(css):
        fails.append("look oswald: site.css has no body.sbp rule that sets Oswald, so the look has no display face to check")
    sw_allowed = {h for h in (_hex_of(c) for c in allowed | set(BULBS)) if h}
    fails += rendered_sweep(out, sw, sw_allowed, osw)
    return fails


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    root = sys.argv[1] if len(sys.argv) > 1 else None
    f = look_canary(root)
    for x in f:
        print("FAIL", x)
    print("look canary:", "PASS" if not f else f"{len(f)} FAIL")
    sys.exit(1 if f else 0)
