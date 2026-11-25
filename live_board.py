#!/usr/bin/env python3
"""live_board.py: the board, re-read without a deploy (S-DONE, November 25 2026).

A deploy changes what the site says; a number changing is not a deploy (the ruling of September
21, 2026, after 1,188 production deploys in a month paused every site on the team). A build every
ten minutes through the week's game windows is about 1,000 deploys a month, the team's whole
allowance, so the stamp cannot be kept inside fifteen minutes by building.

So while a game window is on (cadence.window), each tick of scores-cadence.yml renders the home
and the Scores page with the site's own renderer (site_build.build() in its LIVE_TICK mode: the
same code path as the deploy, stopped once those two pages are written), cuts out the parts a
score changes, and commits them under site/data/live/. The pages fetch that file from the
repository and replace those parts in place (site_build.LIVE_JS), as the inactives board has
since September. netlify_ignore.py never builds a push that touches only site/data/live/.

  home.json, scores.json   {"v", "asof_utc", "day", "look", "parts": {name: inner html}}
  scoreboard.json          the reading the parts were rendered from, whole. scoreboard.refresh()
                           reads it for the time each final was first seen, so "Final as of" does
                           not move from tick to tick, and the health gate reads its history.

A page takes a file only when its look (the stylesheet's hash), its day and a newer asof all
match, so a tick rendered by other code or for another day changes nothing: the built page
stands, with its own stamp. Without script the page is the build's, complete.

USAGE  python3 live_board.py            render and write site/data/live/
       python3 live_board.py --parts F  print the live parts of a built page
"""

import json
import os
import re
import shutil
import sys
import tempfile
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "site", "data", "live")
RAW = "https://raw.githubusercontent.com/jaybiz0131/gocheckmysports/main/site/data/live/"
PAGES = {"home": "index.html", "scores": "scores.html"}
# the parts each page must carry; a render that lost one is not written
NEED = {"home": ("count", "board", "lead"), "scores": ("count", "states", "panels")}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
        "track", "wbr"}


class _Parts(HTMLParser):
    """The inner html of every element that carries data-live, by offset into the source: nothing
    is re-serialized, so a part is byte for byte what the build wrote."""

    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.html = html
        self.lines = [0]
        for m in re.finditer("\n", html):
            self.lines.append(m.end())
        self.stack = []          # (tag, name or None, inner start offset)
        self.parts = {}
        self.attrs = {}

    def _off(self):
        ln, col = self.getpos()
        return self.lines[ln - 1] + col

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "data-live-root" in a:
            self.attrs = {k: v for k, v in a.items() if k.startswith("data-live-")}
        if tag in VOID:
            return
        end = self._off() + len(self.get_starttag_text())
        self.stack.append((tag, a.get("data-live"), end))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        # close to the nearest open element of this name (the build writes well-formed html;
        # a stray end tag is ignored rather than allowed to unbalance the stack)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                _t, name, start = self.stack[i]
                del self.stack[i:]
                if name:
                    self.parts[name] = self.html[start:self._off()]
                return


def parts(html):
    """({name: inner html}, {data-live-* attributes of the page's live root})."""
    p = _Parts(html)
    p.feed(html)
    p.close()
    return p.parts, p.attrs


def doc_for(kind, html, asof_utc):
    got, root = parts(html)
    lost = [n for n in NEED[kind] if n not in got]
    if lost:
        raise ValueError(f"the rendered {PAGES[kind]} carries no live part {', '.join(lost)}")
    if root.get("data-live-root") != kind or not root.get("data-live-day") or not root.get("data-live-look"):
        raise ValueError(f"the rendered {PAGES[kind]} carries no live root for {kind}")
    return {"v": 1, "asof_utc": asof_utc, "day": root["data-live-day"], "look": root["data-live-look"],
            "parts": got}


def render(publish=None):
    """{kind: doc} from a LIVE_TICK build: the scoreboard file as the tick just read it, the other
    inputs as committed, the conditions from the Worker as on any build."""
    import site_build as sb
    tmp = publish or tempfile.mkdtemp(prefix="live-board-")
    keep = (sb.PUBLISH, sb.LIVE_TICK)
    try:
        sb.PUBLISH, sb.LIVE_TICK = tmp, True
        sb.build()
        asof = (sb.SB_DATA or {}).get("fetched_at") or ""
        if not asof:
            raise ValueError("the build read no scoreboard")
        return {k: doc_for(k, open(os.path.join(tmp, f), encoding="utf-8").read(), asof)
                for k, f in PAGES.items()}
    finally:
        sb.PUBLISH, sb.LIVE_TICK = keep
        if not publish:
            shutil.rmtree(tmp, ignore_errors=True)


def write(out=None):
    """Render and write the three files; returns one line for the log."""
    import scoreboard
    out = out or OUT
    docs = render()
    os.makedirs(out, exist_ok=True)
    for k, d in docs.items():
        with open(os.path.join(out, k + ".json"), "w", encoding="utf-8") as f:
            json.dump(d, f, separators=(",", ":"), sort_keys=True)
    shutil.copyfile(scoreboard.OUT, os.path.join(out, "scoreboard.json"))
    return (f"the board re-read as of {docs['scores']['asof_utc']} for {docs['scores']['day']} "
            f"(home {len(json.dumps(docs['home']))} bytes, scores {len(json.dumps(docs['scores']))} bytes)")


if __name__ == "__main__":
    if "--parts" in sys.argv:
        got, root = parts(open(sys.argv[sys.argv.index("--parts") + 1], encoding="utf-8").read())
        print(json.dumps({"root": root, "parts": {k: len(v) for k, v in got.items()}}, indent=1))
        sys.exit(0)
    print(write())
