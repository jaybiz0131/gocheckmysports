#!/usr/bin/env python3
"""live_canary.py: the re-read (S-DONE). Fixture tests, run by the gate on its fixture slate.

  parts          live_board.parts cuts the inner html of each data-live element, byte for byte
  pages          the built home and Scores pages carry their live root, their parts, a stamp with
                 the reading's own time and the script; a game page carries none
  same render    the tick's render (site_build.build() in LIVE_TICK mode) gives the same parts as
                 the full build of the same reading: what the page swaps in is what a deploy
                 would have drawn (U-10)
  in the browser the built page takes a newer board for its own look and day, re-counts its tabs,
                 keeps the tab and the day the reader chose, and takes nothing from a file drawn
                 by another look, for another day, no newer than itself, or absent

USAGE  python3 live_canary.py TREE     TREE is a built fixture slate with scoreboard.json beside it
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import live_board as lb  # noqa: E402



def unit():
    f = []
    html = ('<body><section data-live-root="scores" data-live-day="2026-11-21" data-live-look="ab12">'
            '<span data-live="count">\n        <b>58 games</b> <i data-asof="x">as of</i>\n      </span>'
            '<img src="a.png"><br><div data-live="panels" id="all"><div class="p"><div>one</div>'
            '<p>two<div data-live="inner">in &amp; out</div></div></div>'
            '<script>var s = "</div><div data-live=\\"no\\">";</script></section></body>')
    got, root = lb.parts(html)
    # the count part keeps its own white space: a part is the build's bytes, not a tidied copy
    want = {"count": '\n        <b>58 games</b> <i data-asof="x">as of</i>\n      ',
            "panels": '<div class="p"><div>one</div><p>two<div data-live="inner">in &amp; out</div></div>',
            "inner": "in &amp; out"}
    if got != want:
        f.append(f"live parts: the fixture's parts read {got!r}")
    if root != {"data-live-root": "scores", "data-live-day": "2026-11-21", "data-live-look": "ab12"}:
        f.append(f"live parts: the fixture's root reads {root!r}")
    try:
        lb.doc_for("scores", html, "2026-11-21T20:43:10Z")
        f.append("live parts: a page with no states part made a document")
    except ValueError:
        pass
    return f


def _asof(html):
    m = re.search(r'data-mf="stamp" data-asof="([^"]+)"', html)
    return m.group(1) if m else ""


def pages(tree):
    f = []
    for kind, page in lb.PAGES.items():
        try:
            html = open(os.path.join(tree, page), encoding="utf-8").read()
        except OSError:
            f.append(f"live pages: {page} is not in the tree")
            continue
        got, root = lb.parts(html)
        for n in lb.NEED[kind]:
            if not got.get(n):
                f.append(f"live pages: {page} carries no live part {n!r}")
        if root.get("data-live-root") != kind:
            f.append(f"live pages: {page} carries no live root for {kind}")
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", root.get("data-live-day") or ""):
            f.append(f"live pages: {page} names no day for the re-read")
        if not re.fullmatch(r"[0-9a-f]{10}", root.get("data-live-look") or ""):
            f.append(f"live pages: {page} names no look for the re-read")
        if root.get("data-live-src") != lb.RAW + kind + ".json":
            f.append(f"live pages: {page} reads {root.get('data-live-src')!r}, not {lb.RAW + kind}.json")
        if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", _asof(html)):
            f.append(f"live pages: the stamp on {page} carries no reading time (data-asof)")
        if "data-asof=" not in got.get("count", ""):
            f.append(f"live pages: the stamp on {page} is outside the count part, so a re-read cannot move it")
        if html.count("data-live-root=") != 1 or html.count("gcm:live") < 2:
            f.append(f"live pages: {page} does not carry one live root and the script that reads for it")
    games = sorted(os.listdir(os.path.join(tree, "games"))) if os.path.isdir(os.path.join(tree, "games")) else []
    for g in games[:1]:
        if "data-live-root" in open(os.path.join(tree, "games", g), encoding="utf-8").read():
            f.append(f"live pages: /games/{g} carries a live root; only the home and Scores are re-read")
    if not games:
        f.append("live pages: the tree holds no game page to read")
    return f


def same_render(tree):
    """The tick's render against the full build of the same reading. The full build's scoreboard
    file sits beside the tree (verify_pipeline._fixture_tree) and its conditions are in the tree."""
    f = []
    fx = os.path.join(os.path.dirname(tree.rstrip("/")), "scoreboard.json")
    if not os.path.exists(fx):
        return [f"live render: the slate's scoreboard is not beside the tree ({fx}); nothing was compared"]
    import conditions as cx
    import scoreboard as sbm
    try:
        cxd = json.load(open(os.path.join(tree, "data", "conditions.json"), encoding="utf-8"))
    except (OSError, ValueError):
        cxd = None
    import site_build as sb
    import where_to_watch as w2w
    import inactives as ia
    keep = (sbm.OUT, cx.refresh, sb._NOW_CACHE, w2w.refresh, ia.designations, ia.board)
    try:
        sbm.OUT = fx
        # the inputs a build reads from the network are held to what the full build read, so the
        # two renders differ only by the code path: the Worker's conditions (from the tree), the
        # schedule file as that build left it, and the injury feed as that build's process holds it
        w2w.refresh = lambda *a, **k: None
        if sb.IA_DESIG is not None:
            ia.designations = lambda _d=sb.IA_DESIG: _d
        if sb.IA_BOARD is not None:
            ia.board = lambda _b=sb.IA_BOARD: _b
        if sb._NOW_CACHE is None:
            # run alone (not after the gate's own build in this process): the tree's clock, from its manifest
            try:
                m = json.load(open(os.path.join(tree, "build-manifest.json"), encoding="utf-8"))
                sb._NOW_CACHE = datetime.datetime.strptime(m["built_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc)
            except (OSError, ValueError, KeyError):
                pass
        if cxd is not None:
            cx.refresh = lambda games: cxd
        import contextlib
        import io
        log = io.StringIO()
        try:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                docs = lb.render()
        except Exception as e:                                # noqa: BLE001
            return [f"live render: the tick's render raised {type(e).__name__}: {str(e)[:200]}"]
    finally:
        sbm.OUT, cx.refresh, sb._NOW_CACHE, w2w.refresh, ia.designations, ia.board = keep
    n = 0
    for kind, page in lb.PAGES.items():
        html = open(os.path.join(tree, page), encoding="utf-8").read()
        built, root = lb.parts(html)
        d = docs[kind]
        if d["asof_utc"] != _asof(html) or d["day"] != root.get("data-live-day") or d["look"] != root.get("data-live-look"):
            f.append(f"live render: the tick's {kind} document is for {d['day']} as of {d['asof_utc']} in look {d['look']}; "
                     f"the built page is {root.get('data-live-day')} as of {_asof(html)} in look {root.get('data-live-look')}")
        for name in sorted(set(built) | set(d["parts"])):
            a, b = built.get(name), d["parts"].get(name)
            n += 1
            if a != b:
                i = next((i for i in range(min(len(a or ""), len(b or ""))) if a[i] != b[i]), min(len(a or ""), len(b or "")))
                f.append(f"live render: {kind} part {name!r} differs from the full build at byte {i}: "
                         f"build {(a or '')[max(0, i - 40):i + 60]!r}, tick {(b or '')[max(0, i - 40):i + 60]!r}")
    if n < 7:
        f.append(f"live render: only {n} part(s) were compared")
    return f


def _later(iso, hours, minutes=0):
    t = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(hours=hours, minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _et(iso):
    from zoneinfo import ZoneInfo
    t = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(ZoneInfo("America/New_York"))


def _et_stamp(iso):
    """'Nov 21, 3:43 PM ET' for a reading time, as HONEST_JS prints it on another day."""
    return _et(iso).strftime("%b %-d, %-I:%M %p ET")


def _stamp_at(read_iso, now_iso):
    """The stamp a page prints for a reading, read at `now`: the clock, with the date when the reading
    is from another ET day (site_build.HONEST_JS and build_manifest.asof keep the same rule)."""
    r, n = _et(read_iso), _et(now_iso)
    return "Scores as of " + (r.strftime("%b %-d, ") if r.date() != n.date() else "") + r.strftime("%-I:%M %p ET")


def _cases(tree):
    sc = open(os.path.join(tree, "scores.html"), encoding="utf-8").read()
    hm = open(os.path.join(tree, "index.html"), encoding="utf-8").read()
    sp, sroot = lb.parts(sc)
    hp, hroot = lb.parts(hm)
    asof = _asof(sc)

    def count(newer):
        # the stamp a tick would have rendered for that reading: its own clock, no schedule beside it
        return f'<span class="sb-stamp" data-mf="stamp" data-asof="{newer}">{_stamp_at(newer, newer)}</span>'

    panels = re.split(r'(?=<div class="sc-panel" data-panel=")', sp["panels"])
    live = next(p for p in panels if p.startswith('<div class="sc-panel" data-panel="live"'))
    gone = re.search(r'data-gid="([^"]+)"', live).group(1)
    emptied = "".join('<div class="sc-panel" data-panel="live" id="s-live"><div class="tk-g3">'
                      '<p class="sc-none">Nothing in this state on this day.</p></div></div>'
                      if p is live else p for p in panels)

    def sdoc(look=None, day=None, at=None):
        at = at or _later(asof, 1)
        return {"v": 1, "asof_utc": at, "day": day or sroot["data-live-day"], "look": look or sroot["data-live-look"],
                "parts": {"count": count(at), "states": sp["states"], "panels": emptied}}

    secs = re.split(r'(?=<section class="bd-mod wb-day")', hp["board"])
    secs = [s for s in secs if s]
    hat = _later(_asof(hm), 1)
    hdoc = {"v": 1, "asof_utc": hat, "day": hroot["data-live-day"], "look": hroot["data-live-look"],
            "parts": dict(hp, count=count(hat), board="".join(secs[:-1]))}
    # every case reads on a fixed clock: two minutes after the page's reading, or after the file's
    fresh, hfresh = _later(asof, 0, 2), _later(_asof(hm), 0, 2)
    return gone, len(secs), [
        {"name": "no file", "path": "/scores.html", "doc": None, "gone": gone, "now": fresh},
        {"name": "a newer board", "path": "/scores.html", "doc": sdoc(), "gone": gone, "now": _later(asof, 1, 2)},
        {"name": "another look", "path": "/scores.html", "doc": sdoc(look="0000000000"), "gone": gone, "now": fresh},
        {"name": "another day", "path": "/scores.html", "doc": sdoc(day="2001-01-01"), "gone": gone, "now": fresh},
        {"name": "no newer than the page", "path": "/scores.html", "doc": sdoc(at=asof), "gone": gone, "now": fresh},
        {"name": "the chosen tab", "path": "/scores.html", "doc": sdoc(), "gone": gone, "now": _later(asof, 2, 2),
         "click": '.sc-states [data-tab="final"]', "doc2": sdoc(at=_later(asof, 2))},
        {"name": "home, no file", "path": "/index.html", "doc": None, "now": hfresh},
        {"name": "home, a newer board", "path": "/index.html", "doc": hdoc, "now": _later(_asof(hm), 1, 2)},
        # S-DONE point 2: the same pages read against a reader's clock, with no re-read to be had
        {"name": "read two minutes on", "path": "/scores.html", "doc": None, "now": _later(asof, 0, 2)},
        {"name": "read a day on", "path": "/scores.html", "doc": None, "now": _later(asof, 26)},
        {"name": "home, read a day on", "path": "/index.html", "doc": None, "now": _later(_asof(hm), 26)},
    ]


def browser(tree):
    node = shutil.which("node")
    if not node:
        return ["live in the browser: node is not on this machine; the re-read was not proved on a page"]
    try:
        gone, nsec, cases = _cases(tree)
    except Exception as e:                                    # noqa: BLE001
        return [f"live in the browser: the cases could not be cut from the tree ({type(e).__name__}: {str(e)[:160]})"]
    tmp = tempfile.mkdtemp(prefix="live-cases-")
    try:
        cp = os.path.join(tmp, "cases.json")
        json.dump(cases, open(cp, "w", encoding="utf-8"))
        r = subprocess.run([node, os.path.join(HERE, "scripts", "live-reread.mjs"), tree, cp],
                           capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        return [f"live in the browser: the sweep did not run ({type(e).__name__})"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows = {}
    for line in r.stdout.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("fail"):
            return [f"live in the browser: {o.get('name') or 'the sweep'}: {o['fail']}"]
        rows[o["name"]] = o
    f = []
    miss = [c["name"] for c in cases if c["name"] not in rows]
    if miss or r.returncode != 0:
        return [f"live in the browser: the sweep read {len(rows)} of {len(cases)} cases (exit {r.returncode}); "
                f"not read: {', '.join(miss) or 'none'}"]
    base, hbase = rows["no file"], rows["home, no file"]
    sc_asof = _asof(open(os.path.join(tree, "scores.html"), encoding="utf-8").read())
    hm_asof = _asof(open(os.path.join(tree, "index.html"), encoding="utf-8").read())
    took = _stamp_at(_later(sc_asof, 1), _later(sc_asof, 1, 2))
    if not base["stamp"] or base["stamp"] == took or not base["gone_present"] or base["tabs"]["live"]["cards"] < 1:
        f.append(f"live in the browser: the built Scores page reads {base['stamp']!r} with "
                 f"{base['tabs']['live']['cards']} live card(s); the cases prove nothing")
    for name in ("no file", "another look", "another day", "no newer than the page"):
        o = rows[name]
        if o["stamp"] != base["stamp"] or o["asof"] != base["asof"] or not o["gone_present"] or o["events"]:
            f.append(f"live in the browser: {name}: the page changed (stamp {o['stamp']!r}); it must keep the build's board")
        if name != "no file" and not o["asked"]:
            f.append(f"live in the browser: {name}: the page never asked for the file")
    o = rows["a newer board"]
    if o["stamp"] != took or o["asof"] != _later(sc_asof, 1) or o["gone_present"] or not o["events"]:
        f.append(f"live in the browser: a newer board for this look and day was not taken (stamp {o['stamp']!r}, "
                 f"the emptied panel's card {'still drawn' if o['gone_present'] else 'gone'})")
    else:
        for t, v in o["tabs"].items():
            if v["says"] != v["cards"]:
                f.append(f"live in the browser: after the re-read the {t.title()} tab says {v['says']} over {v['cards']} card(s)")
        # the file's Live panel is empty; read an hour on, the kickoffs that have passed since are listed there
        # (HONEST_JS), so Live holds exactly those and Upcoming the rest of what the file carried
        if o["tabs"]["live"]["cards"] != o["pre_past"] \
                or o["tabs"]["live"]["cards"] + o["tabs"]["upcoming"]["cards"] != base["tabs"]["upcoming"]["cards"]:
            f.append(f"live in the browser: the panels on the page are not the ones the file carried "
                     f"(Live {o['tabs']['live']['cards']}, Upcoming {o['tabs']['upcoming']['cards']}, the file's "
                     f"Upcoming {base['tabs']['upcoming']['cards']}, {o['pre_past']} past kickoff)")
    o = rows["the chosen tab"]
    if o["stamp"] != _stamp_at(_later(sc_asof, 2), _later(sc_asof, 2, 2)) or not o["tabs"]["final"]["on"] \
            or not o["tabs"]["final"]["shown"] \
            or o["tabs"]["live"]["shown"] or o["tabs"]["upcoming"]["shown"]:
        f.append(f"live in the browser: a reader on the Final tab was moved by the next re-read "
                 f"(stamp {o['stamp']!r}, tabs {o['tabs']})")
    o = rows["home, a newer board"]
    if o["stamp"] != _stamp_at(_later(hm_asof, 1), _later(hm_asof, 1, 2)) or o["days"] != nsec - 1:
        f.append(f"live in the browser: the home did not take a newer board (stamp {o['stamp']!r}, {o['days']} day(s) "
                 f"drawn, the file carried {nsec - 1})")
    elif o["days_shown"] != hbase["days_shown"] or o["day_tab_on"] != hbase["day_tab_on"]:
        f.append(f"live in the browser: the home's open day moved on a re-read (was {hbase['days_shown']}, "
                 f"is {o['days_shown']}; tab {o['day_tab_on']})")
    # the aged page (HONEST_JS)
    o = rows["read two minutes on"]
    if o["stamp"] != base["stamp"] or o["aged"] or o["tabs"] != base["tabs"]:
        f.append(f"honest in the browser: a page read two minutes after its reading was changed "
                 f"(stamp {o['stamp']!r}, {len(o['aged'])} card(s) marked)")
    for name, asof_iso, b in (("read a day on", sc_asof, base), ("home, read a day on", hm_asof, hbase)):
        o = rows[name]
        want = "Scores as of " + _et_stamp(asof_iso)
        if o["stamp"] != want:
            f.append(f"honest in the browser: {name}: the stamp reads {o['stamp']!r}, not {want!r} "
                     f"(the reading's date, and no schedule that is not holding)")
        if not o["pre_past"] or len(o["aged"]) != o["pre_past"]:
            f.append(f"honest in the browser: {name}: {o['pre_past']} card(s) are still drawn as upcoming past their "
                     f"kickoff and {len(o['aged'])} say so")
        elif set(o["aged"]) != {"No update since " + _et_stamp(asof_iso)}:
            f.append(f"honest in the browser: {name}: an aged card reads {sorted(set(o['aged']))[0]!r}")
    o = rows["read a day on"]
    if o["aged_outside_live"] or o["tabs"]["upcoming"]["cards"] or o["tabs"]["live"]["says"] != o["tabs"]["live"]["cards"] \
            or o["tabs"]["live"]["cards"] != base["tabs"]["live"]["cards"] + base["tabs"]["upcoming"]["cards"]:
        f.append(f"honest in the browser: a kickoff a day past is not listed with Live and counted there "
                 f"(tabs {o['tabs']}, {o['aged_outside_live']} aged card(s) outside Live)")
    for name, o in rows.items():
        if o["errors"]:
            f.append(f"live in the browser: {name}: {o['errors'][0]}")
    return f


def live_canary(tree, fast=False):
    f = unit()
    if not tree or not os.path.isdir(tree):
        return f + ["live: no fixture slate was built; the pages, the render and the browser were not read"]
    f += pages(tree)
    if not f and not fast:
        f += same_render(tree)
    f += browser(tree)
    return f


if __name__ == "__main__":
    fs = live_canary(sys.argv[1] if len(sys.argv) > 1 else "", fast="--fast" in sys.argv)
    for x in fs:
        print("::error::" + x)
    print("LIVE CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
