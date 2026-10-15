#!/usr/bin/env python3
"""teams.py: the logic behind the team pages (Sprint S-3a, Program 7 section 3).

Pure functions over the desk's own files: no network, no model, no build state, so the canary can
test them on fixtures (teams_canary.py). site_build.py renders; this decides.

THE TOP FORTY PROGRAMS. The AP Top 25 first, in rank order, then the rest of the week board's
college programs by record, best first, until there are forty. Ranked is the poll's judgement and
the board is what the reader can see this week; the order between them is the only editorial call
and it is made here, once, in the open. One page per school: a school that is both ranked and on
the board is one program.

THE CONDITIONS LOG. A game enters the log when the Worker's flags say a number or an alert matters
(wind 15 mph and over, a 40 percent chance of precipitation and over, a feel below 32 or above 90,
an alert). The numbers on a log line are the Worker's own. Past games are not in conditions.json
once the week rolls, so conditions_report.py carries each report's flagged games in its "log"; the
build merges every report's log with the live file, the latest reading of a game winning.
"""

import re


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _pct(rec):
    m = re.match(r"\s*(\d+)-(\d+)(?:-(\d+))?", rec or "")
    if not m:
        return -1.0
    w, l, t = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    n = w + l + t
    return (w + t / 2) / n if n else -1.0


def _teams_on_board(cfb_games):
    for g in cfb_games:
        for side in ("away", "home"):
            t = g.get(side) or {}
            if t.get("school") or t.get("full"):
                yield t


def top_programs(rankings, cfb_games, n=40):
    """The n programs that get a page, as dicts: slug, school, mascot, abbr, id, color, rank,
    previous, trend, record, ranked."""
    by_school, by_abbr = {}, {}
    for t in _teams_on_board(cfb_games):
        by_school[t.get("school") or ""] = t
        by_abbr[t.get("abbr") or ""] = t
    out, seen = [], set()

    def add(school, base, **kw):
        sl = slug(school)
        if not sl or sl in seen:
            return
        seen.add(sl)
        d = {"slug": sl, "school": school, "mascot": base.get("mascot") or "", "abbr": base.get("abbr") or "",
             "id": str(base.get("id") or ""), "color": base.get("color") or "",
             "record": base.get("record") or "", "rank": None, "previous": None, "trend": "", "ranked": False}
        d.update({k: v for k, v in kw.items() if v not in (None, "")})
        out.append(d)

    for r in sorted(((rankings or {}).get("rows") or []), key=lambda r: r.get("rank") or 99):
        school = r.get("school") or ""
        base = dict(by_school.get(school) or by_abbr.get(r.get("abbr") or "") or {})
        base.setdefault("abbr", r.get("abbr"))
        base["mascot"] = base.get("mascot") or r.get("mascot")
        add(school, base, rank=r.get("rank"), previous=r.get("previous"), trend=r.get("trend") or "",
            record=r.get("record") or base.get("record"), ranked=True)
    rest = sorted((t for t in by_school.values() if slug(t.get("school")) not in seen),
                  key=lambda t: (-_pct(t.get("record")), t.get("school") or ""))
    for t in rest:
        if len(out) >= n:
            break
        add(t.get("school"), t)
    return out[:n]


def _kind_tags(e):
    f = (e or {}).get("flags") or {}
    tags = []
    w = f.get("wind") or {}
    if w.get("on"):
        tags.append({"kind": "wind", "text": f"Wind up to {round(w['max_mph'])} mph"})
    p = f.get("precip") or {}
    if p.get("on"):
        tags.append({"kind": "rain", "text": f"{round(p['max_pct'])} percent chance of rain"})
    fe = f.get("feels") or {}
    if fe.get("on"):
        if isinstance(fe.get("min_f"), (int, float)) and fe["min_f"] < fe.get("below_f", 32):
            tags.append({"kind": "cold", "text": f"Feels as cold as {round(fe['min_f'])} degrees"})
        elif isinstance(fe.get("max_f"), (int, float)) and fe["max_f"] > fe.get("above_f", 90):
            tags.append({"kind": "heat", "text": f"Feels as hot as {round(fe['max_f'])} degrees"})
    for a in ((e or {}).get("alerts") or [])[:2]:
        if a.get("event"):
            tags.append({"kind": "alert", "text": str(a["event"])})
    return tags


def bye_weeks(events):
    """The weeks of the season (1 to 18) a team has no fixture, from its fixtures. The feed's own
    "bye" field is wrong for many teams (Chicago's said 7; the week it did not play was 10)."""
    have = {e.get("week") for e in events or [] if e.get("week")}
    if not have:
        return []
    return [w for w in range(1, 19) if w not in have]


def log_entry(g, e):
    """One log line for a game, or None when the Worker's flags say nothing matters. A game under a
    roof is never logged: the weather outside is not the game's weather (S-3a, 15 October)."""
    if not e or e.get("status") != "forecast" or e.get("roof") in ("retractable", "fixed"):
        return None
    tags = _kind_tags(e)
    if not tags:
        return None
    a, h = g.get("away") or {}, g.get("home") or {}
    return {"id": str(g.get("id")), "league": g.get("league"), "start_utc": g.get("start_utc") or "",
            "away": {"abbr": a.get("abbr"), "id": str(a.get("id") or ""), "name": a.get("full") or a.get("name")},
            "home": {"abbr": h.get("abbr"), "id": str(h.get("id") or ""), "name": h.get("full") or h.get("name")},
            "venue": g.get("venue") or "", "tags": tags}


def merge_logs(*lists):
    """Every list's entries, one per game id, the later list's reading winning."""
    by = {}
    for lst in lists:
        for x in lst or []:
            by[x["id"]] = x
    return sorted(by.values(), key=lambda x: (x.get("start_utc") or "", x["id"]))


def team_log(entries, league, abbr=None, tid=None):
    """This team's own entries. NFL matches on the abbreviation, college on the team id: an
    abbreviation is not an identity across leagues (MIA is the Dolphins and the Hurricanes)."""
    out = []
    for x in entries or []:
        if x.get("league") != league:
            continue
        for side in ("away", "home"):
            t = x.get(side) or {}
            if (abbr and t.get("abbr") == abbr and league == "NFL") or (tid and t.get("id") == str(tid)):
                out.append(x)
                break
    return out
