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
  oswald    the h1 a page sets in Oswald is made only of characters the pinned subset carries
  css       every color site.css gives a body.sbp rule is a token and clears 4.5:1 on the frame, the
            panel and a plate

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


def _oswald_texts(h):
    """(label, text) for every element the S-5.5 CSS sets in Oswald, as the page prints it."""
    res = []
    for m in re.finditer(r"<h1\b([^>]*)>(.*?)</h1>", h, re.S):
        if "sr-only" in m.group(1) or "sbp-serif" in m.group(1):
            continue
        res.append(("h1", m.group(2)))
    for m in re.finditer(r'<(?:span|p|div|small)\b[^>]*class="[^"]*\b(?:kicker|bd-eyebrow|ed-kicker)\b[^"]*"[^>]*>(.*?)</(?:span|p|div|small)>', h, re.S):
        res.append(("label", m.group(1)))
    for m in re.finditer(r'<div class="sec-head"[^>]*><h2\b[^>]*>(.*?)</h2>', h, re.S):
        res.append(("section head", m.group(1)))
    return [(t, re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", x)))) for t, x in res]


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
        # every text the look sets in Oswald is made only of characters the subset carries; an h1 the
        # subset cannot draw is marked sbp-serif by the shell and set in the page serif instead
        for tag, texts in _oswald_texts(h):
            odd = sorted(set(texts.upper()) - osw)
            if odd:
                fails.append(f"look oswald: {name} sets its {tag} in Oswald with {odd[:5]}, which the subset cannot draw")
                break
    if n_wear == 0:
        fails.append("look wears: no page was asked to wear the look, so the check proves nothing")
    fails += _luminance_fail(css)
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
