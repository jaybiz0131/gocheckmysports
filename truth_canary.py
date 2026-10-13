#!/usr/bin/env python3
"""truth_canary.py: Sprint S-1 item 0, one truth for counts and stamps (12 October 2026).

The home, Scores, Fantasy and Where to Watch are built from ONE fixture and one manifest
and must agree on every count and stamp. Each check below names the break it exists for;
each was seen red before it was committed (U-9) and the break is recorded in HANDOFF.md.

  agreement      a page prints a stamp or count that is not the manifest's
  final          a game the feed has not finished is printed as Final
  dup-id         a game id renders twice on one page
  live           the word "live" is on a page (visible text, titles, alt, aria, meta)
  week           the NFL week number on the Tuesday 6:00 AM ET boundary, from a fixture clock

Called from verify_pipeline.layer1_canary(); returns a list of failure strings.
"""

import datetime as _d
import re
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}


# ---- readers -------------------------------------------------------------------------

class _Doc(HTMLParser):
    """One pass over a page: visible text (with titles, alt, aria-label, meta content),
    the manifest marks, and the game units."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.text = []
        self.stack = []          # (tag, class string, in_unit_shell)
        self.marks = []          # (kind, text)
        self._mark = None
        self.units = []          # game ids of top-level units
        self.cards = []          # (gid, kicker text) for every article card

    def _inside(self, cls):
        return any(cls in (c or "").split() for _t, c, _u in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag in ("script", "style"):
            self.skip += 1
        for k in ("aria-label", "title", "alt"):
            if a.get(k):
                self.text.append(a[k])
        if tag == "meta" and a.get("content") and not a["content"].startswith("http"):
            self.text.append(a["content"])
        gid = a.get("data-gid")
        if gid and not (self._inside("tk-pair") or self._inside("tk-open")):
            self.units.append(gid)
        if a.get("data-mf"):
            self._mark = [a["data-mf"], []]
        if tag not in VOID:
            self.stack.append((tag, cls, False))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if self._mark is not None and tag in ("p", "span", "div"):
            self.marks.append((self._mark[0], "".join(self._mark[1]).strip()))
            self._mark = None

    def handle_data(self, data):
        if self.skip:
            return
        self.text.append(data)
        if self._mark is not None:
            self._mark[1].append(data)


def read(html):
    p = _Doc()
    p.feed(html or "")
    return p


def visible(html):
    return " ".join(read(html).text)


# ---- the checks ----------------------------------------------------------------------

def check_agreement(pages, manifest, count_for):
    """Every page prints the manifest's stamp and count and nothing else as its own.
    `pages` is {name: html}; `count_for` is {name: the count line that page must print}."""
    fails = []
    want_stamp = f"Updated {manifest['data_stamp'] or manifest['stamp']}"
    for name, html in pages.items():
        marks = read(html).marks
        stamps = [t for k, t in marks if k == "stamp"]
        counts = [t for k, t in marks if k == "count"]
        if not stamps:
            fails.append(f"truth: {name} prints no manifest stamp")
        for s in stamps:
            if s != want_stamp:
                fails.append(f"truth: {name} stamp reads {s!r}, the manifest says {want_stamp!r}")
        if name in count_for:
            if not counts:
                fails.append(f"truth: {name} prints no manifest count")
            for c in counts:
                if c != count_for[name]:
                    fails.append(f"truth: {name} count reads {c!r}, the manifest says "
                                 f"{count_for[name]!r}")
    return fails


def check_no_final_for_scheduled(html, games):
    """No game the feed has not finished may print Final. `games` are the schedule rows.
    Read row by row (the page prints a Final heading after the pending rows, so a window
    of text after the game's name would read the next section's label)."""
    fails = []
    rows = re.findall(r'<div class="(w2w-row[^"]*)">(.*?)</div>', html, re.S)
    for g in games:
        if g.get("state") == "post" or g.get("completed"):
            continue
        name = f"{g['away']} at {g['home']}"
        mine = [(c, b) for c, b in rows if name in re.sub(r"<[^>]+>", "", b)]
        if not mine:
            fails.append(f"truth: scheduled game {name} is not on Where to Watch at all")
        for c, b in mine:
            if "w2w-played" in c or "Final" in re.sub(r"<[^>]+>", " ", b):
                fails.append(f"truth: scheduled game {name} is printed as Final")
    return fails


def check_unique_ids(name, html):
    ids = read(html).units
    dup = sorted({i for i in ids if ids.count(i) > 1})
    return [f"truth: {name} renders game id {i} {ids.count(i)} times" for i in dup]


_LIVE = re.compile(r"(?i)\blive\b")


def check_no_live(name, html):
    m = _LIVE.search(visible(html))
    if not m:
        return []
    t = visible(html)
    return [f"truth: the word \"live\" is on {name}: ...{t[max(0, m.start() - 40):m.end() + 40]!r}"]


# paths whose text is the desk's own writing or a list of it: story text may say "live"
# (archive.html lists story headlines; fantasy/ holds player and injury notes from the league)
EDITORIAL = ("articles/", "edition/", "news/", "sections/", "coverage/", "share/",
             "wire.html", "bottom-line.html", "standards.html", "archive.html")


def live_word_scan(root):
    """The built tree: every page that is not the desk's own writing."""
    import os
    fails = []
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(dp, fn)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if rel.startswith(EDITORIAL):
                continue
            fails.extend(check_no_live(rel, open(path, encoding="utf-8").read()))
    return fails


# ---- the fixture ---------------------------------------------------------------------

def _fixture(sb):
    ET = sb._ET

    def u(et):
        return _d.datetime.fromisoformat(et).replace(tzinfo=ET).astimezone(_d.timezone.utc)

    def g(lg, a, h, kick, st, sa=None, sh=None, per=None):
        return {"league": lg, "id": a + h, "state": st, "period": per, "status_short": "",
                "start_utc": u(kick).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "away": {"abbr": a, "score": sa, "name": a, "full": a},
                "home": {"abbr": h, "score": sh, "name": h, "full": h}}
    nfl = [g("NFL", "CHI", "GB", "2026-10-11T13:00", "pre"),
           g("NFL", "LAR", "NYG", "2026-10-11T16:25", "pre"),
           g("NFL", "BAL", "ATL", "2026-10-10T20:00", "post", "30", "23"),
           g("NFL", "KC", "BUF", "2026-10-11T13:00", "in", "10", "7", 2)]
    cfb = [g("CFB", "ALA", "LSU", "2026-10-10T15:30", "post", "20", "17")]
    nhl = [g("NHL", "BOS", "NYR", "2026-10-11T19:00", "pre")]
    sbd = {"fetched_at": "2026-10-11T12:00:00Z",
           "leagues": [{"league": "NFL", "games": nfl}, {"league": "CFB", "games": cfb},
                       {"league": "NHL", "games": nhl}]}

    def w(a, h, kick, st, sa=None, sh=None, win="Sunday afternoon, 1:00 ET", i="1"):
        k = u(kick)
        return {"away": a, "home": h, "kickoff_utc": k.strftime("%Y-%m-%dT%H:%MZ"),
                "kickoff_et": k.astimezone(ET).strftime("%-I:%M %p ET"),
                "day_et": k.astimezone(ET).strftime("%a, %b %-d"), "window": win,
                "carriers": [{"name": "FOX", "market": "National", "type": "TV"}],
                "id": i, "state": st, "completed": st == "post",
                "status": "Final" if st == "post" else "",
                "away_score": sa, "home_score": sh}
    games = [w("CHI", "GB", "2026-10-11T13:00", "pre", i="1"),
             w("LAR", "NYG", "2026-10-11T16:25", "pre", win="Sunday afternoon, 4:05 and 4:25 ET", i="2"),
             w("BAL", "ATL", "2026-10-10T20:00", "post", "30", "23", win="Saturday", i="3"),
             # the 12 October case: a kickoff that has passed on a file a day old, the feed
             # still says scheduled
             w("DEN", "SEA", "2026-10-09T20:15", "pre", win="Thursday night", i="4")]
    w2w = {"fetched_at": "2026-10-11T12:00:00Z",
           "weeks": [{"season": 2026, "week": 6, "games": games}]}
    return u, sbd, w2w, games


def truth_canary():
    import build_manifest as bm
    import site_build as sb
    fails = []
    u, sbd, w2w, w2w_games = _fixture(sb)
    was = (sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST)
    try:
        # clock: Sunday 11 October 2026, 9:00 AM ET
        sb._NOW_CACHE = u("2026-10-11T09:00")
        sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE = sbd, w2w, True
        sb.MANIFEST = bm.build(sb._build_now(), sbd, w2w)
        m = sb.MANIFEST
        desig = {"groups": {"Out": ["a", "b"], "Questionable": ["c"]},
                 "last_poll": "2026-10-11T12:00:00Z"}
        pages = {
            "home": sb.render_home([], ""),
            "scores": sb.render_scores_page(sbd, {}, ""),
            "fantasy": sb.render_fantasy_hub(None, desig, {}, None, sbd, ""),
            "where-to-watch": sb.render_where_to_watch(w2w["weeks"][0], w2w["weeks"], "",
                                                       current=True),
        }
        # the manifest itself, against the fixture's own arithmetic
        if m["slate"]["date"]["total"] != 4 or m["date"] != "2026-10-11":
            fails.append(f"truth: the manifest counts {m['slate']['date']['total']} games on "
                         f"{m['date']}, the fixture has 4 on 2026-10-11")
        want = {"home": bm.count_line(m), "scores": bm.count_line(m),
                "fantasy": bm.count_line(m, "NFL")}
        fails += check_agreement(pages, m, want)
        # THE META TEST: a page that changes its own count must fail the suite
        bad = dict(pages)
        bad["scores"] = re.sub(r'(data-mf="count">)[^<]*', r"\g<1>99 games today",
                               pages["scores"], count=1)
        if not check_agreement(bad, m, want):
            fails.append("truth: a Scores page that prints its own count did not fail the agreement test")
        bad = dict(pages)
        bad["home"] = pages["home"].replace('data-mf="stamp">Updated ',
                                            'data-mf="stamp">Updated 1:11 AM ', 1)
        if not check_agreement(bad, m, want):
            fails.append("truth: a home stamp that differs did not fail the agreement test")

        # a scheduled game is never Final: the 12 October case
        sb._NOW_CACHE = u("2026-10-12T09:00")
        late = sb.render_where_to_watch(w2w["weeks"][0], w2w["weeks"], "", current=True)
        fails += check_no_final_for_scheduled(late, w2w_games)
        if "Final" not in visible(late):
            fails.append("truth: the finished game is not printed as Final on Where to Watch")
        sb._NOW_CACHE = u("2026-10-11T09:00")

        # every card dates itself: the Saturday game on a Sunday page
        for name in ("home", "scores"):
            if "Sat Oct 10" not in visible(pages[name]):
                fails.append(f"truth: {name} has no card dated \"Sat Oct 10\"")

        # no game id twice on a page
        for name in ("home", "scores", "fantasy", "where-to-watch"):
            fails += check_unique_ids(name, pages[name])
        twice = pages["home"].replace("</main>", "</main>" + _first_unit(pages["home"]), 1)
        if not check_unique_ids("home", twice):
            fails.append("truth: a doubled game card did not fail the duplicate-id test")

        # the word live
        for name, html in pages.items():
            fails += check_no_live(name, html)
        if not check_no_live("probe", "<p>Live now</p>"):
            fails.append("truth: the word-live test does not see \"Live now\"")
    except Exception as e:
        fails.append(f"truth: the fixture build raised {type(e).__name__}: {e}")
    finally:
        sb._NOW_CACHE, sb.SB_DATA, sb.W2W_DATA, sb.W2W_LIVE, sb.MANIFEST = was

    # the week on the Tuesday boundary, from a fixture clock
    weeks = [{"week": 6, "games": [{"kickoff_utc": "2026-10-08T00:15Z"},
                                   {"kickoff_utc": "2026-10-12T00:15Z"}]},
             {"week": 7, "games": [{"kickoff_utc": "2026-10-16T00:15Z"},
                                   {"kickoff_utc": "2026-10-20T00:15Z"}]},
             {"week": 9, "games": [{"kickoff_utc": "2026-11-01T18:00Z"}]}]
    ET = sb._ET
    cases = [("2026-10-12T23:59", 6, "Monday night"),
             ("2026-10-13T05:59:59", 6, "Tuesday 5:59:59 AM ET"),
             ("2026-10-13T06:00", 7, "Tuesday 6:00:00 AM ET"),
             ("2026-10-13T06:00:01", 7, "Tuesday 6:00:01 AM ET"),
             ("2026-10-14T12:00", 7, "Wednesday"),
             ("2026-11-03T05:59", 9, "Tuesday after DST ends, 5:59 AM EST (no week 8 in the file)")]
    for iso, wk, label in cases:
        now = _d.datetime.fromisoformat(iso).replace(tzinfo=ET)
        got = bm.week_for(now, weeks)
        if got != wk:
            fails.append(f"truth: the week at {label} ({iso} ET) is {got}, expected {wk}")
    return fails


def _first_unit(html):
    """The first top-level game unit's html, for the doubled-card probe."""
    i = html.find('<div class="tk-pair"')
    if i < 0:
        i = html.find('<article class="tk-c')
        j = html.find("</article>", i) + len("</article>")
        return html[i:j]
    depth, k = 0, i
    for mm in re.finditer(r"<div\b|</div>", html[i:]):
        depth += 1 if mm.group(0) == "<div" else -1
        k = i + mm.end()
        if depth == 0:
            break
    return html[i:k]


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    fs = truth_canary()
    for f in fs:
        print("::error::" + f)
    print("TRUTH CANARY: " + ("FAIL" if fs else "PASS"))
    sys.exit(1 if fs else 0)
