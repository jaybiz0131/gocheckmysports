#!/usr/bin/env python3
"""measure_canary.py: S-5.2, scorecard lines 4, 7 and 10 measured by the canary on every build.

The strategist's ruling of October 20: lines 4, 7 and 10 are measured by the canary from S-5.2 on,
so no report after S-5.2 can leave them unmeasured. Three reads of the gate's own built tree
(verify_pipeline._built_tree), each printed before it is judged, and a red on any of them fails
the gate:

  performance  Lighthouse's mobile performance score on the built home and a game page, 90 or
               better (line 4). Lighthouse runs in the Chromium CI installs for Playwright,
               through scripts/page-measure.mjs; the figure is the median of LH_RUNS runs.
  console      zero console errors and zero uncaught errors on the built home, a game page and a
               team page (line 10), read in the same browser.
  structured   the JSON-LD of every game page and every team page validated against the property
               lists below (line 7): SportsEvent and BroadcastEvent on a game page, SportsTeam on
               a team page. The game page and team page the browser reads are among them.

Each read has a fixture that must go red, run on every canary so a read that stops seeing cannot
pass in silence (U-9): a page with a console error, a page under 90, a game page with its
BroadcastEvent taken out.

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

LH_MIN = 90      # scorecard line 4: Lighthouse mobile performance 90 or better
LH_RUNS = 3      # Lighthouse's scores vary run to run; the median of three is the figure judged

# ---------------------------------------------------------------------------------------------
# THE PROPERTY LISTS, each beside its source. schema.org itself marks no property of any type as
# required (read October 20, 2026 on schema.org/SportsEvent, /BroadcastEvent, /PublicationEvent,
# /SportsTeam: each page lists expected types and nothing more). The required and recommended
# split for an event is Google Search Central's, for the Event type that SportsEvent extends; for
# BroadcastEvent and SportsTeam, which have no such page, the list is the type's own schema.org
# properties that say what the thing is, and each one the page cannot state is named with why.
# A dotted name is a property of the value ("location.address" is the address of the location).
#
# SportsEvent. Source: https://developers.google.com/search/docs/appearance/structured-data/event
# (Required: location, location.address, name, startDate. Recommended: description, endDate,
# eventStatus, image, location.name, offers and offers.*, organizer, organizer.name,
# organizer.url, performer, performer.name, previousStartDate), and https://schema.org/SportsEvent
# for the type's own properties (awayTeam, competitor, homeTeam, sport; referee left out below).
SPORTS_EVENT_REQUIRED = ["name", "startDate", "location", "location.address",
                         "location.address.addressLocality"]
SPORTS_EVENT_RECOMMENDED = ["description", "image", "eventStatus", "location.name", "organizer",
                            "organizer.name", "url", "sport", "homeTeam", "homeTeam.name",
                            "awayTeam", "awayTeam.name", "competitor"]
SPORTS_EVENT_NOT_STATED = {
    "endDate": "the feed carries no end time, and a guessed one would be a fabricated figure",
    "offers": "the site sells and links no tickets, so there is no offer to state",
    "organizer.url": "the page links no league site, and the markup says nothing the page does not",
    "performer": "Google's performer is a performing act; a game's sides are homeTeam, awayTeam and competitor",
    "previousStartDate": "only for a rescheduled event, and the feed carries no earlier date",
    "referee": "the feed names no officials",
}
# BroadcastEvent. Source: https://schema.org/BroadcastEvent (broadcastOfEvent, isLiveBroadcast,
# subtitleLanguage, videoFormat) and its parent https://schema.org/PublicationEvent (publishedBy,
# publishedOn). Required here: what makes it this game's broadcast on a named carrier.
BROADCAST_EVENT_REQUIRED = ["name", "startDate", "broadcastOfEvent", "isLiveBroadcast",
                            "publishedOn", "publishedOn.name"]
BROADCAST_EVENT_NOT_STATED = {
    "subtitleLanguage": "the feed carries no caption language",
    "videoFormat": "the feed carries no picture format",
    "publishedBy": "the carrier is publishedOn; the feed names no separate publisher",
}
# SportsTeam. Source: https://schema.org/SportsTeam (athlete, coach, gender), its parents
# https://schema.org/SportsOrganization (sport) and https://schema.org/Organization (memberOf,
# event), and Thing (name, url).
SPORTS_TEAM_REQUIRED = ["name", "url", "sport", "memberOf", "memberOf.name"]
SPORTS_TEAM_NOT_STATED = {
    "athlete": "the team page prints no roster",
    "coach": "the team page names no coach",
    "gender": "the page does not say it, so the markup does not",
}


def _ld(html):
    out = []
    for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html or "", re.S):
        try:
            out.append(json.loads(m))
        except ValueError:
            out.append({"@type": "UNPARSEABLE"})
    return out


def _graph(html):
    return [n for d in _ld(html) for n in (d.get("@graph") or [d]) if isinstance(n, dict)]


def _has(node, dotted):
    v = node
    for part in dotted.split("."):
        if isinstance(v, list):
            v = v[0] if v else None
        if not isinstance(v, dict):
            return False
        v = v.get(part)
    if isinstance(v, str):
        return bool(v.strip())
    return v not in (None, [], {})


def _missing(node, names):
    return [n for n in names if not _has(node, n)]


def validate_game(html, label):
    """A game page: one SportsEvent with every listed property, and at least one BroadcastEvent,
    each with every listed property and pointing at that SportsEvent."""
    fails = []
    g = _graph(html)
    if any(n.get("@type") == "UNPARSEABLE" for n in g):
        fails.append(f"structured: {label}: a JSON-LD block does not parse")
    ev = [n for n in g if n.get("@type") == "SportsEvent"]
    if len(ev) != 1:
        return fails + [f"structured: {label}: {len(ev)} SportsEvent nodes, expected 1"]
    ev = ev[0]
    miss = _missing(ev, SPORTS_EVENT_REQUIRED + SPORTS_EVENT_RECOMMENDED)
    if miss:
        fails.append(f"structured: {label}: the SportsEvent has no {', '.join(miss)}")
    bc = [n for n in g if n.get("@type") == "BroadcastEvent"]
    if not bc:
        fails.append(f"structured: {label}: no BroadcastEvent")
    for b in bc:
        miss = _missing(b, BROADCAST_EVENT_REQUIRED)
        if miss:
            fails.append(f"structured: {label}: a BroadcastEvent has no {', '.join(miss)}")
        elif (b.get("broadcastOfEvent") or {}).get("@id") != ev.get("@id"):
            fails.append(f"structured: {label}: a BroadcastEvent does not point at the page's SportsEvent")
    return fails


def validate_team(html, label, tree=None):
    """A team page: one SportsTeam with every listed property. Its next game is the game page's
    event, pointed at by @id (Organization.event), and that page must declare that @id."""
    fails = []
    g = _graph(html)
    if any(n.get("@type") == "UNPARSEABLE" for n in g):
        fails.append(f"structured: {label}: a JSON-LD block does not parse")
    tm = [n for n in g if n.get("@type") == "SportsTeam"]
    if len(tm) != 1:
        return fails + [f"structured: {label}: {len(tm)} SportsTeam nodes, expected 1"]
    miss = _missing(tm[0], SPORTS_TEAM_REQUIRED)
    if miss:
        fails.append(f"structured: {label}: the SportsTeam has no {', '.join(miss)}")
    if any(n.get("@type") == "SportsEvent" for n in g):
        # One event, one page: the game page owns it, and a second copy here drifts from it.
        fails.append(f"structured: {label}: the page restates a SportsEvent the game page owns")
    ref = (tm[0].get("event") or {}).get("@id") if isinstance(tm[0].get("event"), dict) else None
    if ref and tree:
        m = re.search(r"(/games/[^#]+)#event$", ref)
        p = os.path.join(tree, m.group(1).lstrip("/")) if m else ""
        if not (p and os.path.exists(p)):
            fails.append(f"structured: {label}: its next game {ref} is not a built game page")
        else:
            with open(p, encoding="utf-8", errors="ignore") as fh:
                if not any(n.get("@id") == ref for n in _graph(fh.read())):
                    fails.append(f"structured: {label}: {ref} is not declared on its game page")
    return fails


def _pages(tree):
    """The home, the first game the home links that the build wrote, and the team page that
    points at that game (the first NFL team page when none does)."""
    with open(os.path.join(tree, "index.html"), encoding="utf-8", errors="ignore") as fh:
        home = fh.read()
    game = next((p for p in re.findall(r'href="(/games/\d+\.html)"', home)
                 if os.path.exists(os.path.join(tree, p.lstrip("/")))), None)
    team = None
    tdir = os.path.join(tree, "teams")
    nfl = sorted(f for f in os.listdir(tdir) if f.endswith(".html")) if os.path.isdir(tdir) else []
    cfb = sorted("cfb/" + f for f in os.listdir(os.path.join(tdir, "cfb"))
                 if f.endswith(".html")) if os.path.isdir(os.path.join(tdir, "cfb")) else []
    if game:
        want = f"{game}#event"
        for f in nfl + cfb:
            with open(os.path.join(tdir, f), encoding="utf-8", errors="ignore") as fh:
                if want in fh.read():
                    team = f"/teams/{f}"
                    break
    if not team and nfl:
        team = f"/teams/{nfl[0]}"
    return "/index.html", game, team, nfl, cfb


def run_measure(spec):
    """scripts/page-measure.mjs over SPEC; returns (records, failure strings)."""
    node = shutil.which("node")
    if not node:
        return [], ["measure: node is not installed, so nothing was measured"]
    tmp = tempfile.mkdtemp(prefix="page-measure-")
    try:
        sp = os.path.join(tmp, "spec.json")
        with open(sp, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        try:
            r = subprocess.run([node, os.path.join(HERE, "scripts", "page-measure.mjs"), sp],
                               capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            return [], ["measure: the browser read timed out"]
        recs, fails = [], []
        for line in r.stdout.splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if "fail" in o:
                fails.append("measure: " + o["fail"])
            else:
                recs.append(o)
        if r.returncode != 0 and not fails:
            fails.append(f"measure: page-measure exited {r.returncode}: {r.stderr[-300:]}")
        return recs, fails
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def judge_lighthouse(rec):
    if rec.get("score") is None or rec["score"] < LH_MIN:
        return [f"performance: {rec.get('path')} scores {rec.get('score')} on Lighthouse mobile, "
                f"under {LH_MIN}"]
    return []


def judge_console(rec):
    errs = rec.get("errors") or []
    if errs:
        return [f"console: {rec.get('path')} logged {len(errs)} error(s): {errs[0]}"]
    return []


def _inject(html, snippet):
    return html.replace("<head>", "<head>" + snippet, 1) if "<head>" in html else snippet + html


# The fixtures. Each is a built page with one thing added, so it is the shipped page that goes red.
FX_CONSOLE = "/__s52__/console-error.html"
FX_SLOW = "/__s52__/slow.html"
# about 1.5 seconds of main thread before first paint: on Lighthouse's simulated mobile CPU that is
# several seconds of blocking time, far under 90
_SLOW_JS = "<script>(function(){var t=Date.now();while(Date.now()-t<1500){}})();</script>"
_ERR_JS = "<script>console.error('S-5.2 fixture: a console error');</script>"


def measure_canary(tree):
    fails = []
    if not tree or not os.path.isdir(tree):
        return ["measure: the gate built no tree, so lines 4, 7 and 10 were not measured"]
    home, game, team, nfl, cfb = _pages(tree)
    if not game:
        return ["measure: the home links no built game page, so nothing was measured"]
    if not team:
        return ["measure: the build wrote no team page, so nothing was measured"]

    def rd(p):
        with open(os.path.join(tree, p.lstrip("/")), encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    stamp = ""
    try:
        m = re.search(r"commit (\S+)", rd("/stamp.txt"))
        stamp = m.group(1) if m else ""
    except OSError:
        pass

    # LINE 7: every game page and every team page, the chosen two among them.
    gdir = os.path.join(tree, "games")
    gpages = sorted(f for f in os.listdir(gdir) if f.endswith(".html")) if os.path.isdir(gdir) else []
    sfails = []
    for f in gpages:
        sfails += validate_game(rd(f"/games/{f}"), f"/games/{f}")
    for f in nfl + cfb:
        sfails += validate_team(rd(f"/teams/{f}"), f"/teams/{f}", tree)
    gbc = len([n for n in _graph(rd(game)) if n.get("@type") == "BroadcastEvent"])
    print(f"measure: JSON-LD {game}: {'valid' if not validate_game(rd(game), game) else 'INVALID'} "
          f"(SportsEvent, {gbc} BroadcastEvent)")
    print(f"measure: JSON-LD {team}: "
          f"{'valid' if not validate_team(rd(team), team, tree) else 'INVALID'} (SportsTeam)")
    print(f"measure: JSON-LD on {len(gpages)} game pages and {len(nfl) + len(cfb)} team pages: "
          f"{len(sfails)} failure(s)")
    if not gpages or not (nfl + cfb):
        fails.append("structured: the build wrote no game page or no team page to validate")
    fails += sfails
    # FIXTURE: the chosen game page with its BroadcastEvent taken out must fail, naming it.
    gh = rd(game)
    stripped = []
    for d in _ld(gh):
        if "@graph" in d:
            d = dict(d, **{"@graph": [n for n in d["@graph"] if n.get("@type") != "BroadcastEvent"]})
        stripped.append('<script type="application/ld+json">' + json.dumps(d) + "</script>")
    fx = re.sub(r'<script type="application/ld\+json">.*?</script>', "", gh, flags=re.S) + "".join(stripped)
    if not any("BroadcastEvent" in f for f in validate_game(fx, "fixture")):
        fails.append("structured: a game page with no BroadcastEvent passed the validation, so it "
                     "cannot see a missing broadcast")

    # LINES 4 AND 10: the browser reads, the two fixtures in the same run.
    spec = {"root": tree,
            "inline": {FX_CONSOLE: _inject(rd(home), _ERR_JS), FX_SLOW: _inject(rd(game), _SLOW_JS)},
            "console": [home, game, team, FX_CONSOLE],
            "lighthouse": [[home, LH_RUNS], [game, LH_RUNS], [FX_SLOW, 1]]}
    recs, mfails = run_measure(spec)
    fails += mfails
    lh = {r["path"]: r for r in recs if r.get("kind") == "lighthouse"}
    cs = {r["path"]: r for r in recs if r.get("kind") == "console"}
    for p in (home, game):
        r = lh.get(p)
        if not r:
            fails.append(f"performance: {p} was not measured")
            continue
        md = r.get("median") or {}
        print(f"measure: Lighthouse mobile performance {p}: {r['score']} (runs {r.get('runs')}; "
              f"FCP {md.get('fcp')} ms, LCP {md.get('lcp')} ms, TBT {md.get('tbt')} ms, "
              f"CLS {md.get('cls')}, SI {md.get('si')} ms; Lighthouse {md.get('version')}, "
              f"{md.get('formFactor')}, {md.get('throttling')} throttling)")
        if md.get("formFactor") != "mobile":
            fails.append(f"performance: {p} was not read as mobile ({md.get('formFactor')})")
        fails += judge_lighthouse(r)
    for p in (home, game, team):
        r = cs.get(p)
        if not r:
            fails.append(f"console: {p} was not read")
            continue
        print(f"measure: console errors {p}: {len(r.get('errors') or [])}"
              + (f" (third hosts answered empty: {', '.join(r['third'])})" if r.get("third") else ""))
        # U-10: the page read is the tree built, with its own fonts
        if not stamp or r.get("stamp") != stamp:
            fails.append(f"measure: {p} carries build-commit {r.get('stamp')!r}, not the built "
                         f"tree's {stamp!r}, so the read was of another page")
        if not r.get("fonts"):
            fails.append(f"measure: {p} loaded no font, so it was read with a stand-in (U-10)")
        fails += judge_console(r)
    # The fixtures must go red through the same judges.
    r = cs.get(FX_CONSOLE)
    if not r or not judge_console(r):
        fails.append("console: the fixture page with a console error read clean, so the read "
                     "cannot see an error")
    r = lh.get(FX_SLOW)
    if r:
        print(f"measure: the slow fixture scores {r.get('score')} (it must be under {LH_MIN})")
    if not r or not judge_lighthouse(r):
        fails.append(f"performance: the fixture page under {LH_MIN} passed, so the read cannot "
                     f"see a slow page")
    return fails


if __name__ == "__main__":
    import sys
    _f = measure_canary(sys.argv[1])
    for f in _f:
        print("FAIL " + f)
    sys.exit(1 if _f else 0)
